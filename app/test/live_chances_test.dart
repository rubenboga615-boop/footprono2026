import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/api/models.dart';
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
}
