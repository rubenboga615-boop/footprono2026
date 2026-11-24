import 'dart:async';

import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/client.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/visage.dart';
import '../widgets/common.dart';
import '../widgets/live_refresh.dart';
import '../widgets/maquette.dart';
import 'premium_screen.dart' show PremiumCard;
import 'live_tab.dart';
import 'odds_history.dart';
import 'referee_screen.dart';
import 'team_screen.dart';

/// Cotes non mises à jour par la source depuis plus longtemps : signalées comme anciennes.
const staleOdds = Duration(days: 2);

class MatchData {
  MatchData(this.match, this.prediction, this.offers, this.analysis, [this.picks, this.locked = false]);
  final MatchInfo match;
  final Prediction? prediction;
  final List<Offer> offers;

  /// Faits (forme, confrontations, moyennes) : Premium seulement.
  final Json? analysis;

  /// « Les choix du moteur » : une sélection par profil (Sûr gratuit, les autres Premium).
  final Json? picks;

  /// Le serveur a refusé l'analyse (Premium terminé ou retiré) : on montre le cadenas,
  /// pas « pas encore d'analyse ».
  final bool locked;

  /// Même écran, le match mis à jour par un relevé du direct.
  MatchData withMatch(MatchInfo m) =>
      identical(m, match) ? this : MatchData(m, prediction, offers, analysis, picks, locked);
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
    // Le serveur fait foi : un Premium retiré depuis la dernière mise à jour du profil
    // est refusé ici, et le profil est relu pour mettre l'application à jour.
    var locked = !state.premium || (prediction != null && prediction.plan != 'premium');
    if (!locked) {
      try {
        analysis = await api.get('/matches/$matchId/analysis') as Json;
      } on ApiException catch (e) {
        if (e.premiumRequired || e.status == 403) {
          locked = true;
        } else if (e.status != 404) {
          rethrow;
        }
      }
    }
    if (locked && state.premium) unawaited(state.refreshMe().catchError((_) {}));
    Json? picks;
    try {
      picks = (await api.get('/matches/$matchId/picks') as Json)['picks'] as Json;
    } on ApiException {
      // Choix indisponibles : l'écran garde toutes les probabilités.
    }
    return MatchData(match, prediction, offers, analysis, picks, locked);
  }

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<MatchData>(
          load: () => _load(state),
          // Pendant le match : score, minute et statut mis à jour par chaque relevé du
          // direct, sans recharger prévision, cotes, analyse ni choix du moteur (retour du
          // 12/11/2026 : ces quatre requêtes partaient à chaque relevé).
          builder: (context, data, reload) => ValueListenableBuilder<LiveFeed?>(
            valueListenable: state.liveFeed,
            builder: (context, feed, _) {
              final d = data.withMatch(data.match.withFeed(feed));
              return LiveWatch(
                active: d.match.liveSoon,
                child: _MatchView(data: d, reload: reload),
              );
            },
          ),
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
  // Match commencé : onglet « En direct » (« Résumé » une fois fini) en premier, ouvert
  // d'office pendant le match (maquette D2, plan du 10/11/2026, étape 7).
  late int tab = widget.data.match.isLive ? 0 : (widget.data.match.started ? 1 : 0);

  /// Buteurs sous le score (maquette 8), tirés du relevé lu par l'onglet du direct.
  String? scorers;

  void _setScorers(List<Json> events) {
    final line = scorerLine(events);
    if (mounted && line != scorers) setState(() => scorers = line);
  }

  @override
  void didUpdateWidget(_MatchView old) {
    super.didUpdateWidget(old);
    // Coup d'envoi pendant que l'écran est ouvert : l'onglet « En direct » s'ajoute en tête
    // et s'ouvre (retour du fondateur du 12/11/2026).
    final was = old.data.match, now = widget.data.match;
    if (!was.started && now.started) {
      tab = now.isLive ? 0 : tab + 1;
    } else if (!was.isLive && now.isLive && !_picked) {
      tab = 0;
    }
  }

  /// Onglet choisi par le joueur : plus de changement d'office.
  bool _picked = false;

  /// Chances d'avant le match (1, N, 2).
  (double, double, double)? _before(MatchData d) {
    double? p(String sel) =>
        d.prediction?.markets.where((x) => x.market == '1X2' && x.selection == sel).firstOrNull?.probability;
    final h = p('home'), n = p('draw'), a = p('away');
    return h == null || n == null || a == null ? null : (h, n, a);
  }

  @override
  Widget build(BuildContext context) {
    final d = widget.data;
    final m = d.match;
    final live = m.started;
    final index = live ? tab - 1 : tab;
    final content = live && tab == 0
        ? [LiveTab(match: m, before: _before(d), onEvents: _setScorers)]
        : switch (index) {
            0 => _probabilities(d),
            1 => _odds(context, d),
            2 => _analysis(d),
            // Maquette 7 : « Compos » avant le match (données en général une heure avant).
            _ => [LiveTab(match: m, section: 2)],
          };
    return RefreshIndicator(
      onRefresh: widget.reload,
      child: ListView(
        padding: pagePadding(context, 16, 32, maxWidth: 1080),
        children: [
          // Maquettes 7 et 8 du nouveau visage : en-tête unique.
          Row(
            children: [
              BackChevron(onTap: () => Navigator.of(context).maybePop()),
              Expanded(
                child: m.isLive
                    ? Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const VDot(),
                          const SizedBox(width: 6),
                          Text(
                            'EN DIRECT${m.clock.isEmpty ? '' : ' · ${m.clock}'}',
                            style: V.t(11.5, w: FontWeight.w800, color: V.mint),
                          ),
                        ],
                      )
                    // Maquette 9 : sur les autres onglets, le nom du match à la place de la date.
                    : !m.started && tab != 0
                    ? Text(
                        '${m.home.name} – ${m.away.name}',
                        textAlign: TextAlign.center,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: V.b(15.5),
                      )
                    : Text(
                        '${competitionName(m.competition)} · ${_when(m)}',
                        textAlign: TextAlign.center,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: V.mu_(),
                      ),
              ),
              Tooltip(
                message: 'Suivre les équipes',
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () => _follow(context, m),
                  child: Padding(
                    padding: const EdgeInsets.all(8),
                    child: VIc(
                      VIcon.star,
                      size: 19,
                      color: context.watch<AppState>().followed.intersection({m.home.id, m.away.id}).isEmpty
                          ? V.mu
                          : V.amber,
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (!m.started && tab != 0)
            const SizedBox.shrink()
          else if (m.started)
            Row(
              children: [
                Expanded(child: _teamName(m.home)),
                Text(m.score?.replaceAll(' - ', ' – ') ?? '–', style: V.big()),
                Expanded(child: _teamName(m.away)),
              ],
            )
          else
            Row(
              children: [
                Expanded(child: _bigTeam(m.home, Fp.accentLight)),
                Text('vs', style: V.t(12.5, color: V.mu)),
                Expanded(child: _bigTeam(m.away, Fp.lossText)),
              ],
            ),
          if (m.started && scorers != null)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                scorers!,
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: V.mu_(12),
              ),
            ),
          if (m.started && !m.isLive)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(m.when, textAlign: TextAlign.center, style: V.mu_()),
            ),
          if (m.isLive && m.liveUpdatedAt != null) Center(child: UpdatedAgo(m.liveUpdatedAt)),
          if (m.awaitingKickoff)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                '● Coup d\'envoi imminent',
                textAlign: TextAlign.center,
                style: V.t(12.5, w: FontWeight.w700, color: V.mint),
              ),
            ),
          if (m.kickoffDelayed)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                'Coup d\'envoi retardé (heure à confirmer)',
                textAlign: TextAlign.center,
                style: V.t(12.5, w: FontWeight.w700, color: V.mu),
              ),
            ),
          // Chances 1-N-2 en grand (maquette 7), avant le match.
          if (!m.started && tab == 0)
            if (_before(d) case (final h, final n, final a)) ...[
              const SizedBox(height: 12),
              Row(
                children: [
                  for (final (p, c) in [(h, V.vi2), (n, V.mu), (a, V.sky)])
                    Expanded(
                      child: Text(percent(p), textAlign: TextAlign.center, style: V.big(c)),
                    ),
                ],
              ),
              VBar3(h, n, a),
              if (unmeasuredNote(m.competition) case final note?)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    note,
                    textAlign: TextAlign.center,
                    style: V.t(12, color: V.amber),
                  ),
                ),
            ],
          if (m.referee != null && !m.started && tab == 0)
            Center(
              child: InkWell(
                borderRadius: BorderRadius.circular(8),
                onTap: () =>
                    Navigator.of(context)
                        .push(MaterialPageRoute(builder: (_) => RefereeScreen(name: m.referee!))),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
                  child: Text('Arbitre : ${m.referee}', style: V.mu_(12)),
                ),
              ),
            ),
          const SizedBox(height: 10),
          VTabs(
            items: [
              if (live) m.isLive || m.awaitingKickoff || m.kickoffDelayed ? 'En direct' : 'Résumé',
              'Chances',
              'Cotes',
              'Analyse',
              if (!live) 'Compos',
            ],
            selected: tab,
            onSelect: (i) => setState(() {
              tab = i;
              _picked = true;
            }),
          ),
          const SizedBox(height: 16),
          ...deskColumns(context, content),
        ],
      ),
    );
  }

  /// « ven. 20 nov. 20:00 ».
  static String _when(MatchInfo m) {
    final k = (m.kickoffAt ?? m.date).toLocal();
    final day = shortDate(k);
    final text = m.kickoffAt == null ? day : '$day ${hourMinute(k)}';
    return text[0].toLowerCase() + text.substring(1);
  }

  /// Étoile : suivre l'une ou l'autre équipe (filtre « Suivis » des matchs).
  Future<void> _follow(BuildContext context, MatchInfo m) async {
    final state = context.read<AppState>();
    if (state.me == null) return;
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: V.s1,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Consumer<AppState>(
            builder: (ctx, st, _) => Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Suivre', style: V.b(16)),
                Text('Les matchs des équipes suivies sont dans « Suivis ».', style: V.mu_(12)),
                const SizedBox(height: 8),
                for (final t in [m.home, m.away])
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Row(
                      children: [
                        VTeamBadge(t.code),
                        const SizedBox(width: 10),
                        Expanded(child: Text(t.name, style: V.b())),
                        VSwitch(
                          value: st.followed.contains(t.id),
                          label: 'Suivre ${t.name}',
                          onChanged: (_) => guard(ctx, () => st.toggleFollow(t.id)),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// Nom d'une équipe au-dessus du score (maquette 8) ; un appui ouvre sa fiche.
  Widget _teamName(Team t) => GestureDetector(
    onTap: () => Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => TeamScreen(teamId: t.id, name: t.name),
      ),
    ),
    child: Text(t.name, textAlign: TextAlign.center, maxLines: 2, style: V.b(15)),
  );

  /// Toucher une équipe ouvre sa fiche.
  Widget _bigTeam(Team t, Color tint) => Tooltip(
    message: 'Fiche équipe',
    child: InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => TeamScreen(teamId: t.id, name: t.name),
        ),
      ),
      // Maquette 7 : rond de 44 avec les initiales, nom dessous ; un appui ouvre la fiche.
      child: Column(
        children: [
          VTeamBadge(t.code, size: 44),
          const SizedBox(height: 6),
          Text(t.name, textAlign: TextAlign.center, maxLines: 2, style: V.b()),
        ],
      ),
    ),
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
    final scores = [...?byMarket['CS']]..sort((a, b) => b.probability.compareTo(a.probability));

    return [
      // Match commencé (essai du 07/11/2026 : « score le plus probable 0-2 » à 1-0, 78e) :
      // les chances sont celles d'avant le match, et le choix du moteur n'est plus jouable.
      if (m.started) ...[_BeforeKickoff(m), const SizedBox(height: 12)],
      // Maquette 7 : chaque marché, ligne par ligne : moteur, cote, pastille, case de cote.
      VCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const VKicker('Résultat du match'),
            VList(
              children: [
                for (final (label, x) in [(m.home.name, home), ('Match nul', draw), (m.away.name, away)])
                  if (x != null) _ProbRow(label: label, prob: x, match: m, offer: offers[x.key]),
              ],
            ),
            if ((p.xgHome, p.xgAway) case (final double h, final double a))
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('Buts attendus : ${decimal(h)} - ${decimal(a)}', style: V.mu_(12)),
              ),
          ],
        ),
      ),
      // Les choix du moteur par profil, après le résultat du match.
      if (!m.started && d.picks != null) ...[
        const SizedBox(height: 12),
        _EnginePicks(picks: d.picks!, offers: offers, match: m),
      ],
      if (scores.isNotEmpty)
        VCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const VKicker('Scores les plus probables'),
              const SizedBox(height: 8),
              Row(
                children: [
                  for (final (i, sc) in scores.where((x) => x.selection != 'other').take(4).indexed) ...[
                    if (i > 0) const SizedBox(width: 6),
                    Expanded(
                      child: VCard2(
                        border: i == 0 ? V.vi : null,
                        child: Column(
                          children: [
                            Text(sc.selection, style: V.b(16)),
                            Text(percent(sc.probability), style: V.mu_()),
                          ],
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
      // Le premier groupe qui a des marchés est ouvert, les autres repliés.
      for (final (i, g) in marketGroups.where((g) => _shown(g, byMarket).isNotEmpty).indexed)
        ..._group(g, byMarket, offers, m, open: i == 0),
      if (p.lockedMarkets.isNotEmpty) ...[
        const SizedBox(height: 12),
        PremiumLock(
          text:
              '${p.lockedMarkets.length} autres marchés (handicaps, mi-temps, scores exacts, '
              'corners, cartons, tirs…) sont calculés pour ce match. Ils sont inclus dans Premium.',
        ),
      ],
      const SizedBox(height: 8),
      if (!m.started) Text('Touche une cote pour l\'ajouter au coupon.', style: V.mu_()),
      const SizedBox(height: 8),
      Text(
        'Probabilités calculées le ${p.createdAt != null ? dateTime(p.createdAt!) : '—'}. '
        'Elles ne tiennent pas compte des cotes des bookmakers.',
        style: Fp.body(12, color: Fp.text3, height: 1.4),
      ),
    ];
  }

  List<Widget> _group(
    MarketGroup g,
    Map<String, List<Prob>> byMarket,
    Map<String, Offer> offers,
    MatchInfo m, {
    bool open = false,
  }) {
    final markets = _shown(g, byMarket);
    if (markets.isEmpty) return const [];
    return [
      FoldSection(
        key: ValueKey('proba-${g.title}'),
        id: 'proba-${g.title}',
        title: g.title,
        count: _count(markets.length),
        initiallyOpen: open,
        children: [
          for (final k in markets) _MarketCard(market: k, probs: byMarket[k]!, offers: offers, match: m),
        ],
      ),
    ];
  }

  /// Marchés d'un groupe affichés en liste (1X2 et score exact sont en haut de page).
  static List<String> _shown(MarketGroup g, Map<String, List<Prob>> byMarket) =>
      g.markets.where((k) => k != '1X2' && k != 'CS' && byMarket.containsKey(k)).toList();

  static String _count(int n) => n > 1 ? '$n marchés' : '1 marché';

  /// Marchés cotés rangés par groupe (même ordre que l'onglet Probabilités).
  static List<(String, List<String>)> _oddsGroups(List<String> markets) {
    final out = <(String, List<String>)>[];
    final used = <String>{};
    for (final g in marketGroups) {
      final keys = [
        for (final k in markets)
          if (g.markets.contains(k)) k,
      ];
      used.addAll(keys);
      if (keys.isNotEmpty) out.add((g.title, keys));
    }
    final rest = [
      for (final k in markets)
        if (!used.contains(k)) k,
    ];
    if (rest.isNotEmpty) out.add(('Autres', rest));
    return out;
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
    DateTime? latest(Iterable<DateTime?> dates) =>
        dates.whereType<DateTime>().fold<DateTime?>(null, (a, b) => a == null || b.isAfter(a) ? b : a);
    final updated = latest(d.offers.map((o) => o.sourceUpdatedAt));
    final checked = latest(d.offers.map((o) => o.checkedAt ?? o.fetchedAt));
    final stale = updated != null && DateTime.now().difference(updated) > staleOdds;
    return [
      if (m.started) ...[_BeforeKickoff(m), const SizedBox(height: 12)],
      Text(
        'Cotes réelles de 1xBet (Bet365 en secours)'
        '${updated != null ? ', mises à jour le ${dateTime(updated.toLocal())} selon API-Football' : ''}'
        '${checked != null ? ', vérifiées le ${dateTime(checked.toLocal())}' : ''}. Paris en argent fictif. '
        'La probabilité du moteur est une information : elle n\'annonce pas de « bon coup ».',
        style: Fp.body(12, color: Fp.text3, height: 1.4),
      ),
      if (stale) ...[
        const SizedBox(height: 6),
        Text(
          'Attention : la source n\'a pas mis ces cotes à jour depuis plus de 2 jours. Elles peuvent '
          'différer de celles affichées aujourd\'hui chez le bookmaker.',
          style: Fp.body(12, color: Fp.warning, height: 1.4),
        ),
      ],
      const SizedBox(height: 8),
      if (d.offers.isEmpty)
        const EmptyState(
          'Aucune cote récente pour ce match : il n\'est pas jouable pour l\'instant.',
          icon: Icons.money_off_rounded,
        ),
      for (final (gi, (title, keys)) in _oddsGroups(markets).indexed)
        FoldSection(
          key: ValueKey('cotes-$title'),
          id: 'cotes-$title',
          title: title,
          count: _count(keys.length),
          initiallyOpen: gi == 0,
          children: [
            for (final k in keys) ...[
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
                                if (o.moved)
                                  InkWell(
                                    onTap: () => showOddsHistory(context, m, o),
                                    child: Padding(
                                      padding: const EdgeInsets.only(top: 2),
                                      child: Text(
                                        '${o.odds < o.openingOdds! ? '▼' : '▲'} ${odds(o.openingOdds)} → ${odds(o.odds)}'
                                        ' · historique',
                                        style: Fp.body(12, color: Fp.accentLight, weight: FontWeight.w600),
                                      ),
                                    ),
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
          ],
        ),
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
    if (d.locked || !context.read<AppState>().premium) {
      // Maquette validée le 07/11/2026 : aperçu flouté, puis le bouton d'abonnement. L'aperçu ne
      // montre que la structure (titres et barres grises) : aucun chiffre inventé.
      Widget bar(double w) => Container(
        width: w,
        height: 10,
        margin: const EdgeInsets.only(top: 6),
        decoration: BoxDecoration(color: const Color(0x22FFFFFF), borderRadius: BorderRadius.circular(5)),
      );
      return [
        ExcludeSemantics(
          child: ImageFiltered(
            imageFilter: ImageFilter.blur(sigmaX: 3.5, sigmaY: 3.5),
            child: MCard(
              margin: EdgeInsets.zero,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final t in const [
                    'Forme des 5 derniers matchs',
                    'Face-à-face',
                    'Moyennes de la saison',
                  ])
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(t, style: Fp.body(13.5, weight: FontWeight.w600)),
                          bar(220),
                          bar(160),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
        const PremiumCard(
          text:
              'Forme, face-à-face, moyennes de la saison, classement, enjeu, corners, cartons et tirs '
              'attendus.',
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

    // Résumé de 2 lignes en tête (rapport du 07/11/2026) : des faits, aucun avis.
    final summary = [
      if ((p.xgHome, p.xgAway) case (final double h, final double a))
        'Buts attendus par le moteur : ${m.home.name} ${decimal(h)}, ${m.away.name} ${decimal(a)} '
            '(${decimal(h + a)} au total).',
      if (rank != null && points != null)
        '${m.home.name} ${rank[0].round()}e (${points[0].round()} pts), '
            '${m.away.name} ${rank[1].round()}e (${points[1].round()} pts)'
            '${[stakes(0), stakes(1)].any((x) => x != 'rien de particulier') ? ' ; enjeu : ${m.home.name} ${stakes(0)}, ${m.away.name} ${stakes(1)}' : ''}.',
    ];

    return [
      ...facts,
      if (summary.isNotEmpty)
        VCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const VKicker('Ce que le moteur en retient'),
              const SizedBox(height: 6),
              Text(summary.join('\n'), style: V.t(12.5, color: V.mu).copyWith(height: 1.5)),
            ],
          ),
        ),
      const SizedBox(height: 12),
      VCard(
        top: 0,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const VKicker('Situation'),
            const SizedBox(height: 8),
            if ((p.xgHome, p.xgAway) case (final double h, final double a))
              _TwoSided('Buts attendus', h, a, format: decimal),
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
      VCard(
        top: 0,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const VKicker('Enjeu'),
            const SizedBox(height: 6),
            KeyValue(m.home.name, stakes(0)),
            KeyValue(m.away.name, stakes(1)),
          ],
        ),
      ),
      const SizedBox(height: 12),
      VCard(
        top: 0,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const VHead('Moyennes attendues pour ce match'),
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
          Expanded(child: Text(name, style: V.b())),
          for (final f in results.reversed.cast<Json>()) ...[
            const SizedBox(width: 5),
            Tooltip(
              message: '${f['venue'] == 'home' ? 'contre' : 'chez'} ${f['opponent']} : ${f['score']}',
              child: Builder(
                builder: (context) {
                  final (bg, fg, letter) = formColors(f['result']);
                  return Container(
                    width: 26,
                    height: 26,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(color: bg, shape: BoxShape.circle),
                    child: Text(
                      letter,
                      style: V.t(11, w: FontWeight.w700, color: fg),
                    ),
                  );
                },
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
      VCard(
        top: 0,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const VKicker('Forme (5 derniers)'),
            const SizedBox(height: 4),
            formRow(m.home.name, form['home'] as List),
            formRow(m.away.name, form['away'] as List),
          ],
        ),
      ),
      if ((hs['matches'] as int) > 0 || (as_['matches'] as int) > 0) ...[
        VCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const VKicker('Moyennes cette saison'),
              const SizedBox(height: 6),
              // Maquette 9 : un tableau, une colonne par équipe (chaque chiffre dit à qui il va).
              Table(
                columnWidths: const {0: FlexColumnWidth(2), 1: FlexColumnWidth(), 2: FlexColumnWidth()},
                border: const TableBorder(horizontalInside: BorderSide(color: V.line)),
                children: [
                  TableRow(
                    children: [
                      const SizedBox.shrink(),
                      for (final t in [m.home.name, m.away.name])
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 7),
                          child: Text(
                            t,
                            textAlign: TextAlign.right,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: V.t(11, w: FontWeight.w600, color: V.mu),
                          ),
                        ),
                    ],
                  ),
                  for (final e in rows.entries)
                    if (v(hs, e.key) != null && v(as_, e.key) != null)
                      TableRow(
                        children: [
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 7),
                            child: Text(e.value, style: V.t(12)),
                          ),
                          for (final x in [v(hs, e.key)!, v(as_, e.key)!])
                            Padding(
                              padding: const EdgeInsets.symmetric(vertical: 7),
                              child: Text(decimal(x), textAlign: TextAlign.right, style: V.b(12)),
                            ),
                        ],
                      ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                '${hs['matches']} et ${as_['matches']} matchs de championnat joués avant celui-ci.',
                style: V.mu_(),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
      ],
      VCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const VKicker('Confrontations'),
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
    return VCard(
      top: 0,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            VKicker(marketTitle(widget.market, home: m.home.name, away: m.away.name)),
            if (marketHelp(widget.market) case final help?) ...[
              const SizedBox(height: 4),
              Text(help, style: V.mu_()),
            ],
            VList(
              children: [
                for (final s in visible)
                  _ProbRow(
                    explain: explainSelection(
                      widget.market,
                      s.line,
                      s.selection,
                      home: m.home.name,
                      away: m.away.name,
                    ),
                    label: selectionLabel(
                      widget.market,
                      s.line,
                      s.selection,
                      home: m.home.name,
                      away: m.away.name,
                    ),
                    prob: s,
                    offer: widget.offers[s.key],
                    match: m,
                  ),
              ],
            ),
            if (hidden > 0 || all)
              Align(
                alignment: Alignment.centerLeft,
                child: VLink(
                  all ? 'Réduire' : 'Voir les $hidden autres',
                  onTap: () => setState(() => all = !all),
                ),
              ),
          ],
        ),
      ),
    ).withBottom(10);
  }
}

class _ProbRow extends StatelessWidget {
  const _ProbRow({required this.label, required this.prob, required this.match, this.offer, this.explain});
  final String label;
  final String? explain;
  final Prob prob;
  final Offer? offer;
  final MatchInfo match;

  @override
  Widget build(BuildContext context) {
    final push = prob.push > 0.001 ? ' · remboursé ${percent(prob.push)}' : '';
    final o = offer;
    final implied = o == null || o.odds <= 1 ? null : 1 / o.odds;
    // Maquette 7 : « Moins de 2,5 buts » / « moteur 59 % · cote 50 % », pastille, case de cote.
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: V.t(13.5)),
              Text(
                [
                      'moteur ${percent(prob.probability)}',
                      if (implied != null)
                        'cote ${percent(implied)}'
                      else if (prob.fairOdds != null)
                        'cote juste ${decimal(prob.fairOdds)}',
                    ].join(' · ') +
                    push,
                style: V.mu_(),
              ),
              if (explain != null) Text(explain!, style: V.mu_(11)),
            ],
          ),
        ),
        if (o != null && implied != null) ...[
          const SizedBox(width: 8),
          VGapChip(engine: prob.probability, implied: implied, nation: unmeasured(match.competition)),
          const SizedBox(width: 8),
          OddsButton(match: match, offer: o),
        ],
      ],
    );
  }
}

/// Ajoute (ou retire) une sélection. Si le coupon contient déjà une autre sélection du
/// même match, demande laquelle garder : deux sélections d'un même match sont liées et
/// leur cote combinée serait fausse.
Future<void> addToCoupon(BuildContext context, MatchInfo match, Offer offer) async {
  final state = context.read<AppState>();
  final other = state.sameMatch(match.id, offer.key);
  if (other != null) {
    String label(Offer o) =>
        '${fullLabel(o.market, o.line, o.selection, home: match.home.name, away: match.away.name)} '
        '(${odds(o.odds)})';
    final replace = await showModalBottomSheet<bool>(
      context: context,
      backgroundColor: Fp.background,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Déjà une sélection de ce match', style: Fp.title(17)),
              const SizedBox(height: 8),
              Text(
                'Ton coupon contient déjà « ${label(other.offer)} ». Deux sélections d\'un même match '
                'sont liées : leur cote combinée serait fausse. Laquelle gardes-tu ?',
                style: Fp.body(13, color: Fp.text2, height: 1.4),
              ),
              const SizedBox(height: 14),
              OutlinedButton(
                onPressed: () => Navigator.pop(context, false),
                child: Text('Garder : ${label(other.offer)}'),
              ),
              const SizedBox(height: 8),
              FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: Text('Remplacer par : ${label(offer)}'),
              ),
            ],
          ),
        ),
      ),
    );
    if (replace != true) return;
  }
  showMessage(state.toggleCoupon(match, offer));
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
    if (match.started) {
      // Cote d'avant le match : plus jouable une fois le match commencé.
      return Container(
        width: expand ? double.infinity : null,
        // 44 px au moins pour le doigt (étape A du nouveau visage ; avant : 35 px).
        constraints: const BoxConstraints(minWidth: 52, minHeight: 44),
        alignment: Alignment.center,
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
        decoration: BoxDecoration(color: V.s2, borderRadius: BorderRadius.circular(12)),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              odds(offer.odds),
              style: Fp.body(15, weight: FontWeight.w700, color: Fp.textSoft),
            ),
            Text('fermé', style: Fp.body(10.5, color: Fp.muted)),
          ],
        ),
      );
    }
    // Maquettes F et N : petite case #2A2347, violette quand la sélection est dans le coupon.
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(12),
      side: BorderSide(color: on ? Fp.accent2 : Colors.transparent),
    );
    return Material(
      color: on ? V.vi : V.s2,
      shape: shape,
      child: InkWell(
        customBorder: shape,
        onTap: () => addToCoupon(context, match, offer),
        child: Container(
          width: expand ? double.infinity : null,
          constraints: const BoxConstraints(minWidth: 52, minHeight: 44),
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(odds(offer.odds), style: V.t(14, w: FontWeight.w800)),
              // 1xBet : dit en haut de l'écran ; le bookmaker de secours est nommé.
              if (offer.bookmaker != '1xBet')
                Text(offer.bookmaker, style: Fp.body(10, color: on ? Colors.white70 : Fp.muted)),
            ],
          ),
        ),
      ),
    );
  }
}

/// Match commencé : les chances et les cotes affichées sont celles d'avant le coup d'envoi.
class _BeforeKickoff extends StatelessWidget {
  const _BeforeKickoff(this.m);
  final MatchInfo m;

  @override
  Widget build(BuildContext context) {
    final now = m.isLive
        ? ' Score actuel : ${m.score ?? '—'} (${m.clock}).'
        : m.isFinished
        ? ' Score final : ${m.score ?? '—'}.'
        : '';
    return GlassCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.only(top: 2),
            child: Icon(Icons.schedule_rounded, color: Fp.muted, size: 15),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Chances calculées avant le coup d\'envoi : elles ne tiennent pas compte du score.$now '
              'Paris fermés sur ce match.',
              style: Fp.body(13, color: Fp.muted, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}

/// « Les choix du moteur » : la sélection la plus probable de chaque profil parmi les
/// marchés qui ont une vraie cote (celle que prendrait le Coupon intelligent).
class _EnginePicks extends StatelessWidget {
  const _EnginePicks({required this.picks, required this.offers, required this.match});
  final Json picks;
  final Map<String, Offer> offers;
  final MatchInfo match;

  static const _colors = {'sur': Fp.win, 'equilibre': Fp.lilac, 'audacieux': Fp.loss};
  static const _backgrounds = {'sur': Fp.winBg, 'equilibre': Fp.cardHigh, 'audacieux': Fp.lossBg};

  @override
  Widget build(BuildContext context) {
    final rows = <Widget>[];
    for (final key in const ['sur', 'equilibre', 'audacieux']) {
      final p = picks[key] as Json?;
      if (p == null) continue;
      final sel = p['selection'] as Json?;
      final locked = p['locked'] == true;
      final offer = sel == null ? null : offers['${sel['market']}|${sel['line'] ?? ''}|${sel['selection']}'];
      final text = locked
          ? 'Avec Premium'
          : sel == null
          ? 'Aucune sélection dans cette tranche'
          : fullLabel(
              sel['market'] as String,
              (sel['line'] ?? '') as String,
              sel['selection'] as String,
              home: match.home.name,
              away: match.away.name,
            );
      rows.add(
        Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            border: rows.isEmpty ? null : const Border(top: BorderSide(color: Fp.divider)),
          ),
          child: Row(
            children: [
              Tag(p['label'] as String, color: _colors[key]!, background: _backgrounds[key]),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  text,
                  style: Fp.body(
                    14,
                    weight: FontWeight.w700,
                    color: locked || sel == null ? Fp.text3 : Fp.text,
                  ),
                ),
              ),
              if (locked)
                const Icon(Icons.lock_rounded, size: 18, color: Fp.accentLight)
              else if (sel != null) ...[
                const SizedBox(width: 8),
                Text(percent((sel['model_probability'] as num).toDouble()), style: Fp.title(16)),
                // Maquette v3 : la cote 1xBet à côté, un appui l'ajoute au coupon.
                if (offer != null) ...[const SizedBox(width: 8), OddsButton(match: match, offer: offer)],
              ],
            ],
          ),
        ),
      );
    }
    if (rows.isEmpty) return const SizedBox.shrink();
    return GlassCard.section(
      highlight: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const TwoToneTitle('Les choix', 'du moteur', size: 17),
          const SizedBox(height: 6),
          ...rows,
          const SizedBox(height: 4),
          Text(
            'La sélection la plus probable de chaque profil parmi celles qui ont une vraie cote. '
            'Ce n\'est pas un conseil de pari.',
            style: Fp.body(11, color: Fp.text3, height: 1.4),
          ),
        ],
      ),
    );
  }
}

/// « ⚽ Calvert-Lewin 23', Gnonto 58' · Ampadu 51' » : buteurs de l'équipe à domicile puis
/// de l'équipe à l'extérieur ; null sans but. Penalty manqué exclu, contre son camp signalé.
String? scorerLine(List<Json> events) {
  String side(String s) => [
    for (final e in events)
      if (e['kind'] == 'Goal' && e['detail'] != 'Missed Penalty' && e['side'] == s && e['player'] != null)
        '${e['player']}${e['detail'] == 'Own Goal' ? ' (csc)' : ''} '
            '${e['minute']}${e['extra'] != null && e['extra'] != 0 ? '+${e['extra']}' : ''}\'',
  ].join(', ');
  final parts = [side('home'), side('away')].where((t) => t.isNotEmpty);
  return parts.isEmpty ? null : '⚽ ${parts.join(' · ')}';
}
