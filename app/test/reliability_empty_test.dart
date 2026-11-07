import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/api/client.dart';
import 'package:footprono/screens/reliability_screen.dart';
import 'package:footprono/state/app_state.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

void main() {
  // Réponse réelle du serveur sur une base neuve (parcours e2e du 07/11/2026) : aucun match
  // réglé, pas de détail par tranche ; la page plantait (écran gris) au lieu de s'afficher.
  testWidgets('fiabilité sans aucun match réglé : la page s\'affiche', (tester) async {
    final body = File('test/data/reliability_no_matches.json').readAsStringSync();
    final api = ApiClient(
      baseUrl: 'http://x',
      httpClient: MockClient((r) async => http.Response.bytes(utf8.encode(body), 200)),
    );
    final state = AppState(api: api);
    await tester.binding.setSurfaceSize(const Size(430, 1400));
    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: state,
        child: const MaterialApp(home: ReliabilityScreen()),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.textContaining('Simulation'), findsWidgets);
  });
}
