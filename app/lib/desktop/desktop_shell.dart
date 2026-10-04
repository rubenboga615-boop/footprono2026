// Version ordinateur (maquette « FootProba sur ordinateur » validée le 03/10/2026) :
// menu à gauche, barre du haut (recherche, Premium, solde), zone centrale avec sa
// propre navigation, coupon à droite pendant qu'on parcourt les matchs.
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../screens/bookmaker_screen.dart';
import '../screens/coupon_screen.dart';
import '../screens/match_screen.dart';
import '../screens/matches_screen.dart';
import '../screens/merited_screen.dart';
import '../screens/montante_screen.dart';
import '../screens/notifications_screen.dart';
import '../screens/daily_coupons_screen.dart';
import '../screens/profile_screen.dart';
import '../screens/record_screen.dart';
import '../screens/reliability_screen.dart';
import '../screens/smart_coupon_screen.dart';
import '../screens/team_screen.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'layout.dart';

enum DeskSection {
  matchs('Matchs', Icons.sports_soccer_rounded, 'Jouer'),
  coupon('Mon coupon', Icons.confirmation_number_outlined, 'Jouer'),
  jour('Coupons du jour', Icons.today_rounded, 'Jouer'),
  intelligent('Coupon intelligent', Icons.auto_awesome_rounded, 'Jouer'),
  montante('Montante', Icons.stairs_rounded, 'Jouer'),
  bookmaker('Bookmaker fictif', Icons.account_balance_wallet_outlined, 'Jouer'),
  championnats('Championnats', Icons.leaderboard_rounded, 'Comprendre'),
  bilan('Mon bilan', Icons.insights_rounded, 'Comprendre'),
  fiabilite('Fiabilité du moteur', Icons.verified_outlined, 'Comprendre'),
  notifications('Notifications', Icons.notifications_none_rounded, 'Compte'),
  profil('Profil et Premium', Icons.person_outline_rounded, 'Compte');

  const DeskSection(this.label, this.icon, this.group);
  final String label;
  final IconData icon;
  final String group;

  Widget get root => switch (this) {
    matchs => const MatchesScreen(),
    coupon => const CouponScreen(),
    jour => const DailyCouponsScreen(),
    intelligent => const SmartCouponScreen(),
    montante => const MontanteListScreen(),
    bookmaker => const BookmakerScreen(),
    championnats => const MeritedScreen(),
    bilan => const RecordScreen(),
    fiabilite => const ReliabilityScreen(),
    notifications => const NotificationsScreen(),
    profil => const ProfileScreen(),
  };
}

class DesktopShell extends StatefulWidget {
  const DesktopShell({super.key});

  static DesktopShellState? of(BuildContext context) => context.findAncestorStateOfType<DesktopShellState>();

  @override
  State<DesktopShell> createState() => DesktopShellState();
}

class DesktopShellState extends State<DesktopShell> {
  DeskSection section = DeskSection.matchs;
  // Chaque visite d'une rubrique repart de sa page d'accueil (paris placés entre-temps).
  GlobalKey<NavigatorState> _nav = GlobalKey<NavigatorState>();

  void open(DeskSection s, {Widget? page}) {
    setState(() {
      section = s;
      _nav = GlobalKey<NavigatorState>();
    });
    if (s == DeskSection.bookmaker || s == DeskSection.profil) {
      context.read<AppState>().refreshMe().catchError((_) {});
    }
    if (page != null) {
      WidgetsBinding.instance.addPostFrameCallback(
        (_) => _nav.currentState?.push(MaterialPageRoute(builder: (_) => page)),
      );
    }
  }

  Future<void> search() async {
    final target = await showDialog<_Target>(
      context: context,
      barrierColor: const Color(0xAD040308),
      builder: (_) => const _SearchPalette(),
    );
    if (target != null && mounted) open(target.section, page: target.page);
  }

  @override
  Widget build(BuildContext context) {
    final rail = section == DeskSection.matchs;
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyK, control: true): search,
        const SingleActivator(LogicalKeyboardKey.keyK, meta: true): search,
      },
      child: Focus(
        autofocus: true,
        child: Scaffold(
          backgroundColor: Colors.transparent,
          body: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _Sidebar(section: section, onOpen: open),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _TopBar(onSearch: search, onProfile: () => open(DeskSection.profil)),
                    Expanded(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Expanded(
                            child: LayoutBuilder(
                              builder: (context, c) => MediaQuery(
                                data: MediaQuery.of(context).copyWith(size: Size(c.maxWidth, c.maxHeight)),
                                child: DesktopScope(
                                  // Conteneur à part : la barrière des pages de la zone centrale
                                  // cacherait sinon le menu et la barre du haut aux lecteurs d'écran.
                                  child: Semantics(
                                    container: true,
                                    explicitChildNodes: true,
                                    child: ClipRect(
                                      child: Navigator(
                                        key: _nav,
                                        onGenerateRoute: (_) =>
                                            PageRouteBuilder<void>(pageBuilder: (_, _, _) => section.root),
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ),
                          if (rail) const _CouponRail(),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// --- Menu de gauche ----------------------------------------------------------

class _Sidebar extends StatelessWidget {
  const _Sidebar({required this.section, required this.onOpen});
  final DeskSection section;
  final void Function(DeskSection) onOpen;

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    String? group;
    return Container(
      width: 232,
      decoration: const BoxDecoration(
        color: Color(0xC00A090E),
        border: Border(right: BorderSide(color: Fp.divider)),
      ),
      padding: const EdgeInsets.fromLTRB(12, 20, 12, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(10, 0, 10, 14),
            child: FittedBox(fit: BoxFit.scaleDown, alignment: Alignment.centerLeft, child: FpLogo()),
          ),
          Expanded(
            child: ListView(
              children: [
                for (final s in DeskSection.values) ...[
                  if (s.group != group) ...[
                    Padding(
                      padding: const EdgeInsets.fromLTRB(10, 14, 10, 6),
                      child: Text(
                        (group = s.group).toUpperCase(),
                        style: Fp.body(10.5, color: Fp.text4, weight: FontWeight.w700),
                      ),
                    ),
                  ],
                  _SideItem(
                    section: s,
                    selected: s == section,
                    badge: switch (s) {
                      DeskSection.coupon => state.coupon.length,
                      DeskSection.notifications => state.unread,
                      _ => 0,
                    },
                    onTap: () => onOpen(s),
                  ),
                ],
              ],
            ),
          ),
          const Divider(),
          Padding(
            padding: const EdgeInsets.fromLTRB(10, 10, 10, 0),
            child: Text(
              'Argent fictif. Le moteur ne regarde jamais les cotes.',
              style: Fp.body(11.5, color: Fp.text4, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}

class _SideItem extends StatelessWidget {
  const _SideItem({required this.section, required this.selected, required this.badge, required this.onTap});
  final DeskSection section;
  final bool selected;
  final int badge;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 3),
      child: Semantics(
        button: true,
        selected: selected,
        label: section.label,
        excludeSemantics: true,
        child: Material(
          color: selected ? Fp.accentSoft : Colors.transparent,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(11),
            side: BorderSide(color: selected ? Fp.accentLine : Colors.transparent),
          ),
          child: InkWell(
            borderRadius: BorderRadius.circular(11),
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
              child: Row(
                children: [
                  Icon(section.icon, size: 19, color: Fp.accentLight),
                  const SizedBox(width: 11),
                  Expanded(
                    child: Text(
                      section.label,
                      style: Fp.body(13.5, weight: FontWeight.w600, color: selected ? Fp.text : Fp.textSoft),
                    ),
                  ),
                  if (badge > 0)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 1),
                      decoration: BoxDecoration(
                        color: section == DeskSection.notifications ? Fp.loss : Fp.accent,
                        borderRadius: BorderRadius.circular(99),
                      ),
                      child: Text('$badge', style: Fp.body(11, weight: FontWeight.w700)),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// --- Barre du haut -----------------------------------------------------------

class _TopBar extends StatelessWidget {
  const _TopBar({required this.onSearch, required this.onProfile});
  final VoidCallback onSearch;
  final VoidCallback onProfile;

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final me = state.me;
    return Container(
      height: 62,
      padding: const EdgeInsets.symmetric(horizontal: 22),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Fp.divider)),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 380,
            child: Material(
              color: Fp.fill,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(11),
                side: const BorderSide(color: Fp.divider),
              ),
              child: InkWell(
                borderRadius: BorderRadius.circular(11),
                onTap: onSearch,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
                  child: Row(
                    children: [
                      const Icon(Icons.search_rounded, size: 18, color: Fp.text3),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Rechercher un match, une équipe, une rubrique',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: Fp.body(13, color: Fp.text3),
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                        decoration: BoxDecoration(
                          border: Border.all(color: Fp.line),
                          borderRadius: BorderRadius.circular(5),
                        ),
                        child: Text('Ctrl K', style: Fp.body(11, color: Fp.text3)),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          const Spacer(),
          if (me != null) ...[
            InkWell(
              borderRadius: BorderRadius.circular(99),
              onTap: onProfile,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 5),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(99),
                  border: Border.all(color: state.premium ? const Color(0x73FBBF24) : Fp.line),
                ),
                child: Text(
                  state.premium
                      ? '★ Premium · ${me.plan.daysLeft} jour${me.plan.daysLeft > 1 ? 's' : ''}'
                      : 'Formule gratuite',
                  style: Fp.body(12, weight: FontWeight.w700, color: state.premium ? Fp.warning : Fp.text2),
                ),
              ),
            ),
            const SizedBox(width: 18),
            Text.rich(
              TextSpan(
                text: 'Solde ',
                style: Fp.body(13, color: Fp.text2),
                children: [
                  TextSpan(
                    text: money(me.balance, me.currency),
                    style: Fp.body(13, weight: FontWeight.w700),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 16),
            Tooltip(
              message: 'Profil',
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: onProfile,
                child: CircleAvatar(
                  radius: 17,
                  backgroundColor: Fp.accent,
                  child: Text(
                    me.displayName.isEmpty ? '?' : me.displayName[0].toUpperCase(),
                    style: Fp.title(14, color: Colors.white),
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

// --- Coupon à droite ---------------------------------------------------------

class _CouponRail extends StatelessWidget {
  const _CouponRail();

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final shell = DesktopShell.of(context);
    final items = state.coupon;
    final total = items.fold<double>(1, (t, c) => t * c.offer.odds);
    final probs = [for (final c in items) c.offer.modelProbability];
    final chances = probs.contains(null) ? null : probs.fold<double>(1, (t, p) => t * p!);
    return Container(
      width: 320,
      decoration: const BoxDecoration(
        color: Color(0x8C0A090E),
        border: Border(left: BorderSide(color: Fp.divider)),
      ),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 20),
        children: [
          Row(
            children: [
              Expanded(
                child: Text('Mon coupon', style: Fp.title(15, weight: FontWeight.w600)),
              ),
              Tag('${items.length} / ${AppState.maxCoupon}', color: Fp.text2),
            ],
          ),
          const SizedBox(height: 12),
          if (items.isEmpty)
            GlassCard.section(
              child: Text(
                'Ouvre un match puis touche une cote pour l\'ajouter ici. Le coupon reste visible '
                'pendant que tu parcours les matchs.',
                style: Fp.body(13, color: Fp.text2, height: 1.45),
              ),
            )
          else ...[
            GlassCard.section(
              padding: const EdgeInsets.fromLTRB(14, 4, 6, 4),
              child: Column(
                children: [
                  for (final (i, c) in items.indexed) ...[
                    if (i > 0) const Divider(),
                    _RailLine(item: c, onRemove: () => state.removeFromCoupon(c)),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 12),
            GlassCard.section(
              child: Column(
                children: [
                  KeyRow('Cote totale', decimal(total), bold: true),
                  if (chances != null)
                    KeyRow('Chances selon le moteur', percent(chances, decimals: 1), color: Fp.accentLight),
                  KeyRow('Selon la cote', percent(1 / total, decimals: 1), color: Fp.text2),
                ],
              ),
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: () => shell?.open(DeskSection.coupon),
              child: const Text('Miser sur ce coupon'),
            ),
          ],
          const SizedBox(height: 14),
          GlassCard.section(
            highlight: true,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Coupon intelligent', style: Fp.title(14, weight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text(
                  'Le moteur compose un coupon selon ton profil, la cote visée et les jours choisis.',
                  style: Fp.body(12.5, color: Fp.text2, height: 1.4),
                ),
                const SizedBox(height: 10),
                OutlinedButton(
                  onPressed: () => shell?.open(DeskSection.intelligent),
                  child: const Text('Ouvrir l\'atelier'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _RailLine extends StatelessWidget {
  const _RailLine({required this.item, required this.onRemove});
  final CouponItem item;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final m = item.match, o = item.offer;
    final p = o.modelProbability;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  fullLabel(o.market, o.line, o.selection, home: m.home.name, away: m.away.name),
                  style: Fp.body(13, weight: FontWeight.w600),
                ),
                const SizedBox(height: 2),
                Text(
                  '${m.home.name} - ${m.away.name}${p == null ? '' : ' · ${percent(p)}'}',
                  style: Fp.body(11.5, color: Fp.text3),
                ),
              ],
            ),
          ),
          Text(odds(o.odds), style: Fp.title(14)),
          IconButton(
            tooltip: 'Retirer',
            visualDensity: VisualDensity.compact,
            onPressed: onRemove,
            icon: const Icon(Icons.close_rounded, size: 16, color: Fp.text3),
          ),
        ],
      ),
    );
  }
}

/// Ligne libellé / valeur compacte des colonnes de la version ordinateur.
class KeyRow extends StatelessWidget {
  const KeyRow(this.label, this.value, {super.key, this.color = Fp.text, this.bold = false});
  final String label;
  final String value;
  final Color color;
  final bool bold;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(
      children: [
        Expanded(
          child: Text(label, style: Fp.body(13, color: Fp.text2)),
        ),
        Text(
          value,
          style: Fp.body(13.5, color: color, weight: bold ? FontWeight.w800 : FontWeight.w600),
        ),
      ],
    ),
  );
}

// --- Recherche (Ctrl K) ------------------------------------------------------

class _Target {
  const _Target(this.section, [this.page]);
  final DeskSection section;
  final Widget? page;
}

class _Result {
  const _Result(this.icon, this.title, this.subtitle, this.target);
  final IconData icon;
  final String title;
  final String subtitle;
  final _Target target;
}

/// Sans accents ni majuscules : « malaga » trouve « Málaga ».
String fold(String s) {
  const from = 'àâäáãåçéèêëíìîïñóòôöõúùûüýÿœæ';
  const to = 'aaaaaaceeeeiiiinooooouuuuyyoa';
  final b = StringBuffer();
  for (final ch in s.toLowerCase().split('')) {
    final i = from.indexOf(ch);
    b.write(i < 0 ? ch : to[i]);
  }
  return b.toString();
}

class _SearchPalette extends StatefulWidget {
  const _SearchPalette();

  @override
  State<_SearchPalette> createState() => _SearchPaletteState();
}

class _SearchPaletteState extends State<_SearchPalette> {
  String query = '';
  int active = 0;
  List<Upcoming>? upcoming;

  @override
  void initState() {
    super.initState();
    context
        .read<AppState>()
        .api
        .get('/predictions/upcoming', {'limit': 400})
        .then((j) {
          if (mounted) setState(() => upcoming = [for (final u in j as List) Upcoming(u as Json)]);
        })
        .catchError((_) {
          if (mounted) setState(() => upcoming = const []);
        });
  }

  List<_Result> _results() {
    final q = fold(query.trim());
    final out = <_Result>[];
    if (q.isEmpty) {
      return [for (final s in DeskSection.values) _Result(s.icon, s.label, 'Rubrique', _Target(s))];
    }
    final teams = <int, (Team, String)>{};
    for (final u in upcoming ?? const <Upcoming>[]) {
      final m = u.match;
      final hay = fold('${m.home.name} ${m.away.name} ${competitionName(m.competition)}');
      if (!hay.contains(q)) continue;
      final s = u.summary;
      out.add(
        _Result(
          Icons.sports_soccer_rounded,
          '${m.home.name} - ${m.away.name}',
          '${shortDate(m.date)} · ${m.when} · ${competitionName(m.competition)}'
              '${s == null ? '' : '   ${percent(s.home.probability)} · ${percent(s.draw.probability)} · ${percent(s.away.probability)}'}',
          _Target(DeskSection.matchs, MatchScreen(matchId: m.id)),
        ),
      );
      for (final t in [m.home, m.away]) {
        if (fold(t.name).contains(q)) teams[t.id] = (t, m.competition);
      }
    }
    final matches = out.take(6).toList();
    return [
      ...matches,
      for (final (t, comp) in teams.values.take(4))
        _Result(
          Icons.shield_outlined,
          t.name,
          'Fiche équipe',
          _Target(DeskSection.championnats, TeamScreen(teamId: t.id, name: t.name, competition: comp)),
        ),
      for (final s in DeskSection.values)
        if (fold(s.label).contains(q)) _Result(s.icon, s.label, 'Rubrique', _Target(s)),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final results = _results();
    final sel = results.isEmpty ? -1 : active.clamp(0, results.length - 1);
    void choose(_Result r) => Navigator.pop(context, r.target);
    return Align(
      alignment: const Alignment(0, -0.55),
      child: Material(
        color: const Color(0xFF121019),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: Fp.line),
        ),
        clipBehavior: Clip.antiAlias,
        child: SizedBox(
          width: 640,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              CallbackShortcuts(
                bindings: {
                  const SingleActivator(LogicalKeyboardKey.arrowDown): () =>
                      setState(() => active = math.min(sel + 1, results.length - 1)),
                  const SingleActivator(LogicalKeyboardKey.arrowUp): () =>
                      setState(() => active = math.max(sel - 1, 0)),
                },
                child: TextField(
                  autofocus: true,
                  style: Fp.body(17),
                  decoration: const InputDecoration(
                    hintText: 'Équipe, match, championnat ou rubrique',
                    prefixIcon: Icon(Icons.search_rounded),
                    filled: false,
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    contentPadding: EdgeInsets.symmetric(vertical: 18),
                  ),
                  onChanged: (v) => setState(() {
                    query = v;
                    active = 0;
                  }),
                  onSubmitted: (_) {
                    if (sel >= 0) choose(results[sel]);
                  },
                ),
              ),
              const Divider(),
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 420),
                child: results.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.all(22),
                        child: Text(
                          upcoming == null ? 'Chargement des matchs…' : 'Aucun résultat pour « $query ».',
                          style: Fp.body(14, color: Fp.text3),
                        ),
                      )
                    : ListView(
                        shrinkWrap: true,
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        children: [
                          for (final (i, r) in results.indexed)
                            ListTile(
                              selected: i == sel,
                              selectedTileColor: Fp.accentSoft,
                              leading: Icon(r.icon, color: Fp.accentLight, size: 20),
                              title: Text(r.title, style: Fp.body(14, weight: FontWeight.w600)),
                              subtitle: Text(r.subtitle, style: Fp.body(12, color: Fp.text3)),
                              onTap: () => choose(r),
                            ),
                        ],
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
