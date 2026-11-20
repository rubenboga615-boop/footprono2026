import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/api/client.dart';
import 'package:footprono/api/models.dart';
import 'package:footprono/widgets/live_refresh.dart';
import 'package:footprono/widgets/team_logo.dart';
import 'package:footprono/format.dart';
import 'package:footprono/desktop/desktop_shell.dart';
import 'package:footprono/main.dart';
import 'package:footprono/screens/create_screen.dart' show HomeTab;
import 'package:footprono/screens/daily_coupons_screen.dart';
import 'package:footprono/screens/notifications_screen.dart';
import 'package:footprono/screens/live_coupon_screen.dart';
import 'package:footprono/screens/reliability_screen.dart';
import 'package:footprono/screens/smart_coupon_screen.dart';
import 'package:footprono/state/app_state.dart';
import 'package:footprono/theme.dart';
import 'package:footprono/update/installer.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Faux serveur FootProba : mêmes formes de réponse que l'API réelle.
class FakeServer {
  FakeServer({this.premium = false});
  bool premium;
  final List<Map<String, dynamic>> placedBets = [];
  final List<String> devices = [];
  final List<String> platforms = [];
  String? vapidKey;
  String paymentStatus = 'pending';
  String? boughtWith;
  bool oldServer = false;
  bool oddsAvailable = true;
  Map<String, dynamic>? betsSummary;
  final List<Map<String, String>> smartQueries = [];
  final List<Map<String, String>> teamQueries = [];
  final List<Map<String, dynamic>> bookingCodes = [];
  bool admin = false;
  bool dailyNotifications = true;
  bool montanteMode = false;
  bool compareEngines = false;
  bool montanteFinished = false;
  final List<Map<String, dynamic>> stepBets = [];
  bool betaAvailable = false;
  final extraUpcoming = <Map<String, dynamic>>[];
  final live = <Map<String, dynamic>>[];

  /// Chances en direct (étape 6) : non publiées sauf si un test les donne.
  Map<String, dynamic>? liveChances;

  /// Match 7 tel que renvoyé par /matches/7 (un test peut le mettre en direct).
  Map<String, dynamic>? matchNow;

  /// Onglet « En direct » du match 7 (étape 7) : vide sauf si un test le remplit.
  Map<String, dynamic>? matchLive;

  /// Buts et cartons rouges des matchs en cours (liste des matchs, maquette D1).
  Map<String, dynamic> liveSummary = {};

  /// Paris renvoyés par /bets (vide sauf si un test en donne).
  List<Map<String, dynamic>> bets = [];

  /// GET /montantes et GET /bets/{id} (paris des paliers).
  List<Map<String, dynamic>> montantes = [];
  bool freshPlayer = false; // nouveau joueur : aucun pari réglé (tableau de bord)
  // Tableau de bord « Aujourd'hui » (étape B) : courbe, 30 jours, moteur, mises, au-dessus de la cote.
  Map<String, dynamic> dashboard = {
    'balance': 98000,
    'currency': 'XOF',
    'curve': [
      {'day': '2026-10-01', 'balance': 100000},
      {'day': '2026-10-05', 'balance': 96500},
      {'day': '2026-10-09', 'balance': 98000},
    ],
    'last_30_days': {'settled': 6, 'won': 3, 'staked': 6000, 'returned': 5400, 'yield': -0.1},
    'engine': {'selections': 9, 'announced': 0.61, 'observed': 0.56},
    'stakes': {'week': 3000, 'previous_week': 1000},
    'engine_above_odds': [
      {
        'match_id': 7,
        'kickoff_at': '2026-10-10T19:00:00Z',
        'competition': 'LIGUE_1',
        'home': 'Lens',
        'away': 'Lyon',
        'market': 'OU',
        'line': '2.5',
        'selection': 'under',
        'odds': '2.10',
        'bookmaker': '1xBet',
        'engine': 0.53,
        'implied': 0.4762,
      },
    ],
    'gap_min': 0.03,
    'markets_30': [
      {'key': 'DC', 'won': 10, 'lost': 1, 'push': 0, 'rate': 0.91, 'announced': 0.82, 'gap': 'ok'},
      {'key': 'HT_1X2', 'won': 1, 'lost': 3, 'push': 0, 'rate': 0.25, 'announced': 0.71, 'gap': 'low'},
    ],
    'play_plan': {
      'weekly_budget': 5000,
      'loss_limit': null,
      'max_stake': null,
      'reminder': false,
      'pause_until': null,
      'pending': null,
      'pending_applies_at': null,
      'week': {'start': '2026-10-05T00:00:00Z', 'staked': 3500, 'lost': 0},
    },
  };

  /// Plan de jeu (PUT /me/play-plan) et alertes de cote (maquettes 29 et 30).
  final planUpdates = <Map<String, dynamic>>[];
  final alertCalls = <String>[];
  Map<String, dynamic> oddsAlerts = {
    'alerts': [
      {
        'id': 1,
        'match_id': 7,
        'home': 'Lens',
        'away': 'Lyon',
        'competition': 'LIGUE_1',
        'open': true,
        'market': 'BTTS',
        'line': '',
        'selection': 'yes',
        'label': 'les deux équipes marquent',
        'target_odds': 1.95,
        'start_odds': 1.85,
        'odds': 1.85,
        'engine': 0.58,
        'active': true,
        'triggered_at': null,
      },
    ],
    'gap': {'id': 2, 'min_gap': 0.08, 'active': true},
    'hits': [
      {
        'id': 5,
        'alert_id': 2,
        'match_id': 7,
        'home': 'Lens',
        'away': 'Lyon',
        'open': true,
        'market': 'OU',
        'line': '2.5',
        'selection': 'under',
        'label': 'moins de 2,5 buts',
        'from_odds': 1.79,
        'odds': 1.92,
        'engine': 0.59,
        'implied': 0.5208,
        'at': '2026-10-10T07:12:00Z',
      },
    ],
    'gaps': [0.05, 0.08, 0.1],
  };
  Map<int, Map<String, dynamic>> betsById = {};

  /// Suivi des montantes (M1, M2) et Fiabilité des montantes (M4).
  Map<String, dynamic> montanteSummary = {'montantes': 0};
  Map<String, dynamic>? montanteReliability;
  final notifications = <Map<String, dynamic>>[];
  bool paymentsConfigured = true;
  bool betaSharing = false;
  final betaEvents = <Map<String, dynamic>>[];
  int latestBuild = 50;
  bool deleted = false;
  int minimumBuild = 0;

  /// Connexion Google : comptes Google connus, compte lié, inscriptions reçues.
  final Set<String> googleAccounts = {};
  bool googleLinked = false;
  final List<Map<String, dynamic>> googleSignups = [];

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
    'role': admin ? 'admin' : 'user',
    'plan': {
      'name': premium ? 'premium' : 'free',
      'premium_until': premium ? '2026-10-07T10:00:00Z' : null,
      'days_left': premium ? 6 : 0,
      'free_markets': ['1X2', 'BTTS', 'OU'],
      'premium_price': 2000,
      'premium_currency': 'XOF',
    },
    'wallet': {'currency': 'XOF', 'balance': 100000, 'last_refill_at': null},
    'daily_coupons_notifications': dailyNotifications,
    'montante_mode': montanteMode,
    'compare_engines': compareEngines,
    'virtual_money': true,
    'email': googleLinked ? 'kossi@gmail.com' : null,
    'google_linked': googleLinked,
    'has_password': true,
    'beta_available': betaAvailable,
    'beta_sharing': betaAvailable && betaSharing,
    'beta_tester': betaAvailable && betaSharing ? 3 : null,
  };

  /// Requêtes reçues (« GET /matches/7 »…), pour compter ce que l'application demande.
  final calls = <String>[];

  /// Dernier relevé du direct (GET /live/feed).
  Map<String, dynamic>? liveFeed;

  /// Coupon en direct (GET /live/coupons) ; non publié par défaut.
  Map<String, dynamic>? liveCoupons;

  /// Fiabilité des coupons en direct (GET /live/coupons/reliability) ; non publié par défaut.
  Map<String, dynamic>? liveReliability;

  Future<http.Response> handle(http.Request r) async {
    final path = r.url.path.replaceFirst('/api/v1', '');
    calls.add('${r.method} $path');
    Object? body;
    switch ('${r.method} $path') {
      case 'POST /auth/login':
        final b = jsonDecode(r.body) as Map;
        if (b['password'] != 'motdepasse') {
          return _error(401, 'unauthorized', 'numéro ou mot de passe incorrect');
        }
        body = {'access_token': 'jeton', 'token_type': 'bearer'};
      case 'POST /auth/google':
        final b = jsonDecode(r.body) as Map;
        if (!googleAccounts.contains(b['id_token'])) {
          return http.Response(
            jsonEncode({
              'error': {
                'code': 'google_account_unknown',
                'message': 'pas encore de compte FootProba pour ce compte Google',
                'details': {'email': 'kossi@gmail.com', 'name': 'Kossi Mensah'},
              },
            }),
            404,
            headers: {'content-type': 'application/json'},
          );
        }
        body = {'access_token': 'jeton', 'token_type': 'bearer'};
      case 'POST /auth/google/register':
        final b = (jsonDecode(r.body) as Map).cast<String, dynamic>();
        googleSignups.add(b);
        googleAccounts.add(b['id_token'] as String);
        googleLinked = true;
        return http.Response(
          jsonEncode({'access_token': 'jeton', 'token_type': 'bearer'}),
          201,
          headers: {'content-type': 'application/json'},
        );
      case 'POST /me/google':
        googleLinked = true;
        body = me;
      case 'DELETE /me/google':
        googleLinked = false;
        body = me;
      case 'POST /me/password' || 'POST /me/logout-everywhere':
        body = {'access_token': 'jeton', 'token_type': 'bearer'};
      case 'GET /app/support':
        body = {'whatsapp': '+2250500649904', 'whatsapp_url': 'https://wa.me/2250500649904'};
      case 'GET /me':
        if (r.headers['Authorization'] != 'Bearer jeton') {
          return _error(401, 'unauthorized', 'connexion requise');
        }
        body = me;
      case 'GET /me/notifications':
        body = notifications;
      case 'DELETE /me/notifications':
        notifications.clear();
        return http.Response('', 204);
      case final d when d.startsWith('DELETE /me/notifications/'):
        notifications.removeWhere((n) => '${n['id']}' == d.split('/').last);
        return http.Response('', 204);
      case 'GET /app/status':
        body = {'odds_available': oddsAvailable};
      case 'GET /payments/methods' when oldServer:
        // Ancien serveur : « methods » pris pour un numéro de paiement.
        return _error(422, 'validation_error', 'Requête invalide');
      case 'GET /payments/methods':
        body = {
          'price': 2000,
          'currency': 'XOF',
          'days': 30,
          'methods': [
            if (paymentsConfigured) ...[
              {'id': 'wave', 'label': 'Wave'},
              {'id': 'paystack', 'label': 'Orange Money, MTN, Wave ou carte'},
            ],
          ],
          'manual': paymentsConfigured
              ? {'wave_number': '+2250700000000', 'whatsapp': '+2250500649904'}
              : null,
        };
      case 'POST /payments/premium':
        boughtWith = (jsonDecode(r.body) as Map)['method'] as String?;
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
      case 'PUT /me/beta':
        betaSharing = (jsonDecode(r.body) as Map)['enabled'] as bool;
        body = {'enabled': betaSharing, 'tester': betaSharing ? 3 : null};
      case 'POST /me/beta/events':
        final events = ((jsonDecode(r.body) as Map)['events'] as List).cast<Map<String, dynamic>>();
        betaEvents.addAll(events);
        body = {'kept': events.length};
      case 'PUT /me/preferences':
        final prefs = jsonDecode(r.body) as Map;
        if (prefs['daily_coupons_notifications'] case final bool v) dailyNotifications = v;
        if (prefs['montante_mode'] case final bool v) montanteMode = v;
        if (prefs['compare_engines'] case final bool v) compareEngines = v;
        return http.Response('', 204);
      case 'GET /app/web-push':
        body = {'vapid_key': vapidKey};
      case 'POST /me/devices':
        devices.add((jsonDecode(r.body) as Map)['token'] as String);
        platforms.add((jsonDecode(r.body) as Map)['platform'] as String);
        return http.Response('', 204);
      case 'POST /me/devices/remove':
        devices.remove((jsonDecode(r.body) as Map)['token']);
        return http.Response('', 204);
      case 'GET /live':
        body = live;
      case 'GET /montantes':
        body = montantes;
      case 'GET /me/montantes/summary':
        body = montanteSummary;
      case 'GET /reliability/engines':
        if (!compareEngines) return _error(400, 'bad_request', 'comparaison');
        Map<String, dynamic> e(int n, int won, int profit, double? y) => {
          'settled': n,
          'won': won,
          'profit': profit,
          'yield': y,
        };
        body = {
          'matches': 412,
          'calibrated': 380,
          'log_loss': {'1': 0.983, '2': 0.961},
          'money': [
            {
              'source': 'coupon',
              'label': 'Coupon intelligent',
              'engines': {'1': e(40, 12, -1600, -0.04), '2': e(40, 14, -400, -0.01)},
            },
            {
              'source': 'daily',
              'label': 'Coupons du jour',
              'engines': {'1': e(30, 10, -1800, -0.06), '2': e(30, 11, -600, -0.02)},
            },
            {
              'source': 'montante',
              'label': 'Montante (paliers)',
              'engines': {'1': e(0, 0, 0, null), '2': e(0, 0, 0, null)},
            },
          ],
          'settled': {'1': 70, '2': 70},
          'stake': 1000,
          'enough': false,
          'min_matches': 300,
          'min_proposals': 200,
        };
      case 'GET /reliability/montantes':
        body =
            montanteReliability ??
            {'steps': [], 'finished': 0, 'to_end': 0, 'enough': false, 'min_finished': 30};
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
          ...extraUpcoming,
        ];
      case 'GET /matches/7':
        body = matchNow ?? match;
      case 'GET /matches/7/live':
        body = matchLive ?? {'status': null, 'events': [], 'stats': null, 'lineups': []};
      case 'GET /live/summary':
        body = liveSummary;
      case 'GET /live/coupons/reliability':
        body = liveReliability ?? {'published': false, 'total': 0, 'profiles': {}};
      case 'GET /live/coupons':
        body = liveCoupons ?? {'published': false, 'odds_source': 'indicative', 'matches': [], 'combos': {}};
      case 'GET /live/feed':
        body = liveFeed ?? {'type': 'live', 'at': null, 'matches': []};
      case 'GET /live/chances':
        body = liveChances ?? {'published': false, 'matches': {}};
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
      case 'GET /offers/main':
        expect(r.url.queryParametersAll['match_ids'], ['7']);
        body = {
          '7': [
            {
              'market': '1X2',
              'line': null,
              'selection': 'home',
              'odds': '1.850',
              'bookmaker': '1xBet',
              'label': 'Match Winner — Home',
              'fetched_at': '2026-10-09T08:00:00Z',
              'model_probability': 0.41,
            },
          ],
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
            if (compareEngines) ...{'engine2_probability': 0.45, 'engine2_calibrated': true},
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
      case 'GET /smart-coupon/competitions':
        body = {'LIGUE_1': 1};
      case 'GET /smart-coupon':
        if (!premium) return _error(403, 'premium_required', 'réservé à Premium');
        smartQueries.add(r.url.queryParameters);
        final target = r.url.queryParameters['target_odds'];
        final engine2 = r.url.queryParameters['engine'] == '2';
        if (engine2 && !compareEngines) return _error(400, 'bad_request', 'moteur 2');
        body = {
          'engine': engine2 ? 2 : 1,
          'profile': 'equilibre',
          'profile_label': 'Équilibré',
          'period': '3days',
          // Comme le serveur : cote visée en texte (Grosse cote), sinon la tranche du profil.
          'target_odds': target,
          'range': target == null ? [0.6, 0.75] : null,
          'coupon': {
            'selections': [
              engine2
                  ? {
                      ...smartSel,
                      'market': 'OU',
                      'line': '2.5',
                      'selection': 'over',
                      'odds': '1.950',
                      'model_probability': 0.71,
                    }
                  : smartSel,
            ],
            'total_odds': engine2 ? '1.95' : '1.85',
            'probability': engine2 ? 0.71 : 0.62,
            'implied_probability': 0.5405,
            'best_probability': 0.635,
          },
          'alternatives': [],
          'message': null,
        };
      case 'GET /smart-coupons/day' || 'GET /admin/smart-coupons':
        body = {
          'day': '2026-10-10',
          'coupons': [
            {
              'id': 1,
              'day': '2026-10-10',
              'profile': 'sur',
              'profile_label': 'Sûr',
              'selections': [
                {...smartSel, 'result': 'pending', 'state': 'upcoming'},
              ],
              'total_odds': '1.30',
              'probability': 0.8,
              'status': 'pending',
              'display_status': 'upcoming',
              'validated': 0,
              'first_kickoff': '2026-10-10T19:00:00Z',
              'booking_codes': [],
              'settled_at': null,
            },
            {
              'id': 2,
              'day': '2026-10-10',
              'profile': 'equilibre',
              'profile_label': 'Équilibré',
              'selections': [
                {
                  ...smartSel,
                  'result': 'pending',
                  'state': 'live',
                  'minute': 58,
                  'score': [1, 0],
                },
              ],
              'total_odds': '1.85',
              'probability': 0.62,
              'status': 'pending',
              'display_status': 'live',
              'validated': 0,
              'first_kickoff': '2026-10-10T19:00:00Z',
              'booking_codes': [
                {'bookmaker': '1xbet', 'label': '1xBet', 'code': '7HQ2K'},
              ],
              'settled_at': null,
            },
            {
              'id': 3,
              'day': '2026-10-10',
              'profile': 'audacieux',
              'profile_label': 'Audacieux',
              'selections': [
                {
                  ...smartSel,
                  'result': 'loss',
                  'state': 'settled',
                  'score': [0, 2],
                },
              ],
              'total_odds': '3.10',
              'probability': 0.3,
              'status': 'lost',
              'display_status': 'lost',
              'validated': 0,
              'first_kickoff': '2026-10-10T13:00:00Z',
              'booking_codes': [],
              'settled_at': '2026-10-10T15:00:00Z',
            },
          ],
          'summary': {
            'yesterday': {'settled': 3, 'won': 2},
            'last_30_days': {'settled': 90, 'won': 49},
            'last_30_days_by_profile': {
              'sur': {'label': 'Sûr', 'settled': 30, 'won': 17, 'announced': 0.58, 'observed': 0.5667},
              'equilibre': {
                'label': 'Équilibré',
                'settled': 30,
                'won': 14,
                'announced': 0.45,
                'observed': 0.4667,
              },
              'audacieux': {
                'label': 'Audacieux',
                'settled': 30,
                'won': 8,
                'announced': 0.27,
                'observed': 0.2667,
              },
            },
          },
        };
        // Comme le serveur : sans Premium, ni sélections ni code tant que ce n'est pas réglé.
        if (!premium && r.url.path.endsWith('/smart-coupons/day')) {
          for (final c in ((body as Map)['coupons'] as List).cast<Map<String, dynamic>>()) {
            c['selection_count'] = (c['selections'] as List).length;
            c['locked'] = true;
            c['selections'] = [];
            c['booking_codes'] = [];
          }
        }
        // Mode comparaison (K5) : les coupons du jour du moteur 2, à part.
        if (r.url.queryParameters['engine'] == '2') {
          if (!compareEngines) return _error(400, 'bad_request', 'moteur 2');
          final all = ((body as Map)['coupons'] as List).cast<Map<String, dynamic>>();
          body = {
            'day': '2026-10-10',
            'engine': 2,
            'coupons': [
              {...all[0], 'id': 11, 'total_odds': '1.92', 'probability': 0.6},
            ],
            'summary': {
              'yesterday': {'settled': 0, 'won': 0},
              'last_30_days': {'settled': 4, 'won': 3},
            },
          };
        }
      case 'PUT /admin/smart-coupons/1/booking-code':
        bookingCodes.add((jsonDecode(r.body) as Map).cast<String, dynamic>());
        body = {'day': '2026-10-10', 'coupons': [], 'summary': {}};
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
          'has_more': r.url.queryParameters['offset'] == null,
        };
        if (r.url.queryParameters['offset'] != null) {
          // Page suivante : un coupon plus ancien.
          final older = Map<String, dynamic>.from(((body as Map)['coupons'] as List).first as Map);
          body['coupons'] = [
            {...older, 'id': 2, 'day': '2026-09-01', 'status': 'lost'},
          ];
        }
      case 'GET /reliability':
        Map<String, dynamic> bin(String range, int count, double a, double o) => {
          'range': range,
          'count': count,
          'announced': a,
          'observed': o,
        };
        Map<String, dynamic> market(String key, int n, String? warning) => {
          'market': key,
          'matches': n,
          'warning': warning,
          'log_loss': 0.99,
          'naive_log_loss': 1.07,
          'brier': 0.59,
          'most_likely_hit_rate': 0.5,
          'most_likely_announced': 0.5,
          'calibration': [bin('0,2-0,3', 600, 0.25, 0.26), bin('0,8-0,9', 21, 0.84, 0.71)],
        };
        body = {
          'matches': 550,
          'warning': null,
          'min_bin': 50,
          'markets': [
            market('1X2', 550, null),
            market('OU|2.5', 550, null),
            market('BTTS', 170, 'Seulement 170 matchs sur ce marché : échantillon trop petit pour conclure.'),
          ],
          'versus_closing_odds': [],
          'recent': [],
          'nations_vs_odds': {
            'stake': 1000,
            'matches': 40,
            'bands': [
              {
                'from': 0.05,
                'to': 0.10,
                'selections': 12,
                'engine': 0.61,
                'implied': 0.54,
                'won': 0.58,
                'profit': 900,
              },
              {
                'from': 0.10,
                'to': 0.15,
                'selections': 6,
                'engine': 0.66,
                'implied': 0.54,
                'won': 0.5,
                'profit': -700,
              },
              {
                'from': 0.15,
                'to': null,
                'selections': 0,
                'engine': null,
                'implied': null,
                'won': null,
                'profit': 0,
              },
            ],
          },
          'markets_audit': !{null, 'BIG5'}.contains(r.url.queryParameters['competition'])
              ? null
              : {
                  'matches': 7081,
                  'seasons': '2022-23 à 2025-26',
                  'competitions': '5 grands championnats',
                  'rule': 'Juste : écart de 3 points au plus.',
                  'reference': 'Moyenne du championnat.',
                  'families': [
                    {
                      'id': '1X2',
                      'group': 'Résultat et buts',
                      'label': 'Résultat du match',
                      'skill': 0.079,
                      'max_gap_points': 2.2,
                      'passes_rule': true,
                      'withdrawn': null,
                      'calibration': [bin('0,7-0,8', 538, 0.742, 0.764), bin('0,8-0,9', 21, 0.84, 0.85)],
                    },
                    {
                      'id': 'CORNERS_OU',
                      'group': 'Corners',
                      'label': 'Corners : total',
                      'skill': 0.01,
                      'max_gap_points': 1.8,
                      'passes_rule': true,
                      'withdrawn': null,
                      'calibration': [bin('0,4-0,5', 900, 0.45, 0.43)],
                    },
                    {
                      'id': 'SOT_1X2',
                      'group': 'Tirs',
                      'label': 'Tirs cadrés : le plus de',
                      'skill': 0.095,
                      'max_gap_points': 7.5,
                      'passes_rule': false,
                      'withdrawn': 'Retiré le 06/11/2026.',
                      'calibration': [bin('0,7-0,8', 867, 0.743, 0.818)],
                    },
                  ],
                },
          'backtest': {
            'label': 'Backtest',
            'matches': 7081,
            'seasons': '2022-23 à 2025-26',
            'engine_version': '2.1',
            'log_loss': {
              '1X2': {'model': 0.98, 'naive': 1.07, 'closing_odds': 0.97},
            },
            'calibration_1x2': [],
            'note': 'Simulation.',
          },
        };
      case 'GET /competitions':
        body = [
          {
            'code': 'POR',
            'name': 'Liga Portugal',
            'country': 'Portugal',
            'n_teams': 18,
            'understat_slug': null, // pas de xG : absent du classement mérité
            'seasons': [
              {'start_year': 2026, 'label': '2026-27', 'matches': 306, 'finished': 0},
            ],
          },
          {
            'code': 'LIGUE_1',
            'name': 'Ligue 1',
            'country': 'France',
            'n_teams': 18,
            'understat_slug': 'Ligue_1',
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
      case 'GET /me/bets-summary' when betsSummary != null:
        body = betsSummary;
      case 'GET /bets':
        body = bets;
      case 'GET /me/wallet/entries':
        body = [];
      case 'GET /me/dashboard':
        body = dashboard;
      case final c when c.startsWith('PATCH /me/odds-alerts/') || c.startsWith('DELETE /me/odds-alerts/'):
        alertCalls.add('$c ${r.body}');
        body = {'id': 1};
      case 'GET /me/play-plan':
        body = dashboard['play_plan'];
      case 'PUT /me/play-plan':
        final b = (jsonDecode(r.body) as Map).cast<String, dynamic>();
        planUpdates.add(b);
        body = {...(dashboard['play_plan'] as Map), ...b};
        dashboard = {...dashboard, 'play_plan': body};
      case 'POST /me/play-plan/pause':
        body = {...(dashboard['play_plan'] as Map), 'pause_until': '2026-10-11T08:00:00Z'};
      case 'GET /me/odds-alerts':
        body = oddsAlerts;
      case 'PUT /me/odds-alerts/gap' || 'POST /me/odds-alerts':
        alertCalls.add('${r.method} $path ${r.body}');
        body = {'id': 9};
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
          'bets': freshPlayer
              ? {'settled': 0, 'open': 0, 'won': 0, 'lost': 0, 'push': 0, 'partial': 0}
              : {'settled': 26, 'open': 1, 'won': 16, 'lost': 10, 'push': 0, 'partial': 0},
          'staked': 30000,
          'returned': 33000,
          'profit': 3000,
          'yield': 0.1,
          'by_market': [
            {'key': '1X2', 'won': 15, 'lost': 10, 'push': 0, 'rate': 0.6, 'announced': 0.65, 'gap': null},
            {'key': 'DC', 'won': 19, 'lost': 24, 'push': 0, 'rate': 0.4419, 'announced': 0.71, 'gap': 'low'},
            {'key': 'HT_1X2', 'won': 1, 'lost': 6, 'push': 0, 'rate': 0.1429, 'announced': 0.38, 'gap': null},
          ],
          'by_competition': [
            {
              'key': 'LIGUE_1',
              'won': 16,
              'lost': 10,
              'push': 1,
              'rate': 0.6154,
              'announced': 0.62,
              'gap': null,
            },
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
      case 'GET /montantes/4/suggestions':
        if (montanteFinished) {
          return http.Response(
            jsonEncode({
              'error': {
                'code': 'bad_request',
                'message': 'montante terminée : plus de pari possible, crée une nouvelle montante',
                'details': {'code': 'montante_finished', 'status': 'lost'},
              },
            }),
            400,
            headers: _json,
          );
        }
        final engine2 = r.url.queryParameters['engine'] == '2';
        if (engine2 && !compareEngines) return _error(400, 'bad_request', 'moteur 2');
        Map<String, dynamic> sug(String market, String sel, String odds, double p) => {
          'selections': [
            {
              'match_id': 7,
              'market': market,
              'line': market == 'OU' ? '2.5' : null,
              'selection': sel,
              'odds': odds,
              'bookmaker': '1xBet',
              'label': '',
              'model_probability': p,
            },
          ],
          'total_odds': odds,
          'model_probability': p,
          'implied_probability': 0.6,
          'engine_below_odds': false,
        };
        body = {
          'step': 2,
          'odds_min': '1.60',
          'odds_max': '1.95',
          'stake': 7850,
          'engine': engine2 ? 2 : 1,
          'suggestions': [engine2 ? sug('OU', 'over', '1.950', 0.55) : sug('1X2', 'home', '1.850', 0.62)],
        };
      case 'POST /montantes/4/bet':
        stepBets.add(jsonDecode(r.body) as Map<String, dynamic>);
        return http.Response(jsonEncode({'id': 32}), 201, headers: _json);
      case 'POST /bets':
        final b = jsonDecode(r.body) as Map<String, dynamic>;
        placedBets.add(b);
        return http.Response(jsonEncode({'id': 1}), 201, headers: _json);
      default:
        final id = r.method == 'GET' && path.startsWith('/bets/') ? int.tryParse(path.substring(6)) : null;
        if (betsById[id] case final b?) return http.Response(jsonEncode(b), 200, headers: _json);
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

/// Faux Google : renvoie un jeton (ou null : fenêtre de Google fermée).
class FakeGoogle implements GoogleAuthBridge {
  String? next = 'jeton-google';
  int signOuts = 0;

  @override
  Future<String?> idToken() async => next;

  /// Jeton rendu au démarrage (retour de redirection, version web sur téléphone).
  String? redirect;
  @override
  Future<String?> redirectResult() async {
    final t = redirect;
    redirect = null;
    return t;
  }

  @override
  Future<void> signOut() async => signOuts++;
}

class FakePush implements PushBridge {
  final refresh = StreamController<String>.broadcast();
  final tapped = StreamController<String?>.broadcast();
  final received = StreamController<PushMessage>.broadcast();
  String? current = 'jeton-telephone-1';

  @override
  Future<String?> token() async => current;
  @override
  Stream<String> get tokenRefresh => refresh.stream;
  @override
  Stream<String?> get opened => tapped.stream;
  @override
  Future<bool> openedAtLaunch() async => false;
  @override
  Stream<PushMessage> get foreground => received.stream;
}

class FakeWebPush implements WebPushBridge {
  WebPushStatus start = WebPushStatus.off;
  bool allow = true;
  String? key;

  @override
  Future<WebPushStatus> status(String vapidKey) async {
    key = vapidKey;
    return start;
  }

  @override
  Future<String?> token() async => 'jeton-navigateur-1-xxxxxxxxxxxxxxxxxxxx';
  @override
  Future<String?> enable() async => allow ? token() : null;
  @override
  Stream<PushMessage> get foreground => const Stream.empty();
}

Future<(AppState, FakeServer)> startApp(
  WidgetTester tester, {
  bool premium = false,
  bool loggedIn = false,
  PushBridge? push,
  WebPushBridge? webPush,
  int build = 0,
  UrlOpener? openUrl,
  ApkInstaller? installer,
  GoogleAuthBridge? google,
  bool googleRedirectPending = false,
  bool betaAvailable = false,
  int startTab = HomeTab.matchs,
}) async {
  SharedPreferences.setMockInitialValues({
    if (loggedIn) 'token': 'jeton',
    if (googleRedirectPending) 'google_redirect_pending': true,
  });
  final server = FakeServer(premium: premium)..betaAvailable = betaAvailable;
  final state = AppState(
    api: ApiClient(baseUrl: 'http://serveur', httpClient: MockClient(server.handle)),
    socketFactory: (_) => null,
    push: push,
    webPush: webPush,
    google: google,
    build: build,
    android: build > 0,
    openUrl: openUrl,
    installer: installer,
  );
  await tester.binding.setSurfaceSize(const Size(430, 1400));
  await tester.pumpWidget(FootProbaApp(state: state));
  await state.init();
  await tester.pumpAndSettle();
  // Nouveau visage, étape B : l'application s'ouvre sur « Aujourd'hui » ; les tests des autres
  // écrans partent de la liste des matchs, comme avant.
  if (loggedIn && startTab != HomeTab.today && find.byType(HomeShell).evaluate().isNotEmpty) {
    await tab(tester, startTab);
  }
  return (state, server);
}

/// Ouvre un onglet de la barre du bas (ou Mon coupon, la Montante, ouverts depuis « Créer »).
Future<void> tab(WidgetTester tester, int i) async {
  tester.state<HomeShellState>(find.byType(HomeShell)).go(i);
  await tester.pumpAndSettle();
}

void main() {
  // Matchs du faux serveur le 10/10/2026 à 19:00 : le matin même, aucun n'a commencé.
  setUp(() {
    MatchInfo.now = () => DateTime.utc(2026, 10, 10, 8);
    TeamLogo.enabled = false; // pas d'image à télécharger dans les tests
  });

  testWidgets('connexion : erreur du serveur affichée, puis accès aux matchs', (tester) async {
    final (state, _) = await startApp(tester);
    // Accueil de la maquette du 07/11/2026, puis « J'ai déjà un compte » (sans Google : formulaire).
    expect(find.text('Créer mon compte gratuit'), findsOneWidget);
    await tester.tap(find.text('J\'ai déjà un compte'));
    await tester.pumpAndSettle();
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
    // Nouveau visage, étape B : l'application s'ouvre sur « Aujourd'hui ».
    expect(find.text('Aujourd\'hui'), findsWidgets);
    await tab(tester, HomeTab.matchs);
    expect(find.text('Lyon'), findsOneWidget); // carte du match (nouvelle interface)
    expect(find.text('41$nbsp%'), findsOneWidget);
    expect(find.text('1,85'), findsOneWidget); // cote du bookmaker sous la chance
  });

  testWidgets('inscription : case 18 ans obligatoire', (tester) async {
    await startApp(tester);
    await tester.tap(find.text('Créer mon compte gratuit'));
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
    await tester.tap(find.text('Lens').first);
    await tester.pumpAndSettle();
    expect(find.text('RÉSULTAT DU MATCH'), findsOneWidget);
    expect(find.text('41$nbsp%'), findsOneWidget); // tuile Lens
    expect(find.textContaining('2 autres marchés'), findsOneWidget);

    await tester.tap(find.text('1,85').first);
    await tester.pumpAndSettle();
    expect(state.coupon, hasLength(1));

    await tester.tap(find.byTooltip('Retour'));
    await tester.pumpAndSettle();
    await tab(tester, HomeTab.coupon);
    await tester.pumpAndSettle();
    expect(find.text('Victoire Lens'), findsOneWidget);
    // Maquette C3 : « 1 850 F (+850) », mise comprise puis bénéfice net en vert.
    expect(find.textContaining('Tu récupères si tout passe'), findsOneWidget);
    expect(find.text('1${nbsp}850 F (+850)'), findsOneWidget);

    await tester.ensureVisible(find.text('Placer le pari · 1${nbsp}000 F'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Placer le pari · 1${nbsp}000 F'));
    await tester.pumpAndSettle();
    // Maquette N5 : récapitulatif, puis « Confirmer ».
    expect(find.text('Placer ce pari ?'), findsOneWidget);
    expect(server.placedBets, isEmpty);
    await tester.tap(find.text('Confirmer · 1${nbsp}000 F'));
    await tester.pumpAndSettle();
    expect(server.placedBets, hasLength(1));
    expect(server.placedBets.single['stake'], 1000);
    expect((server.placedBets.single['selections'] as List).single['odds'], '1.850');
    expect(state.coupon, isEmpty);
  });

  testWidgets('coupon : « Vider » demande confirmation', (tester) async {
    final (state, _) = await startApp(tester, loggedIn: true);
    await tester.tap(find.text('Lens').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('1,85').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Retour'));
    await tester.pumpAndSettle();
    await tab(tester, HomeTab.coupon);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Vider'));
    await tester.tap(find.text('Vider'));
    await tester.pumpAndSettle();
    expect(find.text('Vider le coupon ?'), findsOneWidget);
    await tester.tap(find.text('Annuler'));
    await tester.pumpAndSettle();
    expect(state.coupon, hasLength(1));
    await tester.tap(find.text('Vider'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Vider'));
    await tester.pumpAndSettle();
    expect(state.coupon, isEmpty);
  });

  testWidgets('Coupon intelligent : cote visée invalide refusée avec un message, retirer sans remplacer', (
    tester,
  ) async {
    await startApp(tester, loggedIn: true, premium: true);
    await tester.binding.setSurfaceSize(const Size(430, 2600));
    await tab(tester, HomeTab.coupon);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coupon intelligent'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Grosse cote'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Autre…'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'abc');
    await tester.tap(find.text('Valider'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Écris une cote entre 2 et 10'), findsOneWidget); // fenêtre gardée
    // Cote visée de 2 à 10 (plan du 10/11/2026, étape 4).
    await tester.enterText(find.byType(TextField).last, '12,5');
    await tester.tap(find.text('Valider'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Écris une cote entre 2 et 10'), findsOneWidget);
    await tester.enterText(find.byType(TextField).last, '6,5');
    await tester.tap(find.text('Valider'));
    await tester.pumpAndSettle();
    expect(find.text('Autre : 6,5'), findsOneWidget);

    await tester.ensureVisible(find.text('Composer le coupon'));
    await tester.tap(find.text('Composer le coupon'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const ValueKey('change-0')));
    await tester.tap(find.byKey(const ValueKey('change-0'))); // toucher une sélection : la changer
    await tester.pumpAndSettle();
    await tester.tap(find.text('Retirer sans remplacer'));
    await tester.pumpAndSettle();
    expect(find.text('Coupon vide : compose un nouveau coupon.'), findsOneWidget);
  });

  testWidgets('Comparer les deux moteurs : réglage du Profil, fiche de match, deux coupons (K1-K3)', (
    tester,
  ) async {
    final (state, server) = await startApp(tester, loggedIn: true, premium: true);
    await tester.binding.setSurfaceSize(const Size(430, 2600));
    // Éteint : ni moteur 2 sur la fiche, ni deuxième coupon.
    expect(server.compareEngines, isFalse);
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Comparer les deux moteurs'), 200);
    await tester.tap(find.text('Comparer les deux moteurs'));
    await tester.pumpAndSettle();
    expect(server.compareEngines, isTrue);
    expect(state.compareEngines, isTrue);

    // K2 : la fiche de match, moteur 1 et moteur 2 côte à côte.
    await tab(tester, HomeTab.matchs);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Lens').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cotes'));
    await tester.pumpAndSettle();
    expect(find.textContaining('moteur 2 calé', findRichText: true), findsOneWidget);
    expect(find.textContaining('moteur 2 45', findRichText: true), findsWidgets);
    await tester.tap(find.byTooltip('Retour'));
    await tester.pumpAndSettle();

    // K3 : deux coupons, chacun avec son bouton.
    await tab(tester, HomeTab.coupon);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coupon intelligent'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Composer le coupon'));
    await tester.tap(find.text('Composer le coupon'));
    await tester.pumpAndSettle();
    expect(find.text('MOTEUR 1'), findsOneWidget);
    expect(find.text('MOTEUR 2'), findsOneWidget);
    expect(server.smartQueries.where((q) => q['engine'] == '2'), hasLength(1));
    await tester.ensureVisible(find.byKey(const ValueKey('add-engine-2')));
    await tester.tap(find.byKey(const ValueKey('add-engine-2')));
    await tester.pumpAndSettle();
    expect(state.coupon.single.offer.market, 'OU');
    // Le pari placé garde le moteur qui l'a proposé (demande du 18/11/2026).
    expect(state.coupon.single.engine, 2);
    expect(state.couponEngine, 2);
    await tester.tap(find.byTooltip('Retour'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Placer le pari · 1${nbsp}000 F'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Placer le pari · 1${nbsp}000 F'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Confirmer · 1${nbsp}000 F'));
    await tester.pumpAndSettle();
    expect(server.placedBets.single['engine'], 2);

    // Constat du 18/11 : en revenant, les deux coupons sont toujours là…
    await tester.tap(find.text('Coupon intelligent'));
    await tester.pumpAndSettle();
    expect(find.text('MOTEUR 1'), findsOneWidget);
    expect(find.text('MOTEUR 2'), findsOneWidget);
    expect(find.textContaining('Composé à'), findsOneWidget);
    // … et un nouveau coupon écarte les matchs déjà joués (chip pour les remettre).
    server.bets = [
      {
        'id': 90,
        'kind': 'single',
        'stake': 1000,
        'currency': 'XOF',
        'total_odds': '1.95',
        'potential_payout': 1950,
        'status': 'open',
        'selections': [
          {'match_id': 7, 'market': 'OU', 'line': '2.5', 'selection': 'over', 'odds': '1.95'},
        ],
      },
    ];
    server.smartQueries.clear();
    await tester.ensureVisible(find.text('Composer le coupon'));
    await tester.tap(find.text('Composer le coupon'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Réglages')); // les exclusions sont dans les réglages
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('1 match déjà dans tes paris'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('1 match déjà dans tes paris'), findsOneWidget);
  });

  testWidgets('Premium : handicap asiatique visible, pas de verrou', (tester) async {
    await startApp(tester, loggedIn: true, premium: true);
    await tester.tap(find.text('Lens').first);
    await tester.pumpAndSettle();
    // Groupes repliés : seul le premier est ouvert ; « Handicaps » s'ouvre d'un toucher.
    expect(find.text('Handicap asiatique'), findsNothing);
    await tester.tap(find.text('Handicaps'));
    await tester.pumpAndSettle();
    expect(find.text('HANDICAP ASIATIQUE'), findsOneWidget);
    expect(find.text('Lens (−0,25)'), findsOneWidget);
    expect(find.textContaining('autres marchés'), findsNothing);

    await tester.tap(find.text('Analyse'));
    await tester.pumpAndSettle();
    expect(find.text('FORME (5 DERNIERS)'), findsOneWidget);
    // Maquette 9 : « Ce que le moteur en retient » : des faits, aucun avis.
    expect(find.text('Buts attendus par le moteur : Lens 1,4, Lyon 1,1 (2,5 au total).'), findsOneWidget);
    expect(find.text('V'), findsNWidgets(5)); // 3 + 2 victoires
    expect(find.text('MOYENNES CETTE SAISON'), findsOneWidget);
    expect(find.text('Lyon 1-2 Lens'), findsOneWidget);
  });

  testWidgets('version gratuite : analyse verrouillée', (tester) async {
    await startApp(tester, loggedIn: true);
    await tester.tap(find.text('Lens').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Analyse'));
    await tester.pumpAndSettle();
    // Aperçu flouté (structure seulement, aucun chiffre) puis le bouton d'abonnement.
    expect(find.text('Inclus dans Premium'), findsOneWidget);
    expect(find.text('Débloquer · 2${nbsp}000 F pour 30 jours'), findsOneWidget);
    expect(find.text('Forme · 5 derniers matchs'), findsNothing);
  });

  testWidgets('fiche équipe gratuite : forme et buts, statistiques avancées verrouillées', (tester) async {
    await startApp(tester, loggedIn: true);
    await tester.tap(find.text('Lens').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Fiche équipe').first);
    await tester.pumpAndSettle();
    expect(find.text('Forme · 5 derniers matchs'), findsOneWidget);
    expect(find.text('chez Monaco'), findsOneWidget);
    expect(find.text('2,41'), findsOneWidget);
    expect(find.text('Statistiques avancées'), findsNothing);
    expect(find.text('Inclus dans Premium'), findsOneWidget);

    await tester.tap(find.text('Extérieur'));
    await tester.pumpAndSettle();
    expect(find.text('22'), findsOneWidget); // points à l'extérieur
  });

  testWidgets('fiche équipe Premium, classement mérité, retour sur une fiche', (tester) async {
    final (_, server) = await startApp(tester, loggedIn: true, premium: true);
    await tester.binding.setSurfaceSize(const Size(430, 2400)); // fiche entière à l'écran
    await tester.tap(find.text('Lens').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Fiche équipe').first);
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

  testWidgets('classement mérité depuis le profil : saison terminée la plus récente', (tester) async {
    await startApp(tester, loggedIn: true);
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Classement mérité'), 200);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Classement mérité'));
    await tester.pumpAndSettle();
    expect(find.text('2025-26'), findsOneWidget);
    expect(find.text('2026-27'), findsNothing); // aucun match terminé
    expect(find.text('+14,4'), findsOneWidget);
    expect(find.text('Liga Portugal'), findsNothing); // pas de xG : pas de classement mérité
  });

  testWidgets('fiche arbitre : sévérité jugée seulement avec assez de matchs, classement', (tester) async {
    await startApp(tester, loggedIn: true);
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    await tester.tap(find.text('Lens').first);
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

  testWidgets('Mes paris : le pari proposé par un moteur garde son nom (18/11)', (tester) async {
    final (_, server) = await startApp(tester, loggedIn: true);
    Map<String, dynamic> bet(int id, int? engine) => {
      'id': id,
      'kind': 'single',
      'stake': 1000,
      'currency': 'XOF',
      'total_odds': '1.92',
      'potential_payout': 1920,
      'status': 'open',
      'engine': engine,
      'selections': [
        {'match_id': 7, 'market': '1X2', 'selection': 'home', 'odds': '1.92'},
      ],
    };
    server.bets = [bet(58, 2), bet(57, null)];
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    await tab(tester, HomeTab.paris);
    await tester.pumpAndSettle();
    expect(find.text('MOTEUR 2'), findsOneWidget); // le pari composé à la main : rien
    expect(find.text('MOTEUR 1'), findsNothing);
  });

  testWidgets('Mon bilan : rendement, annoncé contre réalisé, rappel de jeu responsable', (tester) async {
    await startApp(tester, loggedIn: true);
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    await tab(tester, HomeTab.paris);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Mon bilan'));
    await tester.pumpAndSettle();
    expect(find.text(signedMoney(3000)), findsOneWidget);
    expect(
      find.text('Tes sélections annoncées autour de 65$nbsp% ont gagné 60$nbsp% du temps.'),
      findsOneWidget,
    );
    // Annoncé contre réalisé (bande de 1 sélection) et mi-temps (7 sélections, 38 % contre 14 %).
    expect(find.textContaining('Moins de 20 sélections'), findsNWidgets(2));
    expect(find.textContaining('ont au moins doublé'), findsOneWidget);
    expect(find.text('Résultat du match'), findsOneWidget);
    // Maquette du 17/11/2026 : annoncé à côté du réalisé, écart net signalé.
    expect(find.text('Bien en dessous de l\'annoncé'), findsOneWidget);
    expect(find.text('71$nbsp%'), findsOneWidget);
    expect(find.text('44$nbsp%'), findsOneWidget);
    expect(find.text('27'), findsOneWidget); // Ligue 1 : 16 + 10 + 1 remboursée
    expect(find.text('Ligue 1'), findsOneWidget);
    expect(find.text('Par cote du coupon'), findsOneWidget);
    expect(find.text('20 et plus'), findsOneWidget);
    expect(find.text('−12${nbsp}000'), findsOneWidget);
  });

  testWidgets('mouvement des cotes : ouverture affichée, historique des relevés', (tester) async {
    await startApp(tester, loggedIn: true);
    await tester.tap(find.text('Lens').first);
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
    await tab(tester, HomeTab.coupon);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coupon intelligent'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Grosse cote'));
    await tester.pumpAndSettle();
    expect(find.text('25'), findsNothing); // cotes visées de 2 à 10
    await tester.tap(find.text('5'));
    await tester.tap(find.text('Plus de réglages'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Après 18 h'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Après 18 h'));
    await tester.ensureVisible(find.text('Composer le coupon'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Composer le coupon'));
    await tester.pumpAndSettle();
    expect(server.smartQueries.last, {
      'profile': 'grosse',
      'period': 'next',
      'size': '12',
      'target_odds': '5',
      'after_hour': '18',
    });
    expect(find.textContaining('environ 6 fois sur 10'), findsOneWidget); // probabilité 0,62
    // Phrase de vérité : 10 × 500 F × 0,62 × 1,85 = 5 735 F, arrondi à la centaine.
    final truth = find.text(
      'Environ 1 coupon sur 2 passe. Sur 10 coupons de 500 F comme celui-ci (5\u00a0000 F misés), '
      'tu récupères en moyenne environ 5\u00a0700 F.',
    );
    expect(truth, findsOneWidget);
    expect(find.textContaining('Coupon à gros risque'), findsOneWidget);
    // Règle du coupon expliquée (cotes reçues en texte, comme du serveur).
    expect(find.textContaining('jusqu\'à dépasser la cote visée'), findsOneWidget);

    // Toucher une sélection pour la changer (maquette 11), cinq choix.
    await tester.ensureVisible(find.byKey(const ValueKey('change-0')));
    await tester.tap(find.byKey(const ValueKey('change-0')));
    await tester.pumpAndSettle();
    expect(find.text('Retirer sans remplacer'), findsOneWidget);
    expect(find.text('Exclure ce championnat (Ligue 1)'), findsOneWidget);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Toujours exclure Lens'));
    await tester.pumpAndSettle();
    expect(state.excludedTeams, {1: 'Lens'});
    expect(server.smartQueries.last['exclude_teams'], '1');

    // Proposition du 07/11/2026 : coupon tiré pour ce joueur, dit, et « Un autre coupon ».
    expect(find.textContaining('Composé pour toi parmi les meilleurs'), findsOneWidget);
    expect(
      find.textContaining(RegExp(r'Chance de ce coupon : 62,0\s%\s\(le meilleur : 63,5\s%\)')),
      findsOneWidget,
    );
    await tester.ensureVisible(find.text('Autre coupon'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Autre coupon'));
    await tester.pumpAndSettle();
    expect(server.smartQueries.last['variant'], '1');

    await tester.ensureVisible(find.text('Partager en image'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Partager en image'));
    await tester.pumpAndSettle();
    expect(find.text('Chances du moteur'), findsOneWidget);
    expect(truth, findsNWidgets(2)); // résultat et image partagée
    expect(
      find.text('Probabilités calculées par FootProba. Argent fictif : aucun gain réel.'),
      findsOneWidget,
    );
    Navigator.of(tester.element(find.text('Chances du moteur'))).pop();
    await tester.pumpAndSettle();

    // Ajouté au coupon : mise proposée de 500 F et phrase de vérité dans Mon coupon.
    await tester.ensureVisible(find.text('Ajouter au coupon'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ajouter au coupon'));
    await tester.pumpAndSettle();
    expect(state.coupon, hasLength(1));
    expect(state.couponBig, isTrue);
    await tester.tap(find.text('Voir mon coupon'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextField, '500'), findsOneWidget);
    expect(find.textContaining('Sur 10 coupons de 500 F'), findsOneWidget);
  });

  testWidgets('match : choix du moteur, deux sélections du même match à départager', (tester) async {
    final (state, _) = await startApp(tester, loggedIn: true);
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    await tester.tap(find.text('Lens').first);
    await tester.pumpAndSettle();
    expect(find.text('Les choix du moteur'), findsOneWidget);
    expect(find.text('Aucune sélection dans cette tranche'), findsOneWidget); // Sûr
    expect(find.text('Avec Premium'), findsNWidgets(2));

    await tester.tap(find.text('1,85').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cotes'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Buts'));
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
    await tester.tap(find.text('Lens').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Analyse'));
    await tester.pumpAndSettle();
    expect(find.text("Pas encore d'analyse pour ce match."), findsNothing);
    expect(find.text('Inclus dans Premium'), findsOneWidget);
    expect(state.premium, isFalse); // profil relu
  });

  testWidgets('fenêtre moyenne : colonne centrée de 680 pixels, téléphone inchangé', (tester) async {
    await startApp(tester, loggedIn: true); // 430 pixels de large : téléphone
    expect(tester.getSize(find.byType(Navigator).first).width, 430);
    await tester.binding.setSurfaceSize(const Size(1000, 900));
    await tester.pumpAndSettle();
    expect(find.text('Lyon'), findsOneWidget);
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
    expect(find.text('Aujourd\'hui'), findsWidgets); // rubrique d'ouverture (étape B)
    await tab(tester, HomeTab.matchs);
    expect(find.text('Fiabilité du moteur'), findsOneWidget); // menu
    expect(find.text('Les deux\nmarquent'), findsOneWidget); // en-tête du tableau
    expect(find.text('57$nbsp%'), findsWidgets);
    expect(find.text('Miser sur ce coupon'), findsNothing); // coupon vide

    // Cote réelle sous la probabilité : un clic l'ajoute au coupon, visible à droite.
    await tester.tap(find.text('1,85'));
    await tester.pumpAndSettle();
    expect(state.coupon.single.offer.key, '1X2||home');
    expect(find.text('Miser sur ce coupon'), findsOneWidget);

    // Un match s'ouvre dans la zone centrale ; le menu et le coupon restent.
    await tester.tap(find.text('Lens').first);
    await tester.pumpAndSettle();
    expect(find.text('RÉSULTAT DU MATCH'), findsOneWidget);
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

    // Montante : le plan devient un escalier.
    await tab(tester, HomeTab.montante);
    await tester.pumpAndSettle();
    expect(find.text('PALIER 1'), findsOneWidget);
    expect(find.text('PALIER'), findsNothing); // en-tête du tableau du téléphone
  });

  testWidgets('comparaison des moteurs : suggestions du palier des deux moteurs, moteur gardé (K4)', (
    tester,
  ) async {
    final (state, server) = await startApp(tester, loggedIn: true, premium: true);
    server.compareEngines = true;
    await state.refreshMe();
    server.montantes = [
      {
        'id': 4,
        'status': 'active',
        'currency': 'XOF',
        'start_stake': 5000,
        'secure_pct': 0,
        'current_step': 1,
        'steps': [
          {
            'number': 1,
            'odds_min': '1.60',
            'odds_max': '1.95',
            'result': 'pending',
            'bet_id': null,
            'out_of_range': false,
            'stake': 5000,
            'payout_range': [8000, 9750],
          },
        ],
        'final_payout_range': [8000, 9750],
        'chance_by_odds': 0.6,
        'chance_by_model': null,
        'cashable': 0,
        'net_result': 0,
      },
    ];
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    await tab(tester, HomeTab.montante);
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Suggestions du moteur', findRichText: true));
    await tester.pumpAndSettle();
    expect(find.text('MOTEUR 1'), findsOneWidget);
    expect(find.text('MOTEUR 2'), findsOneWidget);
    await tester.tap(find.text('1,95').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Jouer'));
    await tester.pumpAndSettle();
    expect(server.stepBets.single['engine'], 2);
    expect(server.stepBets.single['from_suggestion'], isTrue);

    // Montante terminée entre-temps (retour du 17/11) : message clair, pas de suggestions.
    server.montanteFinished = true;
    await tester.tap(find.textContaining('Suggestions du moteur', findRichText: true));
    await tester.pumpAndSettle();
    expect(find.textContaining('Cette montante est terminée'), findsOneWidget);
    expect(find.text('Créer une nouvelle montante'), findsOneWidget);
    expect(find.text('MOTEUR 1'), findsNothing);
  });

  testWidgets('montante : match, date et état du pari de chaque palier, comme dans Mes paris', (
    tester,
  ) async {
    final (_, server) = await startApp(tester, loggedIn: true, premium: true);
    server.montantes = [
      {
        'id': 4,
        'status': 'active',
        'currency': 'XOF',
        'start_stake': 5000,
        'secure_pct': 0,
        'current_step': 2,
        'steps': [
          {
            'number': 1,
            'odds_min': '1.55',
            'odds_max': '1.65',
            'result': 'won',
            'bet_id': 31,
            'out_of_range': false,
            'stake': 5000,
            'odds': '1.57',
            'payout': 7850,
          },
          {
            'number': 2,
            'odds_min': '1.60',
            'odds_max': '1.70',
            'result': 'pending',
            'bet_id': null,
            'out_of_range': false,
            'stake': 7850,
            'payout_range': [12560, 13345],
          },
        ],
        'final_payout_range': [12560, 13345],
        'chance_by_odds': 0.6,
        'chance_by_model': null,
        'cashable': 7850,
        'net_result': 2850,
      },
    ];
    server.betsById[31] = {
      'id': 31,
      'kind': 'single',
      'stake': 5000,
      'currency': 'XOF',
      'total_odds': '1.57',
      'potential_payout': 7850,
      'payout': 7850,
      'status': 'settled',
      'selections': [
        {
          'match_id': 9,
          'market': '1X2',
          'selection': 'home',
          'odds': '1.57',
          'result': 'win',
          'home_team': 'Hull',
          'away_team': 'Middlesbrough',
          'kickoff_at': '2026-11-08T16:00:00Z',
          'state': 'settled',
          'score': [2, 1],
        },
      ],
    };
    server.montanteSummary = {
      'montantes': 6,
      'counts': {'completed': 1, 'lost': 2, 'cashed_out': 1, 'active': 2},
      'finished': 4,
      'staked': 26000,
      'returned': 94143,
      'net': 68143,
      'survival': [
        {'step': 1, 'montantes': 4, 'reached': 1.0, 'expected': 1.0},
        {'step': 2, 'montantes': 4, 'reached': 0.75, 'expected': 0.6},
      ],
      'stops': {
        'lost': [
          {'step': 2, 'count': 1},
          {'step': 4, 'count': 1},
        ],
        'cashed_out': [
          {'step': 1, 'count': 1},
        ],
      },
      'choices': {
        'engine': {'steps': 14, 'won': 12},
        'player': {'steps': 6, 'won': 4},
        'unknown': {'steps': 0, 'won': 0},
        'out_of_range': {'steps': 1, 'won': 1},
      },
      'out_of_range_cost': 22000,
      'markets': [
        {'market': 'OU', 'won': 7, 'lost': 2},
      ],
      'enough': false,
      'min_finished': 30,
    };
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    await tab(tester, HomeTab.montante);
    await tester.pumpAndSettle();
    expect(find.text('Hull – Middlesbrough'), findsOneWidget);
    expect(find.textContaining('8 nov'), findsOneWidget);
    expect(find.textContaining('gagné'), findsWidgets);

    // M1 : bilan, gagnées et perdues ensemble.
    expect(find.textContaining('+68\u00A0143'), findsOneWidget);
    expect(find.textContaining('misés au départ'), findsOneWidget);
    // M3 : ce qui est en jeu au palier 2 (pas encore de pari) ; 20 % sécurisés : 1 570 F.
    expect(find.text('Ce qui est en jeu au palier 2'), findsOneWidget);
    expect(find.text('Si j\'arrête maintenant'), findsOneWidget);
    expect(find.textContaining('1\u00A0570'), findsOneWidget);

    // M2 : analyse.
    await tester.tap(find.text('Voir l\'analyse ›'));
    await tester.pumpAndSettle();
    expect(find.text('Jusqu\'où vont mes montantes'), findsOneWidget);
    expect(find.text('P2'), findsOneWidget);
    expect(find.textContaining('trop peu pour conclure'), findsOneWidget);
    expect(find.text('Proposés par le moteur'), findsOneWidget);
    expect(find.text('86\u00A0%'), findsOneWidget); // 12 sur 14
    expect(find.textContaining('de moins à'), findsOneWidget);
    await tester.binding.setSurfaceSize(null);
  });

  testWidgets('comparaison des moteurs : moteur 1 contre 2 dans la Fiabilité (K6)', (tester) async {
    final (state, server) = await startApp(tester, loggedIn: true);
    final context = tester.element(find.byType(Scaffold).first);
    Navigator.of(
      context,
      rootNavigator: true,
    ).push(MaterialPageRoute(builder: (_) => const ReliabilityScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Moteur 1 contre moteur 2'), findsNothing); // seulement en mode comparaison
    Navigator.of(tester.element(find.byType(ReliabilityScreen))).pop();
    await tester.pumpAndSettle();
    server.compareEngines = true;
    await state.refreshMe();
    Navigator.of(
      tester.element(find.byType(Scaffold).first),
      rootNavigator: true,
    ).push(MaterialPageRoute(builder: (_) => const ReliabilityScreen()));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Moteur 1 contre moteur 2'), 200);
    await tester.tap(find.text('Moteur 1 contre moteur 2'));
    await tester.pumpAndSettle();
    expect(find.text('412'), findsOneWidget);
    expect(find.text('0,983'), findsOneWidget);
    expect(find.text('0,961'), findsOneWidget);
    expect(find.text('−4,0\u00A0%'), findsOneWidget);
    expect(find.text('−1,0\u00A0%'), findsOneWidget);
    expect(find.textContaining('Trop peu de données pour conclure'), findsOneWidget);
  });

  testWidgets('fiabilité : sélections nationales, moteur contre cote (retour du 17/11)', (tester) async {
    await startApp(tester, loggedIn: true);
    final context = tester.element(find.byType(Scaffold).first);
    Navigator.of(
      context,
      rootNavigator: true,
    ).push(MaterialPageRoute(builder: (_) => const ReliabilityScreen()));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Sélections nationales : moteur contre cote'), 200);
    expect(find.text('+10 à +15 pts'), findsOneWidget);
    expect(find.text('+15 pts et plus'), findsOneWidget);
    expect(find.textContaining('Seulement 18 sélections'), findsOneWidget);
  });

  testWidgets('fiabilité des montantes : annoncé contre gagné par palier, montantes terminées', (
    tester,
  ) async {
    final (_, server) = await startApp(tester, loggedIn: true);
    server.montanteReliability = {
      'steps': [
        {'steps': '1-2', 'count': 58, 'announced': 0.62, 'won': 0.64, 'fair': true},
      ],
      'finished': 27,
      'to_end': 3,
      'to_end_share': 0.111,
      'expected_share': 0.09,
      'yield': 0.41,
      'enough': false,
      'min_finished': 30,
    };
    final context = tester.element(find.byType(Scaffold).first);
    Navigator.of(
      context,
      rootNavigator: true,
    ).push(MaterialPageRoute(builder: (_) => const ReliabilityScreen()));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Montantes'), 200);
    await tester.tap(find.text('Montantes'));
    await tester.pumpAndSettle();
    expect(find.text('62\u00A0%'), findsOneWidget);
    expect(find.text('64\u00A0%'), findsOneWidget);
    expect(find.text('3 (11\u00A0%)'), findsOneWidget);
    expect(find.text('+41,0\u00A0%'), findsOneWidget);
    expect(find.textContaining('Trop peu de montantes terminées'), findsOneWidget);
  });

  testWidgets('mode Montante : trois onglets, ouvre sur la montante, désactivé dans le Profil', (
    tester,
  ) async {
    final (state, server) = await startApp(tester, loggedIn: true, premium: true);
    // Activé dans le Profil : réglage du compte, l'application ouvre sur la montante.
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Mode Montante'), 200);
    await tester.tap(find.text('Mode Montante'));
    await tester.pumpAndSettle();
    expect(server.montanteMode, isTrue);
    expect(find.text('Coupon'), findsNothing);
    expect(find.text('Mes paris'), findsNothing);
    expect(find.text('Matchs'), findsWidgets);
    expect(find.text('Montante'), findsWidgets);
    expect(find.text('Nombre de paliers'), findsOneWidget); // onglet Montante (aucune en cours)

    // Une cote touchée dans les matchs : « Mon palier » s'ouvre par-dessus.
    await tab(tester, HomeTab.matchs);
    await tester.pumpAndSettle();
    expect(find.textContaining('Mon palier'), findsNothing);
    await tester.tap(find.text('Lens').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('1,85').first);
    await tester.pumpAndSettle();
    expect(state.coupon, hasLength(1));
    await tester.tap(find.byTooltip('Retour'));
    await tester.pumpAndSettle();
    expect(find.text('Mon palier · 1 sélection'), findsOneWidget);
    await tester.tap(find.text('Mon palier · 1 sélection'));
    await tester.pumpAndSettle();
    expect(find.textContaining('palier', findRichText: true), findsWidgets); // titre « Mon palier »
    expect(find.text('Coupon intelligent'), findsNothing);
    await tester.tap(find.byType(BackChevron).first);
    await tester.pumpAndSettle();
    state.clearCoupon();

    // Désactivé : l'application redevient complète.
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Mode Montante'), 200);
    await tester.tap(find.text('Mode Montante'));
    await tester.pumpAndSettle();
    expect(server.montanteMode, isFalse);
    expect(find.bySemanticsLabel('Créer'), findsOneWidget); // bouton « + » de la barre
    expect(find.text('Paris'), findsOneWidget);
  });

  testWidgets('notifications push : téléphone enregistré, notification touchée, déconnexion', (tester) async {
    final push = FakePush();
    final (state, server) = await startApp(tester, loggedIn: true, push: push);
    expect(server.devices, ['jeton-telephone-1']);

    push.refresh.add('jeton-telephone-2');
    await tester.pumpAndSettle();
    expect(server.devices, ['jeton-telephone-1', 'jeton-telephone-2']);

    push.received.add((text: 'FootProba — Notification d\'essai', kind: 'test'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('FootProba — Notification d\'essai'), findsOneWidget);
    await tester.pumpAndSettle(const Duration(seconds: 5));

    push.tapped.add(null);
    await tester.pumpAndSettle();
    expect(find.byType(NotificationsScreen), findsOneWidget);
    Navigator.of(tester.element(find.byType(NotificationsScreen))).pop();
    await tester.pumpAndSettle();

    // « Coupons du jour disponibles » touchée : directement l'écran des coupons du jour.
    push.tapped.add('daily_coupons');
    await tester.pumpAndSettle();
    expect(find.byType(DailyCouponsScreen), findsOneWidget);
    Navigator.of(tester.element(find.byType(DailyCouponsScreen))).pop();
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

  testWidgets('Premium sans paiement en ligne : WhatsApp proposé, jamais d\'impasse', (tester) async {
    SharedPreferences.setMockInitialValues({'token': 'jeton'});
    final server = FakeServer()..paymentsConfigured = false;
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
    await tester.pumpWidget(FootProbaApp(state: state));
    await state.init();
    await tester.pumpAndSettle();
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.textContaining('Passer Premium'), 200);
    await tester.tap(find.textContaining('Passer Premium'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Paiement indisponible'), findsNothing);
    await tester.tap(find.text('Écrire sur WhatsApp'));
    await tester.pumpAndSettle();
    expect(opened.single.host, 'wa.me');
    expect(opened.single.queryParameters['text'], contains('je veux passer Premium'));
    expect(opened.single.queryParameters['text'], contains('n° 1'));
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
    await tester.pumpWidget(FootProbaApp(state: state));
    await state.init();
    await tester.pumpAndSettle();
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.textContaining('Passer Premium'), 200);
    await tester.tap(find.textContaining('Passer Premium'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Ce paiement est réel'), findsOneWidget);
    await tester.tap(find.text('Payer avec Orange Money, MTN, Wave ou carte'));
    await tester.pumpAndSettle();
    expect(server.boughtWith, 'paystack');
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

  testWidgets('Premium : serveur pas encore à jour, paiement quand même possible', (tester) async {
    SharedPreferences.setMockInitialValues({'token': 'jeton'});
    final server = FakeServer()..oldServer = true;
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
    await tester.pumpWidget(FootProbaApp(state: state));
    await state.init();
    await tester.pumpAndSettle();
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.textContaining('Passer Premium'), 200);
    await tester.tap(find.textContaining('Passer Premium'));
    await tester.pumpAndSettle();
    expect(find.text('Requête invalide'), findsNothing);
    await tester.tap(find.text('Payer avec Mobile Money ou carte'));
    await tester.pumpAndSettle();
    expect(server.boughtWith, isNull);
    expect(opened.single.toString(), 'https://checkout.cinetpay.com/payment/abc');
  });

  testWidgets('bookmaker : en-tête calculé sur tous les paris (serveur), pas sur les 100 chargés', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({'token': 'jeton'});
    final server = FakeServer()
      ..betsSummary = {
        'bets': 296,
        'settled': 296,
        'staked': 536205,
        'returned': 516608,
        'yield': -0.036,
        'at_stake': 0,
        'last_30_days': -2784,
      };
    final state = AppState(
      api: ApiClient(baseUrl: 'http://serveur', httpClient: MockClient(server.handle)),
      socketFactory: (_) => null,
    );
    await tester.binding.setSurfaceSize(const Size(430, 1400));
    await tester.pumpWidget(FootProbaApp(state: state));
    await state.init();
    await tester.pumpAndSettle();
    await tab(tester, HomeTab.paris);
    await tester.pumpAndSettle();
    expect(find.textContaining('296'), findsOneWidget);
    expect(find.textContaining('-3,6'), findsOneWidget);
  });

  testWidgets('cotes coupées : bandeau dans le bookmaker et les coupons du jour', (tester) async {
    SharedPreferences.setMockInitialValues({'token': 'jeton'});
    final server = FakeServer()..oddsAvailable = false;
    final state = AppState(
      api: ApiClient(baseUrl: 'http://serveur', httpClient: MockClient(server.handle)),
      socketFactory: (_) => null,
    );
    await tester.binding.setSurfaceSize(const Size(430, 1400));
    await tester.pumpWidget(FootProbaApp(state: state));
    await state.init();
    await tester.pumpAndSettle();
    await tab(tester, HomeTab.paris);
    await tester.pumpAndSettle();
    expect(find.textContaining('Cotes momentanément indisponibles'), findsOneWidget);
    // Retour des cotes : le bandeau disparaît.
    server.oddsAvailable = true;
    await state.checkStatus();
    await tester.pumpAndSettle();
    expect(find.textContaining('Cotes momentanément indisponibles'), findsNothing);
  });

  testWidgets('Premium : Wave manuel, numéro affiché et capture envoyée sur WhatsApp', (tester) async {
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
    await tester.pumpWidget(FootProbaApp(state: state));
    await state.init();
    await tester.pumpAndSettle();
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.textContaining('Passer Premium'), 200);
    await tester.tap(find.textContaining('Passer Premium'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Payer avec Wave (envoi au numéro FootProba)'));
    await tester.pumpAndSettle();
    expect(find.text('+225 07 00 00 00 00'), findsOneWidget); // groupé pour le recopier
    expect(server.boughtWith, isNull);
    await tester.tap(find.text('Envoyer la capture'));
    await tester.pumpAndSettle();
    final text = opened.single.queryParameters['text']!;
    expect(opened.single.host, 'wa.me');
    expect(text, contains('par Wave au +2250700000000'));
    expect(text, contains('compte n° '));
    // Paiement en attente rappelé sur la carte Premium.
    expect(find.textContaining('en attente de vérification'), findsOneWidget);
  });

  testWidgets('version web : notifications activées depuis le profil, jeton « web » envoyé', (tester) async {
    final web = FakeWebPush();
    SharedPreferences.setMockInitialValues({'token': 'jeton'});
    final server = FakeServer()..vapidKey = 'BCle-publique';
    final state = AppState(
      api: ApiClient(baseUrl: 'http://serveur', httpClient: MockClient(server.handle)),
      socketFactory: (_) => null,
      webPush: web,
      android: false,
    );
    await tester.binding.setSurfaceSize(const Size(430, 1400));
    await tester.pumpWidget(FootProbaApp(state: state));
    await state.init();
    await tester.pumpAndSettle();
    expect(web.key, 'BCle-publique');
    expect(server.devices, isEmpty); // rien avant le geste du joueur
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    expect(find.text('Notifications sur cet appareil'), findsOneWidget);
    await tester.ensureVisible(find.text('Activer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Activer'));
    await tester.pumpAndSettle();
    expect(server.platforms, ['web']);
    expect(find.text('Activées'), findsOneWidget);
  });

  testWidgets('version web : rien proposé sans clé du serveur ; iPhone dans Safari guidé', (tester) async {
    final (state, _) = await startApp(tester, loggedIn: true, webPush: FakeWebPush());
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    expect(find.text('Notifications sur cet appareil'), findsNothing);
    state.webPushStatus.value = WebPushStatus.install;
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Écran d\'accueil'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Écran d\'accueil'));
    await tester.pumpAndSettle();
    expect(find.textContaining('ajouté à l\'écran'), findsOneWidget);
  });

  testWidgets('Coupon intelligent : profil et période choisis, coupon expliqué, ajouté au coupon', (
    tester,
  ) async {
    final (state, server) = await startApp(tester, loggedIn: true, premium: true);
    await tab(tester, HomeTab.coupon);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coupon intelligent'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Ce week-end'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ce week-end'));
    await tester.pumpAndSettle();
    // Seulement les championnats qui ont des matchs dans la période (rapport du 07/11/2026).
    expect(find.text('Ligue 1'), findsOneWidget);
    expect(find.text('Premier League'), findsNothing);
    // Le bouton est plus bas : la liste ne le construit qu'une fois atteint.
    await tester.scrollUntilVisible(
      find.text('Composer le coupon'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Composer le coupon'));
    await tester.pumpAndSettle();
    expect(server.smartQueries.single, {'profile': 'equilibre', 'period': 'weekend', 'size': '3'});
    expect(find.textContaining('victoire Lens'), findsOneWidget); // maquette 11
    expect(find.text('1 SÉLECTION · COTE'), findsOneWidget);
    expect(find.text('• Forme (5 derniers) : Lens VNDVV, Lyon DNVVN'), findsOneWidget);
    // Maquette P1 : moteur et cote côte à côte (62 % contre 54 %), sans promesse.
    expect(find.textContaining('trait jaune : selon la cote'), findsOneWidget);
    expect(find.textContaining('Le moteur est un peu plus confiant que la cote'), findsOneWidget);
    expect(find.textContaining('L\'écart ne garantit rien'), findsOneWidget);

    await tester.ensureVisible(find.text('Ajouter au coupon'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ajouter au coupon'));
    await tester.pumpAndSettle();
    expect(state.coupon.single.offer.key, '1X2||home');
    expect(find.text('Voir mon coupon'), findsOneWidget); // dans le message (rapport du 07/11)
    messengerKey.currentState!.removeCurrentSnackBar();
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.byTooltip('Coupons du jour'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Coupons du jour'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byTooltip('Historique complet'),
      300,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Historique complet'));
    await tester.pumpAndSettle();
    expect(find.text('Gagné'), findsWidgets);
    expect(find.textContaining('1 gagné sur 1'), findsOneWidget);
  });

  testWidgets('coupons du jour gratuits : profil, cote et chance, sélections et code dans Premium', (
    tester,
  ) async {
    await startApp(tester, loggedIn: true);
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    await tab(tester, HomeTab.coupon);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coupons du jour'));
    await tester.pumpAndSettle();
    expect(find.text('62$nbsp%'), findsOneWidget); // la chance reste visible
    // Maquette P2 : chance selon la cote sur chaque carte, et la place du moteur.
    expect(find.textContaining('selon la cote : '), findsNWidgets(3));
    expect(find.text('cote'), findsWidgets); // « ≈ cote » : Audacieux 30 % à 3,10 (32 %), −2 points
    expect(find.text('Sélections et code 1xBet dans Premium'), findsNWidgets(3));
    expect(find.text('Copier'), findsNothing);
    expect(find.text('Débloquer les coupons du jour'), findsOneWidget);
    await tester.tap(find.text('Passer Premium · 2${nbsp}000 F pour 30 jours'));
    await tester.pumpAndSettle();
    expect(find.text('Premium · 30 jours'), findsOneWidget); // « Passer Premium » directement
  });

  testWidgets('comparaison des moteurs : coupons du jour des deux moteurs (K5)', (tester) async {
    final (state, server) = await startApp(tester, loggedIn: true, premium: true);
    server.compareEngines = true;
    await state.refreshMe();
    await tester.binding.setSurfaceSize(const Size(430, 3000));
    await tab(tester, HomeTab.coupon);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coupons du jour'));
    await tester.pumpAndSettle();
    expect(find.text('MOTEUR 1'), findsOneWidget);
    expect(find.text('MOTEUR 2'), findsOneWidget);
    expect(find.textContaining('1,92', findRichText: true), findsWidgets);
    expect(find.textContaining('Moteur 2, 30 derniers jours : 3 gagnés sur 4'), findsOneWidget);
  });

  testWidgets('coupons du jour : chance, état en direct, code copié, détail', (tester) async {
    await startApp(tester, loggedIn: true, premium: true);
    final copied = <String>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') copied.add((call.arguments as Map)['text'] as String);
      return null;
    });
    await tab(tester, HomeTab.coupon);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coupons du jour'));
    await tester.pumpAndSettle();
    expect(find.text('2 gagnés sur 3'), findsOneWidget);
    // 30 derniers jours : un profil par ligne, jamais additionnés.
    expect(find.text('49 gagnés sur 90'), findsNothing);
    expect(find.text('17 gagnés sur 30'), findsOneWidget);
    expect(find.text('Chance annoncée 27$nbsp% · réalisé 27$nbsp%'), findsOneWidget);
    // Coupon perdu sans code : plus de « bientôt disponible » (essai du 07/11/2026).
    expect(find.textContaining('Code bientôt disponible'), findsOneWidget);
    expect(find.text('Perdu'), findsOneWidget);
    expect(find.text('En cours'), findsOneWidget);
    expect(find.text('62$nbsp%'), findsOneWidget);

    await tester.ensureVisible(find.text('Copier'));
    await tester.tap(find.text('Copier'));
    await tester.pumpAndSettle();
    expect(copied, ['7HQ2K']);
    expect(find.text('Code 7HQ2K copié : colle-le dans 1xBet.'), findsOneWidget);

    await tester.tap(find.text('ÉQUILIBRÉ'));
    await tester.pumpAndSettle();
    expect(find.text('en cours 58\' · 1-0'), findsOneWidget);
    expect(find.textContaining('Sur 100 coupons comme celui-ci, environ 62 passent.'), findsOneWidget);
    // Matchs commencés : plus d'ajout au coupon.
    expect(find.text('Ajouter à mon coupon'), findsNothing);
  });

  testWidgets('historique des coupons : les plus anciens chargés à la demande', (tester) async {
    await startApp(tester, loggedIn: true, premium: true);
    final context = tester.element(find.byType(Scaffold).first);
    Navigator.of(
      context,
      rootNavigator: true,
    ).push(MaterialPageRoute(builder: (_) => const SmartHistoryScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Bilan depuis le lancement'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Voir les coupons plus anciens'), 200);
    await tester.tap(find.text('Voir les coupons plus anciens'));
    await tester.pumpAndSettle();
    expect(find.text('Perdu'), findsOneWidget);
    expect(find.text('Voir les coupons plus anciens'), findsNothing);
  });

  testWidgets('fiabilité : verdict, un marché à la fois, pronostics publiés et autres championnats', (
    tester,
  ) async {
    await startApp(tester, loggedIn: true);
    final context = tester.element(find.byType(Scaffold).first);
    Navigator.of(
      context,
      rootNavigator: true,
    ).push(MaterialPageRoute(builder: (_) => const ReliabilityScreen()));
    await tester.pumpAndSettle();
    // Verdict d'abord : simulation (5 grands), marché retiré nommé, puis résultats réels de
    // tous les championnats (vue par défaut, essai du 08/11/2026).
    expect(find.text('Tous'), findsOneWidget);
    expect(
      find.textContaining('Simulation : les 2 marchés publiés respectent la règle de justesse'),
      findsOneWidget,
    );
    expect(
      find.textContaining('Résultats réels depuis le lancement (Tous les championnats, 550 matchs)'),
      findsOneWidget,
    );
    expect(find.textContaining('Retiré : « Tirs cadrés : le plus de »'), findsOneWidget);
    // Maquette C5 : la page s'ouvre sur les pronostics publiés (résultats réels).
    expect(find.text('✓ règle respectée'), findsOneWidget);
    expect(find.text('7,5\u00A0%'), findsOneWidget); // 0,99 contre 1,07 (fréquence observée)
    expect(find.textContaining('Pronostics publiés avant les matchs, Tous les championnats'), findsOneWidget);

    // Simulation du résultat du match : annoncé → arrivé, avantage sur la moyenne, bookmakers.
    await tester.tap(find.text('Simulation'));
    await tester.pumpAndSettle();
    expect(find.text('✓ règle respectée · écart max 3 pts'), findsOneWidget);
    expect(find.textContaining('74 → '), findsOneWidget);
    expect(find.text('7,9\u00A0%'), findsOneWidget);
    expect(find.textContaining('en plus que les bookmakers'), findsOneWidget);
    await tester.tap(find.text('Depuis le lancement (550)'));
    await tester.pumpAndSettle();

    // Liste des marchés : un autre marché s'affiche à la place.
    await tester.tap(find.text('Résultat du match'));
    await tester.pumpAndSettle();
    expect(find.text('retiré'), findsOneWidget);
    await tester.tap(find.text('Corners : total'));
    await tester.pumpAndSettle();
    expect(find.textContaining('45 → '), findsOneWidget);
    expect(find.text('pas de cotes passées pour comparer aux bookmakers'), findsOneWidget);

    // Autre championnat : marchés suivis, pronostics publiés et avertissement du petit échantillon.
    await tester.tap(find.text('Tous'));
    await tester.pumpAndSettle();
    expect(find.text('5 grands championnats'), findsOneWidget);
    await tester.tap(find.text('Premier League'));
    await tester.pumpAndSettle();
    expect(find.text('Résultat du match'), findsOneWidget);
    await tester.tap(find.text('Résultat du match'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Les deux marquent'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Seulement 170 matchs sur ce marché'), findsOneWidget);
    // Moins de 200 matchs : jamais de « ✓ », pas encore de verdict.
    expect(find.textContaining('pas encore assez de matchs pour conclure (170 sur 200)'), findsWidgets);
    expect(find.textContaining('✓'), findsNothing);
  });

  testWidgets('profil : notification des coupons du jour désactivée puis réactivée', (tester) async {
    final (state, server) = await startApp(tester, loggedIn: true);
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    final toggle = find.text('Coupons du jour, chaque matin');
    await tester.ensureVisible(toggle);
    // Interrupteurs : mode Montante, comparaison des moteurs (15/11/2026), puis coupons du jour.
    expect(tester.widget<Switch>(find.byType(Switch).at(2)).value, isTrue);
    await tester.tap(toggle);
    await tester.pumpAndSettle();
    expect(server.dailyNotifications, isFalse);
    expect(state.me!.dailyCouponsNotifications, isFalse);
    await tester.tap(toggle);
    await tester.pumpAndSettle();
    expect(server.dailyNotifications, isTrue);
  });

  testWidgets('profil : mode bêta proposé seulement pendant le test, accord demandé avant de partager', (
    tester,
  ) async {
    final (state, server) = await startApp(tester, loggedIn: true);
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    expect(find.text('Aider à améliorer FootProba'), findsNothing); // période de test fermée

    server.betaAvailable = true;
    await state.refreshMe();
    await tester.pumpAndSettle();
    final row = find.text('Aider à améliorer FootProba');
    await tester.scrollUntilVisible(row, 200);
    // Au-dessus de la barre de navigation flottante (une ligne de plus dans Profil).
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -300));
    await tester.pumpAndSettle();
    expect(find.text('TEST'), findsOneWidget);
    expect(state.beta.enabled, isFalse);

    // « Pas maintenant » : rien n'est partagé.
    await tester.tap(row);
    await tester.pumpAndSettle();
    expect(find.textContaining('Jamais partagé'), findsOneWidget);
    await tester.tap(find.text('Pas maintenant'));
    await tester.pumpAndSettle();
    expect(server.betaSharing, isFalse);

    await tester.tap(row);
    await tester.pumpAndSettle();
    await tester.tap(find.text('J\'accepte de partager'));
    await tester.pumpAndSettle();
    expect(server.betaSharing, isTrue);
    expect(state.beta.enabled, isTrue);
    expect(find.textContaining('Testeur n° 3'), findsOneWidget);

    // Arrêter : immédiat, sans question.
    await tester.tap(find.text('Aider à améliorer FootProba'));
    await tester.pumpAndSettle();
    expect(server.betaSharing, isFalse);
    expect(state.beta.enabled, isFalse);
  });

  testWidgets('matchs du jour rangés par heure de coup d\'envoi, pas par championnat', (tester) async {
    final (_, server) = await startApp(tester, loggedIn: true);
    Map<String, dynamic> epl(int id, String home, String away, String at) => {
      'match': {
        ...FakeServer.match,
        'id': id,
        'competition': 'EPL',
        'kickoff_at': at,
        'home_team': {'id': id * 10, 'name': home, 'country': 'England'},
        'away_team': {'id': id * 10 + 1, 'name': away, 'country': 'England'},
      },
      'prediction': null,
    };
    // Ordre de l'API (essai du 08/11) : Premier League 15:00 puis 12:30, puis Ligue 1 19:00.
    server.extraUpcoming
      ..add(epl(8, 'Fulham', 'Newcastle', '2026-10-10T15:00:00Z'))
      ..add(epl(9, 'Arsenal', 'Hull', '2026-10-10T12:30:00Z'));
    // Liste rechargée (tirer vers le bas).
    await tester.fling(find.text('Lens').first, const Offset(0, 400), 1000);
    await tester.pumpAndSettle();
    double y(String team) => tester.getTopLeft(find.textContaining(team).first).dy;
    expect(y('Arsenal'), lessThan(y('Fulham')));
    expect(y('Fulham'), lessThan(y('Lens')));
  });

  testWidgets('en direct : une seule fois dans la liste, minute du temps additionnel, paris fermés', (
    tester,
  ) async {
    final (state, server) = await startApp(tester, loggedIn: true);
    // Essai du 07/11/2026 : le match en cours apparaissait aussi dans la journée, avec ses
    // chances d'avant le match, et sa cote s'ajoutait au coupon.
    final playing = {
      ...FakeServer.match,
      'api_status': '2H',
      'live_minute': 90,
      'live_extra': 4,
      'live_home_goals': 1,
      'live_away_goals': 0,
    };
    server.live.add(playing);
    MatchInfo.now = () => DateTime.utc(2026, 10, 10, 20, 40);
    await tester.fling(find.text('Lens').first, const Offset(0, 400), 1000);
    await tester.pumpAndSettle();
    expect(find.text('1 – 0'), findsOneWidget);
    expect(find.text('90+4\''), findsOneWidget);
    expect(find.text('Lens – Lyon'), findsOneWidget); // une seule carte : plus dans la journée
    final m = MatchInfo(playing);
    expect(m.when, 'En direct 90+4\'');
    expect(
      MatchInfo({...playing, 'api_status': 'ET', 'live_minute': 105, 'live_extra': null}).clock,
      'Prol. 105\'',
    );
    expect(MatchInfo({...playing, 'api_status': 'P'}).clock, 'Tirs au but');
    final offer = Offer({'market': '1X2', 'selection': 'home', 'odds': 1.2, 'bookmaker': '1xBet'});
    expect(state.toggleCoupon(m, offer), 'Lens – Lyon a commencé : paris fermés');
    expect(state.coupon, isEmpty);
    // L'heure de coup d'envoi suffit, même avant le relevé du direct (toutes les 2 minutes).
    expect(MatchInfo(FakeServer.match).started, isTrue);
    MatchInfo.now = () => DateTime.utc(2026, 10, 10, 18);
    expect(MatchInfo(FakeServer.match).started, isFalse);
  });

  testWidgets('en direct : pastille, buteurs et cartons rouges, chances, matchs de mes paris en haut', (
    tester,
  ) async {
    final (_, server) = await startApp(tester, loggedIn: true);
    MatchInfo.now = () => DateTime.utc(2026, 10, 10, 20, 40);
    final playing = {
      ...FakeServer.match,
      'api_status': '2H',
      'live_minute': 81,
      'live_extra': null,
      'live_home_goals': 1,
      'live_away_goals': 1,
    };
    final other = {
      ...playing,
      'id': 8,
      'home_team': {...FakeServer.team1, 'id': 11, 'name': 'Betis'},
      'away_team': {...FakeServer.team2, 'id': 12, 'name': 'Elche'},
      'api_status': 'HT',
      'live_minute': 45,
      'live_home_goals': 0,
      'live_away_goals': 0,
    };
    server.live.addAll([other, playing]);
    server.liveSummary = {
      '7': {
        'goals': [
          {'minute': 12, 'side': 'home', 'player': 'Krstović'},
          {'minute': 77, 'side': 'away', 'player': 'Lucca'},
        ],
        'reds': [
          {'minute': 81, 'side': 'away', 'player': null},
        ],
      },
    };
    server.bets = [
      {
        'id': 57,
        'kind': 'single',
        'stake': 1000,
        'currency': 'XOF',
        'total_odds': '1.92',
        'potential_payout': 1920,
        'status': 'open',
        'selections': [
          {'match_id': 7, 'market': '1X2', 'selection': 'home', 'odds': '1.92'},
        ],
      },
    ];
    server.liveChances = {
      'published': true,
      'matches': {
        '7': {
          'minute': 81,
          'markets': {'1X2||home': 0.38, '1X2||draw': 0.50, '1X2||away': 0.12},
        },
      },
    };
    await tester.fling(find.text('Lens').first, const Offset(0, 400), 1000);
    await tester.pumpAndSettle();
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    await tester.pumpAndSettle();
    await tester.tap(find.text('En direct 2'));
    await tester.pumpAndSettle();
    expect(find.text('Matchs '), findsNothing);
    // Le match de mon pari en premier, marqué ★, avec buteurs et carton rouge.
    expect(find.textContaining('★ '), findsOneWidget);
    expect(find.text('12\' Krstović · 77\' Lucca · carton rouge 81\' Lyon'), findsOneWidget);
    expect(find.textContaining('50\u00a0%'), findsOneWidget); // issue la plus probable en direct
    expect(find.text('MT'), findsOneWidget);
    final top = tester.getTopLeft(find.text('81\'')).dy;
    expect(top, lessThan(tester.getTopLeft(find.text('MT')).dy));
    MatchInfo.now = DateTime.now;
  });

  testWidgets('en direct : onglet du match (chronologie, statistiques, compositions), chances si publiées', (
    tester,
  ) async {
    final (_, server) = await startApp(tester, loggedIn: true);
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    MatchInfo.now = () => DateTime.utc(2026, 10, 10, 20, 40);
    server.matchNow = {
      ...FakeServer.match,
      'api_status': '2H',
      'live_minute': 63,
      'live_extra': null,
      'live_home_goals': 2,
      'live_away_goals': 1,
    };
    Future<void> open() async {
      await tester.tap(find.text('Lens').first);
      await tester.pumpAndSettle();
    }

    await open();
    expect(find.text('Chances en direct'), findsNothing); // pas encore publiées
    navigatorKey.currentState!.pop();
    await tester.pumpAndSettle();

    server.liveChances = {
      'published': true,
      'matches': {
        '7': {
          'status': '2H',
          'minute': 63,
          'extra': 0,
          'markets': {'1X2||home': 0.78, '1X2||draw': 0.17, '1X2||away': 0.05, 'OU|3.5|over': 0.31},
        },
      },
    };
    server.matchLive = {
      'status': '2H',
      'minute': 63,
      'extra': 0,
      'events': [
        {
          'minute': 23,
          'side': 'home',
          'kind': 'Goal',
          'detail': 'Normal Goal',
          'player': 'Calvert-Lewin',
          'assist': 'Gnonto',
        },
        {
          'minute': 45,
          'extra': 2,
          'side': 'away',
          'kind': 'Card',
          'detail': 'Yellow Card',
          'player': 'Ampadu',
        },
        {
          'minute': 46,
          'side': 'away',
          'kind': 'subst',
          'detail': 'Substitution 1',
          'player': 'Maddison',
          'assist': 'Bentancur',
          'player_id': 10,
          'assist_id': 30,
        },
        {'minute': 51, 'side': 'away', 'kind': 'Goal', 'detail': 'Penalty', 'player': 'Son'},
        {
          'minute': 60,
          'side': 'home',
          'kind': 'Goal',
          'detail': 'Normal Goal',
          'player': 'Gnonto',
          'assist': 'Aaronson',
        },
      ],
      'stats': {
        'match': {
          'home': {'Shots on Goal': 6, 'Ball Possession': '44%', 'expected_goals': '1.62', 'Red Cards': null},
          'away': {'Shots on Goal': 3, 'Ball Possession': '56%', 'expected_goals': '1.05', 'Red Cards': null},
        },
        'first': {
          'home': {'Shots on Goal': 2},
          'away': {'Shots on Goal': 1},
        },
        'second': {
          'home': {'Shots on Goal': 4},
          'away': {'Shots on Goal': 2},
        },
      },
      'lineups': [
        {
          'side': 'home',
          'formation': '4-3-3',
          'coach': 'Farke',
          'players': [
            {'name': 'Illan Meslier', 'number': 1, 'grid': '1:1', 'starter': true},
            {'name': 'Joël Piroe', 'number': 7, 'grid': null, 'starter': false},
          ],
        },
        {
          'side': 'away',
          'formation': '4-3-3',
          'coach': 'Postecoglou',
          'players': [
            {'name': 'James Maddison', 'number': 10, 'grid': '4:2', 'starter': true},
            {'name': 'Rodrigo Bentancur', 'id': 30, 'number': 30, 'grid': null, 'starter': false},
          ],
        },
      ],
    };
    // Mon pari sur ce match : « moins de 2,5 buts », perdu pour l'instant (2-1) : 0 % de
    // chances de tenir n'est jamais écrit (« < 1 % »).
    server.bets = [
      {
        'id': 58,
        'kind': 'single',
        'stake': 1000,
        'currency': 'XOF',
        'total_odds': '1.90',
        'potential_payout': 1900,
        'status': 'open',
        'selections': [
          {'match_id': 7, 'market': 'OU', 'line': '3.5', 'selection': 'under', 'odds': '1.90'},
        ],
      },
    ];
    await open();
    // Onglet « En direct » ouvert d'office : chronologie, mi-temps, remplacement, chances.
    expect(find.text('En direct'), findsOneWidget);
    expect(find.text('MI-TEMPS · 1-0'), findsOneWidget);
    expect(find.text('2-1'), findsOneWidget);
    expect(find.textContaining('passe de Aaronson'), findsOneWidget);
    expect(find.text('Maddison → Bentancur'), findsOneWidget);
    expect(find.text('45+2\''), findsOneWidget);
    expect(find.text('Chances en direct'), findsOneWidget);
    expect(find.text('63\''), findsOneWidget);
    expect(find.text('78\u00a0%'), findsOneWidget);
    // 2-1 : la ligne suit le score (plus de 3,5 = encore au moins un but) ; plus de 4,5 n'est
    // pas envoyée, donc pas de « deux buts » (12/11/2026).
    expect(find.text('Encore au moins un but'), findsOneWidget);
    expect(find.text('31\u00a0%'), findsOneWidget);
    expect(find.text('Ta sélection : moins de 3,5 buts — 69\u00a0% de chances de tenir'), findsOneWidget);
    expect(find.text('Plus de 3,5 buts'), findsNothing);
    expect(find.textContaining('Encore au moins deux buts'), findsNothing);
    expect(find.textContaining('ce n\'est pas un conseil de pari'), findsOneWidget);

    // Statistiques : match, puis 2e mi-temps ; possession à la française, pas de cartons
    // rouges à zéro.
    await tester.tap(find.text('Statistiques'));
    await tester.pumpAndSettle();
    expect(find.text('Tirs cadrés'), findsOneWidget);
    expect(find.text('44\u00a0%'), findsOneWidget);
    expect(find.text('1,62'), findsOneWidget);
    expect(find.text('Cartons rouges'), findsNothing);
    await tester.tap(find.text('2e mi-temps'));
    await tester.pumpAndSettle();
    expect(find.text('4'), findsOneWidget);

    // Compositions : systèmes, entraîneurs, remplaçant entré à la 46e.
    await tester.tap(find.text('Compositions'));
    await tester.pumpAndSettle();
    expect(find.text('Farke'), findsOneWidget);
    expect(find.text('Meslier'), findsOneWidget);
    expect(find.text('Rodrigo Bentancur ✓ 46\'', skipOffstage: false), findsOneWidget);
    expect(find.text('Joël Piroe'), findsOneWidget);
    MatchInfo.now = DateTime.now;
  });

  testWidgets('matchs : cloche des notifications, légende de l\'encadré, textes de Flutter en français', (
    tester,
  ) async {
    await startApp(tester, loggedIn: true);
    // Revue du 07/11/2026 : légende visible sous l'en-tête, pas seulement en bas de la liste.
    expect(find.text('Matchs'), findsWidgets);
    final context = tester.element(find.text('Matchs').first);
    expect(MaterialLocalizations.of(context).modalBarrierDismissLabel, 'Ignorer'); // et non « Dismiss »
    await tab(tester, HomeTab.today); // cloche du tableau de bord (maquette 35)
    await tester.tap(find.byTooltip('Notifications'));
    await tester.pumpAndSettle();
    expect(find.text('Notifications'), findsWidgets);
  });

  testWidgets('notifications : glisser pour en effacer une, « Tout effacer » après confirmation', (
    tester,
  ) async {
    final (_, server) = await startApp(tester, loggedIn: true);
    Map<String, dynamic> note(int id, String title) => {
      'id': id,
      'kind': 'bet_settled',
      'title': title,
      'body': 'Lens - Lyon',
      'data': <String, dynamic>{},
      'created_at': DateTime.now().toUtc().toIso8601String(),
      'read_at': '2026-11-07T10:00:00Z',
    };
    server.notifications.addAll([note(1, 'Pari perdu'), note(2, 'Pari gagné'), note(3, 'Palier validé')]);
    await tab(tester, HomeTab.today); // cloche du tableau de bord (maquette 35)
    await tester.tap(find.byTooltip('Notifications'));
    await tester.pumpAndSettle();
    await tester.drag(find.text('Pari perdu'), const Offset(-500, 0));
    await tester.pumpAndSettle();
    expect(find.text('Pari perdu'), findsNothing);
    expect(server.notifications.map((n) => n['id']), [2, 3]);
    await tester.tap(find.text('Tout effacer'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Tout effacer'));
    await tester.pumpAndSettle();
    expect(server.notifications, isEmpty);
    expect(find.text('Aucune notification.'), findsOneWidget);
  });

  testWidgets('mode bêta proposé une seule fois à l\'ouverture, jamais imposé', (tester) async {
    final (state, server) = await startApp(tester, loggedIn: true, betaAvailable: true);
    expect(find.text('J\'accepte de partager'), findsOneWidget);
    await tester.tap(find.text('Pas maintenant'));
    await tester.pumpAndSettle();
    expect(server.betaSharing, isFalse);
    expect(state.shouldOfferBeta, isFalse); // plus jamais redemandé sur ce téléphone
  });

  testWidgets('administrateur : aucun outil d\'administration dans l\'application', (tester) async {
    final (_, server) = await startApp(tester, loggedIn: true);
    server.admin = true;
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    // Tout passe par FootProba Console : l'application reste celle d'un joueur.
    expect(find.text('Administration'), findsNothing);
    expect(find.text('Admin'), findsNothing);
  });

  testWidgets('Coupon intelligent : réservé à Premium', (tester) async {
    await startApp(tester, loggedIn: true);
    await tab(tester, HomeTab.coupon);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coupon intelligent'));
    await tester.pumpAndSettle();
    expect(find.textContaining('le moteur compose le coupon'), findsOneWidget);
    expect(find.text('Composer le coupon'), findsNothing);
    // Exemple : le dernier coupon réglé (public), pas choisi ; puis le bouton d'abonnement.
    expect(find.textContaining('Exemple : coupon du'), findsOneWidget);
    expect(find.text('Gagné'), findsOneWidget);
    expect(find.text('Lens – Lyon'), findsOneWidget);
    await tester.ensureVisible(find.text('Débloquer · 2${nbsp}000 F pour 30 jours'));
    await tester.tap(find.text('Débloquer · 2${nbsp}000 F pour 30 jours'));
    await tester.pumpAndSettle();
    expect(find.text('Premium · 30 jours'), findsOneWidget); // « Passer Premium » directement
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
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Se déconnecter'), 200);
    await tester.pumpAndSettle();
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
    expect(find.text('J\'ai déjà un compte'), findsOneWidget); // retour à l'accueil
  });

  testWidgets('connexion Google : première fois, pays par défaut Côte d\'Ivoire, 18 ans, puis réussite', (
    tester,
  ) async {
    final google = FakeGoogle();
    final (state, server) = await startApp(tester, google: google);
    // Google sur l'écran suivant l'accueil (demandé le 07/11/2026).
    expect(find.text('Continuer avec Google'), findsNothing);
    await tester.tap(find.text('Créer mon compte gratuit'));
    await tester.pumpAndSettle();
    expect(find.text('Continuer avec Google'), findsOneWidget);

    google.next = null; // fenêtre de Google fermée : rien ne se passe
    await tester.tap(find.text('Continuer avec Google'));
    await tester.pumpAndSettle();
    expect(find.text('Continuer avec Google'), findsOneWidget);

    google.next = 'jeton-google';
    await tester.tap(find.text('Continuer avec Google'));
    await tester.pumpAndSettle();
    expect(find.text('kossi@gmail.com · compte Google lié'), findsOneWidget);
    expect(find.text("Côte d'Ivoire"), findsOneWidget); // pays proposé d'abord
    await tester.tap(find.text('Commencer'));
    await tester.pumpAndSettle();
    expect(find.textContaining('18 ans ou plus pour utiliser'), findsOneWidget);
    expect(server.googleSignups, isEmpty);

    await tester.tap(find.byType(Checkbox));
    await tester.tap(find.text('Commencer'));
    await tester.pumpAndSettle();
    expect(server.googleSignups.single, {'id_token': 'jeton-google', 'country': 'CI', 'adult': true});
    expect(find.text('Voir les matchs du jour'), findsOneWidget);
    expect(find.textContaining('Bienvenue, Kossi'), findsOneWidget);
    await tester.tap(find.text('Voir les matchs du jour'));
    await tester.pumpAndSettle();
    expect(state.welcome, isFalse);
    expect(find.text('Lyon'), findsOneWidget); // matchs du jour
  });

  testWidgets('connexion Google : compte connu, directement connecté', (tester) async {
    final google = FakeGoogle();
    final (state, server) = await startApp(tester, google: google);
    server.googleAccounts.add('jeton-google');
    await tester.tap(find.text('J\'ai déjà un compte'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continuer avec Google'));
    await tester.pumpAndSettle();
    expect(state.me?.displayName, 'Kossi');
    expect(find.text('Voir les matchs du jour'), findsOneWidget);
  });

  testWidgets('version web sur téléphone : retour de Google après redirection', (tester) async {
    // Démarrage ordinaire (aucune connexion Google commencée) : Firebase n'est pas
    // attendu, rien ne reprend même si un ancien résultat traîne.
    final (plain, _) = await startApp(tester, google: FakeGoogle()..redirect = 'jeton-google');
    expect(plain.googleSignup, isNull);

    // Pas connecté : la connexion reprend (compte Google inconnu → « Presque prêt »).
    final (state, _) = await startApp(
      tester,
      google: FakeGoogle()..redirect = 'jeton-google',
      googleRedirectPending: true,
    );
    expect(state.googleSignup?.email, 'kossi@gmail.com');

    // Connecté : la demande venait du Profil, le compte Google est lié.
    final (_, server) = await startApp(
      tester,
      loggedIn: true,
      google: FakeGoogle()..redirect = 'jeton-google',
      googleRedirectPending: true,
    );
    expect(server.googleLinked, isTrue);
    expect(find.text('Compte Google lié.'), findsOneWidget);
  });

  testWidgets('numéro : indicatif +225 déjà mis, oubli du mot de passe par WhatsApp', (tester) async {
    final opened = <Uri>[];
    final (state, _) = await startApp(
      tester,
      google: FakeGoogle(),
      openUrl: (url) async {
        opened.add(url);
        return true;
      },
    );
    await tester.tap(find.text('J\'ai déjà un compte'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Numéro de téléphone'));
    await tester.pumpAndSettle();
    expect(find.text('+225'), findsOneWidget);
    await tester.enterText(find.byType(TextField).at(0), '05 00 00 00 01');
    await tester.tap(find.text('Mot de passe oublié ?'));
    await tester.pumpAndSettle();
    expect(find.text('+225 05 00 00 00 01'), findsOneWidget); // numéro du compte repris
    await tester.tap(find.text('Écrire sur WhatsApp'));
    await tester.pumpAndSettle();
    expect(opened.single.host, 'wa.me');
    expect(opened.single.path, '/2250500649904');
    expect(opened.single.queryParameters['text'], contains('+225 05 00 00 00 01'));

    // Autre pays : l'indicatif se change, le joueur ne tape que son numéro.
    await tester.tap(find.text('+225'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Togo'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).at(1), 'motdepasse');
    await tester.tap(find.text('Se connecter'));
    await tester.pumpAndSettle();
    expect(state.me?.displayName, 'Kossi');
  });

  testWidgets('profil : lier puis délier Google, aide WhatsApp', (tester) async {
    final opened = <Uri>[];
    final (_, server) = await startApp(
      tester,
      loggedIn: true,
      google: FakeGoogle(),
      openUrl: (url) async {
        opened.add(url);
        return true;
      },
    );
    await tab(tester, HomeTab.moi);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Lier mon compte Google'), 200);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Lier mon compte Google'));
    await tester.pumpAndSettle();
    expect(server.googleLinked, isTrue);
    await tester.ensureVisible(find.text('Google lié'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Google lié'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Délier'));
    await tester.pumpAndSettle();
    expect(server.googleLinked, isFalse);

    await tester.scrollUntilVisible(find.text('Aide · WhatsApp'), 200);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Aide · WhatsApp'));
    await tester.pumpAndSettle();
    expect(opened.single.toString(), startsWith('https://wa.me/2250500649904?text='));
  });

  /// Relevé du direct du match 7 (message du WebSocket, ou GET /live/feed).
  Map<String, dynamic> feedOf(int minute, int home, String at, {String status = '2H', Map? chances}) => {
    'type': 'live',
    'at': at,
    'matches': [
      {
        'id': 7,
        'status': 'scheduled',
        'api_status': status,
        'minute': minute,
        'extra': 0,
        'home': home,
        'away': 1,
        'updated_at': at,
        'goals': [
          {'minute': 23, 'side': 'home', 'player': 'Calvert-Lewin', 'own_goal': false},
        ],
        'reds': [],
        'chances': chances ?? {},
      },
    ],
  };

  testWidgets('direct : mis à jour par le relevé, sans recharger l\'écran ; 3 requêtes par minute au plus', (
    tester,
  ) async {
    final (state, server) = await startApp(tester, loggedIn: true);
    MatchInfo.now = () => DateTime.utc(2026, 10, 10, 20, 40);
    server.matchNow = {
      ...FakeServer.match,
      'api_status': '2H',
      'live_minute': 63,
      'live_home_goals': 2,
      'live_away_goals': 1,
      'live_updated_at': '2026-10-10T20:39:20Z',
    };
    await tester.tap(find.text('Lens').first);
    await tester.pumpAndSettle();
    expect(find.text('2 – 1'), findsOneWidget);
    expect(find.text('Mis à jour il y a 40 s'), findsOneWidget);

    // But : le relevé arrive par le WebSocket ; score, minute et chances changent sans
    // recharger prévision, cotes, analyse ni choix du moteur.
    server.calls.clear();
    state.receiveSocketMessage(
      jsonEncode(
        feedOf(
          70,
          3,
          '2026-10-10T20:40:00Z',
          chances: {'1X2||home': 0.91, '1X2||draw': 0.07, '1X2||away': 0.02, 'OU|3.5|over': 0.4},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('3 – 1'), findsOneWidget);
    expect(find.text('EN DIRECT · 70\''), findsOneWidget);
    expect(find.text('Mis à jour à l\'instant'), findsOneWidget);
    expect(find.text('91 %'), findsOneWidget); // chances du relevé, sans requête
    expect(state.unread, 0); // un relevé n'est pas une notification
    // L'onglet En direct (statistiques) ; sous l'écran, la liste voit le match commencer et
    // lit une fois mes paris en cours (★).
    expect(server.calls, unorderedEquals(['GET /matches/7/live', 'GET /bets']));

    // Sans WebSocket (ici, comme pour un invité) : GET /live/feed toutes les 30 s, rien
    // d'autre ; jamais la liste des matchs ni l'analyse.
    server.calls.clear();
    server.liveFeed = feedOf(71, 4, '2026-10-10T20:41:00Z');
    await tester.pump(const Duration(seconds: 31));
    await tester.pumpAndSettle();
    expect(find.text('4 – 1'), findsOneWidget);
    for (var i = 0; i < 3; i += 1) {
      await tester.pump(const Duration(seconds: 30));
      await tester.pumpAndSettle();
    }
    // 2 minutes : 4 relevés lus, l'onglet En direct relu une fois (le relevé n'a changé
    // qu'une fois) : au plus 3 requêtes par minute.
    expect(server.calls.where((c) => c == 'GET /live/feed').length, 4);
    expect(server.calls.length, lessThanOrEqualTo(6));
    expect(
      server.calls.where(
        (c) =>
            c.contains('/predictions/upcoming') ||
            c.contains('/prediction') ||
            c.contains('/offer') ||
            c.contains('/analysis') ||
            c.contains('/picks'),
      ),
      isEmpty,
    );

    // Un relevé plus ancien que l'écran ne fait pas revenir en arrière.
    state.receiveSocketMessage(jsonEncode(feedOf(65, 2, '2026-10-10T20:35:00Z')));
    await tester.pumpAndSettle();
    expect(find.text('4 – 1'), findsOneWidget);

    // Application en arrière-plan : plus aucune requête.
    state.didChangeAppLifecycleState(AppLifecycleState.paused);
    server.calls.clear();
    await tester.pump(const Duration(seconds: 61));
    await tester.pumpAndSettle();
    expect(server.calls, isEmpty);
    server.liveFeed = feedOf(80, 5, '2026-10-10T20:50:00Z');
    state.didChangeAppLifecycleState(AppLifecycleState.resumed); // retour : relevé lu une fois
    await tester.pumpAndSettle();
    expect(find.text('5 – 1'), findsOneWidget);
    navigatorKey.currentState!.pop();
    await tester.pumpAndSettle();
    MatchInfo.now = DateTime.now;
  });

  testWidgets('direct : liste des matchs mise à jour par le relevé, buteur et chances sans requête', (
    tester,
  ) async {
    final (state, server) = await startApp(tester, loggedIn: true);
    MatchInfo.now = () => DateTime.utc(2026, 10, 10, 19, 20);
    server.calls.clear();
    // Le match commence après le chargement de la liste : il passe « En direct » seul.
    state.receiveSocketMessage(
      jsonEncode(
        feedOf(
          20,
          1,
          '2026-10-10T19:20:00Z',
          status: '1H',
          chances: {'1X2||home': 0.62, '1X2||draw': 0.25, '1X2||away': 0.13},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('20\''), findsOneWidget);
    expect(find.text('1 – 1'), findsOneWidget);
    expect(find.textContaining('Calvert-Lewin'), findsOneWidget);
    expect(find.textContaining('62\u00a0%'), findsOneWidget);
    // Chargés une fois pour ce nouveau match en cours (buts, chances, mes paris), jamais
    // toute la liste.
    expect(server.calls.where((c) => c.contains('/predictions/upcoming')), isEmpty);
    server.calls.clear();
    state.receiveSocketMessage(jsonEncode(feedOf(21, 2, '2026-10-10T19:21:00Z', status: '1H')));
    await tester.pumpAndSettle();
    expect(find.text('2 – 1'), findsOneWidget);
    expect(server.calls, isEmpty);
    MatchInfo.now = DateTime.now;
  });

  testWidgets('direct : coup d\'envoi imminent, puis retardé, puis onglet En direct au coup d\'envoi', (
    tester,
  ) async {
    final (state, server) = await startApp(tester, loggedIn: true);
    // 19 h 03 : l'heure est passée, la source n'a pas encore donné le coup d'envoi.
    MatchInfo.now = () => DateTime.utc(2026, 10, 10, 19, 3);
    await tester.drag(find.byType(ListView).first, const Offset(0, 400));
    await tester.pumpAndSettle();
    expect(find.textContaining('COUP D\'ENVOI IMMINENT'), findsWidgets);

    await tester.tap(find.text('Lens').first);
    await tester.pumpAndSettle();
    expect(find.text('● Coup d\'envoi imminent'), findsOneWidget);
    expect(find.text('Chances'), findsOneWidget);

    // 19 h 15 : toujours pas commencé (heure à confirmer) ; paris toujours fermés.
    MatchInfo.now = () => DateTime.utc(2026, 10, 10, 19, 15);
    state.receiveSocketMessage(jsonEncode(feedOf(0, 0, '2026-10-10T19:15:00Z', status: 'NS')));
    await tester.pumpAndSettle();
    expect(find.text('Coup d\'envoi retardé (heure à confirmer)'), findsOneWidget);
    expect(find.text('● Coup d\'envoi imminent'), findsNothing);

    server.matchLive = {'status': '1H', 'minute': 4, 'extra': 0, 'events': [], 'stats': {}, 'lineups': []};
    state.receiveSocketMessage(jsonEncode(feedOf(4, 0, '2026-10-10T19:19:00Z', status: '1H')));
    await tester.pumpAndSettle();
    expect(find.text('0 – 1'), findsOneWidget);
    expect(find.text('En direct'), findsOneWidget);
    expect(find.text('Résumé'), findsOneWidget); // onglet En direct ouvert
    navigatorKey.currentState!.pop();
    await tester.pumpAndSettle();
    MatchInfo.now = DateTime.now;
  });

  test('mis à jour il y a… ; match proche, imminent, retardé', () {
    final at = DateTime.utc(2026, 10, 10, 20);
    expect(UpdatedAgo.label(at, at.add(const Duration(seconds: 2))), 'Mis à jour à l\'instant');
    expect(UpdatedAgo.label(at, at.add(const Duration(seconds: 40))), 'Mis à jour il y a 40 s');
    expect(UpdatedAgo.label(at, at.add(const Duration(minutes: 3))), 'Mis à jour il y a 3 min');
    expect(UpdatedAgo.label(null, at), '');
    final m = MatchInfo(FakeServer.match);
    MatchInfo.now = () => DateTime.utc(2026, 10, 10, 18, 49);
    expect((m.liveSoon, m.awaitingKickoff), (false, false));
    MatchInfo.now = () => DateTime.utc(2026, 10, 10, 18, 51);
    expect((m.liveSoon, m.awaitingKickoff, m.when), (true, false, '19:00'));
    MatchInfo.now = () => DateTime.utc(2026, 10, 10, 19, 5);
    expect((m.liveSoon, m.awaitingKickoff, m.when), (true, true, 'Coup d\'envoi imminent'));
    MatchInfo.now = () => DateTime.utc(2026, 10, 10, 19, 40);
    expect((m.liveSoon, m.kickoffDelayed, m.started, m.when), (true, true, true, 'Coup d\'envoi retardé'));
    MatchInfo.now = () => DateTime.utc(2026, 10, 10, 22, 30);
    expect((m.liveSoon, m.kickoffDelayed), (false, false));
    MatchInfo.now = DateTime.now;
  });

  testWidgets('onglet caché : Mes paris ne se recharge pas pendant que la liste est affichée', (
    tester,
  ) async {
    final (_, server) = await startApp(tester, loggedIn: true);
    server.calls.clear();
    for (var i = 0; i < 3; i += 1) {
      await tester.pump(const Duration(seconds: 61));
      await tester.pumpAndSettle();
    }
    expect(server.calls.where((c) => c.contains('/bets') || c.contains('/me/wallet')), isEmpty);
  });

  test('chances en direct : jamais 100 % ni 0 %', () {
    expect(chancePercent(0.9996), '> 99 %');
    expect(chancePercent(1.0), '> 99 %');
    expect(chancePercent(0.0), '< 1 %');
    expect(chancePercent(0.004), '< 1 %');
    expect(chancePercent(0.42), '42 %');
  });

  testWidgets('notification d\'un match de coupon touchée : Mes paris', (tester) async {
    final (_, server) = await startApp(tester, loggedIn: true);
    server.notifications.add({
      'id': 9,
      'kind': 'bet_live',
      'title': '🟢 C\'est parti : Lens - Lyon',
      'body': 'Suis ton coupon en direct.',
      'data': <String, dynamic>{'bet_id': 57},
      'created_at': DateTime.now().toUtc().toIso8601String(),
      'read_at': '2026-11-13T16:00:00Z',
    });
    await tab(tester, HomeTab.today); // cloche du tableau de bord (maquette 35)
    await tester.tap(find.byTooltip('Notifications'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('C\'est parti : Lens - Lyon'));
    await tester.pumpAndSettle();
    expect(find.text('C\'est parti : Lens - Lyon'), findsNothing); // liste refermée
    expect(find.textContaining('En cours ('), findsWidgets); // onglet Mes paris
  });

  testWidgets('fiabilité des coupons en direct : entrée si publié, annoncé contre gagné par moment', (
    tester,
  ) async {
    final (_, server) = await startApp(tester, loggedIn: true);
    server.liveReliability = {
      'published': true,
      'total': 412,
      'stake': 1000,
      'profit': -12500,
      'trial': false,
      'trial_settled': 200,
      'profiles': {
        'Sûr': [
          {
            'moment': 'mi-temps',
            'count': 300,
            'announced': 0.83,
            'won': 0.84,
            'margin': 0.043,
            'fair': true,
            'profit': 4200,
          },
          {'moment': "60'", 'count': 112, 'announced': 0.82, 'won': 0.70, 'margin': 0.073, 'fair': false},
        ],
      },
    };
    final context = tester.element(find.byType(Scaffold).first);
    Navigator.of(
      context,
      rootNavigator: true,
    ).push(MaterialPageRoute(builder: (_) => const ReliabilityScreen()));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Coupons en direct'), 200);
    await tester.tap(find.text('Coupons en direct'));
    await tester.pumpAndSettle();
    expect(find.text('Mi-temps'), findsOneWidget);
    // Bilan en argent (décision du 13/11) : 1 000 F sur chaque proposition réglée.
    expect(find.textContaining('Si tu avais misé 1\u00A0000\u00A0F'), findsOneWidget);
    expect(find.textContaining('−12\u00A0500\u00A0F'), findsOneWidget);
    expect(find.textContaining('bilan +4\u00A0200\u00A0F'), findsOneWidget);
    expect(find.text('83\u00A0%'), findsOneWidget);
    expect(find.text('84\u00A0%'), findsOneWidget);
    expect(find.text('300'), findsOneWidget);
    expect(find.text('juste'), findsOneWidget);
    expect(find.text('à surveiller'), findsOneWidget); // 60e : 70 % gagnés pour 82 % annoncés
    await tester.tap(find.text('Audacieux'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Pas encore de coupon en direct réglé'), findsOneWidget);
  });

  testWidgets('coupon en direct : fenêtre ouverte sans cote assez généreuse, « En test »', (tester) async {
    final (_, server) = await startApp(tester, loggedIn: true);
    server.liveCoupons = {
      'published': true,
      'odds_source': 'indicative',
      'matches': [],
      'combos': {},
      'open': 1,
      'trial': true,
    };
    final context = tester.element(find.byType(Scaffold).first);
    Navigator.of(
      context,
      rootNavigator: true,
    ).push(MaterialPageRoute(builder: (_) => const LiveCouponScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('Aucun coupon intéressant pendant cette fenêtre'), findsOneWidget);
    expect(find.text('En test'), findsOneWidget);
    expect(find.textContaining('Aucun match ouvert'), findsNothing);
  });

  testWidgets('coupon en direct : carte, combiné Sûr ajouté, à placer avant la fermeture', (tester) async {
    final (_, server) = await startApp(tester, loggedIn: true);
    Map<String, dynamic> sel(int id, String market, String line, String pick, double p, String odds) => {
      'match_id': id,
      'market': market,
      'line': line,
      'selection': pick,
      'probability': p,
      'odds': odds,
    };
    final a = sel(11, 'DC', '', '1X', 0.89, '1.10');
    final b = sel(12, 'OU', '2.5', 'under', 0.80, '1.22');
    server.liveCoupons = {
      'published': true,
      'odds_source': 'indicative',
      'matches': [
        {
          'match_id': 11,
          'home': 'RD Congo',
          'away': 'Sierra Leone',
          'status': 'HT',
          'minute': 45,
          'score': [1, 0],
          'moment': 'mi-temps',
          'closes_at': 50,
          'picks': {
            'Sûr': a,
            'Équilibré': {'locked': true},
          },
        },
        {
          'match_id': 12,
          'home': 'Bénin',
          'away': 'Togo',
          'status': '2H',
          'minute': 61,
          'score': [0, 0],
          'moment': "60'",
          'closes_at': 63,
          'picks': {'Sûr': b},
        },
      ],
      'combos': {
        'Sûr': {
          'size': 2,
          'probability': 0.712,
          'odds': '1.342',
          'locked': false,
          'below_odds': true, // 71 % contre 75 % selon la cote
          'selections': [a, b],
        },
        'Équilibré': {'size': 2, 'probability': 0.36, 'odds': '2.6', 'locked': true, 'selections': []},
      },
    };
    await tab(tester, HomeTab.coupon);
    await tester.pumpAndSettle();
    expect(find.text('Coupon en direct · 2 matchs'), findsOneWidget);
    await tester.tap(find.text('Coupon en direct · 2 matchs'));
    await tester.pumpAndSettle();
    expect(find.text('Sûr · 2'), findsOneWidget);
    expect(find.text('71 %'), findsOneWidget);
    expect(find.text('cote ≈ 1,34'), findsOneWidget); // cote indicative
    expect(find.text('Premium'), findsOneWidget); // Équilibré réservé
    expect(find.textContaining('Sûr : moins de 2,5 buts'), findsOneWidget);
    expect(find.text('encore 2 min'), findsOneWidget);
    expect(find.text('jusqu\'à la 50e'), findsOneWidget);

    await tester.tap(find.text('Sûr · 2'));
    await tester.pumpAndSettle();
    expect(find.text('Sûr · combiné de 2 matchs'), findsOneWidget);
    expect(find.textContaining('Le moteur est moins confiant que la cote : 71'), findsOneWidget);
    expect(find.textContaining('Cotes indicatives : relevées chez un autre bookmaker'), findsOneWidget);
    await tester.tap(find.text('Ajouter à mon coupon'));
    await tester.pumpAndSettle();
    expect(find.textContaining('à placer avant la 50e minute'), findsOneWidget);
    expect(find.textContaining('a commencé'), findsNothing); // pas « paris fermés »

    await tester.ensureVisible(find.textContaining('Placer le pari').first);
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Placer le pari').first);
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Confirmer').last);
    await tester.pumpAndSettle();
    expect(server.placedBets.single['selections'], [
      {'match_id': 11, 'market': 'DC', 'line': '', 'selection': '1X', 'odds': '1.10'},
      {'match_id': 12, 'market': 'OU', 'line': '2.5', 'selection': 'under', 'odds': '1.22'},
    ]);
  });

  testWidgets('maquette 35 : barre du bas et tableau de bord complet', (tester) async {
    final (state, server) = await startApp(tester, loggedIn: true, startTab: HomeTab.today);
    await tester.binding.setSurfaceSize(const Size(430, 2600));
    await tester.pumpAndSettle();
    for (final label in ['Aujourd\'hui', 'Matchs', 'Paris', 'Moi']) {
      expect(find.text(label), findsWidgets);
    }
    expect(find.bySemanticsLabel('Créer'), findsOneWidget); // « + » central, sans libellé
    // En-tête, solde et ses 4 indicateurs, sans compteurs inventés.
    expect(find.text('Tableau de bord'), findsOneWidget);
    expect(find.text('98${nbsp}000${nbsp}F'), findsOneWidget);
    expect(find.textContaining('La courbe apparaîtra'), findsNothing); // courbe jusqu'à aujourd'hui
    expect(find.text('3 / 6'), findsOneWidget); // paris gagnés sur 30 jours
    expect(find.text('56$nbsp% / 61$nbsp%'), findsOneWidget); // moteur : réalisé / annoncé
    expect(find.text('3${nbsp}500${nbsp}F'), findsOneWidget); // plan de jeu : misés cette semaine
    expect(find.text('sur 5${nbsp}000${nbsp}F cette sem.'), findsOneWidget);
    // Occasions du jour : pastille et alerte de cote.
    expect(find.text('OCCASIONS DU JOUR'), findsOneWidget);
    expect(find.text('+5 pts'), findsOneWidget);
    expect(find.text('Créer une alerte de cote'), findsOneWidget);
    // Où le moteur tient parole (30 j) : réalisé par marché.
    expect(find.text('OÙ LE MOTEUR TIENT PAROLE (30 J)'), findsOneWidget);
    expect(find.text('91$nbsp%'), findsOneWidget);
    // Le joueur a déjà des paris : pas de cartes « Pour commencer ».
    expect(find.text('POUR COMMENCER'), findsNothing);
    expect(server.calls, contains('GET /me/dashboard'));

    // « Créer » : tous les outils ; Mon coupon ouvre sa page, « Créer » reste allumé.
    await tab(tester, HomeTab.create);
    for (final tool in [
      'Composer moi-même',
      'Coupon intelligent',
      'Coupons du jour',
      'Grosse cote',
      'Montante',
      'Coupon en direct',
    ]) {
      expect(find.text(tool), findsWidgets);
    }
    expect(find.text('En test'), findsOneWidget); // coupon en direct encore en essai
    // Coupon vide : « Composer moi-même » ouvre les matchs ; avec des sélections : Mon coupon.
    await tester.tap(find.text('Composer moi-même'));
    await tester.pumpAndSettle();
    expect(tester.state<HomeShellState>(find.byType(HomeShell)).index, HomeTab.matchs);
    await tester.tap(find.text('1,85').first);
    await tester.pumpAndSettle();
    await tab(tester, HomeTab.create);
    expect(find.text('1 sélection en attente.'), findsOneWidget);
    await tester.tap(find.text('Mon coupon'));
    await tester.pumpAndSettle();
    expect(tester.state<HomeShellState>(find.byType(HomeShell)).index, HomeTab.coupon);
    expect(state.montanteMode, isFalse);
  });

  testWidgets('maquette 30 : mon plan de jeu, budget modifié', (tester) async {
    final (_, server) = await startApp(tester, loggedIn: true, startTab: HomeTab.today);
    await tester.binding.setSurfaceSize(const Size(430, 2600));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Plan de jeu'));
    await tester.pumpAndSettle();
    expect(find.text('Mon plan de jeu'), findsOneWidget);
    expect(find.text('misés sur 5${nbsp}000${nbsp}F prévus'), findsOneWidget);
    expect(find.text('70$nbsp%'), findsOneWidget);
    expect(find.text('Faire une pause'), findsOneWidget);
    expect(find.textContaining('ne se relèvent qu\'au bout de 24 h'), findsOneWidget);
    await tester.tap(find.text('Budget par semaine'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '4000');
    await tester.tap(find.text('Enregistrer'));
    await tester.pumpAndSettle();
    expect(server.planUpdates, [
      {'weekly_budget': 4000},
    ]);
    expect(find.text('misés sur 4${nbsp}000${nbsp}F prévus'), findsOneWidget);
  });

  testWidgets('maquette 29 : mes alertes de cote', (tester) async {
    final (_, server) = await startApp(tester, loggedIn: true, startTab: HomeTab.today);
    await tester.binding.setSurfaceSize(const Size(430, 2600));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Créer une alerte de cote'));
    await tester.pumpAndSettle();
    expect(find.text('Mes alertes de cote'), findsOneWidget);
    expect(find.text('≥ 1,95'), findsOneWidget);
    expect(find.text('1,85 (54$nbsp%)'), findsOneWidget);
    expect(find.text('dès qu\'un pari dépasse la cote de 8 points'), findsOneWidget);
    expect(find.text('cote 1,79 → 1,92'), findsOneWidget);
    expect(find.text('Ajouter au coupon'), findsOneWidget);
    expect(find.text('Au plus une alerte par match, jamais entre 23 h et 8 h.'), findsOneWidget);
    await tester.tap(find.text('5 points'));
    await tester.pumpAndSettle();
    expect(server.alertCalls.single, contains('"min_gap":0.05'));
  });

  testWidgets('étape B : nouveau joueur, trois cartes de départ au lieu de zéros', (tester) async {
    final (_, server) = await startApp(tester, loggedIn: true, startTab: HomeTab.today);
    server.dashboard = {
      ...server.dashboard,
      'curve': [
        {'day': '2026-10-09', 'balance': 100000},
      ],
      'engine_above_odds': <Object>[],
    };
    server.bets = [];
    server.freshPlayer = true;
    server.dashboard = {
      ...server.dashboard,
      'last_30_days': {'settled': 0, 'won': 0, 'staked': 0, 'returned': 0, 'yield': null},
    };
    await tab(tester, HomeTab.matchs);
    await tab(tester, HomeTab.today);
    expect(find.text('POUR COMMENCER'), findsOneWidget);
    expect(find.text('Un premier pari, en argent fictif'), findsOneWidget);
    expect(find.text('OCCASIONS DU JOUR'), findsOneWidget); // dit franchement qu'il n'y en a pas
  });
}
