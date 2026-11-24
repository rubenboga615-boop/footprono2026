import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/labels.dart';
import 'package:footprono/theme.dart';
import 'package:footprono/widgets/engine_vs_odds.dart';

/// Étape A du nouveau visage (20/11/2026) : une seule pastille « moteur contre cote ».
void main() {
  Future<Text> badge(WidgetTester tester, double engine, double implied, {bool nation = false}) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: GapBadge(engine: engine, implied: implied, nation: nation),
        ),
      ),
    );
    return tester.widget<Text>(find.byType(Text));
  }

  testWidgets('au-dessus, à égalité, en dessous', (tester) async {
    var t = await badge(tester, 0.59, 0.50);
    expect(t.data, '+9 pts');
    expect(find.byIcon(Icons.arrow_drop_up_rounded), findsOneWidget);
    expect(t.style!.color, Fp.warning); // prudence, jamais une raison de jouer (24/11)
    t = await badge(tester, 0.62, 0.64);
    expect(t.data, 'cote');
    expect(t.style!.color, Fp.muted);
    t = await badge(tester, 0.41, 0.53);
    expect(t.data, '−12 pts');
    expect(find.byIcon(Icons.arrow_drop_down_rounded), findsOneWidget);
    expect(t.style!.color, Fp.muted);
  });

  testWidgets('sélections nationales : un écart en faveur du moteur reste en prudence', (tester) async {
    final t = await badge(tester, 0.62, 0.41, nation: true);
    expect(t.data, '+21 pts');
    expect(t.style!.color, Fp.warning);
  });

  test('seuils : 3 points', () {
    expect(oddsSide(0.53, 0.50), OddsSide.above);
    expect(oddsSide(0.52, 0.50), OddsSide.agree);
    expect(oddsSide(0.48, 0.50), OddsSide.agree);
    expect(oddsSide(0.47, 0.50), OddsSide.below);
  });

  test('mention des chances non mesurées : coupes d\'Europe et sélections (24/11/2026)', () {
    expect(unmeasuredNote('EPL'), isNull);
    expect(unmeasuredNote('UCL'), contains('coupe d\'Europe'));
    expect(unmeasuredNote('uel'), contains('coupe d\'Europe'));
  });
}
