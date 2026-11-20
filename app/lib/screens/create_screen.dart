// Nouveau visage, étape B (plan du 20/11/2026, écran 10) : « Créer », le bouton central de la
// barre du bas, réunit tout ce qui compose un pari : Mon coupon, Coupon intelligent, Coupons
// du jour, Grosse cote, Montante, Coupon en direct. On choisit un outil, rien ne pousse à parier.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../home_tab.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/nav_icons.dart';
import 'daily_coupons_screen.dart';
import 'live_coupon_screen.dart';
import 'smart_coupon_screen.dart';

export '../home_tab.dart';

class CreateScreen extends StatelessWidget {
  const CreateScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final premium = state.me?.plan.premium ?? false;
    void push(Widget page) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: pagePadding(context, 26, 120, maxWidth: 760),
          children: [
            Text('Créer', style: Fp.title(26)),
            const SizedBox(height: 4),
            Text(
              'Choisis un outil. La pastille « moteur contre cote » est sur chaque sélection.',
              style: Fp.body(13.5, color: Fp.muted, height: 1.4),
            ),
            const SizedBox(height: 16),
            _Tool(
              icon: const NavIcon(NavGlyph.coupon, color: Fp.accentLight, size: 24),
              title: 'Mon coupon',
              text: state.coupon.isEmpty
                  ? 'Vide : ajoute des cotes depuis Matchs.'
                  : '${state.coupon.length} sélection${state.coupon.length > 1 ? 's' : ''} en attente',
              badge: state.coupon.isEmpty ? null : '${state.coupon.length}',
              onTap: () => state.openTab(HomeTab.coupon),
            ),
            _Tool(
              icon: const Icon(Icons.auto_awesome_outlined, color: Fp.accentLight),
              title: 'Coupon intelligent',
              text: 'Le moteur compose selon ton profil : Sûr, Équilibré ou Audacieux.',
              premium: !premium,
              onTap: () => push(const SmartCouponScreen()),
            ),
            _Tool(
              icon: const Icon(Icons.today_outlined, color: Fp.accentLight),
              title: 'Coupons du jour',
              text: 'Trois coupons composés chaque matin, les mêmes pour tous.',
              onTap: () => push(const DailyCouponsScreen()),
            ),
            _Tool(
              icon: const Icon(Icons.trending_up_rounded, color: Fp.accentLight),
              title: 'Grosse cote',
              text: 'Une cote visée : plus elle est haute, plus le coupon perd souvent.',
              premium: !premium,
              onTap: () => push(const SmartCouponScreen(initialProfile: 'grosse')),
            ),
            _Tool(
              icon: const NavIcon(NavGlyph.montante, color: Fp.accentLight, size: 24),
              title: 'Montante',
              text: 'Des paliers enchaînés, avec gain et risque à chaque palier.',
              onTap: () => state.openTab(HomeTab.montante),
            ),
            _Tool(
              icon: const Icon(Icons.sensors_rounded, color: Fp.accentLight),
              title: 'Coupon en direct',
              text: 'Pendant les matchs en cours, à la pause ou en seconde période.',
              onTap: () => push(const LiveCouponScreen()),
            ),
          ],
        ),
      ),
    );
  }
}

class _Tool extends StatelessWidget {
  const _Tool({
    required this.icon,
    required this.title,
    required this.text,
    required this.onTap,
    this.premium = false,
    this.badge,
  });
  final Widget icon;
  final String title;
  final String text;
  final VoidCallback onTap;
  final bool premium;
  final String? badge;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: Material(
      color: Fp.card,
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onTap,
        child: Container(
          constraints: const BoxConstraints(minHeight: 72),
          padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: Fp.line12),
          ),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(color: Fp.cardHigh, borderRadius: BorderRadius.circular(13)),
                child: Center(child: icon),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(title, style: Fp.body(15.5, weight: FontWeight.w700)),
                        ),
                        if (premium) ...[
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                            decoration: BoxDecoration(
                              color: Fp.accent.withValues(alpha: 0.18),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              'Premium',
                              style: Fp.body(10.5, weight: FontWeight.w700, color: Fp.accentLight),
                            ),
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 3),
                    Text(text, style: Fp.body(12.5, color: Fp.muted, height: 1.35)),
                  ],
                ),
              ),
              if (badge != null)
                Container(
                  margin: const EdgeInsets.only(left: 8),
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(color: Fp.accent, borderRadius: BorderRadius.circular(10)),
                  child: Text(badge!, style: Fp.body(12, weight: FontWeight.w700)),
                ),
              const Icon(Icons.chevron_right_rounded, color: Fp.muted),
            ],
          ),
        ),
      ),
    ),
  );
}
