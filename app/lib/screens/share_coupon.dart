import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../share/share_bridge.dart';

import 'package:provider/provider.dart';

import '../state/app_state.dart' show AppState, showMessage;
import '../theme.dart';
import '../widgets/visage.dart';

/// Aperçu du coupon en image (sélections, cotes, chances du moteur, « argent fictif »),
/// puis partage. Aucune donnée personnelle sur l'image.
Future<void> shareCoupon(
  BuildContext context,
  List<Json> sels,
  Json coupon,
  String profile, {
  bool big = false,
}) {
  final key = GlobalKey();
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Fp.background,
    builder: (context) => SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Partager le coupon', style: Fp.title(17)),
            const SizedBox(height: 12),
            RepaintBoundary(
              key: key,
              child: CouponImage(sels: sels, coupon: coupon, profile: profile, big: big),
            ),
            const SizedBox(height: 14),
            FilledButton.icon(
              onPressed: () async {
                try {
                  final boundary = key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
                  final image = await boundary.toImage(pixelRatio: 3);
                  final data = await image.toByteData(format: ui.ImageByteFormat.png);
                  await ShareBridge.shareImage(
                    data!.buffer.asUint8List(),
                    'Mon coupon FootProba (argent fictif)',
                  );
                } catch (_) {
                  showMessage('Partage impossible sur cet appareil.', error: true);
                }
              },
              icon: const Icon(Icons.ios_share_rounded, size: 18),
              label: const Text('Partager l\'image'),
            ),
          ],
        ),
      ),
    ),
  );
}

class CouponImage extends StatelessWidget {
  const CouponImage({
    super.key,
    required this.sels,
    required this.coupon,
    required this.profile,
    this.big = false,
  });
  final List<Json> sels;
  final Json coupon;
  final String profile;

  /// Grosse cote : la phrase de vérité suit la cote et la chance (plan du 10/11/2026).
  final bool big;

  @override
  Widget build(BuildContext context) {
    final p = (coupon['probability'] as num).toDouble();
    final now = DateTime.now();
    // Maquette 28 : logo et date, une ligne par sélection (match, pari, cote), la cote et la
    // chance réelle en grand, « analyse, pas une promesse ».
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: V.vi.withValues(alpha: 0.35)),
        gradient: const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF2A2163), Color(0xFF1A1740)],
        ),
      ),
      child: DefaultTextStyle(
        style: V.t(13.5),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const FpMark(size: 32),
                const SizedBox(width: 10),
                Expanded(child: Text('FootProba', style: V.b(16))),
                if (profile.isNotEmpty) ...[VChip(profile, kind: VChipKind.vi), const SizedBox(width: 8)],
                Text(
                  '${now.day.toString().padLeft(2, '0')}/${now.month.toString().padLeft(2, '0')}',
                  style: V.t(12.5, color: V.mu),
                ),
              ],
            ),
            const SizedBox(height: 8),
            for (final (i, s) in sels.indexed) ...[
              if (i > 0) Divider(height: 1, thickness: 1, color: Colors.white.withValues(alpha: 0.08)),
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('${s['home']} – ${s['away']}', style: V.t(15)),
                          Text(
                            [
                              lowerLabel(
                                pickLabel(
                                  s['market'] as String,
                                  (s['line'] ?? '') as String,
                                  s['selection'] as String,
                                  home: s['home'] as String,
                                  away: s['away'] as String,
                                ),
                              ),
                              // Date et heure du match (rapport du 07/11/2026).
                              if (DateTime.tryParse('${s['kickoff_at']}') case final k?)
                                '${shortDate(k.toLocal())} ${hourMinute(k.toLocal())}',
                            ].join(' · '),
                            style: V.t(12, color: const Color(0xFFB9B3E6)),
                          ),
                        ],
                      ),
                    ),
                    Text(odds(s['odds']), style: V.b(15)),
                  ],
                ),
              ),
            ],
            Divider(height: 1, thickness: 1, color: Colors.white.withValues(alpha: 0.08)),
            const SizedBox(height: 10),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('cote', style: V.t(12, color: const Color(0xFFB9B3E6))),
                      Text(odds(coupon['total_odds']), style: V.big()),
                    ],
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text('chance du moteur', style: V.t(12, color: const Color(0xFFB9B3E6))),
                    Text(percent(p, decimals: p < 0.1 ? 1 : 0), style: V.big()),
                  ],
                ),
              ],
            ),
            if (big && p > 0) ...[
              const SizedBox(height: 8),
              Text(truthPhrase(p, double.parse('${coupon['total_odds']}')), style: V.t(12, color: V.amber)),
            ],
            // Code 1xBet (coupons du jour) : l'image partagée sert à jouer le coupon
            // (rapport du 07/11/2026).
            for (final b in ((coupon['booking_codes'] as List?) ?? const []).cast<Json>()) ...[
              const SizedBox(height: 8),
              Text('Code ${b['label'] ?? b['bookmaker']} : ${b['code']}', style: V.b(15)),
            ],
            const SizedBox(height: 12),
            Text(
              'Analyse, pas une promesse · argent fictif · '
              '${Uri.tryParse(context.read<AppState>().api.baseUrl)?.host ?? ''}',
              style: V.t(12, color: const Color(0xFFB9B3E6)),
            ),
          ],
        ),
      ),
    );
  }
}
