import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/widgets/common.dart';

void main() {
  test("message d'attente : il change avec le temps", () {
    expect(SlowWait.message(0, 'les matchs'), 'Recherche…');
    expect(SlowWait.message(4, 'les matchs'), 'Le moteur étudie les matchs…');
    expect(SlowWait.message(12, 'les matchs'), startsWith('Encore quelques secondes'));
    expect(SlowWait.message(30, 'les matchs'), startsWith('Le serveur est très occupé'));
  });

  testWidgets("l'attente s'explique à l'écran au fil des secondes", (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: SlowWait())));
    expect(find.text('Recherche…'), findsOneWidget);
    await tester.pump(const Duration(seconds: 5));
    expect(find.text('Le moteur étudie les matchs de la période…'), findsOneWidget);
    await tester.pump(const Duration(seconds: 10));
    expect(find.textContaining('Encore quelques secondes'), findsOneWidget);
  });
}
