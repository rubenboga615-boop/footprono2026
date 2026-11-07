// Éléments de la maquette validée le 07/11/2026 (accueil, profil, écran verrouillé,
// matchs) : mêmes tailles, couleurs et coins arrondis que la maquette, valeur par valeur.
import 'package:flutter/material.dart';

import '../theme.dart';

/// Couleurs de la maquette (rgba écrits comme dans la maquette).
abstract final class M {
  static const card = Color(0xCC12101A);
  static const border = Color(0x1FFFFFFF);
  static const hlBorder = Color(0x997C3AED);
  static const hlTop = Color(0xCC2A1655);
  static const muted = Color(0xC7F4F2F8); // 78 %
  static const small = Color(0xB8F4F2F8); // 72 %
  static const line = Color(0x12FFFFFF);
  static const line10 = Color(0x10FFFFFF);
  static const head = Color(0xA0F4F2F8);
  static const lock = Color(0xFFC9B2F8);
  static const green = Color(0xFF34D399);
  static const pink = Color(0xFFF9A8D4);
}

/// Titre de la maquette : Sora 23, second mot violet clair.
class MTitle extends StatelessWidget {
  const MTitle(this.first, [this.second = '', this.size = 23]) : super(key: null);
  final String first;
  final String second;
  final double size;

  @override
  Widget build(BuildContext context) => Text.rich(
    TextSpan(
      children: [
        TextSpan(text: second.isEmpty ? first : '$first '),
        if (second.isNotEmpty)
          TextSpan(
            text: second,
            style: const TextStyle(color: Fp.accentLight),
          ),
      ],
    ),
    style: Fp.title(size),
  );
}

/// Carte : coins arrondis 18, bordure fine ; ``highlight`` : bordure violette et dégradé.
class MCard extends StatelessWidget {
  const MCard({
    super.key,
    required this.child,
    this.highlight = false,
    this.padding = const EdgeInsets.all(14),
    this.margin = const EdgeInsets.only(top: 12),
  });
  final Widget child;
  final bool highlight;
  final EdgeInsets padding;
  final EdgeInsets margin;

  @override
  Widget build(BuildContext context) => Container(
    margin: margin,
    padding: padding,
    decoration: BoxDecoration(
      color: highlight ? null : M.card,
      gradient: highlight
          ? const LinearGradient(
              begin: Alignment(-0.4, -1),
              end: Alignment(0.4, 1),
              colors: [M.hlTop, M.card],
            )
          : null,
      borderRadius: BorderRadius.circular(18),
      border: Border.all(color: highlight ? M.hlBorder : M.border),
    ),
    child: child,
  );
}

/// Bouton principal (violet) ou secondaire (bordure), pleine largeur, coins 14.
class MButton extends StatelessWidget {
  const MButton(this.label, {super.key, required this.onPressed, this.secondary = false, this.busy = false});
  final String label;
  final VoidCallback? onPressed;
  final bool secondary;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(14));
    final child = busy
        ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
        : Text(label, textAlign: TextAlign.center);
    return SizedBox(
      width: double.infinity,
      child: secondary
          ? OutlinedButton(
              onPressed: onPressed,
              style: OutlinedButton.styleFrom(
                shape: shape,
                padding: const EdgeInsets.symmetric(vertical: 11, horizontal: 12),
                minimumSize: const Size(0, 42),
                visualDensity: VisualDensity.standard,
                backgroundColor: Colors.transparent,
                side: const BorderSide(color: Color(0x33FFFFFF)),
                foregroundColor: const Color(0xD0F4F2F8),
                textStyle: Fp.body(14, weight: FontWeight.w700),
              ),
              child: child,
            )
          : FilledButton(
              onPressed: onPressed,
              style: FilledButton.styleFrom(
                shape: shape,
                padding: const EdgeInsets.symmetric(vertical: 13, horizontal: 12),
                minimumSize: const Size(0, 46),
                visualDensity: VisualDensity.standard,
                elevation: 0,
                backgroundColor: Fp.accent,
                foregroundColor: Colors.white,
                textStyle: Fp.body(15, weight: FontWeight.w700),
              ),
              child: child,
            ),
    );
  }
}

/// Pastille : texte 11 gras, fond doux (« 2 000 F / mois », « Gagné »).
class MPill extends StatelessWidget {
  const MPill(this.text, {super.key, this.color = M.lock, this.background = const Color(0x337C3AED)});
  const MPill.win(this.text, {super.key}) : color = M.green, background = const Color(0x2234D399);
  const MPill.loss(this.text, {super.key}) : color = M.pink, background = const Color(0x22F472B6);
  final String text;
  final Color color;
  final Color background;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 2),
    decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(99)),
    child: Text(
      text,
      style: Fp.body(11, weight: FontWeight.w700, color: color),
    ),
  );
}

/// Petite pastille de filtre (« Sam. 7 », « Tous championnats ▾ »).
class MChip extends StatelessWidget {
  const MChip(this.label, {super.key, this.selected = false, required this.onTap});
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
    color: selected ? Fp.accent : Colors.transparent,
    shape: StadiumBorder(side: BorderSide(color: selected ? Fp.accent : const Color(0x22FFFFFF))),
    child: InkWell(
      customBorder: const StadiumBorder(),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        child: Text(label, style: Fp.body(12.5, color: Fp.text)),
      ),
    ),
  );
}
