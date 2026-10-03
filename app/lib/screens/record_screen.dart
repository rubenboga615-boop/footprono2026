import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Mon bilan : les paris fictifs réglés du joueur, visibles par lui seul.
class RecordScreen extends StatelessWidget {
  const RecordScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    final currency = state.me?.currency ?? 'XOF';
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          load: () async => await state.api.get('/me/record') as Json,
          builder: (context, data, reload) => RefreshIndicator(
            onRefresh: reload,
            child: ListView(
              padding: const EdgeInsets.fromLTRB(18, 16, 18, 40),
              children: [
                const BackHeader(
                  'Mon',
                  'bilan',
                  subtitle: 'Tes paris fictifs réglés, visibles par toi seul.',
                ),
                const SizedBox(height: 16),
                ..._content(data, currency),
              ],
            ),
          ),
        ),
      ),
    );
  }

  List<Widget> _content(Json data, String currency) {
    final bets = data['bets'] as Json;
    if ((bets['settled'] as int) == 0) {
      return [
        EmptyState(
          (bets['open'] as int) > 0
              ? 'Aucun pari réglé pour l\'instant : ton bilan apparaîtra après les matchs.'
              : 'Aucun pari réglé pour l\'instant. Place des paris fictifs pour voir ton bilan.',
          icon: Icons.insights_rounded,
        ),
      ];
    }
    final profit = data['profit'] as int;
    final yield_ = (data['yield'] as num?)?.toDouble();
    final bands = (data['calibration'] as List).cast<Json>();
    final best = bands.where((b) => b['enough'] == true).toList()
      ..sort((a, b) => (b['selections'] as int).compareTo(a['selections'] as int));
    return [
      if (data['rising'] == true) ...[
        GlassCard.section(
          highlight: true,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.self_improvement_rounded, color: Fp.warning),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Tes mises de la semaine (${money(data['stakes_7d'] as int, currency)}) ont au moins doublé '
                  'par rapport à la semaine d\'avant (${money(data['stakes_prev_7d'] as int, currency)}). '
                  'Même en argent fictif, garde la tête froide : Profil → Jeu responsable.',
                  style: Fp.body(13, color: Fp.textSoft, height: 1.4),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
      ],
      GlassCard.section(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Rendement', style: Fp.title(15, weight: FontWeight.w600)),
            const SizedBox(height: 6),
            KeyValue('Paris réglés', '${bets['settled']}'),
            KeyValue(
              'Gagnés · perdus',
              '${bets['won']} · ${bets['lost']}'
                  '${(bets['push'] as int) + (bets['partial'] as int) > 0 ? ' · ${(bets['push'] as int) + (bets['partial'] as int)} autres' : ''}',
            ),
            KeyValue('Misé', money(data['staked'] as int, currency)),
            KeyValue('Récupéré', money(data['returned'] as int, currency)),
            KeyValue(
              'Résultat net',
              signedMoney(profit, currency),
              valueColor: profit >= 0 ? Fp.win : Fp.loss,
              bold: true,
            ),
            if (yield_ != null)
              KeyValue(
                'Rendement',
                '${yield_ >= 0 ? '+' : '−'}${percent(yield_.abs(), decimals: 1)}',
                valueColor: yield_ >= 0 ? Fp.win : Fp.loss,
              ),
            if ((bets['open'] as int) > 0)
              Text('${bets['open']} pari(s) en cours non comptés.', style: Fp.body(12, color: Fp.text3)),
          ],
        ),
      ),
      const SizedBox(height: 12),
      GlassCard.section(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Annoncé contre réalisé', style: Fp.title(15, weight: FontWeight.w600)),
            const SizedBox(height: 4),
            Text(
              'Chaque sélection (y compris dans un combiné), groupée selon la probabilité du moteur '
              'au moment du pari.',
              style: Fp.body(12, color: Fp.text3, height: 1.4),
            ),
            if (best.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(
                'Tes sélections annoncées autour de ${percent((best.first['announced'] as num).toDouble())} '
                'ont gagné ${percent((best.first['observed'] as num).toDouble())} du temps.',
                style: Fp.body(14, color: Fp.textSoft, weight: FontWeight.w600, height: 1.4),
              ),
            ],
            if (bands.isEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  'Pas encore de sélection réglée avec une probabilité du moteur.',
                  style: Fp.body(13, color: Fp.text2),
                ),
              ),
            for (final b in bands) _Band(b, data['min_band'] as int),
          ],
        ),
      ),
      const SizedBox(height: 12),
      _Breakdown('Par marché', (data['by_market'] as List).cast<Json>(), (k) => marketTitle(k)),
      const SizedBox(height: 12),
      _Breakdown('Par championnat', (data['by_competition'] as List).cast<Json>(), competitionName),
      if (((data['by_odds'] as List?) ?? const []).isNotEmpty) ...[
        const SizedBox(height: 12),
        _ByOdds((data['by_odds'] as List).cast<Json>(), currency),
      ],
      const SizedBox(height: 14),
      Text(
        'Réussite : sélections gagnées (demi-gains compris) sur gagnées + perdues ; remboursées à part. '
        'Selon la cote : 1 / cote, la probabilité que la cote annonce (marge du bookmaker comprise). '
        'Argent fictif : aucun gain réel.',
        style: Fp.body(12, color: Fp.text3, height: 1.4),
      ),
    ];
  }
}

class _Band extends StatelessWidget {
  const _Band(this.b, this.minBand);
  final Json b;
  final int minBand;

  @override
  Widget build(BuildContext context) {
    double v(String k) => (b[k] as num).toDouble();
    final enough = b['enough'] == true;
    Widget cell(String label, String value, {Color color = Fp.text}) => Expanded(
      child: Column(
        children: [
          Text(value, style: Fp.title(15, color: color)),
          Text(label, style: Fp.body(11, color: Fp.text3)),
        ],
      ),
    );
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Annoncées ${percent(v('low'))} à ${percent(v('high'))} · ${b['selections']} sélection(s)',
            style: Fp.body(13, weight: FontWeight.w600),
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              cell('annoncé', percent(v('announced')), color: Fp.accentLight),
              cell('selon la cote', percent(v('implied')), color: Fp.text2),
              cell('réalisé', percent(v('observed')), color: enough ? Fp.text : Fp.text3),
            ],
          ),
          if (!enough)
            Text(
              'Moins de $minBand sélections : l\'écart vient surtout du hasard.',
              textAlign: TextAlign.center,
              style: Fp.body(11, color: Fp.warning),
            ),
        ],
      ),
    );
  }
}

class _Breakdown extends StatelessWidget {
  const _Breakdown(this.title, this.rows, this.label);
  final String title;
  final List<Json> rows;
  final String Function(String) label;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) return const SizedBox.shrink();
    return GlassCard.section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(title, style: Fp.title(15, weight: FontWeight.w600)),
              ),
              Text('gagnées · perdues · réussite', style: Fp.body(11, color: Fp.text3)),
            ],
          ),
          const SizedBox(height: 4),
          for (final r in rows)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(
                children: [
                  Expanded(
                    child: Text(label(r['key'] as String), style: Fp.body(14, weight: FontWeight.w600)),
                  ),
                  Text('${r['won']} · ${r['lost']}', style: Fp.body(13, color: Fp.text2)),
                  const SizedBox(width: 12),
                  SizedBox(
                    width: 52,
                    child: Text(
                      r['rate'] == null ? '—' : percent((r['rate'] as num).toDouble()),
                      textAlign: TextAlign.right,
                      style: Fp.body(14, color: Fp.accentLight, weight: FontWeight.w700),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// Paris réglés par tranche de cote totale : les grosses cotes réussissent-elles ?
class _ByOdds extends StatelessWidget {
  const _ByOdds(this.rows, this.currency);
  final List<Json> rows;
  final String currency;

  @override
  Widget build(BuildContext context) {
    String band(Json r) {
      final low = (r['low'] as num).toDouble(), high = (r['high'] as num?)?.toDouble();
      if (low <= 1) return 'moins de ${decimal(high, max: 0)}';
      return high == null
          ? '${decimal(low, max: 0)} et plus'
          : '${decimal(low, max: 0)} à ${decimal(high, max: 0)}';
    }

    Widget cell(String t, {TextAlign align = TextAlign.right, Color? color, bool bold = false}) => Text(
      t,
      textAlign: align,
      style: Fp.body(12.5, color: color ?? Fp.text, weight: bold ? FontWeight.w700 : FontWeight.w500),
    );
    return GlassCard.section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Par cote du coupon', style: Fp.title(15, weight: FontWeight.w600)),
          const SizedBox(height: 8),
          Table(
            columnWidths: const {
              0: FlexColumnWidth(1.6),
              1: FlexColumnWidth(),
              2: FlexColumnWidth(),
              3: FlexColumnWidth(1.1),
              4: FlexColumnWidth(1.4),
            },
            children: [
              TableRow(
                children: [
                  for (final (i, h) in ['Cote', 'Paris', 'Gagnés', 'Annoncé', 'Net'].indexed)
                    cell(h, align: i == 0 ? TextAlign.left : TextAlign.right, color: Fp.text3, bold: true),
                ],
              ),
              for (final r in rows)
                TableRow(
                  children: [
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 5),
                      child: cell(band(r), align: TextAlign.left),
                    ),
                    Padding(padding: const EdgeInsets.symmetric(vertical: 5), child: cell('${r['bets']}')),
                    Padding(padding: const EdgeInsets.symmetric(vertical: 5), child: cell('${r['won']}')),
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 5),
                      child: cell(r['announced'] == null ? '—' : percent((r['announced'] as num).toDouble())),
                    ),
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 5),
                      child: cell(
                        "${(r['profit'] as int) >= 0 ? '+' : '−'}${thousands((r['profit'] as int).abs())}",
                        color: (r['profit'] as int) >= 0 ? Fp.win : Fp.loss,
                        bold: true,
                      ),
                    ),
                  ],
                ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            '« Annoncé » : chances moyennes données par le moteur pour ces paris. Avec des chances de 3 %, '
            'perdre 10 paris de suite est normal.',
            style: Fp.body(11, color: Fp.text3, height: 1.4),
          ),
        ],
      ),
    );
  }
}
