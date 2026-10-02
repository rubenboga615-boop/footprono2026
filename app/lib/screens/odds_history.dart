import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Mouvement de la cote d'une sélection : chaque changement relevé, avec son heure.
Future<void> showOddsHistory(BuildContext context, MatchInfo m, Offer o) {
  final api = context.read<AppState>().api;
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Fp.background,
    builder: (context) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 24),
        child: Loader<Json>(
          load: () async => await api.get('/matches/${m.id}/odds-history', {
            'market': o.market,
            'line': o.line,
            'selection': o.selection,
          }) as Json,
          builder: (context, data, _) {
            final points = (data['points'] as List).cast<Json>();
            final first = double.parse('${points.first['odds']}');
            final last = double.parse('${points.last['odds']}');
            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  '${selectionLabel(o.market, o.line, o.selection, home: m.home.name, away: m.away.name)} '
                  '· ${data['bookmaker']}',
                  style: Fp.title(17),
                ),
                const SizedBox(height: 4),
                Text(
                  points.length < 2
                      ? 'Cote inchangée depuis le premier relevé.'
                      : 'La cote est passée de ${odds(first)} à ${odds(last)} '
                            '(${points.length - 1} changement${points.length > 2 ? 's' : ''}).',
                  style: Fp.body(14, color: Fp.textSoft),
                ),
                const SizedBox(height: 12),
                Flexible(
                  child: ListView(
                    shrinkWrap: true,
                    children: [
                      for (final (i, p) in points.indexed)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 6),
                          child: Row(
                            children: [
                              Expanded(
                                child: Text(
                                  dateTime(DateTime.parse(p['at'] as String).toLocal()),
                                  style: Fp.body(14, color: Fp.text2),
                                ),
                              ),
                              if (i > 0)
                                Text(
                                  double.parse('${p['odds']}') < double.parse('${points[i - 1]['odds']}')
                                      ? '▼ '
                                      : '▲ ',
                                  style: Fp.body(13, color: Fp.text3),
                                ),
                              Text(odds(p['odds']), style: Fp.title(16)),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  'Relevé toutes les 3 heures ; seuls les changements sont enregistrés. Une cote bouge '
                  'avec l\'argent des parieurs et les nouvelles (blessures, compositions) : ce n\'est ni '
                  'un signal ni une garantie.',
                  style: Fp.body(12, color: Fp.text3, height: 1.4),
                ),
              ],
            );
          },
        ),
      ),
    ),
  );
}
