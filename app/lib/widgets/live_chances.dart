// Chances du moteur pendant le match (plan du 10/11/2026, étape 6 ; maquettes D2 et D7).
// Rien n'est affiché tant que la console ne les a pas publiées après une vérification juste :
// le serveur répond alors « published: false » et ces cartes restent invisibles.

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../format.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Chances du moment des matchs demandés : {match: {minute, extra, markets: {clé: chance}}} ;
/// vide si non publiées ou en cas d'erreur (l'écran reste tel qu'avant le direct).
Future<Map<int, Json>> loadLiveChances(ApiClient api, Iterable<int> matchIds) async {
  final ids = matchIds.toSet();
  if (ids.isEmpty) return {};
  try {
    final r = await api.get('/live/chances?${ids.map((i) => 'match_ids=$i').join('&')}') as Json;
    if (r['published'] != true) return {};
    return {for (final e in (r['matches'] as Map).entries) int.parse('${e.key}'): (e.value as Json)};
  } on ApiException {
    return {};
  }
}

String _key(BetSel s) => '${s.market}|${s.line}|${s.selection}';

/// Chance du coupon au départ (chances du moteur au moment du pari) et maintenant : sélection
/// gagnée 1, remboursée 1, à venir sa chance d'avant le match, en cours sa chance du moment.
/// Null si une chance manque (match en cours sans chance calculée, carton rouge…) ou si le
/// coupon est déjà perdu : rien plutôt qu'un chiffre faux.
(double, double)? couponChances(Bet b, Map<int, Json> live) {
  var start = 1.0, current = 1.0;
  for (final s in b.selections) {
    final p = s.modelProbability;
    if (p == null) return null;
    start *= p;
    switch (s.result) {
      case 'win' || 'half_win' || 'push' || 'void':
        continue;
      case 'loss' || 'half_loss':
        return null;
    }
    if (s.state == 'live' || s.state == 'finished') {
      final now = ((live[s.matchId]?['markets'] as Map?)?[_key(s)] as num?)?.toDouble();
      if (now == null) return null;
      current *= now;
    } else {
      current *= p;
    }
  }
  return (start, current);
}

/// Encadré vert de la fiche d'un pari en cours (maquette D7).
class LiveCouponChance extends StatefulWidget {
  const LiveCouponChance(this.bet, {super.key});
  final Bet bet;

  @override
  State<LiveCouponChance> createState() => _LiveCouponChanceState();
}

class _LiveCouponChanceState extends State<LiveCouponChance> {
  late final Future<Map<int, Json>> _live = loadLiveChances(context.read<AppState>().api, [
    for (final s in widget.bet.selections)
      if (s.state == 'live') s.matchId,
  ]);

  @override
  Widget build(BuildContext context) => FutureBuilder<Map<int, Json>>(
    future: _live,
    builder: (context, snap) {
      final live = snap.data;
      if (live == null || live.isEmpty) return const SizedBox.shrink();
      final c = couponChances(widget.bet, live);
      if (c == null) return const SizedBox.shrink();
      final (start, now) = c;
      return Container(
        margin: const EdgeInsets.only(top: 10, bottom: 4),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: const Color(0xFF12301F),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFF1F5B3A)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Chance de ton coupon : ${percent(start)} au départ → ${percent(now)} maintenant',
              style: Fp.body(14.5, weight: FontWeight.w700, color: Fp.win, height: 1.35),
            ),
            const SizedBox(height: 4),
            Text('D\'après le score et la minute de chaque match.', style: Fp.body(12.5, color: Fp.text2)),
          ],
        ),
      );
    },
  );
}

/// Carte « Chances en direct » de l'écran d'un match (maquette D2).
class LiveChancesCard extends StatefulWidget {
  const LiveChancesCard({super.key, required this.match, this.before});
  final MatchInfo match;

  /// Chances d'avant le match (1, N, 2), pour comparer.
  final (double, double, double)? before;

  @override
  State<LiveChancesCard> createState() => _LiveChancesCardState();
}

class _LiveChancesCardState extends State<LiveChancesCard> {
  late final Future<Map<int, Json>> _live = loadLiveChances(context.read<AppState>().api, [widget.match.id]);

  @override
  Widget build(BuildContext context) => FutureBuilder<Map<int, Json>>(
    future: _live,
    builder: (context, snap) {
      final j = snap.data?[widget.match.id];
      final markets = j?['markets'] as Map?;
      double? p(String k) => (markets?[k] as num?)?.toDouble();
      final home = p('1X2||home'), draw = p('1X2||draw'), away = p('1X2||away');
      if (j == null || home == null || draw == null || away == null) return const SizedBox.shrink();
      final m = widget.match;
      final extra = (j['extra'] as int? ?? 0) > 0 ? '+${j['extra']}' : '';
      final best = [home, draw, away].reduce((a, b) => a > b ? a : b);
      Widget cell(String label, double v) => Expanded(
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            color: Fp.background,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: v == best ? Fp.accent2 : Fp.background, width: 1.5),
          ),
          child: Column(
            children: [
              Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Fp.body(13, color: Fp.muted),
              ),
              Text(percent(v), style: Fp.body(17, weight: FontWeight.w800)),
            ],
          ),
        ),
      );
      final over = p('OU|3.5|over');
      final b = widget.before;
      return Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(color: Fp.card, borderRadius: BorderRadius.circular(18)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('Chances en direct', style: Fp.body(17, weight: FontWeight.w700)),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                  decoration: BoxDecoration(color: Fp.cardHigh, borderRadius: BorderRadius.circular(10)),
                  child: Text(
                    '${j['minute']}$extra\'',
                    style: Fp.body(13, weight: FontWeight.w700, color: Fp.lilac),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                cell(m.home.name, home),
                const SizedBox(width: 8),
                cell('Nul', draw),
                const SizedBox(width: 8),
                cell(m.away.name, away),
              ],
            ),
            if (over != null && over > 0.005 && over < 0.995) ...[
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: Text('Plus de 3,5 buts', style: Fp.body(14, color: Fp.muted)),
                  ),
                  Text(percent(over), style: Fp.body(15, weight: FontWeight.w700)),
                ],
              ),
            ],
            const SizedBox(height: 8),
            Text(
              [
                if (b != null) 'Avant le match : ${percent(b.$1)} · ${percent(b.$2)} · ${percent(b.$3)}.',
                'Recalculé avec le score et la minute ; ce n\'est pas un conseil de pari.',
              ].join(' '),
              style: Fp.body(12.5, color: Fp.text2, height: 1.4),
            ),
          ],
        ),
      );
    },
  );
}
