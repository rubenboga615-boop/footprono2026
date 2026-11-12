import 'dart:async';

import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter/semantics.dart';
import 'package:provider/provider.dart';

import 'api/client.dart';
import 'desktop/desktop_shell.dart';
import 'desktop/layout.dart';
import 'desktop/welcome.dart';
import 'google_auth.dart';
import 'push.dart';
import 'screens/auth_screen.dart';
import 'screens/bookmaker_screen.dart';
import 'screens/coupon_screen.dart';
import 'screens/daily_coupons_screen.dart';
import 'screens/matches_screen.dart';
import 'screens/montante_screen.dart';
import 'screens/notifications_screen.dart';
import 'screens/profile_screen.dart';
import 'widgets/common.dart' show guard;
import 'state/app_state.dart';
import 'theme.dart';
import 'widgets/nav_icons.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Tests de bout en bout (navigateur) : l'arbre d'accessibilité est activé
  // pour que les boutons et champs soient trouvés par leur libellé.
  if (kIsWeb && Uri.base.queryParameters.containsKey('e2e')) {
    SemanticsBinding.instance.ensureSemantics();
  }
  final state = AppState(
    api: ApiClient(baseUrl: defaultServer()),
    push: await FirebasePush.start(),
    webPush: kIsWeb ? WebFirebasePush() : null,
    google: FirebaseGoogleAuth.start(),
  );
  runApp(FootProbaApp(state: state));
  state.init();
}

class FootProbaApp extends StatelessWidget {
  const FootProbaApp({super.key, required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider.value(
      value: state,
      child: MaterialApp(
        title: 'FootProba',
        debugShowCheckedModeBanner: false,
        theme: Fp.theme(),
        // Fenêtres annoncées en français au lecteur d'écran (avant : « Dialog », « Dismiss »,
        // « Scrim », revue du 07/11/2026).
        locale: const Locale('fr'),
        supportedLocales: const [Locale('fr')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        scaffoldMessengerKey: messengerKey,
        navigatorKey: navigatorKey,
        builder: (context, child) => FpBackground(child: WideFrame(child: child ?? const SizedBox())),
        home: const _Root(),
      ),
    );
  }
}

class _Root extends StatelessWidget {
  const _Root();

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    if (!state.ready) {
      return const Scaffold(
        backgroundColor: Colors.transparent,
        body: Center(child: CircularProgressIndicator()),
      );
    }
    if (state.api.token == null) {
      return MediaQuery.sizeOf(context).width >= desktopMinWidth
          ? const DesktopWelcome(child: AuthScreen())
          : const AuthScreen();
    }
    if (state.welcome) return const WelcomeScreen();
    return const HomeShell();
  }
}

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => HomeShellState();
}

class HomeShellState extends State<HomeShell> {
  int index = 0;

  static HomeShellState? of(BuildContext context) => context.findAncestorStateOfType<HomeShellState>();

  // Coupon, Montante et Bookmaker sont rechargés à chaque visite (paris
  // placés ou réglés entre-temps) ; la liste des matchs garde ses filtres.
  final _generation = List.filled(5, 0);
  late final AppState _state = context.read<AppState>();
  int _openedSeen = 0;

  @override
  void initState() {
    super.initState();
    _state.notificationOpened.addListener(_openNotifications);
    _state.tabRequest.addListener(_openTab);
    _state.update.addListener(_offerUpdate);
    // Application lancée en touchant une notification.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _openNotifications();
      _offerUpdate();
      _offerBeta();
    });
  }

  @override
  void dispose() {
    _state.notificationOpened.removeListener(_openNotifications);
    _state.tabRequest.removeListener(_openTab);
    _state.update.removeListener(_offerUpdate);
    super.dispose();
  }

  /// Période de test : le partage anonyme est proposé une fois (jamais imposé).
  Future<void> _offerBeta() async {
    if (!mounted || !_state.shouldOfferBeta) return;
    await _state.markBetaOffered();
    if (!mounted) return;
    if (await explainBeta(context, ask: true) && mounted) {
      await guard(context, () => _state.setBetaSharing(true));
    }
  }

  int _updateShown = 0;

  /// Nouvelle version publiée : proposée une fois par version (obligatoire : à chaque fois).
  Future<void> _offerUpdate() async {
    final u = _state.update.value;
    if (!mounted || u == null || (u.build == _updateShown && !u.mandatory)) return;
    _updateShown = u.build;
    final go = await showDialog<bool>(
      context: context,
      barrierDismissible: !u.mandatory,
      builder: (context) => AlertDialog(
        title: const Text('Nouvelle version disponible'),
        content: Text(
          [
            if (u.notes.isNotEmpty) u.notes,
            u.mandatory
                ? 'Cette mise à jour est nécessaire pour continuer à utiliser FootProba.'
                : 'Téléchargement de ${u.sizeMb} Mo dans l\'application, puis Android te demande de '
                      'confirmer l\'installation. Tes paris et ton compte sont conservés.',
          ].join('\n\n'),
        ),
        actions: [
          if (!u.mandatory)
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Plus tard')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Mettre à jour')),
        ],
      ),
    );
    if (go == true) await _runUpdate();
    if (u.mandatory && mounted) {
      _updateShown = 0;
      WidgetsBinding.instance.addPostFrameCallback((_) => _offerUpdate());
    }
  }

  /// Téléchargement avec progression, puis écran d'installation d'Android.
  Future<void> _runUpdate() async {
    final navigator = Navigator.of(context);
    unawaited(
      showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _UpdateProgress(_state.updateProgress),
      ),
    );
    final step = await _state.installUpdate();
    if (!mounted) return;
    navigator.pop();
    if (step == UpdateStep.permission) {
      final retry = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Autorisation nécessaire'),
          content: const Text(
            'Une seule fois : dans le réglage qui vient de s\'ouvrir, active « Autoriser cette source » '
            'pour FootProba, reviens ici puis touche « Installer ».',
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Plus tard')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Installer')),
          ],
        ),
      );
      if (retry == true && mounted) await _runUpdate();
    } else if (step == UpdateStep.failed) {
      final choice = await showDialog<String>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Téléchargement impossible'),
          content: const Text(
            'La mise à jour n\'a pas pu être téléchargée en entier (connexion coupée ou serveur '
            'injoignable). Rien n\'a été installé.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, 'browser'),
              child: const Text('Par le navigateur'),
            ),
            FilledButton(onPressed: () => Navigator.pop(context, 'retry'), child: const Text('Réessayer')),
          ],
        ),
      );
      if (!mounted) return;
      if (choice == 'retry') await _runUpdate();
      if (choice == 'browser') await _state.downloadInBrowser();
    }
  }

  /// Notification touchée : écran des notifications.
  void _openTab() {
    final i = _state.tabRequest.value;
    if (mounted && i != null) go(i);
  }

  void _openNotifications() {
    final n = _state.notificationOpened.value;
    if (!mounted || n == _openedSeen) return;
    _openedSeen = n;
    // Notifications des matchs d'un coupon (rappel, « C'est parti », but, validée) : le
    // suivi du coupon dans Mes paris (retour du testeur du 12/11/2026).
    if (const {'bet_kickoff', 'bet_live', 'bet_settled'}.contains(_state.openedKind)) {
      Navigator.of(context).popUntil((r) => r.isFirst);
      go(3);
      return;
    }
    final page = _state.openedKind == 'daily_coupons'
        ? const DailyCouponsScreen()
        : const NotificationsScreen();
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
  }

  final _desk = GlobalKey<DesktopShellState>();

  void go(int i) {
    final desk = _desk.currentState;
    if (desk != null) {
      const sections = [
        DeskSection.matchs,
        DeskSection.coupon,
        DeskSection.montante,
        DeskSection.bookmaker,
        DeskSection.profil,
      ];
      desk.open(sections[i]);
      return;
    }
    if (i == index) return;
    setState(() {
      index = i;
      if (i >= 1 && i <= 3) _generation[i]++;
    });
    if (i == 3 || i == 4) context.read<AppState>().refreshMe().catchError((_) {});
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    // Version ordinateur : menu à gauche à la place de la barre flottante.
    if (MediaQuery.sizeOf(context).width >= desktopMinWidth) return DesktopShell(key: _desk);
    const pages = [MatchesScreen(), CouponScreen(), MontanteListScreen(), BookmakerScreen(), ProfileScreen()];
    return Scaffold(
      backgroundColor: Colors.transparent,
      // Le contenu défile sous la barre flottante (listes : marge basse de 110).
      extendBody: true,
      body: IndexedStack(
        index: index,
        children: [
          // Onglets cachés sans minuteurs (TickerMode) : « Mes paris » se rechargeait chaque
          // minute même liste des matchs affichée (vérification du 12/11/2026, 17 h 20).
          for (var i = 0; i < pages.length; i++)
            TickerMode(
              enabled: i == index,
              child: KeyedSubtree(key: ValueKey('$i-${_generation[i]}'), child: pages[i]),
            ),
        ],
      ),
      bottomNavigationBar: _FloatingNav(
        index: index,
        onTap: go,
        badges: [0, state.coupon.length, 0, 0, state.unread],
      ),
    );
  }
}

/// Barre de navigation flottante des maquettes : capsule en verre, onglet
/// choisi encadré de violet.
class _FloatingNav extends StatelessWidget {
  const _FloatingNav({required this.index, required this.onTap, required this.badges});
  final int index;
  final ValueChanged<int> onTap;
  final List<int> badges;

  static const _items = [
    (NavGlyph.matchs, 'Matchs'),
    (NavGlyph.coupon, 'Coupon'),
    (NavGlyph.montante, 'Montante'),
    // « Mes paris » : le nom dit ce qu'on y trouve (rapport UX du 07/11/2026).
    (NavGlyph.bookmaker, 'Mes paris'),
    (NavGlyph.profil, 'Profil'),
  ];

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      // Barre des maquettes du 07/11/2026 : #15112A, coins 28, liseré #2A2347, 72 de haut.
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 16),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(28),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
            child: Container(
              height: 72,
              padding: const EdgeInsets.symmetric(horizontal: 6),
              decoration: BoxDecoration(
                color: const Color(0xF215112A),
                borderRadius: BorderRadius.circular(28),
                border: Border.all(color: const Color(0xFF2A2347)),
              ),
              child: Row(
                children: [
                  for (var i = 0; i < _items.length; i++) ...[
                    if (i > 0) const SizedBox(width: 4),
                    Expanded(
                      child: _NavItem(
                        icon: _items[i].$1,
                        label: _items[i].$2,
                        selected: i == index,
                        badge: badges[i],
                        badgeColor: i == 4 ? Fp.loss : Fp.accent,
                        onTap: () => onTap(i),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.icon,
    required this.label,
    required this.selected,
    required this.badge,
    required this.badgeColor,
    required this.onTap,
  });
  final NavGlyph icon;
  final String label;
  final bool selected;
  final int badge;
  final Color badgeColor;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    // Maquettes du 07/11/2026 : onglet actif en violet clair, les autres en gris violacé.
    final color = selected ? Fp.lilac : Fp.muted;
    final Widget glyph = NavIcon(icon, color: color);
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 8),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Badge(
                isLabelVisible: badge > 0,
                label: Text('$badge'),
                backgroundColor: badgeColor,
                // Lisible sur le violet comme sur le rose (maquettes : chiffre sombre sur rose).
                textColor: badgeColor == Fp.loss ? Fp.background : Colors.white,
                child: glyph,
              ),
              const SizedBox(height: 4),
              ExcludeSemantics(
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(
                    label,
                    maxLines: 1,
                    style: Fp.body(11, weight: FontWeight.w500, color: color),
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

/// Progression du téléchargement de la mise à jour.
class _UpdateProgress extends StatelessWidget {
  const _UpdateProgress(this.progress);
  final ValueListenable<double?> progress;

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: false,
    child: AlertDialog(
      title: const Text('Téléchargement'),
      content: ValueListenableBuilder<double?>(
        valueListenable: progress,
        builder: (context, p, _) => Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            LinearProgressIndicator(value: p == null || p == 0 ? null : p),
            const SizedBox(height: 12),
            Text(p == null ? 'Préparation…' : '${(p * 100).round()} %'),
          ],
        ),
      ),
    ),
  );
}
