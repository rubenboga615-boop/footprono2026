import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/client.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'daily_coupons_screen.dart';
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
            padding: pagePadding(context, 26, 120, maxWidth: 1080),
            children: [
              Row(
                children: [
                  const Expanded(child: TwoToneTitle('Mon', 'coupon')),
                  if (me != null) InfoPill('Solde fictif · ${money(me.balance, currency)}'),
                ],
              ),
              const SizedBox(height: 14),
              _Banner(
                icon: Icons.star_outline_rounded,
                title: 'Coupon intelligent',
                subtitle: 'Le moteur compose un coupon pour toi',
                onTap: () =>
                    Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SmartCouponScreen())),
              ),
              const SizedBox(height: 8),
              if (items.isEmpty)
                _Banner(
                  icon: Icons.calendar_today_outlined,
                  title: 'Coupons du jour',
                  subtitle: 'Un coupon par profil chaque matin, avec son code',
                  onTap: () =>
                      Navigator.of(context)
                          .push(MaterialPageRoute(builder: (_) => const DailyCouponsScreen())),
                )
              else
                _DailyLink(
                  onTap: () =>
                      Navigator.of(context)
                          .push(MaterialPageRoute(builder: (_) => const DailyCouponsScreen())),
                ),
              const SizedBox(height: 12),
              if (items.isEmpty)
                const EmptyState(
                  'Coupon vide. Ouvre un match et touche une cote pour l\'ajouter.\n'
                  'Un combiné réunit des matchs différents (10 au maximum).',
                  icon: Icons.confirmation_number_outlined,
                )
              else ...[
                ...deskSplit(
                  context,
                  [
                    GlassCard.section(
                      padding: const EdgeInsets.fromLTRB(16, 2, 8, 2),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          for (final (i, c) in items.indexed) ...[
                            if (i > 0) const Divider(),
                            _SelectionRow(item: c, onRemove: busy ? null : () => state.removeFromCoupon(c)),
                          ],
                        ],
                      ),
                    ),
                  ],
                  [
                    const SizedBox(height: 12),
                    GlassCard.section(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          _Line('Cote totale (1xBet)', odds(total), valueStyle: Fp.title(18)),
                          _Line(
                            'Chance selon le moteur',
                            modelProb != null ? pct(modelProb) : '—',
                            valueStyle: Fp.body(15, weight: FontWeight.w800),
                          ),
                          Text(
                            [
                              if (modelProb != null && modelProb > 0)
                                '1 chance sur ${(1 / modelProb).round()}',
                              'selon la cote : ${pct(1 / total)} (marge du bookmaker comprise)',
                            ].join(' · '),
                            style: Fp.body(11.5, color: Fp.text2),
                          ),
                          const SizedBox(height: 4),
                          if (items.length >= 6)
                            Padding(
                              padding: const EdgeInsets.only(bottom: 6),
                              child: Text(
                                '${items.length} sélections : même des choix sûrs, une fois multipliés, font un '
                                'coupon risqué.',
                                style: Fp.body(12, color: Fp.warning, height: 1.4),
                              ),
                            ),
                          if (step == null) ...[
                            const SizedBox(height: 4),
                            Text(
                              'Mise (argent fictif)',
                              style: Fp.body(12.5, weight: FontWeight.w700, color: Fp.textStrong),
                            ),
                            const SizedBox(height: 8),
                            Row(
                              children: [
                                Expanded(
                                  child: TextField(
                                    controller: stake,
                                    keyboardType: TextInputType.number,
                                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                                    onChanged: (_) => setState(() {}),
                                    style: Fp.body(16, weight: FontWeight.w800),
                                  ),
                                ),
                                const SizedBox(width: 8),
                                Container(
                                  height: 52,
                                  padding: const EdgeInsets.symmetric(horizontal: 14),
                                  alignment: Alignment.center,
                                  decoration: BoxDecoration(
                                    color: Fp.fill,
                                    borderRadius: Fp.radius14,
                                    border: Border.all(color: Fp.line),
                                  ),
                                  child: Text(
                                    currencyLabel(currency),
                                    style: Fp.body(13, weight: FontWeight.w700),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                            Wrap(
                              spacing: 6,
                              children: [
                                for (final v in const [500, 1000, 5000])
                                  FpChip('+${thousands(v)}', selected: false, onTap: () => _addStake(v)),
                              ],
                            ),
                          ] else
                            _Line('Mise imposée par la montante', money(step.stake, currency)),
                          const SizedBox(height: 10),
                          _Line(
                            'Gain possible',
                            money(payout, currency),
                            valueStyle: Fp.body(17, weight: FontWeight.w800, color: const Color(0xFF6EE7B7)),
                          ),
                          const SizedBox(height: 10),
                          FilledButton(
                            onPressed: busy || (step != null && items.length > 3) ? null : _place,
                            child: busy
                                ? const SizedBox(
                                    width: 20,
                                    height: 20,
                                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                  )
                                : Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Text(step != null ? 'Jouer le palier ${step.step}' : 'Placer le pari'),
                                      const SizedBox(width: 8),
                                      const Icon(Icons.arrow_forward_rounded, size: 18),
                                    ],
                                  ),
                          ),
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
                    const SizedBox(height: 6),
                    Wrap(
                      alignment: WrapAlignment.center,
                      children: [
                        TextButton(
                          onPressed: busy ? null : _refreshOdds,
                          child: const Text('Mettre à jour les cotes'),
                        ),
                        TextButton(
                          onPressed: busy ? null : state.clearCoupon,
                          style: TextButton.styleFrom(foregroundColor: Fp.lossText),
                          child: const Text('Vider'),
                        ),
                      ],
                    ),
                  ],
                  leftWidth: 520,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Bandeau d'accès (maquette v2) : icône dans un carré violet, titre, sous-titre, flèche.
class _Banner extends StatelessWidget {
  const _Banner({required this.icon, required this.title, required this.subtitle, required this.onTap});
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(18),
      side: const BorderSide(color: Color(0x8CA78BFA)),
    );
    return Material(
      shape: shape,
      color: Colors.transparent,
      clipBehavior: Clip.antiAlias,
      child: Ink(
        decoration: const BoxDecoration(
          gradient: LinearGradient(colors: [Color(0x477C3AED), Color(0x0F7C3AED)]),
        ),
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
            child: Row(
              children: [
                Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                    color: Fp.accentAlpha(0.3),
                    borderRadius: BorderRadius.circular(11),
                  ),
                  child: Icon(icon, size: 20, color: const Color(0xFFE4D8FD)),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title, style: Fp.body(14.5, weight: FontWeight.w800)),
                      Text(subtitle, style: Fp.body(12, color: Fp.text2)),
                    ],
                  ),
                ),
                const Icon(Icons.chevron_right_rounded, color: Color(0xFFC9B2F8)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Lien compact vers les coupons du jour (coupon déjà rempli).
class _DailyLink extends StatelessWidget {
  const _DailyLink({required this.onTap});
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(14),
      side: const BorderSide(color: Fp.line12),
    );
    return Material(
      color: Fp.fill,
      shape: shape,
      child: InkWell(
        customBorder: shape,
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          child: Row(
            children: [
              const Icon(Icons.calendar_today_outlined, size: 18, color: Color(0xFFC9B2F8)),
              const SizedBox(width: 10),
              Expanded(
                child: Text('Coupons du jour', style: Fp.body(13, weight: FontWeight.w700)),
              ),
              const Icon(Icons.chevron_right_rounded, size: 18, color: Color(0xFFC9B2F8)),
            ],
          ),
        ),
      ),
    );
  }
}

/// Sélection du coupon : libellé, match et chance du moteur, cote, croix pour retirer.
class _SelectionRow extends StatelessWidget {
  const _SelectionRow({required this.item, required this.onRemove});
  final CouponItem item;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final c = item;
    final model = c.offer.modelProbability;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  fullLabel(
                    c.offer.market,
                    c.offer.line,
                    c.offer.selection,
                    home: c.match.home.name,
                    away: c.match.away.name,
                  ),
                  style: Fp.body(14.5, weight: FontWeight.w800),
                ),
                const SizedBox(height: 2),
                Text(
                  [
                    '${c.match.home.name} – ${c.match.away.name}',
                    if (model != null) 'moteur ${percent(model)}',
                  ].join(' · '),
                  style: Fp.body(12, color: Fp.text2),
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
                    child: Text(e, style: Fp.body(11.5, color: const Color(0xFFC9B2F8), height: 1.35)),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Text(odds(c.offer.odds), style: Fp.body(15, weight: FontWeight.w800)),
          IconButton(
            tooltip: 'Retirer',
            onPressed: onRemove,
            icon: const Icon(Icons.close_rounded, size: 20, color: Fp.text2),
          ),
        ],
      ),
    );
  }
}

/// Ligne libellé / valeur de la carte de mise.
class _Line extends StatelessWidget {
  const _Line(this.label, this.value, {this.valueStyle});
  final String label;
  final String value;
  final TextStyle? valueStyle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        children: [
          Expanded(
            child: Text(label, style: Fp.body(14, color: Fp.text2)),
          ),
          Text(value, style: valueStyle ?? Fp.body(14, weight: FontWeight.w700)),
        ],
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
