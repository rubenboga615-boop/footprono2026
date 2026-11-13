import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'live_reliability_screen.dart';

/// Page publique « Fiabilité du moteur » (GET /reliability), sur un seul écran
/// (maquette du 06/11/2026) : le verdict d'abord, un marché à la fois, le détail sur demande.
class ReliabilityScreen extends StatefulWidget {
  const ReliabilityScreen({super.key});

  @override
  State<ReliabilityScreen> createState() => _ReliabilityScreenState();
}

/// Marchés suivis depuis le lancement (prédictions publiées) : clé de l'API.
const _liveKeys = {'1X2': '1X2', 'OU': 'OU|2.5', 'BTTS': 'BTTS'};
const _liveNames = {
  '1X2': 'Résultat du match',
  'OU|2.5': 'Plus/moins de 2,5 buts',
  'BTTS': 'Les deux marquent',
};

class _ReliabilityScreenState extends State<ReliabilityScreen> {
  // « Tous » d'abord (essai réel du 08/11/2026 : seule la vue « 5 grands » était proposée,
  // alors que les coupons prennent surtout des matchs des autres championnats).
  static const _comps = [
    '',
    'BIG5',
    'EPL',
    'LA_LIGA',
    'SERIE_A',
    'BUNDESLIGA',
    'LIGUE_1',
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

  /// Famille de l'audit (5 grands championnats) ou marché suivi (autres championnats).
  String market = '1X2';
  String competition = '';
  // Maquette C5 du 07/11/2026 : la page s'ouvre sur les résultats réels.
  bool live = true;

  static String _compLabel(String c) => switch (c) {
    '' => 'Tous les championnats',
    'BIG5' => '5 grands championnats',
    _ => competitionName(c),
  };

  /// Simulation de tous les marchés (audit) : faite sur les 5 grands championnats.
  static bool _audited(String c) => c.isEmpty || c == 'BIG5';

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          key: ValueKey(competition),
          load: () async => await api.get('/reliability', {
            if (competition.isNotEmpty) 'competition': competition,
            'recent': 20,
          }) as Json,
          builder: (context, r, reload) {
            var view = _View.of(r, market, live, _compLabel(competition));
            // Pas encore de résultats réels pour ce choix : la simulation seule.
            if (live && !view.canLive) view = _View.of(r, market, false, _compLabel(competition));
            final showLive = live && view.canLive;
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: pagePadding(context, 16, 32, maxWidth: 640),
                children: [
                  const BackHeader('Fiabilité', 'du moteur'),
                  const SizedBox(height: 12),
                  if (view.canLive) ...[
                    SegmentTabs(
                      labels: ['Depuis le lancement (${thousands(view.liveMatches)})', 'Simulation'],
                      selected: showLive ? 0 : 1,
                      onSelected: (i) => setState(() => live = i == 0),
                    ),
                    const SizedBox(height: 12),
                  ],
                  _Verdict(view.verdict, ok: view.verdictOk),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        flex: 5,
                        child: _Drop(
                          'Marché',
                          view.marketLabel,
                          accent: true,
                          onTap: () => _pickMarket(context, view),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        flex: 4,
                        child: _Drop('Championnat', switch (competition) {
                          '' => 'Tous',
                          'BIG5' => '5 grands',
                          _ => _compLabel(competition),
                        }, onTap: () => _pickCompetition(context)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  GlassCard.section(
                    padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          children: [
                            _legend(_announced, 'annoncé'),
                            const SizedBox(width: 12),
                            _legend(Fp.accent2, 'arrivé'),
                            const Spacer(),
                            if (view.status != null)
                              Flexible(
                                child: Text(
                                  view.status!,
                                  textAlign: TextAlign.right,
                                  style: Fp.body(
                                    12,
                                    weight: FontWeight.w700,
                                    color: view.statusOk ? Fp.win : Fp.warning,
                                  ),
                                ),
                              ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        if (view.calibration.isEmpty)
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 20),
                            child: Text(
                              view.emptyText,
                              textAlign: TextAlign.center,
                              style: Fp.body(13, color: Fp.text2, height: 1.4),
                            ),
                          )
                        else
                          _CalibrationChart(view.calibration, view.minBin),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(view.source, style: Fp.body(12, color: Fp.muted, height: 1.4)),
                  const SizedBox(height: 10),
                  IntrinsicHeight(
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Expanded(
                          child: _Tile(
                            view.vsAverage,
                            view.vsAverageText,
                            good: true,
                            onHelp: () => _help(context, 'La moyenne du championnat', view.averageHelp),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: _Tile(
                            view.vsBookmakers,
                            view.vsBookmakersText,
                            good: view.beatsBookmakers,
                            onHelp: () => _help(context, 'Les bookmakers', view.bookmakersHelp),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    alignment: WrapAlignment.spaceBetween,
                    spacing: 16,
                    children: [
                      _Link('Comment lire ?', () => _help(context, 'Comment lire', view.howTo)),
                      _Link(
                        'Depuis le lancement : ${thousands(view.settled)} réglé${view.settled > 1 ? 's' : ''} ›',
                        () => _sinceLaunch(context, r),
                      ),
                    ],
                  ),
                  const LiveReliabilityLink(),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _legend(Color color, String label) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Container(
        width: 11,
        height: 11,
        decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3)),
      ),
      const SizedBox(width: 5),
      Text(label, style: Fp.body(12, color: Fp.text2)),
    ],
  );

  Future<T?> _sheet<T>(BuildContext context, Widget Function(BuildContext) child) => showModalBottomSheet<T>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Fp.background,
    builder: (context) => SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.8),
        child: child(context),
      ),
    ),
  );

  Future<void> _pickMarket(BuildContext context, _View view) async {
    final choice = await _sheet<String>(
      context,
      (context) => ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 24),
        children: [
          Text('Choisis un marché', style: Fp.title(17)),
          const SizedBox(height: 4),
          Text(view.pickerSubtitle, style: Fp.body(12.5, color: Fp.text3, height: 1.4)),
          for (final g in view.choices) ...[
            if (g.group != null) ...[
              const SizedBox(height: 14),
              Text(
                g.group!.toUpperCase(),
                style: Fp.body(
                  12,
                  weight: FontWeight.w800,
                  color: Fp.accentLight,
                ).copyWith(letterSpacing: 0.6),
              ),
            ],
            for (final c in g.items)
              InkWell(
                onTap: () => Navigator.pop(context, c.id),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 11),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          c.label,
                          style: Fp.body(
                            14,
                            weight: c.id == view.marketId ? FontWeight.w800 : FontWeight.w500,
                            color: c.id == view.marketId ? Fp.text : Fp.textSoft,
                          ),
                        ),
                      ),
                      if (c.status != null)
                        Text(
                          c.status!,
                          style: Fp.body(12, weight: FontWeight.w700, color: c.ok ? Fp.win : Fp.warning),
                        ),
                    ],
                  ),
                ),
              ),
          ],
        ],
      ),
    );
    if (choice != null) setState(() => market = choice);
  }

  Future<void> _pickCompetition(BuildContext context) async {
    final choice = await _sheet<String>(
      context,
      (context) => ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 24),
        children: [
          Text('Choisis un championnat', style: Fp.title(17)),
          const SizedBox(height: 6),
          for (final c in _comps)
            InkWell(
              onTap: () => Navigator.pop(context, c),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 11),
                child: Text(
                  _compLabel(c),
                  style: Fp.body(
                    14,
                    weight: c == competition ? FontWeight.w800 : FontWeight.w500,
                    color: c == competition ? Fp.text : Fp.textSoft,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
    if (choice == null || choice == competition) return;
    setState(() {
      // Hors des 5 grands : seulement les marchés suivis (pas d'audit par championnat).
      if (!_audited(choice) && !_liveKeys.values.contains(market)) market = _liveKeys[market] ?? '1X2';
      if (_audited(choice)) {
        market = _liveKeys.entries.where((e) => e.value == market).firstOrNull?.key ?? market;
      }
      competition = choice;
      live = false;
    });
  }

  Future<void> _help(BuildContext context, String title, String text) => _sheet<void>(
    context,
    (context) => SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(title, style: Fp.title(17)),
          const SizedBox(height: 10),
          Text(text, style: Fp.body(14, color: Fp.textSoft, height: 1.5)),
        ],
      ),
    ),
  );

  Future<void> _sinceLaunch(BuildContext context, Json r) {
    final markets = (r['markets'] as List).cast<Json>();
    final recent = (r['recent'] as List).cast<Json>();
    final n = r['matches'] as int? ?? 0;
    return _sheet<void>(
      context,
      (context) => ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 24),
        children: [
          Text('Depuis le lancement', style: Fp.title(17)),
          const SizedBox(height: 6),
          Text(
            'Pronostics enregistrés avant le coup d\'envoi, jamais modifiés, tous comptés '
            '(${competition.isEmpty ? 'tous les championnats' : _compLabel(competition)}).',
            style: Fp.body(13, color: Fp.text2, height: 1.4),
          ),
          const SizedBox(height: 10),
          KeyValue('Matchs réglés', thousands(n)),
          if (r['warning'] != null) ...[
            const SizedBox(height: 6),
            Text('${r['warning']}', style: Fp.body(12.5, color: Fp.warning, height: 1.4)),
          ],
          for (final m in markets.where((m) => (m['matches'] as int? ?? 0) > 0)) ...[
            const SizedBox(height: 12),
            Text(_liveNames[m['market']] ?? '${m['label']}', style: Fp.body(14, weight: FontWeight.w800)),
            KeyValue('Matchs', thousands(m['matches'] as int)),
            KeyValue('Écart moyen annoncé / arrivé', '${decimal(_gap(m), max: 1)} points'),
            KeyValue(
              'Issue la plus probable trouvée',
              '${percent((m['most_likely_hit_rate'] as num).toDouble())} '
                  '(annoncée ${percent((m['most_likely_announced'] as num).toDouble())})',
            ),
          ],
          if (recent.isNotEmpty) ...[
            const SizedBox(height: 14),
            Text('Derniers matchs', style: Fp.body(14, weight: FontWeight.w800)),
            for (final (i, x) in recent.indexed) ...[if (i > 0) const Divider(), _RecentRow(x)],
          ],
        ],
      ),
    );
  }

  /// Écart moyen (en points) entre annoncé et arrivé, pondéré par tranche.
  static double _gap(Json m) {
    final bins = ((m['calibration'] as List?) ?? const []).cast<Json>();
    var total = 0;
    var sum = 0.0;
    for (final b in bins) {
      final c = b['count'] as int;
      total += c;
      sum += c * ((b['announced'] as num) - (b['observed'] as num)).abs() * 100;
    }
    return total == 0 ? 0 : sum / total;
  }
}

class _Choice {
  const _Choice(this.id, this.label, {this.status, this.ok = true});
  final String id;
  final String label;
  final String? status;
  final bool ok;
}

class _Group {
  const _Group(this.group, this.items);
  final String? group;
  final List<_Choice> items;
}

/// Ce que l'écran affiche pour un championnat et un marché : tout est calculé ici,
/// l'affichage ne fait que le montrer.
class _View {
  _View({
    required this.verdict,
    required this.verdictOk,
    required this.marketId,
    required this.marketLabel,
    required this.choices,
    required this.pickerSubtitle,
    required this.calibration,
    required this.minBin,
    required this.source,
    required this.emptyText,
    required this.status,
    required this.statusOk,
    required this.canLive,
    required this.liveMatches,
    required this.vsAverage,
    required this.vsAverageText,
    required this.vsBookmakers,
    required this.vsBookmakersText,
    required this.beatsBookmakers,
    required this.averageHelp,
    required this.bookmakersHelp,
    required this.howTo,
    required this.settled,
  });

  final String verdict;
  final bool verdictOk;
  final String marketId;
  final String marketLabel;
  final List<_Group> choices;
  final String pickerSubtitle;
  final List<Json> calibration;
  final int minBin;
  final String source;
  final String emptyText;
  final String? status;
  final bool statusOk;
  final bool canLive;
  final int liveMatches;
  final String vsAverage;
  final String vsAverageText;
  final String vsBookmakers;
  final String vsBookmakersText;
  final bool beatsBookmakers;
  final String averageHelp;
  final String bookmakersHelp;
  final String howTo;
  final int settled;

  /// Règle de justesse (la même partout) : dans chaque tranche d'au moins [minBin] cas, écart
  /// entre annoncé et arrivé de 3 points au plus, ou dans la marge du hasard (2 erreurs types).
  /// Résultats réels : pas de verdict avant [minMatches] matchs (essai du 08/11/2026 : « ✓ »
  /// affiché sur 110 matchs, juste au-dessus de « échantillon trop petit pour conclure »).
  static const minMatches = 200;

  static (String, bool) _ruleStatus(List<Json> bins, int minBin, [int? matches]) {
    if (matches != null && matches < minMatches) {
      return ('pas encore assez de matchs pour conclure ($matches sur $minMatches)', true);
    }
    Json? worst;
    var worstGap = 0.0;
    var judged = 0;
    for (final b in bins) {
      final n = b['count'] as int? ?? 0;
      if (n < minBin) continue;
      judged++;
      final a = (b['announced'] as num).toDouble(), o = (b['observed'] as num).toDouble();
      final margin = math.max(0.03, 2 * math.sqrt(a * (1 - a) / n));
      final gap = (o - a).abs();
      if (gap > margin && gap > worstGap) {
        worst = b;
        worstGap = gap;
      }
    }
    if (judged == 0) return ('pas encore assez de cas pour juger', true);
    if (worst == null) return ('✓ règle respectée', true);
    return (
      'pas encore juste : annoncé ${((worst['announced'] as num) * 100).round()} % → '
          'arrivé ${((worst['observed'] as num) * 100).round()} %',
      false,
    );
  }

  /// Erreur relative du moteur face à une référence (log loss) : « 8 % » et le sens.
  static (String, bool) _relative(num model, num reference) {
    final d = (reference - model) / reference;
    if (d.abs() < 0.0005) return (same, false);
    final txt = '${decimal(d.abs() * 100, max: 1)}$nbsp%';
    return (txt, d > 0);
  }

  /// Égalité (« 0,0 % d'erreur en moins » se lisait mal) : « autant d'erreur que … ».
  static const same = '=';
  static String _versus(String txt, bool better, String reference) => txt == same
      ? 'autant d\'erreur que $reference'
      : 'd\'erreur ${better ? 'en moins' : 'en plus'} que $reference';

  static const _howTo =
      'Chaque ligne regroupe les pronostics d\'une même tranche (par exemple ceux annoncés entre 70 et '
      '80 %). Barre grise : ce que le moteur annonçait en moyenne. Barre violette : ce qui est vraiment '
      'arrivé. Si les deux ont la même longueur, le moteur dit juste : quand il annonce 70 %, ça arrive '
      'environ 7 fois sur 10.\n\nSimulation : chaque match passé est prédit avec les seuls matchs joués '
      'avant lui, comme en vrai. Depuis le lancement : les pronostics publiés avant les matchs, tous '
      'comptés, jamais modifiés.\n\nTranches grisées : moins de 50 cas, l\'écart y vient surtout du hasard.';

  factory _View.of(Json r, String market, bool wantLive, String scope) {
    final audit = r['markets_audit'] as Json?;
    final bt = r['backtest'] as Json? ?? const {};
    final btLoss = (bt['log_loss'] as Json?) ?? const {};
    final liveMarkets = {for (final m in (r['markets'] as List).cast<Json>()) m['market'] as String: m};
    final settled = r['matches'] as int? ?? 0;
    final minBin = r['min_bin'] as int? ?? 50;
    final bookmakersHelp =
        'Les dernières cotes des bookmakers juste avant le coup d\'envoi, marge retirée. Elles tiennent '
        'compte de tout ce qui est connu jusqu\'au match (compositions, blessures, argent misé) : elles '
        'restent en général un peu plus précises que le moteur. FootProba ne prétend pas les battre.'
        '${bt['note'] != null ? '\n\n${bt['note']}' : ''}';

    if (audit != null) {
      final families = (audit['families'] as List).cast<Json>();
      final f = families.firstWhere((x) => x['id'] == market, orElse: () => families.first);
      final id = f['id'] as String;
      final published = families.where((x) => x['withdrawn'] == null).toList();
      final good = published.where((x) => x['passes_rule'] == true).toList();
      final worst = good.fold<num>(
        0,
        (m, x) => (x['max_gap_points'] as num) > m ? x['max_gap_points'] as num : m,
      );
      final removed = families.where((x) => x['withdrawn'] != null).map((x) => '« ${x['label']} »').toList();
      final allGood = good.length == published.length;
      final verdict =
          'Simulation : ${allGood ? 'les ${published.length} marchés publiés respectent' : '${good.length} marchés sur ${published.length} respectent'} '
          'la règle de justesse sur ${thousands(audit['matches'] as int)} matchs passés des 5 grands championnats : écart de 3 points '
          'au plus entre annoncé et arrivé, ou dans la marge du hasard (au plus ${worst.ceil()} points).'
          '${removed.isEmpty ? '' : ' Retiré : ${removed.join(', ')}.'}';
      final liveKey = _liveKeys[id];
      final liveM = liveKey == null ? null : liveMarkets[liveKey];
      final liveN = liveM?['matches'] as int? ?? 0;
      final showLive = wantLive && liveN > 0;
      final gapPts = (f['max_gap_points'] as num).ceil().clamp(1, 99);
      final status = f['withdrawn'] != null
          ? 'retiré'
          : f['passes_rule'] == true
          ? '✓ règle respectée · écart max $gapPts pt${gapPts > 1 ? 's' : ''}'
          : 'à corriger';
      final liveCalib = liveM == null
          ? const <Json>[]
          : ((liveM['calibration'] as List?) ?? const []).cast<Json>();
      final (liveStatus, liveOk) = _ruleStatus(liveCalib, minBin, liveN);
      // Pronostics publiés : chiffres clés tirés des résultats réels, pas de la simulation.
      final liveVersus = liveKey == null
          ? null
          : (r['versus_closing_odds'] as List).cast<Json>().where((v) => v['market'] == liveKey).firstOrNull;
      final (liveAvg, liveAvgGood) = liveM != null && liveM['log_loss'] != null
          ? _relative(liveM['log_loss'] as num, liveM['naive_log_loss'] as num)
          : ('—', true);
      final (liveBm, liveBeats) = liveVersus != null
          ? _relative(liveVersus['model_log_loss'] as num, liveVersus['closing_odds_log_loss'] as num)
          : ('—', false);
      final closing = id == '1X2' ? btLoss['1X2'] : (id == 'OU' ? btLoss['OU|2.5'] : null);
      final hasClosing = showLive ? liveVersus != null : closing is Json && closing['closing_odds'] != null;
      final (bmTxt, beats) = showLive
          ? (liveBm, liveBeats)
          : hasClosing
          ? _relative((closing as Json)['model'] as num, closing['closing_odds'] as num)
          : ('—', false);
      final groups = <String, List<_Choice>>{};
      for (final x in families) {
        final ok = x['withdrawn'] == null && x['passes_rule'] == true;
        groups
            .putIfAbsent(x['group'] as String, () => [])
            .add(
              _Choice(
                x['id'] as String,
                x['label'] as String,
                status: x['withdrawn'] != null
                    ? 'retiré'
                    : ok
                    ? '✓ ${(x['max_gap_points'] as num).ceil().clamp(1, 99)} pt${(x['max_gap_points'] as num).ceil() > 1 ? 's' : ''}'
                    : 'à corriger',
                ok: ok,
              ),
            );
      }
      return _View(
        // Rapport du 10/11/2026 : le verdict réel d'abord, la simulation ensuite.
        verdict: liveN > 0
            ? 'Résultats réels depuis le lancement ($scope, ${thousands(liveN)} matchs) : '
                  '${f['label']} — $liveStatus.\n\n$verdict'
            : verdict,
        verdictOk: allGood && liveOk && liveN >= minMatches,
        marketId: id,
        marketLabel: f['label'] as String,
        choices: [for (final e in groups.entries) _Group(e.key, e.value)],
        pickerSubtitle:
            '${published.length} marchés publiés sur ${thousands(audit['matches'] as int)} matchs passés. '
            '✓ = règle de justesse respectée (3 points au plus, ou dans la marge du hasard) ; '
            'à côté, le plus grand écart entre annoncé et arrivé.',
        calibration: showLive
            ? ((liveM!['calibration'] as List?) ?? const []).cast<Json>()
            : ((f['calibration'] as List?) ?? const []).cast<Json>(),
        minBin: minBin,
        source: showLive
            ? (liveM!['warning'] as String? ??
                  'Pronostics publiés avant les matchs, $scope (${thousands(liveN)} matchs).')
            : 'Simulation : ${thousands(audit['matches'] as int)} matchs passés des ${audit['competitions']} '
                  '(saisons ${audit['seasons']}).${f['withdrawn'] != null ? ' ${f['withdrawn']}' : ''}',
        emptyText: 'Pas encore de pronostic réglé sur ce marché.',
        status: showLive ? liveStatus : status,
        statusOk: showLive ? liveOk : status.startsWith('✓'),
        canLive: liveN > 0,
        liveMatches: liveN,
        vsAverage: showLive ? liveAvg : '${decimal(((f['skill'] as num) * 100).abs(), max: 1)} %',
        vsAverageText: showLive
            ? _versus(liveAvg, liveAvgGood, 'la fréquence observée (connue après coup)')
            : _versus(
                (f['skill'] as num).abs() < 0.0005 ? same : '',
                (f['skill'] as num) >= 0,
                'la moyenne du championnat',
              ),
        vsBookmakers: bmTxt,
        vsBookmakersText: hasClosing
            ? '${_versus(bmTxt, beats, 'les bookmakers avant le match')}${id == 'OU' ? ' (plus/moins 2,5)' : ''}'
            : 'pas de cotes passées pour comparer aux bookmakers',
        beatsBookmakers: beats,
        averageHelp:
            '${audit['reference']}\n\nL\'erreur se mesure match par match (log loss) : plus elle est petite, '
            'plus les pourcentages annoncés sont proches de ce qui arrive.\n\n${audit['rule']}',
        bookmakersHelp: bookmakersHelp,
        howTo: _howTo,
        settled: settled,
      );
    }

    // Autres championnats : les marchés suivis, leur simulation et leurs pronostics publiés.
    final key = _liveKeys.values.contains(market) ? market : '1X2';
    final liveM = liveMarkets[key];
    final liveN = liveM?['matches'] as int? ?? 0;
    final showLive = liveN > 0 && (wantLive || !btLoss.containsKey(key));
    final loss = btLoss[key] as Json?;
    final btCalib = key == '1X2'
        ? ((bt['calibration_1x2'] as List?) ?? const []).cast<Json>()
        : const <Json>[];
    final (avgTxt, avgGood) = loss != null && loss['naive'] != null
        ? _relative(loss['model'] as num, loss['naive'] as num)
        : ('—', true);
    final hasClosing = loss != null && loss['closing_odds'] != null;
    final (bmTxt, beats) = hasClosing
        ? _relative(loss['model'] as num, loss['closing_odds'] as num)
        : ('—', false);
    final warning = liveM?['warning'] as String?;
    final (liveStatus, liveOk) = _ruleStatus(
      liveM == null ? const <Json>[] : ((liveM['calibration'] as List?) ?? const []).cast<Json>(),
      minBin,
      liveN,
    );
    final simulation = bt['matches'] != null
        ? 'Simulation sur ${thousands(bt['matches'] as int)} matchs passés (saisons ${bt['seasons']}).'
        : 'Pas encore de simulation pour ce championnat.';
    return _View(
      verdict: liveN > 0
          ? 'Résultats réels depuis le lancement (${thousands(liveN)} matchs) : '
                '${_liveNames[key]} — $liveStatus.\n\n$simulation'
          : simulation,
      verdictOk: liveOk && liveN >= minMatches,
      marketId: key,
      marketLabel: _liveNames[key]!,
      choices: [
        _Group(null, [for (final e in _liveNames.entries) _Choice(e.key, e.value)]),
      ],
      pickerSubtitle: 'Marchés suivis pour ce championnat.',
      calibration: showLive ? ((liveM!['calibration'] as List?) ?? const []).cast<Json>() : btCalib,
      minBin: minBin,
      source: showLive
          ? (liveM!['warning'] as String? ?? 'Pronostics publiés avant les matchs.')
          : bt['matches'] != null
          ? 'Simulation : ${thousands(bt['matches'] as int)} matchs passés (saisons ${bt['seasons']}).'
          : '',
      emptyText: warning ?? 'Pas de détail par tranche pour ce marché dans la simulation.',
      status: showLive ? liveStatus : null,
      statusOk: showLive ? liveOk : true,
      canLive: liveN > 0 && btCalib.isNotEmpty,
      liveMatches: liveN,
      vsAverage: avgTxt,
      vsAverageText: loss == null
          ? 'pas de simulation pour ce marché'
          : _versus(avgTxt, avgGood, 'la moyenne du championnat'),
      vsBookmakers: bmTxt,
      vsBookmakersText: hasClosing
          ? _versus(bmTxt, beats, 'les bookmakers avant le match')
          : 'pas de cotes passées pour comparer aux bookmakers',
      beatsBookmakers: beats,
      averageHelp:
          'Fréquence de chaque issue dans le championnat, sans regarder les équipes.\n\nL\'erreur se '
          'mesure match par match (log loss) : plus elle est petite, plus les pourcentages annoncés sont '
          'proches de ce qui arrive.',
      bookmakersHelp: bookmakersHelp,
      howTo: _howTo,
      settled: settled,
    );
  }
}

class _Verdict extends StatelessWidget {
  const _Verdict(this.text, {required this.ok});
  final String text;
  final bool ok;

  @override
  Widget build(BuildContext context) {
    // Maquette C5 : encadré ambre (pas encore juste) ou vert (règle respectée).
    final (bg, border, color) = ok
        ? (const Color(0xFF12301F), const Color(0xFF1F5B3A), const Color(0xFFC9F5D9))
        : (const Color(0xFF1F1709), const Color(0xFF6B4F1D), Fp.warning);
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 11, 12, 11),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: border),
      ),
      child: Text(text, style: Fp.body(13.5, color: color, height: 1.45)),
    );
  }
}

class _Drop extends StatelessWidget {
  const _Drop(this.label, this.value, {required this.onTap, this.accent = false});
  final String label;
  final String value;
  final VoidCallback onTap;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    // Maquette C5 : carte, petit libellé gris, choix en gras.
    return Material(
      color: Fp.card,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label, style: Fp.body(12, color: Fp.muted)),
                    Text(
                      value,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Fp.body(15, weight: FontWeight.w700),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.expand_more_rounded, size: 18, color: Fp.muted),
            ],
          ),
        ),
      ),
    );
  }
}

class _Tile extends StatelessWidget {
  const _Tile(this.value, this.text, {required this.good, required this.onHelp});
  final String value;
  final String text;
  final bool good;
  final VoidCallback onHelp;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Fp.fill,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: Fp.line10),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onHelp,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 10, 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      value,
                      style: Fp.title(
                        19,
                        weight: FontWeight.w700,
                      ).copyWith(color: value == '—' ? Fp.text2 : (good ? Fp.win : Fp.lossText)),
                    ),
                  ),
                  const Icon(Icons.help_outline_rounded, size: 17, color: Fp.text3),
                ],
              ),
              const SizedBox(height: 2),
              Text(text, style: Fp.body(12, color: Fp.text2, height: 1.35)),
            ],
          ),
        ),
      ),
    );
  }
}

class _Link extends StatelessWidget {
  const _Link(this.text, this.onTap);
  final String text;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Text(
          text,
          style: Fp.body(13.5, weight: FontWeight.w700, color: Fp.accentLight),
        ),
      ),
    );
  }
}

/// Une ligne par tranche : annoncé (gris) au-dessus d'arrivé (violet), « 74 → 76 % ».
/// Tranche grisée sous [minBin] cas.
class _CalibrationChart extends StatelessWidget {
  const _CalibrationChart(this.bins, this.minBin);
  final List<Json> bins;
  final int minBin;

  static String _label(Object? range) {
    final parts = '$range'.split('-').map((p) => double.tryParse(p.replaceAll(',', '.')) ?? 0).toList();
    if (parts.length < 2) return '$range';
    return '${(parts.first * 100).round()} à ${(parts.last * 100).round()}$nbsp%';
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (final b in bins)
          Opacity(
            opacity: (b['count'] as int? ?? 0) < minBin ? 0.4 : 1,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(
                children: [
                  SizedBox(
                    width: 74,
                    child: Text(_label(b['range']), style: Fp.body(12, color: Fp.muted)),
                  ),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _bar((b['announced'] as num).toDouble(), _announced),
                        const SizedBox(height: 3),
                        _bar((b['observed'] as num).toDouble(), Fp.accent2),
                      ],
                    ),
                  ),
                  SizedBox(
                    width: 82,
                    child: Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(
                            text: '${((b['announced'] as num) * 100).round()} → ',
                            style: Fp.body(12.5, weight: FontWeight.w700),
                          ),
                          TextSpan(
                            text: percent((b['observed'] as num).toDouble()),
                            style: Fp.body(12.5, weight: FontWeight.w700),
                          ),
                        ],
                      ),
                      textAlign: TextAlign.right,
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  // Maquette C5 : barres fines de 5, sans fond.
  Widget _bar(double value, Color color) => ClipRRect(
    borderRadius: BorderRadius.circular(3),
    child: SizedBox(
      height: 5,
      child: Stack(
        children: [
          FractionallySizedBox(
            alignment: Alignment.centerLeft,
            heightFactor: 1,
            widthFactor: value.clamp(0.0, 1.0),
            child: ColoredBox(color: color),
          ),
        ],
      ),
    ),
  );
}

class _RecentRow extends StatelessWidget {
  const _RecentRow(this.m);
  final Json m;

  @override
  Widget build(BuildContext context) {
    final probs = (m['probabilities_1x2'] as List).map((v) => (v as num).toDouble()).toList();
    final hit = m['most_likely'] == m['result'];
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        children: [
          Icon(
            hit ? Icons.check_circle_rounded : Icons.cancel_rounded,
            color: hit ? Fp.win : Fp.loss,
            size: 20,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${m['home']} ${m['score']} ${m['away']}', style: Fp.body(14, weight: FontWeight.w700)),
                Text(
                  '1 : ${percent(probs[0])} · N : ${percent(probs[1])} · 2 : ${percent(probs[2])}',
                  style: Fp.body(12, color: Fp.text2),
                ),
              ],
            ),
          ),
          Text(numericDate(DateTime.parse(m['date'] as String)), style: Fp.body(12, color: Fp.text3)),
        ],
      ),
    );
  }
}

/// Barre « annoncé » des maquettes (#6B6490).
const _announced = Color(0xFF6B6490);
