import 'dart:math' as math;

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
import '../widgets/maquette.dart';
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

  /// Maquette N5 : récapitulatif avant de placer le pari (argent fictif).
  Future<void> _confirmPlace() async {
    final state = context.read<AppState>();
    final items = [...state.coupon];
    if (useStep != null || items.any((c) => c.match.started)) return _place();
    final amount = int.tryParse(stake.text.replaceAll(RegExp(r'\D'), '')) ?? 0;
    final total = totalOdds(items);
    final probs = items.map((c) => c.offer.modelProbability).toList();
    final p = probs.contains(null) ? null : probs.fold<double>(1, (a, v) => a * v!);
    final ok = await showModalBottomSheet<bool>(
      context: context,
      backgroundColor: Fp.card,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Placer ce pari ?', style: Fp.body(20, weight: FontWeight.w800)),
              const SizedBox(height: 4),
              Text('Argent fictif : rien n\'est misé pour de vrai.', style: Fp.body(13, color: Fp.muted)),
              const SizedBox(height: 10),
              _Line('${items.length} sélection${items.length > 1 ? 's' : ''} · cote', odds(total)),
              _Line('Mise', money(amount)),
              _Line('Tu récupères si tout passe', money((amount * total).floor())),
              if (p != null)
                _Line(
                  'Chance selon le moteur',
                  [percent(p, decimals: p < 0.995 ? 1 : 0), chanceInWords(p)].join(' · '),
                ),
              const SizedBox(height: 12),
              SizedBox(
                height: 52,
                child: FilledButton(
                  onPressed: () => Navigator.pop(context, true),
                  style: FilledButton.styleFrom(shape: const StadiumBorder()),
                  child: Text(
                    'Confirmer · ${thousands(amount)} F',
                    style: Fp.body(16, weight: FontWeight.w700),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              SizedBox(
                height: 48,
                child: OutlinedButton(
                  onPressed: () => Navigator.pop(context, false),
                  style: OutlinedButton.styleFrom(
                    shape: const StadiumBorder(),
                    side: const BorderSide(color: Fp.line),
                  ),
                  child: const Text('Annuler'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
    if (ok == true) await _place();
  }

  Future<void> _place({bool acceptOutOfRange = false}) async {
    final state = context.read<AppState>();
    final items = [...state.coupon];
    final amount = int.tryParse(stake.text.replaceAll(RegExp(r'\D'), '')) ?? 0;
    // Match commencé : le serveur refuserait tout le coupon (essai du 07/11/2026 : message
    // « match 106064 déjà commencé »). Le dire avec le nom du match, et proposer de le retirer.
    final started = [
      for (final c in items)
        if (c.match.started) c,
    ];
    if (started.isNotEmpty) {
      final names = [for (final c in started) '${c.match.home.name} – ${c.match.away.name}'].join(', ');
      showMessage(
        '$names ${started.length > 1 ? 'ont' : 'a'} commencé : paris fermés. Retire-${started.length > 1 ? 'les' : 'le'} '
        'du coupon.',
        error: true,
        action: SnackBarAction(
          label: 'Retirer',
          onPressed: () {
            for (final c in started) {
              state.removeFromCoupon(c);
            }
          },
        ),
      );
      return;
    }
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
      showMessage('Pari placé. Suivi dans l\'onglet Mes paris.');
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
            ? 'Cotes mises à jour ; $removed sélection${removed > 1 ? 's' : ''} retirée${removed > 1 ? 's' : ''} : '
                  'plus de cote disponible.'
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

  /// « Vider » demande confirmation (essai du 07/11/2026 : 10 sélections effacées d'un appui).
  Future<void> _confirmClear(AppState state, int count) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Vider le coupon ?'),
        content: Text('Retirer ${count > 1 ? 'les $count sélections' : 'la sélection'} du coupon ?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Vider')),
        ],
      ),
    );
    if (ok == true) state.clearCoupon();
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
              // Maquette C3 du 07/11/2026 : titre et solde fictif dans une pastille.
              Row(
                children: [
                  const Expanded(child: MTitle('Mon', 'coupon', 26)),
                  if (me != null)
                    Tooltip(message: 'Solde fictif', child: MOutlinePill(money(me.balance, currency))),
                ],
              ),
              const SizedBox(height: 12),
              const OddsDownBanner(),
              // Coupon vide : les deux entrées vers les coupons du moteur.
              if (items.isEmpty) ...[
                _Banner(
                  icon: Icons.star_outline_rounded,
                  title: 'Coupon intelligent',
                  subtitle: 'Le moteur compose un coupon pour toi',
                  onTap: () =>
                      Navigator.of(context)
                          .push(MaterialPageRoute(builder: (_) => const SmartCouponScreen())),
                ),
                const SizedBox(height: 8),
                _Banner(
                  icon: Icons.calendar_today_outlined,
                  title: 'Coupons du jour',
                  subtitle: 'Un coupon par profil chaque matin, avec son code',
                  onTap: () =>
                      Navigator.of(context)
                          .push(MaterialPageRoute(builder: (_) => const DailyCouponsScreen())),
                ),
                const SizedBox(height: 12),
              ],
              if (items.isEmpty)
                const EmptyState(
                  'Coupon vide. Ouvre un match et touche une cote pour l\'ajouter.\n'
                  'Un combiné réunit des matchs différents (${AppState.maxCoupon} au maximum).',
                  icon: Icons.confirmation_number_outlined,
                )
              else ...[
                ...deskSplit(
                  context,
                  [
                    // Maquette N6 : match commencé, dit en haut avec son nom, et « Retirer ce match ».
                    for (final c in items.where((c) => c.match.started))
                      _StartedWarning(item: c, onRemove: busy ? null : () => state.removeFromCoupon(c)),
                    GlassCard.section(
                      padding: const EdgeInsets.fromLTRB(14, 0, 6, 0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          for (final (i, c) in items.indexed) ...[
                            if (i > 0) const Divider(height: 1, color: Fp.divider),
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
                          _Line(
                            'Cote totale · ${items.length} sélection${items.length > 1 ? 's' : ''}',
                            odds(total),
                            valueStyle: Fp.body(20, weight: FontWeight.w800),
                          ),
                          _Line(
                            'Chance selon le moteur',
                            modelProb == null
                                ? '—'
                                : [pct(modelProb), if (modelProb > 0) chanceInWords(modelProb)].join(' · '),
                            valueStyle: Fp.body(14, weight: FontWeight.w700),
                          ),
                          Text(
                            'Selon la cote 1xBet : ${pct(1 / total)} (marge du bookmaker comprise)',
                            style: Fp.body(11.5, color: Fp.muted),
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
                              style: Fp.body(12, weight: FontWeight.w600, color: Fp.muted),
                            ),
                            const SizedBox(height: 6),
                            // Maquette C3 : champ sombre, la devise à droite dans le champ.
                            TextField(
                              controller: stake,
                              keyboardType: TextInputType.number,
                              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                              onChanged: (_) => setState(() {}),
                              style: Fp.body(16, weight: FontWeight.w700),
                              decoration: InputDecoration(
                                filled: true,
                                fillColor: Fp.background,
                                contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
                                suffixText: currencyLabel(currency),
                                suffixStyle: Fp.body(13, color: Fp.muted),
                                enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(14),
                                  borderSide: const BorderSide(color: Fp.line12),
                                ),
                                focusedBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(14),
                                  borderSide: const BorderSide(color: Fp.accent2),
                                ),
                              ),
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
                          // Mise comprise, puis le bénéfice net (essai du 07/11/2026 : « Gain possible
                          // 1 200 F » laissait croire que l'on gagnait 1 200 F en plus de sa mise).
                          // Maquette C3 : ce qui revient au joueur, mise comprise, et le bénéfice en vert
                          // (essai du 07/11/2026 : « Gain possible » laissait croire à un gain en plus).
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 5),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    'Tu récupères si tout passe',
                                    style: Fp.body(13, color: Fp.muted),
                                  ),
                                ),
                                Text.rich(
                                  TextSpan(
                                    children: [
                                      TextSpan(text: '${thousands(payout)} F '),
                                      TextSpan(
                                        text: '(+${thousands(math.max(0, payout - amount))})',
                                        style: const TextStyle(color: Fp.win),
                                      ),
                                    ],
                                  ),
                                  style: Fp.body(15, weight: FontWeight.w700),
                                ),
                              ],
                            ),
                          ),
                          if (items.length >= 6)
                            Text(
                              '${items.length} sélections : même des choix sûrs, une fois multipliés, font un '
                              'coupon risqué.',
                              style: Fp.body(12.5, color: Fp.warning, height: 1.4),
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        SizedBox(
                          width: 96,
                          height: 48,
                          child: OutlinedButton(
                            onPressed: busy ? null : () => _confirmClear(state, items.length),
                            style: OutlinedButton.styleFrom(
                              shape: const StadiumBorder(),
                              side: const BorderSide(color: Fp.line),
                              padding: EdgeInsets.zero,
                            ),
                            child: Text('Vider', style: Fp.body(15, weight: FontWeight.w600)),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: SizedBox(
                            height: 52,
                            child: FilledButton(
                              onPressed: busy || (step != null && items.length > 3) ? null : _confirmPlace,
                              style: FilledButton.styleFrom(shape: const StadiumBorder()),
                              child: busy
                                  ? const SizedBox(
                                      width: 20,
                                      height: 20,
                                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                    )
                                  : FittedBox(
                                      child: Text(
                                        step != null
                                            ? 'Jouer le palier ${step.step}'
                                            : 'Placer le pari · ${thousands(amount)} F',
                                        style: Fp.body(16, weight: FontWeight.w700),
                                      ),
                                    ),
                            ),
                          ),
                        ),
                      ],
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
                    Center(
                      child: TextButton(
                        onPressed: busy ? null : _refreshOdds,
                        child: const Text('Mettre à jour les cotes'),
                      ),
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
                if (c.match.started)
                  Padding(
                    padding: const EdgeInsets.only(top: 3),
                    child: Text(
                      'Match commencé : paris fermés, retire-le du coupon',
                      style: Fp.body(11.5, color: Fp.warning, weight: FontWeight.w700),
                    ),
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

/// Solde fictif (maquette C3 : pastille à bordure, texte violet clair).
/// Maquette N6 : un match du coupon a commencé ; le dire avec son nom et le retirer d'un appui.
class _StartedWarning extends StatelessWidget {
  const _StartedWarning({required this.item, required this.onRemove});
  final CouponItem item;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) => Container(
    margin: const EdgeInsets.only(bottom: 12),
    padding: const EdgeInsets.fromLTRB(12, 11, 12, 6),
    decoration: BoxDecoration(
      color: const Color(0xFF3A1620),
      borderRadius: BorderRadius.circular(14),
      border: Border.all(color: const Color(0xFF6B2333)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text.rich(
          TextSpan(
            children: [
              TextSpan(
                text: '${item.match.home.name} – ${item.match.away.name} a commencé',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              const TextSpan(
                text: ' : les paris sont fermés sur ce match. Retire-le pour placer le reste du coupon.',
              ),
            ],
          ),
          style: Fp.body(13, color: const Color(0xFFFFD0D7), height: 1.4),
        ),
        TextButton(
          onPressed: onRemove,
          style: TextButton.styleFrom(foregroundColor: Fp.loss, padding: EdgeInsets.zero),
          child: const Text('Retirer ce match'),
        ),
      ],
    ),
  );
}
