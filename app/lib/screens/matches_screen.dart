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
import '../widgets/maquette.dart';
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
          builder: (context, data, reload) {
            final (all, live) = data;
            // Un match en cours n'est que dans « En direct » (essai du 07/11/2026 : il apparaissait
            // aussi dans la journée, avec ses chances d'avant le match).
            final liveIds = {for (final m in live) m.id};
            final upcoming = [
              for (final u in all)
                if (!liveIds.contains(u.match.id) && !u.match.isLive) u,
            ];
            final days = <DateTime>{for (final u in upcoming) _day(u.match.date)}.toList()..sort();
            final selectedDay = day != null && days.contains(day) ? day : (days.isEmpty ? null : days.first);
            // Filtres par importance (5 grands d'abord), matchs par heure de coup d'envoi : le
            // prochain match en premier (essai réel du 06/11/2026 : rangés par championnat, les
            // heures se mélangeaient). Le championnat reste écrit sur chaque match.
            final comps = <String>{for (final u in upcoming) u.match.competition}.toList()
              ..sort((a, b) => competitionRank(a).compareTo(competitionRank(b)));
            final shown =
                upcoming
                    .where((u) => competition.isEmpty || u.match.competition == competition)
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
            return RefreshIndicator(
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
                    // Cloche des notifications (revue du 07/11/2026 : seulement dans le profil).
                    Row(
                      children: [
                        Expanded(child: MTitle('Matchs', selectedDay == today ? 'du jour' : 'à venir', 26)),
                        _Bell(unread: context.watch<AppState>().unread),
                      ],
                    ),
                    const SizedBox(height: 12),
                    // Jours qui défilent ; « Championnats ▾ » toujours visible à droite.
                    Row(
                      children: [
                        Expanded(
                          child: SingleChildScrollView(
                            scrollDirection: Axis.horizontal,
                            child: Row(
                              children: [
                                for (final d in days) ...[
                                  MChip(
                                    dayChip(d),
                                    selected: d == selectedDay,
                                    onTap: () => setState(() => day = d),
                                  ),
                                  const SizedBox(width: 6),
                                ],
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(width: 6),
                        MChip(
                          '${competition.isEmpty ? 'Championnats' : competitionName(competition)} ▾',
                          selected: competition.isNotEmpty,
                          onTap: () => _pickCompetition(context, comps),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Text(
                      'Encadré : l\'issue la plus probable selon le moteur, pas un conseil de pari. '
                      'En dessous : la cote 1xBet.',
                      style: Fp.body(12, color: Fp.muted, height: 1.35),
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
                    // En direct d'abord (cartes vertes), puis les matchs du jour choisi.
                    _CompactList([for (final m in live) Upcoming.of(m), ...shown]),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  static DateTime _day(DateTime d) => DateTime(d.year, d.month, d.day);

  /// « Tous championnats ▾ » : liste des championnats du jour choisi.
  Future<void> _pickCompetition(BuildContext context, List<String> comps) async {
    final choice = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Fp.background,
      builder: (context) => SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.7),
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
            children: [
              Text('Championnat', style: Fp.title(17)),
              const SizedBox(height: 6),
              for (final c in ['', ...comps])
                InkWell(
                  onTap: () => Navigator.pop(context, c),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 11),
                    child: Text(
                      c.isEmpty ? 'Tous championnats' : competitionName(c),
                      style: Fp.body(
                        14,
                        weight: c == competition ? FontWeight.w800 : FontWeight.w500,
                        color: c == competition ? Fp.text : Fp.textSoft,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
    if (choice != null) setState(() => competition = choice);
  }
}

/// Téléphone : maquette C1 validée le 07/11/2026 (docs/maquettes/2-corrigees/C1.html), une
/// carte par match : championnat et jour, les deux équipes avec leur logo, l'heure (ou le
/// score et la minute en direct), puis les chances 1 / N / 2 du moteur avec la cote 1xBet en
/// dessous ; l'issue la plus probable encadrée (pas un conseil de pari). Un appui ouvre le match.
class _CompactList extends StatefulWidget {
  const _CompactList(this.rows);
  final List<Upcoming> rows;

  @override
  State<_CompactList> createState() => _CompactListState();
}

class _CompactListState extends State<_CompactList> {
  Map<int, Map<String, Offer>> offers = {};
  String _loaded = '';
  bool loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(_CompactList old) {
    super.didUpdateWidget(old);
    _load();
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
      final j = await context.read<AppState>().api.get('/offers/main', {'match_ids': ids}) as Json;
      if (!mounted || sig != _loaded) return;
      setState(
        () => offers = {
          for (final e in j.entries)
            int.parse(e.key): {for (final o in (e.value as List).cast<Json>()) Offer(o).key: Offer(o)},
        },
      );
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
      for (final u in widget.rows) _MatchCard(u, offers[u.match.id] ?? const {}, loading: loading),
    ],
  );
}

/// « Aujourd'hui », « Demain », « Lun. 9 ».
String _dayLabel(DateTime d) {
  final now = DateTime.now();
  final day = DateTime(d.year, d.month, d.day);
  final today = DateTime(now.year, now.month, now.day);
  final diff = day.difference(today).inDays;
  return diff == 0 ? 'Aujourd\'hui' : (diff == 1 ? 'Demain' : dayChip(day));
}

class _MatchCard extends StatelessWidget {
  const _MatchCard(this.u, this.offers, {this.loading = false});
  final Upcoming u;
  final Map<String, Offer> offers;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final m = u.match, s = u.summary;
    final live = m.isLive;
    final probs = s == null ? null : [s.home.probability, s.draw.probability, s.away.probability];
    final best = probs == null ? -1 : probs.indexOf(probs.reduce((a, b) => a > b ? a : b));
    const keys = ['1X2||home', '1X2||draw', '1X2||away'];
    Widget team(Team t) => Row(
      children: [
        TeamLogo(t, size: 24),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            t.name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Fp.body(15, weight: FontWeight.w700),
          ),
        ),
      ],
    );
    Widget box(int i) {
      final o = offers[keys[i]];
      final on = i == best;
      return Expanded(
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 2),
          decoration: BoxDecoration(
            color: on ? Fp.cardHigh : Fp.fill,
            borderRadius: BorderRadius.circular(12),
            border: on ? Border.all(color: Fp.accent2, width: 1.5) : null,
          ),
          child: Column(
            children: [
              Text(const ['1', 'N', '2'][i], style: Fp.body(11, color: Fp.muted)),
              Text(probs == null ? '—' : percent(probs[i]), style: Fp.body(15, weight: FontWeight.w700)),
              Text(
                o != null ? odds(o.odds) : (loading && !m.started ? '…' : ' '),
                style: Fp.body(11, color: Fp.textSoft),
              ),
            ],
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(top: 9),
      child: Material(
        color: Fp.card,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: live ? const BorderSide(color: Color(0xFF1F5B3A)) : BorderSide.none,
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () =>
              Navigator.of(context).push(MaterialPageRoute(builder: (_) => MatchScreen(matchId: m.id))),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 11, 12, 11),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        competitionName(m.competition),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Fp.body(12, color: Fp.muted),
                      ),
                    ),
                    if (live)
                      Text(
                        '● En direct',
                        style: Fp.body(12, color: Fp.win, weight: FontWeight.w700),
                      )
                    else
                      Text(_dayLabel((m.kickoffAt ?? m.date).toLocal()), style: Fp.body(12, color: Fp.muted)),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: Column(children: [team(m.home), const SizedBox(height: 6), team(m.away)]),
                    ),
                    const SizedBox(width: 10),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          live ? (m.liveHome == null ? '–' : '${m.liveHome} – ${m.liveAway}') : m.when,
                          style: Fp.body(20, weight: FontWeight.w700),
                        ),
                        if (live)
                          Text(
                            m.clock,
                            style: Fp.body(12, color: Fp.win, weight: FontWeight.w700),
                          ),
                      ],
                    ),
                  ],
                ),
                // En direct : le score et la minute ; les chances d'avant le match n'y ont plus de sens.
                if (!live) ...[
                  const SizedBox(height: 10),
                  Row(children: [box(0), const SizedBox(width: 6), box(1), const SizedBox(width: 6), box(2)]),
                ],
              ],
            ),
          ),
        ),
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
                    Text(p == null ? '—' : percent(p), style: Fp.title(14, weight: FontWeight.w600)),
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
