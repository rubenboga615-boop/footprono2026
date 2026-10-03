import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'team_screen.dart' show seasonLabel;

/// Écart de jaunes par match à partir duquel un arbitre est dit plus sévère ou plus clément.
const _severityGap = 0.5;

String _n(Object? v) => v == null ? '—' : decimal(v);

/// Phrase sur la sévérité, seulement avec assez de matchs.
String? severity(Json s) {
  if (s['enough'] != true || s['yellow'] == null || s['league_yellow'] == null) return null;
  final gap = (s['yellow'] as num) - (s['league_yellow'] as num);
  if (gap >= _severityGap) return 'Plus sévère que la moyenne : +${decimal(gap)} jaune par match.';
  if (gap <= -_severityGap) return 'Plus clément que la moyenne : −${decimal(-gap)} jaune par match.';
  return 'Dans la moyenne du championnat (écart de moins de ${decimal(_severityGap)} jaune).';
}

/// Fiche arbitre : cartons par match comparés à la moyenne du même championnat, mêmes saisons.
class RefereeScreen extends StatelessWidget {
  const RefereeScreen({super.key, required this.name});
  final String name;

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          load: () async => await api.get('/referees/profile', {'name': name}) as Json,
          builder: (context, data, _) => _content(context, data),
        ),
      ),
    );
  }

  Widget _content(BuildContext context, Json data) {
    final total = data['total'] as Json;
    final seasons = (data['seasons'] as List).cast<Json>();
    final recent = (data['recent'] as List).cast<Json>();
    final min = data['min_matches'] as int;
    final latest = seasons.first;
    return ListView(
      padding: pagePadding(context, 16, 40, maxWidth: 1080),
      children: [
        BackHeader(
          'Arbitre',
          data['name'] as String,
          subtitle: '${total['matches']} matchs dirigés dans nos championnats depuis 2016.',
          trailing: SquareButton(
            icon: Icons.leaderboard_rounded,
            tooltip: 'Tous les arbitres',
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => RefereeTableScreen(
                  competition: latest['competition'] as String,
                  season: latest['season'] as int,
                ),
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),
        ...deskColumns(context, [
          _SummaryCard(
            title:
                '${competitionName(latest['competition'] as String)} ${seasonLabel(latest['season'] as int)}',
            s: latest,
            min: min,
          ),
          const SizedBox(height: 12),
          _SummaryCard(title: 'Depuis 2016', s: total, min: min),
          const SizedBox(height: 12),
          GlassCard.section(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Saison par saison', style: Fp.title(15, weight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text('jaunes par match · moyenne du championnat', style: Fp.body(12, color: Fp.text3)),
                const SizedBox(height: 6),
                for (final s in seasons)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 5),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            '${competitionName(s['competition'] as String)} ${seasonLabel(s['season'] as int)}',
                            style: Fp.body(14, weight: FontWeight.w600),
                          ),
                        ),
                        Text('${s['matches']} m.', style: Fp.body(12, color: Fp.text3)),
                        const SizedBox(width: 12),
                        SizedBox(
                          width: 40,
                          child: Text(
                            _n(s['yellow']),
                            textAlign: TextAlign.right,
                            style: Fp.body(14, color: Fp.accentLight, weight: FontWeight.w700),
                          ),
                        ),
                        SizedBox(
                          width: 48,
                          child: Text(
                            _n(s['league_yellow']),
                            textAlign: TextAlign.right,
                            style: Fp.body(14, color: Fp.text2),
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          GlassCard.section(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Derniers matchs', style: Fp.title(15, weight: FontWeight.w600)),
                const SizedBox(height: 6),
                for (final r in recent)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 5),
                    child: Row(
                      children: [
                        SizedBox(
                          width: 78,
                          child: Text(
                            numericDate(DateTime.parse(r['date'] as String)),
                            style: Fp.body(12, color: Fp.text2),
                          ),
                        ),
                        Expanded(
                          child: Text(
                            '${r['home']} – ${r['away']}',
                            overflow: TextOverflow.ellipsis,
                            style: Fp.body(13, weight: FontWeight.w600),
                          ),
                        ),
                        Text(
                          '${r['home_yellow']} + ${r['away_yellow']} J'
                          '${(r['red'] as int) > 0 ? ' · ${r['red']} R' : ''}',
                          style: Fp.body(13, color: Fp.textSoft),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          Text(
            'Cartons : football-data ; arbitre : API-Football (football-data en Premier League). '
            'La moyenne de référence est celle du même championnat sur les mêmes saisons. Le moteur '
            'tient déjà compte de l\'arbitre pour les marchés cartons.',
            style: Fp.body(12, color: Fp.text3, height: 1.4),
          ),
        ]),
      ],
    );
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.title, required this.s, required this.min});
  final String title;
  final Json s;
  final int min;

  @override
  Widget build(BuildContext context) {
    final verdict = severity(s);
    return GlassCard.section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(title, style: Fp.title(15, weight: FontWeight.w600)),
              ),
              Text('${s['matches']} matchs', style: Fp.body(12, color: Fp.text3)),
            ],
          ),
          const SizedBox(height: 6),
          KeyValue('Jaunes par match', '${_n(s['yellow'])}  (moyenne ${_n(s['league_yellow'])})'),
          KeyValue('Rouges par match', '${_n(s['red'])}  (moyenne ${_n(s['league_red'])})'),
          KeyValue('Jaunes à l\'équipe à domicile', _n(s['home_yellow'])),
          KeyValue('Jaunes à l\'équipe à l\'extérieur', _n(s['away_yellow'])),
          const SizedBox(height: 6),
          Text(
            verdict ?? 'Seulement ${s['matches']} matchs : pas assez pour juger ($min minimum).',
            style: Fp.body(13, color: verdict == null ? Fp.warning : Fp.textSoft, height: 1.4),
          ),
        ],
      ),
    );
  }
}

/// Arbitres d'une saison, du plus sévère au plus clément ; peu de matchs : non classés.
class RefereeTableScreen extends StatefulWidget {
  const RefereeTableScreen({super.key, this.competition, this.season});
  final String? competition;
  final int? season;

  @override
  State<RefereeTableScreen> createState() => _RefereeTableScreenState();
}

class _RefereeTableScreenState extends State<RefereeTableScreen> {
  late String? competition = widget.competition;
  late int? season = widget.season;

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<List<Json>>(
          load: () async => (await api.get('/competitions') as List).cast<Json>(),
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
                  'Les',
                  'arbitres',
                  subtitle: 'Cartons jaunes par match, comparés à la moyenne du championnat.',
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
                        await api.get('/competitions/${comp['code']}/seasons/$year/referees') as Json,
                    builder: (context, data, _) => _table(context, data),
                  ),
                ],
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _table(BuildContext context, Json data) {
    final refs = (data['referees'] as List).cast<Json>();
    final ranked = refs.where((r) => r['enough'] == true).toList();
    final others = refs.where((r) => r['enough'] != true).toList();
    final league = (data['league_yellow'] as num).toDouble();
    final scale = [
      5.0,
      for (final r in ranked) (r['yellow'] as num).toDouble(),
    ].reduce((a, b) => a > b ? a : b);
    final missing = data['without_referee'] as int;
    Widget row(Json r, {bool bar = true}) => InkWell(
      onTap: () =>
          Navigator.of(context)
              .push(MaterialPageRoute(builder: (_) => RefereeScreen(name: r['name'] as String))),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(r['name'] as String, style: Fp.body(14, weight: FontWeight.w600)),
                ),
                Text('${r['matches']} m.', style: Fp.body(12, color: Fp.text3)),
                const SizedBox(width: 10),
                SizedBox(
                  width: 40,
                  child: Text(
                    _n(r['yellow']),
                    textAlign: TextAlign.right,
                    style: Fp.body(14, color: bar ? Fp.accentLight : Fp.text3, weight: FontWeight.w700),
                  ),
                ),
              ],
            ),
            if (bar) ...[
              const SizedBox(height: 4),
              LinearProgressIndicator(
                value: (r['yellow'] as num).toDouble() / scale,
                minHeight: 5,
                color: (r['yellow'] as num) >= league ? Fp.loss : Fp.win,
                backgroundColor: Fp.fill7,
                borderRadius: BorderRadius.circular(4),
              ),
            ],
          ],
        ),
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        GlassCard.section(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              KeyValue('Moyenne du championnat', '${_n(league)} jaunes par match', bold: true),
              Text('${data['matches']} matchs terminés', style: Fp.body(12, color: Fp.text3)),
              const Divider(),
              if (ranked.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Text(
                    'Aucun arbitre n\'a encore dirigé ${data['min_matches']} matchs cette saison.',
                    style: Fp.body(13, color: Fp.text2),
                  ),
                )
              else
                for (final r in ranked) row(r),
            ],
          ),
        ),
        if (others.isNotEmpty) ...[
          SectionTitle('Moins de ${data['min_matches']} matchs (non classés)'),
          GlassCard.section(child: Column(children: [for (final r in others) row(r, bar: false)])),
        ],
        const SizedBox(height: 12),
        Text(
          'Barre rose : au-dessus de la moyenne ; verte : en dessous. Échelle de 0 à ${decimal(scale)} '
          'jaunes par match.',
          style: Fp.body(12, color: Fp.text3, height: 1.4),
        ),
        if (missing > 0) ...[
          const SizedBox(height: 8),
          Text(
            '$missing matchs de cette saison sans arbitre connu dans la base : à compléter.',
            style: Fp.body(12, color: Fp.warning, height: 1.4),
          ),
        ],
      ],
    );
  }
}
