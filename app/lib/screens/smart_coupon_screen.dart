import 'dart:ui' show ImageFilter;

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
import '../widgets/maquette.dart';
import 'bookmaker_screen.dart' as bookmaker;
import 'daily_coupons_screen.dart';
import 'premium_screen.dart' show PremiumCard;
import 'share_coupon.dart';

/// Coupon intelligent : la sélection la plus sûre de chaque match (selon le profil),
/// sur une période au choix, avec de vraies cotes et des faits pour chaque choix.
class SmartCouponScreen extends StatefulWidget {
  const SmartCouponScreen({super.key});

  static const profiles = [
    ('sur', 'Sûr', '75 à 92 % chacune'),
    // Ce que le joueur reçoit vraiment (rapport du 07/11/2026 : « 60 à 75 % » affiché, toutes
    // les sélections à 75 %) : la plus sûre de chaque match dans la tranche, donc le haut.
    ('equilibre', 'Équilibré', 'près de 75 % chacune'),
    ('audacieux', 'Audacieux', 'près de 60 % chacune'),
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
    'POL',
    'CZE',
    'CRO',
    'ROU',
    'SRB',
    'ISR',
    'UCL',
    'UEL',
    'UECL',
    'CAN',
    'CANQ',
    'WC',
    'WCQ_AFR',
    'WCQ_EUR',
    'WCQ_SAM',
    'EURO',
    'EUROQ',
    'UNL',
    'COPA',
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
  num target = 25; // le choix le plus courant (essai du 07/11/2026 : 50 coché d'office)
  DateTime day = _today().add(const Duration(days: 1));
  DateTime? rangeTo;
  int hour = 0;
  final Set<String> competitions = {};
  final Set<int> excludedMatches = {};

  /// Championnats écartés (« Toujours exclure ce championnat »), pour ce coupon.
  final Set<String> excludedCompetitions = {};
  bool composing = false; // le moteur compose le coupon
  String? adding; // « Ajout 3 / 7… » pendant l'ajout au coupon
  bool get busy => composing || adding != null;
  bool more = false; // « Plus de réglages » ouvert
  Json? result;
  Object? error;

  /// « Un autre coupon » : tirage suivant parmi les sélections presque à égalité (0 : le tien).
  int variant = 0;

  static DateTime _today() {
    final n = DateTime.now();
    return DateTime(n.year, n.month, n.day);
  }

  bool get _big => SmartCouponScreen.profiles[profile].$1 == 'grosse';
  String get _period => SmartCouponScreen.periods[period].$1;

  static String _iso(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  Future<void> _generate({bool another = false}) async {
    final state = context.read<AppState>();
    setState(() {
      composing = true;
      error = null;
      variant = another ? (variant + 1) % 100 : 0;
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
        if (variant > 0) 'variant': '$variant',
      };
      final r = await state.api.get(_withLists(query), null, ApiClient.slowTimeout) as Json;
      state.beta.action('coupon_compose');
      if (mounted) setState(() => result = r);
    } on ApiException catch (e) {
      // Premium terminé ou retiré depuis la dernière mise à jour : le profil est relu,
      // l'écran affiche alors le cadenas.
      if (e.premiumRequired) await state.refreshMe().catchError((_) {});
      if (mounted) setState(() => error = e.premiumRequired ? null : e);
    } catch (e) {
      if (mounted) setState(() => error = e);
    } finally {
      if (mounted) setState(() => composing = false);
    }
  }

  /// La règle du coupon proposé, avec la raison d'une cote au-dessus de la cible.
  static String? _rule(Json r) {
    final coupon = r['coupon'] as Json?;
    if (coupon == null) return null;
    // Cotes envoyées en texte par le serveur (« 29.07 ») : lues comme dans le reste de l'écran.
    final total = double.parse('${coupon['total_odds']}');
    final target = r['target_odds'] == null ? null : double.parse('${r['target_odds']}');
    if (target != null) {
      final over = total / target - 1;
      return 'Règle : les sélections les plus sûres de la période selon le moteur (une par match), '
          'ajoutées une à une jusqu\'à dépasser la cote visée. Cote obtenue ${odds(total)} pour '
          '${odds(target)} visée${over > 0.1 ? ' : la dernière sélection ajoutée fait dépasser la cible' : ''}.';
    }
    final range = (r['range'] as List?)?.map((v) => double.parse('$v')).toList();
    if (range == null || range.length < 2) return null;
    return 'Règle : les sélections les plus sûres de la période parmi celles que le moteur annonce '
        'entre ${percent(range[0])} et ${percent(range[1])} (profil '
        '${r['profile_label']}), une par match : souvent tout près de ${percent(range[1])}.';
  }

  /// Paramètres répétés (championnats, exclusions) : ajoutés à la main dans l'adresse.
  String _withLists(Map<String, Object?> query) {
    final parts = [
      for (final e in query.entries) '${e.key}=${Uri.encodeQueryComponent('${e.value}')}',
      for (final c in competitions) 'competitions=$c',
      for (final m in excludedMatches) 'exclude_matches=$m',
      for (final t in context.read<AppState>().excludedTeams.keys) 'exclude_teams=$t',
      for (final c in excludedCompetitions) 'exclude_competitions=$c',
    ];
    return '/smart-coupon?${parts.join('&')}';
  }

  /// Cote visée personnalisée : champ vide, valeur refusée avec un message (essai du 07/11/2026 :
  /// 1,5, 0 ou « abc » fermaient la fenêtre sans rien dire).
  Future<void> _customTarget() async {
    final ctrl = TextEditingController();
    String? error;
    final v = await showDialog<num>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setLocal) {
          void submit() {
            final n = num.tryParse(ctrl.text.trim().replaceAll(',', '.'));
            if (n == null || n < 2 || n > 1000) {
              setLocal(() => error = 'Écris une cote entre 2 et 1000 (par exemple 15 ou 12,5).');
              return;
            }
            Navigator.pop(context, n);
          }

          return AlertDialog(
            title: const Text('Cote visée'),
            content: TextField(
              controller: ctrl,
              autofocus: true,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              onSubmitted: (_) => submit(),
              decoration: InputDecoration(
                hintText: 'Actuelle : ${decimal(target)}',
                helperText: error == null ? 'De 2 à 1000' : null,
                errorText: error,
                errorMaxLines: 3,
              ),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
              FilledButton(onPressed: submit, child: const Text('Valider')),
            ],
          );
        },
      ),
    );
    if (v != null) setState(() => target = v);
  }

  /// Remplacer : la sélection est écartée, le moteur recompose le coupon sans ce match.
  Future<void> _replace(Json s) async {
    excludedMatches.add(s['match_id'] as int);
    await _generate();
  }

  /// « Changer » (rapport du 07/11/2026 : Remplacer et Exclure faisaient la même chose, et
  /// on ne pouvait pas retirer une sélection) : un seul bouton, cinq choix.
  Future<void> _change(Json s) async {
    final state = context.read<AppState>();
    final home = s['home'] as String, away = s['away'] as String;
    final comp = s['competition'] as String?;
    Widget option(String value, String label, {IconData? icon}) => ListTile(
      leading: Icon(icon, color: Fp.accentLight, size: 20),
      title: Text(label, style: Fp.body(14)),
      onTap: () => Navigator.pop(context, value),
    );
    final choice = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: Fp.background,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(8, 16, 8, 8),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Text('$home – $away', style: Fp.title(17)),
              ),
              const SizedBox(height: 6),
              option('replace', 'Remplacer par un autre match', icon: Icons.autorenew_rounded),
              option('remove', 'Retirer sans remplacer', icon: Icons.remove_circle_outline_rounded),
              if (s['home_team_id'] != null) ...[
                option('home', 'Toujours exclure $home', icon: Icons.block_rounded),
                option('away', 'Toujours exclure $away', icon: Icons.block_rounded),
              ],
              if (comp != null)
                option(
                  'comp',
                  'Exclure ce championnat (${competitionName(comp)})',
                  icon: Icons.block_rounded,
                ),
              TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
            ],
          ),
        ),
      ),
    );
    switch (choice) {
      case 'replace':
        await _replace(s);
      case 'remove':
        _remove(s);
      case 'home':
        await state.excludeTeam(s['home_team_id'] as int, home);
        await _generate();
      case 'away':
        await state.excludeTeam(s['away_team_id'] as int, away);
        await _generate();
      case 'comp':
        excludedCompetitions.add(comp!);
        await _generate();
    }
  }

  /// Retirer sans remplacer : le coupon garde les autres sélections ; cote et chances
  /// recalculées sur place (produit des cotes, produit des chances du moteur).
  void _remove(Json s) {
    final r = result;
    final coupon = r?['coupon'] as Json?;
    if (r == null || coupon == null) return;
    final sels = [
      for (final x in (coupon['selections'] as List).cast<Json>())
        if (x['match_id'] != s['match_id']) x,
    ];
    excludedMatches.add(s['match_id'] as int);
    if (sels.isEmpty) {
      setState(() => result = {...r, 'coupon': null, 'message': 'Coupon vide : compose un nouveau coupon.'});
      return;
    }
    var total = 1.0, p = 1.0;
    for (final x in sels) {
      total *= double.parse('${x['odds']}');
      p *= (x['model_probability'] as num).toDouble();
    }
    setState(
      () => result = {
        ...r,
        'coupon': {
          ...coupon,
          'selections': sels,
          'total_odds': total.toStringAsFixed(2),
          'probability': p,
          'implied_probability': 1 / total,
          'one_in': (1 / p).round(),
        },
      },
    );
  }

  Future<void> _addToCoupon(List<Json> selections) async {
    setState(() => adding = 'Ajout…');
    final state = context.read<AppState>();
    try {
      await addSelectionsToCoupon(
        state,
        selections,
        onProgress: (done, total) {
          if (mounted) setState(() => adding = 'Ajout $done / $total…');
        },
      );
      state.beta.action('coupon_add');
    } finally {
      if (mounted) setState(() => adding = null);
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
            if (premium) ...[
              const BackHeader('Coupon', 'intelligent', trailing: _PremiumPill()),
              const SizedBox(height: 14),
            ],
            if (!premium) ...[
              const _LockedPreview(),
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
                        SmartCouponScreen.targets.contains(target)
                            ? 'Autre…'
                            : 'Autre : ${decimal(target, max: 2)}',
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
                  // Exclusions toujours visibles, au-dessus de « Composer le coupon ».
                  if (state.excludedTeams.isNotEmpty ||
                      excludedMatches.isNotEmpty ||
                      excludedCompetitions.isNotEmpty) ...[
                    _Label('Exclus'),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final e in state.excludedTeams.entries)
                          InputChip(label: Text(e.value), onDeleted: () => state.includeTeam(e.key)),
                        for (final c in excludedCompetitions)
                          InputChip(
                            label: Text(competitionName(c)),
                            onDeleted: () => setState(() => excludedCompetitions.remove(c)),
                          ),
                        if (excludedMatches.isNotEmpty)
                          InputChip(
                            label: Text(
                              excludedMatches.length == 1
                                  ? '1 match écarté'
                                  : '${excludedMatches.length} matchs écartés',
                            ),
                            onDeleted: () => setState(excludedMatches.clear),
                          ),
                      ],
                    ),
                  ],
                  const SizedBox(height: 10),
                  FilledButton(
                    onPressed: busy ? null : _generate,
                    child: Text(composing ? 'Recherche…' : 'Composer le coupon'),
                  ),
                  if (composing) const SlowWait(),
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
                      rule: _rule(result!),
                      onChange: busy ? null : _change,
                      label: '${result?['profile_label'] ?? ''}',
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
                            child: Text(adding ?? 'Ajouter au coupon'),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    // Proposition du 07/11/2026 : plus le même coupon pour tous (tout le monde
                    // perdant le même jour) ; le joueur le sait et peut en demander un autre.
                    Text(
                      [
                        'Composé pour toi parmi les meilleurs de la période : les autres joueurs '
                            'reçoivent des coupons proches, pas forcément les mêmes. Le tien reste le même '
                            'toute la journée.',
                        if (coupon['best_probability'] case final num b
                            when b - (coupon['probability'] as num) >= 0.0005)
                          'Chance de ce coupon : ${percent((coupon['probability'] as num).toDouble(), decimals: 1)} '
                              '(le meilleur : ${percent(b.toDouble(), decimals: 1)}).',
                      ].join(' '),
                      style: Fp.body(12, color: Fp.text2, height: 1.4),
                    ),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton.icon(
                        onPressed: busy ? null : () => _generate(another: true),
                        icon: const Icon(Icons.refresh_rounded, size: 18),
                        label: const Text('Un autre coupon'),
                      ),
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
                      'Une information, pas un conseil : le moteur ne cherche pas de « bon coup ». La chance '
                      'annoncée a été vérifiée sur les saisons 2022 à 2025 (prudente pour « Sûr ») ; la cote '
                      'du bookmaker contient sa marge. Rien n\'est joué sans ta validation.',
                      style: Fp.body(12, color: Fp.text2, height: 1.4),
                    ),
                  ],
                ],
              ),
            ],
            // Version gratuite : déjà dans la carte « Inclus dans Premium » (bilan des coupons).
            if (premium) const SizedBox(height: 8),
            if (premium)
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
  const _CouponCard({required this.coupon, this.big = false, this.rule, this.onChange, this.label = ''});

  /// Comment le moteur a composé ce coupon, en une phrase (essai réel du 06/11/2026 : le
  /// joueur ne comprenait ni les « 60 % » partout ni la cote au-dessus de la cible).
  final String? rule;
  final Json coupon;
  final bool big;
  final void Function(Json)? onChange;

  /// Profil (« Grosse cote », « Équilibré »…).
  final String label;

  @override
  Widget build(BuildContext context) {
    final sels = (coupon['selections'] as List).cast<Json>();
    final p = (coupon['probability'] as num).toDouble();
    final implied = (coupon['implied_probability'] as num).toDouble();
    // Maquette C4 du 07/11/2026 : en haut, la cote et, à côté, la chance du coupon (revue :
    // « 31,32 » sans sa chance laissait croire à un bon coup) ; dessous, les sélections.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Fp.cardHigh,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: Fp.accent2, width: 1.5),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          [
                            'Coupon proposé',
                            if (label.isNotEmpty) label,
                            '${sels.length} sélection${sels.length > 1 ? 's' : ''}',
                          ].join(' · '),
                          style: Fp.body(12, color: Fp.muted),
                        ),
                        Text(odds(coupon['total_odds']), style: Fp.body(30, weight: FontWeight.w800)),
                      ],
                    ),
                  ),
                  const SizedBox(width: 10),
                  Flexible(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          'Chance selon le moteur',
                          textAlign: TextAlign.right,
                          style: Fp.body(12, color: Fp.muted),
                        ),
                        Text(
                          percent(p, decimals: p < 0.1 ? 1 : 0),
                          style: Fp.body(22, weight: FontWeight.w700, color: Fp.warning),
                        ),
                        if (p > 0)
                          Text(
                            chanceInWords(p),
                            textAlign: TextAlign.right,
                            style: Fp.body(12, color: Fp.muted),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                'Selon la cote (marge comprise) : ${percent(implied, decimals: 1)}.',
                style: Fp.body(12, color: Fp.muted),
              ),
              if (rule != null) ...[
                const SizedBox(height: 6),
                Text(rule!, style: Fp.body(12, color: Fp.muted, height: 1.4)),
              ],
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
        ),
        const SizedBox(height: 12),
        GlassCard.section(
          padding: const EdgeInsets.fromLTRB(14, 4, 14, 4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (final (i, s) in sels.indexed) ...[
                if (i > 0) const Divider(height: 1, color: Fp.divider),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 13),
                  child: _SelectionRow(
                    s,
                    oddsRight: true,
                    trailing: onChange == null
                        ? null
                        : InkWell(
                            onTap: () => onChange!(s),
                            borderRadius: BorderRadius.circular(8),
                            child: Padding(
                              padding: const EdgeInsets.only(top: 6, left: 6, bottom: 2),
                              child: Text(
                                'Changer',
                                style: Fp.body(13, color: Fp.lilac, weight: FontWeight.w600),
                              ),
                            ),
                          ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
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
  // Maquette C4 : étiquette pleine #2B2060, texte violet clair.
  Widget build(BuildContext context) => const Tag('PREMIUM', color: Fp.lilac, background: Fp.cardHigh);
}

class _SelectionRow extends StatelessWidget {
  const _SelectionRow(this.s, {this.trailing, this.oddsRight = false});
  final Json s;
  final Widget? trailing;

  /// Maquette C4 : la cote à droite, « Changer » dessous (sinon après le libellé).
  final bool oddsRight;

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
                    if (!oddsRight) TextSpan(text: ' · ${odds(s['odds'])}'),
                  ],
                ),
                style: Fp.body(14, weight: FontWeight.w700),
              ),
              const SizedBox(height: 2),
              Text(
                'moteur ${percent((s['model_probability'] as num).toDouble())} · '
                '${competitionName(s['competition'] as String)} · $home – $away'
                '${kickoff != null ? ' · ${shortDate(kickoff)} ${hourMinute(kickoff)}' : ''}',
                style: Fp.body(12, color: Fp.text2),
              ),
              // Score de la sélection réglée (rapport du 09/11/2026 : seulement « Gagné »).
              if (result != null && result != 'pending' && s['score'] is List)
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(
                    'Score final${bookmaker.scoreText(s['market'] as String, (s['score'] as List).cast<int?>(), (s['count'] as List?)?.cast<int>(), s['count_label'] as String?).replaceFirst(' ·', ' :')}',
                    style: Fp.body(12, color: Fp.muted),
                  ),
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
        if (oddsRight)
          Padding(
            padding: const EdgeInsets.only(left: 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(odds(s['odds']), style: Fp.body(16, weight: FontWeight.w700)),
                ?trailing,
              ],
            ),
          )
        else
          ?trailing,
      ],
    );
  }
}

/// Bilan des coupons du jour, un profil par ligne : un coupon Sûr et un Audacieux n'ont pas
/// la même chance de passer, ils ne s'additionnent pas. Chance annoncée contre réalisée.
class ProfileRecordCard extends StatelessWidget {
  const ProfileRecordCard(this.title, this.stats, {super.key});
  final String title;
  final Map<String, dynamic> stats;

  @override
  Widget build(BuildContext context) {
    return GlassCard.section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(title, style: Fp.title(15, weight: FontWeight.w600)),
          const SizedBox(height: 4),
          for (final st in stats.values.cast<Json>())
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(st['label'] as String, style: Fp.body(14, weight: FontWeight.w700)),
                      ),
                      Text(
                        st['settled'] == 0
                            ? 'aucun coupon réglé'
                            : '${st['won']} gagné${(st['won'] as int) > 1 ? 's' : ''} sur ${st['settled']}',
                        style: Fp.body(14, weight: FontWeight.w700),
                      ),
                    ],
                  ),
                  if (st['settled'] != 0)
                    Text(
                      'Chance annoncée ${percent((st['announced'] as num).toDouble())} · '
                      'réalisé ${percent((st['observed'] as num).toDouble())}',
                      style: Fp.body(12, color: Fp.text2),
                    ),
                ],
              ),
            ),
          const SizedBox(height: 4),
          Text(
            'Sur peu de coupons, l\'écart entre annoncé et réalisé est surtout du hasard.',
            style: Fp.body(11, color: Fp.text3),
          ),
        ],
      ),
    );
  }
}

/// Coupons du jour : enregistrés chaque matin avant les matchs, gagnés ou perdus, rien n'est effacé.
/// Les plus anciens se chargent page par page (« Voir les coupons plus anciens »).
class SmartHistoryScreen extends StatefulWidget {
  const SmartHistoryScreen({super.key});

  @override
  State<SmartHistoryScreen> createState() => _SmartHistoryScreenState();
}

class _SmartHistoryScreenState extends State<SmartHistoryScreen> {
  final List<Json> _older = [];
  final List<Json> _olderDays = [];
  Object? _firstDay;
  bool? _olderHasMore;
  bool _loading = false;

  Future<void> _loadMore(ApiClient api, int offset) async {
    setState(() => _loading = true);
    try {
      final page = await api.get('/smart-coupons/history', {'offset': offset}) as Json;
      if (!mounted) return;
      setState(() {
        _older.addAll((page['coupons'] as List).cast<Json>());
        _olderDays.addAll(((page['days'] as List?) ?? const []).cast<Json>());
        _firstDay = page['first_day'];
        _olderHasMore = page['has_more'] as bool? ?? false;
      });
    } on ApiException catch (e) {
      showMessage(e.message, error: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          load: () async {
            _older.clear();
            _olderDays.clear();
            _olderHasMore = null;
            return await api.get('/smart-coupons/history') as Json;
          },
          builder: (context, data, reload) {
            final stats = (data['stats'] as Map).cast<String, dynamic>();
            final first = (data['coupons'] as List).cast<Json>();
            final coupons = [...first, ..._older];
            final hasMore = _olderHasMore ?? (data['has_more'] as bool? ?? false);
            // Jours sans coupon pour un profil ou plus, rangés avec les coupons (rapport du
            // 09/11/2026 : un jour manquant passait pour un oubli).
            final gaps = {
              for (final d in [...((data['days'] as List?) ?? const []).cast<Json>(), ..._olderDays])
                d['day'] as String: d,
            };
            final firstDay = (_firstDay ?? data['first_day']) as String?;
            final entries =
                <(String, Json?, Json?)>[
                  for (final c in coupons) (c['day'] as String, c, null),
                  for (final g in gaps.values) (g['day'] as String, null, g),
                ]..sort((a, b) {
                  final byDay = b.$1.compareTo(a.$1);
                  if (byDay != 0) return byDay;
                  return (a.$3 == null ? 0 : 1) - (b.$3 == null ? 0 : 1);
                });
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
                  ProfileRecordCard('Bilan depuis le lancement', stats),
                  const SizedBox(height: 12),
                  if (coupons.isEmpty)
                    const EmptyState('Aucun coupon du jour pour l\'instant.', icon: Icons.history_rounded),
                  for (final (_, c, gap) in entries)
                    if (gap != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Text(
                          gap['none'] == true
                              ? '${shortDate(DateTime.parse(gap['day'] as String))} : pas de coupon ce '
                                    'jour-là (aucun match ne respectait les règles des profils).'
                              : '${shortDate(DateTime.parse(gap['day'] as String))} : pas de coupon '
                                    '${(gap['missing'] as List).join(' ni ')} ce jour-là.',
                          style: Fp.body(12.5, color: Fp.muted, height: 1.4),
                        ),
                      )
                    else if (c != null)
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
                            if (c['locked'] == true)
                              Padding(
                                padding: const EdgeInsets.only(bottom: 10),
                                child: Text(
                                  '${c['selection_count']} sélections : visibles avec Premium jusqu\'à la fin '
                                  'des matchs, puis par tous.',
                                  style: Fp.body(12.5, color: Fp.text2),
                                ),
                              )
                            else
                              for (final s in (c['selections'] as List).cast<Json>())
                                Padding(padding: const EdgeInsets.only(bottom: 10), child: _SelectionRow(s)),
                            Text(
                              '${c['selection_count'] == 1 ? 'Un seul pari ce jour-là · ' : ''}'
                              'Cote ${odds(c['total_odds'])} · probabilité annoncée '
                              '${percent((c['probability'] as num).toDouble(), decimals: 1)}',
                              style: Fp.body(12, color: Fp.text2),
                            ),
                          ],
                        ),
                      ),
                  if (!hasMore && firstDay != null && coupons.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Text(
                        'Premiers coupons : ${longDate(DateTime.parse(firstDay)).toLowerCase()}.',
                        textAlign: TextAlign.center,
                        style: Fp.body(12.5, color: Fp.muted),
                      ),
                    ),
                  if (hasMore)
                    Center(
                      child: _loading
                          ? const Padding(padding: EdgeInsets.all(12), child: CircularProgressIndicator())
                          : TextButton(
                              onPressed: () => _loadMore(api, coupons.length),
                              child: const Text('Voir les coupons plus anciens'),
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
/// « 1 sélection ajoutée », « 7 sélections ajoutées ».
String _selections(int n) => '$n sélection${n > 1 ? 's' : ''} ajoutée${n > 1 ? 's' : ''}';

Future<void> addSelectionsToCoupon(
  AppState state,
  List<Json> selections, {
  void Function(int done, int total)? onProgress,
}) async {
  // Match et cotes du moment de chaque sélection, tous demandés en même temps : l'un après
  // l'autre, 7 sélections prenaient 15 secondes sans aucun signe (essai réel du 06/11/2026).
  var done = 0;
  final total = selections.length;
  onProgress?.call(0, total);
  Future<(MatchInfo, Offer?)> load(Json s) async {
    final id = s['match_id'] as int;
    final key = '${s['market']}|${s['line'] ?? ''}|${s['selection']}';
    final got = await Future.wait([state.api.get('/matches/$id'), state.api.get('/matches/$id/offer')]);
    onProgress?.call(++done, total);
    final offer = [for (final o in got[1] as List) Offer(o as Json)].where((o) => o.key == key).firstOrNull;
    return (MatchInfo(got[0] as Json), offer);
  }

  var added = 0, missing = 0;
  try {
    // Ajoutées dans l'ordre du coupon proposé, une fois tout reçu.
    for (final (match, offer) in await Future.wait(selections.map(load))) {
      if (offer == null) {
        missing++;
      } else if (!state.inCoupon(match.id, offer.key)) {
        state.toggleCoupon(match, offer);
        added++;
      }
    }
    // « Voir mon coupon » dans le message (rapport du 07/11/2026 : il fallait trouver
    // l'onglet soi-même).
    showMessage(
      missing > 0
          ? '${_selections(added)} ; $missing sans cote disponible à présent.'
          : '${_selections(added)} au coupon.',
      action: SnackBarAction(
        label: 'Voir mon coupon',
        onPressed: () {
          navigatorKey.currentState?.popUntil((r) => r.isFirst);
          state.openTab(1);
        },
      ),
    );
  } on ApiException catch (e) {
    showMessage(e.message, error: true);
  }
}

/// Version gratuite (maquette validée le 07/11/2026, valeurs reprises une à une) : le dernier
/// coupon du jour réglé, gagné ou perdu, jamais choisi (les coupons réglés sont publics), ses
/// sélections au-delà de la 2e floutées, puis le bouton d'abonnement.
class _LockedPreview extends StatelessWidget {
  const _LockedPreview();

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    final canPop = Navigator.of(context).canPop();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            // Retour discret (absent de la maquette, mais nécessaire sur la version web).
            if (canPop) ...[
              BackChevron(onTap: () => Navigator.of(context).maybePop()),
              const SizedBox(width: 4),
            ],
            const Expanded(child: MTitle('Coupon', 'intelligent')),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          'Tu choisis ton profil et la cote visée ; le moteur compose le coupon avec ses raisons.',
          style: Fp.body(13.5, color: M.muted, height: 1.45),
        ),
        Loader<Json>(
          load: () async => await api.get('/smart-coupons/history') as Json,
          builder: (context, h, _) {
            final settled = (h['coupons'] as List)
                .cast<Json>()
                .where((c) => c['status'] != 'pending')
                .toList();
            // Revue du 07/11/2026 : toujours le dernier coupon (souvent le même profil, parfois
            // perdu) ; d'abord le bilan honnête de la semaine, puis un exemple qui change de
            // profil chaque jour.
            final since = DateTime.now().subtract(const Duration(days: 7));
            final week = [
              for (final c in settled)
                if (c['status'] != 'void' && DateTime.parse('${c['day']}').isAfter(since)) c,
            ];
            final won = week.where((c) => c['status'] == 'won').length;
            final expected = week.fold<double>(0, (t, c) => t + (c['probability'] as num).toDouble());
            const profiles = ['sur', 'equilibre', 'audacieux'];
            final wanted = profiles[DateTime.now().difference(DateTime(2026)).inDays % profiles.length];
            final c = settled.where((c) => c['profile'] == wanted).firstOrNull ?? settled.firstOrNull;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (week.isNotEmpty)
                  MCard(
                    child: Text(
                      '7 derniers jours : ${week.length > 1 ? '$won coupons gagnés' : '$won coupon gagné'} '
                      'sur ${week.length} (le moteur en annonçait ${expected.toStringAsFixed(1).replaceAll('.', ',')}).',
                      style: Fp.body(13.5, weight: FontWeight.w700, height: 1.4),
                    ),
                  ),
                if (c != null) _Example(c),
              ],
            );
          },
        ),
        PremiumCard(
          text:
              'Le coupon du jour selon ton profil, la cote que tu vises, et pourquoi chaque match a été '
              'choisi.',
          secondary: MButton(
            'Voir le bilan de tous les coupons',
            secondary: true,
            onPressed: () =>
                Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SmartHistoryScreen())),
          ),
        ),
      ],
    );
  }
}

class _Example extends StatelessWidget {
  const _Example(this.c);
  final Json c;

  @override
  Widget build(BuildContext context) {
    final sels = (c['selections'] as List).cast<Json>();
    final total = double.parse('${c['total_odds']}');
    final won = c['status'] == 'won';
    final day = DateTime.tryParse('${c['day']}');
    final now = DateTime.now();
    final yesterday = DateTime(now.year, now.month, now.day - 1);
    final when = day == null
        ? 'dernier coupon réglé'
        : DateUtils.isSameDay(day, yesterday)
        ? 'coupon d\'hier'
        : 'coupon du ${shortDate(day)}';
    return MCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('Exemple : $when · ${c['profile_label']}', style: Fp.body(12.5, color: M.small)),
              ),
              won ? const MPill.win('Gagné') : const MPill.loss('Perdu'),
            ],
          ),
          const SizedBox(height: 6),
          Text.rich(
            TextSpan(
              children: [
                TextSpan(text: 'Cote ${odds(total)}'),
                if (won) ...[
                  const TextSpan(text: ' · '),
                  TextSpan(
                    text: '+${thousands(((total - 1) * 1000).round())} F',
                    style: const TextStyle(color: M.green),
                  ),
                  TextSpan(
                    text: ' pour 1 000 F',
                    style: Fp.body(12.5, color: M.small),
                  ),
                ],
              ],
            ),
            style: Fp.title(20),
          ),
          for (final (i, s) in sels.indexed)
            Container(
              padding: const EdgeInsets.symmetric(vertical: 9),
              decoration: BoxDecoration(
                border: i < sels.length - 1 ? const Border(bottom: BorderSide(color: M.line10)) : null,
              ),
              child: _blurIf(
                i >= 2,
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('${s['home']} – ${s['away']}', style: Fp.body(13.5)),
                          Text(
                            selectionLabel(
                              '${s['market']}',
                              '${s['line'] ?? ''}',
                              '${s['selection']}',
                              home: '${s['home']}',
                              away: '${s['away']}',
                            ),
                            style: Fp.body(12, color: const Color(0xA8F4F2F8)),
                          ),
                        ],
                      ),
                    ),
                    Text(odds(double.parse('${s['odds']}')), style: Fp.body(13.5, weight: FontWeight.w700)),
                    const SizedBox(width: 4),
                    switch (s['result']) {
                      'win' || 'half_win' => const Icon(Icons.check_rounded, size: 15, color: M.green),
                      'loss' || 'half_loss' => const Icon(Icons.close_rounded, size: 15, color: M.pink),
                      _ => const SizedBox(width: 15),
                    },
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  static Widget _blurIf(bool blur, Widget child) => blur
      ? ExcludeSemantics(
          child: Opacity(
            opacity: 0.75,
            child: ImageFiltered(imageFilter: ImageFilter.blur(sigmaX: 3.5, sigmaY: 3.5), child: child),
          ),
        )
      : child;
}
