// État global : adresse du serveur, session, profil, coupon, notifications en direct.
import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../labels.dart';

/// Messages éphémères (erreurs, confirmations, notifications reçues).
final messengerKey = GlobalKey<ScaffoldMessengerState>();

void showMessage(String text, {bool error = false}) {
  messengerKey.currentState
    ?..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(text), backgroundColor: error ? const Color(0xFF3A1430) : null));
}

/// Serveur intégré à l'APK (--dart-define=FP_SERVER=https://…) : le serveur
/// distant. Sans valeur : le serveur Termux du même téléphone.
const builtInServer = String.fromEnvironment('FP_SERVER');

/// Numéro de construction de l'APK (GitHub Actions) ; 0 en développement : pas de
/// vérification de mise à jour.
const appBuild = int.fromEnvironment('FP_BUILD');

/// Adresse par défaut : en version web, le serveur qui a servi la page ;
/// sinon le serveur intégré à l'APK, ou à défaut celui de Termux.
String defaultServer() {
  if (kIsWeb) {
    final base = Uri.base;
    if (base.scheme.startsWith('http')) return base.origin;
  }
  return builtInServer.isNotEmpty ? builtInServer : 'http://127.0.0.1:8000';
}

/// Ouvre le WebSocket ; `null` désactive le direct (tests).
typedef SocketFactory = WebSocketChannel? Function(Uri uri);

/// Notification push reçue application ouverte : « titre — texte » et type.
typedef PushMessage = ({String text, String? kind});

/// Notifications push du téléphone (Firebase sur Android ; absent ailleurs et en test).
abstract class PushBridge {
  /// Jeton de l'appareil, ou null si l'utilisateur refuse les notifications.
  Future<String?> token();
  Stream<String> get tokenRefresh;

  /// Notification touchée alors que l'application tournait en arrière-plan.
  Stream<void> get opened;

  /// L'application a été lancée en touchant une notification.
  Future<bool> openedAtLaunch();

  /// Notifications reçues pendant que l'application est ouverte.
  Stream<PushMessage> get foreground;
}

/// Ouvre une page dans le navigateur (guichet de paiement) ; faux en test.
typedef UrlOpener = Future<bool> Function(Uri url);

Future<bool> _openInBrowser(Uri url) => launchUrl(url, mode: LaunchMode.externalApplication);

class AppState extends ChangeNotifier with WidgetsBindingObserver {
  AppState({
    required this.api,
    this.socketFactory,
    this.push,
    UrlOpener? openUrl,
    this.build = appBuild,
    this.android = !kIsWeb,
  }) : openUrl = openUrl ?? _openInBrowser;

  /// Version installée (comparée à GET /app/version) ; APK Android seulement.
  final int build;
  final bool android;

  /// Nouvelle version publiée sur le serveur (null : à jour ou inconnue).
  final update = ValueNotifier<AppUpdate?>(null);

  final ApiClient api;
  final SocketFactory? socketFactory;
  final PushBridge? push;
  final UrlOpener openUrl;

  /// Paiement Premium ouvert dans le navigateur, vérifié au retour dans l'application.
  int? pendingPayment;
  SharedPreferences? _prefs;

  bool ready = false;
  Me? me;
  final List<CouponItem> coupon = [];
  int unread = 0;

  /// Incrémenté quand l'utilisateur touche une notification : l'écran des
  /// notifications s'ouvre.
  final notificationOpened = ValueNotifier<int>(0);
  String? _pushToken;
  StreamSubscription<String>? _pushRefreshSub;
  StreamSubscription<void>? _pushOpenedSub;
  StreamSubscription<PushMessage>? _pushForegroundSub;

  WebSocketChannel? _socket;
  StreamSubscription<dynamic>? _socketSub;
  Timer? _reconnect;
  Timer? _ping;

  bool get loggedIn => api.token != null && me != null;
  bool get premium => me?.plan.premium ?? false;
  Set<String> get freeMarkets {
    final fm = me?.plan.freeMarkets;
    return fm == null || fm.isEmpty ? defaultFreeMarkets : fm;
  }

  bool marketAllowed(String market) => premium || freeMarkets.contains(market);

  static const _kServer = 'server_url';
  static const _kToken = 'token';

  Future<void> init() async {
    WidgetsBinding.instance.addObserver(this);
    _prefs = await SharedPreferences.getInstance();
    api.baseUrl = _prefs!.getString(_kServer) ?? defaultServer();
    api.token = _prefs!.getString(_kToken);
    unawaited(checkUpdate());
    if (api.token != null) {
      try {
        await refreshMe();
        _connectSocket();
        unawaited(refreshUnread());
        unawaited(_registerPush(atLaunch: true));
      } on ApiException catch (e) {
        if (e.isUnauthorized) await _clearSession();
        // Serveur injoignable : on garde la session, l'écran d'accueil affichera l'erreur.
      }
    }
    ready = true;
    notifyListeners();
  }

  Future<void> setServer(String url) async {
    var u = url.trim();
    if (u.endsWith('/')) u = u.substring(0, u.length - 1);
    if (!u.startsWith('http')) u = 'http://$u';
    api.baseUrl = u;
    await _prefs?.setString(_kServer, u);
    _disconnectSocket();
    if (api.token != null) {
      await refreshMe();
      _connectSocket();
    }
    notifyListeners();
  }

  Future<void> login(String phone, String password) async {
    final r = await api.post('/auth/login', {'phone': phone, 'password': password});
    await _startSession(r['access_token'] as String);
  }

  Future<void> register({
    required String phone,
    required String password,
    required String name,
    required String country,
    required bool adult,
  }) async {
    final r = await api.post('/auth/register', {
      'phone': phone,
      'password': password,
      'display_name': name,
      'country': country,
      'adult': adult,
    });
    await _startSession(r['access_token'] as String);
  }

  Future<void> _startSession(String token) async {
    api.token = token;
    await _prefs?.setString(_kToken, token);
    await refreshMe();
    _connectSocket();
    unawaited(refreshUnread());
    unawaited(_registerPush());
  }

  Future<void> logout() async {
    // Ce téléphone ne reçoit plus les notifications de ce compte.
    final pushToken = _pushToken;
    if (pushToken != null) {
      try {
        await api.post('/me/devices/remove', {'token': pushToken});
      } on ApiException {
        // serveur injoignable : le jeton passera au prochain compte connecté
      }
    }
    await _clearSession();
    notifyListeners();
  }

  /// Suppression définitive du compte (mot de passe redemandé par le serveur).
  Future<void> deleteAccount(String password) async {
    await api.post('/me/delete', {'password': password});
    await _clearSession();
    notifyListeners();
  }

  Future<void> _clearSession() async {
    _disconnectSocket();
    _pushRefreshSub?.cancel();
    _pushRefreshSub = null;
    _pushToken = null;
    api.token = null;
    me = null;
    coupon.clear();
    unread = 0;
    await _prefs?.remove(_kToken);
  }

  Future<void> refreshMe() async {
    try {
      me = Me(await api.get('/me') as Json);
      notifyListeners();
    } on ApiException catch (e) {
      if (e.isUnauthorized) {
        await _clearSession();
        notifyListeners();
      }
      rethrow;
    }
  }

  Future<void> refreshUnread() async {
    if (api.token == null) return;
    try {
      final list = await api.get('/me/notifications', {'unread': true, 'limit': 100}) as List;
      unread = list.length;
      notifyListeners();
    } on ApiException {
      // sans conséquence : le compteur sera mis à jour plus tard
    }
  }

  void setUnread(int n) {
    unread = n;
    notifyListeners();
  }

  // --- Coupon ---------------------------------------------------------------

  bool inCoupon(int matchId, String key) => coupon.any((c) => c.match.id == matchId && c.offer.key == key);

  /// Ajoute une sélection ; une autre sélection du même match est remplacée
  /// (deux sélections d'un même match sont liées : le serveur les refuse).
  String toggleCoupon(MatchInfo match, Offer offer) {
    final existing = coupon.indexWhere((c) => c.match.id == match.id);
    if (existing >= 0 && coupon[existing].offer.key == offer.key) {
      coupon.removeAt(existing);
      notifyListeners();
      return 'Retiré du coupon';
    }
    if (existing >= 0) {
      coupon[existing] = CouponItem(match: match, offer: offer);
      notifyListeners();
      return 'Sélection remplacée : une seule par match dans un combiné';
    }
    if (coupon.length >= 10) return 'Coupon plein (10 sélections au maximum)';
    coupon.add(CouponItem(match: match, offer: offer));
    notifyListeners();
    return 'Ajouté au coupon';
  }

  void removeFromCoupon(CouponItem item) {
    coupon.remove(item);
    notifyListeners();
  }

  void clearCoupon() {
    coupon.clear();
    notifyListeners();
  }

  double get couponOdds => coupon.fold(1.0, (p, c) => p * c.offer.odds);

  // --- Paiement Premium (Mobile Money, CinetPay) -----------------------------

  /// Crée le paiement et ouvre le guichet CinetPay dans le navigateur.
  Future<void> buyPremium() async {
    final payment = await api.post('/payments/premium') as Json;
    pendingPayment = payment['id'] as int;
    final opened = await openUrl(Uri.parse(payment['payment_url'] as String));
    if (!opened) {
      throw ApiException(0, 'browser', 'Impossible d\'ouvrir la page de paiement.');
    }
  }

  /// État du paiement en cours : « accepted », « refused », « error », « pending ».
  Future<String?> checkPayment() async {
    final id = pendingPayment;
    if (id == null) return null;
    final payment = await api.get('/payments/$id') as Json;
    final status = payment['status'] as String;
    if (status != 'pending') {
      pendingPayment = null;
      await refreshMe();
    }
    return status;
  }

  /// Demande au serveur la dernière version de l'application ; silencieux en cas d'échec.
  Future<void> checkUpdate() async {
    if (!android || build <= 0) return;
    try {
      final v = await api.get('/app/version') as Json;
      final latest = (v['build'] as num?)?.toInt() ?? 0;
      if (latest <= build) return;
      update.value = AppUpdate(
        build: latest,
        notes: (v['notes'] as String?) ?? '',
        mandatory: build < ((v['minimum_build'] as num?)?.toInt() ?? 0),
        sizeMb: (((v['size'] as num?) ?? 0) / 1e6).round(),
        url: Uri.parse(api.baseUrl).resolve(v['download_path'] as String),
      );
    } catch (_) {
      // Serveur injoignable ou ancien : on réessaiera au prochain retour dans l'application.
    }
  }

  Future<void> downloadUpdate() async {
    final u = update.value;
    if (u != null) await openUrl(u.url);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Retour du guichet de paiement : vérification immédiate.
    if (state == AppLifecycleState.resumed && pendingPayment != null) {
      unawaited(_announcePayment());
    }
    if (state == AppLifecycleState.resumed) unawaited(checkUpdate());
  }

  Future<void> _announcePayment() async {
    try {
      final status = await checkPayment();
      final text = switch (status) {
        'accepted' => 'Paiement reçu : Premium est activé.',
        'refused' => 'Paiement refusé : aucun montant débité.',
        'error' => 'Paiement non conforme : contacte l\'administrateur.',
        'pending' => 'Paiement en attente de confirmation par l\'opérateur.',
        _ => null,
      };
      if (text != null) showMessage(text, error: status == 'refused' || status == 'error');
    } on ApiException {
      // vérifié de nouveau au prochain retour, et par le serveur toutes les 10 min
    }
  }

  // --- Notifications push (téléphone fermé) -----------------------------------

  Future<void> _registerPush({bool atLaunch = false}) async {
    final p = push;
    if (p == null || api.token == null) return;
    _pushOpenedSub ??= p.opened.listen((_) => notificationOpened.value += 1);
    // Les notifications de paris arrivent aussi par le direct (WebSocket) : pas de
    // doublon, sauf si le direct est coupé. L'essai de l'administrateur n'existe
    // qu'en push.
    _pushForegroundSub ??= p.foreground.listen((m) {
      if (m.kind == 'test' || _socket == null) showMessage(m.text);
    });
    try {
      if (atLaunch && await p.openedAtLaunch()) notificationOpened.value += 1;
      final token = await p.token();
      if (token == null) return;
      await _sendPushToken(token);
      _pushRefreshSub ??= p.tokenRefresh.listen((t) => unawaited(_sendPushToken(t)));
    } catch (e) {
      // Sans notifications push, l'application reste utilisable.
      debugPrint('Notifications push indisponibles : $e');
    }
  }

  Future<void> _sendPushToken(String token) async {
    if (api.token == null) return;
    try {
      await api.post('/me/devices', {'token': token, 'platform': 'android'});
      _pushToken = token;
    } on ApiException catch (e) {
      debugPrint('Enregistrement du téléphone refusé : ${e.message}');
    }
  }

  // --- Notifications en direct ---------------------------------------------------

  void _connectSocket() {
    if (api.token == null || _socket != null) return;
    try {
      final uri = api.notificationsSocket();
      final socket = socketFactory != null ? socketFactory!(uri) : WebSocketChannel.connect(uri);
      if (socket == null) return;
      _socket = socket;
      _socketSub = socket.stream.listen(
        _onSocketMessage,
        onDone: _scheduleReconnect,
        onError: (_) => _scheduleReconnect(),
        cancelOnError: true,
      );
      _ping = Timer.periodic(const Duration(seconds: 30), (_) {
        try {
          _socket?.sink.add('ping');
        } catch (_) {}
      });
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void _onSocketMessage(dynamic raw) {
    Object? data;
    try {
      data = jsonDecode('$raw');
    } catch (_) {
      return;
    }
    if (data is! Map || data['type'] == 'pong' || data['title'] == null) return;
    unread += 1;
    notifyListeners();
    showMessage('${data['title']} — ${data['body'] ?? ''}');
    // Un pari réglé change le solde.
    unawaited(refreshMe().catchError((_) {}));
  }

  void _scheduleReconnect() {
    _disconnectSocket();
    if (api.token == null) return;
    _reconnect = Timer(const Duration(seconds: 15), _connectSocket);
  }

  void _disconnectSocket() {
    _reconnect?.cancel();
    _ping?.cancel();
    _socketSub?.cancel();
    try {
      _socket?.sink.close();
    } catch (_) {}
    _socket = null;
    _socketSub = null;
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _disconnectSocket();
    _pushRefreshSub?.cancel();
    _pushOpenedSub?.cancel();
    _pushForegroundSub?.cancel();
    notificationOpened.dispose();
    super.dispose();
  }
}

/// Version de l'application plus récente que celle installée.
class AppUpdate {
  AppUpdate({
    required this.build,
    required this.notes,
    required this.mandatory,
    required this.sizeMb,
    required this.url,
  });
  final int build;
  final String notes;
  final bool mandatory;
  final int sizeMb;
  final Uri url;
}
