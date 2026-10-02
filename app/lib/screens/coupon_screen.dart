import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'smart_coupon_screen.dart';

/// Montante active dont le palier en cours attend son pari.
class OpenStep {
  OpenStep(this.montanteId, this.step, this.stake, this.oddsMin, this.oddsMax);
  final int montanteId;
  final int step;
  final int stake;
  final double oddsMin;
  final double oddsMax;
}

Future<List<OpenStep>> openSteps(ApiClient api) async {
  final out = <OpenStep>[];
  for (final m in await api.get('/montantes') as List) {
    if (m['status'] != 'active') continue;
    final current = m['current_step'];
    for (final s in m['steps'] as List) {
      if (s['number'] == current && s['bet_id'] == null) {
        out.add(
          OpenStep(
            m['id'] as int,
            current as int,
            s['stake'] as int,
            double.parse('${s['odds_min']}'),
            double.parse('${s['odds_max']}'),
          ),
        );
      }
    }
  }
  return out;
}

class CouponScreen extends StatefulWidget {
  const CouponScreen({super.key});

  @override
  State<CouponScreen> createState() => _CouponScreenState();
}

class _CouponScreenState extends State<CouponScreen> {
  final stake = TextEditingController(text: '1000');
  bool busy = false;
  List<OpenStep> steps = [];
  OpenStep? useStep;
  int _lastCount = -1;

  @override
  void initState() {
    super.initState();
    _loadSteps();
  }

  Future<void> _loadSteps() async {
    try {
      final s = await openSteps(context.read<AppState>().api);
      if (mounted) {
        setState(() {
          steps = s;
          final id = useStep?.montanteId;
          useStep = s.where((x) => x.montanteId == id).firstOrNull;
        });
      }
    } on ApiException {
      // sans montante : le coupon fonctionne normalement
    }
  }

  @override
  void dispose() {
    stake.dispose();
    super.dispose();
  }

  /// Cote totale arrondie au millième, gain au franc inférieur (comme le serveur).
  static double totalOdds(List<CouponItem> items) {
    final t = items.fold(1.0, (p, c) => p * c.offer.odds);
    return (t * 1000).round() / 1000;
  }

  Future<void> _place({bool acceptOutOfRange = false}) async {
    final state = context.read<AppState>();
    final items = [...state.coupon];
    final amount = int.tryParse(stake.text.replaceAll(RegExp(r'\D'), '')) ?? 0;
    setState(() => busy = true);
    try {
      final selections = [for (final c in items) c.toJson()];
      if (useStep != null) {
        await state.api.post('/montantes/${useStep!.montanteId}/bet', {
          'selections': selections,
          'accept_out_of_range': acceptOutOfRange,
        });
      } else {
        await state.api.post('/bets', {'stake': amount, 'selections': selections});
      }
      state.clearCoupon();
      useStep = null;
      showMessage('Pari placé. Suivi dans l\'onglet Bookmaker.');
      await state.refreshMe();
      await _loadSteps();
    } on ApiException catch (e) {
      if (e.outOfRange && mounted) {
        final ok = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Hors de la plage du palier'),
            content: Text(e.message),
            actions: [
              TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
              FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Jouer quand même'),
              ),
            ],
          ),
        );
        if (ok == true) return _place(acceptOutOfRange: true);
      } else if (e.oddsChanged) {
        showMessage('${e.message}. Mets à jour les cotes du coupon.', error: true);
      } else {
        showMessage(e.message, error: true);
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  /// Recharge les cotes actuelles des sélections du coupon.
  Future<void> _refreshOdds() async {
    final state = context.read<AppState>();
    setState(() => busy = true);
    var removed = 0;
    try {
      for (final item in [...state.coupon]) {
        final offers = [
          for (final o in await state.api.get('/matches/${item.match.id}/offer') as List) Offer(o as Json),
        ];
        final fresh = offers.where((o) => o.key == item.offer.key).firstOrNull;
        state.removeFromCoupon(item);
        if (fresh == null) {
          removed++;
        } else {
          state.toggleCoupon(item.match, fresh);
        }
      }
      showMessage(
        removed > 0
            ? 'Cotes mises à jour ; $removed sélection(s) retirée(s) : plus de cote disponible.'
            : 'Cotes mises à jour.',
      );
    } on ApiException catch (e) {
      showMessage(e.message, error: true);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  void _addStake(int v) {
    final current = int.tryParse(stake.text.replaceAll(RegExp(r'\D'), '')) ?? 0;
    setState(() => stake.text = '${current + v}');
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final items = state.coupon;
    if (items.length != _lastCount) {
      // Le coupon a changé (ajout depuis un match) : montantes à jour.
      _lastCount = items.length;
      if (items.isNotEmpty) WidgetsBinding.instance.addPostFrameCallback((_) => _loadSteps());
    }
    final me = state.me;
    final currency = me?.currency ?? 'XOF';
    final total = totalOdds(items);
    final amount = useStep?.stake ?? (int.tryParse(stake.text.replaceAll(RegExp(r'\D'), '')) ?? 0);
    final payout = (amount * total).floor();
    final probs = items.map((c) => c.offer.modelProbability).toList();
    final modelProb = probs.contains(null) ? null : probs.fold<double>(1, (p, v) => p * v!);
    final step = useStep;
    String pct(double p) => percent(p, decimals: p < 0.995 ? 1 : 0);

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        bottom: false,
        child: RefreshIndicator(
          onRefresh: _loadSteps,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(18, 26, 18, 120),
            children: [
              const TwoToneTitle('Mon', 'coupon'),
              const SizedBox(height: 4),
              Text('Compose ton pari : une ou plusieurs sélections.', style: Fp.body(14, color: Fp.text2)),
              const SizedBox(height: 16),
              GlassCard.section(
                highlight: true,
                onTap: () =>
                    Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SmartCouponScreen())),
                child: Row(
                  children: [
                    const Icon(Icons.auto_awesome_rounded, color: Fp.accentLight),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Coupon intelligent', style: Fp.title(15, weight: FontWeight.w600)),
                          const SizedBox(height: 2),
                          Text(
                            'Sûr, équilibré ou audacieux, sur la période de ton choix, expliqué.',
                            style: Fp.body(12, color: Fp.text2),
                          ),
                        ],
                      ),
                    ),
                    const Icon(Icons.chevron_right_rounded, color: Fp.text3),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              if (items.isEmpty)
                const EmptyState(
                  'Coupon vide. Ouvre un match et touche une cote pour l\'ajouter.\n'
                  'Un combiné réunit des matchs différents (10 au maximum).',
                  icon: Icons.confirmation_number_outlined,
                )
              else ...[
                GlassCard.section(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              'Mon coupon · ${items.length} sélection${items.length > 1 ? 's' : ''}',
                              style: Fp.title(15, weight: FontWeight.w600),
                            ),
                          ),
                          GestureDetector(
                            onTap: busy ? null : state.clearCoupon,
                            child: Text(
                              'Vider',
                              style: Fp.body(13, color: Fp.accentLight, weight: FontWeight.w700),
                            ),
                          ),
                        ],
                      ),
                      for (final c in items) ...[
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          child: Row(
                            children: [
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      '${c.match.home.name} – ${c.match.away.name}',
                                      style: Fp.body(13, color: Fp.text2),
                                    ),
                                    const SizedBox(height: 2),
                                    Text(
                                      fullLabel(
                                        c.offer.market,
                                        c.offer.line,
                                        c.offer.selection,
                                        home: c.match.home.name,
                                        away: c.match.away.name,
                                      ),
                                      style: Fp.body(15, weight: FontWeight.w700),
                                    ),
                                    if (explainSelection(
                                          c.offer.market,
                                          c.offer.line,
                                          c.offer.selection,
                                          home: c.match.home.name,
                                          away: c.match.away.name,
                                        )
                                        case final e?)
                                      Padding(
                                        padding: const EdgeInsets.only(top: 3),
                                        child: Text(e, style: Fp.body(12, color: Fp.text3, height: 1.35)),
                                      ),
                                  ],
                                ),
                              ),
                              const SizedBox(width: 10),
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.end,
                                children: [
                                  if (c.offer.modelProbability != null)
                                    Text(
                                      percent(c.offer.modelProbability!),
                                      style: Fp.title(17, color: Fp.accentLight),
                                    ),
                                  Text(
                                    'cote ${odds(c.offer.odds)}',
                                    style: Fp.body(12, color: Fp.text2, weight: FontWeight.w600),
                                  ),
                                ],
                              ),
                              const SizedBox(width: 12),
                              _SquareIconButton(
                                icon: Icons.close_rounded,
                                tooltip: 'Retirer',
                                onTap: busy ? null : () => state.removeFromCoupon(c),
                              ),
                            ],
                          ),
                        ),
                        const Divider(),
                      ],
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: StatTile(
                              'Probabilité combinée',
                              modelProb != null ? pct(modelProb) : '—',
                              valueColor: Fp.accentLight,
                              valueSize: 22,
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(child: StatTile('Cote totale', odds(total), valueSize: 22)),
                        ],
                      ),
                      if (modelProb != null) ...[
                        const SizedBox(height: 8),
                        Text(
                          'Probabilité déduite de la cote : ${pct(1 / total)} '
                          '(marge du bookmaker comprise). Probabilité combinée : produit des sélections, '
                          'des matchs différents étant indépendants.',
                          style: Fp.body(11, color: Fp.text3, height: 1.4),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                GlassCard.section(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text('Mise · bookmaker virtuel', style: Fp.title(15, weight: FontWeight.w600)),
                      const SizedBox(height: 6),
                      KeyValue('Solde disponible', me != null ? money(me.balance, currency) : '—'),
                      if (step == null) ...[
                        const SizedBox(height: 6),
                        Text(
                          'Montant',
                          style: Fp.body(13, weight: FontWeight.w600, color: Fp.textStrong),
                        ),
                        const SizedBox(height: 7),
                        Row(
                          children: [
                            Expanded(
                              child: TextField(
                                controller: stake,
                                keyboardType: TextInputType.number,
                                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                                onChanged: (_) => setState(() {}),
                                style: Fp.title(17, weight: FontWeight.w600),
                                decoration: InputDecoration(suffixText: currencyLabel(currency)),
                              ),
                            ),
                            const SizedBox(width: 8),
                            _AddButton('+500', () => _addStake(500)),
                            const SizedBox(width: 8),
                            _AddButton('+1 000', () => _addStake(1000)),
                          ],
                        ),
                      ] else
                        KeyValue('Mise imposée par la montante', money(step.stake, currency)),
                      const SizedBox(height: 6),
                      KeyValue('Gain possible', money(payout, currency), bold: true, valueColor: Fp.win),
                    ],
                  ),
                ),
                for (final s in steps) ...[
                  const SizedBox(height: 12),
                  _StepSwitch(
                    step: s,
                    total: total,
                    on: step?.montanteId == s.montanteId,
                    currency: currency,
                    onChanged: (v) => setState(() => useStep = v ? s : null),
                  ),
                ],
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: busy || (step != null && items.length > 3) ? null : _place,
                  child: busy
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                        )
                      : Text(step != null ? 'Jouer le palier ${step.step}' : 'Valider le coupon'),
                ),
                const SizedBox(height: 6),
                TextButton(
                  onPressed: busy ? null : _refreshOdds,
                  child: const Text('Mettre à jour les cotes'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _SquareIconButton extends StatelessWidget {
  const _SquareIconButton({required this.icon, required this.onTap, required this.tooltip});
  final IconData icon;
  final VoidCallback? onTap;
  final String tooltip;

  @override
  Widget build(BuildContext context) {
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(10),
      side: const BorderSide(color: Fp.line),
    );
    return Tooltip(
      message: tooltip,
      child: Material(
        color: Fp.fill,
        shape: shape,
        child: InkWell(
          customBorder: shape,
          onTap: onTap,
          child: SizedBox(width: 36, height: 36, child: Icon(icon, size: 18, color: Fp.text)),
        ),
      ),
    );
  }
}

class _AddButton extends StatelessWidget {
  const _AddButton(this.label, this.onTap);
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final shape = RoundedRectangleBorder(
      borderRadius: Fp.radius14,
      side: const BorderSide(color: Fp.line),
    );
    return Material(
      color: Fp.fill,
      shape: shape,
      child: InkWell(
        customBorder: shape,
        onTap: onTap,
        child: Container(
          height: 48,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          alignment: Alignment.center,
          child: Text(label, style: Fp.title(14, weight: FontWeight.w600)),
        ),
      ),
    );
  }
}

class _StepSwitch extends StatelessWidget {
  const _StepSwitch({
    required this.step,
    required this.total,
    required this.on,
    required this.currency,
    required this.onChanged,
  });
  final OpenStep step;
  final double total;
  final bool on;
  final String currency;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final inRange = total >= step.oddsMin && total <= step.oddsMax;
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 10, 12),
      decoration: BoxDecoration(
        color: on ? Fp.accentFaint : Fp.fill,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: on ? Fp.accentLine : Fp.line12),
      ),
      child: Row(
        children: [
          const Icon(Icons.stairs_rounded, color: Fp.accentLight),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Utiliser pour le palier ${step.step} de ma montante',
                  style: Fp.body(14, weight: FontWeight.w700),
                ),
                const SizedBox(height: 2),
                Text(
                  inRange
                      ? 'Mise imposée ${money(step.stake, currency)} · cote dans la plage '
                            '${odds(step.oddsMin)} – ${odds(step.oddsMax)}'
                      : 'Cote ${odds(total)} hors de la plage ${odds(step.oddsMin)} – '
                            '${odds(step.oddsMax)} du palier',
                  style: Fp.body(12, color: inRange ? Fp.text2 : Fp.lossText, height: 1.35),
                ),
              ],
            ),
          ),
          Switch(value: on, onChanged: onChanged),
        ],
      ),
    );
  }
}
