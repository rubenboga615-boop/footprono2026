import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/format.dart';
import 'package:footprono/labels.dart';

void main() {
  test('montants en F CFA avec espaces insécables', () {
    expect(money(150582), '150${nbsp}582${nbsp}F${nbsp}CFA');
    expect(money(0), '0${nbsp}F${nbsp}CFA');
    expect(thousands(1000000), '1${nbsp}000${nbsp}000');
    expect(signedMoney(5000), '+5${nbsp}000${nbsp}F${nbsp}CFA');
  });

  test('pourcentages, cotes et lignes à la française', () {
    expect(percent(0.412), '41$nbsp%');
    expect(percent(0.004), '<${nbsp}1$nbsp%');
    expect(percent(0.0332, decimals: 1), '3,3$nbsp%');
    expect(decimal('1.850'), '1,85');
    expect(decimal(2), '2,0');
    expect(decimal('1.625', max: 3), '1,625');
    expect(lineLabel('2.5'), '2,5');
    expect(lineLabel('-0.25'), '−0,25');
    expect(lineLabel('1', signed: true), '+1,0');
  });

  test('dates en français', () {
    final d = DateTime(2026, 10, 10, 21, 5);
    expect(shortDate(d), 'Sam. 10 oct.');
    expect(longDate(d), 'Samedi 10 octobre');
    expect(hourMinute(d), '21:05');
  });

  test('codes d\'équipe', () {
    expect(teamCode('Manchester United'), 'MUN');
    expect(teamCode('Lens'), 'LEN');
  });

  test('libellés des marchés', () {
    const h = 'Lens', a = 'Lyon';
    expect(selectionLabel('1X2', '', 'home', home: h, away: a), 'Victoire Lens');
    expect(selectionLabel('1X2', '', 'draw', home: h, away: a), 'Match nul');
    expect(selectionLabel('DC', '', 'X2', home: h, away: a), 'Nul ou Lyon');
    expect(selectionLabel('OU', '2.5', 'over'), 'Plus de 2,5 buts');
    expect(selectionLabel('OU', '0.5', 'under'), 'Moins de 0,5 but');
    // Handicap asiatique : ligne côté domicile, l'extérieur a la ligne opposée.
    expect(selectionLabel('AH', '-0.25', 'home', home: h, away: a), 'Lens (−0,25)');
    expect(selectionLabel('AH', '-0.25', 'away', home: h, away: a), 'Lyon (+0,25)');
    expect(selectionLabel('CORNERS_OU', '9.5', 'over'), 'Plus de 9,5 corners');
    expect(selectionLabel('MARGIN', '', 'home+4', home: h, away: a), 'Lens de 4 buts ou plus');
    expect(
      selectionLabel('1X2_OU', '2.5', 'home/over', home: h, away: a),
      'Victoire Lens et plus de 2,5 buts',
    );
    expect(fullLabel('BTTS', '', 'yes'), 'Les deux équipes marquent · Oui, les deux marquent');
    expect(marketTitle('CARDS_TEAM_OU_HOME', home: h), 'Cartons de Lens');
    // Chaque marché du moteur a un titre français.
    for (final g in marketGroups) {
      for (final m in g.markets) {
        expect(marketTitle(m), isNot(m), reason: m);
      }
    }
  });

  test('ordre des sélections', () {
    final sels = [('', 'away'), ('', 'home'), ('', 'draw')];
    sels.sort((a, b) => compareSelections(a.$1, a.$2, b.$1, b.$2));
    expect(sels.map((e) => e.$2), ['home', 'draw', 'away']);
    final lines = [('10.5', 'over'), ('9.5', 'under'), ('9.5', 'over')];
    lines.sort((a, b) => compareSelections(a.$1, a.$2, b.$1, b.$2));
    expect(lines, [('9.5', 'over'), ('9.5', 'under'), ('10.5', 'over')]);
  });
}
