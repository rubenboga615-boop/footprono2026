import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/api/models.dart';
import 'package:footprono/screens/live_tab.dart';
import 'package:footprono/widgets/live_chances.dart';

Json sel(int match, String result, String state, double p, {String market = '1X2', String s = 'home'}) => {
  'match_id': match,
  'market': market,
  'line': '',
  'selection': s,
  'odds': '1.90',
  'model_probability': p,
  'result': result,
  'state': state,
};

Bet bet(List<Json> sels) => Bet({
  'id': 57,
  'kind': 'combo',
  'stake': 1000,
  'currency': 'XOF',
  'total_odds': '3.32',
  'potential_payout': 3320,
  'status': 'open',
  'selections': sels,
});

void main() {
  test('chance du coupon : au départ, puis avec le direct (maquette D7)', () {
    final b = bet([
      sel(1, 'pending', 'live', 0.5),
      sel(2, 'win', 'live', 0.6, market: 'HT_OU', s: 'under'),
      sel(3, 'pending', 'upcoming', 0.4),
    ]);
    final live = {
      1: {
        'markets': {'1X2||home': 0.8},
      },
    };
    final (start, now) = couponChances(b, live)!;
    expect(start, closeTo(0.5 * 0.6 * 0.4, 1e-9));
    expect(now, closeTo(0.8 * 1 * 0.4, 1e-9));
  });

  test('chance du coupon : rien sans chance du moment ou après une sélection perdue', () {
    expect(couponChances(bet([sel(1, 'pending', 'live', 0.5)]), {}), isNull);
    expect(couponChances(bet([sel(1, 'loss', 'live', 0.5), sel(3, 'pending', 'upcoming', 0.4)]), {}), isNull);
  });

  test('chronologie : score après chaque but, mi-temps, remplacement dans le bon sens', () {
    final rows = timeline(
      [
        {'minute': 10, 'side': 'away', 'kind': 'Goal', 'detail': 'Own Goal', 'player': 'Défenseur'},
        {'minute': 30, 'side': 'home', 'kind': 'Goal', 'detail': 'Missed Penalty', 'player': 'Tireur'},
        {'minute': 60, 'side': 'home', 'kind': 'subst', 'player': 'Entrant', 'assist': 'Titulaire'},
        {'minute': 70, 'side': 'away', 'kind': 'Var', 'detail': 'Goal cancelled', 'player': 'Buteur'},
        {'minute': 80, 'side': 'home', 'kind': 'Card', 'detail': 'Red Card', 'player': 'Expulsé'},
      ],
      {'Titulaire'},
    );
    expect(rows.map((r) => r.halfTime ?? '${r.icon} ${r.main}${r.score == null ? '' : ' ${r.score}'}'), [
      '⚽ Défenseur 0-1',
      '❌ Tireur',
      '0-1',
      '🔁 Titulaire → Entrant',
      '📺 VAR : but refusé',
      '🟥 Expulsé',
    ]);
    expect(rows.first.more, 'contre son camp');
    // Score réel 1-0 : le but contre son camp était compté pour l'autre camp.
    final fixed = timeline(
      [
        {'minute': 10, 'side': 'away', 'kind': 'Goal', 'detail': 'Own Goal', 'player': 'Défenseur'},
      ],
      {},
      score: (1, 0),
    );
    expect(fixed.single.score, '1-0');
  });

  test('statistiques écrites à la française', () {
    expect(statText('58%'), '58\u00a0%');
    expect(statText('1.62'), '1,62');
    expect(statText(null), '0');
    expect(statValue('44%'), 44);
  });
}
