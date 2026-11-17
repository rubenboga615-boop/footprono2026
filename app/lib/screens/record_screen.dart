import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
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
              padding: pagePadding(context, 16, 40, maxWidth: 1080),
              children: [
                const BackHeader(
                  'Mon',
                  'bilan',
                  subtitle: 'Tes paris fictifs réglés, visibles par toi seul.',
                ),
                const SizedBox(height: 16),
                ...deskColumns(context, _content(data, currency)),
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
              // Rapport du 09/11/2026 : « 1 autres » ne disait ni l'accord ni ce que c'était.
              [
                '${bets['won']}',
                '${bets['lost']}',
                if (bets['push'] as int > 0) '${bets['push']} remboursé${bets['push'] as int > 1 ? 's' : ''}',
                if (bets['partial'] as int > 0)
                  '${bets['partial']} en partie gagné${bets['partial'] as int > 1 ? 's' : ''}',
              ].join(' · '),
            ),
            KeyValue('Misé', money(data['staked'] as int, currency)),
            KeyValue('Récupéré', money(data['returned'] as int, currency)),
            KeyValue(
              'Résultat net',
              signedMoney(profit, currency),
              valueColor: profit >= 0 ? Fp.win : Fp.loss,
              bold: true,
            ),
            // Même règle que Mes paris (rapport du 10/11/2026 : « −48,1 % » après 3 paris).
            if (yield_ != null && (bets['settled'] as int) >= 20)
              KeyValue(
                'Rendement',
                '${yield_ >= 0 ? '+' : '−'}${percent(yield_.abs(), decimals: 1)}',
                valueColor: yield_ >= 0 ? Fp.win : Fp.loss,
              )
            else if (yield_ != null)
              KeyValue('Rendement', 'trop peu de paris (${bets['settled']} sur 20)'),
            if ((bets['open'] as int) > 0)
              Text(
                '${bets['open']} pari${(bets['open'] as int) > 1 ? 's' : ''} en cours non compté${(bets['open'] as int) > 1 ? 's' : ''}.',
                style: Fp.body(12, color: Fp.text3),
              ),
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
      _Breakdown(
        'Par marché',
        (data['by_market'] as List).cast<Json>(),
        (k) => marketTitle(k),
        data['min_band'] as int,
      ),
      const SizedBox(height: 12),
      _Breakdown(
        'Par championnat',
        (data['by_competition'] as List).cast<Json>(),
        competitionName,
        data['min_band'] as int,
      ),
      if (((data['by_odds'] as List?) ?? const []).isNotEmpty) ...[
        const SizedBox(height: 12),
        _ByOdds((data['by_odds'] as List).cast<Json>(), currency),
      ],
      const SizedBox(height: 14),
      Text(
        'Réalisé : sélections gagnées (demi-gains compris) sur gagnées + perdues ; remboursées à part. '
        'Annoncé : chance moyenne donnée par le moteur au moment du pari. Rouge ou vert : écart net, '
        'plus grand que le hasard, sur au moins ${data['min_band']} sélections. '
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
            'Annoncées ${percent(v('low'))} à ${percent(v('high'))} · ${b['selections']} sélection${(b['selections'] as int) > 1 ? 's' : ''}',
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

/// Par marché ou par championnat, avec la chance annoncée par le moteur à côté du réalisé
/// (maquette docs/maquettes/11-bilan-annonce, validée le 17/11/2026).
class _Breakdown extends StatelessWidget {
  const _Breakdown(this.title, this.rows, this.label, this.minBand);
  final String title;
  final List<Json> rows;
  final String Function(String) label;
  final int minBand;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) return const SizedBox.shrink();
    Widget head(String t, double w) => SizedBox(
      width: w,
      child: Text(
        t,
        textAlign: TextAlign.right,
        style: Fp.body(11, color: Fp.text3),
      ),
    );
    return GlassCard.section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(title, style: Fp.title(15, weight: FontWeight.w600)),
              ),
              head('sél.', 34),
              head('annoncé', 62),
              head('réalisé', 56),
            ],
          ),
          const SizedBox(height: 4),
          for (final r in rows) _BreakdownRow(r, label(r['key'] as String), minBand),
        ],
      ),
    );
  }
}

class _BreakdownRow extends StatelessWidget {
  const _BreakdownRow(this.r, this.name, this.minBand);
  final Json r;
  final String name;
  final int minBand;

  @override
  Widget build(BuildContext context) {
    final graded = (r['won'] as int) + (r['lost'] as int);
    final total = graded + (r['push'] as int);
    final rate = (r['rate'] as num?)?.toDouble();
    final announced = (r['announced'] as num?)?.toDouble();
    final gap = r['gap'] as String?;
    final color = switch (gap) {
      'low' => Fp.loss,
      'high' => Fp.win,
      _ => Fp.accentLight,
    };
    // Petit échantillon et grand écart : on prévient que c'est surtout le hasard.
    final fewButFar =
        gap == null &&
        graded < minBand &&
        rate != null &&
        announced != null &&
        (rate - announced).abs() >= 0.15;
    final note = switch (gap) {
      'low' => ('Bien en dessous de l\'annoncé', Fp.loss),
      'high' => ('Bien au-dessus de l\'annoncé', Fp.win),
      _ when fewButFar => ('Moins de $minBand sélections : l\'écart vient surtout du hasard.', Fp.warning),
      _ => null,
    };
    Widget cell(String t, double w, TextStyle style) => SizedBox(
      width: w,
      child: Text(t, textAlign: TextAlign.right, style: style),
    );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: Fp.body(14, weight: FontWeight.w600)),
                if (note != null) Text(note.$1, style: Fp.body(11.5, color: note.$2)),
              ],
            ),
          ),
          cell('$total', 34, Fp.body(13, color: Fp.text2)),
          cell(
            announced == null ? '—' : percent(announced),
            62,
            Fp.body(14, color: Fp.accentLight, weight: FontWeight.w700),
          ),
          cell(rate == null ? '—' : percent(rate), 56, Fp.body(14, color: color, weight: FontWeight.w700)),
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
