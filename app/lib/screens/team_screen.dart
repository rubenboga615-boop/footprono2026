import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/visage.dart';
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
      backgroundColor: V.bg,
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
    final all = venues['all'] as Json;
    final rank = data['rank'] as Json?;
    final upcoming = ((data['upcoming'] as List?) ?? const []).cast<Json>();
    return ListView(
      padding: pagePadding(context, 16, 40, maxWidth: 640),
      children: [
        // Maquette 26 : retour, « Suivie » à droite ; le classement mérité en plus (utile).
        VTopBar(
          '',
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              _FollowChip(teamId: widget.teamId),
              const SizedBox(width: 8),
              VIconBtn(
                VIcon.trophy,
                tooltip: 'Classement mérité',
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => MeritedScreen(competition: comp, season: year),
                  ),
                ),
              ),
            ],
          ),
        ),
        Row(
          children: [
            VTeamBadge(teamCode(widget.name), size: 56, fontSize: 15),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(widget.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: V.b(20)),
                  Text(
                    [
                      '${competitionName(comp)} ${seasonLabel(year)}',
                      if (rank != null) '${rank['rank']}${rank['rank'] == 1 ? 'er' : 'e'}',
                      if (rank != null) '${rank['points']} pts' else '${all['matches']} matchs',
                    ].join(' · '),
                    style: V.mu_(12.5),
                  ),
                ],
              ),
            ),
          ],
        ),
        if (seasons.length > 1) ...[
          const SizedBox(height: 12),
          VTabs(
            items: [
              for (final s in seasons)
                '${competitionName(s['competition'] as String)} ${seasonLabel(s['season'] as int)}',
            ],
            selected: current < 0 ? 0 : current,
            onSelect: (i) => setState(() {
              competition = seasons[i]['competition'] as String;
              season = seasons[i]['season'] as int;
            }),
          ),
        ],
        _form((data['form'] as List).cast<Json>(), all),
        if (upcoming.isNotEmpty) _upcoming(upcoming),
        const SizedBox(height: 12),
        VSeg(
          items: [for (final x in _venues) x.$2],
          selected: venue,
          onSelect: (i) => setState(() => venue = i),
        ),
        if ((v['matches'] as int) == 0)
          VCard(
            child: Text('Aucun match terminé dans cette configuration.', style: V.t(13, color: V.mu)),
          )
        else ...[
          _basics(v),
          if (locked)
            const Padding(
              padding: EdgeInsets.only(top: 12),
              child: PremiumLock(
                text:
                    'xG créés et concédés, pressing (PPDA), passes dangereuses, tirs cadrés, corners, '
                    'cartons, possession, arrêts et passes réussies sont inclus dans Premium.',
              ),
            )
          else
            _advanced(v),
        ],
        const SizedBox(height: 14),
        Text(
          'Matchs de championnat terminés. Sources : football-data (buts, tirs, corners, cartons), '
          'Understat (xG, pressing, passes dangereuses), API-Football (possession, arrêts, passes). '
          'La forme compte toutes les compétitions.',
          style: V.mu_(11.5),
        ),
      ],
    );
  }

  /// FORME de la maquette 26 : 5 pastilles V / N / D (la plus ancienne à gauche) et les buts
  /// marqués par match ; le détail des 5 matchs dessous (gardé : utile).
  Widget _form(List<Json> form, Json all) {
    final goals = (all['goals_for'] as num?)?.toDouble();
    return VCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const VKicker('Forme'),
          const SizedBox(height: 10),
          if (form.isEmpty)
            Text('Aucun match terminé.', style: V.t(13, color: V.mu))
          else ...[
            Row(
              children: [
                for (final f in form.reversed) ...[
                  _ResultBox(f['result'] as String),
                  const SizedBox(width: 6),
                ],
                const Spacer(),
                if (goals != null)
                  Text(
                    '${decimal(goals, max: 1)} but${goals >= 2 ? 's' : ''} marqué${goals >= 2 ? 's' : ''} / match',
                    style: V.mu_(12),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            for (final f in form)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        '${f['venue'] == 'home' ? 'contre' : 'chez'} ${f['opponent']}',
                        style: V.t(12.5, color: V.mu),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    Text('${f['score']}', style: V.t(12.5, color: V.mu)),
                    const SizedBox(width: 10),
                    Text(numericDate(DateTime.parse(f['date'] as String)), style: V.mu_(11.5)),
                  ],
                ),
              ),
          ],
        ],
      ),
    );
  }

  /// PROCHAINS MATCHS de la maquette 26 : adversaire, lieu, jour, chance de gagner du moteur.
  Widget _upcoming(List<Json> rows) => VCard(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const VKicker('Prochains matchs'),
        for (final (i, u) in rows.indexed) ...[
          if (i > 0) const Divider(height: 1, thickness: 1, color: V.line),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 9),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${u['opponent']} (${u['home'] == true ? 'dom.' : 'ext.'})', style: V.t(14)),
                      Text(
                        u['kickoff_at'] == null
                            ? shortDate(DateTime.parse(u['date'] as String))
                            : '${shortDate(DateTime.parse(u['kickoff_at'] as String).toLocal())} · '
                                  '${hourMinute(DateTime.parse(u['kickoff_at'] as String).toLocal())}',
                        style: V.mu_(12),
                      ),
                    ],
                  ),
                ),
                if (u['win'] != null)
                  Text(percent((u['win'] as num).toDouble()), style: V.t(13, color: V.mu)),
              ],
            ),
          ),
        ],
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
    return VCard(
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
    return VCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              const Expanded(child: VKicker('Statistiques avancées')),
              Text('— = donnée absente', style: V.mu_(11.5)),
            ],
          ),
          const SizedBox(height: 6),
          ...rows,
          for (final n in notes) ...[const SizedBox(height: 8), Text(n, style: V.t(12.5, color: V.mu))],
        ],
      ),
    );
  }
}

class _ResultBox extends StatelessWidget {
  const _ResultBox(this.result);
  final String result;

  @override
  Widget build(BuildContext context) {
    final (bg, fg, letter) = formColors(result);
    return Container(
      width: 28,
      height: 28,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: bg, shape: BoxShape.circle),
      child: Text(letter, style: V.b(12, fg)),
    );
  }
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
              Text(label, style: V.t(14)),
              Text(hint, style: V.mu_(11.5)),
            ],
          ),
        ),
        const SizedBox(width: 10),
        Text(value, style: V.b(16)),
      ],
    ),
  );
}

class _FollowChip extends StatelessWidget {
  const _FollowChip({required this.teamId});
  final int teamId;

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    if (state.me == null) return const SizedBox.shrink();
    final on = state.followed.contains(teamId);
    return GestureDetector(
      onTap: () => guard(context, () => state.toggleFollow(teamId)),
      child: VChip(
        on ? 'Suivie' : 'Suivre',
        kind: on ? VChipKind.vi : VChipKind.eq,
        arrow: const VIc(VIcon.star, size: 13),
      ),
    );
  }
}
