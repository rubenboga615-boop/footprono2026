import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'match_screen.dart';
import 'merited_screen.dart';
import 'notifications_screen.dart';

class MatchesScreen extends StatefulWidget {
  const MatchesScreen({super.key});

  @override
  State<MatchesScreen> createState() => _MatchesScreenState();
}

class _MatchesScreenState extends State<MatchesScreen> {
  String competition = '';
  DateTime? day;

  Future<(List<Upcoming>, List<MatchInfo>)> _load() async {
    final api = context.read<AppState>().api;
    final results = await Future.wait([
      api.get('/predictions/upcoming', {'limit': 400}),
      api.get('/live'),
    ]);
    return (
      [for (final j in results[0] as List) Upcoming(j as Json)],
      [for (final j in results[1] as List) MatchInfo(j as Json)],
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        bottom: false,
        child: Loader<(List<Upcoming>, List<MatchInfo>)>(
          load: _load,
          builder: (context, data, reload) {
            final (upcoming, live) = data;
            final days = <DateTime>{for (final u in upcoming) _day(u.match.date)}.toList()..sort();
            final selectedDay = day != null && days.contains(day) ? day : (days.isEmpty ? null : days.first);
            final comps = <String>{for (final u in upcoming) u.match.competition}.toList()..sort();
            final shown = upcoming
                .where((u) => competition.isEmpty || u.match.competition == competition)
                .where((u) => selectedDay == null || _day(u.match.date) == selectedDay)
                .toList();
            final analysed = shown.where((u) => u.summary != null).length;
            final today = _day(DateTime.now());
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(18, 26, 18, 120),
                children: [
                  Row(
                    children: [
                      const FpLogo(),
                      const Spacer(),
                      SquareButton(
                        icon: Icons.leaderboard_rounded,
                        tooltip: 'Classement mérité',
                        onTap: () =>
                            Navigator.of(context)
                                .push(MaterialPageRoute(builder: (_) => const MeritedScreen())),
                      ),
                      const SizedBox(width: 10),
                      SquareButton(
                        icon: Icons.notifications_none_rounded,
                        tooltip: 'Notifications',
                        dot: state.unread > 0,
                        onTap: () =>
                            Navigator.of(context)
                                .push(MaterialPageRoute(builder: (_) => const NotificationsScreen())),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  TwoToneTitle('Matchs', selectedDay == today ? 'du jour' : 'à venir'),
                  const SizedBox(height: 4),
                  Text(
                    '$analysed matchs analysés sur ${comps.length} championnats',
                    style: Fp.body(13, color: Fp.text2),
                  ),
                  const SizedBox(height: 16),
                  if (days.isNotEmpty) ...[
                    ChipRow(
                      labels: [for (final d in days) shortDate(d)],
                      selected: days.indexOf(selectedDay!),
                      onSelected: (i) => setState(() => day = days[i]),
                    ),
                    const SizedBox(height: 8),
                  ],
                  ChipRow(
                    labels: ['Toutes', for (final c in comps) competitionName(c)],
                    selected: competition.isEmpty ? 0 : comps.indexOf(competition) + 1,
                    onSelected: (i) => setState(() => competition = i == 0 ? '' : comps[i - 1]),
                  ),
                  const SizedBox(height: 16),
                  if (live.isNotEmpty) ...[
                    const SectionTitle('En direct'),
                    for (final m in live) _MatchCard(match: m),
                    const SectionTitle('À venir'),
                  ],
                  if (shown.isEmpty)
                    const EmptyState('Aucun match à venir pour ce filtre.', icon: Icons.event_busy_rounded),
                  for (final u in shown) _MatchCard(match: u.match, summary: u.summary),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  static DateTime _day(DateTime d) => DateTime(d.year, d.month, d.day);
}

class _MatchCard extends StatelessWidget {
  const _MatchCard({required this.match, this.summary});
  final MatchInfo match;
  final Summary? summary;

  @override
  Widget build(BuildContext context) {
    final s = summary;
    final m = match;
    return GlassCard(
      margin: const EdgeInsets.only(bottom: 12),
      highlight: m.isLive,
      onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => MatchScreen(matchId: m.id))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Text(
                competitionName(m.competition),
                style: Fp.body(12, color: Fp.text3, weight: FontWeight.w600),
              ),
              const Spacer(),
              if (m.isLive)
                Tag(m.when, color: Fp.win)
              else
                Text(
                  '${shortDate(m.date)} · ${m.when}',
                  style: Fp.body(12, color: Fp.text3, weight: FontWeight.w600),
                ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              TeamCircle(m.home.code),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  m.home.name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Fp.body(14, weight: FontWeight.w700),
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                child: Text(
                  m.score ?? 'vs',
                  style: m.score != null
                      ? Fp.title(18)
                      : Fp.body(12, color: Fp.text4, weight: FontWeight.w600),
                ),
              ),
              Expanded(
                child: Text(
                  m.away.name,
                  maxLines: 2,
                  textAlign: TextAlign.right,
                  overflow: TextOverflow.ellipsis,
                  style: Fp.body(14, weight: FontWeight.w700),
                ),
              ),
              const SizedBox(width: 10),
              TeamCircle(m.away.code),
            ],
          ),
          if (s != null) ...[
            const SizedBox(height: 12),
            OutcomeBar(s.home.probability, s.draw.probability, s.away.probability),
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  '1 · ${percent(s.home.probability)}',
                  style: Fp.body(12, color: Fp.accentLight, weight: FontWeight.w600),
                ),
                Text(
                  'N · ${percent(s.draw.probability)}',
                  style: Fp.body(12, color: Fp.textSoft, weight: FontWeight.w600),
                ),
                Text(
                  '2 · ${percent(s.away.probability)}',
                  style: Fp.body(12, color: Fp.text3, weight: FontWeight.w600),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: [
                InfoPill('+2,5 buts · ${percent(s.over25.probability)}'),
                InfoPill('Les deux marquent · ${percent(s.btts.probability)}'),
              ],
            ),
          ] else if (!m.isLive) ...[
            const SizedBox(height: 10),
            Text('Pas encore de prédiction pour ce match.', style: Fp.body(12, color: Fp.text3)),
          ],
        ],
      ),
    );
  }
}
