import 'dart:async';

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
import 'screens/create_screen.dart';
import 'screens/daily_coupons_screen.dart';
import 'screens/matches_screen.dart';
import 'screens/montante_screen.dart';
import 'screens/notifications_screen.dart';
import 'screens/odds_alerts_screen.dart';
import 'screens/play_plan_screen.dart';
import 'screens/profile_screen.dart';
import 'screens/today_screen.dart';
import 'widgets/common.dart' show guard;
import 'state/app_state.dart';
import 'theme.dart';
import 'widgets/visage.dart';

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
        navigatorObservers: [pushedPages],
        builder: (context, child) => FpBackground(
          child: WideFrame(child: _PushedNav(child: child ?? const SizedBox())),
        ),
        home: const _Root(),
      ),
    );
  }
}

/// Écrans ouverts par-dessus l'accueil (fiche de match, plan de jeu, pari…) : la barre du bas
/// des maquettes y reste visible (maquettes 07, 19, 29, 30…). Suivi de la pile des écrans.
class PushedPages extends NavigatorObserver {
  /// Un écran au moins est ouvert par-dessus l'accueil.
  final pushed = ValueNotifier<bool>(false);

  final _stack = <Route<dynamic>>[];

  void _update() {
    final p = _stack.whereType<PageRoute<dynamic>>().length > 1;
    // Après l'image en cours : la pile change pendant la construction des écrans.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      pushed.value = p;
    });
    WidgetsBinding.instance.scheduleFrame();
  }

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    // Premier écran d'un nouveau navigateur (application relancée) : pile repartie de zéro.
    if (previousRoute == null) _stack.clear();
    _stack.add(route);
    _update();
  }

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    _stack.remove(route);
    _update();
  }

  @override
  void didRemove(Route<dynamic> route, Route<dynamic>? previousRoute) {
    _stack.remove(route);
    _update();
  }

  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    final i = oldRoute == null ? -1 : _stack.indexOf(oldRoute);
    if (newRoute != null) i >= 0 ? _stack[i] = newRoute : _stack.add(newRoute);
    _update();
  }
}

final pushedPages = PushedPages();

/// Barre du bas sur les écrans ouverts par-dessus l'accueil : l'onglet d'où l'on vient reste
/// en blanc ; toucher un onglet ferme ces écrans et l'ouvre.
class _PushedNav extends StatelessWidget {
  const _PushedNav({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<bool>(
    valueListenable: pushedPages.pushed,
    builder: (context, pushed, _) {
      final state = context.watch<AppState>();
      final mq = MediaQuery.of(context);
      if (!pushed || !state.loggedIn || state.welcome || mq.size.width >= desktopMinWidth) return child;
      final mode = state.montanteMode;
      // Sous le contenu (pas par-dessus) : rien ne se cache derrière la barre, et les feuilles
      // ou fenêtres s'ouvrent au-dessus d'elle.
      return Column(
        children: [
          Expanded(
            child: MediaQuery.removePadding(context: context, removeBottom: true, child: child),
          ),
          if (mq.viewInsets.bottom == 0)
            Material(
              type: MaterialType.transparency,
              child: ValueListenableBuilder<int>(
                valueListenable: state.currentTab,
                builder: (context, index, _) => _FloatingNav(
                  index: index,
                  onTap: (i) {
                    navigatorKey.currentState?.popUntil((r) => r.isFirst);
                    state.openTab(i);
                  },
                  badges: {HomeTab.create: state.coupon.length, HomeTab.moi: state.unread},
                  tabs: mode ? const [HomeTab.montante, HomeTab.matchs, HomeTab.moi] : null,
                ),
              ),
            ),
        ],
      );
    },
  );
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
  bool _mode = false;

  static HomeShellState? of(BuildContext context) => context.findAncestorStateOfType<HomeShellState>();

  // Coupon, Montante et Bookmaker sont rechargés à chaque visite (paris
  // placés ou réglés entre-temps) ; la liste des matchs garde ses filtres.
  // Nouveau visage, étape B : Aujourd'hui, Matchs, Créer, Paris, Moi, puis Mon coupon et la
  // Montante (ouverts depuis « Créer », barre visible) : voir [HomeTab].
  final _generation = List.filled(7, 0);
  late final AppState _state = context.read<AppState>();
  int _openedSeen = 0;

  @override
  void initState() {
    super.initState();
    if (_state.pendingTab case final t?) {
      index = t;
      _state.pendingTab = null;
    }
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
      go(_state.montanteMode ? HomeTab.montante : HomeTab.paris);
      return;
    }
    final page = switch (_state.openedKind) {
      'daily_coupons' => const DailyCouponsScreen(),
      'odds_alert' when oddsAlertsShown => const OddsAlertsScreen(),
      _ => const NotificationsScreen(),
    } as Widget;
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
  }

  final _desk = GlobalKey<DesktopShellState>();

  void go(int i) {
    final desk = _desk.currentState;
    if (desk != null) {
      const sections = [
        DeskSection.aujourdhui,
        DeskSection.matchs,
        DeskSection.creer,
        DeskSection.bookmaker,
        DeskSection.profil,
        DeskSection.coupon,
        DeskSection.montante,
      ];
      desk.open(sections[i]);
      return;
    }
    if (i == index) return;
    setState(() {
      index = i;
      // Rechargés à chaque visite : Aujourd'hui, Paris, Mon coupon, Montante.
      if (const {HomeTab.today, HomeTab.paris, HomeTab.coupon, HomeTab.montante}.contains(i)) {
        _generation[i]++;
      }
    });
    if (i == HomeTab.paris || i == HomeTab.moi) context.read<AppState>().refreshMe().catchError((_) {});
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    // Onglet en blanc dans la barre des écrans ouverts par-dessus.
    WidgetsBinding.instance.addPostFrameCallback((_) => state.currentTab.value = index);
    // Version ordinateur : menu à gauche à la place de la barre flottante.
    if (MediaQuery.sizeOf(context).width >= desktopMinWidth) return DesktopShell(key: _desk);
    const pages = [
      TodayScreen(),
      MatchesScreen(),
      CreateScreen(),
      BookmakerScreen(),
      ProfileScreen(),
      CouponScreen(),
      MontanteListScreen(),
    ];
    // Mode Montante (14/11/2026) : ouvre sur la montante ; seulement Montante, Matchs et Moi.
    final mode = state.montanteMode;
    final switchedOn = mode && !_mode;
    _mode = mode;
    if (switchedOn || (mode && !const {HomeTab.matchs, HomeTab.moi, HomeTab.montante}.contains(index))) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) setState(() => index = HomeTab.montante);
      });
    }
    // Rappel « une heure dans l'appli » du plan de jeu (maquette 30).
    return PlayReminder(
      child: Scaffold(
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
        bottomNavigationBar: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Mode Montante : le palier composé depuis les matchs s'ouvre par-dessus.
            if (mode && index == HomeTab.matchs && state.coupon.isNotEmpty) const _PalierBar(),
            _FloatingNav(
              index: index,
              onTap: go,
              badges: {HomeTab.create: state.coupon.length, HomeTab.moi: state.unread},
              tabs: mode ? const [HomeTab.montante, HomeTab.matchs, HomeTab.moi] : null,
            ),
          ],
        ),
      ),
    );
  }
}

/// Barre du bas des maquettes « nouveau visage » (.nav) : capsule flottante de 66, coins 24,
/// fond rgba(19,26,42,.96), liseré #222C44 ; « + » central en carré violet de 56 surélevé.
class _FloatingNav extends StatelessWidget {
  const _FloatingNav({required this.index, required this.onTap, required this.badges, this.tabs});
  final int index;
  final ValueChanged<int> onTap;
  final Map<int, int> badges;

  /// Onglets montrés (index des pages) ; les 5 de la barre si null. Mode Montante : Montante,
  /// Matchs, Moi.
  final List<int>? tabs;

  static const _items = {
    HomeTab.today: (VIcon.home, 'Aujourd\'hui'),
    HomeTab.matchs: (VIcon.matchs, 'Matchs'),
    HomeTab.create: (VIcon.plus, 'Créer'),
    HomeTab.paris: (VIcon.ticket, 'Paris'),
    HomeTab.moi: (VIcon.user, 'Moi'),
    HomeTab.montante: (VIcon.stairs, 'Montante'),
  };

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(10, 0, 10, 12),
        child: Container(
          height: 66,
          decoration: BoxDecoration(
            color: const Color(0xF5131A2A),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: V.navBorder),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              for (final i in tabs ?? const [0, 1, 2, 3, 4])
                i == HomeTab.create
                    ? _Fab(
                        // Mon coupon et la Montante s'ouvrent depuis « Créer ».
                        selected: i == index || index == HomeTab.coupon || index == HomeTab.montante,
                        badge: badges[i] ?? 0,
                        onTap: () => onTap(i),
                      )
                    : _NavItem(
                        icon: _items[i]!.$1,
                        label: _items[i]!.$2,
                        selected: i == index,
                        badge: badges[i] ?? 0,
                        onTap: () => onTap(i),
                      ),
            ],
          ),
        ),
      ),
    );
  }
}

/// ``.nav .fab`` : 56 × 56, coins 18, violet, remonté de 26, ombre violette.
class _Fab extends StatelessWidget {
  const _Fab({required this.selected, required this.badge, required this.onTap});
  final bool selected;
  final int badge;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    selected: selected,
    label: 'Créer',
    child: Transform.translate(
      offset: const Offset(0, -13),
      child: GestureDetector(
        onTap: onTap,
        child: Badge(
          isLabelVisible: badge > 0,
          label: Text('$badge'),
          backgroundColor: V.coral,
          offset: const Offset(2, -4),
          child: Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              color: V.vi,
              borderRadius: BorderRadius.circular(18),
              boxShadow: const [BoxShadow(color: Color(0x737C5CFF), offset: Offset(0, 8), blurRadius: 20)],
            ),
            child: const Center(child: VIc(VIcon.plus, size: 24, stroke: 2.2, color: Colors.white)),
          ),
        ),
      ),
    ),
  );
}

/// ``.nav span`` : icône 21 au trait, libellé 10,5 600 ; gris mu2, onglet actif en blanc.
class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.icon,
    required this.label,
    required this.selected,
    required this.badge,
    required this.onTap,
  });
  final VIcon icon;
  final String label;
  final bool selected;
  final int badge;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected ? V.tx : V.mu2;
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minWidth: 54, minHeight: 56),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Badge(
                isLabelVisible: badge > 0,
                label: Text('$badge'),
                backgroundColor: V.coral,
                child: VIc(icon, size: 21, color: color),
              ),
              const SizedBox(height: 3),
              ExcludeSemantics(
                child: Text(
                  label,
                  maxLines: 1,
                  style: V.t(10.5, w: FontWeight.w600, color: color),
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

/// Mode Montante : barre « Mon palier » au-dessus des onglets quand des sélections sont
/// choisies dans les matchs ; ouvre le palier (le coupon, mise imposée par la montante).
class _PalierBar extends StatelessWidget {
  const _PalierBar();

  @override
  Widget build(BuildContext context) {
    final n = context.watch<AppState>().coupon.length;
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
      child: Material(
        color: Fp.accent,
        borderRadius: BorderRadius.circular(22),
        child: InkWell(
          borderRadius: BorderRadius.circular(22),
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => Scaffold(
                backgroundColor: Fp.background,
                body: SafeArea(
                  child: Column(
                    children: [
                      Align(
                        alignment: Alignment.centerLeft,
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(8, 4, 8, 0),
                          child: BackChevron(onTap: () => Navigator.of(context).maybePop()),
                        ),
                      ),
                      const Expanded(child: CouponScreen()),
                    ],
                  ),
                ),
              ),
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    'Mon palier · $n sélection${n > 1 ? 's' : ''}',
                    style: Fp.body(15, weight: FontWeight.w700, color: Colors.white),
                  ),
                ),
                const Icon(Icons.chevron_right_rounded, color: Colors.white),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
