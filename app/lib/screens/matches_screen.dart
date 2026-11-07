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
                    MTitle('Matchs', selectedDay == today ? 'du jour' : 'à venir'),
                    const SizedBox(height: 10),
                    // Jours qui défilent ; « Tous championnats ▾ » toujours visible à droite.
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
                          '${competition.isEmpty ? 'Tous championnats' : competitionName(competition)} ▾',
                          selected: competition.isNotEmpty,
                          onTap: () => _pickCompetition(context, comps),
                        ),
                      ],
                    ),
                  ],
                  if (live.isNotEmpty) ...[
                    if (desk) ...[
                      const SectionTitle('En direct'),
                      _MatchTable([for (final m in live) Upcoming.of(m)]),
                      const SectionTitle('À venir'),
                    ] else
                      _CompactList([for (final m in live) Upcoming.of(m)], title: 'En direct', note: false),
                  ],
                  if (shown.isEmpty)
                    const EmptyState('Aucun match à venir pour ce filtre.', icon: Icons.event_busy_rounded)
                  else if (desk)
                    _MatchTable(shown)
                  else
                    _CompactList(
                      shown,
                      title: selectedDay == null ? null : longDate(selectedDay),
                      header: live.isEmpty,
                    ),
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

/// Téléphone (maquette validée le 07/11/2026, valeurs reprises une à une) : en-tête 1 / N / 2,
/// intertitre du jour, puis une ligne par match, rangés par heure, sans carte autour ; chance
/// selon le moteur et, dessous, la cote du bookmaker ; l'issue la plus probable encadrée (pas
/// un conseil de pari). Un appui ouvre le match.
class _CompactList extends StatefulWidget {
  const _CompactList(this.rows, {this.title, this.header = true, this.note = true});
  final List<Upcoming> rows;
  final String? title;
  final bool header;
  final bool note;

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

  static const box = 52.0;
  static const gap = 6.0;
  static const timeWidth = 44.0;

  @override
  Widget build(BuildContext context) {
    const head = Color(0x90F4F2F8);
    Widget col(String t) => SizedBox(
      width: box,
      child: Text(
        t,
        textAlign: TextAlign.center,
        style: Fp.body(11.5, color: head),
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (widget.header)
          Padding(
            padding: const EdgeInsets.only(top: 8, bottom: 2),
            child: Row(
              children: [
                const SizedBox(width: timeWidth + gap),
                Expanded(
                  child: Text('Match', style: Fp.body(11.5, color: head)),
                ),
                const SizedBox(width: gap),
                col('1'),
                const SizedBox(width: gap),
                col('N'),
                const SizedBox(width: gap),
                col('2'),
              ],
            ),
          ),
        if (widget.title != null)
          Padding(
            padding: const EdgeInsets.only(top: 14, bottom: 2),
            child: Text(widget.title!, style: Fp.title(13, color: M.lock)),
          ),
        for (final (i, u) in widget.rows.indexed)
          _CompactRow(u, offers[u.match.id] ?? const {}, last: i == widget.rows.length - 1),
        if (widget.note) ...[
          const SizedBox(height: 12),
          Text(
            offers.isNotEmpty
                ? 'En haut : la chance selon le moteur ; en bas : la cote 1xBet. Encadré : l\'issue la plus '
                      'probable selon le moteur (pas un conseil de pari). Un appui ouvre le match.'
                : 'La chance selon le moteur ; encadré : l\'issue la plus probable (pas un conseil de pari). '
                      'Un appui ouvre le match.',
            style: Fp.body(12.5, color: M.small, height: 1.4),
          ),
        ],
        const SizedBox(height: 8),
      ],
    );
  }
}

class _CompactRow extends StatelessWidget {
  const _CompactRow(this.u, this.offers, {this.last = false});
  final Upcoming u;
  final Map<String, Offer> offers;
  final bool last;

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
        width: _CompactListState.box,
        padding: const EdgeInsets.symmetric(vertical: 4),
        decoration: BoxDecoration(
          color: on ? const Color(0x337C3AED) : const Color(0x0DFFFFFF),
          borderRadius: BorderRadius.circular(9),
          border: Border.all(color: on ? const Color(0x887C3AED) : Colors.transparent),
        ),
        child: Column(
          children: [
            Text(probs == null ? '—' : percent(probs[i]), style: Fp.body(13.5, weight: FontWeight.w700)),
            if (o != null) Text(odds(o.odds), style: Fp.body(11, color: const Color(0xA8F4F2F8))),
          ],
        ),
      );
    }

    const gap = SizedBox(width: _CompactListState.gap);
    return InkWell(
      onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => MatchScreen(matchId: m.id))),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 9),
        decoration: BoxDecoration(
          border: last ? null : const Border(bottom: BorderSide(color: M.line10)),
        ),
        child: Row(
          children: [
            SizedBox(
              width: _CompactListState.timeWidth,
              child: Text(
                // En direct : la minute seule (« En direct 45' » ne tient pas dans la colonne).
                m.isLive ? (m.apiStatus == 'HT' ? 'MT' : '${m.liveMinute ?? ''}\'') : m.when,
                style: Fp.body(12.5, color: m.isLive ? M.green : const Color(0xB0F4F2F8)),
              ),
            ),
            gap,
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    m.score == null
                        ? '${m.home.name} – ${m.away.name}'
                        : '${m.home.name} ${m.score} ${m.away.name}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Fp.body(13.5, weight: FontWeight.w600),
                  ),
                  Text(
                    competitionName(m.competition),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Fp.body(11, color: const Color(0x90F4F2F8)),
                  ),
                ],
              ),
            ),
            gap,
            box(0),
            gap,
            box(1),
            gap,
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
