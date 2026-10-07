import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../desktop/layout.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'share_coupon.dart';
import 'smart_coupon_screen.dart';

/// Jour des coupons du jour : celui du serveur (UTC, heure de la Côte d'Ivoire).
DateTime _serverDay(int offset) {
  final now = DateTime.now().toUtc();
  return DateTime.utc(now.year, now.month, now.day).add(Duration(days: offset));
}

String _iso(DateTime d) =>
    '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

/// Copie le code de réservation et dit quoi en faire.
Future<void> copyBookingCode(Json booking) async {
  await Clipboard.setData(ClipboardData(text: booking['code'] as String));
  showMessage('Code ${booking['code']} copié : colle-le dans ${booking['label']}.');
}

Widget _statusTag(Json c) => switch (c['display_status']) {
  'won' => const Tag.win('Gagné'),
  'lost' => const Tag.loss('Perdu'),
  'live' => const Tag('En cours', color: Fp.warning),
  'upcoming' => const Tag('À venir'),
  final s => Tag(resultLabel(s as String)),
};

/// Coupons du jour : un coupon par profil, enregistré chaque matin avant les matchs, avec
/// sa chance estimée, son état en direct et le code du bookmaker à copier.
class DailyCouponsScreen extends StatefulWidget {
  const DailyCouponsScreen({super.key});

  @override
  State<DailyCouponsScreen> createState() => _DailyCouponsScreenState();
}

class _DailyCouponsScreenState extends State<DailyCouponsScreen> {
  int offset = 0; // 0 : aujourd'hui, -1 : hier
  Timer? _timer;
  Future<void> Function()? _reload;

  @override
  void initState() {
    super.initState();
    // Matchs en cours : l'état se met à jour toute seule, une fois par minute.
    _timer = Timer.periodic(const Duration(minutes: 1), (_) => _reload?.call());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    final day = _serverDay(offset);
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          key: ValueKey(offset),
          load: () async => await api.get('/smart-coupons/day', {'day': _iso(day)}) as Json,
          builder: (context, data, reload) {
            _reload = reload;
            final coupons = (data['coupons'] as List).cast<Json>();
            final summary = (data['summary'] as Map).cast<String, dynamic>();
            final yesterday = (summary['yesterday'] as Map).cast<String, dynamic>();
            final month = (summary['last_30_days'] as Map).cast<String, dynamic>();
            final byProfile = (summary['last_30_days_by_profile'] as Map?)?.cast<String, dynamic>();
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: pagePadding(context, 16, 120, maxWidth: 1080),
                children: [
                  const BackHeader('Coupons', 'du jour'),
                  const SizedBox(height: 14),
                  const OddsDownBanner(),
                  if (byProfile == null)
                    Row(
                      children: [
                        Expanded(child: KeyTile('Hier', _record(yesterday))),
                        const SizedBox(width: 8),
                        Expanded(child: KeyTile('30 derniers jours', _record(month))),
                      ],
                    )
                  else ...[
                    KeyTile('Hier', _record(yesterday)),
                    const SizedBox(height: 8),
                    ProfileRecordCard('30 derniers jours', byProfile),
                  ],
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      for (final (o, label) in const [(-1, 'Hier'), (0, 'Aujourd\'hui')]) ...[
                        FpChip(label, selected: offset == o, onTap: () => setState(() => offset = o)),
                        const SizedBox(width: 8),
                      ],
                    ],
                  ),
                  if (coupons.any((c) => c['locked'] != true && (c['booking_codes'] as List).isNotEmpty)) ...[
                    const SizedBox(height: 10),
                    Text(
                      'Copie le code et colle-le chez le bookmaker : le coupon s\'y remplit tout seul.',
                      style: Fp.body(12, color: Fp.text2, height: 1.4),
                    ),
                  ],
                  const SizedBox(height: 12),
                  if (coupons.isEmpty)
                    EmptyState(
                      offset == 0
                          ? 'Les coupons du jour sont publiés chaque matin vers 8 h.'
                          : 'Aucun coupon ce jour-là.',
                      icon: Icons.confirmation_number_outlined,
                    ),
                  ...deskColumns(context, [
                    for (final c in coupons)
                      _DailyCouponCard(
                        c,
                        onTap: c['locked'] == true
                            ? () => openPremium(context)
                            : () =>
                                  Navigator.of(context)
                                      .push(MaterialPageRoute(builder: (_) => DailyCouponDetail(coupon: c))),
                      ),
                  ]),
                  if (coupons.any((c) => c['locked'] == true)) ...[
                    const _UnlockCard(),
                    const SizedBox(height: 8),
                    Text(
                      'Les coupons terminés restent visibles en entier par tous dans l\'historique : rien '
                      'n\'est trié ni effacé.',
                      style: Fp.body(11.5, color: Fp.text2, height: 1.45),
                    ),
                  ],
                  const SizedBox(height: 8),
                  Center(
                    child: Tooltip(
                      message: 'Historique complet',
                      child: TextButton(
                        onPressed: () =>
                            Navigator.of(context)
                                .push(MaterialPageRoute(builder: (_) => const SmartHistoryScreen())),
                        child: const Text('Voir l\'historique des coupons'),
                      ),
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

  static String _record(Map<String, dynamic> r) =>
      r['settled'] == 0 ? 'aucun coupon réglé' : '${r['won']} gagné(s) sur ${r['settled']}';
}

class _DailyCouponCard extends StatelessWidget {
  const _DailyCouponCard(this.c, {required this.onTap});
  final Json c;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final count = (c['selection_count'] as int?) ?? (c['selections'] as List).length;
    final locked = c['locked'] == true;
    final validated = c['validated'] as int;
    final first = c['first_kickoff'] as String?;
    final codes = (c['booking_codes'] as List).cast<Json>();
    final key = '${c['profile']}';
    final color = switch (key) {
      'sur' => Fp.win,
      'audacieux' || 'grosse' => Fp.lossText,
      _ => Fp.accentLight,
    };
    return GlassCard.section(
      margin: const EdgeInsets.only(bottom: 12),
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Maquette v2 : profil, nombre de sélections et cote, chance du moteur à droite.
          Row(
            children: [
              Tag('${c['profile_label']}'.toUpperCase(), color: color),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  '$count sélection${count > 1 ? 's' : ''} · cote ${odds(c['total_odds'])}',
                  style: Fp.body(14.5, weight: FontWeight.w800),
                ),
              ),
              Text(percent((c['probability'] as num).toDouble()), style: Fp.title(17)),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              _statusTag(c),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  [
                    '$validated / $count validée${validated > 1 ? 's' : ''}',
                    if (first != null) 'premier match ${hourMinute(DateTime.parse(first).toLocal())}',
                  ].join(' · '),
                  style: Fp.body(12.5, color: Fp.text2),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ProbBar(count == 0 ? 0 : validated / count, color: Fp.win),
          const SizedBox(height: 12),
          if (locked)
            Row(
              children: [
                const Icon(Icons.lock_outline_rounded, size: 16, color: Color(0xFFC9B2F8)),
                const SizedBox(width: 8),
                Flexible(
                  child: Text('Sélections et code dans Premium', style: Fp.body(12.5, color: Fp.text2)),
                ),
              ],
            )
          else if (codes.isEmpty)
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0x66000000),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0x52A78BFA)),
              ),
              child: Text('Code bientôt disponible', style: Fp.body(12.5, color: Fp.text2)),
            )
          else
            for (final b in codes) BookingCodeRow(b),
        ],
      ),
    );
  }
}

/// Ouvre l'onglet Profil, où l'on passe Premium (l'écran ouvert par-dessus est refermé).
void openPremium(BuildContext context) {
  Navigator.of(context).popUntil((r) => r.isFirst);
  context.read<AppState>().openTab(4);
}

/// Version gratuite : les coupons du jour (sélections et code) sont dans Premium.
class _UnlockCard extends StatelessWidget {
  const _UnlockCard();

  @override
  Widget build(BuildContext context) {
    return GradientCard(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Débloquer les coupons du jour', style: Fp.body(15, weight: FontWeight.w800)),
          const SizedBox(height: 4),
          Text(
            'Chaque matin : les sélections, la chance et le code 1xBet. Premium · 2 000 F CFA / mois.',
            style: Fp.body(12.5, color: Fp.text2, height: 1.4),
          ),
          const SizedBox(height: 10),
          FilledButton(
            onPressed: () => openPremium(context),
            style: FilledButton.styleFrom(
              backgroundColor: Colors.white,
              foregroundColor: const Color(0xFF2E1065),
              minimumSize: const Size(0, 40),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              textStyle: Fp.body(13, weight: FontWeight.w800),
            ),
            child: const Text('Passer Premium'),
          ),
        ],
      ),
    );
  }
}

/// « 1XBET  7HQ2K  [Copier] »
class BookingCodeRow extends StatelessWidget {
  const BookingCodeRow(this.booking, {super.key});
  final Json booking;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
      decoration: BoxDecoration(
        color: const Color(0x66000000),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0x52A78BFA)),
      ),
      child: Row(
        children: [
          Text('Code ${booking['label']}', style: Fp.body(11.5, color: Fp.text2)),
          const SizedBox(width: 10),
          Expanded(
            child: SelectableText(
              '${booking['code']}',
              style: const TextStyle(
                fontFamily: 'monospace',
                fontSize: 16,
                fontWeight: FontWeight.w700,
                letterSpacing: 2,
                color: Fp.text,
              ),
            ),
          ),
          FilledButton(
            onPressed: () => copyBookingCode(booking),
            style: FilledButton.styleFrom(visualDensity: VisualDensity.compact),
            child: const Text('Copier'),
          ),
        ],
      ),
    );
  }
}

/// Détail d'un coupon du jour : chaque sélection et son état, le code, le partage.
class DailyCouponDetail extends StatelessWidget {
  const DailyCouponDetail({super.key, required this.coupon});
  final Json coupon;

  @override
  Widget build(BuildContext context) {
    final sels = (coupon['selections'] as List).cast<Json>();
    final codes = (coupon['booking_codes'] as List).cast<Json>();
    final probs = [for (final s in sels) percent((s['model_probability'] as num).toDouble())];
    final p = (coupon['probability'] as num).toDouble();
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: ListView(
          padding: pagePadding(context, 16, 120, maxWidth: 820),
          children: [
            BackHeader(
              '${coupon['profile_label']}',
              ' · ${odds(coupon['total_odds'])}',
              joined: true,
              trailing: _statusTag(coupon),
            ),
            const SizedBox(height: 14),
            GlassCard.section(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (codes.isEmpty)
                    Text('Code bientôt disponible.', style: Fp.body(13, color: Fp.text3))
                  else
                    for (final b in codes) BookingCodeRow(b),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      OutlinedButton.icon(
                        onPressed: () => shareCoupon(context, sels, coupon, '${coupon['profile_label']}'),
                        icon: const Icon(Icons.ios_share_rounded, size: 18),
                        label: const Text('Partager en image'),
                      ),
                      OutlinedButton.icon(
                        onPressed: () => addSelectionsToCoupon(context.read<AppState>(), sels),
                        icon: const Icon(Icons.add_rounded, size: 18),
                        label: const Text('Ajouter à mon coupon'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            GlassCard.section(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [for (final s in sels) _LiveSelection(s)],
              ),
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Fp.warning.withValues(alpha: .08),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: Fp.warning.withValues(alpha: .25)),
              ),
              child: Text(
                'Chance du coupon : ${probs.join(' × ')} ≈ ${percent(p)}. Sur 100 coupons comme '
                'celui-ci, environ ${(p * 100).round()} passent.',
                style: Fp.body(12, color: Fp.text2, height: 1.4),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LiveSelection extends StatelessWidget {
  const _LiveSelection(this.s);
  final Json s;

  @override
  Widget build(BuildContext context) {
    final home = s['home'] as String, away = s['away'] as String;
    final result = (s['result'] ?? 'pending') as String;
    final score = (s['score'] as List?)?.cast<int?>();
    final scoreText = score == null ? '' : ' · ${score[0]}-${score[1]}';
    final kickoff = s['kickoff_at'] as String?;
    final (Color dot, String state) = switch (s['state']) {
      'live' => (Fp.warning, 'en cours${s['minute'] == null ? '' : ' ${s['minute']}\''}$scoreText'),
      'finished' => (Fp.text2, 'terminé$scoreText'),
      'settled' => (
        result == 'win' || result == 'half_win' ? Fp.win : (result == 'loss' ? Fp.loss : Fp.text2),
        '${resultLabel(result).toLowerCase()}$scoreText',
      ),
      _ => (
        Fp.text3,
        kickoff == null ? 'à venir' : 'à venir · ${hourMinute(DateTime.parse(kickoff).toLocal())}',
      ),
    };
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 6, right: 10),
            child: Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: dot, shape: BoxShape.circle),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('$home – $away', style: Fp.body(14, weight: FontWeight.w600)),
                Text(
                  selectionLabel(
                    s['market'] as String,
                    (s['line'] ?? '') as String,
                    s['selection'] as String,
                    home: home,
                    away: away,
                  ),
                  style: Fp.body(12, color: Fp.text2),
                ),
                Text(state, style: Fp.body(12, color: dot)),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(odds(s['odds']), style: Fp.title(15)),
              Text(
                percent((s['model_probability'] as num).toDouble()),
                style: Fp.body(12, color: Fp.accentLight, weight: FontWeight.w600),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
