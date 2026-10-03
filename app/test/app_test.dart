import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/api/client.dart';
import 'package:footprono/format.dart';
import 'package:footprono/desktop/desktop_shell.dart';
import 'package:footprono/main.dart';
import 'package:footprono/screens/notifications_screen.dart';
import 'package:footprono/state/app_state.dart';
import 'package:footprono/theme.dart';
import 'package:footprono/update/installer.dart';
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
  final List<Map<String, String>> teamQueries = [];
  int latestBuild = 50;
  bool deleted = false;
  int minimumBuild = 0;

  static const smartSel = {
    'match_id': 7,
    'home': 'Lens',
    'away': 'Lyon',
    'home_team_id': 1,
    'away_team_id': 2,
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
    'referee': null,
    'api_referee': 'Stuart Attwell',
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
            'opening_odds': '2.040',
            'opened_at': '2026-09-30T07:30:00Z',
            'source_updated_at': '2026-09-20T17:09:14Z',
            'checked_at': '2026-10-09T08:00:00Z',
          },
          {
            'market': 'OU',
            'line': '2.5',
            'selection': 'over',
            'odds': '1.950',
            'bookmaker': '1xBet',
            'label': 'Goals Over/Under — Over 2.5',
            'fetched_at': '2026-10-09T08:00:00Z',
            'model_probability': 0.52,
            'model_fair_odds': 1.923,
          },
        ];
      case 'GET /matches/7/picks':
        Map<String, dynamic> pick(String label, bool locked, Map<String, dynamic>? sel) => {
          'label': label,
          'range': [0.6, 0.75],
          'locked': locked,
          'selection': sel,
        };
        body = {
          'match_id': 7,
          'picks': {
            'sur': pick('Sûr', false, null),
            'equilibre': pick('Équilibré', !premium, premium ? smartSel : null),
            'audacieux': pick('Audacieux', !premium, null),
          },
        };
      case 'GET /matches/7/odds-history':
        body = {
          'market': '1X2',
          'line': null,
          'selection': 'home',
          'bookmaker': '1xBet',
          'label': 'Match Winner — Home',
          'points': [
            {'at': '2026-09-30T07:30:00Z', 'odds': '2.040'},
            {'at': '2026-10-01T16:30:00Z', 'odds': '1.980'},
            {'at': '2026-10-02T07:30:00Z', 'odds': '1.850'},
          ],
          'last_seen_at': '2026-10-09T08:00:00Z',
        };
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
          'sha256': 'abc123',
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
      case 'GET /competitions':
        body = [
          {
            'code': 'LIGUE_1',
            'name': 'Ligue 1',
            'country': 'France',
            'n_teams': 18,
            'seasons': [
              {'start_year': 2025, 'label': '2025-26', 'matches': 306, 'finished': 306},
              {'start_year': 2026, 'label': '2026-27', 'matches': 306, 'finished': 0},
            ],
          },
        ];
      case 'GET /competitions/LIGUE_1/seasons/2025/merited':
        Map<String, dynamic> row(
          int rank,
          int? xrank,
          int id,
          String name,
          int pts,
          double? xpts,
          String? v,
        ) => {
          'rank': rank,
          'merited_rank': xrank,
          'team': {'id': id, 'name': name},
          'played': 34,
          'points': pts,
          'goals_for': 50,
          'goals_against': 40,
          'xpts': xpts,
          'xg_for': 48.0,
          'xg_against': 41.0,
          'luck': xpts == null ? null : double.parse((pts - xpts).toStringAsFixed(1)),
          'verdict': v,
        };
        body = {
          'competition': 'LIGUE_1',
          'season': 2025,
          'luck_threshold': 3.0,
          'complete': true,
          'table': [
            row(1, 1, 9, 'Paris SG', 76, 73.3, 'fair'),
            row(2, 3, 3, 'Rennes', 59, 44.6, 'lucky'),
            row(3, 2, 4, 'Nantes', 24, 36.3, 'unlucky'),
          ],
        };
      case _ when path.startsWith('/teams/') && path.endsWith('/profile'):
        teamQueries.add(r.url.queryParameters);
        Map<String, dynamic> venue(int n, int pts) => {
          'matches': n,
          'points': pts,
          'goals_for': 2.41,
          'goals_against': 1.18,
          'xg_for': premium ? 1.95 : null,
          'xg_against': premium ? 1.27 : null,
          'xpts': premium ? 32.9 : null,
          'ppda': premium ? 10.8 : null,
          'deep': premium ? 9.1 : null,
          'shots_on_target': premium ? 6.4 : null,
          'corners': premium ? 5.6 : null,
          'yellow_cards': premium ? 2.2 : null,
          'possession': premium ? 57.8 : null,
          'saves': null,
          'pass_pct': premium ? 87.4 : null,
        };
        body = {
          'team': {'id': 1, 'name': 'Lens'},
          'competition': 'LIGUE_1',
          'season': 2025,
          'seasons': [
            {'competition': 'LIGUE_1', 'season': 2026, 'played': 3},
            {'competition': 'LIGUE_1', 'season': 2025, 'played': 34},
          ],
          'form': [
            {
              'match_id': 1,
              'date': '2026-09-27',
              'competition': 'LIGUE_1',
              'venue': 'away',
              'opponent': 'Monaco',
              'score': '0-2',
              'result': 'W',
            },
          ],
          'venues': {'home': venue(17, 37), 'away': venue(17, 22), 'all': venue(34, 59)},
          'locked': !premium,
        };
      case 'GET /referees/profile':
        Map<String, dynamic> summary(int n, double y, bool enough) => {
          'matches': n,
          'yellow': y,
          'red': 0.12,
          'home_yellow': 1.8,
          'away_yellow': y - 1.8,
          'league_yellow': 3.75,
          'league_red': 0.1,
          'enough': enough,
        };
        body = {
          'name': 'Stuart Attwell',
          'min_matches': 15,
          'total': summary(197, 4.6, true),
          'seasons': [
            {'competition': 'LIGUE_1', 'season': 2026, ...summary(3, 5.67, false)},
            {'competition': 'LIGUE_1', 'season': 2025, ...summary(25, 4.6, true)},
          ],
          'recent': [
            {
              'match_id': 1,
              'date': '2026-09-27',
              'competition': 'LIGUE_1',
              'home': 'Lens',
              'away': 'Monaco',
              'home_yellow': 2,
              'away_yellow': 3,
              'red': 1,
            },
          ],
        };
      case 'GET /competitions/LIGUE_1/seasons/2025/referees':
        Map<String, dynamic> ref(String name, int n, double y) => {
          'name': name,
          'matches': n,
          'yellow': y,
          'red': 0.1,
          'home_yellow': y / 2,
          'away_yellow': y / 2,
          'league_yellow': 3.75,
          'league_red': 0.1,
          'enough': n >= 15,
        };
        body = {
          'competition': 'LIGUE_1',
          'season': 2025,
          'matches': 306,
          'league_yellow': 3.75,
          'league_red': 0.1,
          'min_matches': 15,
          'without_referee': 4,
          'referees': [
            ref('Stuart Attwell', 25, 4.6),
            ref('Craig Pawson', 20, 2.67),
            ref('Tim Kirk', 6, 2.5),
          ],
        };
      case 'GET /bets':
        body = [];
      case 'GET /me/wallet/entries':
        body = [];
      case 'GET /me/record':
        Map<String, dynamic> band(double low, int n, double a, double imp, double obs) => {
          'low': low,
          'high': low + 0.1,
          'selections': n,
          'announced': a,
          'implied': imp,
          'observed': obs,
          'enough': n >= 20,
        };
        body = {
          'bets': {'settled': 26, 'open': 1, 'won': 16, 'lost': 10, 'push': 0, 'partial': 0},
          'staked': 30000,
          'returned': 33000,
          'profit': 3000,
          'yield': 0.1,
          'by_market': [
            {'key': '1X2', 'won': 15, 'lost': 10, 'push': 0, 'rate': 0.6},
          ],
          'by_competition': [
            {'key': 'LIGUE_1', 'won': 16, 'lost': 10, 'push': 1, 'rate': 0.6154},
          ],
          'calibration': [band(0.6, 25, 0.65, 0.625, 0.6), band(0.5, 1, 0.55, 0.5, 1.0)],
          'min_band': 20,
          'stakes_7d': 40000,
          'stakes_prev_7d': 10000,
          'rising': true,
          'by_odds': [
            {'low': 1.0, 'high': 2.0, 'bets': 18, 'won': 11, 'announced': 0.62, 'profit': 3200},
            {'low': 20.0, 'high': null, 'bets': 12, 'won': 0, 'announced': 0.03, 'profit': -12000},
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

/// Faux installateur : téléchargement simulé, autorisation et installation enregistrées.
class FakeInstaller implements ApkInstaller {
  FakeInstaller({this.allowed = true, this.fail = false});
  bool allowed;
  bool fail;
  int downloads = 0;
  int settingsOpened = 0;
  final installed = <String>[];
  String? sha;

  @override
  Future<String> download(
    http.Client client,
    Uri url, {
    required int build,
    required String sha256,
    required void Function(double progress) onProgress,
  }) async {
    downloads++;
    sha = sha256;
    if (fail) throw Exception('connexion coupée');
    onProgress(0.5);
    onProgress(1);
    return '/cache/updates/footprono-$build.apk';
  }

  @override
  Future<bool> canInstall() async => allowed;
  @override
  Future<void> openSettings() async => settingsOpened++;
  @override
  Future<void> install(String path) async => installed.add(path);
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
  ApkInstaller? installer,
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
    installer: installer,
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
    expect(find.text("conditions d'utilisation"), findsOneWidget);
    expect(find.text('politique de confidentialité'), findsOneWidget);
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

  testWidgets('fiche équipe gratuite : forme et buts, statistiques avancées verrouillées', (tester) async {
    await startApp(tester, loggedIn: true);
    await tester.tap(find.text('LEN'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Fiche équipe').first);
    await tester.pumpAndSettle();
    expect(find.text('Forme · 5 derniers matchs'), findsOneWidget);
    expect(find.text('chez Monaco'), findsOneWidget);
    expect(find.text('2,41'), findsOneWidget);
    expect(find.text('Statistiques avancées'), findsNothing);
    expect(find.text('Premium'), findsOneWidget);

    await tester.tap(find.text('Extérieur'));
    await tester.pumpAndSettle();
    expect(find.text('22'), findsOneWidget); // points à l'extérieur
  });

  testWidgets('fiche équipe Premium, classement mérité, retour sur une fiche', (tester) async {
    final (_, server) = await startApp(tester, loggedIn: true, premium: true);
    await tester.binding.setSurfaceSize(const Size(430, 2400)); // fiche entière à l'écran
    await tester.tap(find.text('LEN'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Fiche équipe').first);
    await tester.pumpAndSettle();
    expect(find.text('Statistiques avancées'), findsOneWidget);
    expect(find.text('1,95'), findsOneWidget); // xG créés
    expect(find.text('57,8 %'), findsOneWidget);
    expect(find.text('—'), findsOneWidget); // arrêts : donnée absente, pas 0
    expect(find.textContaining('Marque plus que ses xG'), findsOneWidget);

    await tester.tap(find.byTooltip('Classement mérité'));
    await tester.pumpAndSettle();
    expect(find.text('+14,4'), findsOneWidget);
    expect(find.text('−12,3'), findsOneWidget);
    expect(find.text('+2,7'), findsOneWidget);

    await tester.tap(find.textContaining('Rennes', findRichText: true));
    await tester.pumpAndSettle();
    expect(server.teamQueries.last, {'competition': 'LIGUE_1', 'season': '2025'});
  });

  testWidgets('classement mérité depuis les matchs : saison terminée la plus récente', (tester) async {
    await startApp(tester, loggedIn: true);
    await tester.tap(find.byTooltip('Classement mérité'));
    await tester.pumpAndSettle();
    expect(find.text('2025-26'), findsOneWidget);
    expect(find.text('2026-27'), findsNothing); // aucun match terminé
    expect(find.text('+14,4'), findsOneWidget);
  });

  testWidgets('fiche arbitre : sévérité jugée seulement avec assez de matchs, classement', (tester) async {
    await startApp(tester, loggedIn: true);
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    await tester.tap(find.text('LEN'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Arbitre : Stuart Attwell'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Seulement 3 matchs : pas assez pour juger'), findsOneWidget);
    expect(find.text('Plus sévère que la moyenne : +0,85 jaune par match.'), findsOneWidget);
    expect(find.text('2 + 3 J · 1 R'), findsOneWidget);

    await tester.tap(find.byTooltip('Tous les arbitres'));
    await tester.pumpAndSettle();
    expect(find.text('Craig Pawson'), findsOneWidget);
    expect(find.text('MOINS DE 15 MATCHS (NON CLASSÉS)'), findsOneWidget);
    expect(find.text('Tim Kirk'), findsOneWidget);
    expect(find.textContaining('4 matchs de cette saison sans arbitre connu'), findsOneWidget);
  });

  testWidgets('Mon bilan : rendement, annoncé contre réalisé, rappel de jeu responsable', (tester) async {
    await startApp(tester, loggedIn: true);
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    await tester.tap(find.text('Bookmaker'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Mon bilan'));
    await tester.pumpAndSettle();
    expect(find.text(signedMoney(3000)), findsOneWidget);
    expect(
      find.text('Tes sélections annoncées autour de 65$nbsp% ont gagné 60$nbsp% du temps.'),
      findsOneWidget,
    );
    expect(find.textContaining('Moins de 20 sélections'), findsOneWidget);
    expect(find.textContaining('ont au moins doublé'), findsOneWidget);
    expect(find.text('Résultat du match'), findsOneWidget);
    expect(find.text('Ligue 1'), findsOneWidget);
    expect(find.text('Par cote du coupon'), findsOneWidget);
    expect(find.text('20 et plus'), findsOneWidget);
    expect(find.text('−12${nbsp}000'), findsOneWidget);
  });

  testWidgets('mouvement des cotes : ouverture affichée, historique des relevés', (tester) async {
    await startApp(tester, loggedIn: true);
    await tester.tap(find.text('LEN'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cotes'));
    await tester.pumpAndSettle();
    expect(find.textContaining('mises à jour le'), findsOneWidget);
    expect(find.textContaining('pas mis ces cotes à jour depuis plus de 2 jours'), findsOneWidget);
    await tester.tap(find.text('▼ 2,04 → 1,85 · historique'));
    await tester.pumpAndSettle();
    expect(find.text('La cote est passée de 2,04 à 1,85 (2 changements).'), findsOneWidget);
    expect(find.text('1,98'), findsOneWidget);
  });

  testWidgets('Grosse cote : cote visée envoyée, risque affiché, exclusion d\'une équipe, partage', (
    tester,
  ) async {
    final (state, server) = await startApp(tester, loggedIn: true, premium: true);
    await tester.binding.setSurfaceSize(const Size(430, 2600));
    await tester.tap(find.text('Coupon'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coupon intelligent'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Grosse cote'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('25'));
    await tester.tap(find.text('Après 18 h'));
    await tester.tap(find.text('Composer le coupon'));
    await tester.pumpAndSettle();
    expect(server.smartQueries.last, {
      'profile': 'grosse',
      'period': 'next',
      'size': '12',
      'target_odds': '25',
      'after_hour': '18',
    });
    expect(find.textContaining('1 chance sur 2'), findsOneWidget); // probabilité 0,62
    expect(find.textContaining('Coupon à gros risque'), findsOneWidget);

    await tester.tap(find.byTooltip('Exclure'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Toujours exclure Lens'));
    await tester.pumpAndSettle();
    expect(state.excludedTeams, {1: 'Lens'});
    expect(server.smartQueries.last['exclude_teams'], '1');

    await tester.tap(find.text("Partager l'image").first);
    await tester.pumpAndSettle();
    expect(find.text('Chances du moteur'), findsOneWidget);
    expect(
      find.text('Probabilités calculées par FootProno. Argent fictif : aucun gain réel.'),
      findsOneWidget,
    );
  });

  testWidgets('match : choix du moteur, deux sélections du même match à départager', (tester) async {
    final (state, _) = await startApp(tester, loggedIn: true);
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    await tester.tap(find.text('LEN'));
    await tester.pumpAndSettle();
    expect(find.text('Les choix du moteur'), findsOneWidget);
    expect(find.text('Aucune sélection dans cette tranche'), findsOneWidget); // Sûr
    expect(find.text('Avec Premium'), findsNWidgets(2));

    await tester.tap(find.text('1,85').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cotes'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('1,95').first);
    await tester.pumpAndSettle();
    expect(find.text('Déjà une sélection de ce match'), findsOneWidget);
    await tester.tap(find.textContaining('Remplacer par'));
    await tester.pumpAndSettle();
    expect(state.coupon.single.offer.key, 'OU|2.5|over');
  });

  testWidgets('coupon : 12 sélections au maximum', (tester) async {
    expect(AppState.maxCoupon, 12);
  });

  testWidgets('Premium retiré : cadenas affiché, jamais « pas encore d\'analyse »', (tester) async {
    final (state, server) = await startApp(tester, loggedIn: true, premium: true);
    server.premium = false; // retiré côté serveur, l'application ne le sait pas encore
    await tester.tap(find.text('LEN'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Analyse'));
    await tester.pumpAndSettle();
    expect(find.text("Pas encore d'analyse pour ce match."), findsNothing);
    expect(find.textContaining("L'analyse détaillée"), findsOneWidget);
    expect(state.premium, isFalse); // profil relu
  });

  testWidgets('fenêtre moyenne : colonne centrée de 680 pixels, téléphone inchangé', (tester) async {
    await startApp(tester, loggedIn: true); // 430 pixels de large : téléphone
    expect(tester.getSize(find.byType(Navigator).first).width, 430);
    await tester.binding.setSurfaceSize(const Size(1000, 900));
    await tester.pumpAndSettle();
    expect(find.text('LEN'), findsOneWidget);
    expect(tester.getSize(find.byType(Navigator).first).width, WideFrame.maxWidth - 2); // bordures
  });

  testWidgets('ordinateur : menu à gauche, tableau des matchs, coupon à droite, recherche', (tester) async {
    final (state, _) = await startApp(tester, loggedIn: true);
    await tester.binding.setSurfaceSize(const Size(1440, 900));
    tester.view
      ..physicalSize = const Size(1440, 900)
      ..devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpAndSettle();
    expect(find.byType(DesktopShell), findsOneWidget);
    expect(find.text('Fiabilité du moteur'), findsOneWidget); // menu
    expect(find.text('Les deux\nmarquent'), findsOneWidget); // en-tête du tableau
    expect(find.text('57$nbsp%'), findsWidgets);
    expect(find.text('Miser sur ce coupon'), findsNothing); // coupon vide

    // Un match s'ouvre dans la zone centrale ; le menu et le coupon restent.
    await tester.tap(find.text('LEN'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('1,85').first);
    await tester.pumpAndSettle();
    expect(state.coupon, hasLength(1));
    expect(find.text('Miser sur ce coupon'), findsOneWidget);
    expect(find.text('Fiabilité du moteur'), findsOneWidget);

    // Ctrl K : recherche d'un match par son équipe, sans accent ni majuscule.
    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.keyK);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'lens');
    await tester.pumpAndSettle();
    expect(find.text('Fiche équipe'), findsWidgets);

    // Une rubrique du menu remplace la zone centrale.
    await tester.tapAt(const Offset(5, 5)); // ferme la recherche
    await tester.pumpAndSettle();
    await tester.tap(find.text('Mon bilan'));
    await tester.pumpAndSettle();
    expect(find.text('Tes paris fictifs réglés, visibles par toi seul.'), findsOneWidget);
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
    await tester.ensureVisible(find.text('Composer le coupon'));
    await tester.tap(find.text('Composer le coupon'));
    await tester.pumpAndSettle();
    expect(server.smartQueries.single, {'profile': 'equilibre', 'period': 'weekend', 'size': '3'});
    expect(find.text('Victoire Lens'), findsOneWidget);
    expect(find.text('• Forme (5 derniers) : Lens VNDVV, Lyon DNVVN'), findsOneWidget);

    await tester.ensureVisible(find.text('Mettre dans mon coupon'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Mettre dans mon coupon'));
    await tester.pumpAndSettle();
    expect(state.coupon.single.offer.key, '1X2||home');

    await tester.fling(find.byType(ListView).last, const Offset(0, 3000), 3000); // retour en haut
    await tester.pumpAndSettle();
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

  testWidgets('nouvelle version : téléchargée dans l\'application, installateur ouvert', (tester) async {
    final installer = FakeInstaller();
    await startApp(tester, loggedIn: true, build: 41, installer: installer);
    expect(find.text('Nouvelle version disponible'), findsOneWidget);
    expect(find.textContaining('Coupon intelligent amélioré.'), findsOneWidget);
    expect(find.textContaining('20 Mo'), findsOneWidget);
    await tester.tap(find.text('Mettre à jour'));
    await tester.pumpAndSettle();
    expect(installer.sha, 'abc123'); // empreinte publiée par le serveur, vérifiée au téléchargement
    expect(installer.installed, ['/cache/updates/footprono-50.apk']);
    expect(find.text('Nouvelle version disponible'), findsNothing);
    expect(find.text('Téléchargement'), findsNothing);
  });

  testWidgets('mise à jour : autorisation demandée une fois, sans retélécharger', (tester) async {
    final installer = FakeInstaller(allowed: false);
    await startApp(tester, loggedIn: true, build: 41, installer: installer);
    await tester.tap(find.text('Mettre à jour'));
    await tester.pumpAndSettle();
    expect(installer.settingsOpened, 1);
    expect(find.text('Autorisation nécessaire'), findsOneWidget);
    installer.allowed = true; // l'utilisateur a activé le réglage
    await tester.tap(find.text('Installer'));
    await tester.pumpAndSettle();
    expect(installer.downloads, 1);
    expect(installer.installed, hasLength(1));
  });

  testWidgets('mise à jour : échec annoncé, navigateur en secours', (tester) async {
    final installer = FakeInstaller(fail: true);
    final opened = <Uri>[];
    await startApp(
      tester,
      loggedIn: true,
      build: 41,
      installer: installer,
      openUrl: (url) async {
        opened.add(url);
        return true;
      },
    );
    await tester.tap(find.text('Mettre à jour'));
    await tester.pumpAndSettle();
    expect(find.text('Téléchargement impossible'), findsOneWidget);
    expect(installer.installed, isEmpty);
    await tester.tap(find.text('Par le navigateur'));
    await tester.pumpAndSettle();
    expect(opened.single.path, '/api/v1/app/download');
  });

  testWidgets('version à jour : rien n\'est proposé', (tester) async {
    await startApp(tester, loggedIn: true, build: 50);
    expect(find.text('Nouvelle version disponible'), findsNothing);
  });

  testWidgets('suppression du compte : mot de passe redemandé, puis retour à la connexion', (tester) async {
    final opened = <Uri>[];
    final (state, server) = await startApp(
      tester,
      loggedIn: true,
      openUrl: (url) async {
        opened.add(url);
        return true;
      },
    );
    await tester.tap(find.text('Profil'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Confidentialité'), 200);
    await tester.tap(find.text('Confidentialité'));
    expect(opened.single.path, '/confidentialite');
    // Au-dessus de la barre de navigation flottante.
    await tester.scrollUntilVisible(find.text('Se déconnecter'), 200);
    await tester.pumpAndSettle();
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
