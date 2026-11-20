// Composants des maquettes « nouveau visage » du testeur (docs/maquettes/12-nouveau-visage),
// recopiés classe CSS par classe CSS : mêmes couleurs, tailles, coins et marges.
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme.dart';
import 'visage_icons.dart';

export 'visage_icons.dart';

/// Variables CSS de la maquette (:root).
abstract final class V {
  static const bg = Color(0xFF0B0F1A);
  static const s1 = Color(0xFF131A2A);
  static const s2 = Color(0xFF1B2438);
  static const s3 = Color(0xFF24304A);
  static const line = Color(0xFF26314A);
  static const tx = Color(0xFFF3F5FA);
  static const mu = Color(0xFF9AA4BD);
  static const mu2 = Color(0xFF6E7891);
  static const vi = Color(0xFF7C5CFF);
  static const vi2 = Color(0xFFA48BFF);
  static const vi3 = Color(0xFF2A2163);
  static const mint = Color(0xFF34E0A1);
  static const mintbg = Color(0xFF0F3328);
  static const coral = Color(0xFFFF6B7A);
  static const coralbg = Color(0xFF3A1720);
  static const amber = Color(0xFFFFC56B);
  static const amberbg = Color(0xFF33270F);
  static const sky = Color(0xFF5AB8FF);
  static const cardBorder = Color(0xFF1A2236);
  static const iconBorder = Color(0xFF1F2840);
  static const navBorder = Color(0xFF222C44);

  /// Texte de base : Inter 13,5, interligne 1,35.
  static TextStyle t(double size, {FontWeight w = FontWeight.w400, Color color = tx, double? ls}) =>
      TextStyle(
        fontFamily: Fp.bodyFont,
        fontSize: size,
        fontWeight: w,
        color: color,
        height: 1.35,
        letterSpacing: ls,
        fontFeatures: const [FontFeature.tabularFigures()],
      );

  /// ``b`` : gras.
  static TextStyle b([double size = 13.5, Color color = tx]) => t(size, w: FontWeight.w700, color: color);

  /// ``.mu`` : 11,5 gris.
  static TextStyle mu_([double size = 11.5]) => t(size, color: mu);

  /// ``.big`` : 30, 800, espacement −0,6.
  static TextStyle big([Color color = tx]) => t(30, w: FontWeight.w800, color: color, ls: -0.6);
}

/// ``.c`` : carte s1, coins 20, marge 14, liseré #1A2236, 12 au-dessus.
class VCard extends StatelessWidget {
  const VCard({super.key, required this.child, this.gradient, this.top = 12, this.onTap, this.border});
  final Widget child;
  final Gradient? gradient;
  final double top;
  final VoidCallback? onTap;
  final Color? border;

  @override
  Widget build(BuildContext context) {
    final box = Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: gradient == null ? V.s1 : null,
        gradient: gradient,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: border ?? V.cardBorder),
      ),
      child: child,
    );
    return Padding(
      padding: EdgeInsets.only(top: top),
      child: onTap == null
          ? box
          : Material(
              color: Colors.transparent,
              child: InkWell(borderRadius: BorderRadius.circular(20), onTap: onTap, child: box),
            ),
    );
  }
}

/// ``.c2`` : case s2, coins 16, marge 11 × 12.
class VCard2 extends StatelessWidget {
  const VCard2({super.key, required this.child, this.border, this.onTap, this.width});
  final Widget child;
  final Color? border;
  final VoidCallback? onTap;
  final double? width;

  @override
  Widget build(BuildContext context) {
    final box = Container(
      width: width,
      padding: const EdgeInsets.fromLTRB(12, 11, 12, 11),
      decoration: BoxDecoration(
        color: V.s2,
        borderRadius: BorderRadius.circular(16),
        border: border == null ? null : Border.all(color: border!),
      ),
      child: child,
    );
    if (onTap == null) return box;
    return Material(
      color: Colors.transparent,
      child: InkWell(borderRadius: BorderRadius.circular(16), onTap: onTap, child: box),
    );
  }
}

/// ``.k`` : petit titre en majuscules, 10,5 gras, espacement 0,8, gris mu2.
class VKicker extends StatelessWidget {
  const VKicker(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) => Text(
    text.toUpperCase(),
    style: V.t(10.5, w: FontWeight.w700, color: V.mu2, ls: 0.8),
  );
}

/// Rangée « titre .k + lien violet » (``.row`` avec ``.k.sp`` et ``.lnk``).
class VHead extends StatelessWidget {
  const VHead(this.title, {super.key, this.link, this.onLink, this.trailing});
  final String title;
  final String? link;
  final VoidCallback? onLink;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Expanded(child: VKicker(title)),
      ?trailing,
      if (link != null) VLink(link!, onTap: onLink),
    ],
  );
}

/// ``.lnk`` : lien violet clair, 600.
class VLink extends StatelessWidget {
  const VLink(this.text, {super.key, this.onTap});
  final String text;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => GestureDetector(
    behavior: HitTestBehavior.opaque,
    onTap: onTap,
    child: Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Text(
        text,
        style: V.t(13.5, w: FontWeight.w600, color: V.vi2),
      ),
    ),
  );
}

enum VChipKind { up, dn, eq, am, vi }

/// ``.chip`` : pilule 11 gras, marge 4 × 9 ; up menthe, dn corail, eq gris, am ambre, vi violet.
class VChip extends StatelessWidget {
  const VChip(this.text, {super.key, this.kind = VChipKind.eq, this.arrow});
  final String text;
  final VChipKind kind;

  /// Flèche pleine devant le texte (▲ ▼) ; ``null`` : rien ; ``VIcon.up`` : chevron au trait.
  final Widget? arrow;

  static (Color, Color) colors(VChipKind k) => switch (k) {
    VChipKind.up => (V.mintbg, V.mint),
    VChipKind.dn => (V.coralbg, V.coral),
    VChipKind.eq => (V.s3, V.mu),
    VChipKind.am => (V.amberbg, V.amber),
    VChipKind.vi => (V.vi3, V.vi2),
  };

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = colors(kind);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (arrow != null) ...[
            IconTheme(
              data: IconThemeData(color: fg),
              child: arrow!,
            ),
            const SizedBox(width: 4),
          ],
          Text(
            text,
            style: V.t(11, w: FontWeight.w700, color: fg).copyWith(height: 1.2),
          ),
        ],
      ),
    );
  }
}

/// Triangle plein ▲ ▼ des pastilles (la police n'a pas ces caractères).
class VTriangle extends StatelessWidget {
  const VTriangle({super.key, this.up = true, this.size = 8});
  final bool up;
  final double size;

  @override
  Widget build(BuildContext context) => CustomPaint(
    size: Size(size, size * 0.8),
    painter: _TrianglePainter(up, IconTheme.of(context).color ?? V.tx),
  );
}

class _TrianglePainter extends CustomPainter {
  _TrianglePainter(this.up, this.color);
  final bool up;
  final Color color;

  @override
  void paint(Canvas canvas, Size s) {
    final p = up
        ? (Path()
            ..moveTo(s.width / 2, 0)
            ..lineTo(s.width, s.height)
            ..lineTo(0, s.height))
        : (Path()
            ..moveTo(0, 0)
            ..lineTo(s.width, 0)
            ..lineTo(s.width / 2, s.height));
    canvas.drawPath(p..close(), Paint()..color = color);
  }

  @override
  bool shouldRepaint(_TrianglePainter o) => o.up != up || o.color != color;
}

/// Signe « ≈ » dessiné.
class VApprox extends StatelessWidget {
  const VApprox({super.key, this.size = 9});
  final double size;

  @override
  Widget build(BuildContext context) => CustomPaint(
    size: Size(size, size * 0.75),
    painter: _ApproxPainter(IconTheme.of(context).color ?? V.tx),
  );
}

class _ApproxPainter extends CustomPainter {
  _ApproxPainter(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size s) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5
      ..strokeCap = StrokeCap.round;
    for (final y in [s.height * 0.3, s.height * 0.75]) {
      final p = Path()
        ..moveTo(0, y)
        ..quadraticBezierTo(s.width * 0.25, y - 2.4, s.width * 0.5, y)
        ..quadraticBezierTo(s.width * 0.75, y + 2.4, s.width, y);
      canvas.drawPath(p, paint);
    }
  }

  @override
  bool shouldRepaint(_ApproxPainter o) => o.color != color;
}

/// Pastille « moteur contre cote » de la maquette : « ▲ +9 pts », « ▼ −3 pts », « ≈ cote ».
class VGapChip extends StatelessWidget {
  const VGapChip({super.key, required this.engine, required this.implied, this.nation = false});
  final double engine;
  final double implied;
  final bool nation;

  @override
  Widget build(BuildContext context) {
    final pts = ((engine - implied) * 100).round();
    if (pts.abs() < 3) return const VChip('cote', kind: VChipKind.eq, arrow: VApprox());
    final up = pts > 0;
    return VChip(
      '${up ? '+' : '−'}${pts.abs()} pts',
      kind: nation ? VChipKind.am : (up ? VChipKind.up : VChipKind.dn),
      arrow: VTriangle(up: up),
    );
  }
}

/// ``.seg`` : sélecteur, fond s1 coins 14, cases de 34 coins 11, case choisie s3.
class VSeg extends StatelessWidget {
  const VSeg({
    super.key,
    required this.items,
    required this.selected,
    required this.onSelect,
    this.bg = V.s1,
  });
  final List<String> items;
  final int selected;
  final ValueChanged<int> onSelect;
  final Color bg;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(3),
    decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(14)),
    child: Row(
      children: [
        for (final (i, s) in items.indexed)
          Expanded(
            child: Semantics(
              button: true,
              selected: i == selected,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => onSelect(i),
                child: Container(
                  height: 34,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: i == selected ? V.s3 : null,
                    borderRadius: BorderRadius.circular(11),
                  ),
                  child: Text(
                    s,
                    style: V.t(12.5, w: FontWeight.w600, color: i == selected ? Colors.white : V.mu),
                  ),
                ),
              ),
            ),
          ),
      ],
    ),
  );
}

/// ``.odd`` : case de cote 52 × 44, coins 12, 800 14.
class VOdd extends StatelessWidget {
  const VOdd(this.text, {super.key, this.label, this.on = false, this.onTap});
  final String text;
  final String? label;
  final bool on;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: onTap,
    child: Container(
      constraints: const BoxConstraints(minWidth: 52),
      height: 44,
      padding: const EdgeInsets.symmetric(horizontal: 6),
      decoration: BoxDecoration(color: on ? V.vi : V.s2, borderRadius: BorderRadius.circular(12)),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            text,
            style: V.t(14, w: FontWeight.w800, color: on ? Colors.white : V.tx),
          ),
          if (label != null)
            Text(
              label!,
              style: V.t(9.5, w: FontWeight.w600, color: on ? const Color(0xFFE4DCFF) : V.mu),
            ),
        ],
      ),
    ),
  );
}

/// ``.ring`` : anneau conique violet (``value`` de 0 à 1), pourcentage au centre.
class VRing extends StatelessWidget {
  const VRing(
    this.value, {
    super.key,
    this.size = 64,
    this.inner = 50,
    this.fontSize = 14,
    this.color = V.vi,
  });
  final double value;
  final double size;
  final double inner;
  final double fontSize;
  final Color color;

  @override
  Widget build(BuildContext context) => SizedBox.square(
    dimension: size,
    child: CustomPaint(
      painter: _RingPainter(value.clamp(0, 1), color, (size - inner) / 2),
      child: Center(child: Text('${(value * 100).round()}\u00A0%', style: V.b(fontSize))),
    ),
  );
}

class _RingPainter extends CustomPainter {
  _RingPainter(this.v, this.color, this.width);
  final double v;
  final Color color;
  final double width;

  @override
  void paint(Canvas canvas, Size s) {
    final r = s.width / 2;
    final c = Offset(r, r);
    canvas.drawCircle(c, r, Paint()..color = V.s3);
    canvas.drawArc(
      Rect.fromCircle(center: c, radius: r),
      -math.pi / 2,
      2 * math.pi * v,
      true,
      Paint()..color = color,
    );
    canvas.drawCircle(c, r - width, Paint()..color = V.s1);
  }

  @override
  bool shouldRepaint(_RingPainter o) => o.v != v || o.color != color;
}

/// ``.li`` : ligne de liste (marge 11 en haut et en bas, filet entre les lignes).
class VList extends StatelessWidget {
  const VList({super.key, required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      for (final (i, c) in children.indexed)
        Container(
          padding: const EdgeInsets.symmetric(vertical: 11),
          decoration: i == children.length - 1
              ? null
              : const BoxDecoration(
                  border: Border(bottom: BorderSide(color: V.line)),
                ),
          child: c,
        ),
    ],
  );
}

enum VDotKind { plain, green, red }

/// ``.tl`` : frise (trait à gauche, pastilles rondes).
class VTimeline extends StatelessWidget {
  const VTimeline({super.key, required this.items});
  final List<(String, VDotKind)> items;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(left: 6),
    child: Container(
      padding: const EdgeInsets.only(left: 12),
      decoration: const BoxDecoration(
        border: Border(left: BorderSide(color: V.line, width: 2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final (text, kind) in items)
            Stack(
              clipBehavior: Clip.none,
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Text(text, style: V.t(12.5)),
                ),
                Positioned(
                  left: -20,
                  top: 9,
                  child: Container(
                    width: 14,
                    height: 14,
                    decoration: BoxDecoration(
                      color: switch (kind) {
                        VDotKind.green => V.mint,
                        VDotKind.red => V.coral,
                        VDotKind.plain => V.s3,
                      },
                      shape: BoxShape.circle,
                      border: Border.all(color: V.bg, width: 2),
                    ),
                  ),
                ),
              ],
            ),
        ],
      ),
    ),
  );
}

/// ``.gauge`` : barre (réalisé) et repère ambre (annoncé).
class VGauge extends StatelessWidget {
  const VGauge({super.key, required this.value, this.mark, this.color = V.vi, this.height = 8});
  final double value;
  final double? mark;
  final Color color;
  final double height;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, c) => SizedBox(
      height: height,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Container(
            decoration: BoxDecoration(color: V.s3, borderRadius: BorderRadius.circular(height / 2)),
          ),
          Container(
            width: c.maxWidth * value.clamp(0, 1),
            decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(height / 2)),
          ),
          if (mark != null)
            Positioned(
              left: c.maxWidth * mark!.clamp(0, 1) - 1.5,
              top: -4,
              child: Container(
                width: 3,
                height: height + 8,
                decoration: BoxDecoration(color: V.amber, borderRadius: BorderRadius.circular(2)),
              ),
            ),
        ],
      ),
    ),
  );
}

/// ``.iconbtn`` : bouton carré 40, coins 13, fond s1, pastille corail.
class VIconBtn extends StatelessWidget {
  const VIconBtn(this.icon, {super.key, required this.onTap, this.badge = 0, this.tooltip});
  final VIcon icon;
  final VoidCallback onTap;
  final int badge;
  final String? tooltip;

  @override
  Widget build(BuildContext context) => Tooltip(
    message: tooltip ?? '',
    excludeFromSemantics: true,
    child: Semantics(
      button: true,
      label: tooltip,
      child: GestureDetector(
        onTap: onTap,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: V.s1,
                borderRadius: BorderRadius.circular(13),
                border: Border.all(color: V.iconBorder),
              ),
              child: Center(child: VIc(icon, color: const Color(0xFFDCE1EE))),
            ),
            if (badge > 0)
              Positioned(
                top: -4,
                right: -4,
                child: Container(
                  constraints: const BoxConstraints(minWidth: 18),
                  height: 18,
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  decoration: BoxDecoration(
                    color: V.coral,
                    borderRadius: BorderRadius.circular(9),
                    border: Border.all(color: V.bg, width: 2),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    badge > 99 ? '99+' : '$badge',
                    style: V.t(10.5, w: FontWeight.w800, color: Colors.white).copyWith(height: 1),
                  ),
                ),
              ),
          ],
        ),
      ),
    ),
  );
}

/// ``.logo`` : carré 30 en dégradé violet, disque blanc aux trois quarts.
class VLogo extends StatelessWidget {
  const VLogo({super.key, this.size = 30});
  final double size;

  @override
  Widget build(BuildContext context) => Container(
    width: size,
    height: size,
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(size * 0.3),
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xFF8B6BFF), Color(0xFF5A36E6)],
      ),
    ),
    child: Center(
      child: CustomPaint(size: Size.square(size * 2 / 3), painter: _LogoPainter()),
    ),
  );
}

class _LogoPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size s) {
    final rect = Offset.zero & s;
    canvas.drawCircle(rect.center, s.width / 2, Paint()..color = Colors.white.withValues(alpha: 0.4));
    canvas.drawArc(rect, -math.pi / 2, math.pi * 1.5, true, Paint()..color = Colors.white);
  }

  @override
  bool shouldRepaint(_LogoPainter o) => false;
}

/// ``.btn2`` : bouton secondaire 44, coins 14, liseré.
class VBtn2 extends StatelessWidget {
  const VBtn2(this.text, {super.key, this.icon, required this.onTap});
  final String text;
  final VIcon? icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 8),
    child: Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: Container(
          height: 44,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: V.line),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (icon != null) ...[VIc(icon!, size: 16, color: Colors.white), const SizedBox(width: 8)],
              Text(
                text,
                style: V.t(13.5, w: FontWeight.w600, color: Colors.white),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

/// ``.dot`` : point vert du direct avec son halo.
class VDot extends StatelessWidget {
  const VDot({super.key, this.color = V.mint});
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
    width: 7,
    height: 7,
    decoration: BoxDecoration(
      color: color,
      shape: BoxShape.circle,
      boxShadow: [BoxShadow(color: color.withValues(alpha: 0.18), spreadRadius: 3)],
    ),
  );
}

/// ``.sw`` : interrupteur 42 × 26, violet allumé, s3 éteint.
class VSwitch extends StatelessWidget {
  const VSwitch({super.key, required this.value, required this.onChanged, this.label});
  final bool value;
  final ValueChanged<bool>? onChanged;
  final String? label;

  @override
  Widget build(BuildContext context) => Semantics(
    toggled: value,
    label: label,
    child: GestureDetector(
      onTap: onChanged == null ? null : () => onChanged!(!value),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        width: 42,
        height: 26,
        padding: const EdgeInsets.all(3),
        alignment: value ? Alignment.centerRight : Alignment.centerLeft,
        decoration: BoxDecoration(color: value ? V.vi : V.s3, borderRadius: BorderRadius.circular(13)),
        child: Container(
          width: 20,
          height: 20,
          decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
        ),
      ),
    ),
  );
}

/// ``.btn`` : bouton principal violet 50, coins 16 (``green`` : ``.btn.g``).
class VBtn extends StatelessWidget {
  const VBtn(
    this.text, {
    super.key,
    required this.onTap,
    this.height = 50,
    this.green = false,
    this.top = 12,
  });
  final String text;
  final VoidCallback? onTap;
  final double height;
  final bool green;
  final double top;

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.only(top: top),
    child: Material(
      color: onTap == null ? V.s3 : (green ? V.mint : V.vi),
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: SizedBox(
          height: height,
          child: Center(
            child: Text(
              text,
              style: V.t(15, w: FontWeight.w700, color: green ? const Color(0xFF062117) : Colors.white),
            ),
          ),
        ),
      ),
    ),
  );
}

/// ``.info`` : encadré bleu nuit, texte 12.
class VInfo extends StatelessWidget {
  const VInfo(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    margin: const EdgeInsets.only(top: 10),
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
    decoration: BoxDecoration(
      color: const Color(0xFF121A30),
      border: Border.all(color: const Color(0xFF23305A)),
      borderRadius: BorderRadius.circular(14),
    ),
    child: Text(text, style: V.t(12, color: const Color(0xFFC9D3F5)).copyWith(height: 1.45)),
  );
}

/// En-tête d'un écran ouvert par-dessus : flèche retour violette, titre centré, action à droite.
class VTopBar extends StatelessWidget {
  const VTopBar(this.title, {super.key, this.action, this.onAction, this.actionLabel});
  final String title;
  final VIcon? action;
  final VoidCallback? onAction;
  final String? actionLabel;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: 44,
    child: Row(
      children: [
        SizedBox(
          width: 40,
          child: Semantics(
            button: true,
            label: 'Retour',
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => Navigator.of(context).maybePop(),
              child: const Align(
                alignment: Alignment.centerLeft,
                child: VIc(VIcon.back, size: 22, color: V.vi2),
              ),
            ),
          ),
        ),
        Expanded(
          child: Text(title, textAlign: TextAlign.center, style: V.b(15.5)),
        ),
        SizedBox(
          width: 40,
          child: action == null
              ? null
              : Semantics(
                  button: true,
                  label: actionLabel,
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: onAction,
                    child: Align(
                      alignment: Alignment.centerRight,
                      child: VIc(action!, size: 22, color: V.vi2),
                    ),
                  ),
                ),
        ),
      ],
    ),
  );
}

/// Page ouverte par-dessus, au fond de la maquette (#0B0F1A), marges 16.
class VPage extends StatelessWidget {
  const VPage({super.key, required this.children, this.onRefresh});
  final List<Widget> children;
  final Future<void> Function()? onRefresh;

  @override
  Widget build(BuildContext context) {
    final list = ListView(padding: const EdgeInsets.fromLTRB(16, 6, 16, 40), children: children);
    return Scaffold(
      backgroundColor: V.bg,
      body: SafeArea(
        child: DefaultTextStyle(
          style: V.t(13.5),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 640),
              child: onRefresh == null ? list : RefreshIndicator(onRefresh: onRefresh!, child: list),
            ),
          ),
        ),
      ),
    );
  }
}

/// ``.tabs`` : pastilles qui défilent (s1, liseré, 12 600) ; choisie : claire sur fond sombre.
class VTabs extends StatelessWidget {
  const VTabs({super.key, required this.items, required this.selected, required this.onSelect, this.icons});
  final List<String> items;
  final int selected;
  final ValueChanged<int> onSelect;

  /// Icône devant certaines pastilles (« ☆ Suivis »).
  final Map<int, VIcon>? icons;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    child: Row(
      children: [
        for (final (i, s) in items.indexed) ...[
          if (i > 0) const SizedBox(width: 6),
          Semantics(
            button: true,
            selected: i == selected,
            child: GestureDetector(
              onTap: () => onSelect(i),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                decoration: BoxDecoration(
                  color: i == selected ? V.tx : V.s1,
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(color: i == selected ? V.tx : V.cardBorder),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (icons?[i] case final ic?) ...[
                      VIc(ic, size: 13, color: i == selected ? V.bg : V.mu),
                      const SizedBox(width: 4),
                    ],
                    Text(
                      s,
                      style: V
                          .t(12, w: FontWeight.w600, color: i == selected ? V.bg : V.mu)
                          .copyWith(height: 1.2),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ],
    ),
  );
}

/// ``.team`` : rond 26 avec le code de l'équipe.
class VTeamBadge extends StatelessWidget {
  const VTeamBadge(this.code, {super.key, this.size = 26});
  final String code;
  final double size;

  @override
  Widget build(BuildContext context) => Container(
    width: size,
    height: size,
    alignment: Alignment.center,
    decoration: const BoxDecoration(color: V.s3, shape: BoxShape.circle),
    child: Text(
      code,
      style: V.t(size * 10 / 26, w: FontWeight.w800, color: const Color(0xFFCFD5E6)).copyWith(height: 1),
    ),
  );
}

/// ``.bar3`` : barre des chances 1-N-2 (violet, gris, bleu), 8 de haut, 2 entre les parts.
class VBar3 extends StatelessWidget {
  const VBar3(this.home, this.draw, this.away, {super.key});
  final double home, draw, away;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 8),
    child: ClipRRect(
      borderRadius: BorderRadius.circular(4),
      child: SizedBox(
        height: 8,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (final (i, (p, c)) in [(home, V.vi), (draw, V.s3), (away, V.sky)].indexed) ...[
              if (i > 0) const SizedBox(width: 2),
              Expanded(
                flex: math.max(1, (p * 1000).round()),
                child: ColoredBox(color: c),
              ),
            ],
          ],
        ),
      ),
    ),
  );
}
