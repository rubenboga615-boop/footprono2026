// Recherche (loupe de l'en-tête du tableau de bord, maquette 35) : matchs à venir et équipes,
// comme la palette de la version ordinateur. ``pickMatch`` : choisir un match (nouvelle alerte
// de cote) au lieu de l'ouvrir.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../desktop/desktop_shell.dart' show fold;
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../widgets/visage.dart';
import 'match_screen.dart';
import 'team_screen.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key, this.pickMatch = false});
  final bool pickMatch;

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  String query = '';
  List<Upcoming>? upcoming;

  @override
  void initState() {
    super.initState();
    context
        .read<AppState>()
        .api
        .get('/predictions/upcoming', {'limit': 400, 'cups': 'true', 'nations': 'true'})
        .then((j) {
          if (mounted) setState(() => upcoming = [for (final u in j as List) Upcoming(u as Json)]);
        })
        .catchError((Object _) {
          if (mounted) setState(() => upcoming = const []);
        });
  }

  @override
  Widget build(BuildContext context) {
    final q = fold(query.trim());
    final all = (upcoming ?? const <Upcoming>[]).where((u) => !u.match.started).toList();
    final matches = [
      for (final u in all)
        if (q.isEmpty ||
            fold('${u.match.home.name} ${u.match.away.name} ${competitionName(u.match.competition)}')
                .contains(q))
          u.match,
    ].take(q.isEmpty ? 12 : 30).toList();
    final teams = <int, (Team, String)>{};
    if (q.isNotEmpty && !widget.pickMatch) {
      for (final u in all) {
        for (final t in [u.match.home, u.match.away]) {
          if (fold(t.name).contains(q)) teams[t.id] = (t, u.match.competition);
        }
      }
    }
    return VPage(
      children: [
        VTopBar(widget.pickMatch ? 'Choisir un match' : 'Rechercher'),
        const SizedBox(height: 6),
        TextField(
          autofocus: true,
          style: V.t(15),
          decoration: InputDecoration(
            hintText: 'Équipe, match ou championnat',
            hintStyle: V.t(14, color: V.mu2),
            prefixIcon: const Padding(
              padding: EdgeInsets.all(12),
              child: VIc(VIcon.search, color: V.mu),
            ),
            filled: true,
            fillColor: V.s1,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(14),
              borderSide: const BorderSide(color: V.iconBorder),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(14),
              borderSide: const BorderSide(color: V.iconBorder),
            ),
          ),
          onChanged: (v) => setState(() => query = v),
        ),
        if (upcoming == null)
          const Padding(
            padding: EdgeInsets.only(top: 40),
            child: Center(child: CircularProgressIndicator()),
          )
        else if (matches.isEmpty && teams.isEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 24),
            child: Text(
              'Aucun match à venir pour « $query ».',
              textAlign: TextAlign.center,
              style: V.mu_(13),
            ),
          )
        else ...[
          if (teams.isNotEmpty)
            VCard(
              child: VList(
                children: [
                  for (final (t, comp) in teams.values.take(4))
                    GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => TeamScreen(teamId: t.id, name: t.name, competition: comp),
                        ),
                      ),
                      child: Row(
                        children: [
                          const VIc(VIcon.shield, size: 17, color: V.vi2),
                          const SizedBox(width: 10),
                          Expanded(child: Text(t.name, style: V.b())),
                          Text(competitionName(comp), style: V.mu_()),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          if (matches.isNotEmpty)
            VCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  VKicker(q.isEmpty ? 'Prochains matchs' : 'Matchs'),
                  VList(
                    children: [
                      for (final m in matches)
                        GestureDetector(
                          behavior: HitTestBehavior.opaque,
                          onTap: () => widget.pickMatch
                              ? Navigator.of(context).pop(m)
                              : Navigator.of(context)
                                    .push(MaterialPageRoute(builder: (_) => MatchScreen(matchId: m.id))),
                          child: Row(
                            children: [
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text('${m.home.name} – ${m.away.name}', style: V.b()),
                                    Text(
                                      '${shortDate(m.date)} · ${m.when} · ${competitionName(m.competition)}',
                                      style: V.mu_(),
                                    ),
                                  ],
                                ),
                              ),
                              const RotatedBox(
                                quarterTurns: 2,
                                child: VIc(VIcon.back, size: 16, color: V.mu2),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                ],
              ),
            ),
        ],
      ],
    );
  }
}
