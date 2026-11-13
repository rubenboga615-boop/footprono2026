// Fiabilité des coupons en direct (maquette D15 validée le 13/11/2026) : par profil et par
// moment, chance annoncée par le moteur et part réellement gagnée des sélections proposées
// depuis la mise en service, avec le nombre de sélections.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/models.dart';
import '../format.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';

const _profiles = ['Sûr', 'Équilibré', 'Audacieux'];

String _momentLabel(String m) => switch (m) {
  'mi-temps' => 'Mi-temps',
  "60'" => '60e',
  "75'" => '75e',
  _ => m,
};

class LiveReliabilityScreen extends StatefulWidget {
  const LiveReliabilityScreen({super.key});

  @override
  State<LiveReliabilityScreen> createState() => _LiveReliabilityScreenState();
}

class _LiveReliabilityScreenState extends State<LiveReliabilityScreen> {
  int profile = 0;

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          errorHeader: const BackHeader('Fiabilité', 'en direct'),
          load: () async => await api.get('/live/coupons/reliability') as Json,
          builder: (context, r, reload) {
            final all = (r['profiles'] as Map?) ?? const {};
            final rows = ((all[_profiles[profile]] as List?) ?? const []).cast<Map>();
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: pagePadding(context, 16, 32, maxWidth: 640),
                children: [
                  const BackHeader('Fiabilité', 'en direct'),
                  const SizedBox(height: 8),
                  Text(
                    'Coupons proposés en direct depuis la mise en service : chance annoncée par le '
                    'moteur et part réellement gagnée, par moment.',
                    style: Fp.body(13, color: Fp.text2, height: 1.4),
                  ),
                  const SizedBox(height: 12),
                  SegmentTabs(
                    labels: _profiles,
                    selected: profile,
                    onSelected: (i) => setState(() => profile = i),
                  ),
                  const SizedBox(height: 12),
                  GlassCard.section(
                    padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                    child: rows.isEmpty
                        ? Padding(
                            padding: const EdgeInsets.symmetric(vertical: 18),
                            child: Text(
                              'Pas encore de coupon en direct réglé pour ce profil. Les chiffres '
                              'arrivent après les premiers matchs.',
                              textAlign: TextAlign.center,
                              style: Fp.body(13, color: Fp.text2, height: 1.4),
                            ),
                          )
                        : Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              _Row(_profiles[profile], 'Annoncé', 'Gagnés', 'Coupons', header: true),
                              for (final row in rows)
                                _Row(
                                  _momentLabel('${row['moment']}'),
                                  percent((row['announced'] as num).toDouble()),
                                  percent((row['won'] as num).toDouble()),
                                  thousands(row['count'] as num),
                                  fair: row['fair'] == true,
                                ),
                            ],
                          ),
                  ),
                  if (r['total'] is num && (r['total'] as num) > 0) ...[
                    const SizedBox(height: 12),
                    _Money(r),
                  ],
                  if (rows.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      'Juste : écart dans la marge attendue pour ce nombre de coupons (deux erreurs '
                      'types). Peu de coupons : marge large.',
                      style: Fp.body(12, color: Fp.muted, height: 1.4),
                    ),
                    const SizedBox(height: 12),
                    for (final row in rows) _Bar(row),
                  ],
                  const SizedBox(height: 16),
                  GlassCard.section(
                    padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Avant la mise en service', style: Fp.body(14, weight: FontWeight.w700)),
                        const SizedBox(height: 4),
                        Text(
                          'Vérifié sur 13 347 matchs des saisons passées, jamais vus par le moteur '
                          'pendant l\'apprentissage.',
                          style: Fp.body(12.5, color: Fp.text2, height: 1.4),
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

class _Row extends StatelessWidget {
  const _Row(this.label, this.announced, this.won, this.count, {this.header = false, this.fair});
  final String label;
  final String announced;
  final String won;
  final String count;
  final bool header;
  final bool? fair;

  @override
  Widget build(BuildContext context) {
    final style = header
        ? Fp.body(12, weight: FontWeight.w600, color: Fp.text2)
        : Fp.body(13.5, weight: FontWeight.w600);
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 9),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Fp.line)),
      ),
      child: Row(
        children: [
          Expanded(
            flex: 4,
            child: Text(label, style: header ? style.copyWith(color: Fp.text) : style),
          ),
          Expanded(
            flex: 3,
            child: Text(announced, textAlign: TextAlign.right, style: style),
          ),
          Expanded(
            flex: 3,
            child: Text(
              won,
              textAlign: TextAlign.right,
              style: fair == null ? style : style.copyWith(color: fair! ? Fp.win : Fp.warning),
            ),
          ),
          Expanded(
            flex: 3,
            child: Text(count, textAlign: TextAlign.right, style: style),
          ),
        ],
      ),
    );
  }
}

/// Bilan en argent : une mise de 1 000 F sur chaque proposition réglée (décision du 13/11).
class _Money extends StatelessWidget {
  const _Money(this.r);
  final Map r;

  @override
  Widget build(BuildContext context) {
    final profit = (r['profit'] as num?)?.toInt() ?? 0;
    final total = (r['total'] as num).toInt();
    final stake = (r['stake'] as num?)?.toInt() ?? 1000;
    final trial = r['trial'] != false;
    final rate = profit / (total * stake);
    return GlassCard.section(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Si tu avais misé ${money(stake)} sur chaque coupon en direct proposé ($total réglés) :',
            style: Fp.body(12.5, color: Fp.text2, height: 1.4),
          ),
          const SizedBox(height: 4),
          Text(
            '${signedMoney(profit)} · ${rate >= 0 ? '+' : '−'}${percent(rate.abs(), decimals: 1)}',
            style: Fp.body(18, weight: FontWeight.w800, color: profit >= 0 ? Fp.win : Fp.loss),
          ),
          if (trial) ...[
            const SizedBox(height: 4),
            Text(
              'En test : moins de ${r['trial_settled'] ?? 200} coupons réglés, ou bilan négatif.',
              style: Fp.body(12, color: Fp.warning, height: 1.4),
            ),
          ],
        ],
      ),
    );
  }
}

/// Barre : part gagnée ; trait vert : chance annoncée ; « juste » ou « à surveiller ».
class _Bar extends StatelessWidget {
  const _Bar(this.row);
  final Map row;

  @override
  Widget build(BuildContext context) {
    final announced = (row['announced'] as num).toDouble().clamp(0.0, 1.0);
    final won = (row['won'] as num).toDouble().clamp(0.0, 1.0);
    final fair = row['fair'] == true;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${_momentLabel('${row['moment']}')} · annoncé contre gagné'
                  '${row['profit'] is num ? ' · bilan ${signedMoney(row['profit'] as num)}' : ''}',
                  style: Fp.body(12.5, color: Fp.text2),
                ),
              ),
              Text(
                fair ? 'juste' : 'à surveiller',
                style: Fp.body(12, weight: FontWeight.w700, color: fair ? Fp.win : Fp.warning),
              ),
            ],
          ),
          const SizedBox(height: 6),
          LayoutBuilder(
            builder: (context, c) => SizedBox(
              height: 14,
              child: Stack(
                children: [
                  Positioned(
                    left: 0,
                    right: 0,
                    top: 3,
                    height: 8,
                    child: DecoratedBox(
                      decoration: BoxDecoration(color: Fp.line, borderRadius: BorderRadius.circular(4)),
                    ),
                  ),
                  Positioned(
                    left: 0,
                    top: 3,
                    height: 8,
                    width: c.maxWidth * won,
                    child: DecoratedBox(
                      decoration: BoxDecoration(color: Fp.accent, borderRadius: BorderRadius.circular(4)),
                    ),
                  ),
                  Positioned(
                    left: (c.maxWidth * announced - 1).clamp(0.0, c.maxWidth - 2),
                    top: 0,
                    width: 2,
                    height: 14,
                    child: const ColoredBox(color: Fp.win),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Entrée depuis la Fiabilité, seulement quand le coupon en direct est publié.
class LiveReliabilityLink extends StatelessWidget {
  const LiveReliabilityLink({super.key});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return FutureBuilder<Object?>(
      future: api.get('/live/coupons/reliability').then<Object?>((v) => v, onError: (Object _) => null),
      builder: (context, snap) {
        final r = snap.data;
        if (r is! Map || r['published'] != true) return const SizedBox.shrink();
        return Padding(
          padding: const EdgeInsets.only(top: 12),
          child: InkWell(
            onTap: () =>
                Navigator.of(context)
                    .push(MaterialPageRoute<void>(builder: (_) => const LiveReliabilityScreen())),
            child: GlassCard.section(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Coupons en direct', style: Fp.body(14, weight: FontWeight.w700)),
                        const SizedBox(height: 2),
                        Text(
                          'Annoncé contre gagné, à la mi-temps, à la 60e et à la 75e',
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
      },
    );
  }
}
