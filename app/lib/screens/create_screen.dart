// « Créer », le bouton central de la barre du bas : copie de la maquette 10 du testeur
// (docs/maquettes/12-nouveau-visage). Tous les outils de jeu au même endroit, chacun dit en
// une ligne à quoi il sert. On choisit un outil, rien ne pousse à parier.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../desktop/layout.dart';
import '../home_tab.dart';
import '../state/app_state.dart';
import '../widgets/visage.dart';
import 'daily_coupons_screen.dart';
import 'live_coupon_screen.dart';
import 'smart_coupon_screen.dart';

export '../home_tab.dart';

class CreateScreen extends StatefulWidget {
  const CreateScreen({super.key});

  @override
  State<CreateScreen> createState() => _CreateScreenState();
}

class _CreateScreenState extends State<CreateScreen> {
  /// Montante en cours (« Palier 3 sur 6 en cours. ») et coupon en direct encore en test.
  Json? montante;
  bool liveTrial = true;

  @override
  void initState() {
    super.initState();
    final api = context.read<AppState>().api;
    api
        .get('/montantes')
        .then((l) {
          final m = (l as List).cast<Json>().where((m) => m['status'] == 'active').firstOrNull;
          if (mounted) setState(() => montante = m);
        })
        .catchError((Object _) {});
    api
        .get('/live/coupons')
        .then((j) {
          if (mounted) setState(() => liveTrial = (j as Json)['trial'] as bool? ?? true);
        })
        .catchError((Object _) {});
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final premium = state.me?.plan.premium ?? false;
    final n = state.coupon.length;
    void push(Widget page) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
    final m = montante;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        bottom: false,
        child: DefaultTextStyle(
          style: V.t(13.5),
          child: ListView(
            padding: pagePadding(context, 14, 120, maxWidth: 760),
            children: [
              Text.rich(
                TextSpan(
                  children: const [
                    TextSpan(text: 'Créer un '),
                    TextSpan(
                      text: 'pari',
                      style: TextStyle(color: V.vi2),
                    ),
                  ],
                ),
                style: V.t(24, w: FontWeight.w800, ls: -0.4),
              ),
              const SizedBox(height: 2),
              Text('Choisis comment tu veux jouer.', style: V.t(12.5, color: V.mu)),
              _Tool(
                icon: VIcon.spark,
                title: 'Coupon intelligent',
                text: 'Le moteur compose selon ton profil et ta période.',
                premium: !premium,
                onTap: () => push(const SmartCouponScreen()),
              ),
              _Tool(
                icon: VIcon.sun,
                title: 'Coupons du jour',
                text: '3 coupons prêts chaque matin, bilan public.',
                onTap: () => push(const DailyCouponsScreen()),
              ),
              _Tool(
                icon: VIcon.stairs,
                title: 'Montante',
                text: m == null
                    ? 'Des paliers enchaînés, gain et risque à chaque palier.'
                    : 'Palier ${m['current_step']} sur ${(m['steps'] as List).length} en cours.',
                onTap: () => state.openTab(HomeTab.montante),
              ),
              _Tool(
                icon: VIcon.live,
                iconBg: V.mintbg,
                iconColor: V.mint,
                title: 'Coupon en direct',
                text: 'Ouvert à la pause, à la 60e, à la 75e',
                trial: liveTrial,
                onTap: () => push(const LiveCouponScreen()),
              ),
              _Tool(
                icon: VIcon.pen,
                title: n == 0 ? 'Composer moi-même' : 'Mon coupon',
                text: n == 0 ? 'Depuis la liste des matchs.' : '$n sélection${n > 1 ? 's' : ''} en attente.',
                badge: n == 0 ? null : '$n',
                onTap: () => state.openTab(n == 0 ? HomeTab.matchs : HomeTab.coupon),
              ),
              _Tool(
                icon: VIcon.flame,
                iconBg: V.amberbg,
                iconColor: V.amber,
                title: 'Grosse cote',
                text: 'Cote jusqu\'à 10, chance affichée sans détour.',
                premium: !premium,
                onTap: () => push(const SmartCouponScreen(initialProfile: 'grosse')),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Carte d'un outil (``.c.row``) : icône 30 sur fond violet foncé, titre, ligne d'aide, ›.
class _Tool extends StatelessWidget {
  const _Tool({
    required this.icon,
    required this.title,
    required this.text,
    required this.onTap,
    this.iconBg = V.vi3,
    this.iconColor = Colors.white,
    this.premium = false,
    this.trial = false,
    this.badge,
  });
  final VIcon icon;
  final Color iconBg;
  final Color iconColor;
  final String title;
  final String text;
  final VoidCallback onTap;
  final bool premium;
  final bool trial;
  final String? badge;

  @override
  Widget build(BuildContext context) => VCard(
    onTap: onTap,
    child: Semantics(
      button: true,
      label: title,
      child: Row(
        children: [
          Container(
            width: 30,
            height: 30,
            decoration: BoxDecoration(color: iconBg, borderRadius: BorderRadius.circular(9)),
            child: Center(child: VIc(icon, size: 18, color: iconColor)),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(child: Text(title, style: V.b())),
                    if (premium) ...[const SizedBox(width: 6), const VChip('Premium', kind: VChipKind.vi)],
                  ],
                ),
                Text(text, style: V.mu_()),
                if (trial)
                  const Padding(
                    padding: EdgeInsets.only(top: 4),
                    child: VChip('En test', kind: VChipKind.am),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          if (badge != null)
            VChip(badge!, kind: VChipKind.vi)
          else
            const RotatedBox(quarterTurns: 2, child: VIc(VIcon.back, size: 16, color: V.vi2)),
        ],
      ),
    ),
  );
}
