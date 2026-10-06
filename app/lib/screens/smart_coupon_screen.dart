import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/client.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'daily_coupons_screen.dart';
import 'share_coupon.dart';

/// Coupon intelligent : la sélection la plus sûre de chaque match (selon le profil),
/// sur une période au choix, avec de vraies cotes et des faits pour chaque choix.
class SmartCouponScreen extends StatefulWidget {
  const SmartCouponScreen({super.key});

  static const profiles = [
    ('sur', 'Sûr', '75 à 92 % chacune'),
    ('equilibre', 'Équilibré', '60 à 75 % chacune'),
    ('audacieux', 'Audacieux', '45 à 60 % chacune'),
    ('grosse', 'Grosse cote', 'cote visée'),
  ];
  static const leagues = [
    'LIGUE_1',
    'EPL',
    'LA_LIGA',
    'SERIE_A',
    'BUNDESLIGA',
    'POR',
    'BEL',
    'NED',
    'GRE',
    'TUR',
    'SCO',
    'SUI',
    'NOR',
    'SWE',
    'DEN',
    'AUT',
  ];
  static const targets = [10, 25, 50, 100];
  static const hours = [(null, 'Toute heure'), (15, 'Après 15 h'), (18, 'Après 18 h'), (20, 'Après 20 h')];
  static const periods = [
    ('today', 'Aujourd\'hui'),
    ('tomorrow', 'Demain'),
    ('3days', '3 jours'),
    ('weekend', 'Ce week-end'),
    ('week', '7 jours'),
    ('next', 'Prochaine journée'),
    ('day', 'Un seul jour'),
    ('range', 'Plusieurs jours'),
  ];

  @override
  State<SmartCouponScreen> createState() => _SmartCouponScreenState();
}

class _SmartCouponScreenState extends State<SmartCouponScreen> {
  int profile = 1;
  int period = 5; // Prochaine journée : jamais vide pendant une trêve
  int size = 3;
  int maxBig = AppState.maxCoupon; // Grosse cote : plafond de sélections
  num target = 50;
  DateTime day = _today().add(const Duration(days: 1));
  DateTime? rangeTo;
  int hour = 0;
  final Set<String> competitions = {};
  final Set<int> excludedMatches = {};
  bool busy = false;
  bool more = false; // « Plus de réglages » ouvert
  Json? result;
  Object? error;

  static DateTime _today() {
    final n = DateTime.now();
    return DateTime(n.year, n.month, n.day);
  }

  bool get _big => SmartCouponScreen.profiles[profile].$1 == 'grosse';
  String get _period => SmartCouponScreen.periods[period].$1;

  static String _iso(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  Future<void> _generate() async {
    final state = context.read<AppState>();
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final query = <String, Object?>{
        'profile': SmartCouponScreen.profiles[profile].$1,
        'period': _period,
        'size': '${_big ? maxBig : size}',
        if (_big) 'target_odds': '$target',
        if (_period == 'day') 'day': _iso(day),
        if (_period == 'range') ...{'date_from': _iso(day), 'date_to': _iso(rangeTo ?? day)},
        if (SmartCouponScreen.hours[hour].$1 != null) 'after_hour': '${SmartCouponScreen.hours[hour].$1}',
      };
      final r = await state.api.get(_withLists(query)) as Json;
      if (mounted) setState(() => result = r);
    } on ApiException catch (e) {
      // Premium terminé ou retiré depuis la dernière mise à jour : le profil est relu,
      // l'écran affiche alors le cadenas.
      if (e.premiumRequired) await state.refreshMe().catchError((_) {});
      if (mounted) setState(() => error = e.premiumRequired ? null : e);
    } catch (e) {
      if (mounted) setState(() => error = e);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  /// Paramètres répétés (championnats, exclusions) : ajoutés à la main dans l'adresse.
  String _withLists(Map<String, Object?> query) {
    final parts = [
      for (final e in query.entries) '${e.key}=${Uri.encodeQueryComponent('${e.value}')}',
      for (final c in competitions) 'competitions=$c',
      for (final m in excludedMatches) 'exclude_matches=$m',
      for (final t in context.read<AppState>().excludedTeams.keys) 'exclude_teams=$t',
    ];
    return '/smart-coupon?${parts.join('&')}';
  }

  Future<void> _customTarget() async {
    final ctrl = TextEditingController(text: '$target');
    final v = await showDialog<num>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Cote visée'),
        content: TextField(
          controller: ctrl,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(helperText: 'De 2 à 1000'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
          FilledButton(
            onPressed: () => Navigator.pop(context, num.tryParse(ctrl.text.replaceAll(',', '.'))),
            child: const Text('Valider'),
          ),
        ],
      ),
    );
    if (v != null && v >= 2 && v <= 1000) setState(() => target = v);
  }

  /// Remplacer : la sélection est écartée, le moteur recompose le coupon sans ce match.
  Future<void> _replace(Json s) async {
    excludedMatches.add(s['match_id'] as int);
    await _generate();
  }

  Future<void> _exclude(Json s) async {
    final state = context.read<AppState>();
    final home = s['home'] as String, away = s['away'] as String;
    final choice = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: Fp.background,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Exclure $home – $away ?', style: Fp.title(17)),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: () => Navigator.pop(context, 'match'),
                child: const Text('Seulement ce match'),
              ),
              if (s['home_team_id'] != null) ...[
                const SizedBox(height: 8),
                OutlinedButton(
                  onPressed: () => Navigator.pop(context, 'home'),
                  child: Text('Toujours exclure $home'),
                ),
                const SizedBox(height: 8),
                OutlinedButton(
                  onPressed: () => Navigator.pop(context, 'away'),
                  child: Text('Toujours exclure $away'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
    if (choice == null) return;
    if (choice == 'match') excludedMatches.add(s['match_id'] as int);
    if (choice == 'home') await state.excludeTeam(s['home_team_id'] as int, home);
    if (choice == 'away') await state.excludeTeam(s['away_team_id'] as int, away);
    await _generate();
  }

  Future<void> _addToCoupon(List<Json> selections) async {
    setState(() => busy = true);
    try {
      await addSelectionsToCoupon(context.read<AppState>(), selections);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final premium = state.premium;
    final coupon = result?['coupon'] as Json?;
    final alternatives = ((result?['alternatives'] as List?) ?? const []).cast<Json>();
    final message = result?['message'] as String?;
    final days = [for (var i = 0; i < 10; i++) _today().add(Duration(days: i))];
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: ListView(
          padding: pagePadding(context, 16, 40, maxWidth: 1120),
          children: [
            BackHeader('Coupon', 'intelligent', trailing: premium ? const _PremiumPill() : null),
            const SizedBox(height: 14),
            if (!premium) ...[
              const PremiumLock(
                text:
                    'Le Coupon intelligent est inclus dans Premium. Les coupons du jour et leur bilan '
                    '(bouton historique en haut) restent publics.',
              ),
            ] else ...[
              ...deskSplit(
                context,
                [
                  _Label('Profil'),
                  // Maquette v2 : de grandes cases, le profil choisi en violet.
                  GridView.count(
                    crossAxisCount: 2,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    mainAxisSpacing: 8,
                    crossAxisSpacing: 8,
                    childAspectRatio: 2.9,
                    children: [
                      for (final (i, p) in SmartCouponScreen.profiles.indexed)
                        _ProfileTile(
                          title: p.$2,
                          subtitle: p.$3,
                          selected: i == profile,
                          onTap: () => setState(() => profile = i),
                        ),
                    ],
                  ),
                  if (_big) ...[
                    _Label('Cote visée'),
                    _Chips([
                      for (final t in SmartCouponScreen.targets)
                        FpChip('$t', selected: target == t, onTap: () => setState(() => target = t)),
                      FpChip(
                        SmartCouponScreen.targets.contains(target) ? 'Autre…' : 'Autre : ${decimal(target)}',
                        selected: !SmartCouponScreen.targets.contains(target),
                        onTap: _customTarget,
                      ),
                    ]),
                  ],
                  _Label('Période et championnats'),
                  _Chips([
                    for (final (i, p) in SmartCouponScreen.periods.indexed)
                      FpChip(p.$2, selected: i == period, onTap: () => setState(() => period = i)),
                  ]),
                  if (_period == 'day' || _period == 'range') ...[
                    const SizedBox(height: 10),
                    Text(_period == 'day' ? 'Jour' : 'Du', style: Fp.body(12, color: Fp.text3)),
                    const SizedBox(height: 6),
                    ChipRow(
                      labels: [for (final d in days) shortDate(d)],
                      selected: days.indexOf(day).clamp(0, days.length - 1),
                      onSelected: (i) => setState(() {
                        day = days[i];
                        if (rangeTo != null && rangeTo!.isBefore(day)) rangeTo = day;
                      }),
                    ),
                    if (_period == 'range') ...[
                      const SizedBox(height: 8),
                      Text('Au', style: Fp.body(12, color: Fp.text3)),
                      const SizedBox(height: 6),
                      ChipRow(
                        labels: [for (final d in days.where((d) => !d.isBefore(day))) shortDate(d)],
                        selected: (rangeTo == null ? 0 : rangeTo!.difference(day).inDays).clamp(0, 9),
                        onSelected: (i) => setState(() => rangeTo = day.add(Duration(days: i))),
                      ),
                    ],
                  ],
                  const SizedBox(height: 8),
                  _Chips([
                    FpChip('Tous', selected: competitions.isEmpty, onTap: () => setState(competitions.clear)),
                    for (final c in SmartCouponScreen.leagues)
                      FpChip(
                        competitionName(c),
                        selected: competitions.contains(c),
                        onTap: () => setState(
                          () => competitions.contains(c) ? competitions.remove(c) : competitions.add(c),
                        ),
                      ),
                  ]),
                  const SizedBox(height: 6),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton.icon(
                      onPressed: () => setState(() => more = !more),
                      icon: Icon(more ? Icons.expand_less_rounded : Icons.expand_more_rounded, size: 18),
                      label: Text(more ? 'Moins de réglages' : 'Plus de réglages'),
                    ),
                  ),
                  if (more) ...[
                    _Label('Heure des matchs'),
                    _Chips([
                      for (final (i, h) in SmartCouponScreen.hours.indexed)
                        FpChip(h.$2, selected: i == hour, onTap: () => setState(() => hour = i)),
                    ]),
                    _Label(_big ? 'Sélections au maximum' : 'Nombre de sélections'),
                    ChipRow(
                      labels: [for (var i = 1; i <= AppState.maxCoupon; i++) '$i'],
                      selected: (_big ? maxBig : size) - 1,
                      onSelected: (i) => setState(() => _big ? maxBig = i + 1 : size = i + 1),
                    ),
                  ],
                  if (state.excludedTeams.isNotEmpty || excludedMatches.isNotEmpty) ...[
                    _Label('Exclus'),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final e in state.excludedTeams.entries)
                          InputChip(label: Text(e.value), onDeleted: () => state.includeTeam(e.key)),
                        if (excludedMatches.isNotEmpty)
                          InputChip(
                            label: Text('${excludedMatches.length} match(s) écarté(s)'),
                            onDeleted: () => setState(excludedMatches.clear),
                          ),
                      ],
                    ),
                  ],
                  const SizedBox(height: 10),
                  FilledButton(
                    onPressed: busy ? null : _generate,
                    child: Text(busy ? 'Recherche…' : 'Composer le coupon'),
                  ),
                ],
                [
                  const SizedBox(height: 14),
                  if (error != null) ErrorPanel(error: error!),
                  if (message != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(message, style: Fp.body(13, color: Fp.warning, height: 1.4)),
                    ),
                  if (coupon != null) ...[
                    _CouponCard(
                      coupon: coupon,
                      big: _big,
                      onReplace: busy ? null : _replace,
                      onExclude: busy ? null : _exclude,
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton(
                            onPressed: () => shareCoupon(
                              context,
                              _sels(coupon),
                              coupon,
                              '${result?['profile_label'] ?? ''}',
                            ),
                            child: const Text('Partager en image'),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: FilledButton(
                            onPressed: busy ? null : () => _addToCoupon(_sels(coupon)),
                            child: const Text('Ajouter au coupon'),
                          ),
                        ),
                      ],
                    ),
                    if (alternatives.isNotEmpty) ...[
                      const SectionTitle('Autres choix (moins sûrs)'),
                      for (final s in alternatives)
                        GlassCard.section(
                          margin: const EdgeInsets.only(bottom: 10),
                          child: _SelectionRow(
                            s,
                            trailing: IconButton(
                              tooltip: 'Ajouter au coupon',
                              icon: const Icon(Icons.add_circle_outline_rounded, color: Fp.accentLight),
                              onPressed: busy ? null : () => _addToCoupon([s]),
                            ),
                          ),
                        ),
                    ],
                    const SizedBox(height: 12),
                    Text(
                      'Une information, pas un conseil : le moteur ne cherche pas de « bon coup ». La cote '
                      'du bookmaker contient sa marge ; rien n\'est joué sans ta validation.',
                      style: Fp.body(12, color: Fp.text2, height: 1.4),
                    ),
                  ],
                ],
              ),
            ],
            const SizedBox(height: 8),
            Center(
              child: Tooltip(
                message: 'Coupons du jour',
                child: TextButton(
                  onPressed: () =>
                      Navigator.of(context)
                          .push(MaterialPageRoute(builder: (_) => const DailyCouponsScreen())),
                  child: const Text('Voir les coupons du jour et leur bilan'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  static List<Json> _sels(Json coupon) => (coupon['selections'] as List).cast<Json>();
}

class _CouponCard extends StatelessWidget {
  const _CouponCard({required this.coupon, this.big = false, this.onReplace, this.onExclude});
  final Json coupon;
  final bool big;
  final void Function(Json)? onReplace;
  final void Function(Json)? onExclude;

  @override
  Widget build(BuildContext context) {
    final sels = (coupon['selections'] as List).cast<Json>();
    final p = (coupon['probability'] as num).toDouble();
    final implied = (coupon['implied_probability'] as num).toDouble();
    final oneIn = (coupon['one_in'] as num?)?.toInt() ?? (p > 0 ? (1 / p).round() : null);
    return GlassCard.section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              const Expanded(child: TwoToneTitle('Coupon', 'proposé', size: 17)),
              Text(odds(coupon['total_odds']), style: Fp.title(19)),
            ],
          ),
          const Divider(height: 18),
          for (final (i, s) in sels.indexed) ...[
            if (i > 0) const Divider(height: 18),
            _SelectionRow(
              s,
              trailing: onReplace == null
                  ? null
                  : Column(
                      children: [
                        IconButton(
                          tooltip: 'Remplacer',
                          visualDensity: VisualDensity.compact,
                          icon: const Icon(Icons.autorenew_rounded, size: 18, color: Fp.text2),
                          onPressed: () => onReplace!(s),
                        ),
                        IconButton(
                          tooltip: 'Exclure',
                          visualDensity: VisualDensity.compact,
                          icon: const Icon(Icons.close_rounded, size: 18, color: Fp.text2),
                          onPressed: () => onExclude!(s),
                        ),
                      ],
                    ),
            ),
          ],
          const Divider(height: 18),
          Row(
            children: [
              Expanded(
                child: Text('Chance selon le moteur', style: Fp.body(14, color: Fp.text2)),
              ),
              Text(
                percent(p, decimals: p < 0.1 ? 1 : 0),
                style: Fp.body(15, weight: FontWeight.w800),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            [
              if (oneIn != null) '1 chance sur $oneIn',
              'selon la cote (marge comprise) : ${percent(implied, decimals: 1)}',
            ].join(' · '),
            style: Fp.body(12, color: Fp.text3),
          ),
          if (big || sels.length >= 6) ...[
            const SizedBox(height: 8),
            Text(
              'Coupon à gros risque : le bookmaker prend une marge d\'environ 5 à 8 % sur chaque cote, '
              'et ces marges se multiplient avec le nombre de sélections. Argent fictif.',
              style: Fp.body(12, color: Fp.warning, height: 1.4),
            ),
          ],
        ],
      ),
    );
  }
}

/// Petit titre de rubrique (maquette v2).
class _Label extends StatelessWidget {
  const _Label(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 14, bottom: 8),
    child: Text(
      text,
      style: Fp.body(13, weight: FontWeight.w700, color: Fp.text2),
    ),
  );
}

/// Puces sur une ligne qui défile (toutes construites : rien de caché aux lecteurs d'écran).
class _Chips extends StatelessWidget {
  const _Chips(this.children);
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    child: Row(
      children: [
        for (final (i, c) in children.indexed) ...[if (i > 0) const SizedBox(width: 8), c],
      ],
    ),
  );
}

/// Case de profil : nom en gras, repère en dessous ; violette quand elle est choisie.
class _ProfileTile extends StatelessWidget {
  const _ProfileTile({
    required this.title,
    required this.subtitle,
    required this.selected,
    required this.onTap,
  });
  final String title;
  final String subtitle;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(14),
      side: BorderSide(color: selected ? const Color(0x99A78BFA) : Fp.line12),
    );
    return Material(
      color: selected ? Fp.accentAlpha(0.24) : Fp.fill,
      shape: shape,
      child: InkWell(
        customBorder: shape,
        onTap: onTap,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(title, style: Fp.body(14, weight: FontWeight.w800)),
              const SizedBox(height: 2),
              Text(subtitle, style: Fp.body(11.5, color: selected ? const Color(0xFFE4D8FD) : Fp.text2)),
            ],
          ),
        ),
      ),
    );
  }
}

class _PremiumPill extends StatelessWidget {
  const _PremiumPill();

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(99),
      border: Border.all(color: const Color(0x99A78BFA)),
      color: Fp.accentAlpha(0.18),
    ),
    child: Text(
      'PREMIUM',
      style: Fp.body(11, weight: FontWeight.w800, color: const Color(0xFFE4D8FD)),
    ),
  );
}

class _SelectionRow extends StatelessWidget {
  const _SelectionRow(this.s, {this.trailing});
  final Json s;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final home = s['home'] as String, away = s['away'] as String;
    final kickoff = parseDate(s['kickoff_at'])?.toLocal();
    final reasons = ((s['reasons'] as List?) ?? const []).cast<String>();
    final result = s['result'] as String?;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text.rich(
                TextSpan(
                  children: [
                    TextSpan(
                      text: fullLabel(
                        s['market'] as String,
                        (s['line'] ?? '') as String,
                        s['selection'] as String,
                        home: home,
                        away: away,
                      ),
                    ),
                    TextSpan(text: ' · ${odds(s['odds'])}'),
                  ],
                ),
                style: Fp.body(14.5, weight: FontWeight.w800),
              ),
              const SizedBox(height: 2),
              Text(
                'Moteur ${percent((s['model_probability'] as num).toDouble())} · $home – $away'
                '${kickoff != null ? ' · ${shortDate(kickoff)} ${hourMinute(kickoff)}' : ''}',
                style: Fp.body(12, color: Fp.text2),
              ),
              if (explainSelection(
                    s['market'] as String,
                    (s['line'] ?? '') as String,
                    s['selection'] as String,
                    home: home,
                    away: away,
                  )
                  case final e?)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(e, style: Fp.body(12, color: Fp.accentLight, height: 1.35)),
                ),
              for (final r in reasons)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text('• $r', style: Fp.body(12, color: Fp.text3, height: 1.35)),
                ),
            ],
          ),
        ),
        if (result != null && result != 'pending') ...[
          const SizedBox(width: 10),
          result == 'win' || result == 'half_win'
              ? Tag.win(resultLabel(result))
              : result == 'loss' || result == 'half_loss'
              ? Tag.loss(resultLabel(result))
              : Tag(resultLabel(result)),
        ],
        ?trailing,
      ],
    );
  }
}

/// Coupons du jour : enregistrés chaque matin avant les matchs, gagnés ou perdus, rien n'est effacé.
class SmartHistoryScreen extends StatelessWidget {
  const SmartHistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          load: () async => await api.get('/smart-coupons/history') as Json,
          builder: (context, data, reload) {
            final stats = (data['stats'] as Map).cast<String, dynamic>();
            final coupons = (data['coupons'] as List).cast<Json>();
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: pagePadding(context, 16, 40),
                children: [
                  const BackHeader(
                    'Coupons',
                    'du jour',
                    subtitle:
                        'Chaque matin, un coupon par profil est enregistré avant les matchs. Tous restent '
                        'affichés, gagnés ou perdus : c\'est le vrai bilan du Coupon intelligent.',
                  ),
                  const SizedBox(height: 16),
                  GlassCard.section(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text('Bilan', style: Fp.title(15, weight: FontWeight.w600)),
                        for (final st in stats.values.cast<Json>())
                          KeyValue(
                            st['label'] as String,
                            st['settled'] == 0
                                ? 'aucun coupon réglé'
                                : '${st['won']} gagné(s) sur ${st['settled']} · annoncé '
                                      '${percent((st['announced'] as num).toDouble())}, '
                                      'observé ${percent((st['observed'] as num).toDouble())}',
                          ),
                        const SizedBox(height: 4),
                        Text(
                          'Sur peu de coupons, l\'écart entre annoncé et observé est surtout du hasard.',
                          style: Fp.body(11, color: Fp.text3),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  if (coupons.isEmpty)
                    const EmptyState('Aucun coupon du jour pour l\'instant.', icon: Icons.history_rounded),
                  for (final c in coupons)
                    GlassCard.section(
                      margin: const EdgeInsets.only(bottom: 12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  '${c['profile_label']} · ${shortDate(DateTime.parse(c['day'] as String))}',
                                  style: Fp.title(14, weight: FontWeight.w600),
                                ),
                              ),
                              switch (c['status']) {
                                'won' => const Tag.win('Gagné'),
                                'lost' => const Tag.loss('Perdu'),
                                'pending' => const Tag('En cours'),
                                final s => Tag(resultLabel(s as String)),
                              },
                            ],
                          ),
                          const SizedBox(height: 10),
                          for (final s in (c['selections'] as List).cast<Json>())
                            Padding(padding: const EdgeInsets.only(bottom: 10), child: _SelectionRow(s)),
                          Text(
                            'Cote ${odds(c['total_odds'])} · probabilité annoncée '
                            '${percent((c['probability'] as num).toDouble(), decimals: 1)}',
                            style: Fp.body(12, color: Fp.text2),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

/// Ajoute des sélections (coupon intelligent ou coupon du jour) au coupon personnel, aux
/// cotes actuelles relues sur le serveur ; une sélection sans cote disponible est comptée.
Future<void> addSelectionsToCoupon(AppState state, List<Json> selections) async {
  var added = 0, missing = 0;
  try {
    for (final s in selections) {
      final id = s['match_id'] as int;
      final match = MatchInfo(await state.api.get('/matches/$id') as Json);
      final key = '${s['market']}|${s['line'] ?? ''}|${s['selection']}';
      final offers = [for (final o in await state.api.get('/matches/$id/offer') as List) Offer(o as Json)];
      final offer = offers.where((o) => o.key == key).firstOrNull;
      if (offer == null) {
        missing++;
      } else if (!state.inCoupon(id, key)) {
        state.toggleCoupon(match, offer);
        added++;
      }
    }
    showMessage(
      missing > 0
          ? '$added sélection(s) ajoutée(s) ; $missing sans cote disponible à présent.'
          : '$added sélection(s) ajoutée(s) au coupon (onglet Coupon).',
    );
  } on ApiException catch (e) {
    showMessage(e.message, error: true);
  }
}
