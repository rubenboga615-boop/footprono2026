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
import 'match_screen.dart';
import 'merited_screen.dart';
import 'notifications_screen.dart';

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
    final state = context.watch<AppState>();
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        bottom: false,
        child: Loader<(List<Upcoming>, List<MatchInfo>)>(
          load: _load,
          builder: (context, data, reload) {
            final (upcoming, live) = data;
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
                padding: pagePadding(context, 26, 120, maxWidth: 1040),
                children: [
                  // Ordinateur : logo, classements et notifications sont dans le menu de gauche.
                  if (!desk)
                    Row(
                      children: [
                        const FpLogo(),
                        const Spacer(),
                        SquareButton(
                          icon: Icons.leaderboard_rounded,
                          tooltip: 'Classement mérité',
                          onTap: () =>
                              Navigator.of(context)
                                  .push(MaterialPageRoute(builder: (_) => const MeritedScreen())),
                        ),
                        const SizedBox(width: 10),
                        SquareButton(
                          icon: Icons.notifications_none_rounded,
                          tooltip: 'Notifications',
                          dot: state.unread > 0,
                          onTap: () =>
                              Navigator.of(context)
                                  .push(MaterialPageRoute(builder: (_) => const NotificationsScreen())),
                        ),
                      ],
                    ),
                  if (!desk) const SizedBox(height: 16),
                  const InstallTip(margin: EdgeInsets.only(bottom: 14)),
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
                  if (live.isNotEmpty) ...[
                    const SectionTitle('En direct'),
                    if (desk)
                      _MatchTable([for (final m in live) Upcoming.of(m)])
                    else
                      _CompactList([for (final m in live) Upcoming.of(m)]),
                    const SectionTitle('À venir'),
                  ],
                  if (shown.isEmpty)
                    const EmptyState('Aucun match à venir pour ce filtre.', icon: Icons.event_busy_rounded)
                  else if (desk)
                    _MatchTable(shown)
                  else
                    _CompactList(shown),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  static DateTime _day(DateTime d) => DateTime(d.year, d.month, d.day);
}

/// Téléphone (maquette validée le 07/11/2026) : une ligne par match, rangés par heure, avec la
/// chance selon le moteur et, dessous, la cote du bookmaker ; l'issue la plus probable selon le
/// moteur est encadrée (pas un conseil de pari). Un appui ouvre le match.
class _CompactList extends StatefulWidget {
  const _CompactList(this.rows);
  final List<Upcoming> rows;

  @override
  State<_CompactList> createState() => _CompactListState();
}

class _CompactListState extends State<_CompactList> {
  Map<int, Map<String, Offer>> offers = {};
  String _loaded = '';

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
    final ids = [for (final u in widget.rows.take(80)) u.match.id];
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
      // Cotes indisponibles : seules les chances sont affichées.
    }
  }

  static const _box = 54.0;

  @override
  Widget build(BuildContext context) {
    Widget head(String t) => SizedBox(
      width: _box,
      child: Text(
        t,
        textAlign: TextAlign.center,
        style: Fp.body(11.5, color: Fp.text3, weight: FontWeight.w700),
      ),
    );
    final hasOdds = offers.isNotEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        GlassCard.section(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.fromLTRB(12, 8, 10, 4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  const SizedBox(width: 46),
                  Expanded(
                    child: Text(
                      'Match',
                      style: Fp.body(11.5, color: Fp.text3, weight: FontWeight.w700),
                    ),
                  ),
                  head('1'),
                  const SizedBox(width: 5),
                  head('N'),
                  const SizedBox(width: 5),
                  head('2'),
                ],
              ),
              for (final (i, u) in widget.rows.indexed) ...[
                if (i > 0) const Divider(height: 1),
                _CompactRow(u, offers[u.match.id] ?? const {}),
              ],
            ],
          ),
        ),
        Text(
          hasOdds
              ? 'En haut : la chance selon le moteur ; en bas : la cote du bookmaker. Encadré : l\'issue la '
                    'plus probable selon le moteur (pas un conseil de pari). Un appui ouvre le match.'
              : 'La chance selon le moteur ; encadré : l\'issue la plus probable (pas un conseil de pari). '
                    'Un appui ouvre le match.',
          style: Fp.body(12, color: Fp.text3, height: 1.4),
        ),
        const SizedBox(height: 8),
      ],
    );
  }
}

class _CompactRow extends StatelessWidget {
  const _CompactRow(this.u, this.offers);
  final Upcoming u;
  final Map<String, Offer> offers;

  @override
  Widget build(BuildContext context) {
    final m = u.match, s = u.summary;
    final probs = s == null ? null : [s.home.probability, s.draw.probability, s.away.probability];
    final best = probs == null ? -1 : probs.indexOf(probs.reduce((a, b) => a > b ? a : b));
    const keys = ['1X2||home', '1X2||draw', '1X2||away'];
    Widget box(int i) {
      final o = offers[keys[i]];
      final on = i == best;
      return Container(
        width: _CompactListState._box,
        padding: const EdgeInsets.symmetric(vertical: 4),
        decoration: BoxDecoration(
          color: on ? Fp.accentAlpha(0.22) : Fp.fill,
          borderRadius: BorderRadius.circular(9),
          border: Border.all(color: on ? Fp.accentAlpha(0.6) : Colors.transparent),
        ),
        child: Column(
          children: [
            Text(probs == null ? '—' : percent(probs[i]), style: Fp.body(13.5, weight: FontWeight.w800)),
            if (o != null)
              Text(
                odds(o.odds),
                style: Fp.body(11, color: Fp.text2, weight: FontWeight.w600),
              ),
          ],
        ),
      );
    }

    return InkWell(
      onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => MatchScreen(matchId: m.id))),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Row(
          children: [
            SizedBox(
              width: 46,
              child: Text(
                // En direct : la minute seule (« En direct 45' » ne tient pas dans la colonne).
                m.isLive ? (m.apiStatus == 'HT' ? 'MT' : '${m.liveMinute ?? ''}\'') : m.when,
                style: Fp.body(12.5, color: m.isLive ? Fp.win : Fp.text2, weight: FontWeight.w700),
              ),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Deux lignes : les noms longs (Eyüpspor, Kocaelispor) ne sont jamais coupés au
                  // point de cacher l'équipe à l'extérieur.
                  for (final (i, name) in [m.home.name, m.away.name].indexed)
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Fp.body(13.5, weight: FontWeight.w700),
                          ),
                        ),
                        if (m.score case final sc?)
                          Text(
                            sc.split(' - ')[i],
                            style: Fp.body(13.5, weight: FontWeight.w800, color: m.isLive ? Fp.win : Fp.text),
                          ),
                      ],
                    ),
                  Text(
                    competitionName(m.competition),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Fp.body(11.5, color: Fp.text3),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 6),
            box(0),
            const SizedBox(width: 5),
            box(1),
            const SizedBox(width: 5),
            box(2),
          ],
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
    final ids = [for (final u in widget.rows.take(80)) u.match.id];
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
                    TeamCircle(m.home.code, size: 30),
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
