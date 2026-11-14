// Moteur contre cote (maquettes P1 et P2 validées le 14/11/2026) : la chance du moteur et la
// chance selon la cote (1 / cote, marge du bookmaker comprise), côte à côte. On informe, on
// n'interdit rien ; le moteur et ses choix ne changent pas. Jamais « value » ni « bon plan ».
import 'package:flutter/material.dart';

import '../format.dart';
import '../theme.dart';

/// Où se place le moteur par rapport à la cote : au moins 2 points sous, au moins 2 points
/// au-dessus, ou d'accord (même règle que la montante et le coupon en direct).
enum OddsSide { below, agree, above }

OddsSide oddsSide(double engine, double implied) => engine <= implied - 0.02
    ? OddsSide.below
    : engine >= implied + 0.02
    ? OddsSide.above
    : OddsSide.agree;

Color oddsSideColor(OddsSide side) => switch (side) {
  OddsSide.below => Fp.warning,
  OddsSide.above => Fp.win,
  OddsSide.agree => Fp.muted,
};

/// Barres « Le moteur » et « Selon la cote », puis une phrase : ambre si le moteur est sous
/// la cote, vert s'il est au-dessus (« ne garantit rien »), gris s'ils sont d'accord.
class EngineVsOdds extends StatelessWidget {
  const EngineVsOdds({super.key, required this.engine, required this.implied, this.what = 'ce coupon'});
  final double engine;
  final double implied;
  final String what;

  @override
  Widget build(BuildContext context) {
    final side = oddsSide(engine, implied);
    final color = oddsSideColor(side);
    final e = percent(engine), c = percent(implied);
    final loses = ((1 - engine) * 10).round().clamp(1, 9);
    final (text, bg, border) = switch (side) {
      OddsSide.below => (
        'Le moteur est moins confiant que la cote sur $what : $e contre $c.',
        const Color(0xFF1F1709),
        const Color(0xFF6B4F1D),
      ),
      OddsSide.above => (
        'Le moteur est un peu plus confiant que la cote ($e contre $c). L\'écart ne garantit rien : '
            '$what perd environ $loses fois sur 10.',
        const Color(0xFF12301F),
        const Color(0xFF1F5B3A),
      ),
      OddsSide.agree => ('Le moteur et la cote sont d\'accord ($e et $c).', Fp.card, Fp.line10),
    };
    Widget bar(String label, double v, Color fill) => Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Row(
        children: [
          SizedBox(
            width: 92,
            child: Text(label, style: Fp.body(12.5, color: Fp.text2)),
          ),
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: v.clamp(0.0, 1.0),
                minHeight: 7,
                backgroundColor: Fp.line10,
                color: fill,
              ),
            ),
          ),
          const SizedBox(width: 10),
          SizedBox(
            width: 42,
            child: Text(
              percent(v),
              textAlign: TextAlign.right,
              style: Fp.body(12.5, weight: FontWeight.w700),
            ),
          ),
        ],
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        bar('Le moteur', engine, color),
        bar('Selon la cote', implied, Fp.lilac),
        Container(
          margin: const EdgeInsets.only(top: 10),
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: border),
          ),
          child: Text(
            text,
            style: Fp.body(
              12.5,
              color: switch (side) {
                OddsSide.below => Fp.warning,
                OddsSide.above => const Color(0xFFC9F5D9),
                OddsSide.agree => Fp.text2,
              },
              height: 1.4,
            ),
          ),
        ),
      ],
    );
  }
}

/// Pastille « moteur 75 % · cote 81 % » d'une sélection.
class OddsPill extends StatelessWidget {
  const OddsPill({super.key, required this.engine, required this.implied});
  final double engine;
  final double implied;

  @override
  Widget build(BuildContext context) {
    final color = oddsSideColor(oddsSide(engine, implied));
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(8)),
      child: Text(
        'moteur ${percent(engine)} · cote ${percent(implied)}',
        style: Fp.body(11.5, weight: FontWeight.w700, color: color),
      ),
    );
  }
}

/// Étiquette « au-dessus de la cote », « d'accord avec la cote », « ⚠ sous la cote ».
class OddsSideTag extends StatelessWidget {
  const OddsSideTag(this.side, {super.key});
  final OddsSide side;

  @override
  Widget build(BuildContext context) {
    final color = oddsSideColor(side);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(8)),
      child: Text(switch (side) {
        OddsSide.below => '⚠ sous la cote',
        OddsSide.above => 'au-dessus de la cote',
        OddsSide.agree => 'd\'accord avec la cote',
      }, style: Fp.body(11.5, weight: FontWeight.w700, color: color)),
    );
  }
}
