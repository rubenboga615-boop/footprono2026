import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../desktop/layout.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/maquette.dart';

/// Mouvement de la cote d'une sélection (maquette N10) : la cote actuelle, sa courbe depuis
/// le premier relevé, chaque changement avec son heure ; la chance du moteur à côté.
Future<void> showOddsHistory(BuildContext context, MatchInfo m, Offer o) => Navigator.of(context).push(
  MaterialPageRoute<void>(
    builder: (_) => OddsHistoryScreen(match: m, offer: o),
  ),
);

class OddsHistoryScreen extends StatelessWidget {
  const OddsHistoryScreen({super.key, required this.match, required this.offer});
  final MatchInfo match;
  final Offer offer;

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    final m = match, o = offer;
    final label = fullLabel(o.market, o.line, o.selection, home: m.home.name, away: m.away.name);
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          load: () async => await api.get('/matches/${m.id}/odds-history', {
            'market': o.market,
            'line': o.line,
            'selection': o.selection,
          }) as Json,
          builder: (context, data, _) {
            final points = (data['points'] as List).cast<Json>();
            final values = [for (final p in points) double.parse('${p['odds']}')];
            final times = [for (final p in points) DateTime.parse(p['at'] as String).toLocal()];
            final first = values.first, last = values.last;
            final down = last < first;
            final p = o.modelProbability;
            return ListView(
              padding: pagePadding(context, 16, 32, maxWidth: 640),
              children: [
                BackHeader('${m.home.name} –', m.away.name),
                MCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        'Historique de la cote ${data['bookmaker']}',
                        style: Fp.body(12.5, color: Fp.muted),
                      ),
                      Text(label, style: Fp.title(18)),
                      const SizedBox(height: 6),
                      Row(
                        children: [
                          Text(odds(last), style: Fp.title(30, weight: FontWeight.w800)),
                          const SizedBox(width: 10),
                          if (values.length > 1)
                            Tag(
                              '${down ? '▼' : '▲'} ${odds(first)} → ${odds(last)}',
                              color: down ? Fp.win : Fp.loss,
                              background: down ? const Color(0xFF12301F) : const Color(0xFF3A1620),
                            ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        values.length < 2
                            ? 'Cote inchangée depuis le premier relevé.'
                            : 'La cote est passée de ${odds(first)} à ${odds(last)} '
                                  '(${values.length - 1} changement${values.length > 2 ? 's' : ''}).',
                        style: Fp.body(13, color: Fp.muted),
                      ),
                      if (values.length > 1) ...[
                        const SizedBox(height: 14),
                        ExcludeSemantics(
                          child: SizedBox(
                            height: 130,
                            child: CustomPaint(painter: _OddsLine(values, odds(first), odds(last))),
                          ),
                        ),
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            Expanded(
                              child: Text(shortDate(times.first), style: Fp.body(12.5, color: Fp.muted)),
                            ),
                            Text(
                              '${shortDate(times.last)} ${hourMinute(times.last)}',
                              style: Fp.body(12.5, color: Fp.muted),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
                if (p != null)
                  MCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _kv('Chance selon le moteur', percent(p)),
                        _kv('Cote juste (sans marge)', decimal(1 / p)),
                        const SizedBox(height: 4),
                        Text(
                          '${down
                              ? 'La cote a baissé : le bookmaker paie moins ce résultat'
                              : last > first
                              ? 'La cote a monté : le bookmaker paie plus ce résultat'
                              : 'La cote n\'a pas bougé'}${last == first ? '.' : ' (argent des parieurs, nouvelles du match).'} '
                          'C\'est une information, pas un signal.',
                          style: Fp.body(13, color: Fp.muted, height: 1.4),
                        ),
                      ],
                    ),
                  ),
                if (values.length > 1)
                  MCard(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
                    child: Column(
                      children: [
                        for (var i = values.length - 1; i >= 0; i--) ...[
                          if (i < values.length - 1)
                            const Divider(height: 1, thickness: 1, color: Fp.divider),
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 10),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    '${shortDate(times[i])} ${hourMinute(times[i])}',
                                    style: Fp.body(13.5, color: Fp.muted),
                                  ),
                                ),
                                if (i > 0)
                                  Text(
                                    values[i] < values[i - 1] ? '▼ ' : '▲ ',
                                    style: Fp.body(12, color: Fp.muted),
                                  ),
                                Text(odds(values[i]), style: Fp.body(15, weight: FontWeight.w700)),
                              ],
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                const SizedBox(height: 12),
                Text(
                  'Relevé toutes les 3 heures ; seuls les changements sont enregistrés. Une cote bouge '
                  'avec l\'argent des parieurs et les nouvelles (blessures, compositions) : ce n\'est ni '
                  'un signal ni une garantie.',
                  style: Fp.body(12, color: Fp.muted, height: 1.4),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  static Widget _kv(String k, String v) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: Row(
      children: [
        Expanded(
          child: Text(k, style: Fp.body(13.5, color: Fp.muted)),
        ),
        Text(v, style: Fp.body(15, weight: FontWeight.w700)),
      ],
    ),
  );
}

/// Courbe de la cote, relevé après relevé (espacement régulier), trois lignes de repère,
/// première et dernière valeur écrites.
class _OddsLine extends CustomPainter {
  _OddsLine(this.values, this.firstLabel, this.lastLabel);
  final List<double> values;
  final String firstLabel;
  final String lastLabel;

  @override
  void paint(Canvas canvas, Size size) {
    final lo = values.reduce((a, b) => a < b ? a : b), hi = values.reduce((a, b) => a > b ? a : b);
    final span = hi - lo == 0 ? 1.0 : hi - lo;
    const top = 18.0, bottom = 18.0;
    final h = size.height - top - bottom;
    final grid = Paint()
      ..color = Fp.divider
      ..strokeWidth = 1;
    for (var i = 0; i < 3; i++) {
      final y = top + h * i / 2;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), grid);
    }
    Offset at(int i) => Offset(
      values.length == 1 ? 0 : size.width * i / (values.length - 1),
      top + h * (1 - (values[i] - lo) / span),
    );
    final path = Path()..moveTo(at(0).dx, at(0).dy);
    for (var i = 1; i < values.length; i++) {
      path.lineTo(at(i).dx, at(i).dy);
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = Fp.accent2
        ..strokeWidth = 2.5
        ..style = PaintingStyle.stroke
        ..strokeJoin = StrokeJoin.round,
    );
    void label(String text, Offset p, {bool right = false}) {
      final tp = TextPainter(
        text: TextSpan(
          text: text,
          style: Fp.body(11.5, color: Fp.muted),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      final above = p.dy - tp.height - 4 >= 0;
      final dy = above ? p.dy - tp.height - 4 : p.dy + 4;
      tp.paint(canvas, Offset(right ? size.width - tp.width : 2, dy.clamp(0, size.height - tp.height)));
    }

    label(firstLabel, at(0));
    label(lastLabel, at(values.length - 1), right: true);
  }

  @override
  bool shouldRepaint(_OddsLine old) => old.values != values;
}
