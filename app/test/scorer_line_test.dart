import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/screens/match_screen.dart' show scorerLine;

void main() {
  test('buteurs sous le score : domicile puis extérieur, penalty manqué exclu', () {
    expect(scorerLine([]), isNull);
    expect(
      scorerLine([
        {'minute': 23, 'side': 'home', 'kind': 'Goal', 'detail': 'Normal Goal', 'player': 'Calvert-Lewin'},
        {'minute': 30, 'side': 'away', 'kind': 'Goal', 'detail': 'Missed Penalty', 'player': 'X'},
        {'minute': 45, 'extra': 2, 'side': 'away', 'kind': 'Goal', 'detail': 'Own Goal', 'player': 'Ampadu'},
        {'minute': 58, 'side': 'home', 'kind': 'Goal', 'detail': 'Penalty', 'player': 'Gnonto'},
        {'minute': 60, 'side': 'home', 'kind': 'Card', 'detail': 'Yellow Card', 'player': 'Y'},
      ]),
      "⚽ Calvert-Lewin 23', Gnonto 58' · Ampadu (csc) 45+2'",
    );
  });
}
