// Nouveau visage, étape B (plan du 20/11/2026, écrans 35 et 36) : « Aujourd'hui », le tableau de
// bord. Seulement des données qui existent : solde et sa courbe, 30 derniers jours, moteur
// annoncé contre réalisé, mises de la semaine, mes paris (en direct, en cours, à venir), le
// moteur au-dessus de la cote, les coupons du jour, la montante, la justesse par marché.
// On informe ; rien ne pousse à parier. Section vide : cachée, jamais d'écran « rien de valable ».
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../desktop/layout.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/engine_vs_odds.dart';
import '../widgets/live_chances.dart';
import 'create_screen.dart' show HomeTab;
import 'daily_coupons_screen.dart';
import 'match_screen.dart';
import 'notifications_screen.dart';
import 'record_screen.dart';
import 'reliability_screen.dart';

/// Données du tableau de bord, chargées ensemble (une erreur sur une partie secondaire la
/// cache sans bloquer le reste).
class TodayData {
  TodayData({
    required this.dash,
    required this.openBets,
    required this.montantes,
    required this.daily,
    required this.record,
    required this.chances,
  });
  final Json dash;
  final List<Bet> openBets;
  final List<Json> montantes;
  final Json? daily;
  final Json? record;
  final Map<int, Json> chances;

  /// Nouveau joueur : ni pari, ni mouvement autre que l'ouverture du compte.
  bool get newPlayer =>
      openBets.isEmpty &&
      ((record?['bets'] as Json?)?['settled'] as int? ?? 0) == 0 &&
      (dash['curve'] as List).length <= 1;

  static Future<TodayData> load(ApiClient api) async {
    Future<Object?> soft(Future<Object?> f) => f.then<Object?>((v) => v, onError: (Object _) => null);
    final r = await Future.wait([
      api.get('/me/dashboard'),
      soft(api.get('/bets', {'status': 'open', 'limit': 30})),
      soft(api.get('/montantes')),
      soft(api.get('/smart-coupons/day')),
      soft(api.get('/me/record')),
    ]);
    final bets = [for (final j in (r[1] as List?) ?? const []) Bet(j as Json)];
    final live = {
      for (final b in bets)
        for (final s in b.selections)
          if (s.state == 'live') s.matchId,
    };
    return TodayData(
      dash: r[0] as Json,
      openBets: bets,
      montantes: ((r[2] as List?) ?? const []).cast<Json>(),
      daily: r[3] as Json?,
      record: r[4] as Json?,
      chances: await loadLiveChances(api, live),
    );
  }
}

class TodayScreen extends StatelessWidget {
  const TodayScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final now = DateTime.now();
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        bottom: false,
        child: Loader<TodayData>(
          load: () => TodayData.load(state.api),
          builder: (context, d, reload) {
            final currency = d.dash['currency'] as String? ?? 'XOF';
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: pagePadding(context, 22, 120, maxWidth: 1000),
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Aujourd\'hui', style: Fp.title(26)),
                            Text(shortDate(now), style: Fp.body(13, color: Fp.muted)),
                          ],
                        ),
                      ),
                      IconButton(
                        tooltip: 'Notifications',
                        onPressed: () =>
                            Navigator.of(context)
                                .push(MaterialPageRoute(builder: (_) => const NotificationsScreen())),
                        icon: Badge(
                          isLabelVisible: state.unread > 0,
                          label: Text('${state.unread}'),
                          backgroundColor: Fp.accent,
                          child: const Icon(Icons.notifications_none_rounded, color: Fp.text),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  _BalanceCard(dash: d.dash, currency: currency),
                  const SizedBox(height: 12),
                  if (d.newPlayer)
                    ..._starter(context)
                  else ...[
                    _Indicators(dash: d.dash, currency: currency),
                    if (_live(d).isNotEmpty) ...[
                      const SectionTitle('En direct pour moi'),
                      for (final b in _live(d)) _BetRow(bet: b, chances: d.chances, live: true),
                    ],
                    if (d.openBets.isNotEmpty) ...[
                      _Title(
                        'Mes paris en cours',
                        action: 'Tout voir',
                        onAction: () => state.openTab(HomeTab.paris),
                      ),
                      for (final b in d.openBets.where((b) => !_live(d).contains(b)).take(4))
                        _BetRow(bet: b, chances: d.chances),
                    ],
                    if (_agenda(d).isNotEmpty) ...[
                      const SectionTitle('À venir dans mes paris'),
                      _Agenda(items: _agenda(d)),
                    ],
                  ],
                  if ((d.dash['engine_above_odds'] as List).isNotEmpty) ...[
                    const SectionTitle('Le moteur au-dessus de la cote'),
                    _EngineAbove(items: (d.dash['engine_above_odds'] as List).cast<Json>()),
                  ],
                  if (((d.daily?['coupons'] as List?) ?? const []).isNotEmpty) ...[
                    _Title(
                      'Coupons du jour',
                      action: 'Ouvrir',
                      onAction: () =>
                          Navigator.of(context)
                              .push(MaterialPageRoute(builder: (_) => const DailyCouponsScreen())),
                    ),
                    _Daily(coupons: (d.daily!['coupons'] as List).cast<Json>()),
                  ],
                  if (d.montantes.where((m) => m['status'] == 'active').firstOrNull case final m?) ...[
                    _Title('Ma montante', action: 'Ouvrir', onAction: () => state.openTab(HomeTab.montante)),
                    _Montante(m: m, currency: currency),
                  ],
                  if (_markets(d).isNotEmpty) ...[
                    _Title(
                      'Justesse du moteur sur mes paris',
                      action: 'Mon bilan',
                      onAction: () =>
                          Navigator.of(context).push(MaterialPageRoute(builder: (_) => const RecordScreen())),
                    ),
                    _Markets(rows: _markets(d)),
                  ],
                  const SizedBox(height: 8),
                  Text(
                    'Argent fictif. Le moteur calcule des chances ; ce n\'est jamais un conseil de pari.',
                    style: Fp.body(12, color: Fp.text4, height: 1.4),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  static List<Bet> _live(TodayData d) =>
      d.openBets.where((b) => b.selections.any((s) => s.state == 'live')).toList();

  /// Prochains matchs de mes paris (pas encore commencés), du plus proche au plus lointain.
  static List<BetSel> _agenda(TodayData d) {
    final seen = <int>{};
    final out = [
      for (final b in d.openBets)
        for (final s in b.selections)
          if (s.state == 'upcoming' && s.kickoffAt != null && seen.add(s.matchId)) s,
    ]..sort((a, b) => a.kickoffAt!.compareTo(b.kickoffAt!));
    return out.take(5).toList();
  }

  /// Marchés de mes paris avec la chance annoncée, les plus joués d'abord.
  static List<Json> _markets(TodayData d) => [
    for (final m in ((d.record?['by_market'] as List?) ?? const []).cast<Json>())
      if (m['announced'] != null && m['rate'] != null) m,
  ].take(4).toList();

  /// Nouveau joueur : trois cartes de départ au lieu de compteurs à zéro.
  List<Widget> _starter(BuildContext context) {
    final state = context.read<AppState>();
    void push(Widget page) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
    return [
      const SectionTitle('Pour commencer'),
      _StartCard(
        icon: Icons.sports_soccer_rounded,
        title: 'Un premier pari, en argent fictif',
        text: 'Touche une cote dans Matchs : la chance du moteur est à côté.',
        onTap: () => state.openTab(HomeTab.matchs),
      ),
      _StartCard(
        icon: Icons.today_outlined,
        title: 'Les coupons du jour',
        text: 'Trois coupons composés chaque matin, avec la cote en face.',
        onTap: () => push(const DailyCouponsScreen()),
      ),
      _StartCard(
        icon: Icons.verified_outlined,
        title: 'Le moteur est-il juste ?',
        text: 'Ce qu\'il annonce, face à ce qui arrive vraiment.',
        onTap: () => push(const ReliabilityScreen()),
      ),
    ];
  }
}

class _Title extends StatelessWidget {
  const _Title(this.text, {required this.action, required this.onAction});
  final String text;
  final String action;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 18, bottom: 6),
    child: Row(
      children: [
        Expanded(child: Text(text, style: Fp.title(16))),
        TextButton(onPressed: onAction, child: Text(action)),
      ],
    ),
  );
}

/// Solde et sa courbe (fin de journée), sur 7 jours, 30 jours, 3 mois ou tout.
class _BalanceCard extends StatefulWidget {
  const _BalanceCard({required this.dash, required this.currency});
  final Json dash;
  final String currency;

  @override
  State<_BalanceCard> createState() => _BalanceCardState();
}

class _BalanceCardState extends State<_BalanceCard> {
  static const ranges = [('7 j', 7), ('30 j', 30), ('3 mois', 90), ('Tout', 0)];
  int range = 1;

  @override
  Widget build(BuildContext context) {
    final curve = [
      for (final p in (widget.dash['curve'] as List).cast<Json>())
        (DateTime.parse(p['day'] as String), (p['balance'] as num).toDouble()),
    ];
    final days = ranges[range].$2;
    final from = DateTime.now().subtract(Duration(days: days));
    var points = days == 0 ? curve : curve.where((p) => !p.$1.isBefore(from)).toList();
    // Solde de départ de la période : le dernier connu avant elle.
    final before = curve.where((p) => p.$1.isBefore(from)).lastOrNull;
    if (days != 0 && before != null) points = [(from, before.$2), ...points];
    // La courbe va jusqu'à aujourd'hui (solde actuel), même sans mouvement récent.
    final balanceNow = (widget.dash['balance'] as num).toDouble();
    if (points.isNotEmpty || curve.isNotEmpty) points = [...points, (DateTime.now(), balanceNow)];
    final change = points.length >= 2 ? points.last.$2 - points.first.$2 : 0.0;
    final balance = balanceNow.round();
    return GlassCard.section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Solde fictif', style: Fp.body(12.5, color: Fp.muted)),
          const SizedBox(height: 2),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(child: Text(money(balance, widget.currency), style: Fp.title(28))),
              if (points.length >= 2)
                Text(
                  signedMoney(change.round(), widget.currency),
                  style: Fp.body(13.5, weight: FontWeight.w700, color: change >= 0 ? Fp.win : Fp.loss),
                ),
            ],
          ),
          const SizedBox(height: 10),
          SizedBox(
            height: 70,
            width: double.infinity,
            child: points.length >= 2
                ? CustomPaint(
                    painter: _CurvePainter([for (final p in points) p.$2], change >= 0 ? Fp.win : Fp.loss),
                  )
                : Center(
                    child: Text(
                      'La courbe apparaîtra après tes premiers paris.',
                      style: Fp.body(12, color: Fp.text4),
                    ),
                  ),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final (i, r) in ranges.indexed)
                Padding(
                  padding: EdgeInsets.zero,
                  child: ChoiceChip(
                    label: Text(r.$1),
                    selected: i == range,
                    showCheckmark: false,
                    onSelected: (_) => setState(() => range = i),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _CurvePainter extends CustomPainter {
  _CurvePainter(this.values, this.color);
  final List<double> values;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final lo = values.reduce(math.min), hi = values.reduce(math.max);
    final span = hi - lo == 0 ? 1.0 : hi - lo;
    Offset at(int i) => Offset(
      size.width * i / (values.length - 1),
      size.height - 4 - (values[i] - lo) / span * (size.height - 8),
    );
    final line = Path()..moveTo(at(0).dx, at(0).dy);
    for (var i = 1; i < values.length; i++) {
      line.lineTo(at(i).dx, at(i).dy);
    }
    final fill = Path.from(line)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawPath(
      fill,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [color.withValues(alpha: 0.28), color.withValues(alpha: 0)],
        ).createShader(Offset.zero & size),
    );
    canvas.drawPath(
      line,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.2
        ..strokeJoin = StrokeJoin.round,
    );
  }

  @override
  bool shouldRepaint(_CurvePainter old) => old.values != values || old.color != color;
}

/// Quatre indicateurs : rendement et paris gagnés sur 30 jours, moteur annoncé contre réalisé,
/// mises de la semaine (le budget viendra avec « Mon plan de jeu »).
class _Indicators extends StatelessWidget {
  const _Indicators({required this.dash, required this.currency});
  final Json dash;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final m = dash['last_30_days'] as Json;
    final e = dash['engine'] as Json;
    final st = dash['stakes'] as Json;
    final yield_ = (m['yield'] as num?)?.toDouble();
    final settled = m['settled'] as int;
    final announced = (e['announced'] as num?)?.toDouble();
    final observed = (e['observed'] as num?)?.toDouble();
    final week = st['week'] as int, prev = st['previous_week'] as int;
    Widget tile(String label, String value, String sub, {Color color = Fp.text}) => Container(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      decoration: BoxDecoration(
        color: Fp.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Fp.line12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Fp.body(11.5, color: Fp.muted)),
          const SizedBox(height: 3),
          Text(value, style: Fp.title(19, color: color)),
          const SizedBox(height: 2),
          Text(sub, maxLines: 2, style: Fp.body(11, color: Fp.text4, height: 1.3)),
        ],
      ),
    );
    final tiles = [
      tile(
        'Rendement 30 j',
        yield_ == null ? '—' : '${yield_ >= 0 ? '+' : '−'}${percent(yield_.abs(), decimals: 1)}',
        settled == 0
            ? 'aucun pari réglé'
            : '$settled pari${settled > 1 ? 's' : ''} réglé${settled > 1 ? 's' : ''}',
        color: yield_ == null ? Fp.text : (yield_ >= 0 ? Fp.win : Fp.loss),
      ),
      tile('Paris gagnés 30 j', settled == 0 ? '—' : '${m['won']} sur $settled', 'remboursés exclus'),
      tile(
        'Moteur sur mes paris',
        announced == null || observed == null ? '—' : '${percent(observed)} réalisé',
        announced == null
            ? 'pas encore de sélection réglée'
            : 'annoncé ${percent(announced)} · ${e['selections']} sél.',
      ),
      tile(
        'Mises de la semaine',
        money(week, currency),
        prev == 0 ? '7 derniers jours' : 'semaine d\'avant : ${money(prev, currency)}',
        color: prev > 0 && week >= 2 * prev ? Fp.warning : Fp.text,
      ),
    ];
    return LayoutBuilder(
      builder: (context, c) {
        final cols = c.maxWidth >= 640 ? 4 : 2;
        final w = (c.maxWidth - 10 * (cols - 1)) / cols;
        return Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [for (final t in tiles) SizedBox(width: w, child: t)],
        );
      },
    );
  }
}

class _BetRow extends StatelessWidget {
  const _BetRow({required this.bet, required this.chances, this.live = false});
  final Bet bet;
  final Map<int, Json> chances;
  final bool live;

  @override
  Widget build(BuildContext context) {
    final first = bet.selections.first;
    final name = bet.selections.length == 1
        ? fullLabel(first.market, first.line, first.selection, home: first.homeTeam, away: first.awayTeam)
        : 'Combiné de ${bet.selections.length}';
    final match = bet.selections.length == 1 ? '${first.homeTeam} – ${first.awayTeam}' : null;
    final c = couponChances(bet, chances);
    final liveSel = bet.selections.where((s) => s.state == 'live').firstOrNull;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: GlassCard.section(
        onTap: () => context.read<AppState>().openTab(HomeTab.paris),
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name, style: Fp.body(14, weight: FontWeight.w700)),
                  if (match != null) Text(match, style: Fp.body(12, color: Fp.muted)),
                  if (live && liveSel != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 3),
                      child: Text(
                        '${liveSel.homeTeam} ${liveSel.score?[0] ?? '-'}–${liveSel.score?[1] ?? '-'} '
                        '${liveSel.awayTeam} · ${liveSel.minute ?? ''}${liveSel.extra != null ? '+${liveSel.extra}' : ''}\'',
                        style: Fp.body(12.5, weight: FontWeight.w700, color: Fp.loss),
                      ),
                    ),
                  if (c != null)
                    Text(
                      'chance de tenir : ${percent(c.$2)}',
                      style: Fp.body(12, color: c.$2 >= c.$1 ? Fp.win : Fp.textSoft),
                    ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(odds(bet.totalOdds), style: Fp.body(15, weight: FontWeight.w700)),
                Text(
                  '${money(bet.stake, bet.currency)} → ${money(bet.potentialPayout, bet.currency)}',
                  style: Fp.body(11.5, color: Fp.muted),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Agenda extends StatelessWidget {
  const _Agenda({required this.items});
  final List<BetSel> items;

  @override
  Widget build(BuildContext context) => GlassCard.section(
    child: Column(
      children: [
        for (final s in items)
          InkWell(
            onTap: () =>
                Navigator.of(context)
                    .push(MaterialPageRoute(builder: (_) => MatchScreen(matchId: s.matchId))),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 7),
              child: Row(
                children: [
                  SizedBox(
                    width: 92,
                    child: Text(
                      '${shortDate(s.kickoffAt!.toLocal())}\n${hourMinute(s.kickoffAt!.toLocal())}',
                      style: Fp.body(12, color: Fp.muted, height: 1.3),
                    ),
                  ),
                  Expanded(
                    child: Text(
                      '${s.homeTeam} – ${s.awayTeam}',
                      style: Fp.body(13.5, weight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    ),
  );
}

class _EngineAbove extends StatelessWidget {
  const _EngineAbove({required this.items});
  final List<Json> items;

  @override
  Widget build(BuildContext context) => GlassCard.section(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Matchs des prochaines 36 heures où le moteur est plus confiant que la cote '
          '(sélections nationales à part). Une information, pas un conseil.',
          style: Fp.body(12, color: Fp.muted, height: 1.4),
        ),
        for (final a in items)
          InkWell(
            onTap: () =>
                Navigator.of(context)
                    .push(MaterialPageRoute(builder: (_) => MatchScreen(matchId: a['match_id'] as int))),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 9),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          fullLabel(
                            a['market'] as String,
                            (a['line'] ?? '') as String,
                            a['selection'] as String,
                            home: a['home'] as String,
                            away: a['away'] as String,
                          ),
                          style: Fp.body(13.5, weight: FontWeight.w700),
                        ),
                        Text(
                          [
                            competitionName(a['competition'] as String),
                            '${a['home']} – ${a['away']}',
                            if (parseDate(a['kickoff_at']) case final k?) hourMinute(k.toLocal()),
                          ].join(' · '),
                          style: Fp.body(12, color: Fp.muted),
                        ),
                        const SizedBox(height: 4),
                        GapBadge(
                          engine: (a['engine'] as num).toDouble(),
                          implied: (a['implied'] as num).toDouble(),
                        ),
                      ],
                    ),
                  ),
                  Text(odds(a['odds']), style: Fp.body(15, weight: FontWeight.w700)),
                ],
              ),
            ),
          ),
      ],
    ),
  );
}

class _Daily extends StatelessWidget {
  const _Daily({required this.coupons});
  final List<Json> coupons;

  @override
  Widget build(BuildContext context) => GlassCard.section(
    child: Column(
      children: [
        for (final c in coupons)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    '${c['profile_label'] ?? c['profile']}',
                    style: Fp.body(14, weight: FontWeight.w700),
                  ),
                ),
                if (c['probability'] is num && c['total_odds'] != null) ...[
                  GapBadge(
                    engine: (c['probability'] as num).toDouble(),
                    implied: 1 / double.parse('${c['total_odds']}'),
                  ),
                  const SizedBox(width: 10),
                ],
                Text('cote ${odds(c['total_odds'])}', style: Fp.body(14, weight: FontWeight.w700)),
              ],
            ),
          ),
      ],
    ),
  );
}

/// Ma montante : palier, et le gain et le risque côte à côte (si ça passe, si j'arrête, si ça
/// rate).
class _Montante extends StatelessWidget {
  const _Montante({required this.m, required this.currency});
  final Json m;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final steps = (m['steps'] as List).cast<Json>();
    final current = m['current_step'] as int? ?? 1;
    final step = steps.where((s) => s['number'] == current).firstOrNull;
    final pass = (m['final_payout_range'] as List?)?.cast<num>();
    final stake = (step?['stake'] as num?)?.toInt();
    Widget col(String label, String value, Color color) => Expanded(
      child: Column(
        children: [
          Text(label, style: Fp.body(11.5, color: Fp.muted)),
          const SizedBox(height: 2),
          Text(
            value,
            textAlign: TextAlign.center,
            style: Fp.body(13.5, weight: FontWeight.w700, color: color),
          ),
        ],
      ),
    );
    return GlassCard.section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              for (final s in steps)
                Expanded(
                  child: Container(
                    height: 8,
                    margin: const EdgeInsets.symmetric(horizontal: 2),
                    decoration: BoxDecoration(
                      color: switch (s['result']) {
                        'win' => Fp.win,
                        'loss' => Fp.loss,
                        _ => s['number'] == current ? Fp.accent : Fp.line12,
                      },
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Text('Palier $current sur ${steps.length}', style: Fp.body(14, weight: FontWeight.w700)),
          const SizedBox(height: 10),
          Row(
            children: [
              col('Si tout passe', pass == null ? '—' : money(pass.first, currency), Fp.win),
              col('Si j\'arrête', money((m['cashable'] as num?) ?? 0, currency), Fp.text),
              col('Si ça rate', stake == null ? '—' : '−${money(stake, currency)}', Fp.loss),
            ],
          ),
        ],
      ),
    );
  }
}

class _Markets extends StatelessWidget {
  const _Markets({required this.rows});
  final List<Json> rows;

  @override
  Widget build(BuildContext context) => GlassCard.section(
    child: Column(
      children: [
        for (final r in rows)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Row(
              children: [
                Expanded(child: Text(marketTitle(r['key'] as String), style: Fp.body(13.5))),
                Text(
                  'annoncé ${percent((r['announced'] as num).toDouble())}',
                  style: Fp.body(12, color: Fp.muted),
                ),
                const SizedBox(width: 10),
                SizedBox(
                  width: 92,
                  child: Text(
                    'réalisé ${percent((r['rate'] as num).toDouble())}',
                    textAlign: TextAlign.right,
                    style: Fp.body(
                      12.5,
                      weight: FontWeight.w700,
                      color: switch (r['gap']) {
                        'low' => Fp.loss,
                        'high' => Fp.win,
                        _ => Fp.text,
                      },
                    ),
                  ),
                ),
              ],
            ),
          ),
      ],
    ),
  );
}

class _StartCard extends StatelessWidget {
  const _StartCard({required this.icon, required this.title, required this.text, required this.onTap});
  final IconData icon;
  final String title;
  final String text;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: GlassCard.section(
      onTap: onTap,
      child: Row(
        children: [
          Icon(icon, color: Fp.accentLight),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Fp.body(14.5, weight: FontWeight.w700)),
                Text(text, style: Fp.body(12.5, color: Fp.muted, height: 1.35)),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded, color: Fp.muted),
        ],
      ),
    ),
  );
}
