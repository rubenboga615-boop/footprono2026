import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'team_screen.dart';

/// Classement réel à côté du classement « mérité » (xPts d'Understat : les points qu'une
/// équipe obtiendrait en moyenne avec la qualité de ses occasions et de celles concédées).
class MeritedScreen extends StatefulWidget {
  const MeritedScreen({super.key, this.competition, this.season});
  final String? competition;
  final int? season;

  @override
  State<MeritedScreen> createState() => _MeritedScreenState();
}

class _MeritedScreenState extends State<MeritedScreen> {
  late String? competition = widget.competition;
  late int? season = widget.season;

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<List<Json>>(
          // Classement mérité : xG nécessaires (5 grands championnats seulement).
          load: () async => [
            for (final c in (await api.get('/competitions') as List).cast<Json>())
              if (c['understat_slug'] != null) c,
          ],
          builder: (context, comps, _) {
            if (comps.isEmpty) return const EmptyState('Aucun championnat.');
            final comp = comps.firstWhere((c) => c['code'] == competition, orElse: () => comps.first);
            final seasons = [
              for (final s in (comp['seasons'] as List).cast<Json>().reversed)
                if ((s['finished'] as int) > 0) s,
            ].take(10).toList();
            final year = seasons.any((s) => s['start_year'] == season)
                ? season!
                : seasons.isEmpty
                ? null
                : seasons.first['start_year'] as int;
            return ListView(
              padding: pagePadding(context, 16, 40),
              children: [
                const BackHeader(
                  'Classement',
                  'mérité',
                  subtitle:
                      'Points réels contre points mérités (xPts) : ceux qu\'une équipe obtient en moyenne '
                      'avec la qualité de ses occasions et de celles qu\'elle concède.',
                ),
                const SizedBox(height: 14),
                ChipRow(
                  labels: [for (final c in comps) competitionName(c['code'] as String)],
                  selected: comps.indexOf(comp),
                  onSelected: (i) => setState(() {
                    competition = comps[i]['code'] as String;
                    season = null;
                  }),
                ),
                const SizedBox(height: 8),
                if (year == null)
                  const EmptyState('Aucun match terminé pour ce championnat.')
                else ...[
                  ChipRow(
                    labels: [for (final s in seasons) seasonLabel(s['start_year'] as int)],
                    selected: seasons.indexWhere((s) => s['start_year'] == year),
                    onSelected: (i) => setState(() => season = seasons[i]['start_year'] as int),
                  ),
                  const SizedBox(height: 14),
                  Loader<Json>(
                    key: ValueKey('${comp['code']}-$year'),
                    load: () async =>
                        await api.get('/competitions/${comp['code']}/seasons/$year/merited') as Json,
                    builder: (context, data, _) => _table(data),
                  ),
                ],
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _table(Json data) {
    final table = (data['table'] as List).cast<Json>();
    final threshold = (data['luck_threshold'] as num).toDouble();
    if (table.isEmpty) return const EmptyState('Aucun match terminé.');
    Widget header(String t, {double? width, TextAlign align = TextAlign.right}) => SizedBox(
      width: width,
      child: Text(
        t,
        textAlign: align,
        style: Fp.body(12, color: Fp.text3, weight: FontWeight.w600),
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        GlassCard.section(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 6),
          child: Column(
            children: [
              Row(
                children: [
                  header('#', width: 24, align: TextAlign.left),
                  Expanded(child: header('Équipe', align: TextAlign.left)),
                  header('Pts', width: 36),
                  header('Mérité', width: 56),
                  header('Écart', width: 56),
                ],
              ),
              const SizedBox(height: 4),
              for (final t in table) _row(t, data['competition'] as String, data['season'] as int),
            ],
          ),
        ),
        const SizedBox(height: 12),
        _Legend(
          color: Fp.win,
          text: 'Vert : plus de points que mérité (chance, gardien en feu, finition rare).',
        ),
        _Legend(
          color: Fp.loss,
          text: 'Rose : moins de points que mérité (malchance) ; souvent, ça se rééquilibre.',
        ),
        _Legend(
          color: Fp.text4,
          text: 'Gris : écart de moins de ${decimal(threshold, max: 0)} points, du hasard ordinaire.',
        ),
        const SizedBox(height: 8),
        Text(
          '${table.first['played']} matchs joués par le leader. Entre parenthèses : le rang au classement mérité. '
          'Source des xPts : Understat.',
          style: Fp.body(12, color: Fp.text3, height: 1.4),
        ),
        if (data['complete'] != true) ...[
          const SizedBox(height: 8),
          Text(
            'Understat n\'a pas encore les xPts de quelques matchs : les points mérités de certaines équipes '
            'sont incomplets.',
            style: Fp.body(12, color: Fp.warning, height: 1.4),
          ),
        ],
      ],
    );
  }

  Widget _row(Json t, String comp, int year) {
    final team = t['team'] as Json;
    final luck = (t['luck'] as num?)?.toDouble();
    final color = switch (t['verdict']) {
      'lucky' => Fp.win,
      'unlucky' => Fp.loss,
      _ => Fp.text3,
    };
    final merited = t['merited_rank'];
    return InkWell(
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => TeamScreen(
            teamId: team['id'] as int,
            name: team['name'] as String,
            competition: comp,
            season: year,
          ),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Row(
          children: [
            SizedBox(
              width: 24,
              child: Text('${t['rank']}', style: Fp.body(13, color: Fp.text2)),
            ),
            Expanded(
              child: Text.rich(
                TextSpan(
                  children: [
                    TextSpan(
                      text: team['name'] as String,
                      style: Fp.body(14, weight: FontWeight.w600),
                    ),
                    if (merited != null)
                      TextSpan(
                        text: '  ($merited)',
                        style: Fp.body(12, color: Fp.text3),
                      ),
                  ],
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            SizedBox(
              width: 36,
              child: Text(
                '${t['points']}',
                textAlign: TextAlign.right,
                style: Fp.body(14, weight: FontWeight.w700),
              ),
            ),
            SizedBox(
              width: 56,
              child: Text(
                t['xpts'] == null ? '—' : decimal(t['xpts'], max: 1),
                textAlign: TextAlign.right,
                style: Fp.body(14, color: Fp.text2),
              ),
            ),
            SizedBox(
              width: 56,
              child: Text(
                luck == null
                    ? '—'
                    : '${luck > 0
                          ? '+'
                          : luck < 0
                          ? '−'
                          : ''}${decimal(luck.abs(), max: 1)}',
                textAlign: TextAlign.right,
                style: Fp.body(14, color: color, weight: FontWeight.w700),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend({required this.color, required this.text});
  final Color color;
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 3),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 10,
          height: 10,
          margin: const EdgeInsets.only(top: 4, right: 8),
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        Expanded(
          child: Text(text, style: Fp.body(12, color: Fp.textSoft, height: 1.4)),
        ),
      ],
    ),
  );
}
