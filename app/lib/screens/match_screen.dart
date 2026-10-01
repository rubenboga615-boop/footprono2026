import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';

class MatchData {
  MatchData(this.match, this.prediction, this.offers, this.analysis);
  final MatchInfo match;
  final Prediction? prediction;
  final List<Offer> offers;

  /// Faits (forme, confrontations, moyennes) : Premium seulement.
  final Json? analysis;
}

class MatchScreen extends StatelessWidget {
  const MatchScreen({super.key, required this.matchId});
  final int matchId;

  Future<MatchData> _load(AppState state) async {
    final api = state.api;
    final match = MatchInfo(await api.get('/matches/$matchId') as Json);
    Prediction? prediction;
    try {
      prediction = Prediction(await api.get('/matches/$matchId/prediction') as Json);
    } on ApiException catch (e) {
      if (e.status != 404) rethrow;
    }
    final offers = [for (final o in await api.get('/matches/$matchId/offer') as List) Offer(o as Json)];
    Json? analysis;
    if (state.premium) {
      try {
        analysis = await api.get('/matches/$matchId/analysis') as Json;
      } on ApiException catch (e) {
        if (e.status != 403 && e.status != 404) rethrow;
      }
    }
    return MatchData(match, prediction, offers, analysis);
  }

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<MatchData>(
          load: () => _load(state),
          builder: (context, data, reload) => _MatchView(data: data, reload: reload),
        ),
      ),
    );
  }
}

class _MatchView extends StatefulWidget {
  const _MatchView({required this.data, required this.reload});
  final MatchData data;
  final Future<void> Function() reload;

  @override
  State<_MatchView> createState() => _MatchViewState();
}

class _MatchViewState extends State<_MatchView> {
  int tab = 0;

  @override
  Widget build(BuildContext context) {
    final d = widget.data;
    final m = d.match;
    final content = switch (tab) {
      0 => _probabilities(d),
      1 => _odds(context, d),
      _ => _analysis(d),
    };
    return RefreshIndicator(
      onRefresh: widget.reload,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 32),
        children: [
          Row(
            children: [
              SquareButton(
                icon: Icons.arrow_back_rounded,
                tooltip: 'Retour',
                onTap: () => Navigator.of(context).maybePop(),
              ),
              Expanded(
                child: Column(
                  children: [
                    Text(
                      competitionName(m.competition),
                      style: Fp.body(13, color: Fp.text2, weight: FontWeight.w600),
                    ),
                    Text(
                      longDate(m.date),
                      style: Fp.body(13, color: Fp.text2, weight: FontWeight.w600),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 44),
            ],
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              Expanded(child: _bigTeam(m.home)),
              Column(
                children: [
                  Text(
                    m.score ?? 'VS',
                    style: m.score != null
                        ? Fp.title(26)
                        : Fp.body(15, color: Fp.text4, weight: FontWeight.w700),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    m.when,
                    style: Fp.body(12, color: m.isLive ? Fp.win : Fp.text2, weight: FontWeight.w600),
                  ),
                ],
              ),
              Expanded(child: _bigTeam(m.away)),
            ],
          ),
          const SizedBox(height: 18),
          SegmentTabs(
            labels: const ['Probabilités', 'Cotes', 'Analyse'],
            selected: tab,
            onSelected: (i) => setState(() => tab = i),
          ),
          const SizedBox(height: 16),
          ...content,
        ],
      ),
    );
  }

  Widget _bigTeam(Team t) => Column(
    children: [
      TeamCircle(t.code, size: 60),
      const SizedBox(height: 8),
      Text(
        t.name,
        textAlign: TextAlign.center,
        maxLines: 2,
        style: Fp.body(15, weight: FontWeight.w700),
      ),
    ],
  );

  // --- Probabilités -----------------------------------------------------------

  List<Widget> _probabilities(MatchData d) {
    final p = d.prediction;
    final m = d.match;
    if (p == null) {
      return const [
        EmptyState('Le moteur n\'a pas encore calculé ce match.', icon: Icons.hourglass_empty_rounded),
      ];
    }
    final byMarket = <String, List<Prob>>{};
    for (final s in p.markets) {
      byMarket.putIfAbsent(s.market, () => []).add(s);
    }
    for (final list in byMarket.values) {
      list.sort((a, b) => compareSelections(a.line, a.selection, b.line, b.selection));
    }
    final offers = {for (final o in d.offers) o.key: o};
    Prob? find(String sel) => byMarket['1X2']?.where((x) => x.selection == sel).firstOrNull;
    final home = find('home'), draw = find('draw'), away = find('away');
    final best = [
      home,
      draw,
      away,
    ].whereType<Prob>().fold<double>(0, (a, b) => b.probability > a ? b.probability : a);
    final scores = [...?byMarket['CS']]..sort((a, b) => b.probability.compareTo(a.probability));

    Widget outcomeTile(String label, Prob? x) {
      final offer = x == null ? null : offers[x.key];
      return Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            StatTile(
              label,
              x == null ? '—' : percent(x.probability),
              center: true,
              valueSize: 20,
              valueColor: x != null && x.probability == best ? Fp.accentLight : Fp.text,
            ),
            if (offer != null) ...[
              const SizedBox(height: 6),
              OddsButton(match: m, offer: offer, expand: true),
            ],
          ],
        ),
      );
    }

    return [
      GlassCard.section(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Résultat du match', style: Fp.title(15, weight: FontWeight.w600)),
            const SizedBox(height: 12),
            if (home != null && draw != null && away != null)
              OutcomeBar(home.probability, draw.probability, away.probability),
            const SizedBox(height: 12),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                outcomeTile(m.home.name, home),
                const SizedBox(width: 8),
                outcomeTile('Nul', draw),
                const SizedBox(width: 8),
                outcomeTile(m.away.name, away),
              ],
            ),
            const SizedBox(height: 10),
            KeyValue('Buts attendus', '${decimal(p.xgHome)} - ${decimal(p.xgAway)}'),
            if (scores.isNotEmpty) ...[
              const SizedBox(height: 14),
              Text('Scores les plus probables', style: Fp.title(15, weight: FontWeight.w600)),
              const SizedBox(height: 12),
              GridView.count(
                crossAxisCount: 3,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                mainAxisSpacing: 8,
                crossAxisSpacing: 8,
                childAspectRatio: 1.6,
                children: [
                  for (final (i, sc) in scores.where((x) => x.selection != 'other').take(6).indexed)
                    Container(
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: i == 0 ? Fp.accentSoft : Fp.fill,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: i == 0 ? Fp.accentLine : Colors.transparent),
                      ),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(sc.selection, style: Fp.title(17)),
                          Text(percent(sc.probability), style: Fp.body(12, color: Fp.text2)),
                        ],
                      ),
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
      for (final g in marketGroups) ..._group(g, byMarket, offers, m),
      if (p.lockedMarkets.isNotEmpty) ...[
        const SizedBox(height: 12),
        PremiumLock(
          text:
              '${p.lockedMarkets.length} autres marchés (handicaps, mi-temps, scores exacts, '
              'corners, cartons, tirs…) sont calculés pour ce match. Ils sont inclus dans Premium.',
        ),
      ],
      const SizedBox(height: 16),
      Text(
        'Probabilités du moteur ${p.engineVersion}, calculées le '
        '${p.createdAt != null ? dateTime(p.createdAt!) : '—'}. Elles ne tiennent pas compte des cotes '
        'des bookmakers.',
        style: Fp.body(12, color: Fp.text3, height: 1.4),
      ),
    ];
  }

  List<Widget> _group(
    MarketGroup g,
    Map<String, List<Prob>> byMarket,
    Map<String, Offer> offers,
    MatchInfo m,
  ) {
    final markets = g.markets.where((k) => k != '1X2' && k != 'CS' && byMarket.containsKey(k)).toList();
    if (markets.isEmpty) return const [];
    return [
      SectionTitle(g.title),
      for (final k in markets) _MarketCard(market: k, probs: byMarket[k]!, offers: offers, match: m),
    ];
  }

  List<Widget> _odds(BuildContext context, MatchData d) {
    final state = context.watch<AppState>();
    final m = d.match;
    final byMarket = <String, List<Offer>>{};
    for (final o in d.offers) {
      byMarket.putIfAbsent(o.market, () => []).add(o);
    }
    for (final list in byMarket.values) {
      list.sort((a, b) => compareSelections(a.line, a.selection, b.line, b.selection));
    }
    final order = [for (final g in marketGroups) ...g.markets];
    int rank(String k) => order.contains(k) ? order.indexOf(k) : 999;
    final markets = byMarket.keys.toList()..sort((a, b) => rank(a).compareTo(rank(b)));
    final newest = d.offers
        .map((o) => o.fetchedAt)
        .whereType<DateTime>()
        .fold<DateTime?>(null, (a, b) => a == null || b.isAfter(a) ? b : a);
    return [
      Text(
        'Cotes réelles relevées chez 1xBet (Bet365 en secours)'
        '${newest != null ? ', dernier relevé le ${dateTime(newest)}' : ''}. Paris en argent fictif. '
        'La probabilité du moteur est une information : elle n\'annonce pas de « bon coup ».',
        style: Fp.body(12, color: Fp.text3, height: 1.4),
      ),
      const SizedBox(height: 8),
      if (d.offers.isEmpty)
        const EmptyState(
          'Aucune cote récente pour ce match : il n\'est pas jouable pour l\'instant.',
          icon: Icons.money_off_rounded,
        ),
      for (final k in markets) ...[
        SectionTitle(marketTitle(k, home: m.home.name, away: m.away.name)),
        GlassCard(
          child: Column(
            children: [
              for (final (i, o) in byMarket[k]!.indexed) ...[
                if (i > 0) const Divider(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            selectionLabel(
                              o.market,
                              o.line,
                              o.selection,
                              home: m.home.name,
                              away: m.away.name,
                            ),
                            style: Fp.body(14, weight: FontWeight.w700),
                          ),
                          if (o.modelProbability != null)
                            Text(
                              'Moteur ${percent(o.modelProbability!)} · cote juste ${decimal(1 / o.modelProbability!)}',
                              style: Fp.body(12, color: Fp.text2),
                            ),
                        ],
                      ),
                    ),
                    OddsButton(match: m, offer: o),
                  ],
                ),
              ],
            ],
          ),
        ),
      ],
      if (!state.premium) ...[
        const SizedBox(height: 16),
        const PremiumLock(
          text:
              'Version gratuite : 1X2, plus/moins de buts et les deux marquent. '
              'Handicaps, double chance, mi-temps, corners… avec Premium.',
        ),
      ],
    ];
  }

  List<Widget> _analysis(MatchData d) {
    final p = d.prediction;
    final m = d.match;
    if (!context.read<AppState>().premium) {
      return const [
        PremiumLock(
          text:
              'L\'analyse détaillée (forme, confrontations, moyennes de la saison, classement, enjeu, '
              'corners, cartons et tirs attendus) est incluse dans Premium.',
        ),
      ];
    }
    final facts = d.analysis == null ? const <Widget>[] : _facts(d.analysis!, m);
    if (p == null || p.counts == null || p.context == null) {
      if (facts.isEmpty) {
        return const [
          EmptyState('Pas encore d\'analyse pour ce match.', icon: Icons.hourglass_empty_rounded),
        ];
      }
      return [
        ...facts,
        const SizedBox(height: 12),
        Text(
          'Les estimations du moteur apparaîtront une fois le match prédit.',
          style: Fp.body(12, color: Fp.text3),
        ),
      ];
    }
    final ctx = p.context!;
    final counts = p.counts!;
    List<double>? pair(String k) => (ctx[k] as List?)?.map((v) => (v as num).toDouble()).toList();
    final rank = pair('rank'), points = pair('points'), rest = pair('rest');
    final form = pair('form'), luck = pair('luck');
    final dead = pair('dead'), top = pair('fight_top'), bottom = pair('fight_bottom');

    String stakes(int i) {
      final out = <String>[];
      if ((dead?[i] ?? 0) > 0.5) out.add('plus rien à jouer');
      if ((top?[i] ?? 0) > 0.5) out.add('course au haut du classement');
      if ((bottom?[i] ?? 0) > 0.5) out.add('lutte pour le maintien');
      return out.isEmpty ? 'rien de particulier' : out.join(', ');
    }

    String signed(double v) => '${v > 0 ? '+' : ''}${decimal(v)}';

    const statNames = {
      'corners': 'Corners',
      'shots': 'Tirs',
      'shots_on_target': 'Tirs cadrés',
      'cards': 'Cartons',
      'yellow_cards': 'Cartons jaunes',
      'red_cards': 'Cartons rouges',
    };

    return [
      ...facts,
      if (facts.isNotEmpty) const SizedBox(height: 12),
      GlassCard.section(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Situation', style: Fp.title(15, weight: FontWeight.w600)),
            const SizedBox(height: 8),
            _TwoSided('Buts attendus', p.xgHome, p.xgAway, format: decimal),
            if (rank != null) _TwoSided.text('Classement', '${rank[0].round()}e', '${rank[1].round()}e'),
            if (points != null) _TwoSided.text('Points', '${points[0].round()}', '${points[1].round()}'),
            if (rest != null)
              _TwoSided.text(
                'Jours de repos',
                '${(rest[0] * 7 + 7).round()}${rest[0] >= 1 ? '+' : ''}',
                '${(rest[1] * 7 + 7).round()}${rest[1] >= 1 ? '+' : ''}',
              ),
            if (form != null)
              _TwoSided.text('Forme (écart de buts récent)', signed(form[0]), signed(form[1])),
            if (luck != null) _TwoSided.text('Réussite récente', signed(luck[0]), signed(luck[1])),
          ],
        ),
      ),
      const SizedBox(height: 12),
      GlassCard.section(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Enjeu', style: Fp.title(15, weight: FontWeight.w600)),
            const SizedBox(height: 6),
            KeyValue(m.home.name, stakes(0)),
            KeyValue(m.away.name, stakes(1)),
          ],
        ),
      ),
      const SizedBox(height: 12),
      GlassCard.section(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('Moyennes attendues', style: Fp.title(15, weight: FontWeight.w600)),
                ),
                Text('pour ce match', style: Fp.body(12, color: Fp.text3)),
              ],
            ),
            const SizedBox(height: 8),
            for (final e in statNames.entries)
              if (counts[e.key] is Map)
                _TwoSided(
                  e.value,
                  ((counts[e.key] as Map)['mean_home'] as num).toDouble(),
                  ((counts[e.key] as Map)['mean_away'] as num).toDouble(),
                  format: decimal,
                ),
            if ((counts['cards'] as Map?)?['referee_factor'] != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  'Arbitre : ${decimal((counts['cards'] as Map)['referee_factor'])} × la moyenne de cartons.',
                  style: Fp.body(12, color: Fp.text3),
                ),
              ),
          ],
        ),
      ),
      const SizedBox(height: 14),
      Text(
        'Moyennes du moteur pour ce match, calculées avec les seuls matchs déjà joués.',
        style: Fp.body(12, color: Fp.text3, height: 1.4),
      ),
    ];
  }

  /// Faits : forme sur 5 matchs, moyennes de la saison, confrontations directes.
  List<Widget> _facts(Json a, MatchInfo m) {
    final form = a['form'] as Json;
    final season = a['season'] as Json;
    final h2h = (a['head_to_head'] as List).cast<Json>();
    Widget formRow(String name, List results) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Expanded(
            child: Text(name, style: Fp.body(15, weight: FontWeight.w600)),
          ),
          for (final f in results.reversed.cast<Json>()) ...[
            const SizedBox(width: 6),
            Tooltip(
              message: '${f['venue'] == 'home' ? 'contre' : 'chez'} ${f['opponent']} : ${f['score']}',
              child: Container(
                width: 28,
                height: 28,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: switch (f['result']) {
                    'W' => Fp.win,
                    'L' => Fp.loss,
                    _ => const Color(0x8CF4F2F8),
                  },
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(switch (f['result']) {
                  'W' => 'G',
                  'L' => 'P',
                  _ => 'N',
                }, style: Fp.body(13, weight: FontWeight.w700, color: const Color(0xFF0B0A10))),
              ),
            ),
          ],
        ],
      ),
    );
    final hs = season['home'] as Json, as_ = season['away'] as Json;
    double? v(Json j, String k) => (j[k] as num?)?.toDouble();
    const rows = {
      'goals_for': 'Buts marqués',
      'goals_against': 'Buts encaissés',
      'xg_for': 'xG (Understat)',
      'shots_on_target': 'Tirs cadrés',
      'corners': 'Corners',
    };
    return [
      GlassCard.section(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Forme · 5 derniers matchs', style: Fp.title(15, weight: FontWeight.w600)),
            const SizedBox(height: 6),
            formRow(m.home.name, form['home'] as List),
            formRow(m.away.name, form['away'] as List),
          ],
        ),
      ),
      const SizedBox(height: 12),
      if ((hs['matches'] as int) > 0 || (as_['matches'] as int) > 0) ...[
        GlassCard.section(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text('Moyennes cette saison', style: Fp.title(15, weight: FontWeight.w600)),
                  ),
                  Text('par match', style: Fp.body(12, color: Fp.text3)),
                ],
              ),
              const SizedBox(height: 6),
              for (final e in rows.entries)
                if (v(hs, e.key) != null && v(as_, e.key) != null)
                  _TwoSided(e.value, v(hs, e.key)!, v(as_, e.key)!, format: decimal),
              const SizedBox(height: 4),
              Text(
                '${hs['matches']} et ${as_['matches']} matchs de championnat joués avant celui-ci.',
                style: Fp.body(12, color: Fp.text3),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
      ],
      GlassCard.section(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Confrontations', style: Fp.title(15, weight: FontWeight.w600)),
            const SizedBox(height: 6),
            if (h2h.isEmpty)
              Text(
                'Aucune confrontation dans notre historique (depuis 2016).',
                style: Fp.body(13, color: Fp.text2),
              )
            else
              for (final (i, c) in h2h.indexed) ...[
                if (i > 0) const Divider(),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 82,
                        child: Text(
                          numericDate(DateTime.parse(c['date'] as String)),
                          style: Fp.body(12, color: Fp.text2),
                        ),
                      ),
                      Expanded(
                        child: Text(
                          '${c['home']} ${c['score']} ${c['away']}',
                          style: Fp.body(14, weight: FontWeight.w600),
                        ),
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

/// Ligne « domicile · libellé · extérieur », avec barres proportionnelles.
class _TwoSided extends StatelessWidget {
  const _TwoSided(
    this.label,
    double this.home,
    double this.away, {
    required String Function(Object?) this.format,
  }) : homeText = null,
       awayText = null;
  const _TwoSided.text(this.label, String this.homeText, String this.awayText)
    : home = null,
      away = null,
      format = null;
  final String label;
  final double? home, away;
  final String? homeText, awayText;
  final String Function(Object?)? format;

  @override
  Widget build(BuildContext context) {
    final h = homeText ?? format!(home);
    final a = awayText ?? format!(away);
    final bars = home != null && away != null && home! + away! > 0;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Column(
        children: [
          Row(
            children: [
              Text(h, style: Fp.title(15, color: Fp.accentLight)),
              Expanded(
                child: Text(
                  label,
                  textAlign: TextAlign.center,
                  style: Fp.body(13, color: Fp.textSoft),
                ),
              ),
              Text(a, style: Fp.title(15)),
            ],
          ),
          if (bars) ...[
            const SizedBox(height: 6),
            Row(
              children: [
                Expanded(
                  flex: (home! * 100).round().clamp(1, 100000),
                  child: const SizedBox(
                    height: 6,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: Fp.accentBar,
                        borderRadius: BorderRadius.all(Radius.circular(6)),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 6),
                Expanded(
                  flex: (away! * 100).round().clamp(1, 100000),
                  child: const SizedBox(
                    height: 6,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: Color(0x40FFFFFF),
                        borderRadius: BorderRadius.all(Radius.circular(6)),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _MarketCard extends StatefulWidget {
  const _MarketCard({required this.market, required this.probs, required this.offers, required this.match});
  final String market;
  final List<Prob> probs;
  final Map<String, Offer> offers;
  final MatchInfo match;

  @override
  State<_MarketCard> createState() => _MarketCardState();
}

class _MarketCardState extends State<_MarketCard> {
  bool all = false;

  /// Lignes montrées d'abord : les 3 plus équilibrées (ordre croissant conservé).
  List<Prob> _visible() {
    final probs = widget.probs;
    final lines = <String>{for (final p in probs) p.line}.toList();
    if (lines.length <= 3 || all) return probs;
    double balance(String line) {
      final ps = probs.where((p) => p.line == line).map((p) => p.probability);
      return ps.map((x) => (x - 1 / ps.length).abs()).fold(0.0, (a, b) => a + b);
    }

    final keep = ([...lines]..sort((a, b) => balance(a).compareTo(balance(b)))).take(3).toSet();
    return probs.where((p) => keep.contains(p.line)).toList();
  }

  @override
  Widget build(BuildContext context) {
    final m = widget.match;
    final visible = _visible();
    final hidden = widget.probs.length - visible.length;
    return GlassCard(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            marketTitle(widget.market, home: m.home.name, away: m.away.name),
            style: Fp.title(15, weight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          for (final s in visible)
            _ProbRow(
              label: selectionLabel(widget.market, s.line, s.selection, home: m.home.name, away: m.away.name),
              prob: s,
              offer: widget.offers[s.key],
              match: m,
            ),
          if (hidden > 0 || all)
            TextButton(
              onPressed: () => setState(() => all = !all),
              child: Text(all ? 'Réduire' : 'Voir les $hidden autres'),
            ),
        ],
      ),
    );
  }
}

class _ProbRow extends StatelessWidget {
  const _ProbRow({required this.label, required this.prob, required this.match, this.offer});
  final String label;
  final Prob prob;
  final Offer? offer;
  final MatchInfo match;

  @override
  Widget build(BuildContext context) {
    final push = prob.push > 0.001 ? ' · remboursé ${percent(prob.push)}' : '';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(label, style: Fp.body(14, color: Fp.textStrong)),
                    ),
                    const SizedBox(width: 8),
                    Text(percent(prob.probability), style: Fp.body(14, weight: FontWeight.w700)),
                  ],
                ),
                const SizedBox(height: 8),
                ProbBar(prob.probability, height: 6),
                if (prob.fairOdds != null || push.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    'Cote juste ${prob.fairOdds != null ? decimal(prob.fairOdds) : '—'}$push',
                    style: Fp.body(11, color: Fp.text3),
                  ),
                ],
              ],
            ),
          ),
          if (offer != null) ...[const SizedBox(width: 12), OddsButton(match: match, offer: offer!)],
        ],
      ),
    );
  }
}

/// Cote réelle jouable : ajoute ou retire la sélection du coupon.
class OddsButton extends StatelessWidget {
  const OddsButton({super.key, required this.match, required this.offer, this.expand = false});
  final MatchInfo match;
  final Offer offer;
  final bool expand;

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final on = state.inCoupon(match.id, offer.key);
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(12),
      side: BorderSide(color: on ? Fp.accentLine : Fp.line),
    );
    return Material(
      color: on ? Fp.accent : Fp.fill,
      shape: shape,
      child: InkWell(
        customBorder: shape,
        onTap: () => showMessage(state.toggleCoupon(match, offer)),
        child: Container(
          width: expand ? double.infinity : null,
          constraints: const BoxConstraints(minWidth: 58),
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
          child: Column(
            children: [
              Text(odds(offer.odds), style: Fp.title(15, color: Colors.white)),
              Text(offer.bookmaker, style: Fp.body(10, color: on ? Colors.white70 : Fp.text3)),
            ],
          ),
        ),
      ),
    );
  }
}
