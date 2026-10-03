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
import 'record_screen.dart';

class BookmakerScreen extends StatefulWidget {
  const BookmakerScreen({super.key});

  @override
  State<BookmakerScreen> createState() => _BookmakerScreenState();
}

class _BookmakerScreenState extends State<BookmakerScreen> {
  int tab = 0; // 0 en cours, 1 réglés, 2 mouvements
  Key _key = UniqueKey();

  Future<void> _refill() async {
    final state = context.read<AppState>();
    final done = await guard(context, () => state.api.post('/me/wallet/refill'));
    if (done != null) {
      showMessage('Solde rechargé.');
      await state.refreshMe();
      setState(() => _key = UniqueKey());
    }
  }

  Future<(List<Bet>, List<Json>)> _load(ApiClient api) async {
    final results = await Future.wait([
      api.get('/bets', {'limit': 100}),
      api.get('/me/wallet/entries', {'limit': 100}),
    ]);
    return ([for (final b in results[0] as List) Bet(b as Json)], (results[1] as List).cast<Json>());
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
        child: Loader<(List<Bet>, List<Json>)>(
          key: _key,
          load: () => _load(state.api),
          builder: (context, data, reload) {
            final (bets, entries) = data;
            final open = bets.where((b) => b.status == 'open').toList();
            final settled = bets.where((b) => b.status != 'open').toList();
            final atStake = open.fold<int>(0, (a, b) => a + b.stake);
            final staked = settled.fold<int>(0, (a, b) => a + b.stake);
            final returned = settled.fold<int>(0, (a, b) => a + (b.payout ?? 0));
            final roi = staked > 0 ? (returned - staked) / staked : null;
            return RefreshIndicator(
              onRefresh: () async {
                await guard(context, state.refreshMe);
                await reload();
              },
              child: ListView(
                padding: pagePadding(context, 26, 120),
                children: [
                  Row(
                    children: [
                      const Expanded(child: TwoToneTitle('Bookmaker', 'virtuel')),
                      SquareButton(
                        icon: Icons.insights_rounded,
                        tooltip: 'Mon bilan',
                        onTap: () =>
                            Navigator.of(context)
                                .push(MaterialPageRoute(builder: (_) => const RecordScreen())),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Parie sans argent réel pour tester tes stratégies.',
                    style: Fp.body(14, color: Fp.text2),
                  ),
                  const SizedBox(height: 18),
                  GlassCard.main(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    'Solde virtuel',
                                    style: Fp.body(13, color: Fp.text2, weight: FontWeight.w600),
                                  ),
                                  const SizedBox(height: 4),
                                  FittedBox(
                                    fit: BoxFit.scaleDown,
                                    alignment: Alignment.centerLeft,
                                    child: Text(
                                      me != null ? money(me.balance, currency) : '—',
                                      style: Fp.title(32),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const Tag('Argent fictif'),
                          ],
                        ),
                        const SizedBox(height: 16),
                        Row(
                          children: [
                            Expanded(child: StatTile('En jeu', '${thousands(atStake)} F')),
                            const SizedBox(width: 8),
                            Expanded(child: StatTile('Paris', '${bets.length}')),
                            const SizedBox(width: 8),
                            Expanded(
                              child: StatTile(
                                'Rendement',
                                roi == null ? '—' : '${roi >= 0 ? '+' : ''}${percent(roi, decimals: 1)}',
                                valueColor: roi == null ? null : (roi >= 0 ? Fp.win : Fp.lossText),
                              ),
                            ),
                          ],
                        ),
                        if (me != null && me.balance < 1000) ...[
                          const SizedBox(height: 14),
                          OutlinedButton.icon(
                            onPressed: _refill,
                            icon: const Icon(Icons.refresh_rounded),
                            label: const Text('Recharger (une fois par semaine)'),
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  SegmentTabs(
                    labels: const ['En cours', 'Réglés', 'Mouvements'],
                    selected: tab,
                    onSelected: (i) => setState(() => tab = i),
                  ),
                  const SizedBox(height: 12),
                  if (tab < 2)
                    _BetList(
                      bets: tab == 0 ? open : settled,
                      empty: tab == 0 ? 'Aucun pari en cours.' : 'Aucun pari réglé pour l\'instant.',
                    )
                  else if (entries.isEmpty)
                    const EmptyState('Aucun mouvement.')
                  else
                    GlassCard.section(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                      child: Column(
                        children: [
                          for (final (i, e) in entries.indexed) ...[
                            if (i > 0) const Divider(),
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
    return GlassCard.section(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Mes paris', style: Fp.title(15, weight: FontWeight.w600)),
          for (final (i, b) in bets.indexed) ...[_BetRow(bet: b), if (i < bets.length - 1) const Divider()],
        ],
      ),
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
    _ => Tag(label, color: b.status == 'open' ? Fp.accentLight : Fp.textSoft),
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
            child: BetCard(bet: b),
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
                  child: Text(
                    betKind(b),
                    style: Fp.body(12, color: Fp.text2, weight: FontWeight.w600),
                  ),
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
              style: Fp.body(13, color: Fp.text2),
            ),
          ],
        ),
      ),
    );
  }
}

const _entryKinds = {
  'opening': 'Solde de départ',
  'refill': 'Rechargement',
  'stake': 'Mise',
  'payout': 'Gain',
  'void': 'Remboursement',
  'correction': 'Correction (score rectifié)',
};

class _EntryRow extends StatelessWidget {
  const _EntryRow({required this.e, required this.currency});
  final Json e;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final amount = e['amount'] as int;
    final when = parseDate(e['created_at']);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${_entryKinds[e['kind']] ?? e['kind']}${e['bet_id'] != null ? ' · pari n° ${e['bet_id']}' : ''}',
                  style: Fp.body(13, weight: FontWeight.w600),
                ),
                Text(
                  '${when != null ? dateTime(when) : ''}${e['note'] != null ? ' · ${e['note']}' : ''}',
                  style: Fp.body(11, color: Fp.text3),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                signedMoney(amount, currency),
                style: Fp.body(13, weight: FontWeight.w700, color: amount >= 0 ? Fp.win : Fp.loss),
              ),
              Text(
                'solde ${money(e['balance_after'] as int, currency)}',
                style: Fp.body(11, color: Fp.text3),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class BetCard extends StatelessWidget {
  const BetCard({super.key, required this.bet});
  final Bet bet;

  @override
  Widget build(BuildContext context) {
    final b = bet;
    final color = switch (b.outcome) {
      'won' || 'partial' => Fp.win,
      'lost' => Fp.loss,
      _ => b.status == 'open' ? Fp.accentLight : Fp.text2,
    };
    return GlassCard.section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('Pari n° ${b.id} · ${betKind(b)}', style: Fp.title(15, weight: FontWeight.w600)),
              ),
              betTag(b),
            ],
          ),
          const SizedBox(height: 10),
          for (final s in b.selections)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(
                children: [
                  Icon(
                    switch (s.result) {
                      'win' || 'half_win' => Icons.check_circle_rounded,
                      'loss' || 'half_loss' => Icons.cancel_rounded,
                      'push' => Icons.replay_circle_filled_rounded,
                      _ => Icons.schedule_rounded,
                    },
                    size: 18,
                    color: switch (s.result) {
                      'win' || 'half_win' => Fp.win,
                      'loss' || 'half_loss' => Fp.loss,
                      _ => Fp.text3,
                    },
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${s.homeTeam} - ${s.awayTeam}', style: Fp.body(11, color: Fp.text3)),
                        Text(
                          fullLabel(s.market, s.line, s.selection, home: s.homeTeam, away: s.awayTeam),
                          style: Fp.body(13, weight: FontWeight.w600),
                        ),
                      ],
                    ),
                  ),
                  Text(odds(s.odds), style: Fp.body(13, weight: FontWeight.w700)),
                ],
              ),
            ),
          const Divider(height: 18),
          KeyValue('Mise · cote ${odds(b.totalOdds)}', money(b.stake, b.currency)),
          if (b.status == 'open')
            KeyValue('Gain possible', money(b.potentialPayout, b.currency), valueColor: Fp.win)
          else
            KeyValue('Rendu', money(b.payout ?? 0, b.currency), valueColor: color, bold: true),
          if (b.placedAt != null)
            Text('Placé le ${dateTime(b.placedAt!)}', style: Fp.body(11, color: Fp.text3)),
        ],
      ),
    );
  }
}
