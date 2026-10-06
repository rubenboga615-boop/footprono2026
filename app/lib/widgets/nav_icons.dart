import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Icônes au trait de la barre du bas, redessinées d'après la maquette v2 (grille de 24,
/// trait de 1,8) : Matchs, Coupon, Montante, Bookmaker, Profil.
enum NavGlyph { matchs, coupon, montante, bookmaker, profil }

class NavIcon extends StatelessWidget {
  const NavIcon(this.glyph, {super.key, required this.color, this.size = 22});
  final NavGlyph glyph;
  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) =>
      CustomPaint(size: Size.square(size), painter: _NavIconPainter(glyph, color));
}

class _NavIconPainter extends CustomPainter {
  _NavIconPainter(this.glyph, this.color);
  final NavGlyph glyph;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.scale(size.width / 24);
    final pen = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.8
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    switch (glyph) {
      case NavGlyph.matchs:
        canvas.drawCircle(const Offset(12, 12), 9, pen);
        canvas.drawPath(
          Path()
            ..moveTo(12, 7)
            ..lineTo(16, 10)
            ..lineTo(14.5, 14.5)
            ..lineTo(9.5, 14.5)
            ..lineTo(8, 10)
            ..close(),
          pen,
        );
      case NavGlyph.coupon:
        final ticket = Path()
          ..moveTo(3, 7)
          ..lineTo(21, 7)
          ..lineTo(21, 10)
          ..arcToPoint(const Offset(21, 14), radius: const Radius.circular(2), clockwise: false)
          ..lineTo(21, 17)
          ..lineTo(3, 17)
          ..lineTo(3, 14)
          ..arcToPoint(const Offset(3, 10), radius: const Radius.circular(2), clockwise: false)
          ..close();
        canvas.drawPath(ticket, pen);
        for (var y = 7.0; y < 17; y += 4) {
          canvas.drawLine(Offset(14, y), Offset(14, math.min(y + 2, 17)), pen);
        }
      case NavGlyph.montante:
        canvas.drawPath(
          Path()
            ..moveTo(3, 20)
            ..lineTo(8, 20)
            ..lineTo(8, 15)
            ..lineTo(13, 15)
            ..lineTo(13, 10)
            ..lineTo(18, 10)
            ..lineTo(18, 5)
            ..lineTo(21, 5),
          pen,
        );
      case NavGlyph.bookmaker:
        canvas.drawPath(
          Path()
            ..moveTo(3, 7)
            ..lineTo(19, 7)
            ..arcToPoint(const Offset(21, 9), radius: const Radius.circular(2))
            ..lineTo(21, 18)
            ..arcToPoint(const Offset(19, 20), radius: const Radius.circular(2))
            ..lineTo(3, 20)
            ..close(),
          pen,
        );
        canvas.drawPath(
          Path()
            ..moveTo(3, 7)
            ..lineTo(15, 4)
            ..lineTo(15, 7),
          pen,
        );
        canvas.drawCircle(const Offset(16, 13.5), 1.4, pen);
      case NavGlyph.profil:
        canvas.drawCircle(const Offset(12, 8), 4, pen);
        canvas.drawPath(
          Path()
            ..moveTo(4, 21)
            ..cubicTo(5.5, 17, 8.5, 15, 12, 15)
            ..cubicTo(15.5, 15, 18.5, 17, 20, 21),
          pen,
        );
    }
  }

  @override
  bool shouldRepaint(_NavIconPainter old) => old.glyph != glyph || old.color != color;
}
