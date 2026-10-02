import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/labels.dart';

void main() {
  String? ah(String line, String sel) =>
      explainSelection('AH', line, sel, home: 'Real Madrid', away: 'Villarreal');

  test('handicap asiatique expliqué simplement', () {
    // Ligne côté domicile −2,25 : Villarreal reçoit +2,25.
    expect(
      ah('-2.25', 'away'),
      'Gagné si Villarreal gagne, fait match nul ou perd d\'un seul but. '
      'Villarreal perd de 2 buts : moitié gagnée, moitié remboursée. Sinon perdu.',
    );
    expect(
      ah('-2.25', 'home'),
      'Gagné si Real Madrid gagne de 3 buts ou plus. '
      'Real Madrid gagne de 2 buts : moitié perdue, moitié remboursée. Sinon perdu.',
    );
    expect(ah('0', 'home'), 'Gagné si Real Madrid gagne. Match nul : mise remboursée. Sinon perdu.');
    expect(ah('-1.5', 'home'), 'Gagné si Real Madrid gagne de 2 buts ou plus. Sinon perdu.');
    expect(
      ah('1', 'home'),
      'Gagné si Real Madrid gagne ou fait match nul. '
      'Real Madrid perd d\'un but : mise remboursée. Sinon perdu.',
    );
  });

  test('handicap européen et remboursé si nul', () {
    expect(
      explainSelection('EH', '-3', 'away', home: 'Racing', away: 'Valencia'),
      'Gagné si Valencia ne perd pas de 3 buts ou plus. Sinon perdu.',
    );
    expect(
      explainSelection('EH', '-1', 'draw', home: 'Racing', away: 'Valencia'),
      'Gagné seulement si Racing gagne d\'un but.',
    );
    expect(
      explainSelection('DNB', '', 'home', home: 'Lens'),
      'Gagné si Lens gagne. Match nul : mise remboursée.',
    );
    expect(explainSelection('OU', '2.5', 'over'), isNull);
  });
}
