// Onglet « En direct » de l'écran d'un match (plan du 10/11/2026, étape 7 ; maquettes D2 à
// D4) : Résumé (chronologie et chances en direct), Statistiques (match, 1re, 2e mi-temps),
// Compositions (terrain, systèmes, entraîneurs, remplaçants). Après le match : « Résumé ».

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../format.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/live_chances.dart';
import 'live_coupon_screen.dart';

/// Statistiques montrées, dans l'ordre de la maquette D3 (nom chez API-Football → libellé).
const liveStatLabels = [
  ('Shots on Goal', 'Tirs cadrés'),
  ('Total Shots', 'Tirs'),
  ('Corner Kicks', 'Corners'),
  ('Ball Possession', 'Possession'),
  ('expected_goals', 'xG'),
  ('Fouls', 'Fautes'),
  ('Yellow Cards', 'Cartons jaunes'),
  ('Red Cards', 'Cartons rouges'),
  ('Offsides', 'Hors-jeu'),
  ('Goalkeeper Saves', 'Arrêts du gardien'),
];

class LiveTab extends StatefulWidget {
  const LiveTab({super.key, required this.match, this.before});
  final MatchInfo match;

  /// Chances d'avant le match (1, N, 2), pour la carte « Chances en direct ».
  final (double, double, double)? before;

  @override
  State<LiveTab> createState() => _LiveTabState();
}

class _LiveTabState extends State<LiveTab> {
  int sub = 0;
  int half = 0;
  Json? data;
  Object? error;

  @override
  void initState() {
    super.initState();
    _load();
    _loadCoupons(null);
  }

  // Coupon en direct (maquette D13) : propositions relues quand le match entre dans une
  // fenêtre (pause, 60e, 75e) ; une requête à chaque ouverture de fenêtre.
  void _loadCoupons(LiveTab? old) {
    final now = liveWindow(widget.match.apiStatus, widget.match.liveMinute);
    final before = old == null ? null : liveWindow(old.match.apiStatus, old.match.liveMinute);
    if (now != null && now != before) context.read<AppState>().loadLiveCoupons();
  }

  // Relu à chaque nouveau relevé du match (l'écran du match se recharge à chaque relevé
  // poussé, ou toutes les 30 s) : avant, le minuteur ne partait pas si le match commençait
  // après l'ouverture de l'écran (retour du fondateur du 12/11/2026).
  @override
  void didUpdateWidget(LiveTab old) {
    super.didUpdateWidget(old);
    if (old.match.liveKey != widget.match.liveKey) _load();
    _loadCoupons(old);
  }

  Future<void> _load() async {
    try {
      final j = await context.read<AppState>().api.get('/matches/${widget.match.id}/live') as Json;
      if (mounted) {
        setState(() {
          data = j;
          error = null;
        });
      }
    } on ApiException catch (e) {
      if (mounted && data == null) setState(() => error = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = data;
    if (d == null) {
      return error == null
          ? const Padding(
              padding: EdgeInsets.all(24),
              child: Center(child: CircularProgressIndicator()),
            )
          : Text('Détails du match indisponibles pour le moment.', style: Fp.body(13, color: Fp.muted));
    }
    final m = widget.match;
    final live = m.isLive;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SegmentTabs(
          labels: [live ? 'Résumé' : 'Déroulé', 'Statistiques', 'Compositions'],
          selected: sub,
          onSelected: (i) => setState(() => sub = i),
        ),
        const SizedBox(height: 12),
        ...switch (sub) {
          0 => _summary(d),
          1 => _stats(d),
          _ => _lineups(d),
        },
      ],
    );
  }

  // --- Résumé ---------------------------------------------------------------

  List<Widget> _summary(Json d) {
    final m = widget.match;
    final events = (d['events'] as List).cast<Json>();
    final lineups = (d['lineups'] as List).cast<Json>();
    final starters = {
      for (final l in lineups)
        for (final p in (l['players'] as List).cast<Json>())
          if (p['starter'] == true) '${p['name']}',
    };
    final now = m.isLive ? (m.liveHome, m.liveAway) : (m.homeGoals, m.awayGoals);
    final rows = timeline(
      events,
      starters,
      score: now.$1 == null || now.$2 == null ? null : (now.$1!, now.$2!),
    );
    return [
      if (rows.isEmpty)
        Text(
          m.isLive ? 'Pas encore d\'événement dans ce match.' : 'Pas de détails pour ce match.',
          style: Fp.body(13, color: Fp.muted),
        )
      else
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
          decoration: BoxDecoration(color: Fp.card, borderRadius: BorderRadius.circular(18)),
          child: Column(
            children: [
              for (final (i, r) in rows.reversed.indexed) ...[
                if (i > 0) const Divider(height: 1, color: Fp.divider),
                _row(r),
              ],
            ],
          ),
        ),
      const SizedBox(height: 12),
      if (m.isLive) LiveChancesCard(match: m, before: widget.before),
      if (liveWindow(m.apiStatus, m.liveMinute) case (_, final closes))
        ValueListenableBuilder<LiveCoupons?>(
          valueListenable: context.read<AppState>().liveCoupons,
          builder: (context, lc, _) => lc == null || !lc.matches.any((x) => x.id == m.id)
              ? const SizedBox.shrink()
              : Material(
                  color: Fp.card,
                  borderRadius: BorderRadius.circular(18),
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: () =>
                        Navigator.of(context)
                            .push(MaterialPageRoute(builder: (_) => const LiveCouponScreen())),
                    child: Container(
                      padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: const Color(0xFF6B4F1D)),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('Coupon en direct', style: Fp.body(15, weight: FontWeight.w700)),
                                Text(
                                  'Propositions du moteur avec ce match · jusqu\'à la ${closes}e',
                                  style: Fp.body(12.5, color: Fp.muted),
                                ),
                              ],
                            ),
                          ),
                          Text(
                            'Voir ›',
                            style: Fp.body(13, color: Fp.lilac, weight: FontWeight.w700),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
        ),
    ];
  }

  Widget _row(TimelineRow r) {
    if (r.halfTime != null) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Center(
          child: Text(
            'MI-TEMPS · ${r.halfTime}',
            style: Fp.body(12, weight: FontWeight.w700, color: Fp.muted).copyWith(letterSpacing: 1),
          ),
        ),
      );
    }
    final home = r.side != 'away';
    final minute = Text(
      r.minute,
      style: Fp.body(13.5, weight: FontWeight.w700, color: Fp.muted),
    );
    final text = Expanded(
      child: Text.rich(
        TextSpan(
          children: [
            TextSpan(
              text: r.main,
              style: Fp.body(14, weight: r.bold ? FontWeight.w700 : FontWeight.w500),
            ),
            if (r.more != null)
              TextSpan(
                text: ' ${r.more}',
                style: Fp.body(13, color: Fp.muted),
              ),
          ],
        ),
        textAlign: home ? TextAlign.left : TextAlign.right,
      ),
    );
    final icon = Text(r.icon, style: const TextStyle(fontSize: 15));
    final score = Text(r.score ?? '', style: Fp.body(14, weight: FontWeight.w700));
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        children: home
            ? [SizedBox(width: 48, child: minute), icon, const SizedBox(width: 10), text, score]
            : [
                score,
                const SizedBox(width: 8),
                text,
                const SizedBox(width: 10),
                icon,
                SizedBox(
                  width: 48,
                  child: Align(alignment: Alignment.centerRight, child: minute),
                ),
              ],
      ),
    );
  }

  // --- Statistiques ---------------------------------------------------------

  List<Widget> _stats(Json d) {
    final s = d['stats'] as Json?;
    if (s == null) {
      return [Text('Pas encore de statistiques pour ce match.', style: Fp.body(13, color: Fp.muted))];
    }
    final halves = s['first'] != null;
    final pick = switch (halves ? half : 0) {
      1 => s['first'] as Json,
      2 => s['second'] as Json,
      _ => s['match'] as Json,
    };
    final home = (pick['home'] as Map?)?.cast<String, dynamic>() ?? {};
    final away = (pick['away'] as Map?)?.cast<String, dynamic>() ?? {};
    final rows = [
      for (final (key, label) in liveStatLabels)
        if (home.containsKey(key) || away.containsKey(key))
          if (!(key == 'Red Cards' && statValue(home[key]) == 0 && statValue(away[key]) == 0))
            (label, home[key], away[key]),
    ];
    return [
      if (halves) ...[
        SegmentTabs(
          labels: const ['Match', '1re mi-temps', '2e mi-temps'],
          selected: half,
          onSelected: (i) => setState(() => half = i),
        ),
        const SizedBox(height: 12),
      ],
      Container(
        padding: const EdgeInsets.fromLTRB(14, 6, 14, 10),
        decoration: BoxDecoration(color: Fp.card, borderRadius: BorderRadius.circular(18)),
        child: Column(children: [for (final (label, h, a) in rows) _statRow(label, h, a)]),
      ),
      const SizedBox(height: 10),
      Text(
        widget.match.isLive ? 'Relevé chaque minute (API-Football).' : 'Statistiques d\'API-Football.',
        style: Fp.body(12.5, color: Fp.text2),
      ),
    ];
  }

  Widget _statRow(String label, Object? h, Object? a) {
    final hv = statValue(h), av = statValue(a);
    final total = hv + av;
    final share = total <= 0 ? 0.5 : hv / total;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Column(
        children: [
          Row(
            children: [
              Text(statText(h), style: Fp.body(15, weight: FontWeight.w700)),
              Expanded(
                child: Text(
                  label,
                  textAlign: TextAlign.center,
                  style: Fp.body(14, color: Fp.muted),
                ),
              ),
              Text(statText(a), style: Fp.body(15, weight: FontWeight.w700)),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              Expanded(
                flex: (share * 1000).round().clamp(1, 999),
                child: Container(
                  height: 6,
                  decoration: BoxDecoration(color: Fp.accent, borderRadius: BorderRadius.circular(3)),
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                flex: ((1 - share) * 1000).round().clamp(1, 999),
                child: Container(
                  height: 6,
                  decoration: BoxDecoration(color: Fp.line, borderRadius: BorderRadius.circular(3)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // --- Compositions ---------------------------------------------------------

  List<Widget> _lineups(Json d) {
    final lineups = {for (final l in (d['lineups'] as List).cast<Json>()) '${l['side']}': l};
    if (lineups.isEmpty) {
      return [
        Text(
          'Compositions pas encore données (en général une heure avant le match).',
          style: Fp.body(13, color: Fp.muted),
        ),
      ];
    }
    final m = widget.match;
    final events = (d['events'] as List).cast<Json>();
    Widget title(Json? l, String team) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Expanded(
            child: Text(
              [team, if (l?['formation'] != null) '${l!['formation']}'].join(' · '),
              style: Fp.body(16, weight: FontWeight.w700),
            ),
          ),
          if (l?['coach'] != null) Text('${l!['coach']}', style: Fp.body(13.5, color: Fp.muted)),
        ],
      ),
    );
    final home = lineups['home'], away = lineups['away'];
    return [
      title(home, m.home.name),
      LayoutBuilder(
        builder: (context, c) => _Pitch(home: home, away: away, width: c.maxWidth),
      ),
      title(away, m.away.name),
      const SizedBox(height: 6),
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
        decoration: BoxDecoration(color: Fp.card, borderRadius: BorderRadius.circular(18)),
        child: Column(
          children: [
            for (final (i, (side, team)) in [('home', m.home.name), ('away', m.away.name)].indexed)
              if (lineups[side] != null) ...[
                if (i > 0) const Divider(height: 1, color: Fp.divider),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Remplaçants · $team', style: Fp.body(14.5, weight: FontWeight.w700)),
                      const SizedBox(height: 4),
                      Text(
                        substitutes(lineups[side]!, events).join(', '),
                        style: Fp.body(13.5, color: Fp.muted, height: 1.4),
                      ),
                    ],
                  ),
                ),
              ],
          ],
        ),
      ),
    ];
  }
}

/// Valeur comptable d'une statistique (« 58% » → 58, « 1.21 » → 1,21, rien → 0).
double statValue(Object? v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v'.replaceAll('%', '').trim()) ?? 0;
}

/// Statistique écrite à la française : « 58 % », « 1,62 », « 0 ».
String statText(Object? v) {
  if (v == null) return '0';
  final s = '$v';
  if (s.endsWith('%')) return '${s.substring(0, s.length - 1).trim()}$nbsp%';
  return s.replaceAll('.', ',');
}

/// Remplaçants, avec « ✓ 46' » pour ceux qui sont entrés.
List<String> substitutes(Json lineup, List<Json> events) {
  final side = '${lineup['side']}';
  // Joueur reconnu par son numéro chez API-Football, sinon par son nom.
  final entered = <String, String>{};
  for (final e in events) {
    if (e['kind'] != 'subst' || e['side'] != side) continue;
    for (final key in [e['player_id'], e['assist_id'], e['player'], e['assist']]) {
      if (key != null) entered['$key'] = minuteText(e);
    }
  }
  String? when(Json p) => entered['${p['id']}'] ?? entered['${p['name']}'];
  return [
    for (final p in (lineup['players'] as List).cast<Json>())
      if (p['starter'] != true) when(p) == null ? '${p['name']}' : '${p['name']} ✓ ${when(p)}',
  ];
}

String minuteText(Json e) {
  final extra = e['extra'] as int?;
  return '${e['minute'] ?? ''}${extra != null && extra > 0 ? '+$extra' : ''}\'';
}

class TimelineRow {
  TimelineRow({
    this.minute = '',
    this.side,
    this.icon = '',
    this.main = '',
    this.more,
    this.score,
    this.bold = false,
    this.halfTime,
  });
  final String minute;
  final String? side;
  final String icon;
  final String main;
  final String? more;
  final String? score;
  final bool bold;

  /// Ligne « MI-TEMPS · 1-0 » entre les deux périodes.
  final String? halfTime;
}

/// Chronologie dans l'ordre du match (la plus récente est montrée en haut), score après
/// chaque but, ligne de la mi-temps. Remplacement : « sortant → entrant » (le titulaire sort).
///
/// But contre son camp : le camp donné par API-Football n'est pas toujours celui qui marque ;
/// si le score obtenu ne redonne pas [score] (score du moment), ces buts changent de camp.
List<TimelineRow> timeline(List<Json> events, Set<String> starters, {(int, int)? score}) {
  if (score != null) {
    final goals = events.where((e) => e['kind'] == 'Goal' && e['detail'] != 'Missed Penalty');
    final h = goals.where((e) => e['side'] == 'home').length;
    final a = goals.where((e) => e['side'] == 'away').length;
    if ((h, a) != score) {
      events = [
        for (final e in events)
          e['kind'] == 'Goal' && e['detail'] == 'Own Goal'
              ? {...e, 'side': e['side'] == 'home' ? 'away' : 'home'}
              : e,
      ];
    }
  }
  var home = 0, away = 0;
  var halfDone = false;
  final out = <TimelineRow>[];
  for (final e in events) {
    final minute = e['minute'] as int? ?? 0;
    if (!halfDone && minute > 45) {
      halfDone = true;
      out.add(TimelineRow(halfTime: '$home-$away'));
    }
    final kind = '${e['kind']}', detail = '${e['detail'] ?? ''}';
    final player = e['player'] as String?, assist = e['assist'] as String?;
    final side = e['side'] as String?;
    switch (kind) {
      case 'Goal' when detail != 'Missed Penalty':
        if (side == 'home') home++;
        if (side == 'away') away++;
        out.add(
          TimelineRow(
            minute: minuteText(e),
            side: side,
            icon: '⚽',
            main: player ?? 'But',
            more: switch (detail) {
              'Penalty' => 'penalty',
              'Own Goal' => 'contre son camp',
              _ => assist == null ? null : 'passe de $assist',
            },
            score: '$home-$away',
            bold: true,
          ),
        );
      case 'Goal':
        out.add(
          TimelineRow(
            minute: minuteText(e),
            side: side,
            icon: '❌',
            main: player ?? '',
            more: 'penalty manqué',
          ),
        );
      case 'Card':
        final red = detail.toLowerCase().contains('red') || detail.toLowerCase().contains('second');
        out.add(TimelineRow(minute: minuteText(e), side: side, icon: red ? '🟥' : '🟨', main: player ?? ''));
      case 'subst':
        final (out_, in_) = assist != null && starters.contains(assist) && !starters.contains(player)
            ? (assist, player)
            : (player, assist);
        out.add(
          TimelineRow(minute: minuteText(e), side: side, icon: '🔁', main: '${out_ ?? '?'} → ${in_ ?? '?'}'),
        );
      case 'Var':
        out.add(
          TimelineRow(
            minute: minuteText(e),
            side: side,
            icon: '📺',
            main: 'VAR : ${detail.isEmpty ? 'décision' : varLabel(detail)}',
            more: player,
          ),
        );
    }
  }
  return out;
}

String varLabel(String detail) => switch (detail) {
  'Goal cancelled' => 'but refusé',
  'Penalty confirmed' => 'penalty confirmé',
  'Penalty cancelled' => 'penalty annulé',
  'Goal confirmed' => 'but confirmé',
  'Card upgrade' => 'carton modifié',
  _ => detail,
};

/// Terrain (maquette D4) : domicile en haut (gardien en haut), extérieur en bas ; chaque
/// joueur à sa place « ligne:colonne » donnée par API-Football.
class _Pitch extends StatelessWidget {
  const _Pitch({required this.home, required this.away, required this.width});
  final Json? home;
  final Json? away;
  final double width;

  @override
  Widget build(BuildContext context) {
    List<List<Json>> lines(Json? l) {
      final byRow = <int, List<Json>>{};
      for (final p in ((l?['players'] as List?) ?? const []).cast<Json>()) {
        final grid = '${p['grid'] ?? ''}'.split(':');
        if (p['starter'] != true || grid.length != 2) continue;
        final row = int.tryParse(grid[0]), col = int.tryParse(grid[1]);
        if (row == null || col == null) continue;
        byRow.putIfAbsent(row, () => []).add({...p, '_col': col});
      }
      final keys = byRow.keys.toList()..sort();
      return [
        for (final k in keys) byRow[k]!..sort((a, b) => (a['_col'] as int).compareTo(b['_col'] as int)),
      ];
    }

    final top = lines(home), bottom = lines(away).reversed.toList();
    if (top.isEmpty && bottom.isEmpty) return const SizedBox.shrink();
    Widget row(List<Json> players, Color color, Color text) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          for (final p in players)
            SizedBox(
              width: (width - 24) / 5,
              child: Column(
                children: [
                  CircleAvatar(
                    radius: 15,
                    backgroundColor: color,
                    child: Text(
                      '${p['number'] ?? ''}',
                      style: Fp.body(12.5, weight: FontWeight.w800, color: text),
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    shortName('${p['name']}'),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.center,
                    style: Fp.body(11.5, color: Colors.white),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF12301F),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFF1F5B3A)),
      ),
      child: Column(
        children: [
          for (final r in top) row(r, Fp.accent, Colors.white),
          if (top.isNotEmpty && bottom.isNotEmpty) const Divider(color: Color(0xFF1F5B3A), height: 14),
          for (final r in bottom) row(r, Fp.loss, const Color(0xFF3A0D16)),
        ],
      ),
    );
  }
}

/// « C. Lewin » plutôt que « Dominic Calvert-Lewin » sur le terrain : le nom de famille.
String shortName(String name) {
  final parts = name.trim().split(RegExp(r'\s+'));
  return parts.length <= 1 ? name : parts.sublist(1).join(' ');
}
