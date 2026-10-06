import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Page publique « Fiabilité du moteur » (GET /reliability).
class ReliabilityScreen extends StatefulWidget {
  const ReliabilityScreen({super.key});

  @override
  State<ReliabilityScreen> createState() => _ReliabilityScreenState();
}

class _ReliabilityScreenState extends State<ReliabilityScreen> {
  static const _markets = ['1X2', 'OU|2.5', 'BTTS'];
  static const _marketNames = ['1 / N / 2', 'Buts', 'Les 2 marquent'];
  static const _comps = [
    '',
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
  ];
  int market = 0;
  String competition = '';
  bool backtest = false;

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          key: ValueKey(competition),
          load: () async => await api.get('/reliability', {
            'competition': competition.isEmpty ? null : competition,
            'recent': 20,
          }) as Json,
          builder: (context, r, reload) {
            final markets = (r['markets'] as List).cast<Json>();
            final m = markets.firstWhere((x) => x['market'] == _markets[market]);
            final versus = (r['versus_closing_odds'] as List).cast<Json>();
            final closing = versus.where((v) => v['market'] == _markets[market]).firstOrNull;
            final recent = (r['recent'] as List).cast<Json>();
            final bt = r['backtest'] as Json;
            final n = r['matches'] as int;
            final hasLive = (m['matches'] as int? ?? 0) > 0;
            final showBacktest = backtest || !hasLive;
            final calib = showBacktest
                ? (market == 0 ? (bt['calibration_1x2'] as List).cast<Json>() : const <Json>[])
                : (m['calibration'] as List).cast<Json>();
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: pagePadding(context, 16, 32, maxWidth: 1080),
                children: [
                  const BackHeader(
                    'Fiabilité',
                    'du moteur',
                    subtitle:
                        'Quand le moteur annonce 70\u00A0%, est-ce que ça arrive vraiment 7 fois sur 10\u00A0? '
                        'Tous les pronostics réglés, publiés sans tri.',
                  ),
                  const SizedBox(height: 16),
                  ChipRow(
                    labels: _marketNames,
                    selected: market,
                    onSelected: (i) => setState(() => market = i),
                  ),
                  const SizedBox(height: 8),
                  ChipRow(
                    labels: [
                      for (final c in _comps) c.isEmpty ? 'Tous les championnats' : competitionName(c),
                    ],
                    selected: _comps.indexOf(competition),
                    onSelected: (i) => setState(() => competition = _comps[i]),
                  ),
                  const SizedBox(height: 16),
                  ...deskColumns(context, [
                    if (r['warning'] != null) ...[_Warning('${r['warning']}'), const SizedBox(height: 14)],
                    GlassCard.section(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Wrap(
                            spacing: 18,
                            runSpacing: 6,
                            children: [
                              _legend(const Color(0x66F4F2F8), 'Annoncé'),
                              _legend(const Color(0xFF8B5CF6), 'Réalisé'),
                            ],
                          ),
                          if (hasLive) ...[
                            const SizedBox(height: 12),
                            SegmentTabs(
                              labels: const ['Prédictions publiées', 'Backtest'],
                              selected: showBacktest ? 1 : 0,
                              onSelected: (i) => setState(() => backtest = i == 1),
                            ),
                          ],
                          const SizedBox(height: 16),
                          if (calib.isEmpty)
                            Padding(
                              padding: const EdgeInsets.symmetric(vertical: 24),
                              child: Text(
                                showBacktest
                                    ? 'Calibration du backtest publiée pour le 1X2 seulement.'
                                    : 'Pas encore de prédiction publiée à comparer.',
                                textAlign: TextAlign.center,
                                style: Fp.body(13, color: Fp.text2),
                              ),
                            )
                          else
                            _CalibrationChart(calib),
                          if (showBacktest) ...[
                            const SizedBox(height: 10),
                            Text(
                              'Source : backtest (simulation sur ${thousands(bt['matches'] as int)} matchs des saisons '
                              '${bt['seasons']}), pas des prédictions publiées.',
                              style: Fp.body(12, color: Fp.warning, height: 1.4),
                            ),
                          ],
                        ],
                      ),
                    ),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        Expanded(child: KeyTile('Depuis le lancement', '${thousands(n)} réglés')),
                        const SizedBox(width: 8),
                        Expanded(
                          child: KeyTile(
                            'Backtest (saisons passées)',
                            '${thousands(bt['matches'] as int)} matchs',
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Text(
                      'Quand le moteur annonce 60\u00A0%, l\'événement doit se produire environ 6 fois sur 10 : '
                      'les deux barres de chaque tranche doivent rester de la même longueur. Page publique, '
                      'consultable sans compte.',
                      style: Fp.body(11.5, color: Fp.text2, height: 1.45),
                    ),
                    const SizedBox(height: 14),
                    GlassCard.section(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text('Depuis le lancement', style: Fp.title(17, weight: FontWeight.w600)),
                          const SizedBox(height: 8),
                          KeyValue('Matchs pronostiqués', thousands(n)),
                          if (hasLive) ...[
                            KeyValue(
                              'Écart moyen annoncé / observé',
                              '${_gap(m).toStringAsFixed(1).replaceAll('.', ',')} points',
                            ),
                            KeyValue(
                              'Issue la plus probable trouvée',
                              percent((m['most_likely_hit_rate'] as num).toDouble()),
                            ),
                            KeyValue(
                              '… annoncée en moyenne à',
                              percent((m['most_likely_announced'] as num).toDouble()),
                            ),
                            KeyValue('Log loss du modèle', decimal(m['log_loss'], max: 4)),
                            KeyValue('Référence naïve (fréquences)', decimal(m['naive_log_loss'], max: 4)),
                            KeyValue('Score de Brier', decimal(m['brier'], max: 4)),
                            KeyValue(
                              'Référence : cotes de clôture',
                              closing != null ? decimal(closing['closing_odds_log_loss'], max: 4) : '—',
                            ),
                            const SizedBox(height: 6),
                            Text(
                              'Log loss : plus bas = meilleur. La référence naïve n\'est connue qu\'après coup ; les '
                              'cotes de clôture intègrent tout ce qui est connu jusqu\'au coup d\'envoi.',
                              style: Fp.body(12, color: Fp.text3, height: 1.4),
                            ),
                          ],
                        ],
                      ),
                    ),
                    const SizedBox(height: 14),
                    _Backtest(bt),
                    if (recent.isNotEmpty) ...[
                      const SectionTitle('Derniers matchs'),
                      GlassCard.section(
                        padding: const EdgeInsets.fromLTRB(16, 4, 16, 4),
                        child: Column(
                          children: [
                            for (final (i, x) in recent.indexed) ...[
                              if (i > 0) const Divider(),
                              _RecentRow(x),
                            ],
                          ],
                        ),
                      ),
                    ],
                  ]),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  /// Écart moyen (en points) entre annoncé et observé, pondéré par tranche.
  static double _gap(Json m) {
    final bins = (m['calibration'] as List).cast<Json>();
    var total = 0;
    var sum = 0.0;
    for (final b in bins) {
      final c = b['count'] as int;
      total += c;
      sum += c * ((b['announced'] as num) - (b['observed'] as num)).abs() * 100;
    }
    return total == 0 ? 0 : sum / total;
  }

  Widget _legend(Color color, String label) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Container(
        width: 12,
        height: 12,
        decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3)),
      ),
      const SizedBox(width: 6),
      Text(label, style: Fp.body(13, color: Fp.textStrong)),
    ],
  );
}

class _Warning extends StatelessWidget {
  const _Warning(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Fp.warning.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Fp.warning.withValues(alpha: 0.25)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.info_outline_rounded, size: 18, color: Fp.warning),
          const SizedBox(width: 10),
          Expanded(
            child: Text(text, style: Fp.body(13, color: Fp.warning, height: 1.4)),
          ),
        ],
      ),
    );
  }
}

/// Une ligne par tranche (maquette v2) : annoncé (gris) au-dessus de réalisé (violet).
class _CalibrationChart extends StatelessWidget {
  const _CalibrationChart(this.bins);
  final List<Json> bins;

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
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 5),
            child: Row(
              children: [
                SizedBox(
                  width: 74,
                  child: Text(_label(b['range']), style: Fp.body(12, color: Fp.text2)),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _bar((b['announced'] as num).toDouble(), const Color(0x66F4F2F8)),
                      const SizedBox(height: 3),
                      _bar((b['observed'] as num).toDouble(), const Color(0xFF8B5CF6)),
                    ],
                  ),
                ),
                SizedBox(
                  width: 48,
                  child: Text(
                    percent((b['observed'] as num).toDouble()),
                    textAlign: TextAlign.right,
                    style: Fp.body(13, weight: FontWeight.w800),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _bar(double value, Color color) => ClipRRect(
    borderRadius: BorderRadius.circular(99),
    child: SizedBox(
      height: 9,
      child: Stack(
        children: [
          const Positioned.fill(child: ColoredBox(color: Fp.fill6)),
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
      padding: const EdgeInsets.symmetric(vertical: 12),
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
                  '1 ${percent(probs[0])} · N ${percent(probs[1])} · 2 ${percent(probs[2])}',
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

class _Backtest extends StatelessWidget {
  const _Backtest(this.b);
  final Json b;

  @override
  Widget build(BuildContext context) {
    final ll = b['log_loss'] as Json;
    const names = {
      '1X2': 'Résultat du match',
      'OU|2.5': 'Plus/moins de 2,5 buts',
      'BTTS': 'Les deux marquent',
    };
    return GlassCard.section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('Backtest', style: Fp.title(17, weight: FontWeight.w600)),
              ),
              const Tag('Simulation', color: Fp.warning),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            '${b['label']} · ${thousands(b['matches'] as int)} matchs, saisons ${b['seasons']}, '
            'moteur ${b['engine_version']}.',
            style: Fp.body(13, color: Fp.text2, height: 1.4),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              const Expanded(flex: 4, child: SizedBox()),
              for (final h in const ['Modèle', 'Naïf', 'Clôture'])
                Expanded(
                  flex: 2,
                  child: Text(
                    h,
                    textAlign: TextAlign.right,
                    style: Fp.body(11, color: Fp.text2, weight: FontWeight.w700),
                  ),
                ),
            ],
          ),
          for (final e in ll.entries)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(
                children: [
                  Expanded(
                    flex: 4,
                    child: Text(names[e.key] ?? e.key, style: Fp.body(13, color: Fp.textStrong)),
                  ),
                  for (final k in const ['model', 'naive', 'closing_odds'])
                    Expanded(
                      flex: 2,
                      child: Text(
                        (e.value as Json)[k] == null ? '—' : decimal((e.value as Json)[k], max: 4),
                        textAlign: TextAlign.right,
                        style: Fp.body(
                          13,
                          weight: FontWeight.w700,
                          color: k == 'model' ? Fp.accentLight : Fp.text,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          const SizedBox(height: 8),
          Text('${b['note']}', style: Fp.body(12, color: Fp.text3, height: 1.4)),
        ],
      ),
    );
  }
}
