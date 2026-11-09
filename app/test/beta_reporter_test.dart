import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/api/client.dart';
import 'package:footprono/state/beta_reporter.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  late List<Map<String, dynamic>> sent;
  late DateTime now;
  late ApiClient api;
  late BetaReporter beta;

  setUp(() {
    sent = [];
    now = DateTime(2026, 11, 6, 12);
    api = ApiClient(
      baseUrl: 'http://test',
      token: 'jeton',
      httpClient: MockClient((r) async {
        final path = r.url.path.replaceFirst('/api/v1', '');
        if (path == BetaReporter.path) {
          sent.addAll(((jsonDecode(r.body) as Map)['events'] as List).cast<Map<String, dynamic>>());
          return http.Response('{"kept": 1}', 200);
        }
        if (path == '/reliability') return http.Response('{"error": {"code": "x"}}', 500);
        if (path == '/bets') return http.Response('{"error": {"code": "odds_changed"}}', 409);
        return http.Response('{}', 200);
      }),
    );
    beta = BetaReporter(api, clock: () => now);
    api.observer = beta.observe;
  });

  test('éteint : rien n\'est gardé ni envoyé', () async {
    await api.get('/smart-coupon', {'profile': 'balanced'});
    expect(beta.pending, isEmpty);
    expect(sent, isEmpty);
  });

  test('allumé : écrans suivis, pannes du serveur, actions ; envois groupés', () async {
    beta.enabled = true;
    await api.get('/smart-coupon?period=day&competitions=EPL');
    await Future<void>.delayed(Duration.zero);
    // Premier événement : envoyé tout de suite, sans les paramètres de l'adresse.
    expect(sent.single['path'], '/smart-coupon');
    expect(sent.single['kind'], 'timing');

    await api.get('/me'); // écran non suivi
    await expectLater(api.get('/reliability'), throwsA(isA<ApiException>()));
    await expectLater(api.post('/bets', {}), throwsA(isA<ApiException>())); // cote changée : normal
    beta.action('coupon_add');
    expect(beta.pending.map((e) => e['kind']), ['error', 'action']);
    expect(beta.pending.first['detail'], 'http_500');

    now = now.add(BetaReporter.every);
    await api.get('/matches/7/offer');
    await Future<void>.delayed(Duration.zero);
    expect(sent.map((e) => e['kind']), ['timing', 'error', 'action', 'timing']);
    expect(beta.pending, isEmpty);
  });

  test('éteint en cours de route : les événements en attente sont oubliés', () async {
    beta.enabled = true;
    await api.get('/montantes');
    await Future<void>.delayed(Duration.zero);
    beta.action('coupon_compose');
    expect(beta.pending, hasLength(1));
    beta.enabled = false;
    expect(beta.pending, isEmpty);
  });

  test('arrière-plan : les requêtes suspendues par le téléphone ne sont pas des pannes', () async {
    beta.enabled = true;
    final timeout = ApiException(0, 'timeout', '');
    beta.background = true;
    beta.observe('/me/bets-summary', const Duration(seconds: 20), timeout);
    // Commencée en arrière-plan, finie après le retour : ignorée aussi.
    beta.background = false;
    now = now.add(const Duration(seconds: 5));
    beta.observe('/me/wallet/entries', const Duration(seconds: 20), timeout);
    expect(beta.pending, isEmpty);
    // Commencée après le retour : comptée.
    beta.observe('/me/wallet/entries', const Duration(seconds: 2), timeout);
    await Future<void>.delayed(Duration.zero);
    expect([...sent, ...beta.pending].map((e) => e['path']), ['/me/wallet/entries']);
  });
}
