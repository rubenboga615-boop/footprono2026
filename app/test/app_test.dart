import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/api/client.dart';
import 'package:footprono/format.dart';
import 'package:footprono/main.dart';
import 'package:footprono/screens/notifications_screen.dart';
import 'package:footprono/state/app_state.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Faux serveur FootProno : mêmes formes de réponse que l'API réelle.
class FakeServer {
  FakeServer({this.premium = false});
  bool premium;
  final List<Map<String, dynamic>> placedBets = [];
  final List<String> devices = [];
  String paymentStatus = 'pending';
  final List<Map<String, String>> smartQueries = [];
  int latestBuild = 50;
  bool deleted = false;
  int minimumBuild = 0;

  static const smartSel = {
    'match_id': 7,
    'home': 'Lens',
    'away': 'Lyon',
    'competition': 'LIGUE_1',
    'kickoff_at': '2026-10-10T19:00:00Z',
    'market': '1X2',
    'line': null,
    'selection': 'home',
    'odds': '1.850',
    'bookmaker': '1xBet',
    'model_probability': 0.62,
    'reasons': ['Forme (5 derniers) : Lens VNDVV, Lyon DNVVN'],
  };

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
      case 'POST /payments/premium':
        return http.Response(
          jsonEncode({
            'id': 1,
            'status': 'pending',
            'payment_url': 'https://checkout.cinetpay.com/payment/abc',
          }),
          201,
          headers: {'content-type': 'application/json'},
        );
      case 'GET /payments/1':
        if (paymentStatus == 'accepted') premium = true;
        body = {'id': 1, 'status': paymentStatus};
      case 'POST /me/devices':
        devices.add((jsonDecode(r.body) as Map)['token'] as String);
        return http.Response('', 204);
      case 'POST /me/devices/remove':
        devices.remove((jsonDecode(r.body) as Map)['token']);
        return http.Response('', 204);
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
      case 'POST /me/delete':
        if ((jsonDecode(r.body) as Map)['password'] != 'motdepasse') {
          return _error(401, 'unauthorized', 'mot de passe incorrect');
        }
        deleted = true;
        return http.Response('', 204);
      case 'GET /app/version':
        body = {
          'build': latestBuild,
          'minimum_build': minimumBuild,
          'notes': 'Coupon intelligent amélioré.',
          'size': 19500000,
          'sha256': 'x',
          'published_at': '2026-10-02T12:00:00Z',
          'download_path': '/api/v1/app/download',
        };
      case 'GET /smart-coupon':
        if (!premium) return _error(403, 'premium_required', 'réservé à Premium');
        smartQueries.add(r.url.queryParameters);
        body = {
          'profile': 'equilibre',
          'period': '3days',
          'coupon': {
            'selections': [smartSel],
            'total_odds': '1.85',
            'probability': 0.62,
            'implied_probability': 0.5405,
          },
          'alternatives': [],
          'message': null,
        };
      case 'GET /smart-coupons/history':
        body = {
          'stats': {
            'sur': {'label': 'Sûr', 'settled': 0, 'won': 0, 'announced': null, 'observed': null},
            'equilibre': {'label': 'Équilibré', 'settled': 1, 'won': 1, 'announced': 0.62, 'observed': 1.0},
          },
          'coupons': [
            {
              'id': 1,
              'day': '2026-10-10',
              'profile': 'equilibre',
              'profile_label': 'Équilibré',
              'selections': [
                {...smartSel, 'result': 'win'},
              ],
              'total_odds': '1.85',
              'probability': 0.62,
              'status': 'won',
              'settled_at': '2026-10-10T21:00:00Z',
            },
          ],
        };
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

class FakePush implements PushBridge {
  final refresh = StreamController<String>.broadcast();
  final tapped = StreamController<void>.broadcast();
  final received = StreamController<PushMessage>.broadcast();
  String? current = 'jeton-telephone-1';

  @override
  Future<String?> token() async => current;
  @override
  Stream<String> get tokenRefresh => refresh.stream;
  @override
  Stream<void> get opened => tapped.stream;
  @override
  Future<bool> openedAtLaunch() async => false;
  @override
  Stream<PushMessage> get foreground => received.stream;
}

Future<(AppState, FakeServer)> startApp(
  WidgetTester tester, {
  bool premium = false,
  bool loggedIn = false,
  PushBridge? push,
  int build = 0,
  UrlOpener? openUrl,
}) async {
  SharedPreferences.setMockInitialValues(loggedIn ? {'token': 'jeton'} : {});
  final server = FakeServer(premium: premium);
  final state = AppState(
    api: ApiClient(baseUrl: 'http://serveur', httpClient: MockClient(server.handle)),
    socketFactory: (_) => null,
    push: push,
    build: build,
    android: build > 0,
    openUrl: openUrl,
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

  testWidgets('notifications push : téléphone enregistré, notification touchée, déconnexion', (tester) async {
    final push = FakePush();
    final (state, server) = await startApp(tester, loggedIn: true, push: push);
    expect(server.devices, ['jeton-telephone-1']);

    push.refresh.add('jeton-telephone-2');
    await tester.pumpAndSettle();
    expect(server.devices, ['jeton-telephone-1', 'jeton-telephone-2']);

    push.received.add((text: 'FootProno — Notification d\'essai', kind: 'test'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('FootProno — Notification d\'essai'), findsOneWidget);
    await tester.pumpAndSettle(const Duration(seconds: 5));

    push.tapped.add(null);
    await tester.pumpAndSettle();
    expect(find.byType(NotificationsScreen), findsOneWidget);
    Navigator.of(tester.element(find.byType(NotificationsScreen))).pop();
    await tester.pumpAndSettle();

    await state.logout();
    await tester.pumpAndSettle();
    expect(server.devices, ['jeton-telephone-1']);
  });

  testWidgets('notifications refusées : rien n\'est enregistré', (tester) async {
    final push = FakePush()..current = null;
    final (_, server) = await startApp(tester, loggedIn: true, push: push);
    expect(server.devices, isEmpty);
  });

  testWidgets('Premium : paiement ouvert dans le navigateur, vérifié au retour', (tester) async {
    SharedPreferences.setMockInitialValues({'token': 'jeton'});
    final server = FakeServer();
    final opened = <Uri>[];
    final state = AppState(
      api: ApiClient(baseUrl: 'http://serveur', httpClient: MockClient(server.handle)),
      socketFactory: (_) => null,
      openUrl: (url) async {
        opened.add(url);
        return true;
      },
    );
    await tester.binding.setSurfaceSize(const Size(430, 1400));
    await tester.pumpWidget(FootPronoApp(state: state));
    await state.init();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Profil'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.textContaining('Passer Premium'), 200);
    await tester.tap(find.textContaining('Passer Premium'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Ce paiement est réel'), findsOneWidget);
    await tester.tap(find.text('Payer'));
    await tester.pumpAndSettle();
    expect(opened.single.toString(), 'https://checkout.cinetpay.com/payment/abc');

    // Retour dans l'application avant confirmation : en attente.
    state.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.textContaining('en attente de confirmation'), findsOneWidget);
    await tester.pumpAndSettle(const Duration(seconds: 5));

    server.paymentStatus = 'accepted';
    state.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(find.text('Paiement reçu : Premium est activé.'), findsOneWidget);
    expect(state.premium, isTrue);
    expect(state.pendingPayment, isNull);
  });

  testWidgets('Coupon intelligent : profil et période choisis, coupon expliqué, ajouté au coupon', (
    tester,
  ) async {
    final (state, server) = await startApp(tester, loggedIn: true, premium: true);
    await tester.tap(find.text('Coupon'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coupon intelligent'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ce week-end'));
    await tester.tap(find.text('Composer le coupon'));
    await tester.pumpAndSettle();
    expect(server.smartQueries.single, {'profile': 'equilibre', 'period': 'weekend', 'size': '3'});
    expect(find.text('Victoire Lens'), findsOneWidget);
    expect(find.text('• Forme (5 derniers) : Lens VNDVV, Lyon DNVVN'), findsOneWidget);

    await tester.tap(find.text('Mettre dans mon coupon'));
    await tester.pumpAndSettle();
    expect(state.coupon.single.offer.key, '1X2||home');

    await tester.tap(find.byTooltip('Coupons du jour'));
    await tester.pumpAndSettle();
    expect(find.text('Gagné'), findsWidgets);
    expect(find.textContaining('1 gagné(s) sur 1'), findsOneWidget);
  });

  testWidgets('Coupon intelligent : réservé à Premium', (tester) async {
    await startApp(tester, loggedIn: true);
    await tester.tap(find.text('Coupon'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coupon intelligent'));
    await tester.pumpAndSettle();
    expect(find.textContaining('inclus dans Premium'), findsOneWidget);
    expect(find.text('Composer le coupon'), findsNothing);
  });

  testWidgets('nouvelle version : proposée, téléchargée depuis le serveur', (tester) async {
    final opened = <Uri>[];
    await startApp(
      tester,
      loggedIn: true,
      build: 41,
      openUrl: (url) async {
        opened.add(url);
        return true;
      },
    );
    expect(find.text('Nouvelle version disponible'), findsOneWidget);
    expect(find.textContaining('Coupon intelligent amélioré.'), findsOneWidget);
    expect(find.textContaining('20 Mo'), findsOneWidget);
    await tester.tap(find.text('Mettre à jour'));
    await tester.pumpAndSettle();
    expect(opened.single.path, '/api/v1/app/download');
    expect(find.text('Nouvelle version disponible'), findsNothing);
  });

  testWidgets('version à jour : rien n\'est proposé', (tester) async {
    await startApp(tester, loggedIn: true, build: 50);
    expect(find.text('Nouvelle version disponible'), findsNothing);
  });

  testWidgets('suppression du compte : mot de passe redemandé, puis retour à la connexion', (tester) async {
    final (state, server) = await startApp(tester, loggedIn: true);
    await tester.tap(find.text('Profil'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Supprimer mon compte'), 200);
    await tester.tap(find.text('Supprimer mon compte'));
    await tester.pumpAndSettle();
    expect(find.textContaining('ne peut pas être annulée'), findsOneWidget);

    await tester.enterText(find.byType(TextField).last, 'mauvais');
    await tester.tap(find.text('Supprimer définitivement'));
    await tester.pumpAndSettle();
    expect(find.text('mot de passe incorrect'), findsOneWidget);
    expect(server.deleted, isFalse);

    await tester.enterText(find.byType(TextField).last, 'motdepasse');
    await tester.tap(find.text('Supprimer définitivement'));
    await tester.pumpAndSettle();
    expect(server.deleted, isTrue);
    expect(state.me, isNull);
    expect(find.text('Se connecter'), findsOneWidget);
  });
}
