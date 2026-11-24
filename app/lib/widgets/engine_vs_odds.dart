// Moteur contre cote (maquettes P1 et P2 validées le 14/11/2026) : la chance du moteur et la
// chance selon la cote (1 / cote, marge du bookmaker comprise), côte à côte. On informe, on
// n'interdit rien ; le moteur et ses choix ne changent pas. Jamais « value » ni « bon plan ».
import 'package:flutter/material.dart';

import '../format.dart';
import '../theme.dart';

/// Où se place le moteur par rapport à la cote, en points arrondis (étape A du nouveau
/// visage, 20/11/2026) : 3 points ou plus au-dessus, 3 points ou plus en dessous, sinon
/// d'accord (« ≈ cote », de −2 à +2).
enum OddsSide { below, agree, above }

/// Écart moteur − cote en points entiers (75 % contre 81 % : −6).
int gapPoints(double engine, double implied) => ((engine - implied) * 100).round();

OddsSide oddsSide(double engine, double implied) {
  final pts = gapPoints(engine, implied);
  return pts <= -3
      ? OddsSide.below
      : pts >= 3
      ? OddsSide.above
      : OddsSide.agree;
}

// Décision du 24/11/2026 : un moteur plus optimiste que la cote n'est jamais présenté comme une
// raison de jouer (ses plus gros écarts sont surtout ses erreurs) : ambre, pour prévenir.
// Moins confiant que la cote : gris, simple information.
Color oddsSideColor(OddsSide side) => switch (side) {
  OddsSide.below => Fp.muted,
  OddsSide.above => Fp.warning,
  OddsSide.agree => Fp.muted,
};

/// Pastille unique « moteur contre cote », sur chaque sélection, coupon, proposition :
/// « ▲ +5 pts » (ambre : prudence), « ≈ cote » et « ▼ −6 pts » (gris).
class GapBadge extends StatelessWidget {
  const GapBadge({super.key, required this.engine, required this.implied, this.nation = false});
  final double engine;
  final double implied;
  final bool nation;

  @override
  Widget build(BuildContext context) {
    final side = oddsSide(engine, implied);
    final pts = gapPoints(engine, implied);
    final color = nation && side == OddsSide.above ? Fp.warning : oddsSideColor(side);
    // Flèches et « ≈ » dessinés : ces signes ne sont pas dans la police Inter de l'application
    // (réduite aux caractères latins) et s'afficheraient en carrés vides sur le web.
    final label = switch (side) {
      OddsSide.above => '+$pts pts',
      OddsSide.below => '−${-pts} pts',
      OddsSide.agree => 'cote',
    };
    final mark = switch (side) {
      OddsSide.above => Icon(Icons.arrow_drop_up_rounded, size: 18, color: color),
      OddsSide.below => Icon(Icons.arrow_drop_down_rounded, size: 18, color: color),
      OddsSide.agree => CustomPaint(size: const Size(12, 10), painter: _ApproxPainter(color)),
    };
    return Tooltip(
      message:
          'Moteur ${percent(engine)}, selon la cote ${percent(implied)}'
          '${side == OddsSide.above ? ' · la vraie chance est probablement plus proche de celle du bookmaker' : ''}',
      child: Container(
        padding: const EdgeInsets.fromLTRB(4, 3, 8, 3),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(width: 18, child: Center(child: mark)),
            if (side == OddsSide.agree) const SizedBox(width: 2),
            Text(
              label,
              style: Fp.body(11.5, weight: FontWeight.w700, color: color),
            ),
          ],
        ),
      ),
    );
  }
}

/// « ≈ » dessiné (deux vagues).
class _ApproxPainter extends CustomPainter {
  const _ApproxPainter(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final pen = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.6
      ..strokeCap = StrokeCap.round;
    for (final y in [size.height * 0.32, size.height * 0.72]) {
      final w = size.width;
      final path = Path()
        ..moveTo(0, y)
        ..quadraticBezierTo(w * 0.25, y - 2.4, w * 0.5, y)
        ..quadraticBezierTo(w * 0.75, y + 2.4, w, y);
      canvas.drawPath(path, pen);
    }
  }

  @override
  bool shouldRepaint(_ApproxPainter old) => old.color != color;
}

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
        Fp.lossBg,
        Fp.lossLine,
      ),
      OddsSide.above => (
        'Le moteur est un peu plus confiant que la cote ($e contre $c). L\'écart ne garantit rien : '
            '$what perd environ $loses fois sur 10.',
        Fp.winBg,
        Fp.winLine,
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
        bar('Selon la cote', implied, Fp.warning),
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
                OddsSide.below => Fp.lossSoft,
                OddsSide.above => Fp.winSoft,
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

/// Pastille d'une sélection : la même pastille « moteur contre cote » partout.
class OddsPill extends StatelessWidget {
  const OddsPill({super.key, required this.engine, required this.implied, this.nation = false});
  final double engine;
  final double implied;
  final bool nation;

  @override
  Widget build(BuildContext context) => GapBadge(engine: engine, implied: implied, nation: nation);
}

/// Pastille d'un coupon dont on connaît seulement le côté (coupons du jour).
class OddsSideTag extends StatelessWidget {
  const OddsSideTag(this.side, {super.key, this.engine, this.implied});
  final OddsSide side;
  final double? engine;
  final double? implied;

  @override
  Widget build(BuildContext context) {
    if (engine != null && implied != null) return GapBadge(engine: engine!, implied: implied!);
    final color = oddsSideColor(side);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(8)),
      child: Text(switch (side) {
        OddsSide.below => 'sous la cote',
        OddsSide.above => 'au-dessus de la cote',
        OddsSide.agree => 'd\'accord avec la cote',
      }, style: Fp.body(11.5, weight: FontWeight.w700, color: color)),
    );
  }
}
