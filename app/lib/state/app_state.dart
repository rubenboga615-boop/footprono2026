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
import '../update/installer.dart';

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

/// Choix de l'adresse du serveur : seulement en développement (APK sans serveur intégré).
/// Les joueurs ne voient jamais l'adresse du serveur.
bool get serverChoice => !kIsWeb && builtInServer.isEmpty;

/// Ouvre le WebSocket ; `null` désactive le direct (tests).
typedef SocketFactory = WebSocketChannel? Function(Uri uri);

/// Notification push reçue application ouverte : « titre — texte » et type.
typedef PushMessage = ({String text, String? kind});

/// Notifications push du téléphone (Firebase sur Android ; absent ailleurs et en test).
abstract class PushBridge {
  /// Jeton de l'appareil, ou null si l'utilisateur refuse les notifications.
  Future<String?> token();
  Stream<String> get tokenRefresh;

  /// Notification touchée alors que l'application tournait en arrière-plan (son type).
  Stream<String?> get opened;

  /// L'application a été lancée en touchant une notification.
  Future<bool> openedAtLaunch();

  /// Notifications reçues pendant que l'application est ouverte.
  Stream<PushMessage> get foreground;
}

/// Notifications de la version web, selon le navigateur.
enum WebPushStatus {
  /// Navigateur sans notifications, ou serveur non configuré : rien n'est proposé.
  unavailable,

  /// iPhone dans Safari : il faut d'abord ajouter FootProba à l'écran d'accueil.
  install,

  /// Possible, pas encore autorisé : bouton « Activer ».
  off,
  denied,
  on,
}

/// Notifications de la version web (Firebase Cloud Messaging dans le navigateur).
abstract class WebPushBridge {
  /// État sur ce navigateur ; [vapidKey] : clé publique Web Push donnée par le serveur.
  Future<WebPushStatus> status(String vapidKey);

  /// Jeton du navigateur, si l'autorisation est déjà donnée.
  Future<String?> token();

  /// Demande l'autorisation (à appeler depuis un geste du joueur : exigé sur iPhone)
  /// puis renvoie le jeton ; null si le joueur refuse.
  Future<String?> enable();

  /// Notifications reçues pendant que la page est ouverte.
  Stream<PushMessage> get foreground;
}

/// Connexion avec Google (Firebase sur Android ; absent sur le web et en test).
abstract class GoogleAuthBridge {
  /// Jeton d'identité Firebase, ou null si le joueur ferme la fenêtre de Google.
  Future<String?> idToken();

  /// Version web sur téléphone : Google répond en rechargeant la page ; le jeton
  /// arrive au démarrage suivant (null s'il n'y a pas de connexion en cours).
  Future<String?> redirectResult();
  Future<void> signOut();
}

/// Compte Google sans compte FootProba : écran « Presque prêt » (pays, 18 ans).
typedef GoogleSignup = ({String token, String email, String name});

/// Ouvre une page dans le navigateur (guichet de paiement) ; faux en test.
typedef UrlOpener = Future<bool> Function(Uri url);

Future<bool> _openInBrowser(Uri url) => launchUrl(url, mode: LaunchMode.externalApplication);

class AppState extends ChangeNotifier with WidgetsBindingObserver {
  AppState({
    required this.api,
    this.socketFactory,
    this.push,
    this.webPush,
    this.google,
    UrlOpener? openUrl,
    this.build = appBuild,
    this.android = !kIsWeb,
    ApkInstaller? installer,
  }) : openUrl = openUrl ?? _openInBrowser,
       installer = installer ?? (android && !kIsWeb ? ChannelInstaller() : null);

  /// Version installée (comparée à GET /app/version) ; APK Android seulement.
  final int build;
  final bool android;

  /// Nouvelle version publiée sur le serveur (null : à jour ou inconnue).
  final update = ValueNotifier<AppUpdate?>(null);

  /// Téléchargement de la mise à jour : 0 à 1 (null : aucun en cours).
  final updateProgress = ValueNotifier<double?>(null);
  final ApkInstaller? installer;
  String? _downloadedApk;
  int? _downloadedBuild;

  final ApiClient api;
  final SocketFactory? socketFactory;
  final PushBridge? push;
  final WebPushBridge? webPush;

  /// Notifications de la version web sur ce navigateur (profil : « Activer »).
  final webPushStatus = ValueNotifier<WebPushStatus>(WebPushStatus.unavailable);
  StreamSubscription<PushMessage>? _webForegroundSub;
  final GoogleAuthBridge? google;
  final UrlOpener openUrl;

  /// Compte Google à compléter (pays, 18 ans) avant de créer le compte.
  GoogleSignup? googleSignup;

  /// Écran « Connexion réussie » juste après une connexion avec Google.
  bool welcome = false;
  Uri? _support;

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

  /// Onglet demandé depuis un écran ouvert par-dessus (ex. « Passer Premium » → Profil).
  final tabRequest = ValueNotifier<int?>(null);
  void openTab(int i) {
    tabRequest.value = null;
    tabRequest.value = i;
  }

  /// Type de la dernière notification touchée (« daily_coupons » : écran des coupons du jour).
  String? openedKind;
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
  static const _kExcludedTeams = 'excluded_teams';

  /// Nombre maximum de sélections d'un coupon (comme le serveur).
  static const maxCoupon = 12;

  /// Équipes que l'utilisateur ne veut plus voir dans le Coupon intelligent (id → nom),
  /// mémorisées sur le téléphone.
  final Map<int, String> excludedTeams = {};

  Future<void> init() async {
    WidgetsBinding.instance.addObserver(this);
    _prefs = await SharedPreferences.getInstance();
    api.baseUrl = (serverChoice ? _prefs!.getString(_kServer) : null) ?? defaultServer();
    api.token = _prefs!.getString(_kToken);
    try {
      final raw = _prefs!.getString(_kExcludedTeams);
      if (raw != null) {
        (jsonDecode(raw) as Map<String, dynamic>).forEach((k, v) => excludedTeams[int.parse(k)] = '$v');
      }
    } catch (_) {
      // Préférence illisible : ignorée.
    }
    unawaited(checkUpdate());
    if (api.token != null) {
      try {
        await refreshMe();
        _connectSocket();
        unawaited(refreshUnread());
        unawaited(_registerPush(atLaunch: true));
        unawaited(_registerWebPush());
      } on ApiException catch (e) {
        if (e.isUnauthorized) await _clearSession();
        // Serveur injoignable : on garde la session, l'écran d'accueil affichera l'erreur.
      }
    }
    await _resumeGoogleRedirect();
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

  Future<String?> _googleToken() async {
    final g = google;
    if (g == null) return null;
    try {
      return await g.idToken();
    } catch (_) {
      throw ApiException(0, 'google', 'Connexion Google impossible. Réessaie ou utilise ton numéro.');
    }
  }

  /// Connexion avec Google. Compte Google encore inconnu : [googleSignup] est rempli
  /// (écran « Presque prêt »). Faux si le joueur a fermé la fenêtre de Google.
  Future<bool> signInWithGoogle() async {
    final token = await _googleToken();
    if (token == null) return false;
    await _signInWithGoogleToken(token);
    return true;
  }

  Future<void> _signInWithGoogleToken(String token) async {
    try {
      final r = await api.post('/auth/google', {'id_token': token});
      welcome = true;
      await _startSession(r['access_token'] as String);
    } on ApiException catch (e) {
      if (e.code != 'google_account_unknown') rethrow;
      final d = e.details is Map ? e.details as Map : const {};
      googleSignup = (token: token, email: '${d['email'] ?? ''}', name: '${d['name'] ?? ''}');
      notifyListeners();
    }
  }

  /// Retour de Google après redirection (version web sur téléphone) : connecté, la
  /// demande venait du Profil (lier le compte) ; sinon de l'écran de connexion.
  Future<void> _resumeGoogleRedirect() async {
    final g = google;
    if (g == null) return;
    final String? token;
    try {
      token = await g.redirectResult();
    } catch (_) {
      showMessage('Connexion Google impossible. Réessaie ou utilise ton numéro.', error: true);
      return;
    }
    if (token == null) return;
    try {
      if (me != null) {
        await _linkGoogleToken(token);
        showMessage('Compte Google lié.');
      } else {
        await _signInWithGoogleToken(token);
      }
    } on ApiException catch (e) {
      showMessage(e.message, error: true);
    }
  }

  Future<void> registerWithGoogle({required String country, required bool adult}) async {
    final signup = googleSignup;
    if (signup == null) return;
    final r = await api.post('/auth/google/register', {
      'id_token': signup.token,
      'country': country,
      'adult': adult,
    });
    googleSignup = null;
    welcome = true;
    await _startSession(r['access_token'] as String);
  }

  void cancelGoogleSignup() {
    googleSignup = null;
    unawaited(google?.signOut());
    notifyListeners();
  }

  void closeWelcome() {
    welcome = false;
    notifyListeners();
  }

  /// Lie le compte Google au compte connecté (Premium et solde inchangés).
  Future<bool> linkGoogle() async {
    final token = await _googleToken();
    if (token == null) return false;
    await _linkGoogleToken(token);
    return true;
  }

  Future<void> _linkGoogleToken(String token) async {
    me = Me(await api.post('/me/google', {'id_token': token}) as Json);
    notifyListeners();
  }

  Future<void> unlinkGoogle() async {
    me = Me(await api.delete('/me/google') as Json);
    unawaited(google?.signOut());
    notifyListeners();
  }

  /// Aide FootProba sur WhatsApp (numéro donné par le serveur), message prérempli.
  Future<bool> openSupport(String message) async {
    if (_support == null) {
      try {
        final r = await api.get('/app/support') as Json;
        final url = r['whatsapp_url'] as String?;
        if (url != null) _support = Uri.parse(url);
      } on ApiException {
        // serveur injoignable : message ci-dessous
      }
    }
    final base = _support;
    if (base == null) {
      showMessage('Aide indisponible pour le moment. Réessaie plus tard.', error: true);
      return false;
    }
    return openUrl(base.replace(queryParameters: {'text': message}));
  }

  Future<void> _startSession(String token) async {
    api.token = token;
    await _prefs?.setString(_kToken, token);
    await refreshMe();
    _connectSocket();
    unawaited(refreshUnread());
    unawaited(_registerPush());
    unawaited(_registerWebPush());
  }

  Future<void> logout() async {
    unawaited(google?.signOut());
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

  /// Nouveau mot de passe : les autres téléphones sont déconnectés, celui-ci reçoit
  /// un nouveau jeton.
  Future<void> changePassword(String current, String next) async {
    final r = await api.post('/me/password', {'current_password': current, 'new_password': next});
    await _replaceToken(r['access_token'] as String);
  }

  /// Déconnecte tous les autres téléphones (téléphone perdu ou prêté).
  Future<void> logoutOtherDevices() async {
    final r = await api.post('/me/logout-everywhere');
    await _replaceToken(r['access_token'] as String);
  }

  Future<void> _replaceToken(String token) async {
    api.token = token;
    await _prefs?.setString(_kToken, token);
    _disconnectSocket();
    _connectSocket();
  }

  /// Suppression définitive du compte (mot de passe, ou Google pour un compte
  /// créé avec Google, redemandé par le serveur).
  Future<void> deleteAccount(String password) async {
    await api.post('/me/delete', {'password': password});
    await _clearSession();
    notifyListeners();
  }

  /// Compte créé avec Google : nouvelle connexion Google pour confirmer. Faux si annulé.
  Future<bool> deleteAccountWithGoogle() async {
    final token = await _googleToken();
    if (token == null) return false;
    await api.post('/me/delete', {'google_id_token': token});
    await _clearSession();
    notifyListeners();
    return true;
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

  /// Active ou coupe la notification quotidienne des coupons du jour.
  Future<void> setDailyCouponsNotifications(bool on) async {
    await api.put('/me/preferences', {'daily_coupons_notifications': on});
    await refreshMe();
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

  /// Autre sélection du même match déjà dans le coupon (deux sélections liées), ou null.
  CouponItem? sameMatch(int matchId, String key) =>
      coupon.where((c) => c.match.id == matchId && c.offer.key != key).firstOrNull;

  Future<void> excludeTeam(int id, String name) async {
    excludedTeams[id] = name;
    notifyListeners();
    await _saveExcluded();
  }

  Future<void> includeTeam(int id) async {
    excludedTeams.remove(id);
    notifyListeners();
    await _saveExcluded();
  }

  Future<void> _saveExcluded() async {
    try {
      await _prefs?.setString(
        _kExcludedTeams,
        jsonEncode({for (final e in excludedTeams.entries) '${e.key}': e.value}),
      );
    } catch (_) {}
  }

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
    if (coupon.length >= maxCoupon) return 'Coupon plein ($maxCoupon sélections au maximum)';
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

  // --- Paiement Premium (Wave, Paystack, CinetPay ; ou Wave manuel) -----------

  /// Moyens de paiement proposés par le serveur : prix, `methods` [{id, label}] et
  /// `manual` (numéro Wave de FootProba, vérification par l'administrateur) ou null.
  Future<Json> paymentMethods() async => await api.get('/payments/methods') as Json;

  /// Crée le paiement et ouvre la page de paiement du prestataire dans le navigateur.
  Future<void> buyPremium([String? method]) async {
    final payment = await api.post('/payments/premium', {'method': method}) as Json;
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
        sha256: (v['sha256'] as String?) ?? '',
        url: Uri.parse(api.baseUrl).resolve(v['download_path'] as String),
      );
    } catch (_) {
      // Serveur injoignable ou ancien : on réessaiera au prochain retour dans l'application.
    }
  }

  /// Télécharge la mise à jour dans l'application (une seule fois par version), vérifie son
  /// empreinte, puis ouvre l'écran d'installation d'Android.
  Future<UpdateStep> installUpdate() async {
    final u = update.value;
    if (u == null) return UpdateStep.failed;
    final inst = installer;
    if (inst == null || u.sha256.isEmpty) return downloadInBrowser();
    try {
      if (_downloadedBuild != u.build) {
        updateProgress.value = 0;
        _downloadedApk = await inst.download(
          api.httpClient,
          u.url,
          build: u.build,
          sha256: u.sha256,
          onProgress: (p) => updateProgress.value = p,
        );
        _downloadedBuild = u.build;
      }
      if (!await inst.canInstall()) {
        await inst.openSettings();
        return UpdateStep.permission;
      }
      await inst.install(_downloadedApk!);
      return UpdateStep.installing;
    } catch (_) {
      _downloadedBuild = null;
      return UpdateStep.failed;
    } finally {
      updateProgress.value = null;
    }
  }

  /// Solution de secours : téléchargement par le navigateur.
  Future<UpdateStep> downloadInBrowser() async {
    final u = update.value;
    if (u != null) await openUrl(u.url);
    return UpdateStep.browser;
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
    _pushOpenedSub ??= p.opened.listen((kind) {
      openedKind = kind;
      notificationOpened.value += 1;
    });
    // Les notifications de paris arrivent aussi par le direct (WebSocket) : pas de
    // doublon, sauf si le direct est coupé. L'essai de l'administrateur n'existe
    // qu'en push.
    _pushForegroundSub ??= p.foreground.listen((m) {
      if (m.kind == 'test' || _socket == null) showMessage(m.text);
    });
    try {
      if (atLaunch && await p.openedAtLaunch()) {
        openedKind = null;
        notificationOpened.value += 1;
      }
      final token = await p.token();
      if (token == null) return;
      await _sendPushToken(token);
      _pushRefreshSub ??= p.tokenRefresh.listen((t) => unawaited(_sendPushToken(t)));
    } catch (e) {
      // Sans notifications push, l'application reste utilisable.
      debugPrint('Notifications push indisponibles : $e');
    }
  }

  /// Version web : état des notifications, et jeton renvoyé si elles sont déjà autorisées.
  Future<void> _registerWebPush() async {
    final w = webPush;
    if (w == null || api.token == null) return;
    try {
      final key = (await api.get('/app/web-push') as Json)['vapid_key'] as String?;
      if (key == null) return;
      webPushStatus.value = await w.status(key);
      _webForegroundSub ??= w.foreground.listen((m) {
        if (m.kind == 'test' || _socket == null) showMessage(m.text);
      });
      if (webPushStatus.value == WebPushStatus.on) {
        final token = await w.token();
        if (token != null) await _sendPushToken(token, platform: 'web');
      }
    } catch (e) {
      debugPrint('Notifications web indisponibles : $e');
    }
  }

  /// Bouton « Activer » du profil (geste du joueur, exigé par l'iPhone).
  Future<void> enableWebPush() async {
    final w = webPush;
    if (w == null) return;
    final String? token;
    try {
      token = await w.enable();
    } catch (e) {
      debugPrint('Activation des notifications web impossible : $e');
      showMessage('Notifications impossibles à activer sur ce navigateur.', error: true);
      return;
    }
    if (token == null) {
      webPushStatus.value = WebPushStatus.denied;
      showMessage('Notifications refusées : autorise-les dans les réglages du navigateur.', error: true);
      return;
    }
    await _sendPushToken(token, platform: 'web');
    webPushStatus.value = WebPushStatus.on;
    showMessage('Notifications activées sur cet appareil.');
  }

  Future<void> _sendPushToken(String token, {String platform = 'android'}) async {
    if (api.token == null) return;
    try {
      await api.post('/me/devices', {'token': token, 'platform': platform});
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
    tabRequest.dispose();
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
    this.sha256 = '',
  });
  final int build;
  final String notes;
  final bool mandatory;
  final int sizeMb;
  final Uri url;
  final String sha256;
}

/// Où en est la mise à jour après « Mettre à jour ».
enum UpdateStep { installing, permission, browser, failed }
