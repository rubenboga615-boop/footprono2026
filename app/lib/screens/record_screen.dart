import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../widgets/common.dart';
import '../widgets/visage.dart';

/// Mon bilan (maquette 21 du nouveau visage) : période 7 j / 30 j / Tout, résultat en grand
/// avec ses barres, annoncé contre réalisé par marché ; gardés en plus, dans le même style :
/// le rappel de jeu responsable, le détail par championnat, par cote du coupon et par niveau
/// de chance.
class RecordScreen extends StatefulWidget {
  const RecordScreen({super.key});

  @override
  State<RecordScreen> createState() => _RecordScreenState();
}

class _RecordScreenState extends State<RecordScreen> {
  static const _periods = [(7, '7 j'), (30, '30 j'), (null, 'Tout')];
  int period = 1;

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    final currency = state.me?.currency ?? 'XOF';
    final days = _periods[period].$1;
    return VPage(
      children: [
        const VTopBar('Mon bilan'),
        VSeg(
          items: [for (final p in _periods) p.$2],
          selected: period,
          onSelect: (i) => setState(() => period = i),
        ),
        Loader<Json>(
          key: ValueKey(days),
          load: () async =>
              await state.api.get(days == null ? '/me/record' : '/me/record?days=$days') as Json,
          builder: (context, data, reload) => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: _content(data, currency, days),
          ),
        ),
      ],
    );
  }

  List<Widget> _content(Json data, String currency, int? days) {
    final bets = data['bets'] as Json;
    if ((bets['settled'] as int) == 0) {
      return [
        VCard(
          child: Text(
            (bets['open'] as int) > 0
                ? 'Aucun pari réglé sur cette période : ton bilan apparaîtra après les matchs.'
                : 'Aucun pari réglé sur cette période. Place des paris fictifs pour voir ton bilan.',
            style: V.t(13.5, color: V.mu),
          ),
        ),
      ];
    }
    final bands = (data['calibration'] as List).cast<Json>();
    final best = bands.where((b) => b['enough'] == true).toList()
      ..sort((a, b) => (b['selections'] as int).compareTo(a['selections'] as int));
    final minBand = data['min_band'] as int;
    return [
      if (data['rising'] == true)
        VCard(
          border: V.amber.withValues(alpha: 0.45),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'JEU RESPONSABLE',
                style: V.t(10.5, w: FontWeight.w700, color: V.amber, ls: 0.8),
              ),
              const SizedBox(height: 6),
              Text(
                'Tes mises de la semaine (${money(data['stakes_7d'] as int, currency)}) ont au moins doublé '
                'par rapport à la semaine d\'avant (${money(data['stakes_prev_7d'] as int, currency)}). '
                'Même en argent fictif, garde la tête froide : Moi → Jeu responsable.',
                style: V.t(13, color: V.tx),
              ),
            ],
          ),
        ),
      _Result(data: data, currency: currency),
      _Breakdown(
        'Annoncé contre réalisé',
        'Marché',
        (data['by_market'] as List).cast<Json>(),
        (k) => marketTitle(k),
        minBand,
        footer: 'Couleur seulement si l\'écart dépasse le hasard ($minBand sélections au moins).',
      ),
      _Breakdown(
        'Par championnat',
        'Championnat',
        (data['by_competition'] as List).cast<Json>(),
        competitionName,
        minBand,
      ),
      if (((data['by_odds'] as List?) ?? const []).isNotEmpty)
        _ByOdds((data['by_odds'] as List).cast<Json>(), currency),
      VCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const VKicker('Par niveau de chance'),
            if (best.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                'Tes sélections annoncées autour de ${percent((best.first['announced'] as num).toDouble())} '
                'ont gagné ${percent((best.first['observed'] as num).toDouble())} du temps.',
                style: V.b(13.5),
              ),
            ],
            if (bands.isEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  'Pas encore de sélection réglée avec une probabilité du moteur.',
                  style: V.t(13, color: V.mu),
                ),
              ),
            for (final b in bands) _Band(b, minBand),
          ],
        ),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(4, 12, 4, 0),
        child: Text(
          'Réalisé : sélections gagnées (demi-gains compris) sur gagnées + perdues ; remboursées à part. '
          'Annoncé : chance moyenne donnée par le moteur au moment du pari. Selon la cote : 1 / cote '
          '(marge du bookmaker comprise). Argent fictif : aucun gain réel.',
          style: V.t(11.5, color: V.mu2),
        ),
      ),
    ];
  }
}

/// Carte « Résultat » de la maquette 21 : gain ou perte en grand, misé et rendement à droite,
/// une barre par jour (7 j), par semaine (30 j) ou par mois (Tout), menthe ou corail.
class _Result extends StatelessWidget {
  const _Result({required this.data, required this.currency});
  final Json data;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final bets = data['bets'] as Json;
    final profit = data['profit'] as int;
    final yield_ = (data['yield'] as num?)?.toDouble();
    final bars = ((data['bars'] as List?) ?? const []).cast<int>();
    final top = bars.fold<int>(1, (m, v) => v.abs() > m ? v.abs() : m);
    final settled = bets['settled'] as int;
    // Même règle que Mes paris (rapport du 10/11/2026 : « −48,1 % » après 3 paris).
    final yieldText = yield_ == null
        ? null
        : settled >= 20
        ? 'rendement ${yield_ >= 0 ? '+' : '−'}${percent(yield_.abs(), decimals: 1)}'
        : 'rendement : $settled paris sur 20';
    final parts = [
      '$settled pari${settled > 1 ? 's' : ''} réglé${settled > 1 ? 's' : ''}',
      '${bets['won']} gagné${(bets['won'] as int) > 1 ? 's' : ''}',
      if (bets['push'] as int > 0) '${bets['push']} remboursé${(bets['push'] as int) > 1 ? 's' : ''}',
      if (bets['partial'] as int > 0)
        '${bets['partial']} en partie gagné${(bets['partial'] as int) > 1 ? 's' : ''}',
      if (bets['open'] as int > 0)
        '${bets['open']} en cours non compté${(bets['open'] as int) > 1 ? 's' : ''}',
    ];
    return VCard(
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
                    const VKicker('Résultat'),
                    FittedBox(
                      fit: BoxFit.scaleDown,
                      child: Text(
                        signedMoney(profit, currency),
                        style: V.big(profit > 0 ? V.mint : (profit < 0 ? V.coral : V.tx)),
                      ),
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  const SizedBox(height: 14),
                  Text('misé ${money(data['staked'] as int, currency)}', style: V.mu_(12)),
                  if (yieldText != null) Text(yieldText, style: V.mu_(12)),
                ],
              ),
            ],
          ),
          if (bars.any((v) => v != 0)) ...[
            const SizedBox(height: 14),
            SizedBox(
              height: 64,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  for (final (i, v) in bars.indexed) ...[
                    if (i > 0) const SizedBox(width: 6),
                    Expanded(
                      child: Container(
                        height: v == 0 ? 3 : 8 + 56 * v.abs() / top,
                        decoration: BoxDecoration(
                          color: v > 0 ? V.mint : (v < 0 ? V.coral : V.s3),
                          borderRadius: BorderRadius.circular(6),
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
          const SizedBox(height: 10),
          Text(parts.join(' · '), style: V.mu_(12)),
        ],
      ),
    );
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
    Widget cell(String label, String value, {Color color = V.tx}) => Expanded(
      child: Column(
        children: [
          Text(value, style: V.b(15, color)),
          Text(label, style: V.mu_(11)),
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
            style: V.t(12.5, color: V.mu),
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              cell('annoncé', percent(v('announced')), color: V.vi2),
              cell('selon la cote', percent(v('implied')), color: V.mu),
              cell('réalisé', percent(v('observed')), color: enough ? V.tx : V.mu2),
            ],
          ),
          if (!enough)
            Text(
              'Moins de $minBand sélections : l\'écart vient surtout du hasard.',
              textAlign: TextAlign.center,
              style: V.t(11, color: V.amber),
            ),
        ],
      ),
    );
  }
}

/// Par marché ou par championnat, avec la chance annoncée par le moteur à côté du réalisé
/// (maquette docs/maquettes/11-bilan-annonce, validée le 17/11/2026).
class _Breakdown extends StatelessWidget {
  const _Breakdown(this.title, this.column, this.rows, this.label, this.minBand, {this.footer});
  final String title;

  /// En-tête de la première colonne (« Marché », « Championnat »).
  final String column;
  final String? footer;
  final List<Json> rows;
  final String Function(String) label;
  final int minBand;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) return const SizedBox.shrink();
    Widget head(String t, double w) => SizedBox(
      width: w,
      child: Text(t, textAlign: TextAlign.right, style: V.mu_(11)),
    );
    return VCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          VKicker(title),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(child: Text(column, style: V.mu_(11))),
              head('sél.', 34),
              head('annoncé', 62),
              head('réalisé', 56),
            ],
          ),
          for (final r in rows) ...[
            const Divider(height: 1, thickness: 1, color: V.line),
            _BreakdownRow(r, label(r['key'] as String), minBand),
          ],
          if (footer != null) ...[
            const Divider(height: 1, thickness: 1, color: V.line),
            const SizedBox(height: 8),
            Text(footer!, style: V.mu_(11.5)),
          ],
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
      'low' => V.coral,
      'high' => V.mint,
      _ => V.tx,
    };
    // Petit échantillon et grand écart : on prévient que c'est surtout le hasard.
    final fewButFar =
        gap == null &&
        graded < minBand &&
        rate != null &&
        announced != null &&
        (rate - announced).abs() >= 0.15;
    final note = switch (gap) {
      'low' => ('Bien en dessous de l\'annoncé', V.coral),
      'high' => ('Bien au-dessus de l\'annoncé', V.mint),
      _ when fewButFar => ('Moins de $minBand sélections : l\'écart vient surtout du hasard.', V.amber),
      _ => null,
    };
    Widget cell(String t, double w, TextStyle style) => SizedBox(
      width: w,
      child: Text(t, textAlign: TextAlign.right, style: style),
    );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 9),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: V.t(13.5)),
                if (note != null) Text(note.$1, style: V.t(11.5, color: note.$2)),
              ],
            ),
          ),
          cell('$total', 34, V.b(13)),
          cell(announced == null ? '—' : percent(announced), 62, V.b(13)),
          cell(rate == null ? '—' : percent(rate), 56, V.b(13, color)),
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
      style: V.t(12.5, color: color ?? V.tx, w: bold ? FontWeight.w700 : FontWeight.w400),
    );
    return VCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const VKicker('Par cote du coupon'),
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
                    cell(h, align: i == 0 ? TextAlign.left : TextAlign.right, color: V.mu),
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
                        color: (r['profit'] as int) >= 0 ? V.mint : V.coral,
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
            style: V.mu_(11),
          ),
        ],
      ),
    );
  }
}
