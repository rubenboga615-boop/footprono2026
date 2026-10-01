import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/api/client.dart';
import 'package:footprono/format.dart';
import 'package:footprono/main.dart';
import 'package:footprono/state/app_state.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Faux serveur FootProno : mêmes formes de réponse que l'API réelle.
class FakeServer {
  FakeServer({this.premium = false});
  bool premium;
  final List<Map<String, dynamic>> placedBets = [];

  static const team1 = {'id': 1, 'name': 'Lens', 'country': 'France'};
  static const team2 = {'id': 2, 'name': 'Lyon', 'country': 'France'};
  static final match = {
    'id': 7,
    'competition': 'LIGUE_1',
    'season': 2026,
    'match_date': '2026-10-10',
    'kickoff_time': '19:00:00',
    'kickoff_at': '2026-10-10T19:00:00Z',
    'status': 'scheduled',
    'api_status': 'NS',
    'home_team': team1,
    'away_team': team2,
    'home_goals': null,
    'away_goals': null,
    'result_source': null,
    'live_minute': null,
    'live_home_goals': null,
    'live_away_goals': null,
  };

  static Map<String, dynamic> sel(String market, String? line, String s, double p) => {
    'market': market,
    'line': line,
    'selection': s,
    'probability': p,
    'half_win': 0.0,
    'push': 0.0,
    'half_loss': 0.0,
    'fair_odds': 1 / p,
  };

  Map<String, dynamic> get me => {
    'id': 1,
    'phone': '+22997000000',
    'display_name': 'Kossi',
    'country': 'BJ',
    'currency': 'XOF',
    'created_at': '2026-09-30T10:00:00Z',
    'role': 'user',
    'plan': {
      'name': premium ? 'premium' : 'free',
      'premium_until': premium ? '2026-10-07T10:00:00Z' : null,
      'days_left': premium ? 6 : 0,
      'free_markets': ['1X2', 'BTTS', 'OU'],
      'premium_price': 2000,
      'premium_currency': 'XOF',
    },
    'wallet': {'currency': 'XOF', 'balance': 100000, 'last_refill_at': null},
    'virtual_money': true,
  };

  Future<http.Response> handle(http.Request r) async {
    final path = r.url.path.replaceFirst('/api/v1', '');
    Object? body;
    switch ('${r.method} $path') {
      case 'POST /auth/login':
        final b = jsonDecode(r.body) as Map;
        if (b['password'] != 'motdepasse') {
          return _error(401, 'unauthorized', 'numéro ou mot de passe incorrect');
        }
        body = {'access_token': 'jeton', 'token_type': 'bearer'};
      case 'GET /me':
        if (r.headers['Authorization'] != 'Bearer jeton') {
          return _error(401, 'unauthorized', 'connexion requise');
        }
        body = me;
      case 'GET /me/notifications':
        body = [];
      case 'GET /live':
        body = [];
      case 'GET /montantes':
        body = [];
      case 'GET /predictions/upcoming':
        body = [
          {
            'match': match,
            'prediction': {
              'run_id': 1,
              'engine_version': '2.1',
              'created_at': '2026-10-09T06:00:00Z',
              'expected_goals': {'home': 1.4, 'away': 1.1},
              'home': sel('1X2', null, 'home', 0.41),
              'draw': sel('1X2', null, 'draw', 0.28),
              'away': sel('1X2', null, 'away', 0.31),
              'over_2_5': sel('OU', '2.5', 'over', 0.52),
              'both_score': sel('BTTS', null, 'yes', 0.57),
            },
          },
        ];
      case 'GET /matches/7':
        body = match;
      case 'GET /matches/7/prediction':
        body = {
          'match_id': 7,
          'run_id': 1,
          'engine_version': '2.1',
          'as_of': '2026-10-09',
          'created_at': '2026-10-09T06:00:00Z',
          'expected_goals': {'home': 1.4, 'away': 1.1},
          'markets': [
            sel('1X2', null, 'home', 0.41),
            sel('1X2', null, 'draw', 0.28),
            sel('1X2', null, 'away', 0.31),
            sel('OU', '2.5', 'over', 0.52),
            sel('OU', '2.5', 'under', 0.48),
            if (premium) sel('AH', '-0.25', 'home', 0.47),
          ],
          'counts': premium ? {} : null,
          'context': premium ? {} : null,
          'plan': premium ? 'premium' : 'free',
          'locked_markets': premium ? [] : ['AH', 'CORNERS_OU'],
        };
      case 'GET /matches/7/analysis':
        if (!premium) return _error(403, 'premium_required', 'réservé à Premium');
        Map<String, dynamic> f(String opp, String res) => {
          'match_id': 1,
          'date': '2026-10-01',
          'competition': 'LIGUE_1',
          'venue': 'home',
          'opponent': opp,
          'score': '1-0',
          'result': res,
        };
        Map<String, dynamic> avg() => {
          'matches': 7,
          'goals_for': 1.6,
          'goals_against': 0.9,
          'xg_for': 1.4,
          'xg_against': 1.0,
          'shots_on_target': 5.1,
          'corners': 5.5,
        };
        body = {
          'match_id': 7,
          'form': {
            'home': [f('Nice', 'W'), f('Lille', 'D'), f('Brest', 'L'), f('Nantes', 'W'), f('Lorient', 'W')],
            'away': [f('Metz', 'L'), f('Paris FC', 'D'), f('Lens', 'W'), f('Auxerre', 'W'), f('Angers', 'D')],
          },
          'head_to_head': [
            {
              'match_id': 3,
              'date': '2026-02-01',
              'competition': 'LIGUE_1',
              'home': 'Lyon',
              'away': 'Lens',
              'score': '1-2',
              'winner': 'Lens',
            },
          ],
          'season': {'home': avg(), 'away': avg()},
        };
      case 'GET /matches/7/offer':
        body = [
          {
            'market': '1X2',
            'line': null,
            'selection': 'home',
            'odds': '1.850',
            'bookmaker': '1xBet',
            'label': 'Match Winner — Home',
            'fetched_at': '2026-10-09T08:00:00Z',
            'model_probability': 0.41,
            'model_fair_odds': 2.439,
          },
        ];
      case 'POST /bets':
        final b = jsonDecode(r.body) as Map<String, dynamic>;
        placedBets.add(b);
        return http.Response(jsonEncode({'id': 1}), 201, headers: _json);
      default:
        return _error(404, 'not_found', 'route inconnue ${r.method} $path');
    }
    return http.Response(jsonEncode(body), 200, headers: _json);
  }

  static const _json = {'content-type': 'application/json; charset=utf-8'};

  http.Response _error(int status, String code, String message) => http.Response(
    jsonEncode({
      'error': {'code': code, 'message': message, 'request_id': 'x'},
    }),
    status,
    headers: _json,
  );
}

Future<(AppState, FakeServer)> startApp(
  WidgetTester tester, {
  bool premium = false,
  bool loggedIn = false,
}) async {
  SharedPreferences.setMockInitialValues(loggedIn ? {'token': 'jeton'} : {});
  final server = FakeServer(premium: premium);
  final state = AppState(
    api: ApiClient(baseUrl: 'http://serveur', httpClient: MockClient(server.handle)),
    socketFactory: (_) => null,
  );
  await tester.binding.setSurfaceSize(const Size(430, 1400));
  await tester.pumpWidget(FootPronoApp(state: state));
  await state.init();
  await tester.pumpAndSettle();
  return (state, server);
}

void main() {
  testWidgets('connexion : erreur du serveur affichée, puis accès aux matchs', (tester) async {
    final (state, _) = await startApp(tester);
    expect(find.text('Se connecter'), findsOneWidget);

    await tester.enterText(find.byType(TextField).at(0), '+229 97 00 00 00');
    await tester.enterText(find.byType(TextField).at(1), 'mauvais');
    await tester.tap(find.text('Se connecter'));
    await tester.pumpAndSettle();
    expect(find.text('numéro ou mot de passe incorrect'), findsOneWidget);

    await tester.enterText(find.byType(TextField).at(1), 'motdepasse');
    await tester.tap(find.text('Se connecter'));
    await tester.pumpAndSettle();
    expect(state.me?.displayName, 'Kossi');
    expect(find.text('LEN'), findsOneWidget);
    expect(find.text('1 · 41$nbsp%'), findsOneWidget);
    expect(find.text('Les deux marquent · 57$nbsp%'), findsOneWidget);
  });

  testWidgets('inscription : case 18 ans obligatoire', (tester) async {
    await startApp(tester);
    await tester.tap(find.text('Créer un compte'));
    await tester.pumpAndSettle();
    expect(find.text("J'ai 18 ans ou plus"), findsOneWidget);
    await tester.tap(find.text('Créer mon compte'));
    await tester.pumpAndSettle();
    expect(find.textContaining('18 ans ou plus pour utiliser'), findsOneWidget);
  });

  testWidgets('match : marchés Premium signalés, cote ajoutée au coupon, pari placé', (tester) async {
    final (state, server) = await startApp(tester, loggedIn: true);
    await tester.tap(find.text('LEN'));
    await tester.pumpAndSettle();
    expect(find.text('Résultat du match'), findsOneWidget);
    expect(find.text('41$nbsp%'), findsOneWidget); // tuile Lens
    expect(find.textContaining('2 autres marchés'), findsOneWidget);

    await tester.tap(find.text('1,85').first);
    await tester.pumpAndSettle();
    expect(state.coupon, hasLength(1));

    await tester.tap(find.byTooltip('Retour'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coupon'));
    await tester.pumpAndSettle();
    expect(find.text('Victoire Lens'), findsOneWidget);
    expect(find.text(money(1850)), findsOneWidget); // 1 000 × 1,85

    await tester.tap(find.text('Valider le coupon'));
    await tester.pumpAndSettle();
    expect(server.placedBets, hasLength(1));
    expect(server.placedBets.single['stake'], 1000);
    expect((server.placedBets.single['selections'] as List).single['odds'], '1.850');
    expect(state.coupon, isEmpty);
  });

  testWidgets('Premium : handicap asiatique visible, pas de verrou', (tester) async {
    await startApp(tester, loggedIn: true, premium: true);
    await tester.tap(find.text('LEN'));
    await tester.pumpAndSettle();
    expect(find.text('Handicap asiatique'), findsOneWidget);
    expect(find.text('Lens (−0,25)'), findsOneWidget);
    expect(find.textContaining('autres marchés'), findsNothing);

    await tester.tap(find.text('Analyse'));
    await tester.pumpAndSettle();
    expect(find.text('Forme · 5 derniers matchs'), findsOneWidget);
    expect(find.text('G'), findsNWidgets(5)); // 3 + 2 victoires
    expect(find.text('Moyennes cette saison'), findsOneWidget);
    expect(find.text('Lyon 1-2 Lens'), findsOneWidget);
  });

  testWidgets('version gratuite : analyse verrouillée', (tester) async {
    await startApp(tester, loggedIn: true);
    await tester.tap(find.text('LEN'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Analyse'));
    await tester.pumpAndSettle();
    expect(find.text('Premium'), findsOneWidget);
    expect(find.text('Forme · 5 derniers matchs'), findsNothing);
  });
}
