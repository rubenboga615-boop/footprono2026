import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Coupon intelligent : la sélection la plus sûre de chaque match (selon le profil),
/// sur une période au choix, avec de vraies cotes et des faits pour chaque choix.
class SmartCouponScreen extends StatefulWidget {
  const SmartCouponScreen({super.key});

  static const profiles = [
    ('sur', 'Sûr', '75 à 92 % par sélection'),
    ('equilibre', 'Équilibré', '60 à 75 % par sélection'),
    ('audacieux', 'Audacieux', '45 à 60 % par sélection'),
  ];
  static const periods = [
    ('today', 'Aujourd\'hui'),
    ('tomorrow', 'Demain'),
    ('3days', '3 jours'),
    ('weekend', 'Ce week-end'),
    ('week', '7 jours'),
    ('next', 'Prochaine journée'),
  ];

  @override
  State<SmartCouponScreen> createState() => _SmartCouponScreenState();
}

class _SmartCouponScreenState extends State<SmartCouponScreen> {
  int profile = 1;
  int period = 5; // Prochaine journée : jamais vide pendant une trêve
  int size = 3;
  bool busy = false;
  Json? result;
  Object? error;

  Future<void> _generate() async {
    final api = context.read<AppState>().api;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final r = await api.get('/smart-coupon', {
        'profile': SmartCouponScreen.profiles[profile].$1,
        'period': SmartCouponScreen.periods[period].$1,
        'size': '$size',
      }) as Json;
      if (mounted) setState(() => result = r);
    } catch (e) {
      if (mounted) setState(() => error = e);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  /// Ajoute des sélections au coupon, aux cotes actuelles (relues sur le serveur).
  Future<void> _addToCoupon(List<Json> selections) async {
    final state = context.read<AppState>();
    setState(() => busy = true);
    var added = 0, missing = 0;
    try {
      for (final s in selections) {
        final id = s['match_id'] as int;
        final match = MatchInfo(await state.api.get('/matches/$id') as Json);
        final key = '${s['market']}|${s['line'] ?? ''}|${s['selection']}';
        final offers = [for (final o in await state.api.get('/matches/$id/offer') as List) Offer(o as Json)];
        final offer = offers.where((o) => o.key == key).firstOrNull;
        if (offer == null) {
          missing++;
        } else if (!state.inCoupon(id, key)) {
          state.toggleCoupon(match, offer);
          added++;
        }
      }
      showMessage(
        missing > 0
            ? '$added sélection(s) ajoutée(s) ; $missing sans cote disponible à présent.'
            : '$added sélection(s) ajoutée(s) au coupon (onglet Coupon).',
      );
    } on ApiException catch (e) {
      showMessage(e.message, error: true);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final premium = context.watch<AppState>().premium;
    final (_, _, range) = SmartCouponScreen.profiles[profile];
    final coupon = result?['coupon'] as Json?;
    final alternatives = ((result?['alternatives'] as List?) ?? const []).cast<Json>();
    final message = result?['message'] as String?;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(18, 16, 18, 40),
          children: [
            BackHeader(
              'Coupon',
              'intelligent',
              subtitle:
                  'Dans chaque match, la sélection la plus probable du profil choisi, avec une vraie '
                  'cote. Jamais deux sélections du même match.',
              trailing: SquareButton(
                icon: Icons.history_rounded,
                tooltip: 'Coupons du jour',
                onTap: () =>
                    Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SmartHistoryScreen())),
              ),
            ),
            const SizedBox(height: 18),
            if (!premium) ...[
              const PremiumLock(
                text:
                    'Le Coupon intelligent est inclus dans Premium. Les coupons du jour et leur bilan '
                    '(bouton historique en haut) restent publics.',
              ),
            ] else ...[
              const SectionTitle('Profil'),
              SegmentTabs(
                labels: [for (final p in SmartCouponScreen.profiles) p.$2],
                selected: profile,
                onSelected: (i) => setState(() => profile = i),
              ),
              const SizedBox(height: 6),
              Text(range, style: Fp.body(12, color: Fp.text3)),
              const SectionTitle('Période des matchs'),
              // Toutes les périodes visibles d'un coup (pas de défilement caché).
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final (i, p) in SmartCouponScreen.periods.indexed)
                    FpChip(p.$2, selected: i == period, onTap: () => setState(() => period = i)),
                ],
              ),
              const SectionTitle('Nombre de sélections'),
              ChipRow(
                labels: const ['1', '2', '3', '4'],
                selected: size - 1,
                onSelected: (i) => setState(() => size = i + 1),
              ),
              const SizedBox(height: 18),
              FilledButton(
                onPressed: busy ? null : _generate,
                child: Text(busy ? 'Recherche…' : 'Composer le coupon'),
              ),
              const SizedBox(height: 18),
              if (error != null) ErrorPanel(error: error!),
              if (message != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(message, style: Fp.body(13, color: Fp.warning, height: 1.4)),
                ),
              if (coupon != null) ...[
                _CouponCard(coupon: coupon, onAdd: busy ? null : () => _addToCoupon(_sels(coupon))),
                if (alternatives.isNotEmpty) ...[
                  const SectionTitle('Autres choix (moins sûrs)'),
                  for (final s in alternatives)
                    GlassCard.section(
                      margin: const EdgeInsets.only(bottom: 10),
                      child: _SelectionRow(
                        s,
                        trailing: IconButton(
                          tooltip: 'Ajouter au coupon',
                          icon: const Icon(Icons.add_circle_outline_rounded, color: Fp.accentLight),
                          onPressed: busy ? null : () => _addToCoupon([s]),
                        ),
                      ),
                    ),
                ],
                const SizedBox(height: 12),
                Text(
                  'Probabilité estimée : produit des probabilités du moteur, mesurée juste sur 2022-2025 '
                  '(prudente pour « Sûr »). La cote du bookmaker contient sa marge : ce coupon ne promet '
                  'aucun gain et ne bat pas le bookmaker à long terme. Rien n\'est joué sans ta validation.',
                  style: Fp.body(12, color: Fp.text3, height: 1.4),
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }

  static List<Json> _sels(Json coupon) => (coupon['selections'] as List).cast<Json>();
}

class _CouponCard extends StatelessWidget {
  const _CouponCard({required this.coupon, required this.onAdd});
  final Json coupon;
  final VoidCallback? onAdd;

  @override
  Widget build(BuildContext context) {
    final sels = (coupon['selections'] as List).cast<Json>();
    final p = (coupon['probability'] as num).toDouble();
    final implied = (coupon['implied_probability'] as num).toDouble();
    return GlassCard.section(
      highlight: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final (i, s) in sels.indexed) ...[if (i > 0) const Divider(height: 22), _SelectionRow(s)],
          const Divider(height: 26),
          Row(
            children: [
              Expanded(child: StatTile('Cote totale', odds(coupon['total_odds']), valueSize: 20)),
              const SizedBox(width: 8),
              Expanded(
                child: StatTile(
                  'Probabilité estimée',
                  percent(p, decimals: 1),
                  valueColor: Fp.accentLight,
                  valueSize: 20,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Selon la cote (marge comprise) : ${percent(implied, decimals: 1)}.',
            style: Fp.body(12, color: Fp.text3),
          ),
          const SizedBox(height: 14),
          FilledButton(onPressed: onAdd, child: const Text('Mettre dans mon coupon')),
        ],
      ),
    );
  }
}

class _SelectionRow extends StatelessWidget {
  const _SelectionRow(this.s, {this.trailing});
  final Json s;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final home = s['home'] as String, away = s['away'] as String;
    final kickoff = parseDate(s['kickoff_at'])?.toLocal();
    final reasons = ((s['reasons'] as List?) ?? const []).cast<String>();
    final result = s['result'] as String?;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                fullLabel(
                  s['market'] as String,
                  (s['line'] ?? '') as String,
                  s['selection'] as String,
                  home: home,
                  away: away,
                ), // fmt
                style: Fp.body(15, weight: FontWeight.w700),
              ),
              const SizedBox(height: 2),
              Text(
                '$home – $away · ${competitionName(s['competition'] as String)}'
                '${kickoff != null ? ' · ${shortDate(kickoff)} ${hourMinute(kickoff)}' : ''}',
                style: Fp.body(12, color: Fp.text2),
              ),
              for (final r in reasons)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text('• $r', style: Fp.body(12, color: Fp.text3, height: 1.35)),
                ),
            ],
          ),
        ),
        const SizedBox(width: 10),
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(
              percent((s['model_probability'] as num).toDouble()),
              style: Fp.title(16, color: Fp.accentLight),
            ),
            Text(
              'cote ${odds(s['odds'])}',
              style: Fp.body(12, color: Fp.text2, weight: FontWeight.w600),
            ),
            if (result != null && result != 'pending') ...[
              const SizedBox(height: 4),
              result == 'win' || result == 'half_win'
                  ? Tag.win(resultLabel(result))
                  : result == 'loss' || result == 'half_loss'
                  ? Tag.loss(resultLabel(result))
                  : Tag(resultLabel(result)),
            ],
          ],
        ),
        ?trailing,
      ],
    );
  }
}

/// Coupons du jour : enregistrés chaque matin avant les matchs, gagnés ou perdus, rien n'est effacé.
class SmartHistoryScreen extends StatelessWidget {
  const SmartHistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          load: () async => await api.get('/smart-coupons/history') as Json,
          builder: (context, data, reload) {
            final stats = (data['stats'] as Map).cast<String, dynamic>();
            final coupons = (data['coupons'] as List).cast<Json>();
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(18, 16, 18, 40),
                children: [
                  const BackHeader(
                    'Coupons',
                    'du jour',
                    subtitle:
                        'Chaque matin, un coupon par profil est enregistré avant les matchs. Tous restent '
                        'affichés, gagnés ou perdus : c\'est le vrai bilan du Coupon intelligent.',
                  ),
                  const SizedBox(height: 16),
                  GlassCard.section(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text('Bilan', style: Fp.title(15, weight: FontWeight.w600)),
                        for (final st in stats.values.cast<Json>())
                          KeyValue(
                            st['label'] as String,
                            st['settled'] == 0
                                ? 'aucun coupon réglé'
                                : '${st['won']} gagné(s) sur ${st['settled']} · annoncé '
                                      '${percent((st['announced'] as num).toDouble())}, '
                                      'observé ${percent((st['observed'] as num).toDouble())}',
                          ),
                        const SizedBox(height: 4),
                        Text(
                          'Sur peu de coupons, l\'écart entre annoncé et observé est surtout du hasard.',
                          style: Fp.body(11, color: Fp.text3),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  if (coupons.isEmpty)
                    const EmptyState('Aucun coupon du jour pour l\'instant.', icon: Icons.history_rounded),
                  for (final c in coupons)
                    GlassCard.section(
                      margin: const EdgeInsets.only(bottom: 12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  '${c['profile_label']} · ${shortDate(DateTime.parse(c['day'] as String))}',
                                  style: Fp.title(14, weight: FontWeight.w600),
                                ),
                              ),
                              switch (c['status']) {
                                'won' => const Tag.win('Gagné'),
                                'lost' => const Tag.loss('Perdu'),
                                'pending' => const Tag('En cours'),
                                final s => Tag(resultLabel(s as String)),
                              },
                            ],
                          ),
                          const SizedBox(height: 10),
                          for (final s in (c['selections'] as List).cast<Json>())
                            Padding(padding: const EdgeInsets.only(bottom: 10), child: _SelectionRow(s)),
                          Text(
                            'Cote ${odds(c['total_odds'])} · probabilité annoncée '
                            '${percent((c['probability'] as num).toDouble(), decimals: 1)}',
                            style: Fp.body(12, color: Fp.text2),
                          ),
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
