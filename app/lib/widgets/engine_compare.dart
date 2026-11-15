// Comparaison des moteurs (maquettes K1-K6 validées le 15/11/2026) : le moteur 1 (inchangé)
// et le moteur 2 (le même, calé sur la cote de référence), côte à côte, pour que le joueur
// juge lui-même. Montré seulement avec « Comparer les deux moteurs » (Profil).
import 'package:flutter/material.dart';

import '../api/models.dart';
import '../format.dart';
import '../theme.dart';

const engine1Color = Fp.accentLight;
const engine2Color = Color(0xFF4FC3F7);

/// « moteur 1 41 % · moteur 2 45 % » d'une sélection (fiche de match, K2).
class EngineCompareLine extends StatelessWidget {
  const EngineCompareLine({super.key, required this.engine1, required this.engine2});
  final double? engine1;
  final double engine2;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 3),
    child: Text.rich(
      TextSpan(
        children: [
          TextSpan(
            text: 'moteur 1 ${engine1 == null ? '—' : percent(engine1!)}',
            style: Fp.body(12, weight: FontWeight.w700, color: engine1Color),
          ),
          TextSpan(
            text: ' · ',
            style: Fp.body(12, color: Fp.text3),
          ),
          TextSpan(
            text: 'moteur 2 ${percent(engine2)}',
            style: Fp.body(12, weight: FontWeight.w700, color: engine2Color),
          ),
        ],
      ),
    ),
  );
}

/// Ligne de comparaison d'une offre, ou rien hors du mode comparaison.
Widget engineCompareOf(Offer? o) => o?.engine2Probability == null
    ? const SizedBox.shrink()
    : EngineCompareLine(engine1: o!.modelProbability, engine2: o.engine2Probability!);

/// « Moteur 2 calé » ou « non calé » pour ce match (K2).
class Engine2Status extends StatelessWidget {
  const Engine2Status(this.calibrated, {super.key});
  final bool calibrated;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.fromLTRB(12, 9, 12, 9),
    decoration: BoxDecoration(
      color: engine2Color.withValues(alpha: 0.10),
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: engine2Color.withValues(alpha: 0.35)),
    ),
    child: Text(
      calibrated
          ? 'Comparaison : moteur 2 calé sur la cote de référence pour ce match.'
          : 'Comparaison : moteur 2 non calé pour ce match (pas de cote de référence récente) : '
                'il donne les mêmes chances que le moteur 1.',
      style: Fp.body(12, color: Fp.text2, height: 1.4),
    ),
  );
}

/// Étiquette « MOTEUR 1 » / « MOTEUR 2 » d'un coupon (K3).
class EngineTag extends StatelessWidget {
  const EngineTag(this.engine, {super.key});
  final int engine;

  @override
  Widget build(BuildContext context) {
    final color = engine == 2 ? engine2Color : engine1Color;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.16), borderRadius: BorderRadius.circular(8)),
      child: Text(
        'MOTEUR $engine',
        style: Fp.body(11.5, weight: FontWeight.w800, color: color),
      ),
    );
  }
}
