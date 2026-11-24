import 'dart:async';

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
import 'bet_screen.dart';
import '../widgets/common.dart';
import '../widgets/live_chances.dart';
import '../widgets/maquette.dart';
import 'match_screen.dart';
import 'record_screen.dart';

class BookmakerScreen extends StatefulWidget {
  const BookmakerScreen({super.key});

  @override
  State<BookmakerScreen> createState() => _BookmakerScreenState();
}

class _BookmakerScreenState extends State<BookmakerScreen> {
  int tab = 0; // 0 en cours, 1 réglés, 2 mouvements
  Key _key = UniqueKey();
  Timer? _timer;
  Future<void> Function()? _reload;

  @override
  void initState() {
    super.initState();
    // Paris en cours : résultats et scores des matchs mis à jour tout seuls, chaque minute.
    // Arrêté en arrière-plan (rapport du 09/11/2026), rechargé une fois au retour.
    _foreground = context.read<AppState>().foreground..addListener(_onForeground);
    // Seulement onglet affiché : caché (autre onglet, écran d'un match par-dessus), il ne
    // demandait pas moins paris, porte-monnaie et bilan chaque minute (retour du 12/11/2026).
    _timer = Timer.periodic(const Duration(minutes: 1), (_) {
      if (_shown && tab == 0) _reload?.call();
    });
  }

  late final ValueNotifier<bool> _foreground;

  bool get _shown => mounted && _foreground.value && TickerMode.valuesOf(context).enabled;

  void _onForeground() {
    if (_shown && tab == 0) _reload?.call();
  }

  @override
  void dispose() {
    _foreground.removeListener(_onForeground);
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refill() async {
    final state = context.read<AppState>();
    final done = await guard(context, () => state.api.post('/me/wallet/refill'));
    if (done != null) {
      showMessage('Solde rechargé.');
      await state.refreshMe();
      setState(() => _key = UniqueKey());
    }
  }

  /// Chances du direct des matchs en cours de mes paris (anneaux, maquette 18).
  Map<int, Json> chances = {};

  Future<(List<Bet>, List<Json>, Json?)> _load(ApiClient api) async {
    final results = await Future.wait([
      api.get('/bets', {'limit': 100}),
      api.get('/me/wallet/entries', {'limit': 100}),
      _summary(api),
    ]);
    final bets = [for (final b in results[0] as List) Bet(b as Json)];
    chances = await loadLiveChances(api, {
      for (final b in bets)
        if (b.status == 'open')
          for (final s in b.selections)
            if (s.state == 'live') s.matchId,
    });
    return (bets, (results[1] as List).cast<Json>(), results[2] as Json?);
  }

  /// Totaux de tous les paris (la liste n'en charge que 100) ; null avec un serveur
  /// pas encore à jour : l'en-tête se calcule alors sur la liste chargée.
  static Future<Json?> _summary(ApiClient api) async {
    try {
      return await api.get('/me/bets-summary') as Json;
    } on ApiException catch (e) {
      if (e.status == 404 || e.status == 422) return null;
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final me = state.me;
    final currency = me?.currency ?? 'XOF';
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        bottom: false,
        child: Loader<(List<Bet>, List<Json>, Json?)>(
          key: _key,
          load: () => _load(state.api),
          builder: (context, data, reload) {
            _reload = reload;
            final (bets, entries, summary) = data;
            final open = bets.where((b) => b.status == 'open').toList();
            final settled = bets.where((b) => b.status != 'open').toList();
            // En-tête : tous les paris du joueur (mêmes chiffres que Mon bilan).
            final int atStake;
            final double? roi;
            final int month;
            final int count;
            final int settledCount;
            if (summary != null) {
              atStake = summary['at_stake'] as int;
              roi = (summary['yield'] as num?)?.toDouble();
              month = summary['last_30_days'] as int;
              count = summary['bets'] as int;
              settledCount = (summary['settled'] as int?) ?? settled.length;
            } else {
              settledCount = settled.length;
              atStake = open.fold<int>(0, (a, b) => a + b.stake);
              final staked = settled.fold<int>(0, (a, b) => a + b.stake);
              final returned = settled.fold<int>(0, (a, b) => a + (b.payout ?? 0));
              roi = staked > 0 ? (returned - staked) / staked : null;
              // Résultat des paris réglés placés ces 30 derniers jours (maquette v2).
              final since = DateTime.now().subtract(const Duration(days: 30));
              month = settled
                  .where((b) => b.placedAt != null && b.placedAt!.isAfter(since))
                  .fold<int>(0, (a, b) => a + (b.payout ?? 0) - b.stake);
              count = bets.length;
            }
            return RefreshIndicator(
              onRefresh: () async {
                await guard(context, state.refreshMe);
                await reload();
              },
              child: ListView(
                padding: pagePadding(context, 26, 120),
                children: [
                  // Maquette 18 : « Mes paris », En cours · Réglés · Solde, une carte par pari,
                  // le solde en bas.
                  Text.rich(
                    const TextSpan(
                      children: [
                        TextSpan(text: 'Mes '),
                        TextSpan(
                          text: 'paris',
                          style: TextStyle(color: V.vi2),
                        ),
                      ],
                    ),
                    style: V.t(24, w: FontWeight.w800, ls: -0.4),
                  ),
                  const SizedBox(height: 10),
                  const OddsDownBanner(),
                  VSeg(
                    items: ['En cours ${open.length}', 'Réglés', 'Solde'],
                    selected: tab,
                    onSelect: (i) => setState(() => tab = i),
                  ),
                  if (tab == 0) ...[
                    _BetList(bets: open, chances: chances, empty: 'Aucun pari en cours.'),
                    if (settled.isNotEmpty) ...[
                      const SizedBox(height: 16),
                      const VKicker('Derniers paris réglés'),
                      _BetList(bets: settled.take(3).toList(), chances: chances, empty: ''),
                    ],
                  ] else if (tab == 1)
                    _BetList(bets: settled, chances: chances, empty: 'Aucun pari réglé pour l\'instant.')
                  else if (entries.isEmpty)
                    const Padding(padding: EdgeInsets.only(top: 12), child: EmptyState('Aucun mouvement.'))
                  else
                    VCard(
                      child: VList(
                        children: [for (final e in entries) _EntryRow(e: e, currency: currency)],
                      ),
                    ),
                  VCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const VKicker('Solde fictif'),
                                  Text(me != null ? '${thousands(me.balance)} F' : '—', style: V.b(18)),
                                ],
                              ),
                            ),
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                // Période écrite en clair (séance du testeur du 24/11/2026 : « Ce mois »
                                // à côté des « 30 j » du tableau de bord faisait croire à une erreur).
                                VKicker('Depuis le 1er ${longDate(DateTime.now()).split(' ').last}'),
                                Text(
                                  '${month > 0
                                      ? '+'
                                      : month < 0
                                      ? '−'
                                      : ''}${thousands(month.abs())} F',
                                  style: V.b(13.5, month > 0 ? V.mint : (month < 0 ? V.coral : V.tx)),
                                ),
                              ],
                            ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        Text(
                          [
                            'En jeu ${thousands(atStake)} F',
                            '${thousands(count)} paris',
                            if (roi != null && settledCount >= 20)
                              'rendement ${roi >= 0 ? '+' : ''}${percent(roi, decimals: 1)}',
                          ].join(' · '),
                          style: V.mu_(),
                        ),
                        if (roi != null && settledCount > 0 && settledCount < 20)
                          Text(
                            'Rendement : trop peu de paris réglés pour conclure ($settledCount sur 20).',
                            style: V.mu_(11),
                          ),
                        Row(
                          children: [
                            VLink(
                              'Mon bilan ›',
                              onTap: () =>
                                  Navigator.of(context)
                                      .push(MaterialPageRoute(builder: (_) => const RecordScreen())),
                            ),
                            const Spacer(),
                            if (me != null && me.balance < 1000) VLink('Recharger', onTap: _refill),
                          ],
                        ),
                        if (me != null && me.balance < 1000)
                          Text('Recharge possible une fois par semaine.', style: V.mu_(11)),
                      ],
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

class _BetList extends StatelessWidget {
  const _BetList({required this.bets, required this.empty, required this.chances});
  final List<Bet> bets;
  final String empty;
  final Map<int, Json> chances;

  @override
  Widget build(BuildContext context) {
    if (bets.isEmpty) {
      return Padding(
        padding: const EdgeInsets.only(top: 12),
        child: EmptyState(empty, icon: Icons.sports_score_rounded),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [for (final b in bets) _BetRow(bet: b, chances: chances)],
    );
  }
}

String betKind(Bet b) {
  final n = b.selections.length;
  final base = n == 1 ? 'simple' : 'combiné de $n';
  if (b.montanteStepId != null) return 'Montante · $base';
  return n == 1 ? 'Simple' : 'Coupon · $n sélections';
}

/// Pastille d'état d'un pari (maquettes 18 et 19) : gagné, perdu, en cours…
Widget betStatusChip(Bet b) {
  final label = betStatusLabel(b.status, b.outcome);
  return VChip(
    label.toLowerCase(),
    kind: switch (b.outcome) {
      'won' || 'partial' => VChipKind.up,
      'lost' => VChipKind.dn,
      _ when b.status == 'open' => VChipKind.am,
      _ => VChipKind.eq,
    },
  );
}

Widget betTag(Bet b) => betStatusChip(b);

/// Carte d'un pari (maquette 18) : titre, « n° · mise · cote » ; combiné en cours : anneau de
/// la chance de passer maintenant et une pastille par sélection.
class _BetRow extends StatelessWidget {
  const _BetRow({required this.bet, required this.chances});
  final Bet bet;
  final Map<int, Json> chances;

  @override
  Widget build(BuildContext context) {
    final b = bet;
    final n = b.selections.length;
    final first = b.selections.first;
    final label = selectionLabel(
      first.market,
      first.line,
      first.selection,
      home: first.homeTeam,
      away: first.awayTeam,
    );
    final title = b.montanteStepId != null
        ? 'Montante · ${n == 1 ? label : 'combiné de $n'}'
        : n == 1
        ? 'Simple · ${lowerLabel(label)}'
        : 'Combiné · $n sélections';
    final sub = [
      'n° ${b.id}',
      if (n == 1) '${first.homeTeam} – ${first.awayTeam}',
      '${thousands(b.stake)} F',
      odds(b.totalOdds),
      if (b.status != 'open' && b.payout != null && b.payout! > 0) 'rendu ${thousands(b.payout!)} F',
    ].join(' · ');
    final c = b.status == 'open' ? couponChances(b, chances) : null;
    final open = b.status == 'open';
    Widget trailing;
    if (open && n > 1 && c != null) {
      trailing = VRing(c.$2, size: 52, inner: 40, fontSize: 12);
    } else if (open && n == 1) {
      final s = first;
      trailing = switch (s.now) {
        'win' || 'half_win' => VChip(c == null ? 'gagnant' : 'gagnant ${percent(c.$2)}', kind: VChipKind.up),
        'loss' ||
        'half_loss' => VChip(c == null ? 'perdant' : 'perdant ${percent(c.$2)}', kind: VChipKind.dn),
        _ => VChip(s.state == 'live' ? 'en cours' : 'à venir', kind: VChipKind.eq),
      };
    } else {
      trailing = betStatusChip(b);
    }
    return VCard(
      onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => BetScreen(bet: b))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, maxLines: 2, overflow: TextOverflow.ellipsis, style: V.b(15)),
                    Text(sub, style: V.mu_(12.5)),
                  ],
                ),
              ),
              trailing,
            ],
          ),
          if (open && n > 1) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final s in b.selections)
                  switch (s.result) {
                    'win' || 'half_win' => VChip(
                      s.homeTeam,
                      kind: VChipKind.up,
                      arrow: const VIc(VIcon.check, size: 12, stroke: 2.4),
                    ),
                    'loss' || 'half_loss' => VChip(s.homeTeam, kind: VChipKind.dn),
                    _ when s.state == 'live' => VChip(
                      '${s.homeTeam} ${s.score?[0] ?? '-'}-${s.score?[1] ?? '-'} · ${s.minute ?? ''}\'',
                      kind: VChipKind.vi,
                      arrow: const VDot(),
                    ),
                    _ => VChip(
                      '${s.homeTeam}${s.kickoffAt == null ? '' : ' ${shortDate(s.kickoffAt!.toLocal()).split(' ').first.toLowerCase()}'}',
                      kind: VChipKind.eq,
                    ),
                  },
              ],
            ),
            const SizedBox(height: 8),
            Text(
              c == null
                  ? betProgress(b)
                  : 'Chance de passer : ${percent(c.$1)} au départ → ${percent(c.$2)} maintenant',
              style: V.mu_(12.5),
            ),
          ],
        ],
      ),
    );
  }
}

/// Combiné perdu avant la fin de tous ses matchs : dit pourquoi les autres sélections restent
/// « à venir » (essai réel du 06/11/2026 : rien ne le disait).
String? lostEarly(Bet b) {
  if (b.outcome != 'lost' || !b.selections.any((s) => s.result == 'pending')) return null;
  final first = b.selections.where((s) => s.result == 'loss' || s.result == 'half_loss').firstOrNull;
  final where = first == null ? '' : ' sur ${first.homeTeam} – ${first.awayTeam}';
  return 'Pari perdu$where : les autres matchs ne comptent plus. Ils restent affichés pour information.';
}

/// Avancement d'un combiné en cours, comme chez un bookmaker :
/// « 3 sur 11 validées · 1 en cours · 7 à venir ».
String betProgress(Bet b) {
  final n = b.selections.length;
  final won = b.selections.where((s) => s.result == 'win' || s.result == 'half_win').length;
  final lost = b.selections.where((s) => s.result == 'loss' || s.result == 'half_loss').length;
  final refunded = b.selections.where((s) => s.result == 'push').length;
  final pending = b.selections.where((s) => s.result == 'pending');
  final live = pending.where((s) => s.state == 'live' || s.state == 'finished').length;
  final upcoming = pending.length - live;
  return [
    '$won sur $n ${won > 1 ? 'validées' : 'validée'}',
    if (lost > 0) '$lost ${lost > 1 ? 'perdues' : 'perdue'}',
    if (refunded > 0) '$refunded ${refunded > 1 ? 'remboursées' : 'remboursée'}',
    if (live > 0) '$live en cours',
    if (upcoming > 0) '$upcoming à venir',
  ].join(' · ');
}

/// Ce qui compte pour une sélection : le score, ou pour un pari sur les corners (cartons,
/// tirs) leur nombre, « · 11 corners (6-5) » ; jamais le score en buts à côté d'un pari sur
/// les corners (essai réel du 06/11/2026).
String scoreText(String market, List<int?>? score, List<int>? count, String? countLabel) {
  if (count != null && count.length == 2) {
    return ' · ${count[0] + count[1]} ${countLabel ?? ''} (${count[0]}-${count[1]})';
  }
  if (isCountMarket(market)) return '';
  return score == null || score[0] == null ? '' : ' · ${score[0]}-${score[1]}';
}

bool isCountMarket(String market) =>
    const ['CORNERS', 'CARDS', 'SHOTS', 'SOT', 'BOOKING'].contains(market.split('_').first);

/// Défilement signalé : barre toujours visible et « Faire défiler ↓ » tant que le bas de la
/// fiche n'est pas atteint.
class _ScrollHint extends StatefulWidget {
  const _ScrollHint({required this.child});
  final Widget Function(ScrollController controller) child;

  @override
  State<_ScrollHint> createState() => _ScrollHintState();
}

class _ScrollHintState extends State<_ScrollHint> {
  final controller = ScrollController();
  bool more = false;

  void _check() {
    if (!controller.hasClients) return;
    final position = controller.position;
    final value = position.extentAfter > 24;
    if (value != more) setState(() => more = value);
  }

  @override
  void initState() {
    super.initState();
    controller.addListener(_check);
    WidgetsBinding.instance.addPostFrameCallback((_) => _check());
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Scrollbar(controller: controller, thumbVisibility: true, child: widget.child(controller)),
        if (more)
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: IgnorePointer(
              child: Container(
                padding: const EdgeInsets.only(top: 28, bottom: 8),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [Fp.card.withValues(alpha: 0), Fp.card],
                  ),
                ),
                child: Text(
                  'Faire défiler ↓',
                  textAlign: TextAlign.center,
                  style: Fp.body(12.5, color: Fp.lilac, weight: FontWeight.w600),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// « Gagnante pour l'instant » : la sélection réglée sur le score actuel (maquette C7).
String? nowLabel(BetSel s) => switch (s.now) {
  'win' => 'gagnante pour l\'instant',
  'half_win' => 'à moitié gagnante pour l\'instant',
  'push' => 'remboursée si le score ne bouge plus',
  'half_loss' => 'à moitié perdante pour l\'instant',
  'loss' => 'perdante pour l\'instant',
  _ => null,
};

/// Date et état du match d'une sélection : « Sam. 7 nov. 15:00 · à venir »,
/// « En direct 67' · 1-1 · gagnante pour l'instant » (maquette C7).
String selectionState(BetSel s) {
  final k = s.kickoffAt?.toLocal();
  final when = k == null ? '' : '${shortDate(k)} ${hourMinute(k)}';
  final score = scoreText(s.market, s.score, s.count, s.countLabel);
  if (s.result == 'pending' && s.state == 'live') {
    final minute = s.minute == null
        ? ''
        : s.extra != null && s.extra! > 0
        ? ' ${s.minute}+${s.extra}\''
        : ' ${s.minute}\'';
    return ['En direct$minute$score', ?nowLabel(s)].join(' · ');
  }
  final state = switch (s.result) {
    'pending' => switch (s.state) {
      'finished' => 'terminé$score · résultat dans quelques minutes',
      _ => 'à venir',
    },
    final r => '${resultLabel(r).toLowerCase()}$score',
  };
  // Réglée pendant le match (mi-temps, 3e but…) : la minute plutôt que la date.
  if (s.result != 'pending' && s.state == 'live') {
    final minute = s.minute == null ? '' : ' ${s.minute}\'';
    return '$state · en direct$minute';
  }
  return when.isEmpty ? state : '$when · $state';
}

Color selectionColor(BetSel s) => switch (s.result) {
  'win' || 'half_win' => Fp.win,
  'loss' || 'half_loss' => Fp.loss,
  'pending' when s.state == 'live' => switch (s.now) {
    'win' || 'half_win' => Fp.win,
    'push' => Fp.muted,
    _ => Fp.warning,
  },
  _ => Fp.muted,
};

const _entryKinds = {
  'opening': 'Solde de départ',
  'refill': 'Rechargement',
  'admin_credit': 'Rechargement par FootProba',
  'stake': 'Mise',
  'payout': 'Gain',
  'void': 'Remboursement',
  'correction': 'Correction (score rectifié)',
};

/// Un mouvement du solde (maquette N9) : « Mise · pari n° 32 », date courte ; montant à
/// droite, rose pour une mise, vert pour un gain, lilas pour le reste ; solde après, en petit.
/// Note utile seulement si elle dit autre chose que le type et le numéro du pari
/// (« solde de départ », « pari 38 » répétaient la ligne ; « match reporté » non).
bool _usefulNote(String note, String kind, Object? betId) {
  final n = note.trim().toLowerCase();
  return n.isNotEmpty && n != (_entryKinds[kind] ?? kind).toLowerCase() && n != 'pari $betId';
}

class _EntryRow extends StatelessWidget {
  const _EntryRow({required this.e, required this.currency});
  final Json e;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final amount = e['amount'] as int;
    final when = parseDate(e['created_at'])?.toLocal();
    final kind = e['kind'] as String;
    final color = switch (kind) {
      'stake' => Fp.loss,
      'payout' => Fp.win,
      _ => amount < 0 ? Fp.loss : Fp.lilac,
    };
    final short = currency == 'XOF' || currency == 'XAF';
    final value = short
        ? '${amount > 0
              ? '+'
              : amount < 0
              ? '−'
              : ''}${thousands(amount.abs())} F'
        : signedMoney(amount, currency);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  [
                    _entryKinds[kind] ?? kind,
                    if (e['bet_id'] != null) 'pari n° ${e['bet_id']}',
                    // Note utile seulement si elle dit autre chose que le type (« match reporté »).
                    if (e['note'] case final String note when _usefulNote(note, kind, e['bet_id'])) note,
                  ].join(' · '),
                  style: Fp.body(15, weight: FontWeight.w700),
                ),
                if (when != null)
                  Text('${shortDate(when)} ${hourMinute(when)}', style: Fp.body(13, color: Fp.muted)),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                value,
                style: Fp.body(15, weight: FontWeight.w700, color: color),
              ),
              Text(
                'solde ${thousands(e['balance_after'] as int)}${short ? ' F' : ''}',
                style: Fp.body(11.5, color: Fp.muted),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class BetCard extends StatelessWidget {
  const BetCard({super.key, required this.bet, this.plain = false});
  final Bet bet;

  /// Dans la fenêtre du bas : sans carte autour (maquette C7).
  final bool plain;

  @override
  Widget build(BuildContext context) {
    final b = bet;
    final color = switch (b.outcome) {
      'won' || 'partial' => Fp.win,
      'lost' => Fp.loss,
      _ => b.status == 'open' ? Fp.accentLight : Fp.text2,
    };
    Widget kv(String k, String v, Color valueColor) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        children: [
          Expanded(
            child: Text(k, style: Fp.body(13, color: Fp.muted)),
          ),
          Text(
            v,
            style: Fp.body(15, weight: FontWeight.w700, color: valueColor),
          ),
        ],
      ),
    );
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: Text('Pari n° ${b.id} · ${betKind(b)}', style: Fp.title(17))),
            const SizedBox(width: 8),
            betTag(b),
          ],
        ),
        // Coupon en direct (maquette D14) : pari placé pendant le match, chance de départ
        // prise à ce moment-là (score et minute).
        if (b.selections.any((s) => s.bookmaker == 'direct'))
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              'Placé en direct${b.placedAt == null ? '' : ' à ${hourMinute(b.placedAt!.toLocal())}'} · '
              'cotes du direct',
              style: Fp.body(12.5, color: Fp.muted),
            ),
          ),
        if (b.status == 'open' && b.selections.any((s) => s.state == 'live')) LiveCouponChance(b),
        const SizedBox(height: 4),
        for (final (i, s) in b.selections.indexed)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(
              border: i < b.selections.length - 1
                  ? const Border(bottom: BorderSide(color: Fp.divider))
                  : null,
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 5),
                  child: Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(color: selectionColor(s), shape: BoxShape.circle),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${s.homeTeam} – ${s.awayTeam}', style: Fp.body(12, color: Fp.muted)),
                      const SizedBox(height: 1),
                      Text(
                        fullLabel(s.market, s.line, s.selection, home: s.homeTeam, away: s.awayTeam),
                        style: Fp.body(14, weight: FontWeight.w700),
                      ),
                      const SizedBox(height: 2),
                      Text(selectionState(s), style: Fp.body(12, color: selectionColor(s))),
                      // Maquette D7 : « Suivre › » ouvre le match sur son onglet « En direct ».
                      if (s.state == 'live')
                        InkWell(
                          borderRadius: BorderRadius.circular(8),
                          onTap: () =>
                              Navigator.of(context)
                                  .push(MaterialPageRoute(builder: (_) => MatchScreen(matchId: s.matchId))),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(vertical: 4),
                            child: Text(
                              'Suivre ›',
                              style: Fp.body(12.5, weight: FontWeight.w700, color: Fp.lilac),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                Text(odds(s.odds), style: Fp.body(14, weight: FontWeight.w700)),
              ],
            ),
          ),
        const Divider(height: 1, thickness: 1, color: Fp.divider),
        if (b.status == 'open' && b.selections.length > 1) ...[
          const SizedBox(height: 10),
          Text(betProgress(b), style: Fp.body(13, color: Fp.muted)),
        ],
        if (lostEarly(b) case final note?) ...[
          const SizedBox(height: 8),
          Text(note, style: Fp.body(12, color: Fp.muted, height: 1.4)),
        ],
        const SizedBox(height: 6),
        kv('Mise · cote ${odds(b.totalOdds)}', money(b.stake, b.currency), Fp.text),
        if (b.status == 'open')
          kv('Gain possible', money(b.potentialPayout, b.currency), Fp.win)
        else
          kv('Rendu', money(b.payout ?? 0, b.currency), color),
        if (b.status == 'open' && b.selections.any((s) => s.now != null)) ...[
          const SizedBox(height: 4),
          Text(
            '« Pour l\'instant » d\'après le score actuel ; le règlement se fait à la fin du match.',
            style: Fp.body(12, color: Fp.muted, height: 1.35),
          ),
        ],
        if (b.placedAt != null) ...[
          const SizedBox(height: 4),
          Text('Placé le ${dateTime(b.placedAt!)}', style: Fp.body(12, color: Fp.muted)),
        ],
      ],
    );
    return plain ? body : MCard(child: body);
  }
}
