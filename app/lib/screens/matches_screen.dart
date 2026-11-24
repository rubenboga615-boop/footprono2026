import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../desktop/layout.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/install_tip.dart';
import '../widgets/live_chances.dart';
import '../widgets/live_refresh.dart';
import '../widgets/maquette.dart';
import '../widgets/visage.dart';
import 'match_screen.dart';
import 'notifications_screen.dart';
import '../widgets/team_logo.dart';

class MatchesScreen extends StatefulWidget {
  const MatchesScreen({super.key});

  @override
  State<MatchesScreen> createState() => _MatchesScreenState();
}

class _MatchesScreenState extends State<MatchesScreen> {
  String competition = '';
  DateTime? day;

  /// Pastille « ● En direct N » choisie : seulement les matchs en cours (maquette D1).
  bool liveOnly = false;

  Future<(List<Upcoming>, List<MatchInfo>)> _load() async {
    final api = context.read<AppState>().api;
    final results = await Future.wait([
      // Coupes d'Europe et sélections comprises (sans plus/moins 2,5 en coupe).
      api.get('/predictions/upcoming', {'limit': 400, 'cups': 'true', 'nations': 'true'}),
      api.get('/live'),
    ]);
    return (
      [for (final j in results[0] as List) Upcoming(j as Json)],
      [for (final j in results[1] as List) MatchInfo(j as Json)],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        bottom: false,
        child: Loader<(List<Upcoming>, List<MatchInfo>)>(
          load: _load,
          errorHeader: DesktopScope.of(context)
              ? null
              : Row(
                  children: [
                    const Expanded(child: MTitle('Matchs', 'du jour', 26)),
                    _Bell(unread: context.watch<AppState>().unread),
                  ],
                ),
          // Pendant les matchs : mise à jour à chaque relevé du direct (WebSocket, ou
          // /live/feed sans WebSocket), sans recharger la liste (retour du 12/11/2026).
          builder: (context, data, reload) => ValueListenableBuilder<LiveFeed?>(
            valueListenable: context.read<AppState>().liveFeed,
            builder: (context, feed, _) {
              final (loaded, loadedLive) = data;
              final all = [
                for (final u in loaded)
                  feed?.matches.containsKey(u.match.id) == true
                      ? Upcoming.withMatch(u, u.match.withFeed(feed))
                      : u,
              ];
              final loadedIds = {for (final m in loadedLive) m.id};
              // Match commencé depuis le chargement : passe dans « En direct » ; match fini :
              // en sort.
              final live = [
                for (final m in loadedLive)
                  if (m.withFeed(feed).isLive) m.withFeed(feed),
                for (final u in all)
                  if (u.match.isLive && !loadedIds.contains(u.match.id)) u.match,
              ];
              // Un match en cours n'est que dans « En direct » (essai du 07/11/2026 : il apparaissait
              // aussi dans la journée, avec ses chances d'avant le match).
              final liveIds = {for (final m in live) m.id};
              final upcoming = [
                for (final u in all)
                  if (!liveIds.contains(u.match.id) && !u.match.isLive) u,
              ];
              final days = <DateTime>{for (final u in upcoming) _day(u.match.date)}.toList()..sort();
              final selectedDay = day != null && days.contains(day)
                  ? day
                  : (days.isEmpty ? null : days.first);
              // Filtres par importance (5 grands d'abord), matchs par heure de coup d'envoi : le
              // prochain match en premier (essai réel du 06/11/2026 : rangés par championnat, les
              // heures se mélangeaient). Le championnat reste écrit sur chaque match.
              final comps = <String>{for (final u in upcoming) u.match.competition}.toList()
                ..sort((a, b) => competitionRank(a).compareTo(competitionRank(b)));
              final shown =
                  upcoming
                      .where((u) => _keep(u.match, context))
                      .where((u) => selectedDay == null || _day(u.match.date) == selectedDay)
                      .toList()
                    ..sort((a, b) {
                      // Heure du coup d'envoi (``date`` n'est que le jour : avec elle, les matchs
                      // d'un même jour restaient rangés par championnat, essai du 08/11/2026).
                      final t = (a.match.kickoffAt ?? a.match.date).compareTo(
                        b.match.kickoffAt ?? b.match.date,
                      );
                      return t != 0
                          ? t
                          : competitionRank(a.match.competition)
                                .compareTo(competitionRank(b.match.competition));
                    });
              final today = _day(DateTime.now());
              final desk = DesktopScope.of(context);
              return LiveWatch(
                active: live.isNotEmpty || all.any((u) => u.match.liveSoon),
                child: RefreshIndicator(
                  onRefresh: reload,
                  child: ListView(
                    padding: pagePadding(context, 18, 120, maxWidth: 1040),
                    children: [
                      // Ordinateur : logo, classements et notifications sont dans le menu de gauche.
                      // Téléphone (maquette validée le 07/11/2026) : le titre seul, puis une rangée de
                      // petites pastilles (jours, puis « Tous championnats ▾ »).
                      const InstallTip(margin: EdgeInsets.only(bottom: 14)),
                      if (desk) ...[
                        TwoToneTitle('Matchs', selectedDay == today ? 'du jour' : 'à venir'),
                        const SizedBox(height: 16),
                        if (days.isNotEmpty) ...[
                          ChipRow(
                            labels: [for (final d in days) shortDate(d)],
                            selected: days.indexOf(selectedDay!),
                            onSelected: (i) => setState(() => day = days[i]),
                          ),
                          const SizedBox(height: 8),
                        ],
                        ChipRow(
                          labels: ['Toutes', for (final c in comps) competitionName(c)],
                          selected: competition.isEmpty ? 0 : comps.indexOf(competition) + 1,
                          onSelected: (i) => setState(() => competition = i == 0 ? '' : comps[i - 1]),
                        ),
                        const SizedBox(height: 16),
                      ] else ...[
                        // Maquette 6 du nouveau visage : titre et « ● En direct N », jours en
                        // pastilles, puis Tous · Suivis · championnats sur une ligne.
                        Row(
                          children: [
                            Expanded(
                              child: Text('Matchs', style: V.t(24, w: FontWeight.w800, ls: -0.4)),
                            ),
                            if (live.isNotEmpty)
                              GestureDetector(
                                onTap: () => setState(() => liveOnly = !liveOnly),
                                child: Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                                  decoration: BoxDecoration(
                                    color: liveOnly ? V.vi : V.vi3,
                                    borderRadius: BorderRadius.circular(999),
                                  ),
                                  child: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      const VDot(),
                                      const SizedBox(width: 6),
                                      Text(
                                        'En direct ${live.length}',
                                        style: V.t(
                                          12.5,
                                          w: FontWeight.w700,
                                          color: liveOnly ? Colors.white : V.vi2,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        if (days.isNotEmpty)
                          VTabs(
                            items: [for (final d in days) dayChip(d)],
                            selected: liveOnly && live.isNotEmpty ? -1 : days.indexOf(selectedDay!),
                            onSelect: (i) => setState(() {
                              day = days[i];
                              liveOnly = false;
                            }),
                          ),
                        const SizedBox(height: 8),
                        VTabs(
                          items: ['Tous', 'Suivis', for (final c in comps) competitionName(c)],
                          icons: const {1: VIcon.star},
                          selected: competition.isEmpty
                              ? 0
                              : competition == _followed
                              ? 1
                              : comps.indexOf(competition) + 2,
                          onSelect: (i) => setState(
                            () => competition = switch (i) {
                              0 => '',
                              1 => _followed,
                              _ => comps[i - 2],
                            },
                          ),
                        ),
                        if (competition == _followed && context.watch<AppState>().followed.isEmpty)
                          Padding(
                            padding: const EdgeInsets.only(top: 12),
                            child: Text(
                              'Aucune équipe suivie : ouvre la fiche d\'une équipe et touche « Suivre ».',
                              style: V.mu_(12.5),
                            ),
                          ),
                      ],
                      if (live.isNotEmpty && desk) ...[
                        const SectionTitle('En direct'),
                        _MatchTable([for (final m in live) Upcoming.of(m)]),
                        const SectionTitle('À venir'),
                      ],
                      if (desk)
                        shown.isEmpty
                            ? const EmptyState(
                                'Aucun match à venir pour ce filtre.',
                                icon: Icons.event_busy_rounded,
                              )
                            : _MatchTable(shown)
                      else if (shown.isEmpty && live.isEmpty)
                        // Maquette N15.
                        const EmptyState(
                          'Pas de match pour ce filtre.\nAucun championnat choisi ne joue ce jour-là.',
                          icon: Icons.event_busy_rounded,
                        )
                      else
                        // En direct d'abord (cartes vertes), puis les matchs du jour choisi ; la
                        // pastille « En direct » ne garde que les matchs en cours.
                        _CompactList([
                          for (final m in live)
                            if (_keep(m, context)) _withSummary(m, all),
                          if (!(liveOnly && live.isNotEmpty)) ...shown,
                        ], feed: feed),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }

  static DateTime _day(DateTime d) => DateTime(d.year, d.month, d.day);

  /// Filtre « Suivis » (équipes suivies, maquettes 6 et 26).
  static const _followed = '*suivis*';

  bool _keep(MatchInfo m, BuildContext context) {
    if (competition.isEmpty) return true;
    if (competition == _followed) {
      final f = context.read<AppState>().followed;
      return f.contains(m.home.id) || f.contains(m.away.id);
    }
    return m.competition == competition;
  }

  /// Match en cours avec ses chances d'avant le match (pour « avant le match : … »).
  static Upcoming _withSummary(MatchInfo m, List<Upcoming> all) {
    final u = all.where((u) => u.match.id == m.id).firstOrNull;
    return u == null ? Upcoming.of(m) : Upcoming.withMatch(u, m);
  }
}

/// Téléphone : maquette C1 validée le 07/11/2026 (docs/maquettes/2-corrigees/C1.html), une
/// carte par match : championnat et jour, les deux équipes avec leur logo, l'heure (ou le
/// score et la minute en direct), puis les chances 1 / N / 2 du moteur avec la cote 1xBet en
/// dessous ; l'issue la plus probable encadrée (pas un conseil de pari). Un appui ouvre le match.
class _CompactList extends StatefulWidget {
  const _CompactList(this.rows, {this.feed});
  final List<Upcoming> rows;

  /// Relevés du direct : buts, cartons rouges et chances des matchs en cours.
  final LiveFeed? feed;

  @override
  State<_CompactList> createState() => _CompactListState();
}

class _CompactListState extends State<_CompactList> {
  Map<int, Map<String, Offer>> offers = {};

  /// Cotes en plus de 1, N, 2 par match (« +86 › », maquette 6).
  Map<int, int> counts = {};
  String _loaded = '';
  bool loading = true;

  // Matchs en cours (maquette D1) : buts et cartons rouges, chances en direct (si publiées),
  // matchs de mes paris en cours (★, en haut).
  Map<int, Json> summaries = {};
  Map<int, Json> chances = {};
  Set<int> mine = {};
  String _liveLoaded = '';

  @override
  void initState() {
    super.initState();
    _load();
    _loadLive();
  }

  @override
  void didUpdateWidget(_CompactList old) {
    super.didUpdateWidget(old);
    _load();
    _loadLive();
  }

  Future<void> _loadLive() async {
    final ids = [
      for (final u in widget.rows)
        if (u.match.isLive) u.match.id,
    ];
    // Chargés une fois par ensemble de matchs en cours ; ensuite, les relevés du direct
    // les tiennent à jour (retour du 12/11/2026 : pas de requête à chaque relevé).
    final sig = ids.join(',');
    if (ids.isEmpty || sig == _liveLoaded) return;
    _liveLoaded = sig;
    final state = context.read<AppState>();
    final api = state.api;
    try {
      // Matchs déjà relevés par le direct : buts et chances viennent du relevé.
      final missing = [
        for (final i in ids)
          if (widget.feed?.matches.containsKey(i) != true) i,
      ];
      final r = missing.isEmpty
          ? const <String, dynamic>{}
          : await api.get('/live/summary?${missing.map((i) => 'match_ids=$i').join('&')}') as Json;
      final c = await loadLiveChances(api, missing);
      var my = <int>{};
      if (state.loggedIn) {
        final bets = await api.get('/bets', {'limit': 100}) as List;
        my = {
          for (final b in bets.cast<Json>())
            if (b['status'] == 'open')
              for (final s in (b['selections'] as List).cast<Json>()) s['match_id'] as int,
        };
      }
      if (!mounted || sig != _liveLoaded) return;
      setState(() {
        summaries = {for (final e in r.entries) int.parse(e.key): e.value as Json};
        chances = c;
        mine = my;
      });
    } on Object {
      // Détails du direct indisponibles : la carte garde le score et la minute.
    }
  }

  /// Cotes des matchs affichés, en un seul appel ; sans cotes, seules les chances s'affichent.
  Future<void> _load() async {
    // Match commencé : les cotes d'avant le match ne sont plus jouables, pas affichées.
    final ids = [
      for (final u in widget.rows.take(80))
        if (!u.match.started) u.match.id,
    ];
    final sig = ids.join(',');
    if (sig == _loaded) return;
    _loaded = sig;
    if (ids.isEmpty) {
      setState(() => loading = false);
      return;
    }
    setState(() => loading = true);
    try {
      final api = context.read<AppState>().api;
      final (j, c) = await (
        api.get('/offers/main', {'match_ids': ids}),
        api.get('/offers/counts', {'match_ids': ids}).catchError((Object _) => <String, dynamic>{}),
      ).wait;
      if (!mounted || sig != _loaded) return;
      setState(() {
        offers = {
          for (final e in (j as Json).entries)
            int.parse(e.key): {for (final o in (e.value as List).cast<Json>()) Offer(o).key: Offer(o)},
        };
        counts = {for (final e in (c as Json).entries) int.parse(e.key): (e.value as num).toInt()};
      });
    } on Object {
      // Cotes indisponibles : seules les chances sont affichées.
    } finally {
      if (mounted && sig == _loaded) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      // Maquette N14 : les chances d'abord, « … » à la place des cotes en attendant.
      if (loading && widget.rows.any((u) => !u.match.started))
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text('Chargement des cotes…', style: Fp.body(12, color: Fp.muted)),
        ),
      for (final u in _ordered())
        _MatchCard(
          u,
          offers[u.match.id] ?? const {},
          more: counts[u.match.id],
          loading: loading,
          summary: _summary(u.match.id),
          chances: _chances(u.match.id),
          mine: mine.contains(u.match.id),
        ),
    ],
  );

  // Dernier relevé du direct s'il y en a un, sinon ce qui a été chargé.
  Json? _summary(int id) {
    final f = widget.feed?.matches[id];
    return f == null ? summaries[id] : {'goals': f['goals'] ?? const [], 'reds': f['reds'] ?? const []};
  }

  Json? _chances(int id) =>
      widget.feed?.matches.containsKey(id) == true ? widget.feed!.chancesOf(id) : chances[id];

  /// Matchs en cours de mes paris d'abord (★), l'ordre reçu sinon.
  List<Upcoming> _ordered() {
    final rows = widget.rows;
    if (mine.isEmpty) return rows;
    bool first(Upcoming u) => u.match.isLive && mine.contains(u.match.id);
    return [...rows.where(first), ...rows.where((u) => !first(u))];
  }
}

/// « 23' Calvert-Lewin · 51' Son · carton rouge 81' Udinese » (maquette D1 ; sans emoji
/// depuis l'étape A du nouveau visage, 20/11/2026).
String liveFacts(Json? summary, MatchInfo m) {
  if (summary == null) return '';
  String when(Json e) {
    final extra = e['extra'] as int?;
    return '${e['minute'] ?? ''}${extra != null && extra > 0 ? '+$extra' : ''}\'';
  }

  String who(Json e) => '${e['player'] ?? (e['side'] == 'away' ? m.away.name : m.home.name)}';
  final items = [
    for (final g in (summary['goals'] as List? ?? const []).cast<Json>())
      (g['minute'] as int? ?? 0, '${when(g)} ${who(g)}${g['own_goal'] == true ? ' (c.s.c.)' : ''}'),
    for (final r in (summary['reds'] as List? ?? const []).cast<Json>())
      (r['minute'] as int? ?? 0, 'carton rouge ${when(r)} ${who(r)}'),
  ]..sort((a, b) => a.$1.compareTo(b.$1));
  return items.map((i) => i.$2).join(' · ');
}

class _MatchCard extends StatelessWidget {
  const _MatchCard(
    this.u,
    this.offers, {
    this.more,
    this.loading = false,
    this.summary,
    this.chances,
    this.mine = false,
  });
  final Upcoming u;
  final Map<String, Offer> offers;

  /// Nombre de cotes en plus de 1, N, 2 (null : inconnu).
  final int? more;
  final bool loading;

  /// En direct : buts et cartons rouges (`/live/summary`), chances du moment (si publiées).
  final Json? summary;
  final Json? chances;

  /// Match d'un de mes paris en cours (★).
  final bool mine;

  @override
  Widget build(BuildContext context) {
    final m = u.match, s = u.summary;
    final live = m.isLive;
    final before = s == null ? null : [s.home.probability, s.draw.probability, s.away.probability];
    final liveMarkets = chances?['markets'] as Map?;
    final now = [
      for (final k in const ['1X2||home', '1X2||draw', '1X2||away']) (liveMarkets?[k] as num?)?.toDouble(),
    ];
    void open() => Navigator.of(context).push(MaterialPageRoute(builder: (_) => MatchScreen(matchId: m.id)));
    final comp = competitionName(m.competition).toUpperCase();

    // Maquette 6, match en cours : carte compacte (minute, score, issue la plus probable).
    if (live) {
      final probs = now.contains(null) ? null : now.cast<double>();
      String? best;
      if (probs != null) {
        final i = probs.indexOf(probs.reduce(math.max));
        best = '${['${m.home.name} gagne', 'nul', '${m.away.name} gagne'][i]} ${percent(probs[i])}';
      }
      return VCard(
        onTap: open,
        child: Semantics(
          button: true,
          label: '${m.home.name} – ${m.away.name}, en direct ${m.clock}, ouvrir le match',
          excludeSemantics: true,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  const VDot(),
                  const SizedBox(width: 4),
                  Text(
                    m.clock.isEmpty ? 'En direct' : m.clock,
                    style: V.t(11.5, w: FontWeight.w800, color: V.mint),
                  ),
                  Expanded(
                    child: Text(
                      ' · ${mine ? '★ ' : ''}$comp',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: V.mu_(),
                    ),
                  ),
                  Text(m.liveHome == null ? '–' : '${m.liveHome} – ${m.liveAway}', style: V.b()),
                ],
              ),
              const SizedBox(height: 6),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${m.home.name} – ${m.away.name}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: V.b(),
                    ),
                  ),
                  if (best != null) Text(best, style: V.t(12.5, color: V.mu)),
                ],
              ),
              // Buteurs et cartons rouges (maquette D1, demandés par le testeur le 10/11).
              if (liveFacts(summary, m).isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    liveFacts(summary, m),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: V.mu_(),
                  ),
                ),
            ],
          ),
        ),
      );
    }

    // Maquette 6, match à venir : championnat et heure, pastille moteur contre cote, équipes et
    // chances, barre 1-N-2, cotes en boutons de 44.
    const keys = ['1X2||home', '1X2||draw', '1X2||away'];
    (double, double)? gap; // (moteur, cote) de l'écart le plus grand
    for (final o in offers.values) {
      final p = o.modelProbability;
      if (p == null || o.odds <= 1) continue;
      if (gap == null || p - 1 / o.odds > gap.$1 - gap.$2) gap = (p, 1 / o.odds);
    }
    final state = context.watch<AppState>();
    final when = m.awaitingKickoff
        ? 'COUP D\'ENVOI IMMINENT'
        : m.kickoffDelayed
        ? 'RETARDÉ'
        : m.when; // le jour est dans la pastille choisie (maquette 6 : « LIGA · 20:00 »)
    Widget team(Team t, double? p, double top) => Padding(
      padding: EdgeInsets.only(top: top),
      child: Row(
        children: [
          VTeamBadge(t.code),
          const SizedBox(width: 10),
          Expanded(
            child: Text(t.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: V.b(15)),
          ),
          if (p != null) Text(percent(p), style: V.b(15)),
        ],
      ),
    );
    return VCard(
      onTap: open,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Semantics(
            button: true,
            label: [
              '${m.home.name} – ${m.away.name}',
              when,
              if (before != null) '1 ${percent(before[0])}, N ${percent(before[1])}, 2 ${percent(before[2])}',
              'ouvrir le match',
            ].join(', '),
            excludeSemantics: true,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        '${mine ? '★ ' : ''}$comp · $when',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: V.mu_(12.5),
                      ),
                    ),
                    if (gap != null)
                      VGapChip(engine: gap.$1, implied: gap.$2, nation: isNation(m.competition)),
                  ],
                ),
                team(m.home, before?[0], 8),
                team(m.away, before?[2], 6),
                if (before != null) VBar3(before[0], before[1], before[2]),
              ],
            ),
          ),
          if (keys.any(offers.containsKey))
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Row(
                children: [
                  for (final (i, k) in keys.indexed) ...[
                    if (i > 0) const SizedBox(width: 6),
                    if (offers[k] case final o?)
                      Semantics(
                        button: true,
                        label: 'cote ${const ['1', 'N', '2'][i]} ${odds(o.odds)}, ajouter au coupon',
                        child: VOdd(
                          odds(o.odds),
                          label: const ['1', 'N', '2'][i],
                          on: state.coupon.any((c) => c.match.id == m.id && c.offer.key == o.key),
                          onTap: () {
                            final msg = state.toggleCoupon(m, o);
                            ScaffoldMessenger.of(context)
                              ..hideCurrentSnackBar()
                              ..showSnackBar(
                                SnackBar(content: Text(msg), duration: const Duration(seconds: 2)),
                              );
                          },
                        ),
                      ),
                  ],
                  const Spacer(),
                  VLink(more == null ? 'Toutes les cotes ›' : '+$more ›', onTap: open),
                ],
              ),
            )
          else if (loading)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Text('Cotes…', style: V.mu_()),
            ),
        ],
      ),
    );
  }
}

/// Version ordinateur : un tableau, une ligne par match, une colonne par marché.
/// Plus la case est violette, plus le moteur juge l'issue probable ; dessous, la cote réelle.
/// Un clic sur une cote l'ajoute au coupon, un clic ailleurs ouvre le match.
class _MatchTable extends StatefulWidget {
  const _MatchTable(this.rows);
  final List<Upcoming> rows;

  static const cellWidth = 76.0;
  static const keys = ['1X2||home', '1X2||draw', '1X2||away', 'OU|2.5|over', 'BTTS||yes'];

  @override
  State<_MatchTable> createState() => _MatchTableState();
}

class _MatchTableState extends State<_MatchTable> {
  Map<int, Map<String, Offer>> offers = {};
  String _loaded = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(_MatchTable old) {
    super.didUpdateWidget(old);
    _load();
  }

  /// Cotes des matchs affichés (un seul appel ; sans cotes, le tableau garde les probabilités).
  Future<void> _load() async {
    // Match commencé : les cotes d'avant le match ne sont plus jouables, pas affichées.
    final ids = [
      for (final u in widget.rows.take(80))
        if (!u.match.started) u.match.id,
    ];
    final sig = ids.join(',');
    if (sig == _loaded || ids.isEmpty) return;
    _loaded = sig;
    try {
      final j = await context.read<AppState>().api.get('/offers/main', {'match_ids': ids}) as Json;
      if (!mounted || sig != _loaded) return;
      setState(
        () => offers = {
          for (final e in j.entries)
            int.parse(e.key): {for (final o in (e.value as List).cast<Json>()) Offer(o).key: Offer(o)},
        },
      );
    } on Object {
      // Cotes indisponibles : seules les probabilités sont affichées.
    }
  }

  @override
  Widget build(BuildContext context) {
    final sorted = [...widget.rows]
      ..sort((a, b) {
        final c = competitionName(a.match.competition).compareTo(competitionName(b.match.competition));
        return c != 0 ? c : a.match.date.compareTo(b.match.date);
      });
    Widget head(String t, {double? width}) => SizedBox(
      width: width ?? _MatchTable.cellWidth,
      child: Text(
        t,
        textAlign: TextAlign.center,
        style: Fp.body(11.5, color: Fp.text3, weight: FontWeight.w700),
      ),
    );
    String? comp;
    return GlassCard.section(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              const SizedBox(width: 56),
              Expanded(
                child: Text(
                  'Match',
                  style: Fp.body(11.5, color: Fp.text3, weight: FontWeight.w700),
                ),
              ),
              head('1'),
              head('N'),
              head('2'),
              head('+2,5 buts'),
              head('Les deux\nmarquent'),
              head('Buts\nattendus', width: 86),
            ],
          ),
          const SizedBox(height: 4),
          for (final u in sorted) ...[
            if (u.match.competition != comp)
              Padding(
                padding: const EdgeInsets.fromLTRB(4, 12, 4, 6),
                child: Text(
                  competitionName(comp = u.match.competition).toUpperCase(),
                  style: Fp.body(11, color: Fp.accentLight, weight: FontWeight.w700),
                ),
              ),
            _MatchRow(u, offers[u.match.id] ?? const {}),
          ],
          const SizedBox(height: 10),
          Text(
            'En haut, la probabilité du moteur ; en bas, la cote réelle (1xBet, Bet365 en secours). '
            'Clique sur une cote pour l\'ajouter au coupon, sur le match pour l\'ouvrir. '
            'La probabilité du moteur est une information, pas un conseil de pari.',
            style: Fp.body(11.5, color: Fp.text3, height: 1.4),
          ),
        ],
      ),
    );
  }
}

class _MatchRow extends StatelessWidget {
  const _MatchRow(this.u, this.offers);
  final Upcoming u;
  final Map<String, Offer> offers;

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final m = u.match, s = u.summary;
    final probs = [
      s?.home.probability,
      s?.draw.probability,
      s?.away.probability,
      s?.over25?.probability,
      s?.btts?.probability,
    ];
    void open() => Navigator.of(context).push(MaterialPageRoute(builder: (_) => MatchScreen(matchId: m.id)));
    Widget cell(double? p, Offer? o) {
      final chosen = o != null && state.inCoupon(m.id, o.key);
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 3),
        child: Material(
          color: p == null ? Fp.fill : Fp.accentAlpha(((p - 0.15) / 1.1).clamp(0.0, 0.6)),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(9),
            side: BorderSide(color: chosen ? Fp.accentLight : Colors.transparent, width: 1.5),
          ),
          child: InkWell(
            borderRadius: BorderRadius.circular(9),
            onTap: o == null ? open : () => addToCoupon(context, m, o),
            child: SizedBox(
              width: _MatchTable.cellWidth - 6,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Column(
                  children: [
                    Text(p == null ? '—' : chancePercent(p), style: Fp.title(14, weight: FontWeight.w600)),
                    Text(
                      o == null ? ' ' : odds(o.odds),
                      style: Fp.body(11.5, color: chosen ? Fp.text : Fp.text2, weight: FontWeight.w600),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
    }

    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: open,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Row(
            children: [
              SizedBox(
                width: 56,
                child: m.isLive
                    ? Tag(m.when, color: Fp.win)
                    : Text(
                        m.when,
                        style: Fp.body(13, color: Fp.text3, weight: FontWeight.w600),
                      ),
              ),
              Expanded(
                child: Row(
                  children: [
                    TeamLogo(m.home, size: 30),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            m.home.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Fp.body(13.5, weight: FontWeight.w700),
                          ),
                          Text(
                            m.away.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Fp.body(13.5, color: Fp.text2, weight: FontWeight.w600),
                          ),
                        ],
                      ),
                    ),
                    if (m.score != null)
                      Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: Text(m.score!, style: Fp.title(16)),
                      ),
                  ],
                ),
              ),
              for (final (i, k) in _MatchTable.keys.indexed) cell(probs[i], offers[k]),
              SizedBox(
                width: 86,
                child: Text(
                  switch ((s?.xgHome, s?.xgAway)) {
                    (final double h, final double a) => '${decimal(h, max: 1)} - ${decimal(a, max: 1)}',
                    _ => '—',
                  },
                  textAlign: TextAlign.center,
                  style: Fp.body(13, color: Fp.textSoft, weight: FontWeight.w600),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Cloche des notifications, avec le nombre de non lues.
class _Bell extends StatelessWidget {
  const _Bell({required this.unread});
  final int unread;

  @override
  Widget build(BuildContext context) => IconButton(
    tooltip: unread > 0 ? 'Notifications, $unread non lues' : 'Notifications',
    onPressed: () =>
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => const NotificationsScreen())),
    icon: Badge(
      isLabelVisible: unread > 0,
      label: Text(unread > 99 ? '99+' : '$unread'),
      backgroundColor: Fp.accent,
      child: const Icon(Icons.notifications_none_rounded, color: Fp.text),
    ),
  );
}
