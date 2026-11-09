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
import '../widgets/common.dart';
import '../widgets/maquette.dart';
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
    _timer = Timer.periodic(const Duration(minutes: 1), (_) {
      if (mounted && tab == 0 && _foreground.value) _reload?.call();
    });
  }

  late final ValueNotifier<bool> _foreground;

  void _onForeground() {
    if (mounted && tab == 0 && _foreground.value) _reload?.call();
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

  Future<(List<Bet>, List<Json>, Json?)> _load(ApiClient api) async {
    final results = await Future.wait([
      api.get('/bets', {'limit': 100}),
      api.get('/me/wallet/entries', {'limit': 100}),
      _summary(api),
    ]);
    return (
      [for (final b in results[0] as List) Bet(b as Json)],
      (results[1] as List).cast<Json>(),
      results[2] as Json?,
    );
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
                  const TwoToneTitle('Mes', 'paris'),
                  const SizedBox(height: 16),
                  const OddsDownBanner(),
                  MCard(
                    margin: EdgeInsets.zero,
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        // Maquette I : solde, puis En jeu · 30 jours · Paris sur une ligne.
                        Text('Solde (argent fictif)', style: Fp.body(13, color: Fp.muted)),
                        const SizedBox(height: 2),
                        FittedBox(
                          fit: BoxFit.scaleDown,
                          alignment: Alignment.centerLeft,
                          child: Text.rich(
                            TextSpan(
                              children: [
                                TextSpan(
                                  text: me != null ? thousands(me.balance) : '—',
                                  style: Fp.title(34, weight: FontWeight.w800),
                                ),
                                TextSpan(
                                  text: ' ${currencyLabel(currency)}',
                                  style: Fp.body(13, color: Fp.muted, weight: FontWeight.w600),
                                ),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 14,
                          runSpacing: 4,
                          children: [
                            for (final (label, value, color) in [
                              ('En jeu', '${thousands(atStake)} F', Fp.text),
                              (
                                '30 jours',
                                '${month > 0
                                    ? '+'
                                    : month < 0
                                    ? '−'
                                    : ''}${thousands(month.abs())} F',
                                month > 0 ? Fp.win : (month < 0 ? Fp.loss : Fp.text),
                              ),
                              ('Paris', thousands(count), Fp.text),
                              // Rapport du 09/11/2026 : « −48,1 % » après 3 paris alarmait sans rien
                              // dire. En dessous de 20 paris réglés, le rendement n'est pas affiché.
                              if (roi != null && settledCount >= 20)
                                (
                                  'Rendement',
                                  '${roi >= 0 ? '+' : ''}${percent(roi, decimals: 1)}',
                                  roi >= 0 ? Fp.win : Fp.loss,
                                ),
                            ])
                              Text.rich(
                                TextSpan(
                                  style: Fp.body(13, color: Fp.muted),
                                  children: [
                                    TextSpan(text: '$label '),
                                    TextSpan(
                                      text: value,
                                      style: Fp.body(13, weight: FontWeight.w700, color: color),
                                    ),
                                  ],
                                ),
                              ),
                          ],
                        ),
                        if (roi != null && settledCount > 0 && settledCount < 20) ...[
                          const SizedBox(height: 4),
                          Text(
                            'Rendement : trop peu de paris réglés pour conclure ($settledCount sur 20).',
                            style: Fp.body(12, color: Fp.muted),
                          ),
                        ],
                        const SizedBox(height: 14),
                        Row(
                          children: [
                            Expanded(
                              child: MButton(
                                'Mon bilan',
                                secondary: true,
                                onPressed: () =>
                                    Navigator.of(context)
                                        .push(MaterialPageRoute(builder: (_) => const RecordScreen())),
                              ),
                            ),
                            if (me != null && me.balance < 1000) ...[
                              const SizedBox(width: 10),
                              Expanded(child: MButton('Recharger', onPressed: _refill)),
                            ],
                          ],
                        ),
                        if (me != null && me.balance < 1000) ...[
                          const SizedBox(height: 6),
                          Text(
                            'Recharge possible une fois par semaine.',
                            style: Fp.body(11.5, color: Fp.text3),
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  SegmentTabs(
                    labels: ['En cours (${open.length})', 'Réglés', 'Mouvements'],
                    selected: tab,
                    onSelected: (i) => setState(() => tab = i),
                  ),
                  const SizedBox(height: 12),
                  if (tab == 0) ...[
                    _BetList(bets: open, empty: 'Aucun pari en cours.'),
                    // Maquette v2 : les derniers paris réglés sous les paris en cours.
                    if (settled.isNotEmpty) ...[
                      const SectionTitle('Derniers paris réglés'),
                      _BetList(bets: settled.take(3).toList(), empty: ''),
                    ],
                  ] else if (tab == 1)
                    _BetList(bets: settled, empty: 'Aucun pari réglé pour l\'instant.')
                  else if (entries.isEmpty)
                    const EmptyState('Aucun mouvement.')
                  else
                    MCard(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
                      child: Column(
                        children: [
                          for (final (i, e) in entries.indexed) ...[
                            if (i > 0) const Divider(height: 1, thickness: 1, color: Fp.divider),
                            _EntryRow(e: e, currency: currency),
                          ],
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
  const _BetList({required this.bets, required this.empty});
  final List<Bet> bets;
  final String empty;

  @override
  Widget build(BuildContext context) {
    if (bets.isEmpty) return EmptyState(empty, icon: Icons.sports_score_rounded);
    // Maquette I : une carte par pari.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final (i, b) in bets.indexed)
          MCard(
            margin: EdgeInsets.only(top: i == 0 ? 0 : 12),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            child: _BetRow(bet: b),
          ),
      ],
    );
  }
}

String betKind(Bet b) {
  final n = b.selections.length;
  final base = n == 1 ? 'simple' : 'combiné de $n';
  if (b.montanteStepId != null) return 'Montante · $base';
  return n == 1 ? 'Simple' : 'Coupon · $n sélections';
}

Widget betTag(Bet b) {
  final label = betStatusLabel(b.status, b.outcome);
  return switch (b.outcome) {
    'won' || 'partial' => Tag.win(label),
    'lost' => Tag.loss(label),
    // Maquette C7 : « En cours » en ambre.
    _ when b.status == 'open' => Tag(label, color: Fp.warning, background: const Color(0xFF1F1709)),
    _ => Tag(label, color: Fp.textSoft),
  };
}

class _BetRow extends StatelessWidget {
  const _BetRow({required this.bet});
  final Bet bet;

  @override
  Widget build(BuildContext context) {
    final b = bet;
    final title = b.selections.length == 1
        ? () {
            final s = b.selections.single;
            return '${s.homeTeam} – ${s.awayTeam} · '
                '${fullLabel(s.market, s.line, s.selection, home: s.homeTeam, away: s.awayTeam)}';
          }()
        : b.selections.map((s) => '${s.homeTeam} – ${s.awayTeam}').join(', ');
    return InkWell(
      onTap: () => showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        showDragHandle: true,
        builder: (_) => SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
            child: BetCard(bet: b, plain: true),
          ),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(betKind(b), style: Fp.body(13, color: Fp.muted)),
                ),
                betTag(b),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: Fp.body(15, weight: FontWeight.w700),
            ),
            const SizedBox(height: 4),
            Text(
              '${money(b.stake, b.currency)} · cote ${odds(b.totalOdds)}'
              '${b.status == 'open'
                  ? ' · gain possible ${money(b.potentialPayout, b.currency)}'
                  : b.payout != null && b.payout! > 0
                  ? ' · rendu ${money(b.payout!, b.currency)}'
                  : ''}',
              style: Fp.body(13, color: Fp.muted),
            ),
            if (b.status == 'open' && b.selections.length > 1) ...[
              const SizedBox(height: 10),
              ProbBar(
                b.selections.where((s) => s.result == 'win' || s.result == 'half_win').length /
                    b.selections.length,
                height: 5,
                color: Fp.win,
              ),
              const SizedBox(height: 8),
              Text(betProgress(b), style: Fp.body(13, color: Fp.muted)),
            ],
          ],
        ),
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
