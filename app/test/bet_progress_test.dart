import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/api/models.dart';
import 'package:footprono/labels.dart';
import 'package:footprono/screens/bookmaker_screen.dart';

Json _sel(int id, String result, String state, {int? minute, List<int>? score, String? now}) => {
  'match_id': id,
  'market': 'TEAM_OU_AWAY',
  'line': '1.5',
  'selection': 'under',
  'odds': '1.75',
  'bookmaker': '1xBet',
  'result': result,
  'home_team': 'Silkeborg',
  'away_team': 'Lyngby',
  'kickoff_at': '2026-11-07T15:00:00Z',
  'state': state,
  'minute': minute,
  'score': score,
  'now': now,
};

void main() {
  test('combiné en cours : sélections validées au fil des matchs, comme chez un bookmaker', () {
    final bet = Bet({
      'id': 19,
      'kind': 'combo',
      'stake': 5000,
      'currency': 'XOF',
      'total_odds': '5.25',
      'potential_payout': 26230,
      'status': 'open',
      'outcome': null,
      'payout': null,
      'placed_at': '2026-11-05T01:53:00Z',
      'montante_step_id': null,
      'selections': [
        _sel(1, 'win', 'settled', score: [0, 1]),
        _sel(2, 'win', 'settled', score: [2, 0]),
        _sel(3, 'pending', 'live', minute: 67, score: [1, 1], now: 'win'),
        _sel(4, 'pending', 'upcoming'),
      ],
    });
    expect(betProgress(bet), '2 sur 4 validées · 1 en cours · 1 à venir');
    final live = bet.selections[2];
    expect(selectionState(live), "En direct 67' · 1-1 · gagnante pour l'instant");
    expect(selectionState(bet.selections[0]), endsWith('gagné · 0-1'));
    expect(selectionState(bet.selections[3]), endsWith('à venir'));
    expect(selectionState(bet.selections[3]), contains('7 nov.'));
  });

  test('marché par équipe toujours nommé', () {
    expect(
      fullLabel('TEAM_OU_AWAY', '1.5', 'under', home: 'Silkeborg', away: 'Lyngby'),
      'Buts de Lyngby · Moins de 1,5 but',
    );
  });
}
