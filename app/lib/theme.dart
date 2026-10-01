// Direction « Verre violet » validée le 30/09/2026 (docs/DESIGN.md). Valeurs
// reprises des maquettes (A-*.dc.html) : fond, halos, rubans, cartes, boutons.
import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/material.dart';

class Fp {
  static const background = Color(0xFF060509);
  static const accent = Color(0xFF7C3AED);
  // Accent mélangé à 45 % de blanc : texte sur fond sombre.
  static const accentLight = Color(0xFFB793F5);
  static const text = Color(0xFFF4F2F8);
  static const text2 = Color(0xADF4F2F8); // 68 %
  static const text3 = Color(0x9EF4F2F8); // 62 %
  static const text4 = Color(0x8CF4F2F8); // 55 %
  static const textSoft = Color(0xC7F4F2F8); // 78 %
  static const textStrong = Color(0xD1F4F2F8); // 82 %
  static const win = Color(0xFF34D399);
  static const loss = Color(0xFFF472B6);
  static const lossText = Color(0xFFF9A8D4);
  static const warning = Color(0xFFFBBF24);
  static const glass = Color(0xB812101A); // rgba(18,16,26,0.72)
  static const fill = Color(0x0DFFFFFF); // blanc 5 %
  static const fill6 = Color(0x0FFFFFFF); // blanc 6 %
  static const fill7 = Color(0x12FFFFFF); // blanc 7 %
  static const line = Color(0x24FFFFFF); // blanc 14 %
  static const line12 = Color(0x1FFFFFFF);
  static const line10 = Color(0x1AFFFFFF);
  static const divider = Color(0x12FFFFFF); // blanc 7 %

  static Color accentAlpha(double a) => accent.withValues(alpha: a);
  static final accentSoft = accentAlpha(0.16);
  static final accentFaint = accentAlpha(0.08);
  static final accentLine = accentAlpha(0.5);
  static const accentBar = LinearGradient(colors: [accent, accentLight]);

  static const titleFont = 'Sora';
  static const bodyFont = 'PlusJakartaSans';

  static TextStyle title(double size, {Color color = text, FontWeight weight = FontWeight.w700}) => TextStyle(
    fontFamily: titleFont,
    fontSize: size,
    fontWeight: weight,
    color: color,
    letterSpacing: size >= 20 ? -0.02 * size : -0.01 * size,
    height: 1.15,
  );

  static TextStyle body(
    double size, {
    Color color = text,
    FontWeight weight = FontWeight.w400,
    double? height,
  }) => TextStyle(fontFamily: bodyFont, fontSize: size, fontWeight: weight, color: color, height: height);

  static final radius14 = BorderRadius.circular(14);

  static ThemeData theme() {
    final scheme = ColorScheme.fromSeed(
      seedColor: accent,
      brightness: Brightness.dark,
      primary: accent,
      onPrimary: Colors.white,
      surface: const Color(0xFF12101A),
      onSurface: text,
      error: loss,
    );
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: Colors.transparent,
      canvasColor: const Color(0xFF15121F),
      fontFamily: bodyFont,
      textTheme: ThemeData.dark().textTheme.apply(fontFamily: bodyFont, bodyColor: text, displayColor: text),
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        foregroundColor: text,
        titleTextStyle: title(18),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: fill,
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        hintStyle: body(15, color: const Color(0x80F4F2F8)),
        labelStyle: body(14, color: text2),
        prefixIconColor: text2,
        suffixIconColor: text2,
        suffixStyle: body(14, color: accentLight, weight: FontWeight.w600),
        border: OutlineInputBorder(
          borderRadius: radius14,
          borderSide: const BorderSide(color: line),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: radius14,
          borderSide: const BorderSide(color: line),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: radius14,
          borderSide: BorderSide(color: accentLine, width: 1.2),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: accent,
          foregroundColor: Colors.white,
          disabledBackgroundColor: accentAlpha(0.35),
          disabledForegroundColor: Colors.white70,
          minimumSize: const Size(0, 52),
          elevation: 10,
          shadowColor: accentAlpha(0.7),
          textStyle: body(15, weight: FontWeight.w700),
          shape: RoundedRectangleBorder(borderRadius: radius14),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: text,
          backgroundColor: fill,
          minimumSize: const Size(0, 48),
          side: const BorderSide(color: line),
          textStyle: body(14, weight: FontWeight.w600),
          shape: RoundedRectangleBorder(borderRadius: radius14),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: accentLight,
          textStyle: body(14, weight: FontWeight.w700),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: const Color(0xFF1C1828),
        contentTextStyle: body(14),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: radius14,
          side: const BorderSide(color: line),
        ),
      ),
      dividerTheme: const DividerThemeData(color: divider, space: 1, thickness: 1),
      checkboxTheme: CheckboxThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        fillColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? accent : fill),
        side: const BorderSide(color: line),
      ),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? Colors.white : const Color(0xFFE9E6F2),
        ),
        trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? accent : fill7),
        trackOutlineColor: const WidgetStatePropertyAll(line),
      ),
      sliderTheme: SliderThemeData(
        activeTrackColor: accent,
        inactiveTrackColor: fill7,
        thumbColor: Colors.white,
        overlayColor: accentAlpha(0.2),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: const Color(0xFF15121F),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: const BorderSide(color: line),
        ),
        titleTextStyle: title(18),
        contentTextStyle: body(14, color: text2, height: 1.45),
      ),
      bottomSheetTheme: const BottomSheetThemeData(backgroundColor: Color(0xFF15121F)),
      progressIndicatorTheme: const ProgressIndicatorThemeData(color: accentLight),
      popupMenuTheme: const PopupMenuThemeData(color: Color(0xFF1A1626)),
    );
  }
}

// --- Fond ------------------------------------------------------------------

/// Fond des maquettes : noir violacé, deux halos, rubans lumineux diagonaux.
/// Dessiné une seule fois (aucune animation : économie de batterie).
class FpBackground extends StatelessWidget {
  const FpBackground({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        const Positioned.fill(
          child: RepaintBoundary(child: CustomPaint(painter: _BackgroundPainter())),
        ),
        Positioned.fill(child: child),
      ],
    );
  }
}

class _BackgroundPainter extends CustomPainter {
  const _BackgroundPainter();

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = Fp.background);
    // Coordonnées des maquettes (écran de 390 × 844), mises à l'échelle.
    final sx = size.width / 390, sy = size.height / 844;
    final s = math.min(sx, 1.4);

    void halo(double left, double top, double d, double opacity) {
      final rect = Rect.fromLTWH(left * sx, top * sy, d * s, d * s);
      canvas.drawOval(
        rect,
        Paint()
          ..shader = RadialGradient(colors: [Fp.accentAlpha(0.35 * opacity), Fp.accentAlpha(0)])
              .createShader(rect),
      );
    }

    void ribbon(
      double left,
      double top,
      double height,
      double angle,
      double blur,
      double opacity,
      bool line,
    ) {
      canvas.save();
      final rect = Rect.fromLTWH(left * sx, top * sy, 900 * s, height);
      canvas.translate(rect.center.dx, rect.center.dy);
      canvas.rotate(angle * math.pi / 180);
      final r = Rect.fromCenter(center: Offset.zero, width: rect.width, height: rect.height);
      final colors = line
          ? [
              Colors.transparent,
              Fp.accentAlpha(0.25 * opacity),
              Colors.white.withValues(alpha: 0.18 * opacity),
              Colors.transparent,
            ]
          : [Colors.transparent, Fp.accentAlpha(0.55 * opacity), Colors.transparent];
      final paint = Paint()..shader = LinearGradient(colors: colors).createShader(r);
      if (blur > 0) paint.maskFilter = MaskFilter.blur(BlurStyle.normal, blur);
      canvas.drawRect(r, paint);
      canvas.restore();
    }

    halo(-180, -120, 560, 0.9);
    halo(390 - 520 + 260, 844 - 520 + 160, 520, 0.6);
    ribbon(-260, 150, 46, -24, 14, 0.7, false);
    ribbon(-240, 190, 3, -24, 0, 0.9, true);
    ribbon(-200, 640, 70, -18, 22, 0.55, false);
    ribbon(-220, 690, 2, -18, 0, 0.8, true);
  }

  @override
  bool shouldRepaint(_BackgroundPainter old) => false;
}

// --- Cartes en verre -----------------------------------------------------------

/// Contour : coins supérieur gauche et inférieur droit coupés.
Path cutCornerPath(Size s, double cut) {
  final c = math.min(cut, math.min(s.width, s.height) / 2);
  return Path()
    ..moveTo(c, 0)
    ..lineTo(s.width, 0)
    ..lineTo(s.width, s.height - c)
    ..lineTo(s.width - c, s.height)
    ..lineTo(0, s.height)
    ..lineTo(0, c)
    ..close();
}

class _CutClipper extends CustomClipper<Path> {
  const _CutClipper(this.cut);
  final double cut;
  @override
  Path getClip(Size size) => cutCornerPath(size, cut);
  @override
  bool shouldReclip(_CutClipper old) => old.cut != cut;
}

class _BorderPainter extends CustomPainter {
  _BorderPainter(this.cut, this.highlight);
  final double cut;
  final bool highlight;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    // Bordure de 1 px en dégradé (160°) : 28 % → 6 % → 16 % de blanc.
    canvas.drawPath(
      cutCornerPath(size, cut),
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1
        ..shader = LinearGradient(
          begin: const Alignment(-0.35, -1),
          end: const Alignment(0.35, 1),
          colors: highlight
              ? [Fp.accentLight, Fp.accentAlpha(0.3), Fp.accentLine]
              : const [Color(0x47FFFFFF), Color(0x0FFFFFFF), Color(0x29FFFFFF)],
          stops: const [0, 0.45, 1],
        ).createShader(rect),
    );
  }

  @override
  bool shouldRepaint(_BorderPainter old) => old.cut != cut || old.highlight != highlight;
}

/// Carte en verre : fond translucide, flou d'arrière-plan, bordure en dégradé.
/// La version principale ([GlassCard.main]) a des coins de 30 px et deux
/// triangles décoratifs décalés hors de la carte.
class GlassCard extends StatelessWidget {
  const GlassCard({
    super.key,
    required this.child,
    this.cut = 16,
    this.padding = const EdgeInsets.fromLTRB(16, 14, 16, 14),
    this.onTap,
    this.highlight = false,
    this.ornaments = false,
    this.margin = EdgeInsets.zero,
  });

  const GlassCard.main({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.fromLTRB(20, 24, 20, 24),
    this.onTap,
    this.highlight = false,
    this.margin = const EdgeInsets.symmetric(vertical: 6),
  }) : cut = 30,
       ornaments = true;

  const GlassCard.section({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.fromLTRB(16, 14, 16, 14),
    this.onTap,
    this.highlight = false,
    this.margin = EdgeInsets.zero,
  }) : cut = 18,
       ornaments = false;

  final Widget child;
  final double cut;
  final EdgeInsets padding;
  final EdgeInsets margin;
  final VoidCallback? onTap;
  final bool highlight;
  final bool ornaments;

  @override
  Widget build(BuildContext context) {
    Widget content = Padding(padding: padding, child: child);
    if (onTap != null) {
      content = InkWell(onTap: onTap, splashColor: Fp.accentAlpha(0.18), child: content);
    }
    Widget card = CustomPaint(
      foregroundPainter: _BorderPainter(cut, highlight),
      child: ClipPath(
        clipper: _CutClipper(cut),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
          // Material (et non un simple fond) : les ListTile et InkWell de la
          // carte y dessinent leurs effets de toucher.
          child: Material(
            color: highlight ? Color.alphaBlend(Fp.accentFaint, Fp.glass) : Fp.glass,
            child: content,
          ),
        ),
      ),
    );
    if (ornaments) {
      card = Stack(
        clipBehavior: Clip.none,
        children: [
          const Positioned(left: -10, top: -10, child: _Ornament(topLeft: true)),
          const Positioned(right: -10, bottom: -10, child: _Ornament(topLeft: false)),
          card,
        ],
      );
    }
    return Padding(padding: margin, child: card);
  }
}

class _Ornament extends StatelessWidget {
  const _Ornament({required this.topLeft});
  final bool topLeft;

  @override
  Widget build(BuildContext context) =>
      CustomPaint(size: const Size(46, 46), painter: _OrnamentPainter(topLeft));
}

class _OrnamentPainter extends CustomPainter {
  _OrnamentPainter(this.topLeft);
  final bool topLeft;

  @override
  void paint(Canvas canvas, Size s) {
    final path = topLeft
        ? (Path()
            ..moveTo(6, 0)
            ..lineTo(s.width, 0)
            ..lineTo(0, s.height)
            ..lineTo(0, 6)
            ..quadraticBezierTo(0, 0, 6, 0))
        : (Path()
            ..moveTo(s.width, 0)
            ..lineTo(s.width, s.height - 6)
            ..quadraticBezierTo(s.width, s.height, s.width - 6, s.height)
            ..lineTo(0, s.height)
            ..close());
    canvas.drawPath(path, Paint()..color = const Color(0x1AFFFFFF));
  }

  @override
  bool shouldRepaint(_OrnamentPainter old) => false;
}

// --- Petits éléments ---------------------------------------------------------------

/// Titre en deux tons : premier mot blanc, second dans l'accent clair.
class TwoToneTitle extends StatelessWidget {
  const TwoToneTitle(this.first, this.second, {super.key, this.size = 24, this.joined = false});
  final String first;
  final String second;
  final double size;

  /// Sans espace entre les deux parties (« Notifi|cations »).
  final bool joined;

  @override
  Widget build(BuildContext context) {
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(text: joined ? first : '$first ', style: Fp.title(size)),
          TextSpan(
            text: second,
            style: Fp.title(size, color: Fp.accentLight),
          ),
        ],
      ),
    );
  }
}

/// Carré arrondi à fond violet doux (logo, icône de notification…).
class IconSquare extends StatelessWidget {
  const IconSquare(this.icon, {super.key, this.size = 32, this.iconSize = 18, this.radius = 10});
  final IconData icon;
  final double size;
  final double iconSize;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: Fp.accentSoft,
        border: Border.all(color: Fp.accentLine),
        borderRadius: BorderRadius.circular(radius),
      ),
      child: Icon(icon, size: iconSize, color: Fp.accentLight),
    );
  }
}

/// Logo : ballon dans un carré violet et « FootProno ».
class FpLogo extends StatelessWidget {
  const FpLogo({super.key, this.size = 18});
  final double size;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconSquare(Icons.sports_soccer_rounded, size: size + 14, iconSize: size),
        const SizedBox(width: 10),
        Text.rich(
          TextSpan(
            children: [
              TextSpan(text: 'Foot', style: Fp.title(size)),
              TextSpan(
                text: 'Prono',
                style: Fp.title(size, color: Fp.accentLight),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// Bouton carré de 44 px (retour, notifications).
class SquareButton extends StatelessWidget {
  const SquareButton({super.key, required this.icon, required this.onTap, this.dot = false, this.tooltip});
  final IconData icon;
  final VoidCallback onTap;
  final bool dot;
  final String? tooltip;

  @override
  Widget build(BuildContext context) {
    final button = Material(
      color: Fp.fill6,
      shape: RoundedRectangleBorder(
        borderRadius: Fp.radius14,
        side: const BorderSide(color: Fp.line),
      ),
      child: InkWell(
        customBorder: RoundedRectangleBorder(borderRadius: Fp.radius14),
        onTap: onTap,
        child: SizedBox(
          width: 44,
          height: 44,
          child: Stack(
            alignment: Alignment.center,
            children: [
              Icon(icon, size: 20, color: Fp.text),
              if (dot)
                const Positioned(
                  top: 10,
                  right: 11,
                  child: CircleAvatar(radius: 4, backgroundColor: Fp.accent),
                ),
            ],
          ),
        ),
      ),
    );
    return tooltip == null ? button : Tooltip(message: tooltip, child: button);
  }
}

/// En-tête d'écran secondaire : bouton retour carré et titre en deux tons.
class BackHeader extends StatelessWidget {
  const BackHeader(this.first, this.second, {super.key, this.trailing, this.subtitle, this.joined = false});
  final String first;
  final String second;
  final bool joined;
  final Widget? trailing;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            SquareButton(
              icon: Icons.arrow_back_rounded,
              tooltip: 'Retour',
              onTap: () => Navigator.of(context).maybePop(),
            ),
            const SizedBox(width: 14),
            Expanded(child: TwoToneTitle(first, second, size: 24, joined: joined)),
            ?trailing,
          ],
        ),
        if (subtitle != null) ...[
          const SizedBox(height: 12),
          Text(subtitle!, style: Fp.body(14, color: Fp.text2, height: 1.4)),
        ],
      ],
    );
  }
}

/// Pastille arrondie (statut, championnat, Premium…).
class Tag extends StatelessWidget {
  const Tag(this.text, {super.key, this.color = Fp.accentLight, this.background, this.icon});
  final String text;
  final Color color;
  final Color? background;
  final IconData? icon;

  /// Gagné : fond vert, texte sombre.
  const Tag.win(this.text, {super.key}) : color = const Color(0xFF052E1C), background = Fp.win, icon = null;

  /// Perdu : fond rose, texte sombre.
  const Tag.loss(this.text, {super.key}) : color = const Color(0xFF3B0A24), background = Fp.loss, icon = null;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: background ?? color.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(99),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[Icon(icon, size: 12, color: color), const SizedBox(width: 4)],
          Text(
            text,
            style: Fp.body(11, color: color, weight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}

/// Pastille grise d'information (« +2,5 buts · 71 % »).
class InfoPill extends StatelessWidget {
  const InfoPill(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(color: Fp.fill6, borderRadius: BorderRadius.circular(99)),
      child: Text(text, style: Fp.body(12, color: Fp.textStrong)),
    );
  }
}

/// Puce de filtre (arrondie) : violette si choisie.
class FpChip extends StatelessWidget {
  const FpChip(this.label, {super.key, required this.selected, required this.onTap});
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(99),
      side: BorderSide(color: selected ? Fp.accentLine : Fp.line12),
    );
    return Material(
      color: selected ? Fp.accentSoft : Fp.fill,
      shape: shape,
      child: InkWell(
        customBorder: shape,
        onTap: onTap,
        child: Container(
          height: 36,
          padding: const EdgeInsets.symmetric(horizontal: 14),
          child: Center(
            widthFactor: 1,
            child: Text(
              label,
              style: Fp.body(13, weight: FontWeight.w600, color: selected ? Colors.white : Fp.textSoft),
            ),
          ),
        ),
      ),
    );
  }
}

/// Rangée de puces défilante.
class ChipRow extends StatelessWidget {
  const ChipRow({super.key, required this.labels, required this.selected, required this.onSelected});
  final List<String> labels;
  final int selected;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 36,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: labels.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (context, i) => FpChip(labels[i], selected: i == selected, onTap: () => onSelected(i)),
      ),
    );
  }
}

/// Onglets en segments (Probabilités / Cotes / Analyse…).
class SegmentTabs extends StatelessWidget {
  const SegmentTabs({super.key, required this.labels, required this.selected, required this.onSelected});
  final List<String> labels;
  final int selected;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: Fp.fill,
        borderRadius: Fp.radius14,
        border: Border.all(color: Fp.line10),
      ),
      child: Row(
        children: [
          for (var i = 0; i < labels.length; i++) ...[
            if (i > 0) const SizedBox(width: 6),
            Expanded(
              child: Material(
                color: i == selected ? Fp.accentSoft : Colors.transparent,
                borderRadius: BorderRadius.circular(10),
                child: InkWell(
                  borderRadius: BorderRadius.circular(10),
                  onTap: () => onSelected(i),
                  child: SizedBox(
                    height: 38,
                    child: Center(
                      child: Text(
                        labels[i],
                        style: Fp.body(
                          13,
                          weight: FontWeight.w600,
                          color: i == selected ? Colors.white : const Color(0xB8F4F2F8),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Tuile de chiffre (« En jeu · 12 000 F »).
class StatTile extends StatelessWidget {
  const StatTile(
    this.label,
    this.value, {
    super.key,
    this.valueColor,
    this.center = false,
    this.valueSize = 16,
  });
  final String label;
  final String value;
  final Color? valueColor;
  final bool center;
  final double valueSize;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(color: Fp.fill, borderRadius: BorderRadius.circular(12)),
      child: Column(
        crossAxisAlignment: center ? CrossAxisAlignment.center : CrossAxisAlignment.start,
        children: [
          Text(
            label,
            textAlign: center ? TextAlign.center : TextAlign.start,
            style: Fp.body(11, color: Fp.text2, weight: FontWeight.w600),
          ),
          const SizedBox(height: 2),
          Text(value, style: Fp.title(valueSize, color: valueColor ?? Fp.text)),
        ],
      ),
    );
  }
}

/// Cercle d'équipe avec son code (« PSG »).
class TeamCircle extends StatelessWidget {
  const TeamCircle(this.code, {super.key, this.size = 34});
  final String code;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: Fp.fill7,
        border: Border.all(color: const Color(0x29FFFFFF)),
      ),
      child: Text(
        code,
        style: Fp.title(size * 0.32, weight: FontWeight.w600, color: const Color(0xFFE9E6F2)),
      ),
    );
  }
}

/// Barre 1 / N / 2 en trois segments (domicile en violet).
class OutcomeBar extends StatelessWidget {
  const OutcomeBar(this.home, this.draw, this.away, {super.key, this.height = 8});
  final double home, draw, away;
  final double height;

  @override
  Widget build(BuildContext context) {
    int flex(double v) => math.max(1, (v * 1000).round());
    return ClipRRect(
      borderRadius: BorderRadius.circular(99),
      child: SizedBox(
        height: height,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              flex: flex(home),
              child: const DecoratedBox(decoration: BoxDecoration(gradient: Fp.accentBar)),
            ),
            const SizedBox(width: 3),
            Expanded(
              flex: flex(draw),
              child: const ColoredBox(color: Color(0x61FFFFFF)),
            ),
            const SizedBox(width: 3),
            Expanded(
              flex: flex(away),
              child: const ColoredBox(color: Color(0x29FFFFFF)),
            ),
          ],
        ),
      ),
    );
  }
}

/// Barre de probabilité (0 à 1).
class ProbBar extends StatelessWidget {
  const ProbBar(this.value, {super.key, this.height = 6, this.color});
  final double value;
  final double height;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(height),
      child: SizedBox(
        height: height,
        child: Stack(
          children: [
            const Positioned.fill(child: ColoredBox(color: Color(0x14FFFFFF))),
            FractionallySizedBox(
              alignment: Alignment.centerLeft,
              widthFactor: value.clamp(0.0, 1.0),
              heightFactor: 1,
              child: DecoratedBox(
                decoration: BoxDecoration(gradient: color != null ? null : Fp.accentBar, color: color),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Champ de saisie des maquettes : libellé au-dessus, icône à gauche.
class FpField extends StatelessWidget {
  const FpField({
    super.key,
    required this.label,
    required this.controller,
    this.icon,
    this.hint,
    this.keyboardType,
    this.obscure = false,
    this.suffix,
    this.onSubmitted,
    this.helper,
    this.textCapitalization = TextCapitalization.none,
    this.maxLength,
  });
  final String label;
  final TextEditingController controller;
  final IconData? icon;
  final String? hint;
  final TextInputType? keyboardType;
  final bool obscure;
  final Widget? suffix;
  final ValueChanged<String>? onSubmitted;
  final String? helper;
  final TextCapitalization textCapitalization;
  final int? maxLength;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: Fp.body(13, weight: FontWeight.w600, color: Fp.textStrong),
        ),
        const SizedBox(height: 7),
        // Libellé lu par les lecteurs d'écran (et les tests de bout en bout).
        Semantics(
          label: label,
          child: TextField(
            controller: controller,
            keyboardType: keyboardType,
            obscureText: obscure,
            onSubmitted: onSubmitted,
            textCapitalization: textCapitalization,
            maxLength: maxLength,
            style: Fp.body(15),
            decoration: InputDecoration(
              hintText: hint,
              helperText: helper,
              counterText: '',
              prefixIcon: icon == null ? null : Icon(icon, size: 20),
              suffixIcon: suffix,
            ),
          ),
        ),
      ],
    );
  }
}
