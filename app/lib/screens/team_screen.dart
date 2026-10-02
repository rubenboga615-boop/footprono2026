import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'merited_screen.dart';

/// Valeur absente (source sans donnée) : « — », jamais 0.
String _d(Object? v, {int max = 2, String unit = ''}) => v == null ? '—' : '${decimal(v, max: max)}$unit';

String seasonLabel(int year) => '$year-${((year + 1) % 100).toString().padLeft(2, '0')}';

/// Fiche équipe : les données collectées, domicile et extérieur séparés.
/// Gratuit : forme, buts, points. Premium : xG, pressing, corners, tirs, cartons, possession.
class TeamScreen extends StatefulWidget {
  const TeamScreen({super.key, required this.teamId, required this.name, this.competition, this.season});
  final int teamId;
  final String name;
  final String? competition;
  final int? season;

  @override
  State<TeamScreen> createState() => _TeamScreenState();
}

class _TeamScreenState extends State<TeamScreen> {
  late String? competition = widget.competition;
  late int? season = widget.season;
  int venue = 0;

  static const _venues = [('home', 'Domicile'), ('away', 'Extérieur'), ('all', 'Saison')];

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          key: ValueKey('$competition-$season'),
          load: () async => await api.get('/teams/${widget.teamId}/profile', {
            'competition': ?competition,
            if (season != null) 'season': '$season',
          }) as Json,
          builder: (context, data, reload) => _content(data),
        ),
      ),
    );
  }

  Widget _content(Json data) {
    final seasons = (data['seasons'] as List).cast<Json>().take(8).toList();
    final comp = data['competition'] as String, year = data['season'] as int;
    final current = seasons.indexWhere((s) => s['competition'] == comp && s['season'] == year);
    final locked = data['locked'] as bool;
    final venues = data['venues'] as Json;
    final v = venues[_venues[venue].$1] as Json;
    return ListView(
      padding: const EdgeInsets.fromLTRB(18, 16, 18, 40),
      children: [
        BackHeader(
          widget.name,
          '',
          subtitle: '${competitionName(comp)} ${seasonLabel(year)} · ${v['matches']} matchs joués',
          trailing: SquareButton(
            icon: Icons.leaderboard_rounded,
            tooltip: 'Classement mérité',
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => MeritedScreen(competition: comp, season: year),
              ),
            ),
          ),
        ),
        const SizedBox(height: 14),
        if (seasons.length > 1) ...[
          ChipRow(
            labels: [
              for (final s in seasons)
                '${competitionName(s['competition'] as String)} ${seasonLabel(s['season'] as int)}',
            ],
            selected: current < 0 ? 0 : current,
            onSelected: (i) => setState(() {
              competition = seasons[i]['competition'] as String;
              season = seasons[i]['season'] as int;
            }),
          ),
          const SizedBox(height: 12),
        ],
        _form((data['form'] as List).cast<Json>()),
        const SizedBox(height: 12),
        SegmentTabs(
          labels: [for (final x in _venues) x.$2],
          selected: venue,
          onSelected: (i) => setState(() => venue = i),
        ),
        const SizedBox(height: 12),
        if ((v['matches'] as int) == 0)
          const EmptyState('Aucun match terminé dans cette configuration.', icon: Icons.sports_soccer_rounded)
        else ...[
          _basics(v),
          const SizedBox(height: 12),
          if (locked)
            const PremiumLock(
              text:
                  'xG créés et concédés, pressing (PPDA), passes dangereuses, tirs cadrés, corners, '
                  'cartons, possession, arrêts et passes réussies sont inclus dans Premium.',
            )
          else
            _advanced(v),
        ],
        const SizedBox(height: 14),
        Text(
          'Matchs de championnat terminés. Sources : football-data (buts, tirs, corners, cartons), '
          'Understat (xG, pressing, passes dangereuses), API-Football (possession, arrêts, passes). '
          'La forme compte toutes les compétitions.',
          style: Fp.body(12, color: Fp.text3, height: 1.4),
        ),
      ],
    );
  }

  Widget _form(List<Json> form) => GlassCard.section(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Forme · 5 derniers matchs', style: Fp.title(15, weight: FontWeight.w600)),
        const SizedBox(height: 10),
        if (form.isEmpty)
          Text('Aucun match terminé.', style: Fp.body(13, color: Fp.text2))
        else
          for (final f in form)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(
                children: [
                  _ResultBox(f['result'] as String),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      '${f['venue'] == 'home' ? 'contre' : 'chez'} ${f['opponent']}',
                      style: Fp.body(14, weight: FontWeight.w600),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Text('${f['score']}', style: Fp.body(14, color: Fp.text2)),
                  const SizedBox(width: 10),
                  Text(numericDate(DateTime.parse(f['date'] as String)), style: Fp.body(12, color: Fp.text3)),
                ],
              ),
            ),
      ],
    ),
  );

  String get _where => switch (venue) {
    0 => ' à domicile',
    1 => ' à l\'extérieur',
    _ => '',
  };

  Widget _basics(Json v) {
    final n = v['matches'] as int, pts = v['points'] as int;
    return GlassCard.section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _Stat('Points', '$pts', '${decimal(pts / n)} par match$_where, sur $n matchs'),
          _Stat('Buts marqués', _d(v['goals_for']), 'par match$_where'),
          _Stat('Buts encaissés', _d(v['goals_against']), 'par match$_where'),
        ],
      ),
    );
  }

  Widget _advanced(Json v) {
    final rows = <Widget>[
      _Stat('xG créés', _d(v['xg_for']), 'qualité des occasions créées, par match'),
      _Stat('xG concédés', _d(v['xg_against']), 'qualité des occasions laissées, par match'),
      if (v['xpts'] != null) _Stat('Points mérités (xPts)', _d(v['xpts'], max: 1), 'avec ces occasions'),
      _Stat(
        'Pressing (PPDA)',
        _d(v['ppda'], max: 1),
        'passes adverses par action défensive : plus bas = plus intense',
      ),
      _Stat(
        'Passes dangereuses (deep)',
        _d(v['deep'], max: 1),
        'passes réussies près de la surface, par match',
      ),
      _Stat('Tirs cadrés', _d(v['shots_on_target'], max: 1), 'par match'),
      _Stat('Corners', _d(v['corners'], max: 1), 'obtenus par match'),
      _Stat('Cartons jaunes', _d(v['yellow_cards'], max: 1), 'par match'),
      _Stat('Possession', _d(v['possession'], max: 1, unit: ' %'), 'moyenne'),
      _Stat('Arrêts du gardien', _d(v['saves'], max: 1), 'par match'),
      _Stat('Passes réussies', _d(v['pass_pct'], max: 1, unit: ' %'), 'moyenne'),
    ];
    final notes = <String>[];
    final gf = (v['goals_for'] as num?)?.toDouble(), xg = (v['xg_for'] as num?)?.toDouble();
    final ga = (v['goals_against'] as num?)?.toDouble(), xga = (v['xg_against'] as num?)?.toDouble();
    if (gf != null && xg != null && (gf - xg).abs() >= 0.2) {
      notes.add(
        gf > xg
            ? 'Marque plus que ses xG (${decimal(gf)} contre ${decimal(xg)}) : finition efficace ou chanceuse, '
                  'ça ne dure pas toujours.'
            : 'Marque moins que ses xG (${decimal(gf)} contre ${decimal(xg)}) : finition ratée ou malchance, '
                  'souvent ça se rééquilibre.',
      );
    }
    if (ga != null && xga != null && (ga - xga).abs() >= 0.2) {
      notes.add(
        ga < xga
            ? 'Encaisse moins que ses xG concédés (${decimal(ga)} contre ${decimal(xga)}) : bon gardien ou chance.'
            : 'Encaisse plus que ses xG concédés (${decimal(ga)} contre ${decimal(xga)}) : gardien en difficulté '
                  'ou malchance.',
      );
    }
    return GlassCard.section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('Statistiques avancées', style: Fp.title(15, weight: FontWeight.w600)),
              ),
              Text('— = donnée absente', style: Fp.body(12, color: Fp.text3)),
            ],
          ),
          const SizedBox(height: 6),
          ...rows,
          for (final n in notes) ...[
            const SizedBox(height: 8),
            Text(n, style: Fp.body(13, color: Fp.textSoft, height: 1.4)),
          ],
        ],
      ),
    );
  }
}

class _ResultBox extends StatelessWidget {
  const _ResultBox(this.result);
  final String result;

  @override
  Widget build(BuildContext context) => Container(
    width: 26,
    height: 26,
    alignment: Alignment.center,
    decoration: BoxDecoration(
      color: switch (result) {
        'W' => Fp.win,
        'L' => Fp.loss,
        _ => Fp.text4,
      },
      borderRadius: BorderRadius.circular(8),
    ),
    child: Text(switch (result) {
      'W' => 'G',
      'L' => 'P',
      _ => 'N',
    }, style: Fp.body(13, weight: FontWeight.w700, color: const Color(0xFF0B0A10))),
  );
}

class _Stat extends StatelessWidget {
  const _Stat(this.label, this.value, this.hint);
  final String label, value, hint;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 7),
    child: Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: Fp.body(14, weight: FontWeight.w600)),
              Text(hint, style: Fp.body(12, color: Fp.text3)),
            ],
          ),
        ),
        const SizedBox(width: 10),
        Text(value, style: Fp.title(17, color: Fp.accentLight)),
      ],
    ),
  );
}
