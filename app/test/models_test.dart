import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/api/models.dart';
import 'package:footprono/labels.dart';

Map<String, dynamic> _sel(String market, String sel, double p) => {
  'market': market,
  'line': null,
  'selection': sel,
  'probability': p,
  'half_win': 0,
  'push': 0,
  'half_loss': 0,
  'fair_odds': 1 / p,
};

void main() {
  test('pronostic de coupe : sans plus/moins 2,5 ni buts attendus', () {
    final s = Summary({
      'run_id': 1,
      'engine_version': 'coupes 1.0',
      'created_at': '2026-11-20T08:00:00Z',
      'expected_goals': null,
      'home': _sel('1X2', 'home', 0.5),
      'draw': _sel('1X2', 'draw', 0.25),
      'away': _sel('1X2', 'away', 0.25),
      'over_2_5': null,
      'both_score': _sel('BTTS', 'yes', 0.55),
    });
    expect(s.over25, isNull);
    expect(s.xgHome, isNull);
    expect(s.btts!.probability, 0.55);
    expect(competitionName('UCL'), 'Ligue des Champions');
    expect(competitionName('srb'), 'Super Liga serbe');
  });

  test('pronostic de championnat : tout est lu', () {
    final s = Summary({
      'expected_goals': {'home': 1.6, 'away': 0.9},
      'home': _sel('1X2', 'home', 0.5),
      'draw': _sel('1X2', 'draw', 0.25),
      'away': _sel('1X2', 'away', 0.25),
      'over_2_5': _sel('OU', 'over', 0.52),
      'both_score': null,
    });
    expect(s.over25!.probability, 0.52);
    expect(s.xgHome, 1.6);
    expect(s.btts, isNull);
  });
}
