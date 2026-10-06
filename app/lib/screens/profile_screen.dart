import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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

  Future<void> _googleLinked(BuildContext context, AppState state) async {
    final me = state.me!;
    final canUnlink = me.hasPassword && me.phone != null;
    final unlink = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Compte Google lié'),
        content: Text(
          '${me.email ?? ''}\n\nTu te connectes d\'un seul appui avec ce compte Google.'
          '${canUnlink ? '' : '\n\nPour le délier, ajoute d\'abord un numéro et un mot de passe.'}',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Fermer')),
          if (canUnlink)
            TextButton(
              onPressed: () => Navigator.pop(context, true),
              style: TextButton.styleFrom(foregroundColor: Fp.lossText),
              child: const Text('Délier'),
            ),
        ],
      ),
    );
    if (unlink != true) return;
    try {
      await state.unlinkGoogle();
      showMessage('Compte Google délié.');
    } on ApiException catch (e) {
      showMessage(e.message, error: true);
    }
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
                          width: 60,
                          height: 60,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: Fp.accentAlpha(0.2),
                            borderRadius: BorderRadius.circular(18),
                            border: Border.all(color: const Color(0x8CA78BFA)),
                          ),
                          child: Text(
                            me.displayName.isEmpty ? '?' : me.displayName[0].toUpperCase(),
                            style: Fp.title(24, color: const Color(0xFFE4D8FD)),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(me.displayName, style: Fp.title(22)),
                              const SizedBox(height: 2),
                              Text(
                                [
                                  me.email ?? me.phone ?? '',
                                  countries[me.country] ?? me.country,
                                ].where((t) => t.isNotEmpty).join(' · '),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: Fp.body(13, color: Fp.text2),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 18),
                    const _PlanCard(),
                    if (!me.googleLinked && state.google != null) ...[
                      const SizedBox(height: 12),
                      const _GoogleCard(),
                    ],
                    const SizedBox(height: 12),
                  ],
                ],
                [
                  // Maquette v2 : les réglages du joueur, puis le compte (pages légales
                  // obligatoires, mot de passe, suppression) dans une seconde carte.
                  GlassCard.section(
                    padding: const EdgeInsets.fromLTRB(16, 2, 16, 2),
                    child: Column(
                      children: [
                        _Item(
                          icon: Icons.notifications_none_rounded,
                          title: 'Notifications',
                          badge: state.unread,
                          onTap: () => open(const NotificationsScreen()),
                        ),
                        const Divider(),
                        _SwitchItem(
                          icon: Icons.calendar_today_outlined,
                          title: 'Coupons du jour, chaque matin',
                          value: me?.dailyCouponsNotifications ?? true,
                          onChanged: me == null
                              ? null
                              : (on) => guard(context, () => state.setDailyCouponsNotifications(on)),
                        ),
                        ValueListenableBuilder(
                          valueListenable: state.webPushStatus,
                          builder: (context, web, _) => switch (web) {
                            WebPushStatus.unavailable => const SizedBox.shrink(),
                            _ => Column(
                              children: [
                                const Divider(),
                                _Item(
                                  icon: Icons.phone_iphone_rounded,
                                  title: 'Notifications sur cet appareil',
                                  trailing: switch (web) {
                                    WebPushStatus.on => 'Activées',
                                    WebPushStatus.denied => 'Refusées',
                                    WebPushStatus.install => 'Écran d\'accueil',
                                    _ => 'Activer',
                                  },
                                  onTap: switch (web) {
                                    WebPushStatus.off => state.enableWebPush,
                                    WebPushStatus.on => null,
                                    _ => () => _webPushHelp(context, web),
                                  },
                                ),
                              ],
                            ),
                          },
                        ),
                        const Divider(),
                        _Item(
                          icon: Icons.verified_user_outlined,
                          title: 'Fiabilité du moteur',
                          onTap: () => open(const ReliabilityScreen()),
                        ),
                        if (me?.googleLinked ?? false) ...[
                          const Divider(),
                          _Item(
                            icon: Icons.g_mobiledata_rounded,
                            title: 'Google lié',
                            trailing: me!.email,
                            onTap: () => _googleLinked(context, state),
                          ),
                        ],
                        const Divider(),
                        _Item(
                          icon: Icons.chat_bubble_outline_rounded,
                          title: 'Aide · WhatsApp',
                          onTap: () => state.openSupport('Bonjour FootProba, '),
                        ),
                        const Divider(),
                        _Item(
                          icon: Icons.lock_outline_rounded,
                          title: 'Jeu responsable',
                          onTap: () => _responsible(context),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  GlassCard.section(
                    padding: const EdgeInsets.fromLTRB(16, 2, 16, 2),
                    child: Column(
                      children: [
                        if (me?.hasPassword ?? true) ...[
                          _Item(
                            icon: Icons.key_outlined,
                            title: 'Mot de passe',
                            onTap: () => _changePassword(context, state),
                          ),
                          const Divider(),
                        ],
                        _Item(
                          icon: Icons.phonelink_erase_outlined,
                          title: 'Déconnecter mes autres téléphones',
                          onTap: () => _logoutOthers(context, state),
                        ),
                        const Divider(),
                        if (serverChoice) ...[
                          _Item(
                            icon: Icons.dns_outlined,
                            title: 'Serveur (développement)',
                            trailing: state.api.baseUrl,
                            onTap: () => showServerDialog(context),
                          ),
                          const Divider(),
                        ],
                        const _Item(icon: Icons.language_rounded, title: 'Langue', trailing: 'Français'),
                        const Divider(),
                        _Item(
                          icon: Icons.privacy_tip_outlined,
                          title: 'Confidentialité',
                          onTap: () =>
                              state.openUrl(Uri.parse(state.api.baseUrl).resolve('/confidentialite')),
                        ),
                        const Divider(),
                        _Item(
                          icon: Icons.gavel_outlined,
                          title: 'Conditions d\'utilisation',
                          onTap: () => state.openUrl(Uri.parse(state.api.baseUrl).resolve('/conditions')),
                        ),
                        const Divider(),
                        _Item(
                          icon: Icons.delete_outline_rounded,
                          title: 'Supprimer mon compte',
                          warning: 'Efface tes données, définitivement',
                          onTap: () => _deleteAccount(context, state),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  Center(
                    child: TextButton.icon(
                      onPressed: () => _logout(context, state),
                      icon: const Icon(Icons.logout_rounded, size: 18),
                      label: const Text('Se déconnecter'),
                      style: TextButton.styleFrom(
                        foregroundColor: Fp.lossText,
                        textStyle: Fp.body(14, weight: FontWeight.w700),
                      ),
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

/// Notifications web impossibles pour l'instant : ce qu'il faut faire.
void _webPushHelp(BuildContext context, WebPushStatus status) {
  showDialog<void>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Notifications'),
      content: Text(
        status == WebPushStatus.install
            ? 'Sur iPhone, les notifications marchent quand FootProba est ajouté à l\'écran '
                  'd\'accueil : dans Safari, touche Partager puis « Sur l\'écran d\'accueil », '
                  'ouvre FootProba depuis cette icône, puis reviens ici et touche « Activer ».'
            : 'Tu as refusé les notifications pour FootProba. Pour les recevoir, autorise-les '
                  'dans les réglages (iPhone : Réglages → Notifications → FootProba), puis rouvre '
                  'l\'application.',
        style: Fp.body(13, height: 1.45),
      ),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK'))],
    ),
  );
}

class _PlanCard extends StatelessWidget {
  const _PlanCard();

  /// Choix du moyen de paiement (ceux du serveur, et le Wave manuel s'il est proposé).
  Future<void> _buy(BuildContext context, Plan plan) async {
    final state = context.read<AppState>();
    final offer = await guard(context, state.paymentMethods);
    if (offer == null || !context.mounted) return;
    final amount = money(offer['price'] as int, offer['currency'] as String);
    final methods = [for (final m in offer['methods'] as List) m as Json];
    final manual = offer['manual'] as Json?;
    if (methods.isEmpty && manual == null) {
      showMessage('Paiement indisponible pour le moment. Réessaie plus tard.', error: true);
      return;
    }
    final choice = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Premium · 30 jours'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '$amount, payés une fois (pas de renouvellement automatique)'
              '${plan.premium ? ', à la suite de ta période en cours' : ''}. Ce paiement est réel '
              '(contrairement aux paris, en argent fictif).',
              style: Fp.body(13, color: Fp.text2, height: 1.4),
            ),
            const SizedBox(height: 12),
            for (final m in methods)
              _MethodTile(
                icon: m['id'] == 'wave' ? Icons.waves_rounded : Icons.phone_android_rounded,
                title: m['label'] as String,
                subtitle: 'Premium activé dès la confirmation du paiement',
                onTap: () => Navigator.pop(context, m['id'] as String),
              ),
            if (manual != null)
              _MethodTile(
                icon: Icons.send_to_mobile_rounded,
                title: methods.isEmpty ? 'Wave' : 'Wave (envoi au numéro FootProba)',
                subtitle: 'Premium activé après vérification de l\'envoi',
                onTap: () => Navigator.pop(context, 'manual'),
              ),
          ],
        ),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler'))],
      ),
    );
    if (choice == null || !context.mounted) return;
    if (choice == 'manual') {
      await _manualWave(context, state, amount, manual!['wave_number'] as String);
      return;
    }
    await guard(context, () => state.buyPremium(choice));
  }

  /// Wave sans compte marchand : le joueur envoie le montant au numéro de FootProba puis
  /// la capture sur WhatsApp ; l'administrateur vérifie la réception et active Premium.
  Future<void> _manualWave(BuildContext context, AppState state, String amount, String number) async {
    final me = state.me!;
    final account = 'compte n° ${me.id}${me.phone != null ? ' (${me.phone})' : ''}';
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Payer avec Wave'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('1. Dans Wave, envoie exactement $amount au numéro :', style: Fp.body(13, height: 1.4)),
            const SizedBox(height: 6),
            Row(
              children: [
                Expanded(
                  child: Text(number, style: Fp.body(18, weight: FontWeight.w800)),
                ),
                IconButton(
                  tooltip: 'Copier le numéro',
                  icon: const Icon(Icons.copy_rounded, size: 18),
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: number));
                    showMessage('Numéro copié');
                  },
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              '2. Envoie la capture du reçu Wave sur WhatsApp (bouton ci-dessous).\n\n'
              'Premium est activé sur ton $account dès que la réception est vérifiée, '
              'en général dans la journée. Tu reçois une notification.',
              style: Fp.body(13, color: Fp.text2, height: 1.4),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Fermer')),
          FilledButton.icon(
            onPressed: () {
              Navigator.pop(context);
              state.openSupport(
                'Bonjour FootProba, j\'ai payé Premium ($amount) par Wave au $number. '
                'Mon $account. Voici la capture du reçu :',
              );
            },
            icon: const Icon(Icons.chat_rounded, size: 18),
            label: const Text('Envoyer la capture'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final me = context.watch<AppState>().me!;
    final plan = me.plan;
    final price = money(plan.price, plan.priceCurrency);
    const lines = [
      'Tous les marchés : buts, mi-temps, handicaps, corners, cartons, tirs',
      'Analyses détaillées et choix du moteur de chaque match',
      'Suggestions de pari pour la montante',
    ];
    return GradientCard(
      padding: const EdgeInsets.fromLTRB(18, 16, 18, 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: plan.premium
                    ? const TwoToneTitle('FootProba', 'Premium', size: 18)
                    : const TwoToneTitle('Version', 'gratuite', size: 18),
              ),
              if (plan.premium)
                const Tag('ACTIF', color: Color(0xFF6EE7B7), background: Color(0x2E34D399))
              else
                const Tag('GRATUIT', color: Fp.textSoft),
            ],
          ),
          const SizedBox(height: 6),
          if (plan.premium && plan.premiumUntil != null)
            Text(
              'Jusqu\'au ${numericDate(plan.premiumUntil!.toLocal())} · encore ${plan.daysLeft} jour'
              '${plan.daysLeft > 1 ? 's' : ''}',
              style: Fp.body(13, color: Fp.text2),
            )
          else ...[
            for (final line in lines)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.check_rounded, size: 16, color: Fp.accentLight),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(line, style: Fp.body(13, color: Fp.textStrong, height: 1.35)),
                    ),
                  ],
                ),
              ),
          ],
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerLeft,
            child: FilledButton(
              onPressed: () => _buy(context, plan),
              style: FilledButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: const Color(0xFF2E1065),
                minimumSize: const Size(0, 42),
                padding: const EdgeInsets.symmetric(horizontal: 16),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                textStyle: Fp.body(13, weight: FontWeight.w800),
              ),
              child: Text(plan.premium ? 'Prolonger · $price / mois' : 'Passer Premium · $price / mois'),
            ),
          ),
        ],
      ),
    );
  }
}

class _Item extends StatelessWidget {
  const _Item({
    required this.icon,
    required this.title,
    this.trailing,
    this.onTap,
    this.badge = 0,
    this.warning,
  });
  final IconData icon;
  final String title;

  /// Avertissement sous le titre (seulement « Supprimer mon compte »).
  final String? warning;

  /// Valeur affichée à droite (langue, adresse Google).
  final String? trailing;
  final VoidCallback? onTap;
  final int badge;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 52),
        child: Row(
          children: [
            Icon(icon, color: const Color(0xFFC9B2F8), size: 20),
            const SizedBox(width: 12),
            Expanded(
              child: warning == null
                  ? Text(title, style: Fp.body(14, weight: FontWeight.w600))
                  : Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(title, style: Fp.body(14, weight: FontWeight.w600)),
                          Text(warning!, style: Fp.body(12, color: Fp.text3)),
                        ],
                      ),
                    ),
            ),
            if (trailing != null)
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 190),
                child: Text(
                  trailing!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.right,
                  style: Fp.body(12, color: Fp.text2),
                ),
              ),
            if (badge > 0) ...[
              const SizedBox(width: 8),
              Badge(label: Text('$badge'), backgroundColor: Fp.loss),
            ],
            if (onTap != null && trailing == null) ...[
              const SizedBox(width: 8),
              const Icon(Icons.chevron_right_rounded, size: 18, color: Fp.text4),
            ],
          ],
        ),
      ),
    );
  }
}

/// Ligne avec interrupteur compact (42 × 24 dans la maquette v2).
class _SwitchItem extends StatelessWidget {
  const _SwitchItem({required this.icon, required this.title, required this.value, this.onChanged});
  final IconData icon;
  final String title;
  final bool value;
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) {
    return MergeSemantics(
      child: InkWell(
        onTap: onChanged == null ? null : () => onChanged!(!value),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 52),
          child: Row(
            children: [
              Icon(icon, color: const Color(0xFFC9B2F8), size: 20),
              const SizedBox(width: 12),
              Expanded(
                child: Text(title, style: Fp.body(14, weight: FontWeight.w600)),
              ),
              SizedBox(
                width: 46,
                height: 28,
                child: FittedBox(
                  child: Switch(
                    value: value,
                    onChanged: onChanged,
                    activeTrackColor: Fp.accent,
                    activeThumbColor: Colors.white,
                    trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
                  ),
                ),
              ),
            ],
          ),
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

class _MethodTile extends StatelessWidget {
  const _MethodTile({required this.icon, required this.title, required this.subtitle, required this.onTap});

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 8),
    child: Material(
      color: Fp.fill7,
      borderRadius: BorderRadius.circular(12),
      child: ListTile(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        leading: Icon(icon, color: Fp.accentLight),
        title: Text(title, style: Fp.body(14, weight: FontWeight.w700)),
        subtitle: Text(subtitle, style: Fp.body(12, color: Fp.text3)),
        trailing: const Icon(Icons.chevron_right_rounded),
        onTap: onTap,
      ),
    ),
  );
}
