// Suivi et analyse des montantes (maquettes M1, M2 et M4 validées le 13/11/2026) : bilan
// du joueur, gagnées et perdues ensemble ; analyse de ses montantes ; Fiabilité des
// montantes pour tous les joueurs. Chiffres réels uniquement, jamais de conseil de pari.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../desktop/layout.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';

String _signed(num v) => signedMoney(v.round());

/// M1 : bilan de mes montantes, en haut de l'onglet Montante.
class MontanteSummaryCard extends StatelessWidget {
  const MontanteSummaryCard({super.key});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return FutureBuilder<Object?>(
      future: api.get('/me/montantes/summary').then<Object?>((v) => v, onError: (Object _) => null),
      builder: (context, snap) {
        final r = snap.data;
        if (r is! Map || (r['montantes'] as num? ?? 0) == 0) return const SizedBox.shrink();
        final counts = (r['counts'] as Map?) ?? const {};
        final net = (r['net'] as num).toInt();
        Widget cell(String label, Object? n, [Color? color]) => Expanded(
          child: Container(
            padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
            decoration: BoxDecoration(color: Fp.background, borderRadius: BorderRadius.circular(12)),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: Fp.body(11.5, color: Fp.muted)),
                Text(
                  '${n ?? 0}',
                  style: Fp.body(17, weight: FontWeight.w800, color: color ?? Fp.text),
                ),
              ],
            ),
          ),
        );
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: GlassCard.section(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Mon bilan des montantes', style: Fp.body(12, color: Fp.muted)),
                Text(
                  _signed(net),
                  style: Fp.body(28, weight: FontWeight.w800, color: net >= 0 ? Fp.win : Fp.lossText),
                ),
                Text(
                  '${money(r['staked'] as num)} misés au départ · ${money(r['returned'] as num)} encaissés'
                  '${(counts['active'] as num? ?? 0) > 0 ? ' · en cours comptées comme misées' : ''}',
                  style: Fp.body(12.5, color: Fp.text2, height: 1.4),
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    cell('Réussies', counts['completed'], Fp.win),
                    const SizedBox(width: 8),
                    cell('Perdues', counts['lost'], Fp.lossText),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    cell('Encaissées avant la fin', counts['cashed_out']),
                    const SizedBox(width: 8),
                    cell('En cours', counts['active']),
                  ],
                ),
                const SizedBox(height: 10),
                InkWell(
                  onTap: () =>
                      Navigator.of(context)
                          .push(MaterialPageRoute<void>(builder: (_) => MontanteAnalysisScreen(summary: r))),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Text(
                      'Voir l\'analyse ›',
                      style: Fp.body(13.5, weight: FontWeight.w700, color: Fp.accentLight),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// Barres « jusqu'où vont mes montantes » : barre violette = part arrivée au palier,
/// trait vert = attendu selon les cotes.
class _Survival extends StatelessWidget {
  const _Survival(this.rows);
  final List<Map> rows;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 150,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (final r in rows)
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 3),
                child: LayoutBuilder(
                  builder: (context, c) {
                    final h = c.maxHeight - 48;
                    final reached = (r['reached'] as num).toDouble().clamp(0.0, 1.0);
                    final expected = (r['expected'] as num).toDouble().clamp(0.0, 1.0);
                    return Column(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        Text(percent(reached), style: Fp.body(10.5, color: Fp.text2)),
                        const SizedBox(height: 2),
                        SizedBox(
                          height: h,
                          child: Stack(
                            alignment: Alignment.bottomCenter,
                            children: [
                              Container(
                                height: (h * reached).clamp(2.0, h),
                                decoration: BoxDecoration(
                                  color: Fp.accent,
                                  borderRadius: const BorderRadius.vertical(top: Radius.circular(6)),
                                ),
                              ),
                              Positioned(
                                left: -2,
                                right: -2,
                                bottom: (h * expected - 1).clamp(0.0, h - 2),
                                child: Container(height: 2, color: Fp.win),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text('P${r['step']}', style: Fp.body(11, color: Fp.muted)),
                      ],
                    );
                  },
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// M2 : analyse de mes montantes.
class MontanteAnalysisScreen extends StatelessWidget {
  const MontanteAnalysisScreen({super.key, required this.summary});
  final Map summary;

  @override
  Widget build(BuildContext context) {
    final r = summary;
    final survival = ((r['survival'] as List?) ?? const []).cast<Map>();
    final stops = (r['stops'] as Map?) ?? const {};
    final choices = (r['choices'] as Map?) ?? const {};
    final markets = ((r['markets'] as List?) ?? const []).cast<Map>();
    final finished = (r['finished'] as num? ?? 0).toInt();
    String share(Map c) {
      final n = (c['steps'] as num? ?? 0).toInt();
      return n == 0 ? '—' : percent((c['won'] as num) / n);
    }

    TableRow row(List<String> cells, {bool header = false}) => TableRow(
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Fp.line10)),
      ),
      children: [
        for (final (i, t) in cells.indexed)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text(
              t,
              textAlign: i == 0 ? TextAlign.left : TextAlign.right,
              style: header
                  ? Fp.body(11.5, color: Fp.muted, weight: FontWeight.w600)
                  : Fp.body(13, weight: i == 0 ? FontWeight.w500 : FontWeight.w700),
            ),
          ),
      ],
    );

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: ListView(
          padding: pagePadding(context, 16, 32, maxWidth: 640),
          children: [
            const BackHeader('Mes', 'montantes', joined: true),
            const SizedBox(height: 12),
            GlassCard.section(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('Jusqu\'où vont mes montantes', style: Fp.body(14, weight: FontWeight.w700)),
                  Text(
                    'Barre : mes montantes terminées arrivées à ce palier · trait vert : attendu selon les cotes',
                    style: Fp.body(12, color: Fp.muted, height: 1.4),
                  ),
                  const SizedBox(height: 12),
                  if (survival.isEmpty)
                    Text('Pas encore de montante terminée.', style: Fp.body(13, color: Fp.text2))
                  else
                    _Survival(survival),
                  const SizedBox(height: 8),
                  Text(
                    r['enough'] == true
                        ? '$finished montantes terminées. Au-dessus du trait vert : mieux que ce que disent les cotes.'
                        : '$finished montante${finished > 1 ? 's' : ''} terminée${finished > 1 ? 's' : ''} : '
                              'trop peu pour conclure (il en faut ${r['min_finished'] ?? 30}). Au-dessus du trait '
                              'vert : mieux que ce que disent les cotes.',
                    style: Fp.body(12, color: Fp.muted, height: 1.4),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            GlassCard.section(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('Où elles s\'arrêtent', style: Fp.body(14, weight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  for (final (kind, label) in [('lost', 'perdue'), ('cashed_out', 'encaissée')])
                    for (final s in ((stops[kind] as List?) ?? const []).cast<Map>())
                      KeyValue(
                        'Palier ${s['step']}',
                        '${s['count']} $label${(s['count'] as num) > 1 ? 's' : ''}',
                      ),
                  if (((stops['lost'] as List?) ?? const []).isEmpty &&
                      ((stops['cashed_out'] as List?) ?? const []).isEmpty)
                    Text('Aucune montante arrêtée.', style: Fp.body(13, color: Fp.text2)),
                ],
              ),
            ),
            const SizedBox(height: 12),
            GlassCard.section(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('Mes choix', style: Fp.body(14, weight: FontWeight.w700)),
                  Table(
                    columnWidths: const {
                      0: FlexColumnWidth(3),
                      1: FlexColumnWidth(1.2),
                      2: FlexColumnWidth(1.2),
                    },
                    children: [
                      row(['', 'Paliers', 'Gagnés'], header: true),
                      for (final (key, label) in [
                        ('engine', 'Proposés par le moteur'),
                        ('player', 'Composés moi-même'),
                        ('unknown', 'Avant le 14/11 (non connu)'),
                        ('out_of_range', 'Cote hors de la plage'),
                      ])
                        if (((choices[key] as Map?)?['steps'] as num? ?? 0) > 0)
                          row([label, '${(choices[key] as Map)['steps']}', share(choices[key] as Map)]),
                    ],
                  ),
                  if ((r['out_of_range_cost'] as num? ?? 0) > 0) ...[
                    const SizedBox(height: 8),
                    Text(
                      'Paliers joués sous leur plage : environ ${money(r['out_of_range_cost'] as num)} de moins à '
                      'l\'arrivée de mes montantes réussies.',
                      style: Fp.body(12, color: Fp.muted, height: 1.4),
                    ),
                  ],
                ],
              ),
            ),
            if (markets.isNotEmpty) ...[
              const SizedBox(height: 12),
              GlassCard.section(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text('Mes marchés en montante', style: Fp.body(14, weight: FontWeight.w700)),
                    Table(
                      columnWidths: const {
                        0: FlexColumnWidth(3),
                        1: FlexColumnWidth(1.2),
                        2: FlexColumnWidth(1.2),
                      },
                      children: [
                        row(['', 'Gagnés', 'Perdus'], header: true),
                        for (final m in markets.take(6))
                          row([marketTitle('${m['market']}'), '${m['won']}', '${m['lost']}']),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// M4 : Fiabilité des montantes, pour tous les joueurs, sans nom.
class MontanteReliabilityScreen extends StatelessWidget {
  const MontanteReliabilityScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          errorHeader: const BackHeader('Fiabilité', 'montantes'),
          load: () async => await api.get('/reliability/montantes') as Json,
          builder: (context, r, reload) {
            final steps = ((r['steps'] as List?) ?? const []).cast<Map>();
            final finished = (r['finished'] as num? ?? 0).toInt();
            final enough = r['enough'] == true;
            final yieldValue = r['yield'] as num?;
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: pagePadding(context, 16, 32, maxWidth: 640),
                children: [
                  const BackHeader('Fiabilité', 'montantes'),
                  const SizedBox(height: 8),
                  Text(
                    'Toutes les montantes des joueurs, sans nom : la chance annoncée par le moteur pour '
                    'chaque palier, contre ce qui est arrivé.',
                    style: Fp.body(13, color: Fp.text2, height: 1.4),
                  ),
                  const SizedBox(height: 12),
                  GlassCard.section(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text('Paliers joués', style: Fp.body(14, weight: FontWeight.w700)),
                        const SizedBox(height: 4),
                        if (steps.isEmpty)
                          Text('Pas encore de palier réglé.', style: Fp.body(13, color: Fp.text2))
                        else
                          Table(
                            columnWidths: const {
                              0: FlexColumnWidth(1.4),
                              1: FlexColumnWidth(1.2),
                              2: FlexColumnWidth(1.2),
                              3: FlexColumnWidth(1),
                            },
                            children: [
                              for (final (i, cells) in [
                                ['Palier', 'Annoncé', 'Gagnés', 'Paris'],
                                for (final s in steps)
                                  [
                                    '${s['steps']}',
                                    percent((s['announced'] as num).toDouble()),
                                    percent((s['won'] as num).toDouble()),
                                    '${s['count']}',
                                  ],
                              ].indexed)
                                TableRow(
                                  decoration: const BoxDecoration(
                                    border: Border(bottom: BorderSide(color: Fp.line10)),
                                  ),
                                  children: [
                                    for (final (j, t) in cells.indexed)
                                      Padding(
                                        padding: const EdgeInsets.symmetric(vertical: 8),
                                        child: Text(
                                          t,
                                          textAlign: j == 0 ? TextAlign.left : TextAlign.right,
                                          style: i == 0
                                              ? Fp.body(11.5, color: Fp.muted, weight: FontWeight.w600)
                                              : Fp.body(
                                                  13,
                                                  weight: FontWeight.w700,
                                                  color: j == 2 && enough
                                                      ? (steps[i - 1]['fair'] == true ? Fp.win : Fp.warning)
                                                      : Fp.text,
                                                ),
                                        ),
                                      ),
                                  ],
                                ),
                            ],
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  GlassCard.section(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text('Toutes les montantes terminées', style: Fp.body(14, weight: FontWeight.w700)),
                        const SizedBox(height: 4),
                        KeyValue('Montantes', thousands(finished)),
                        KeyValue(
                          'Allées au bout',
                          r['to_end_share'] == null
                              ? '—'
                              : '${r['to_end']} (${percent((r['to_end_share'] as num).toDouble())})',
                        ),
                        KeyValue(
                          'Attendu selon les cotes',
                          r['expected_share'] == null
                              ? '—'
                              : percent((r['expected_share'] as num).toDouble()),
                        ),
                        KeyValue(
                          'Bilan, mises de départ comprises',
                          yieldValue == null
                              ? '—'
                              : '${yieldValue >= 0 ? '+' : '−'}${percent(yieldValue.abs().toDouble(), decimals: 1)}',
                          valueColor: yieldValue == null ? null : (yieldValue >= 0 ? Fp.win : Fp.lossText),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          enough
                              ? 'Un seul succès change beaucoup le bilan : il se lit sur la durée.'
                              : 'Trop peu de montantes terminées pour conclure (il en faut ${r['min_finished'] ?? 30}).',
                          style: Fp.body(12, color: Fp.muted, height: 1.4),
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

/// Entrée « Montantes » de la Fiabilité.
class MontanteReliabilityLink extends StatelessWidget {
  const MontanteReliabilityLink({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: InkWell(
        onTap: () =>
            Navigator.of(context)
                .push(MaterialPageRoute<void>(builder: (_) => const MontanteReliabilityScreen())),
        child: GlassCard.section(
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Montantes', style: Fp.body(14, weight: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Text(
                      'Chance annoncée pour chaque palier contre ce qui est arrivé',
                      style: Fp.body(12.5, color: Fp.text2),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right_rounded, color: Fp.accentLight),
            ],
          ),
        ),
      ),
    );
  }
}
