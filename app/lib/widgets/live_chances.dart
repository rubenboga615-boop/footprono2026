// Chances du moteur pendant le match (plan du 10/11/2026, étape 6 ; maquettes D2 et D7).
// Rien n'est affiché tant que la console ne les a pas publiées après une vérification juste :
// le serveur répond alors « published: false » et ces cartes restent invisibles.

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'visage.dart';

/// Chances du moment des matchs demandés : {match: {minute, extra, markets: {clé: chance}}} ;
/// vide si non publiées ou en cas d'erreur (l'écran reste tel qu'avant le direct).
Future<Map<int, Json>> loadLiveChances(ApiClient api, Iterable<int> matchIds) async {
  final ids = matchIds.toSet();
  if (ids.isEmpty) return {};
  try {
    final r = await api.get('/live/chances?${ids.map((i) => 'match_ids=$i').join('&')}') as Json;
    if (r['published'] != true) return {};
    return {for (final e in (r['matches'] as Map).entries) int.parse('${e.key}'): (e.value as Json)};
  } on ApiException {
    return {};
  }
}

String _key(BetSel s) => '${s.market}|${s.line}|${s.selection}';

/// Chance du coupon au départ (chances du moteur au moment du pari) et maintenant : sélection
/// gagnée 1, remboursée 1, à venir sa chance d'avant le match, en cours sa chance du moment.
/// Null si une chance manque (match en cours sans chance calculée, carton rouge…) ou si le
/// coupon est déjà perdu : rien plutôt qu'un chiffre faux.
(double, double)? couponChances(Bet b, Map<int, Json> live) {
  var start = 1.0, current = 1.0;
  for (final s in b.selections) {
    final p = s.modelProbability;
    if (p == null) return null;
    start *= p;
    switch (s.result) {
      case 'win' || 'half_win' || 'push' || 'void':
        continue;
      case 'loss' || 'half_loss':
        return null;
    }
    if (s.state == 'live' || s.state == 'finished') {
      final now = ((live[s.matchId]?['markets'] as Map?)?[_key(s)] as num?)?.toDouble();
      if (now == null) return null;
      current *= now;
    } else {
      current *= p;
    }
  }
  return (start, current);
}

/// Encadré vert de la fiche d'un pari en cours (maquette D7).
class LiveCouponChance extends StatefulWidget {
  const LiveCouponChance(this.bet, {super.key});
  final Bet bet;

  @override
  State<LiveCouponChance> createState() => _LiveCouponChanceState();
}

class _LiveCouponChanceState extends State<LiveCouponChance> {
  late final AppState _state = context.read<AppState>();
  Map<int, Json>? live;

  Set<int> get _ids => {
    for (final s in widget.bet.selections)
      if (s.state == 'live') s.matchId,
  };

  @override
  void initState() {
    super.initState();
    _load();
    // Relue à chaque relevé du direct d'un de ses matchs (retour du fondateur du 12/11/2026).
    _state.liveFeed.addListener(_onFeed);
  }

  @override
  void dispose() {
    _state.liveFeed.removeListener(_onFeed);
    super.dispose();
  }

  void _onFeed() {
    final feed = _state.liveFeed.value;
    if (feed != null && feed.matches.keys.any(_ids.contains)) _load();
  }

  Future<void> _load() async {
    final r = await loadLiveChances(_state.api, _ids);
    if (mounted) setState(() => live = r);
  }

  @override
  Widget build(BuildContext context) => Builder(
    builder: (context) {
      final live = this.live;
      if (live == null || live.isEmpty) return const SizedBox.shrink();
      final c = couponChances(widget.bet, live);
      if (c == null) return const SizedBox.shrink();
      final (start, now) = c;
      return Container(
        margin: const EdgeInsets.only(top: 10, bottom: 4),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Fp.winBg,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: Fp.winLine),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Chance de ton coupon : ${percent(start)} au départ → ${chancePercent(now)} maintenant',
              style: Fp.body(14.5, weight: FontWeight.w700, color: Fp.win, height: 1.35),
            ),
            const SizedBox(height: 4),
            Text('D\'après le score et la minute de chaque match.', style: Fp.body(12.5, color: Fp.text2)),
          ],
        ),
      );
    },
  );
}

/// Carte « Chances en direct » de l'écran d'un match (maquette D2).
class LiveChancesCard extends StatefulWidget {
  const LiveChancesCard({super.key, required this.match, this.before});
  final MatchInfo match;

  /// Chances d'avant le match (1, N, 2), pour comparer.
  final (double, double, double)? before;

  @override
  State<LiveChancesCard> createState() => _LiveChancesCardState();
}

class _LiveChancesCardState extends State<LiveChancesCard> {
  Map<int, Json>? live;

  /// Mes sélections « plus/moins de buts » en cours sur ce match (lues une fois).
  List<BetSel> mine = const [];

  @override
  void initState() {
    super.initState();
    _load();
    _loadMine();
  }

  Future<void> _loadMine() async {
    final state = context.read<AppState>();
    if (!state.loggedIn) return;
    try {
      final bets = [
        for (final b in await state.api.get('/bets', {'limit': 100}) as List) Bet(b as Json),
      ];
      final found = [
        for (final b in bets)
          if (b.status == 'open')
            for (final s in b.selections)
              if (s.matchId == widget.match.id && s.result == 'pending') s,
      ];
      if (mounted) setState(() => mine = found);
    } on Object {
      // Paris indisponibles : la carte garde les chances du match.
    }
  }

  // Chargées une fois ; ensuite, les relevés du direct portent les chances du moment (retour
  // du 12/11/2026 : pas de requête à chaque relevé).
  Future<void> _load() async {
    final r = await loadLiveChances(context.read<AppState>().api, [widget.match.id]);
    if (mounted) setState(() => live = r);
  }

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<LiveFeed?>(
    valueListenable: context.read<AppState>().liveFeed,
    builder: (context, feed, _) {
      final id = widget.match.id;
      final j = feed?.matches.containsKey(id) == true ? feed!.chancesOf(id) : live?[id];
      final markets = j?['markets'] as Map?;
      double? p(String k) => (markets?[k] as num?)?.toDouble();
      final home = p('1X2||home'), draw = p('1X2||draw'), away = p('1X2||away');
      if (j == null || home == null || draw == null || away == null) return const SizedBox.shrink();
      final m = widget.match;
      // Ligne qui suit le score (demande du fondateur du 12/11/2026) : à 2-0, « encore au moins
      // un but » = plus de 2,5 ; au-delà de 5,5, rien plutôt qu'un chiffre faux.
      final goals = (m.liveHome ?? 0) + (m.liveAway ?? 0);
      double? overLine(double line) => line > 5.5 ? null : p('OU|${line.toStringAsFixed(1)}|over');
      final one = overLine(goals + 0.5), two = overLine(goals + 1.5);
      final none = goals == 0;
      final b = widget.before;
      final minute = (j['minute'] as num?)?.toInt() ?? m.liveMinute ?? 0;
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Maquette 8 : « Mon pari » en premier, avec sa chance de tenir.
          for (final s in mine)
            if (p('${s.market}|${s.line}|${s.selection}') ??
                    (s.market == 'OU' && s.selection == 'under'
                        ? (p('OU|${s.line}|over') == null ? null : 1 - p('OU|${s.line}|over')!)
                        : null)
                case final now?)
              _MyBetCard(sel: s, now: now, minute: minute, match: m),
          VCard(
            top: mine.isEmpty ? 0 : 12,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const VKicker('Chances maintenant'),
                VBar3(home, draw, away),
                const SizedBox(height: 6),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    for (final (label, v) in [(m.home.name, home), ('nul', draw), (m.away.name, away)])
                      Flexible(
                        child: Text.rich(
                          TextSpan(
                            children: [
                              TextSpan(text: '$label '),
                              TextSpan(
                                text: chancePercent(v),
                                style: const TextStyle(fontWeight: FontWeight.w700),
                              ),
                            ],
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: V.t(12, color: V.mu),
                        ),
                      ),
                  ],
                ),
                if (one != null || two != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: VList(
                      children: [
                        if (one != null)
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  none ? 'Au moins un but dans le match' : 'Encore au moins un but',
                                ),
                              ),
                              Text(chancePercent(one), style: V.b()),
                            ],
                          ),
                        if (two != null)
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  none ? 'Au moins deux buts dans le match' : 'Encore au moins deux buts',
                                ),
                              ),
                              Text(chancePercent(two), style: V.b()),
                            ],
                          ),
                      ],
                    ),
                  ),
                const SizedBox(height: 4),
                Text(
                  [
                    if (b != null) 'Avant le match : ${percent(b.$1)} · ${percent(b.$2)} · ${percent(b.$3)}.',
                    'Recalculé avec le score et la minute ; ce n\'est pas un conseil de pari.',
                  ].join(' '),
                  style: V.mu_(),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
        ],
      );
    },
  );
}

/// « Mon pari · moins de 2,5 buts » (maquette 8) : anneau de la chance de tenir, chance au
/// départ et minutes restantes ; liseré vert quand la sélection gagnerait maintenant.
class _MyBetCard extends StatelessWidget {
  const _MyBetCard({required this.sel, required this.now, required this.minute, required this.match});
  final BetSel sel;
  final double now;
  final int minute;
  final MatchInfo match;

  @override
  Widget build(BuildContext context) {
    final s = sel;
    final (chip, kind) = switch (s.now) {
      'win' || 'half_win' => ('gagnant', VChipKind.up),
      'loss' || 'half_loss' => ('perdant', VChipKind.dn),
      'push' || 'void' => ('remboursé', VChipKind.eq),
      _ => (null, VChipKind.eq),
    };
    final label = selectionLabel(s.market, s.line, s.selection, home: match.home.name, away: match.away.name);
    final left = 90 - minute;
    return VCard(
      top: 0,
      border: kind == VChipKind.up ? const Color(0xFF1D5A44) : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Mon pari · $label'.toUpperCase(),
                  style: V.t(10.5, w: FontWeight.w700, color: V.mint, ls: 0.8),
                ),
              ),
              if (chip != null) VChip(chip, kind: kind),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              VRing(now),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('de chances de tenir', style: V.t(12.5, color: V.mu)),
                    Text(
                      [
                        if (s.modelProbability != null) '${percent(s.modelProbability!)} au départ',
                        if (left > 0) 'encore $left min',
                      ].join(' · '),
                      style: V.mu_(),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    ).withBottom(12);
  }
}
