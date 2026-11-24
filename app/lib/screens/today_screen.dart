// « Aujourd'hui », le tableau de bord : copie de la maquette 35 du testeur
// (docs/maquettes/12-nouveau-visage, « Tableau de bord complet »), bloc par bloc, avec les
// vraies données : solde et courbe, 4 indicateurs (dont le plan de jeu), mes matchs en direct,
// mes paris avec leur chance, mon agenda, les occasions (moteur au-dessus de la cote) et
// l'alerte de cote, les coupons du jour, la montante, la justesse du moteur par marché (30 j).
// On informe ; rien ne pousse à parier. Section sans donnée : cachée.
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../desktop/layout.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../widgets/common.dart';
import '../widgets/live_chances.dart';
import '../widgets/visage.dart';
import 'create_screen.dart' show HomeTab;
import 'daily_coupons_screen.dart';
import 'match_screen.dart';
import 'notifications_screen.dart';
import 'odds_alerts_screen.dart';
import 'play_plan_screen.dart';
import 'reliability_screen.dart';
import 'search_screen.dart';

/// Données du tableau de bord, chargées ensemble (une erreur sur une partie secondaire la
/// cache sans bloquer le reste).
class TodayData {
  TodayData({
    required this.dash,
    required this.openBets,
    required this.montantes,
    required this.daily,
    required this.chances,
  });
  final Json dash;
  final List<Bet> openBets;
  final List<Json> montantes;
  final Json? daily;
  final Map<int, Json> chances;

  /// Nouveau joueur : ni pari, ni mouvement autre que l'ouverture du compte.
  bool get newPlayer =>
      openBets.isEmpty &&
      ((dash['last_30_days'] as Json)['settled'] as int? ?? 0) == 0 &&
      (dash['curve'] as List).length <= 1;

  static Future<TodayData> load(ApiClient api) async {
    Future<Object?> soft(Future<Object?> f) => f.then<Object?>((v) => v, onError: (Object _) => null);
    final r = await Future.wait([
      api.get('/me/dashboard'),
      soft(api.get('/bets', {'status': 'open', 'limit': 30})),
      soft(api.get('/montantes')),
      soft(api.get('/smart-coupons/day')),
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
      chances: await loadLiveChances(api, live),
    );
  }
}

/// Montant comme la maquette : « 90 339 F ».
String fcfa(num v, [String currency = 'XOF']) =>
    '${thousands(v)}$nbsp${const {'XOF', 'XAF'}.contains(currency) ? 'F' : currency}';

String _pct(double p) => '${(p * 100).round()}$nbsp%';

void _push(BuildContext context, Widget page) =>
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));

class TodayScreen extends StatelessWidget {
  const TodayScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        bottom: false,
        child: Loader<TodayData>(
          load: () => TodayData.load(state.api),
          builder: (context, d, reload) {
            final cur = d.dash['currency'] as String? ?? 'XOF';
            final live = _liveSels(d);
            final above = (d.dash['engine_above_odds'] as List).cast<Json>();
            final coupons = ((d.daily?['coupons'] as List?) ?? const []).cast<Json>();
            final montante = d.montantes.where((m) => m['status'] == 'active').firstOrNull;
            final markets = _markets(d);
            final agenda = _agenda(d);
            return RefreshIndicator(
              onRefresh: reload,
              child: DefaultTextStyle(
                style: V.t(13.5),
                child: ListView(
                  padding: pagePadding(context, 6, 120, maxWidth: 760),
                  children: [
                    _Header(unread: state.unread),
                    _BalanceCard(dash: d.dash, currency: cur),
                    if (d.newPlayer)
                      ..._starter(context)
                    else ...[
                      _Indicators(dash: d.dash, currency: cur),
                      if (live.isNotEmpty) ...[
                        Padding(
                          padding: const EdgeInsets.only(top: 16),
                          child: VHead('En direct pour moi', link: '${live.length}'),
                        ),
                        const SizedBox(height: 8),
                        SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          clipBehavior: Clip.none,
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              for (final (i, s) in live.indexed) ...[
                                if (i > 0) const SizedBox(width: 8),
                                _LiveCard(sel: s, chances: d.chances),
                              ],
                            ],
                          ),
                        ),
                      ],
                      if (d.openBets.isNotEmpty)
                        VCard(
                          child: Column(
                            children: [
                              VHead(
                                'Mes paris en cours',
                                link: 'Tout',
                                onLink: () => state.openTab(HomeTab.paris),
                              ),
                              VList(
                                children: [
                                  for (final b in d.openBets.take(4))
                                    _BetLine(bet: b, chances: d.chances, montantes: d.montantes),
                                ],
                              ),
                            ],
                          ),
                        ),
                      if (agenda.isNotEmpty)
                        VCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              const VKicker('Mon agenda'),
                              const SizedBox(height: 6),
                              VTimeline(items: agenda),
                            ],
                          ),
                        ),
                    ],
                    if (oddsAlertsShown) _Occasions(items: above),
                    if (coupons.isNotEmpty) _Daily(coupons: coupons),
                    if (montante != null) _Montante(m: montante, currency: cur),
                    if (markets.isNotEmpty) _Markets(rows: markets),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  /// Sélections en cours de mes paris (une carte par match).
  static List<BetSel> _liveSels(TodayData d) {
    final seen = <int>{};
    return [
      for (final b in d.openBets)
        for (final s in b.selections)
          if (s.state == 'live' && seen.add(s.matchId)) s,
    ];
  }

  /// Frise (maquette 35) : fin prévue des matchs en cours, puis coup d'envoi des matchs à venir
  /// (« (palier 3) » pour un pari de montante), du plus proche au plus lointain.
  static List<(String, VDotKind)> _agenda(TodayData d) {
    final now = MatchInfo.now().toLocal();
    final seen = <int>{};
    // Palier de montante de chaque pari (« Sam. 20:45 · Lens – Lyon (palier 3) »).
    final step = <int, int>{
      for (final m in d.montantes)
        if (m['status'] == 'active')
          for (final s in (m['steps'] as List).cast<Json>())
            if (s['bet_id'] case final int id) id: s['number'] as int,
    };
    final rows = <(DateTime, String, VDotKind)>[];
    // Paris de montante d'abord : un match commun garde la mention « (palier N) ».
    for (final b in [
      ...d.openBets.where((b) => step.containsKey(b.id)),
      ...d.openBets.where((b) => !step.containsKey(b.id)),
    ]) {
      for (final s in b.selections) {
        if (s.kickoffAt == null || !seen.add(s.matchId)) continue;
        final k = s.kickoffAt!.toLocal();
        final match = '${s.homeTeam} – ${s.awayTeam}';
        if (s.state == 'live') {
          // Fin prévue : coup d'envoi + 1 h 55 (deux mi-temps, la pause et le temps additionnel).
          final end = k.add(const Duration(minutes: 115));
          final de = RegExp(r'^[AEIOUYÉÈÊÂÎÔaeiouyéèêâîô]').hasMatch(s.homeTeam) ? 'd\'' : 'de ';
          rows.add((end, '${_day(end, now)} ${hourMinute(end)} · fin $de$match', VDotKind.plain));
        } else if (s.state == 'upcoming') {
          final n = step[b.id];
          rows.add((
            k,
            '${_day(k, now)} ${hourMinute(k)} · $match${n == null ? '' : ' (palier $n)'}',
            VDotKind.plain,
          ));
        }
      }
    }
    rows.sort((x, y) => x.$1.compareTo(y.$1));
    return [for (final r in rows.take(5)) (r.$2, r.$3)];
  }

  /// « Ce soir », « Aujourd'hui », « Demain », sinon « Sam. ».
  static String _day(DateTime k, DateTime now) {
    final diff = DateTime(k.year, k.month, k.day).difference(DateTime(now.year, now.month, now.day)).inDays;
    if (diff == 0) return k.hour >= 18 ? 'Ce soir' : 'Aujourd\'hui';
    if (diff == 1) return 'Demain';
    final d = shortDate(k).split(' ').first;
    return '${d[0].toUpperCase()}${d.substring(1)}';
  }

  /// « Où le moteur tient parole (30 j) » : marchés avec une chance annoncée, les plus joués.
  /// Maquette 35 : noms courts (« Buts d'une équipe », « Handicap », « 1re mi-temps ») ; les
  /// marchés du même nom court sont additionnés (chance annoncée pondérée par les sélections).
  static List<Json> _markets(TodayData d) {
    final groups = <String, List<Json>>{};
    for (final m in ((d.dash['markets_30'] as List?) ?? const []).cast<Json>()) {
      if (m['announced'] == null || m['rate'] == null) continue;
      groups.putIfAbsent(shortMarket(m['key'] as String), () => []).add(m);
    }
    final out = <Json>[];
    for (final MapEntry(key: name, value: rows) in groups.entries) {
      if (rows.length == 1) {
        out.add({...rows.single, 'name': name});
        continue;
      }
      var won = 0, lost = 0;
      var weighted = 0.0;
      for (final r in rows) {
        final w = r['won'] as int, l = r['lost'] as int;
        won += w;
        lost += l;
        weighted += (r['announced'] as num) * (w + l);
      }
      final n = won + lost;
      if (n == 0) continue;
      final announced = weighted / n;
      // Même règle que le serveur : écart au-delà de deux écarts-types du hasard (10 sélections au moins).
      final spread = 2 * math.sqrt(math.max(announced * (1 - announced), 1e-9) / n);
      final rate = won / n;
      out.add({
        'name': name,
        'won': won,
        'lost': lost,
        'rate': rate,
        'announced': announced,
        'gap': n < 10
            ? null
            : rate < announced - spread
            ? 'low'
            : rate > announced + spread
            ? 'high'
            : null,
      });
    }
    out.sort(
      (x, y) => ((y['won'] as int) + (y['lost'] as int)).compareTo((x['won'] as int) + (x['lost'] as int)),
    );
    return out.take(4).toList();
  }

  /// Nouveau joueur : cartes de départ au lieu de compteurs à zéro.
  List<Widget> _starter(BuildContext context) {
    final state = context.read<AppState>();
    Widget card(VIcon icon, String title, String text, VoidCallback onTap) => VCard(
      onTap: onTap,
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(color: V.s2, borderRadius: BorderRadius.circular(13)),
            child: Center(child: VIc(icon, color: V.vi2)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: V.b()),
                Text(text, style: V.mu_()),
              ],
            ),
          ),
        ],
      ),
    );
    return [
      const SizedBox(height: 16),
      const VKicker('Pour commencer'),
      card(
        VIcon.ball,
        'Un premier pari, en argent fictif',
        'Touche une cote dans Matchs : la chance du moteur est à côté.',
        () => state.openTab(HomeTab.matchs),
      ),
      card(
        VIcon.ticket,
        'Les coupons du jour',
        'Trois coupons composés chaque matin, avec la cote en face.',
        () => _push(context, const DailyCouponsScreen()),
      ),
      card(
        VIcon.target,
        'Le moteur est-il juste ?',
        'Ce qu\'il annonce, face à ce qui arrive vraiment.',
        () => _push(context, const ReliabilityScreen()),
      ),
    ];
  }
}

/// En-tête : logo, date, « Tableau de bord », recherche et cloche.
class _Header extends StatelessWidget {
  const _Header({required this.unread});
  final int unread;

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Row(
        children: [
          const VLogo(),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(longDate(now), style: V.mu_()),
                Text('Tableau de bord', style: V.b(17)),
              ],
            ),
          ),
          VIconBtn(VIcon.search, tooltip: 'Rechercher', onTap: () => _push(context, const SearchScreen())),
          const SizedBox(width: 10),
          VIconBtn(
            VIcon.bell,
            tooltip: 'Notifications',
            badge: unread,
            onTap: () => _push(context, const NotificationsScreen()),
          ),
        ],
      ),
    );
  }
}

/// Carte du solde : dégradé, montant, variation de la période, courbe violette, périodes.
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
    if (curve.isNotEmpty) points = [...points, (DateTime.now(), balanceNow)];
    final change = points.length >= 2 ? (points.last.$2 - points.first.$2).round() : 0;
    final up = change >= 0;
    return VCard(
      gradient: const LinearGradient(
        // 160deg : du haut un peu à gauche vers le bas un peu à droite.
        begin: Alignment(-0.34, -1),
        end: Alignment(0.34, 1),
        colors: [Color(0xFF1A1A3E), V.s1],
        stops: [0, 0.7],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const VKicker('Solde fictif'),
                    FittedBox(
                      fit: BoxFit.scaleDown,
                      alignment: Alignment.centerLeft,
                      child: Text(fcfa(balanceNow.round(), widget.currency), style: V.big()),
                    ),
                  ],
                ),
              ),
              if (points.length >= 2)
                VChip(
                  '${up ? '+' : '−'}${fcfa(change.abs(), widget.currency)} · ${ranges[range].$1}',
                  kind: up ? VChipKind.up : VChipKind.dn,
                  arrow: Transform.rotate(
                    angle: up ? 0 : math.pi,
                    child: const VIc(VIcon.up, size: 12, stroke: 2.4),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 6),
          SizedBox(
            height: 90,
            child: points.length >= 2
                ? CustomPaint(painter: _CurvePainter([for (final p in points) p.$2]))
                : Center(child: Text('La courbe apparaîtra après tes premiers paris.', style: V.mu_(12))),
          ),
          const SizedBox(height: 6),
          VSeg(
            items: [for (final r in ranges) r.$1],
            selected: range,
            onSelect: (i) => setState(() => range = i),
          ),
        ],
      ),
    );
  }
}

class _CurvePainter extends CustomPainter {
  _CurvePainter(this.values);
  final List<double> values;

  @override
  void paint(Canvas canvas, Size size) {
    final lo = values.reduce(math.min), hi = values.reduce(math.max);
    final span = hi - lo == 0 ? 1.0 : hi - lo;
    // Comme la maquette : de 10 (plus haut) à 84 (plus bas) sur 90.
    Offset at(int i) =>
        Offset(size.width * i / (values.length - 1), size.height * (84 - (values[i] - lo) / span * 74) / 90);
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
          colors: [V.vi.withValues(alpha: 0.35), V.vi.withValues(alpha: 0)],
        ).createShader(Offset.zero & size),
    );
    canvas.drawPath(
      line,
      Paint()
        ..color = V.vi
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.2
        ..strokeJoin = StrokeJoin.round,
    );
    final end = at(values.length - 1);
    canvas.drawCircle(end, 4, Paint()..color = Colors.white);
    canvas.drawCircle(
      end,
      4,
      Paint()
        ..color = V.vi
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2,
    );
  }

  @override
  bool shouldRepaint(_CurvePainter old) => old.values != values;
}

/// Grille 2 × 2 : rendement, paris gagnés, moteur, plan de jeu.
class _Indicators extends StatelessWidget {
  const _Indicators({required this.dash, required this.currency});
  final Json dash;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final m = dash['last_30_days'] as Json;
    final e = dash['engine'] as Json;
    final plan = dash['play_plan'] as Json?;
    final yield_ = (m['yield'] as num?)?.toDouble();
    final settled = m['settled'] as int;
    final won = m['won'] as int;
    final announced = (e['announced'] as num?)?.toDouble();
    final observed = (e['observed'] as num?)?.toDouble();
    final budget = plan?['weekly_budget'] as int?;
    final weekStaked = ((plan?['week'] as Json?)?['staked'] as int?) ?? 0;
    Widget tile(VIcon icon, String label, String value, String sub, {Color? color, VoidCallback? onTap}) =>
        VCard2(
          onTap: onTap,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  VIc(icon, size: 15, color: V.mu),
                  const SizedBox(width: 6),
                  Expanded(child: Text(label, style: V.mu_())),
                ],
              ),
              const SizedBox(height: 6),
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(value, style: V.b(19, color ?? V.tx)),
              ),
              const SizedBox(height: 2),
              Text(sub, maxLines: 1, overflow: TextOverflow.ellipsis, style: V.mu_()),
            ],
          ),
        );
    final tiles = [
      tile(
        VIcon.bars,
        'Rendement',
        yield_ == null ? '—' : '${yield_ >= 0 ? '+' : '−'}${percent(yield_.abs(), decimals: 1)}',
        settled == 0 ? 'aucun pari réglé · 30 j' : 'sur ${fcfa(m['staked'] as int, currency)} misés',
        color: yield_ == null ? null : (yield_ >= 0 ? V.mint : V.coral),
      ),
      tile(
        VIcon.trophy,
        'Paris gagnés',
        settled == 0 ? '—' : '$won / $settled',
        settled == 0 ? '30 j' : '${_pct(won / settled)} · 30 j',
      ),
      tile(
        VIcon.target,
        'Moteur',
        announced == null || observed == null ? '—' : '${_pct(observed)} / ${_pct(announced)}',
        'réalisé / annoncé',
      ),
      tile(
        VIcon.shield,
        'Plan de jeu',
        fcfa(weekStaked, currency),
        budget == null ? 'misés · fixer un budget' : 'sur ${fcfa(budget, currency)} cette sem.',
        color: budget != null && weekStaked >= budget ? V.amber : null,
        onTap: () => _push(context, const PlayPlanScreen()),
      ),
    ];
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(
        children: [
          for (var r = 0; r < 2; r++) ...[
            if (r > 0) const SizedBox(height: 8),
            IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(child: tiles[2 * r]),
                  const SizedBox(width: 8),
                  Expanded(child: tiles[2 * r + 1]),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Carte d'un match en direct de mes paris (230 de large, liseré vert si je gagne).
class _LiveCard extends StatelessWidget {
  const _LiveCard({required this.sel, required this.chances});
  final BetSel sel;
  final Map<int, Json> chances;

  @override
  Widget build(BuildContext context) {
    final s = sel;
    final (chip, kind) = switch (s.now) {
      'win' || 'half_win' => ('gagnant', VChipKind.up),
      'loss' || 'half_loss' => ('perdant', VChipKind.dn),
      'push' || 'void' => ('remboursé', VChipKind.eq),
      _ => (null, VChipKind.eq),
    };
    final p = ((chances[s.matchId]?['markets'] as Map?)?['${s.market}|${s.line}|${s.selection}'] as num?)
        ?.toDouble();
    final label = lowerLabel(
      selectionLabel(s.market, s.line, s.selection, home: s.homeTeam, away: s.awayTeam),
    );
    return SizedBox(
      width: 230,
      child: VCard2(
        border: kind == VChipKind.up ? const Color(0xFF1D5A44) : null,
        onTap: () => _push(context, MatchScreen(matchId: s.matchId)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const VDot(),
                const SizedBox(width: 10),
                Text(
                  '${s.minute ?? ''}${s.extra != null ? '+${s.extra}' : ''}\'',
                  style: V.t(11.5, w: FontWeight.w800, color: V.mint),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    s.competition == null ? '' : competitionName(s.competition!),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: V.mu_(),
                  ),
                ),
                if (chip != null) ...[const SizedBox(width: 10), VChip(chip, kind: kind)],
              ],
            ),
            const SizedBox(height: 8),
            for (final (team, goals) in [(s.homeTeam, s.score?[0]), (s.awayTeam, s.score?[1])])
              Row(
                children: [
                  Expanded(
                    child: Text(team, maxLines: 1, overflow: TextOverflow.ellipsis, style: V.b()),
                  ),
                  Text('${goals ?? '-'}', style: V.b()),
                ],
              ),
            const SizedBox(height: 6),
            Text(
              p == null ? label : '$label · tient à ${_pct(p)}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: V.mu_(),
            ),
          ],
        ),
      ),
    );
  }
}

/// Ligne « mes paris en cours » : anneau de chance, titre, détails, gain possible.
class _BetLine extends StatelessWidget {
  const _BetLine({required this.bet, required this.chances, required this.montantes});
  final Bet bet;
  final Map<int, Json> chances;
  final List<Json> montantes;

  @override
  Widget build(BuildContext context) {
    final b = bet;
    final first = b.selections.first;
    final n = b.selections.length;
    final cur = b.currency;
    final validated = b.selections.where((s) => s.result == 'win' || s.result == 'half_win').length;
    // Palier de montante : « Montante n° 9 · palier 3 ».
    String? montante;
    for (final m in montantes) {
      for (final s in (m['steps'] as List).cast<Json>()) {
        if (s['bet_id'] == b.id) montante = 'Montante n° ${m['id']} · palier ${s['number']}';
      }
    }
    final title =
        montante ??
        (n == 1
            ? selectionLabel(
                first.market,
                first.line,
                first.selection,
                home: first.homeTeam,
                away: first.awayTeam,
              )
            : 'Combiné · $n sélections');
    // Palier de montante pas encore joué : la date du match (maquette 35 « Lens – Lyon · sam. 20:45 »).
    final k = first.kickoffAt?.toLocal();
    final sub = n == 1
        ? '${first.homeTeam} – ${first.awayTeam} · '
              '${montante != null && first.state == 'upcoming' && k != null ? '${shortDate(k).split(' ').first.toLowerCase()} ${hourMinute(k)}' : fcfa(b.stake, cur)}'
        : '${fcfa(b.stake, cur)} · cote ${odds(b.totalOdds)} · $validated sur $n validée${validated > 1 ? 's' : ''}';
    final chance = couponChances(b, chances)?.$2;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => context.read<AppState>().openTab(HomeTab.paris),
      child: Row(
        children: [
          chance == null
              ? Container(
                  width: 44,
                  height: 44,
                  decoration: const BoxDecoration(color: V.s3, shape: BoxShape.circle),
                  alignment: Alignment.center,
                  child: Text('—', style: V.b(11)),
                )
              : VRing(chance, size: 44, inner: 34, fontSize: 11),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, maxLines: 1, overflow: TextOverflow.ellipsis, style: V.b()),
                Text(sub, maxLines: 2, overflow: TextOverflow.ellipsis, style: V.mu_()),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Text(fcfa(b.potentialPayout, cur), style: V.b()),
        ],
      ),
    );
  }
}

/// « Occasions du jour » : sélections où le moteur dépasse la cote, puis l'alerte de cote.
class _Occasions extends StatefulWidget {
  const _Occasions({required this.items});
  final List<Json> items;

  @override
  State<_Occasions> createState() => _OccasionsState();
}

class _OccasionsState extends State<_Occasions> {
  bool all = false;

  @override
  Widget build(BuildContext context) {
    final items = widget.items;
    return VCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          VHead(
            'Occasions du jour',
            link: items.length > 3 ? (all ? 'Moins' : 'Toutes') : null,
            onLink: () => setState(() => all = !all),
          ),
          if (items.isEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                'Aucune sélection des 36 prochaines heures où le moteur dépasse la cote.',
                style: V.mu_(),
              ),
            )
          else
            VList(children: [for (final a in all ? items : items.take(3)) _OccasionLine(a: a)]),
          VBtn2(
            'Créer une alerte de cote',
            icon: VIcon.bell,
            onTap: () => _push(context, const OddsAlertsScreen()),
          ),
        ],
      ),
    );
  }
}

class _OccasionLine extends StatelessWidget {
  const _OccasionLine({required this.a});
  final Json a;

  @override
  Widget build(BuildContext context) {
    final home = a['home'] as String, away = a['away'] as String;
    final engine = (a['engine'] as num).toDouble(), implied = (a['implied'] as num).toDouble();
    final label = lowerLabel(
      selectionLabel(
        a['market'] as String,
        (a['line'] ?? '') as String,
        a['selection'] as String,
        home: home,
        away: away,
      ),
    );
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => _push(context, MatchScreen(matchId: a['match_id'] as int)),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('$home – $away', maxLines: 1, overflow: TextOverflow.ellipsis, style: V.b()),
                Text(
                  '$label · ${_pct(engine)} / ${_pct(implied)}',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: V.mu_(),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          VGapChip(engine: engine, implied: implied),
          const SizedBox(width: 10),
          VOdd(odds(a['odds'])),
        ],
      ),
    );
  }
}

/// « Coupons du jour » : trois cases, cote et pastille moteur contre cote.
class _Daily extends StatelessWidget {
  const _Daily({required this.coupons});
  final List<Json> coupons;

  @override
  Widget build(BuildContext context) => VCard(
    onTap: () => _push(context, const DailyCouponsScreen()),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const VKicker('Coupons du jour'),
        const SizedBox(height: 8),
        Row(
          children: [
            for (final (i, c) in coupons.take(3).indexed) ...[
              if (i > 0) const SizedBox(width: 6),
              Expanded(
                child: VCard2(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${c['profile_label'] ?? c['profile']}', style: V.mu_()),
                      Text(odds(c['total_odds']), style: V.b()),
                      if (c['probability'] is num && c['total_odds'] != null) ...[
                        const SizedBox(height: 4),
                        FittedBox(
                          fit: BoxFit.scaleDown,
                          alignment: Alignment.centerLeft,
                          child: VGapChip(
                            engine: (c['probability'] as num).toDouble(),
                            implied: 1 / double.parse('${c['total_odds']}'),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ],
    ),
  );
}

/// « Montante n° 9 » : paliers en barres, puis si ça passe, si j'arrête, si ça rate.
class _Montante extends StatelessWidget {
  const _Montante({required this.m, required this.currency});
  final Json m;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final steps = (m['steps'] as List).cast<Json>();
    final current = m['current_step'] as int? ?? 1;
    final step = steps.where((s) => s['number'] == current).firstOrNull;
    final stake = (step?['stake'] as num?)?.toInt();
    // Pari du palier placé : gain exact ; sinon à la cote du milieu de la plage, arrondi (comme l'écran 15).
    final placed = (step?['potential_payout'] as num?)?.toInt();
    final lo = double.tryParse('${step?['odds_min']}'), hi = double.tryParse('${step?['odds_max']}');
    final payout =
        placed ??
        (stake == null || lo == null || hi == null
            ? null
            : stake + ((stake * (lo + hi) / 2 - stake) / 100).round() * 100);
    final cashable = (m['cashable'] as num? ?? 0).toInt();
    Widget col(String label, String value, Color color) => Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: V.mu_()),
          Text(value, style: V.b(13.5, color)),
        ],
      ),
    );
    return VCard(
      onTap: () => context.read<AppState>().openTab(HomeTab.montante),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(child: VKicker('Montante n° ${m['id']}')),
              Text('palier $current sur ${steps.length}', style: V.mu_()),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              for (final (i, s) in steps.indexed) ...[
                if (i > 0) const SizedBox(width: 4),
                Expanded(
                  child: Container(
                    height: 6,
                    decoration: BoxDecoration(
                      color: switch (s['result']) {
                        'won' || 'win' => V.mint,
                        'lost' || 'loss' => V.coral,
                        _ => s['number'] == current ? V.vi : V.s3,
                      },
                      borderRadius: BorderRadius.circular(3),
                    ),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              col(
                'si ça passe',
                payout == null || stake == null ? '—' : '+${fcfa(payout - stake, currency)}',
                V.mint,
              ),
              col('si j\'arrête', fcfa(cashable, currency), V.tx),
              col('si ça rate', stake == null ? '—' : '−${fcfa(stake, currency)}', V.coral),
            ],
          ),
        ],
      ),
    );
  }
}

/// « Où le moteur tient parole (30 j) » : barre du réalisé, trait ambre de l'annoncé.
class _Markets extends StatelessWidget {
  const _Markets({required this.rows});
  final List<Json> rows;

  @override
  Widget build(BuildContext context) => VCard(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const VKicker('Où le moteur tient parole (30 j)'),
        for (final r in rows)
          Padding(
            padding: const EdgeInsets.only(top: 9),
            child: Row(
              children: [
                SizedBox(
                  width: 110,
                  child: Text(
                    r['name'] as String,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: V.t(12.5, color: V.mu),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: VGauge(
                    value: (r['rate'] as num).toDouble(),
                    mark: (r['announced'] as num).toDouble(),
                    color: switch (r['gap']) {
                      'low' => V.coral,
                      'high' => V.mint,
                      _ => V.vi,
                    },
                  ),
                ),
                const SizedBox(width: 10),
                SizedBox(
                  width: 46,
                  child: Text(_pct((r['rate'] as num).toDouble()), textAlign: TextAlign.right, style: V.b()),
                ),
              ],
            ),
          ),
        const SizedBox(height: 8),
        Text('trait ambre : chance annoncée · barre : réalisé', style: V.mu_()),
      ],
    ),
  );
}
