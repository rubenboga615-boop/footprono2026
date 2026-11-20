// Icônes au trait des maquettes « nouveau visage » (docs/maquettes/12-nouveau-visage), recopiées
// tracé par tracé depuis leur SVG (grille 24 × 24, trait 1,8, bouts et angles arrondis).
import 'dart:math' as math;

import 'package:flutter/material.dart';

enum VIcon {
  home,
  matchs,
  plus,
  ticket,
  user,
  back,
  check,
  star,
  bell,
  ball,
  bars,
  trophy,
  pause,
  stairs,
  send,
  search,
  target,
  shield,
  card,
  spark,
  sun,
  live,
  pen,
  flame,
  clock,
  gift,
  up,
  wallet,
}

sealed class _S {
  const _S({this.fill = false});
  final bool fill;
}

class _P extends _S {
  const _P(this.d, {this.dash});
  final String d;
  final List<double>? dash;
}

class _C extends _S {
  const _C(this.x, this.y, this.r, {super.fill});
  final double x, y, r;
}

class _R extends _S {
  const _R(this.x, this.y, this.w, this.h, this.rx, {super.fill});
  final double x, y, w, h, rx;
}

const Map<VIcon, List<_S>> _shapes = {
  VIcon.home: [_P('M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1z')],
  VIcon.matchs: [_R(3, 5, 18, 14, 2), _P('M12 5v14'), _C(12, 12, 2.6)],
  VIcon.plus: [_P('M12 5v14M5 12h14')],
  VIcon.ticket: [
    _P(
      'M4 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2.5a2.5 2.5 0 0 0 0 5V17a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2.5a2.5 2.5 0 0 0 0-5z',
    ),
    _P('M14 6v12', dash: [2, 2]),
  ],
  VIcon.user: [_C(12, 8, 3.6), _P('M5 20c1.2-3.6 4-5 7-5s5.8 1.4 7 5')],
  VIcon.back: [_P('M15 5l-7 7 7 7')],
  VIcon.check: [_P('M5 12.5l4.5 4.5L19 7.5')],
  VIcon.star: [_P('M12 4l2.4 5 5.4.6-4 3.7 1.1 5.4L12 16l-4.9 2.7 1.1-5.4-4-3.7 5.4-.6z')],
  VIcon.bell: [_P('M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z'), _P('M10 20.5a2.2 2.2 0 0 0 4 0')],
  VIcon.ball: [
    _C(12, 12, 8.5),
    _P('M12 8.5l3.2 2.3-1.2 3.7h-4l-1.2-3.7z'),
    _P('M12 3.5v5M15.2 10.8l4.5-1.5M14 14.5l2.8 3.8M10 14.5l-2.8 3.8M8.8 10.8 4.3 9.3'),
  ],
  VIcon.bars: [_P('M4 19h16'), _P('M7 16v-4M11 16V8M15 16v-6M19 16V5')],
  VIcon.trophy: [_P('M8 4h8v5a4 4 0 0 1-8 0zM8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 13v4M8.5 20h7')],
  VIcon.pause: [_C(12, 12, 9), _P('M10 9v6M14 9v6')],
  VIcon.stairs: [_P('M4 19h5v-5h5V9h6'), _P('M15 5h5v5')],
  VIcon.send: [_P('M4 12l16-7-6 15-2.5-6.5z')],
  VIcon.search: [_C(11, 11, 6.5), _P('M16 16l4 4')],
  VIcon.target: [_C(12, 12, 8), _C(12, 12, 4), _C(12, 12, 1, fill: true)],
  VIcon.shield: [_P('M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z')],
  VIcon.card: [_R(7, 4, 10, 15, 2, fill: true)],
  VIcon.spark: [
    _P('M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.5 2.5M15.2 15.2l2.5 2.5M6.3 17.7l2.5-2.5M15.2 8.8l2.5-2.5'),
  ],
  VIcon.sun: [
    _C(12, 12, 4),
    _P(
      'M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8',
    ),
  ],
  VIcon.live: [_C(12, 12, 3, fill: true), _P('M7 7a7 7 0 0 0 0 10M17 7a7 7 0 0 1 0 10')],
  VIcon.pen: [_P('M4 20h4L19 9l-4-4L4 16z'), _P('M13.5 6.5l4 4')],
  VIcon.flame: [
    _P('M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2.5 1.5-4 2.5-5 .3 1.6 1.2 2.6 2.5 3 0-3-1-5.5 0-8z'),
  ],
  VIcon.clock: [_C(12, 12, 8.5), _P('M12 7.5V12l3 2')],
  VIcon.gift: [
    _R(4, 9, 16, 11, 1.5),
    _P('M3 9h18M12 9v11M12 9c-1.5-3.5-5-3.5-5-1.2C7 9 12 9 12 9zM12 9c1.5-3.5 5-3.5 5-1.2C17 9 12 9 12 9z'),
  ],
  VIcon.up: [_P('M5 15l7-7 7 7')],
  VIcon.wallet: [_P('M4 7h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z'), _P('M4 7l11-3v3M16 13.5h2')],
};

/// Icône des maquettes : ``size`` comme l'attribut width du SVG, ``stroke`` comme stroke-width.
class VIc extends StatelessWidget {
  const VIc(this.icon, {super.key, this.size = 19, this.color, this.stroke = 1.8});
  final VIcon icon;
  final double size;
  final Color? color;
  final double stroke;

  @override
  Widget build(BuildContext context) => SizedBox.square(
    dimension: size,
    child: CustomPaint(
      painter: _IconPainter(
        _shapes[icon]!,
        color ?? IconTheme.of(context).color ?? DefaultTextStyle.of(context).style.color ?? Colors.white,
        stroke,
      ),
    ),
  );
}

class _IconPainter extends CustomPainter {
  _IconPainter(this.shapes, this.color, this.stroke);
  final List<_S> shapes;
  final Color color;
  final double stroke;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.scale(size.width / 24, size.height / 24);
    final line = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final fill = Paint()
      ..color = color
      ..style = PaintingStyle.fill;
    for (final s in shapes) {
      final path = switch (s) {
        _P(:final d) => svgPath(d),
        _C(:final x, :final y, :final r) => Path()..addOval(Rect.fromCircle(center: Offset(x, y), radius: r)),
        _R(:final x, :final y, :final w, :final h, :final rx) =>
          Path()..addRRect(RRect.fromRectAndRadius(Rect.fromLTWH(x, y, w, h), Radius.circular(rx))),
      };
      if (s.fill) {
        canvas.drawPath(path, fill);
      } else if (s is _P && s.dash != null) {
        canvas.drawPath(_dashed(path, s.dash!), line);
      } else {
        canvas.drawPath(path, line);
      }
    }
  }

  static Path _dashed(Path src, List<double> dash) {
    final out = Path();
    for (final m in src.computeMetrics()) {
      var d = 0.0;
      var i = 0;
      while (d < m.length) {
        final len = dash[i % dash.length];
        if (i.isEven) out.addPath(m.extractPath(d, math.min(d + len, m.length)), Offset.zero);
        d += len;
        i++;
      }
    }
    return out;
  }

  @override
  bool shouldRepaint(_IconPainter old) => old.shapes != shapes || old.color != color || old.stroke != stroke;
}

/// Tracé SVG (attribut d) : M L H V C S Q A Z, majuscules et minuscules.
Path svgPath(String d) {
  final tokens = RegExp(r'[MmLlHhVvCcSsQqAaZz]|-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?')
      .allMatches(d)
      .map((m) => m[0]!);
  final it = tokens.toList();
  final path = Path();
  var i = 0;
  var cmd = 'M';
  var x = 0.0, y = 0.0, sx = 0.0, sy = 0.0;
  double? cx2, cy2; // dernier point de contrôle (pour S)
  bool isCmd(String t) => RegExp(r'^[A-Za-z]$').hasMatch(t);
  double n() => double.parse(it[i++]);
  while (i < it.length) {
    if (isCmd(it[i])) cmd = it[i++];
    final rel = cmd == cmd.toLowerCase();
    final ox = rel ? x : 0.0, oy = rel ? y : 0.0;
    switch (cmd.toUpperCase()) {
      case 'M':
        x = ox + n();
        y = oy + n();
        path.moveTo(x, y);
        sx = x;
        sy = y;
        cmd = rel ? 'l' : 'L'; // les paires suivantes sont des L
        cx2 = null;
      case 'L':
        x = ox + n();
        y = oy + n();
        path.lineTo(x, y);
        cx2 = null;
      case 'H':
        x = ox + n();
        path.lineTo(x, y);
        cx2 = null;
      case 'V':
        y = oy + n();
        path.lineTo(x, y);
        cx2 = null;
      case 'C':
        final x1 = ox + n(), y1 = oy + n(), x2 = ox + n(), y2 = oy + n();
        x = ox + n();
        y = oy + n();
        path.cubicTo(x1, y1, x2, y2, x, y);
        cx2 = x2;
        cy2 = y2;
      case 'S':
        final x1 = cx2 == null ? x : 2 * x - cx2;
        final y1 = cy2 == null || cx2 == null ? y : 2 * y - cy2;
        final x2 = ox + n(), y2 = oy + n();
        x = ox + n();
        y = oy + n();
        path.cubicTo(x1, y1, x2, y2, x, y);
        cx2 = x2;
        cy2 = y2;
      case 'Q':
        final x1 = ox + n(), y1 = oy + n();
        x = ox + n();
        y = oy + n();
        path.quadraticBezierTo(x1, y1, x, y);
        cx2 = null;
      case 'A':
        final rx = n(), ry = n(), rot = n();
        final large = n() != 0, sweep = n() != 0;
        x = ox + n();
        y = oy + n();
        path.arcToPoint(
          Offset(x, y),
          radius: Radius.elliptical(rx, ry),
          rotation: rot,
          largeArc: large,
          clockwise: sweep,
        );
        cx2 = null;
      case 'Z':
        path.close();
        x = sx;
        y = sy;
        cx2 = null;
    }
  }
  return path;
}
