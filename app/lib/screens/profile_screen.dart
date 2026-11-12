import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/client.dart';
import '../api/models.dart';

import '../format.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/maquette.dart';
import 'auth_screen.dart' show countries;
import 'merited_screen.dart';
import 'notifications_screen.dart';
import 'premium_screen.dart';
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
            padding: pagePadding(context, 18, 120, maxWidth: 1080),
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
                    // Maquettes N4 et C6 (07/11/2026) : « Mon profil », puis la carte Premium.
                    const MTitle('Mon', 'profil', 26),
                    const SizedBox(height: 4),
                    const _PlanCard(),
                  ],
                ],
                [
                  // Maquettes N4 et C6 : lignes en gras sans icône, séparées d'un trait ; les
                  // réglages du joueur, puis le compte, puis le partage et les pages légales.
                  ValueListenableBuilder(
                    valueListenable: state.webPushStatus,
                    builder: (context, web, _) => _Group([
                      _Item(
                        // Le badge rouge de l'onglet Profil : dit en clair ici.
                        title: state.unread > 0
                            ? 'Notifications · ${state.unread} non lue${state.unread > 1 ? 's' : ''}'
                            : 'Notifications',
                        badge: state.unread,
                        onTap: () => open(const NotificationsScreen()),
                      ),
                      _SwitchItem(
                        title: 'Coupons du jour, chaque matin',
                        value: me?.dailyCouponsNotifications ?? true,
                        onChanged: me == null
                            ? null
                            : (on) => guard(context, () => state.setDailyCouponsNotifications(on)),
                      ),
                      // Demande du fondateur du 12/11/2026 : validé, perdu, but, dernier match.
                      _Item(
                        title: 'Pendant mes matchs',
                        trailing: matchNotificationLabels[me?.matchNotifications ?? 'all'],
                        onTap: me == null ? null : () => _matchNotifications(context, state),
                      ),
                      if (web != WebPushStatus.unavailable)
                        _Item(
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
                      _Item(title: 'Fiabilité du moteur', onTap: () => open(const ReliabilityScreen())),
                      // Ancien bouton de l'écran Matchs (retiré : maquette du 07/11/2026).
                      _Item(title: 'Classement mérité', onTap: () => open(const MeritedScreen())),
                      if (me?.googleLinked ?? false)
                        _Item(
                          title: 'Google lié',
                          trailing: me!.email,
                          onTap: () => _googleLinked(context, state),
                        )
                      else if (me != null && state.google != null)
                        // Maquette validée le 07/11/2026 : une simple ligne (la grande carte
                        // prenait plus de place que l'abonnement).
                        _Item(
                          title: 'Lier mon compte Google',
                          onTap: () => guard(context, () async {
                            if (await state.linkGoogle()) showMessage('Compte Google lié.');
                          }),
                        ),
                      _Item(title: 'Aide · WhatsApp', onTap: () => state.openSupport('Bonjour FootProba, ')),
                    ]),
                  ),
                  _Group([
                    if (me != null)
                      _Item(
                        title: me.displayName,
                        subtitle: me.email ?? me.phone,
                        trailing: countries[me.country] ?? me.country,
                      ),
                    if (me?.hasPassword ?? true)
                      _Item(title: 'Mot de passe', onTap: () => _changePassword(context, state)),
                    _Item(
                      title: 'Déconnecter mes autres téléphones',
                      onTap: () => _logoutOthers(context, state),
                    ),
                    if (serverChoice)
                      _Item(
                        title: 'Serveur (développement)',
                        trailing: state.api.baseUrl,
                        onTap: () => showServerDialog(context),
                      ),
                    const _Item(title: 'Langue', trailing: 'Français'),
                  ]),
                  _Group([
                    if (me != null && me.betaAvailable) _BetaItem(me: me),
                    _Item(
                      title: 'Conditions d\'utilisation',
                      onTap: () => state.openUrl(Uri.parse(state.api.baseUrl).resolve('/conditions')),
                    ),
                    _Item(
                      title: 'Confidentialité',
                      onTap: () => state.openUrl(Uri.parse(state.api.baseUrl).resolve('/confidentialite')),
                    ),
                    _Item(title: 'Jeu responsable', onTap: () => _responsible(context)),
                  ]),
                  const SizedBox(height: 12),
                  // Maquette C6 : bouton entouré, texte lilas.
                  SizedBox(
                    height: 48,
                    child: OutlinedButton.icon(
                      onPressed: () => _logout(context, state),
                      icon: const Icon(Icons.logout_rounded, size: 18),
                      label: const Text('Se déconnecter'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Fp.lilac,
                        side: const BorderSide(color: Fp.line),
                        shape: const StadiumBorder(),
                        textStyle: Fp.body(15, weight: FontWeight.w600),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  MCard(
                    padding: EdgeInsets.zero,
                    child: InkWell(
                      borderRadius: BorderRadius.circular(18),
                      onTap: () => _deleteAccount(context, state),
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Supprimer mon compte',
                              style: Fp.body(15, weight: FontWeight.w700, color: Fp.loss),
                            ),
                            const SizedBox(height: 2),
                            Text('Efface tes données, définitivement', style: Fp.body(12, color: Fp.muted)),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    appBuild > 0 ? 'FootProba · version $appBuild' : 'FootProba · version de développement',
                    textAlign: TextAlign.center,
                    style: Fp.body(12, color: Fp.muted),
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
/// Réglage « Pendant mes matchs » (demande du fondateur du 12/11/2026).
const matchNotificationLabels = {'all': 'Tout', 'results': 'Validé ou perdu', 'none': 'Rien'};

void _matchNotifications(BuildContext context, AppState state) {
  final current = state.me?.matchNotifications ?? 'all';
  const help = {
    'all': 'Sélection validée ou perdue, but qui change ton coupon, dernier match, match retardé.',
    'results': 'Seulement quand une sélection est validée ou perdue.',
    'none': 'Aucune notification pendant les matchs (le résultat du coupon reste notifié).',
  };
  showModalBottomSheet<void>(
    context: context,
    backgroundColor: Fp.background,
    builder: (sheet) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 10),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Pendant mes matchs', style: Fp.title(17)),
            const SizedBox(height: 4),
            Text(
              'Rien sur le téléphone entre 23 h et 8 h : tu retrouves tout dans Notifications.',
              style: Fp.body(12.5, color: Fp.muted, height: 1.4),
            ),
            const SizedBox(height: 8),
            for (final e in matchNotificationLabels.entries)
              InkWell(
                onTap: () {
                  Navigator.pop(sheet);
                  if (e.key != current) guard(context, () => state.setMatchNotifications(e.key));
                },
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Row(
                    children: [
                      Icon(
                        e.key == current ? Icons.radio_button_checked : Icons.radio_button_off,
                        color: e.key == current ? Fp.accent : Fp.muted,
                        size: 20,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(e.value, style: Fp.body(15, weight: FontWeight.w700)),
                            Text(help[e.key]!, style: Fp.body(12.5, color: Fp.text2, height: 1.35)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    ),
  );
}

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

  @override
  Widget build(BuildContext context) {
    final me = context.watch<AppState>().me!;
    final plan = me.plan;
    final price = money(plan.price, plan.priceCurrency);
    // « 2 000 F / mois » comme la maquette (la devise reste dite dans la fenêtre de paiement).
    final short = plan.priceCurrency == 'XOF' ? '${thousands(plan.price)} F' : price;
    return MCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(plan.premium ? 'FootProba Premium' : 'Version gratuite', style: Fp.title(17)),
              ),
              if (plan.premium) const Tag.win('Actif') else MOutlinePill('$short / mois'),
            ],
          ),
          if (plan.premium && plan.premiumUntil != null) ...[
            const SizedBox(height: 6),
            Text(
              'Jusqu\'au ${numericDate(plan.premiumUntil!.toLocal())} · encore ${plan.daysLeft} jour'
              '${plan.daysLeft > 1 ? 's' : ''}',
              style: Fp.body(13.5, color: M.muted),
            ),
          ] else ...[
            const SizedBox(height: 6),
            const PremiumTable(),
          ],
          const SizedBox(height: 12),
          MButton(
            plan.premium ? 'Prolonger · $short / mois' : 'Passer Premium · $short / mois',
            onPressed: () => openPremiumPurchase(context, plan),
          ),
          if (context.watch<AppState>().wavePendingSince case final since?) ...[
            const SizedBox(height: 10),
            Text(
              'Paiement Wave envoyé le ${numericDate(since)} : en attente de vérification. Premium est '
              'activé dès la réception confirmée, en général dans la journée.',
              textAlign: TextAlign.center,
              style: Fp.body(12.5, color: Fp.warning, height: 1.4),
            ),
          ],
          if (!plan.premium) ...[
            const SizedBox(height: 8),
            Text(
              'Payé une fois, 30 jours, sans renouvellement automatique.',
              textAlign: TextAlign.center,
              style: Fp.body(12.5, color: Fp.muted),
            ),
          ],
        ],
      ),
    );
  }
}

/// Carte de lignes séparées d'un trait (maquettes C6 et N4).
class _Group extends StatelessWidget {
  const _Group(this.rows);
  final List<Widget> rows;

  @override
  Widget build(BuildContext context) => MCard(
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
    child: Column(
      children: [
        for (final (i, row) in rows.indexed) ...[
          if (i > 0) const Divider(height: 1, thickness: 1, color: Fp.divider),
          row,
        ],
      ],
    ),
  );
}

class _Item extends StatelessWidget {
  const _Item({required this.title, this.subtitle, this.trailing, this.onTap, this.badge = 0});
  final String title;

  /// Sous le titre, en petit (l'adresse ou le numéro du compte).
  final String? subtitle;

  /// Valeur affichée à droite (pays, langue, adresse Google).
  final String? trailing;
  final VoidCallback? onTap;
  final int badge;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        // Maquette C6 : lignes de 46, texte 15 en gras, valeur et › en gris.
        constraints: const BoxConstraints(minHeight: 46),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 10),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: Fp.body(15, weight: FontWeight.w700)),
                    if (subtitle case final s? when s.isNotEmpty)
                      Text(s, style: Fp.body(12, color: Fp.muted)),
                  ],
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
                    style: Fp.body(13, color: Fp.muted),
                  ),
                ),
              if (badge > 0) ...[
                const SizedBox(width: 8),
                Badge(label: Text('$badge'), backgroundColor: Fp.loss, textColor: Fp.background),
              ],
              if (onTap != null && trailing == null) ...[
                const SizedBox(width: 8),
                const Icon(Icons.chevron_right_rounded, size: 18, color: Fp.muted),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Interrupteur de la maquette (44 × 26, gris éteint).
class _Toggle extends StatelessWidget {
  const _Toggle({required this.value, required this.onChanged});
  final bool value;
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: 46,
    height: 28,
    child: FittedBox(
      child: Switch(
        value: value,
        onChanged: onChanged,
        activeTrackColor: Fp.accent,
        activeThumbColor: Colors.white,
        inactiveTrackColor: const Color(0xFF3A3550),
        inactiveThumbColor: Colors.white,
        trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
      ),
    ),
  );
}

class _SwitchItem extends StatelessWidget {
  const _SwitchItem({required this.title, required this.value, this.onChanged});
  final String title;
  final bool value;
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) {
    return MergeSemantics(
      child: InkWell(
        onTap: onChanged == null ? null : () => onChanged!(!value),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 46),
          child: Row(
            children: [
              Expanded(
                child: Text(title, style: Fp.body(15, weight: FontWeight.w700)),
              ),
              _Toggle(value: value, onChanged: onChanged),
            ],
          ),
        ),
      ),
    );
  }
}

/// Explication du mode bêta, puis l'accord (« J'accepte de partager » / « Pas maintenant »).
Future<bool> explainBeta(BuildContext context, {required bool ask}) => _BetaItem._explain(context, ask: ask);

/// Mode bêta (maquette validée le 06/11/2026) : éteint au départ ; l'allumer montre
/// d'abord ce qui est partagé et ce qui ne l'est jamais, puis demande l'accord.
class _BetaItem extends StatelessWidget {
  const _BetaItem({required this.me});
  final Me me;

  /// Vrai : le joueur accepte de partager.
  static Future<bool> explain(BuildContext context, {required bool ask}) => explainBeta(context, ask: ask);

  static Future<bool> _explain(BuildContext context, {required bool ask}) async {
    Widget point(String label, String text, Color color) => Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Text.rich(
        TextSpan(
          children: [
            TextSpan(
              text: '$label : ',
              style: Fp.body(13.5, weight: FontWeight.w700, color: color),
            ),
            TextSpan(text: text),
          ],
        ),
        style: Fp.body(13.5, color: Fp.text2),
      ),
    );
    final ok = await showModalBottomSheet<bool>(
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
              Text('Aider à améliorer FootProba', style: Fp.title(18)),
              const SizedBox(height: 8),
              Text(
                'Pendant la période de test seulement. Tu deviens « Testeur n° … » : personne ne '
                'sait que c\'est toi.',
                style: Fp.body(13.5, color: Fp.text2),
              ),
              point(
                'Partagé',
                'tes paris fictifs, gains, rendement, réussite par marché ; tes montantes ; les '
                    'coupons intelligents demandés ; les erreurs et attentes trop longues de '
                    'l\'application.',
                Fp.win,
              ),
              point(
                'Jamais partagé',
                'ton nom, ton numéro, ton e-mail, ton compte Google, tes paiements.',
                Fp.lossText,
              ),
              const SizedBox(height: 8),
              Text(
                'Tu peux l\'arrêter quand tu veux : ce qui a été partagé est alors effacé. À la fin '
                'de la période de test, tout est effacé.',
                style: Fp.body(13.5, color: Fp.text2),
              ),
              const SizedBox(height: 14),
              if (ask) ...[
                FilledButton(
                  onPressed: () => Navigator.pop(context, true),
                  child: const Text('J\'accepte de partager'),
                ),
                const SizedBox(height: 8),
                OutlinedButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('Pas maintenant'),
                ),
              ] else
                OutlinedButton(onPressed: () => Navigator.pop(context, false), child: const Text('Fermer')),
            ],
          ),
        ),
      ),
    );
    return ok ?? false;
  }

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    Future<void> toggle(bool on) async {
      if (on && !await explain(context, ask: true)) return;
      if (!context.mounted) return;
      await guard(context, () => state.setBetaSharing(on));
    }

    final tester = me.betaTester;
    return MergeSemantics(
      child: InkWell(
        onTap: () => toggle(!me.betaSharing),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(
                      crossAxisAlignment: WrapCrossAlignment.center,
                      spacing: 6,
                      children: [
                        Text('Aider à améliorer FootProba', style: Fp.body(15, weight: FontWeight.w700)),
                        const Tag('TEST', color: Fp.warning, background: Color(0xFF1F1709)),
                      ],
                    ),
                    const SizedBox(height: 3),
                    Text(
                      me.betaSharing && tester != null
                          ? 'Tu partages en tant que « Testeur n° $tester ». Jamais ton nom ni ton numéro.'
                          : 'Partage anonyme de ton activité pendant la période de test. Jamais ton nom '
                                'ni ton numéro.',
                      style: Fp.body(12.5, color: Fp.muted),
                    ),
                    const SizedBox(height: 2),
                    GestureDetector(
                      onTap: () => explain(context, ask: false),
                      child: Text(
                        'Ce qui est partagé ›',
                        style: Fp.body(13, weight: FontWeight.w600, color: Fp.lilac),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              _Toggle(value: me.betaSharing, onChanged: toggle),
            ],
          ),
        ),
      ),
    );
  }
}
