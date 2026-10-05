import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/client.dart';
import '../api/models.dart';

import '../format.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'auth_screen.dart' show GlowButton, GoogleMark, countries;
import 'notifications_screen.dart';
import 'reliability_screen.dart';
import 'server_dialog.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  Future<void> _logout(BuildContext context, AppState state) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Se déconnecter'),
        content: const Text('Le coupon en cours sera vidé.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Se déconnecter')),
        ],
      ),
    );
    if (ok == true) await state.logout();
  }

  Future<void> _deleteAccount(BuildContext context, AppState state) async {
    final password = TextEditingController();
    final withPassword = state.me?.hasPassword ?? true;
    String? error;
    var busy = false;
    await showDialog<void>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('Supprimer mon compte'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Effacés définitivement : numéro, nom, mot de passe, solde fictif, paris, '
                  'montantes, notifications et historique Premium. Un Premium en cours est perdu.\n\n'
                  'Gardés sans ton nom ni ton numéro (obligation comptable) : les paiements Premium. '
                  'Un paiement en cours est annulé.\n\nCette action ne peut pas être annulée.',
                  style: Fp.body(13, color: Fp.text2, height: 1.4),
                ),
                const SizedBox(height: 14),
                if (withPassword)
                  FpField(label: 'Mot de passe', controller: password, obscure: true)
                else
                  Text(
                    'Pour confirmer, reconnecte-toi avec ton compte Google.',
                    style: Fp.body(13, color: Fp.textStrong, height: 1.4),
                  ),
                if (error != null) ...[
                  const SizedBox(height: 12),
                  Text(error!, style: Fp.body(13, color: Fp.lossText)),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: Fp.loss, minimumSize: const Size(0, 44)),
              onPressed: busy
                  ? null
                  : () async {
                      setState(() {
                        busy = true;
                        error = null;
                      });
                      try {
                        if (withPassword) {
                          await state.deleteAccount(password.text);
                        } else if (!await state.deleteAccountWithGoogle()) {
                          setState(() => busy = false);
                          return;
                        }
                        if (context.mounted) Navigator.pop(context);
                        showMessage('Compte supprimé. Tes données personnelles ont été effacées.');
                      } on ApiException catch (e) {
                        setState(() {
                          busy = false;
                          error = e.message;
                        });
                      }
                    },
              child: const Text('Supprimer définitivement'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _logoutOthers(BuildContext context, AppState state) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Déconnecter mes autres téléphones ?'),
        content: Text(
          'Les autres téléphones et navigateurs connectés à ton compte devront se reconnecter. '
          'Celui-ci reste connecté.',
          style: Fp.body(13, color: Fp.text2, height: 1.4),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Déconnecter')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await state.logoutOtherDevices();
      showMessage('Tes autres téléphones sont déconnectés.');
    } on ApiException catch (e) {
      showMessage(e.message, error: true);
    }
  }

  Future<void> _changePassword(BuildContext context, AppState state) async {
    final current = TextEditingController(),
        next = TextEditingController(),
        confirm = TextEditingController();
    String? error;
    await showDialog<void>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('Mot de passe'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                FpField(label: 'Mot de passe actuel', controller: current, obscure: true),
                const SizedBox(height: 12),
                FpField(
                  label: 'Nouveau mot de passe',
                  controller: next,
                  obscure: true,
                  helper: '8 caractères au minimum',
                ),
                const SizedBox(height: 12),
                FpField(label: 'Confirmer', controller: confirm, obscure: true),
                if (error != null) ...[
                  const SizedBox(height: 12),
                  Text(error!, style: Fp.body(13, color: Fp.lossText)),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
            FilledButton(
              style: FilledButton.styleFrom(minimumSize: const Size(0, 44)),
              onPressed: () async {
                if (next.text != confirm.text) {
                  setState(() => error = 'Les deux nouveaux mots de passe sont différents.');
                  return;
                }
                try {
                  await state.changePassword(current.text, next.text);
                  if (context.mounted) Navigator.pop(context);
                  showMessage('Mot de passe changé.');
                } on ApiException catch (e) {
                  setState(() => error = e.message);
                }
              },
              child: const Text('Changer'),
            ),
          ],
        ),
      ),
    );
  }

  void _responsible(BuildContext context) => showDialog<void>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Jeu responsable'),
      content: const Text(
        'FootProba utilise uniquement de l\'argent fictif : rien n\'est misé ni gagné pour de vrai.\n\n'
        'Les probabilités sont des estimations : même un pari probable peut perdre, et aucun pronostic ne '
        'garantit un gain.\n\n'
        'Si tu paries de l\'argent réel ailleurs, fixe-toi une limite, fais des pauses et ne cherche jamais à '
        '« te refaire ». Le jeu est interdit aux moins de 18 ans.',
      ),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Compris'))],
    ),
  );

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final me = state.me;
    void open(Widget page) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        bottom: false,
        child: RefreshIndicator(
          onRefresh: () async => guard(context, state.refreshMe),
          child: ListView(
            padding: pagePadding(context, 26, 120, maxWidth: 1080),
            children: [
              ...deskSplit(
                context,
                [
                  if (me == null)
                    ErrorPanel(
                      error: 'Profil indisponible : serveur injoignable ?',
                      onRetry: () => guard(context, state.refreshMe),
                    )
                  else ...[
                    Row(
                      children: [
                        Container(
                          width: 64,
                          height: 64,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: Fp.accentSoft,
                            borderRadius: BorderRadius.circular(18),
                            border: Border.all(color: Fp.accentLine),
                          ),
                          child: Text(
                            me.displayName.isEmpty ? '?' : me.displayName[0].toUpperCase(),
                            style: Fp.title(26),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(me.displayName, style: Fp.title(24)),
                              const SizedBox(height: 2),
                              Text(me.phone ?? me.email ?? '', style: Fp.body(14, color: Fp.text2)),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 18),
                    const _PlanCard(),
                    if (me.googleLinked || state.google != null) ...[
                      const SizedBox(height: 14),
                      const _GoogleCard(),
                    ],
                  ],
                ],
                [
                  GlassCard.section(
                    padding: const EdgeInsets.fromLTRB(16, 4, 16, 4),
                    child: Column(
                      children: [
                        _Item(
                          icon: Icons.notifications_none_rounded,
                          title: 'Notifications',
                          subtitle: 'Paris réglés, montante, scores corrigés',
                          badge: state.unread,
                          onTap: () => open(const NotificationsScreen()),
                        ),
                        const Divider(),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          secondary: const Icon(Icons.today_rounded, color: Fp.accentLight, size: 22),
                          title: Text('Coupons du jour', style: Fp.body(16, weight: FontWeight.w700)),
                          subtitle: Text(
                            'Prévenir quand les codes du jour sont prêts',
                            style: Fp.body(13, color: Fp.text2),
                          ),
                          value: me?.dailyCouponsNotifications ?? true,
                          onChanged: me == null
                              ? null
                              : (on) => guard(context, () => state.setDailyCouponsNotifications(on)),
                        ),
                        const Divider(),
                        _Item(
                          icon: Icons.auto_awesome_outlined,
                          title: 'Fiabilité du modèle',
                          subtitle: 'Historique public des pronostics',
                          onTap: () => open(const ReliabilityScreen()),
                        ),
                        const Divider(),
                        if (me?.hasPassword ?? true) ...[
                          _Item(
                            icon: Icons.key_outlined,
                            title: 'Mot de passe',
                            subtitle: 'Changer mon mot de passe',
                            onTap: () => _changePassword(context, state),
                          ),
                          const Divider(),
                        ],
                        _Item(
                          icon: Icons.phonelink_erase_rounded,
                          title: 'Déconnecter mes autres téléphones',
                          subtitle: 'Téléphone perdu ou prêté',
                          onTap: () => _logoutOthers(context, state),
                        ),
                        const Divider(),
                        _Item(
                          icon: Icons.support_agent_rounded,
                          title: 'Aide',
                          subtitle: 'Nous écrire sur WhatsApp',
                          onTap: () => state.openSupport('Bonjour FootProba, '),
                        ),
                        const Divider(),
                        _Item(
                          icon: Icons.lock_outline_rounded,
                          title: 'Jeu responsable',
                          subtitle: 'Argent fictif, limites et pauses',
                          onTap: () => _responsible(context),
                        ),
                        const Divider(),
                        if (serverChoice) ...[
                          _Item(
                            icon: Icons.dns_outlined,
                            title: 'Serveur (développement)',
                            subtitle: state.api.baseUrl,
                            onTap: () => showServerDialog(context),
                          ),
                          const Divider(),
                        ],
                        const _Item(icon: Icons.language_rounded, title: 'Langue', subtitle: 'Français'),
                        const Divider(),
                        _Item(
                          icon: Icons.privacy_tip_outlined,
                          title: 'Confidentialité',
                          subtitle: 'Données collectées, durée, tes droits',
                          onTap: () =>
                              state.openUrl(Uri.parse(state.api.baseUrl).resolve('/confidentialite')),
                        ),
                        const Divider(),
                        _Item(
                          icon: Icons.gavel_outlined,
                          title: 'Conditions d\'utilisation',
                          subtitle: 'Argent fictif, Premium, remboursement',
                          onTap: () => state.openUrl(Uri.parse(state.api.baseUrl).resolve('/conditions')),
                        ),
                        const Divider(),
                        _Item(
                          icon: Icons.delete_forever_outlined,
                          title: 'Supprimer mon compte',
                          subtitle: 'Efface tes données, définitivement',
                          onTap: () => _deleteAccount(context, state),
                        ),
                        const Divider(),
                        InkWell(
                          onTap: () => _logout(context, state),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(vertical: 16),
                            child: Row(
                              children: [
                                Text(
                                  'Se déconnecter',
                                  style: Fp.body(16, color: Fp.loss, weight: FontWeight.w700),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                  Text(
                    appBuild > 0 ? 'FootProba · version $appBuild' : 'FootProba · version de développement',
                    textAlign: TextAlign.center,
                    style: Fp.body(12, color: Fp.text3),
                  ),
                ],
                leftWidth: 480,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PlanCard extends StatelessWidget {
  const _PlanCard();

  Future<void> _buy(BuildContext context, Plan plan) async {
    final state = context.read<AppState>();
    final amount = money(plan.price, plan.priceCurrency);
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Premium · 30 jours'),
        content: Text(
          'Tu vas payer $amount par Mobile Money (Orange, MTN, Moov, Wave) sur la page '
          'sécurisée de CinetPay. Premium est activé dès que l\'opérateur confirme le paiement'
          '${plan.premium ? ', à la suite de ta période en cours' : ''}.\n\n'
          'Ce paiement est réel (contrairement aux paris, en argent fictif).',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Payer')),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    await guard(context, state.buyPremium);
  }

  @override
  Widget build(BuildContext context) {
    final me = context.watch<AppState>().me!;
    final plan = me.plan;
    final price = 'Mobile Money · ${money(plan.price, plan.priceCurrency)} / mois';
    final lines = plan.premium
        ? const [
            'Tous les marchés : buts, mi-temps, handicaps, corners, cartons, tirs',
            'Analyses détaillées de chaque match',
            'Suggestions de pari pour la montante',
            'Coupons, montantes et bookmaker virtuel',
          ]
        : const [
            'Inclus : 1X2, plus/moins de buts, les deux marquent',
            'Coupons, montantes et bookmaker virtuel',
            'Premium : tous les marchés, analyses, suggestions de montante',
          ];
    return GlassCard.main(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(
                plan.premium ? Icons.workspace_premium_outlined : Icons.person_outline_rounded,
                color: Fp.accentLight,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(plan.premium ? 'FootProba Premium' : 'Version gratuite', style: Fp.title(20)),
              ),
              plan.premium ? const Tag.win('Actif') : const Tag('Gratuit', color: Fp.textSoft),
            ],
          ),
          const SizedBox(height: 12),
          if (plan.premium && plan.premiumUntil != null)
            KeyValue('Jusqu\'au', '${numericDate(plan.premiumUntil!.toLocal())} (${plan.daysLeft} j)'),
          KeyValue('Paiement', price),
          KeyValue(
            'Pays et devise',
            '${countries[me.country] ?? me.country} · ${currencyLabel(me.currency)}',
          ),
          const SizedBox(height: 8),
          for (final line in lines)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.check_rounded, size: 18, color: Fp.accentLight),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(line, style: Fp.body(15, color: Fp.textStrong, height: 1.35)),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 14),
          FilledButton(
            onPressed: () => _buy(context, plan),
            child: Text(
              plan.premium
                  ? 'Prolonger de 30 jours · ${money(plan.price, plan.priceCurrency)}'
                  : 'Passer Premium · ${money(plan.price, plan.priceCurrency)}',
            ),
          ),
        ],
      ),
    );
  }
}

class _Item extends StatelessWidget {
  const _Item({required this.icon, required this.title, this.subtitle, this.onTap, this.badge = 0});
  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback? onTap;
  final int badge;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 14),
        child: Row(
          children: [
            Icon(icon, color: Fp.accentLight, size: 22),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: Fp.body(16, weight: FontWeight.w700)),
                  if (subtitle != null)
                    Text(
                      subtitle!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Fp.body(13, color: Fp.text2),
                    ),
                ],
              ),
            ),
            if (badge > 0) ...[
              Badge(label: Text('$badge'), backgroundColor: Fp.loss),
              const SizedBox(width: 10),
            ],
            if (onTap != null) const Icon(Icons.arrow_forward_rounded, size: 20, color: Fp.textSoft),
          ],
        ),
      ),
    );
  }
}

/// Compte Google : lier (connexion sans mot de passe) ou délier.
class _GoogleCard extends StatefulWidget {
  const _GoogleCard();

  @override
  State<_GoogleCard> createState() => _GoogleCardState();
}

class _GoogleCardState extends State<_GoogleCard> {
  bool busy = false;

  Future<void> _do(Future<void> Function() action) async {
    setState(() => busy = true);
    try {
      await action();
    } on ApiException catch (e) {
      showMessage(e.message, error: true);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final me = state.me!;
    if (me.googleLinked) {
      final canUnlink = me.hasPassword && me.phone != null;
      return GlassCard.section(
        child: Row(
          children: [
            const Icon(Icons.verified_user_outlined, color: Fp.win, size: 22),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Google lié', style: Fp.body(15, weight: FontWeight.w700)),
                  Text(me.email ?? '', style: Fp.body(13, color: Fp.text2)),
                ],
              ),
            ),
            if (canUnlink)
              TextButton(
                onPressed: busy ? null : () => _do(state.unlinkGoogle),
                style: TextButton.styleFrom(foregroundColor: Fp.lossText),
                child: const Text('Délier'),
              ),
          ],
        ),
      );
    }
    return GlassCard.main(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Padding(
            padding: EdgeInsets.only(left: 20),
            child: TwoToneTitle('Lier mon compte', 'Google', size: 20),
          ),
          const SizedBox(height: 8),
          Text(
            'Ensuite tu te connectes d\'un seul appui, sans mot de passe. Ton Premium, ton solde '
            'et tes paris restent sur ce compte.',
            style: Fp.body(13, color: Fp.textSoft, height: 1.5),
          ),
          const SizedBox(height: 14),
          GlowButton(
            busy: busy,
            onPressed: busy
                ? null
                : () => _do(() async {
                    if (await state.linkGoogle()) showMessage('Compte Google lié.');
                  }),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [GoogleMark(size: 26), SizedBox(width: 10), Text('Lier avec Google')],
            ),
          ),
        ],
      ),
    );
  }
}
