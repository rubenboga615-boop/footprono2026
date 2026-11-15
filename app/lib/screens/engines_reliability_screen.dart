// Moteur 1 contre moteur 2 (maquette K6 validée le 15/11/2026) : le juge. Sur les mêmes
// matchs, chances annoncées contre réalité (log loss), puis bilan en argent avec une mise fixe
// sur chaque proposition de chaque moteur, jouée ou non. Verdict seulement avec assez de
// données ; jamais de conclusion avant.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../desktop/layout.dart';
import '../format.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/engine_compare.dart';

class EnginesReliabilityScreen extends StatelessWidget {
  const EnginesReliabilityScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          errorHeader: const BackHeader('Moteur 1', 'contre 2'),
          load: () async => await api.get('/reliability/engines') as Json,
          builder: (context, r, reload) {
            final loss = (r['log_loss'] as Map).cast<String, dynamic>();
            final bilans = (r['money'] as List).cast<Json>();
            final stake = (r['stake'] as num?)?.toInt() ?? 1000;
            final enough = r['enough'] == true;
            final n = (r['matches'] as num).toInt();
            String ll(Object? v) => v == null ? '—' : decimal(v, max: 3);
            String yieldOf(Json e) {
              final y = e['yield'];
              if (y == null) return '—';
              final v = (y as num).toDouble();
              return '${v >= 0 ? '+' : '−'}${percent(v.abs(), decimals: 1)}';
            }

            Color yieldColor(Json e) {
              final y = e['yield'];
              return y == null ? Fp.text2 : ((y as num) >= 0 ? Fp.win : Fp.loss);
            }

            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: pagePadding(context, 16, 32, maxWidth: 640),
                children: [
                  const BackHeader('Moteur 1', 'contre 2'),
                  const SizedBox(height: 8),
                  Text(
                    'Le juge : sur les mêmes matchs, les chances annoncées contre la réalité, puis le bilan '
                    'si tu avais misé ${money(stake)} sur chaque proposition de chaque moteur, jouée ou non.',
                    style: Fp.body(13, color: Fp.text2, height: 1.4),
                  ),
                  const SizedBox(height: 12),
                  GlassCard.section(
                    padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          'Chances (mêmes matchs, avant le coup d\'envoi)',
                          style: Fp.body(14, weight: FontWeight.w700),
                        ),
                        const SizedBox(height: 6),
                        const _Header(),
                        _Line('Matchs comparés', thousands(n), null),
                        _Line(
                          'Justesse (log loss, plus bas = mieux)',
                          ll(loss['1']),
                          ll(loss['2']),
                          highlight: _better(loss['1'], loss['2'], lowerIsBetter: true),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Moteur 2 calé sur la cote de référence pour ${thousands(r['calibrated'] as num)} de '
                          'ces matchs ; les autres, il donne les mêmes chances que le moteur 1.',
                          style: Fp.body(12, color: Fp.muted, height: 1.4),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  GlassCard.section(
                    padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          'Bilan, ${money(stake)} par proposition',
                          style: Fp.body(14, weight: FontWeight.w700),
                        ),
                        const SizedBox(height: 6),
                        const _Header(),
                        for (final m in bilans)
                          Builder(
                            builder: (context) {
                              final e = (m['engines'] as Map).cast<String, dynamic>();
                              final one = (e['1'] as Map).cast<String, dynamic>();
                              final two = (e['2'] as Map).cast<String, dynamic>();
                              return _Line(
                                '${m['label']} (${one['settled']} · ${two['settled']})',
                                yieldOf(one),
                                yieldOf(two),
                                colors: (yieldColor(one), yieldColor(two)),
                              );
                            },
                          ),
                        const SizedBox(height: 4),
                        Text(
                          'Entre parenthèses : propositions réglées de chaque moteur. Remboursées non comptées.',
                          style: Fp.body(12, color: Fp.muted, height: 1.4),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
                    decoration: BoxDecoration(
                      color: enough ? Fp.card : const Color(0xFF1F1709),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: enough ? Fp.line10 : const Color(0xFF6B4F1D)),
                    ),
                    child: Text(
                      enough
                          ? _verdict(loss, bilans)
                          : 'Trop peu de données pour conclure (il faut au moins ${r['min_matches']} matchs et '
                                '${r['min_proposals']} propositions réglées par moteur).',
                      style: Fp.body(13, color: enough ? Fp.text : Fp.warning, height: 1.4),
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

  /// 1 ou 2 : le meilleur des deux ; null : égalité ou rien à comparer.
  static int? _better(Object? a, Object? b, {required bool lowerIsBetter}) {
    if (a is! num || b is! num || a == b) return null;
    return (a < b) == lowerIsBetter ? 1 : 2;
  }

  /// Ce que disent les chiffres, sans rien ajouter : justesse puis argent, chacun à part.
  static String _verdict(Map<String, dynamic> loss, List<Json> money) {
    final best = _better(loss['1'], loss['2'], lowerIsBetter: true);
    var profit1 = 0, profit2 = 0;
    for (final m in money) {
      final e = (m['engines'] as Map).cast<String, dynamic>();
      profit1 += ((e['1'] as Map)['profit'] as num).toInt();
      profit2 += ((e['2'] as Map)['profit'] as num).toInt();
    }
    final chances = best == null
        ? 'Les deux moteurs sont aussi justes sur les chances.'
        : 'Le moteur $best est le plus juste sur les chances.';
    final cash = profit1 == profit2
        ? 'Même bilan en argent.'
        : 'Meilleur bilan en argent : moteur ${profit1 > profit2 ? 1 : 2} '
              '(${signedMoney(profit1)} contre ${signedMoney(profit2)}).';
    return '$chances $cash Une mesure du passé, pas une garantie.';
  }
}

class _Header extends StatelessWidget {
  const _Header();

  @override
  Widget build(BuildContext context) => const Padding(
    padding: EdgeInsets.only(bottom: 4),
    child: Row(
      children: [
        Expanded(child: SizedBox()),
        SizedBox(
          width: 70,
          child: Align(alignment: Alignment.centerRight, child: EngineTag(1)),
        ),
        SizedBox(width: 8),
        SizedBox(
          width: 70,
          child: Align(alignment: Alignment.centerRight, child: EngineTag(2)),
        ),
      ],
    ),
  );
}

class _Line extends StatelessWidget {
  const _Line(this.label, this.one, this.two, {this.highlight, this.colors});
  final String label;
  final String one;
  final String? two;
  final int? highlight;
  final (Color, Color)? colors;

  @override
  Widget build(BuildContext context) {
    TextStyle style(int engine) => Fp.body(
      13.5,
      weight: highlight == engine ? FontWeight.w800 : FontWeight.w600,
      color: colors == null
          ? (highlight == engine ? Fp.win : Fp.text)
          : (engine == 1 ? colors!.$1 : colors!.$2),
    );
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 8),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Fp.line)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(label, style: Fp.body(13, color: Fp.text2, height: 1.3)),
          ),
          SizedBox(
            width: two == null ? 148 : 70,
            child: Text(one, textAlign: TextAlign.right, style: style(1)),
          ),
          if (two != null) ...[
            const SizedBox(width: 8),
            SizedBox(
              width: 70,
              child: Text(two!, textAlign: TextAlign.right, style: style(2)),
            ),
          ],
        ],
      ),
    );
  }
}

/// Entrée depuis la Fiabilité, seulement en mode comparaison.
class EnginesReliabilityLink extends StatelessWidget {
  const EnginesReliabilityLink({super.key});

  @override
  Widget build(BuildContext context) {
    if (!context.watch<AppState>().compareEngines) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: InkWell(
        onTap: () =>
            Navigator.of(context)
                .push(MaterialPageRoute<void>(builder: (_) => const EnginesReliabilityScreen())),
        child: GlassCard.section(
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Moteur 1 contre moteur 2', style: Fp.body(14, weight: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Text(
                      'Mêmes matchs, mêmes règles : lequel est le plus juste',
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
