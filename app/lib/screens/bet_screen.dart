// « Fiche d'un pari » : copie de la maquette 19 du testeur (docs/maquettes/12-nouveau-visage).
// Gain (ou gain possible), mise et cote, chance annoncée contre la cote ; les sélections avec
// leur résultat ; l'histoire du pari en frise (GET /bets/{id}/history).
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../widgets/live_chances.dart';
import '../widgets/visage.dart';
import 'bookmaker_screen.dart' show betStatusChip, lostEarly, selectionState;
import 'match_screen.dart';

class BetScreen extends StatefulWidget {
  const BetScreen({super.key, required this.bet});
  final Bet bet;

  @override
  State<BetScreen> createState() => _BetScreenState();
}

class _BetScreenState extends State<BetScreen> {
  List<Json>? history;

  @override
  void initState() {
    super.initState();
    context
        .read<AppState>()
        .api
        .get('/bets/${widget.bet.id}/history')
        .then((j) {
          if (mounted) setState(() => history = ((j as Json)['events'] as List).cast<Json>());
        })
        .catchError((Object _) {
          if (mounted) setState(() => history = const []);
        });
  }

  @override
  Widget build(BuildContext context) {
    final b = widget.bet;
    final cur = b.currency;
    String f(num v) => '${thousands(v)}$nbsp${cur == 'XOF' || cur == 'XAF' ? 'F' : cur}';
    final probs = b.selections.map((s) => s.modelProbability).toList();
    final announced = probs.contains(null) ? null : probs.fold<double>(1, (a, v) => a * v!);
    final open = b.status == 'open';
    final gain = open ? b.potentialPayout - b.stake : (b.payout ?? 0) - b.stake;
    final color = open ? V.tx : (gain > 0 ? V.mint : (gain < 0 ? V.coral : V.tx));
    return VPage(
      children: [
        VTopBar('Pari n° ${b.id}', trailing: betStatusChip(b)),
        VCard(
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
                        VKicker(open ? 'Gain possible' : 'Gain'),
                        FittedBox(
                          fit: BoxFit.scaleDown,
                          alignment: Alignment.centerLeft,
                          child: Text(
                            '${gain > 0
                                ? '+'
                                : gain < 0
                                ? '−'
                                : ''}${f(gain.abs())}',
                            style: V.big(color),
                          ),
                        ),
                      ],
                    ),
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text('mise ${f(b.stake)}', style: V.mu_(12.5)),
                      Text('cote ${decimal(b.totalOdds, max: 3)}', style: V.mu_(12.5)),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                [
                  if (announced != null) 'Chance annoncée : ${percent(announced)}',
                  'selon la cote : ${percent(1 / b.totalOdds)}',
                ].join(' · '),
                style: V.mu_(12.5),
              ),
              if (b.selections.any((s) => s.bookmaker == 'direct'))
                Text(
                  'Placé en direct${b.placedAt == null ? '' : ' à ${hourMinute(b.placedAt!.toLocal())}'} · '
                  'cotes du direct',
                  style: V.mu_(),
                ),
            ],
          ),
        ),
        if (open && b.selections.any((s) => s.state == 'live')) LiveCouponChance(b),
        VCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const VKicker('Sélections'),
              VList(
                children: [
                  for (final s in b.selections)
                    GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () =>
                          Navigator.of(context)
                              .push(MaterialPageRoute(builder: (_) => MatchScreen(matchId: s.matchId))),
                      child: Row(
                        children: [
                          _ResultChip(s),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  s.score?[0] != null && s.state != 'upcoming'
                                      ? '${s.homeTeam} ${s.score![0]}-${s.score![1]} ${s.awayTeam}'
                                      : '${s.homeTeam} – ${s.awayTeam}',
                                  style: V.t(13.5),
                                ),
                                Text(
                                  lowerLabel(
                                    pickLabel(
                                      s.market,
                                      s.line,
                                      s.selection,
                                      home: s.homeTeam,
                                      away: s.awayTeam,
                                    ),
                                  ),
                                  style: V.mu_(),
                                ),
                                if (s.result == 'pending') Text(selectionState(s), style: V.mu_(11)),
                              ],
                            ),
                          ),
                          Text(odds(s.odds), style: V.b()),
                        ],
                      ),
                    ),
                ],
              ),
              if (lostEarly(b) case final note?) Text(note, style: V.mu_()),
            ],
          ),
        ),
        VCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const VKicker('Histoire du pari'),
              const SizedBox(height: 6),
              if (history == null)
                const Center(child: CircularProgressIndicator())
              else if (history!.isEmpty)
                Text('Pas encore d\'événement.', style: V.mu_())
              else
                VTimeline(
                  items: [
                    for (final e in history!)
                      (
                        '${_when(parseDate(e['at']))} · ${e['text']}',
                        switch (e['tone']) {
                          'green' => VDotKind.green,
                          'red' => VDotKind.red,
                          _ => VDotKind.plain,
                        },
                      ),
                  ],
                ),
            ],
          ),
        ),
      ],
    );
  }

  /// « 17/11 21:40 ».
  static String _when(DateTime? d) {
    if (d == null) return '';
    final l = d.toLocal();
    return '${l.day.toString().padLeft(2, '0')}/${l.month.toString().padLeft(2, '0')} ${hourMinute(l)}';
  }
}

/// Pastille du résultat d'une sélection : ✓ gagnée, × perdue, point vert en cours, ≈ à venir.
class _ResultChip extends StatelessWidget {
  const _ResultChip(this.s);
  final BetSel s;

  @override
  Widget build(BuildContext context) => switch (s.result) {
    'win' ||
    'half_win' => const VChip('', kind: VChipKind.up, arrow: VIc(VIcon.check, size: 13, stroke: 2.4)),
    'loss' || 'half_loss' => const VChip('×', kind: VChipKind.dn),
    'push' || 'void' => const VChip('=', kind: VChipKind.eq),
    _ when s.state == 'live' => const VChip('', kind: VChipKind.vi, arrow: VDot()),
    _ => const VChip('…', kind: VChipKind.eq),
  };
}
