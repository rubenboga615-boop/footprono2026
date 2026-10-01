import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:provider/provider.dart';

import 'api/client.dart';
import 'push.dart';
import 'screens/auth_screen.dart';
import 'screens/bookmaker_screen.dart';
import 'screens/coupon_screen.dart';
import 'screens/matches_screen.dart';
import 'screens/montante_screen.dart';
import 'screens/notifications_screen.dart';
import 'screens/profile_screen.dart';
import 'state/app_state.dart';
import 'theme.dart';

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
  );
  runApp(FootPronoApp(state: state));
  state.init();
}

class FootPronoApp extends StatelessWidget {
  const FootPronoApp({super.key, required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider.value(
      value: state,
      child: MaterialApp(
        title: 'FootProno',
        debugShowCheckedModeBanner: false,
        theme: Fp.theme(),
        scaffoldMessengerKey: messengerKey,
        builder: (context, child) => FpBackground(child: child ?? const SizedBox()),
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
    if (state.api.token == null) return const AuthScreen();
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
    // Application lancée en touchant une notification.
    WidgetsBinding.instance.addPostFrameCallback((_) => _openNotifications());
  }

  @override
  void dispose() {
    _state.notificationOpened.removeListener(_openNotifications);
    super.dispose();
  }

  /// Notification touchée : écran des notifications.
  void _openNotifications() {
    final n = _state.notificationOpened.value;
    if (!mounted || n == _openedSeen) return;
    _openedSeen = n;
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => const NotificationsScreen()));
  }

  void go(int i) {
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
    const pages = [MatchesScreen(), CouponScreen(), MontanteListScreen(), BookmakerScreen(), ProfileScreen()];
    return Scaffold(
      backgroundColor: Colors.transparent,
      // Le contenu défile sous la barre flottante (listes : marge basse de 110).
      extendBody: true,
      body: IndexedStack(
        index: index,
        children: [
          for (var i = 0; i < pages.length; i++)
            KeyedSubtree(key: ValueKey('$i-${_generation[i]}'), child: pages[i]),
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
    (Icons.sports_soccer_rounded, 'Matchs'),
    (Icons.confirmation_number_outlined, 'Coupon'),
    (Icons.stairs_rounded, 'Montante'),
    (Icons.account_balance_wallet_outlined, 'Bookmaker'),
    (Icons.person_outline_rounded, 'Profil'),
  ];

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(22),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              decoration: BoxDecoration(
                color: const Color(0xD10E0C14),
                borderRadius: BorderRadius.circular(22),
                border: Border.all(color: Fp.line12),
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
  final IconData icon;
  final String label;
  final bool selected;
  final int badge;
  final Color badgeColor;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected ? Fp.accentLight : Fp.textSoft;
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: Material(
        color: selected ? Fp.accentSoft : Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: BorderSide(color: selected ? Fp.accentLine : Colors.transparent),
        ),
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
                  child: Icon(icon, size: 22, color: color),
                ),
                const SizedBox(height: 4),
                ExcludeSemantics(
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(
                      label,
                      maxLines: 1,
                      style: Fp.body(11, weight: FontWeight.w600, color: color),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
