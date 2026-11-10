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
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Fp.background,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Fp.accentLight.withValues(alpha: 0.4)),
        gradient: RadialGradient(
          center: Alignment.topLeft,
          radius: 1.4,
          colors: [Fp.accent.withValues(alpha: 0.45), Fp.background],
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(text: 'Foot', style: Fp.title(17)),
                      TextSpan(
                        text: 'Proba',
                        style: Fp.title(17, color: Fp.accentLight),
                      ),
                    ],
                  ),
                ),
              ),
              if (profile.isNotEmpty) Tag(profile),
            ],
          ),
          const SizedBox(height: 10),
          for (final s in sels)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(
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
                            home: s['home'] as String,
                            away: s['away'] as String,
                          ),
                          style: Fp.body(13, weight: FontWeight.w700),
                        ),
                        Text(
                          [
                            '${s['home']} – ${s['away']}',
                            // Date et heure du match (rapport du 07/11/2026).
                            if (DateTime.tryParse('${s['kickoff_at']}') case final k?)
                              '${shortDate(k.toLocal())} ${hourMinute(k.toLocal())}',
                            percent((s['model_probability'] as num).toDouble()),
                          ].join(' · '),
                          style: Fp.body(11, color: Fp.text2),
                        ),
                      ],
                    ),
                  ),
                  Text(odds(s['odds']), style: Fp.title(14, color: Fp.accentLight)),
                ],
              ),
            ),
          const Divider(height: 18),
          Row(
            children: [
              Expanded(child: StatTile('Cote totale', odds(coupon['total_odds']), valueSize: 18)),
              const SizedBox(width: 8),
              Expanded(
                child: StatTile(
                  'Chances du moteur',
                  percent(p, decimals: p < 0.1 ? 1 : 0),
                  valueColor: Fp.accentLight,
                  valueSize: 18,
                ),
              ),
            ],
          ),
          if (big && p > 0) ...[
            const SizedBox(height: 8),
            Text(
              truthPhrase(p, double.parse('${coupon['total_odds']}')),
              style: Fp.body(12, color: Fp.warning, height: 1.4),
            ),
          ],
          // Code 1xBet (coupons du jour) et adresse de FootProba : l'image partagée sur WhatsApp
          // sert à jouer le coupon et à faire venir de nouveaux joueurs (rapport du 07/11/2026).
          for (final b in ((coupon['booking_codes'] as List?) ?? const []).cast<Json>()) ...[
            const SizedBox(height: 8),
            Text('Code ${b['label'] ?? b['bookmaker']} : ${b['code']}', style: Fp.title(15)),
          ],
          const SizedBox(height: 8),
          Text(
            'Probabilités calculées par FootProba. Argent fictif : aucun gain réel.',
            style: Fp.body(11, color: Fp.text3),
          ),
          const SizedBox(height: 2),
          Text(
            Uri.tryParse(context.read<AppState>().api.baseUrl)?.host ?? '',
            style: Fp.body(12, color: Fp.accentLight, weight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}
