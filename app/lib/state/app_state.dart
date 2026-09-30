// État global : adresse du serveur, session, profil, coupon, notifications en direct.
import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
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

/// Adresse par défaut : le serveur Termux sur le même téléphone ; en version
/// web, le serveur qui a servi la page.
String defaultServer() {
  if (kIsWeb) {
    final base = Uri.base;
    if (base.scheme.startsWith('http')) return base.origin;
  }
  return 'http://127.0.0.1:8000';
}

/// Ouvre le WebSocket ; `null` désactive le direct (tests).
typedef SocketFactory = WebSocketChannel? Function(Uri uri);

class AppState extends ChangeNotifier {
  AppState({required this.api, this.socketFactory});

  final ApiClient api;
  final SocketFactory? socketFactory;
  SharedPreferences? _prefs;

  bool ready = false;
  Me? me;
  final List<CouponItem> coupon = [];
  int unread = 0;

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
    _prefs = await SharedPreferences.getInstance();
    api.baseUrl = _prefs!.getString(_kServer) ?? defaultServer();
    api.token = _prefs!.getString(_kToken);
    if (api.token != null) {
      try {
        await refreshMe();
        _connectSocket();
        unawaited(refreshUnread());
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
  }

  Future<void> logout() async {
    await _clearSession();
    notifyListeners();
  }

  Future<void> _clearSession() async {
    _disconnectSocket();
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
    _disconnectSocket();
    super.dispose();
  }
}
