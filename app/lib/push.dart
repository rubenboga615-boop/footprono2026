// Notifications sur le téléphone fermé (Firebase Cloud Messaging) : Android, et version
// web (iPhone avec FootProba sur l'écran d'accueil, ordinateur).
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import 'firebase_options.dart';
import 'state/app_state.dart';

class FirebasePush implements PushBridge {
  FirebasePush._();

  /// null hors Android (version web) ou si Firebase ne démarre pas : l'application
  /// fonctionne alors sans notifications push (les notifications restent visibles
  /// dans l'application).
  static Future<FirebasePush?> start() async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) return null;
    try {
      await Firebase.initializeApp(options: firebaseOptions);
      return FirebasePush._();
    } catch (e) {
      debugPrint('Firebase indisponible : $e');
      return null;
    }
  }

  FirebaseMessaging get _fm => FirebaseMessaging.instance;

  @override
  Future<String?> token() async {
    // Android 13 et plus : demande l'autorisation d'afficher des notifications.
    final settings = await _fm.requestPermission();
    if (settings.authorizationStatus == AuthorizationStatus.denied) return null;
    return _fm.getToken();
  }

  @override
  Stream<String> get tokenRefresh => _fm.onTokenRefresh;

  @override
  Stream<String?> get opened => FirebaseMessaging.onMessageOpenedApp.map((m) => m.data['kind']?.toString());

  @override
  Future<bool> openedAtLaunch() async => await _fm.getInitialMessage() != null;

  // Application ouverte : Android n'affiche pas la notification, l'application le fait.
  @override
  Stream<PushMessage> get foreground => FirebaseMessaging.onMessage
      .where((m) => m.notification != null)
      .map(
        (m) => (
          text: '${m.notification!.title ?? 'FootProba'} — ${m.notification!.body ?? ''}',
          kind: m.data['kind']?.toString(),
        ),
      );
}

/// Version web : Firebase démarré seulement si le serveur propose les notifications ;
/// le service worker (web/push/firebase-messaging-sw.js) affiche celles reçues page fermée.
class WebFirebasePush implements WebPushBridge {
  String? _vapidKey;

  static const _worker = 'push/firebase-messaging-sw.js';

  @override
  Future<WebPushStatus> status(String vapidKey) async {
    _vapidKey = vapidKey;
    if (!firebaseWebReady) return WebPushStatus.unavailable;
    if (Firebase.apps.isEmpty) await Firebase.initializeApp(options: firebaseWebOptions(Uri.base));
    final fm = FirebaseMessaging.instance;
    if (!await fm.isSupported()) {
      // Safari sur iPhone : notifications seulement depuis l'écran d'accueil (iOS 16.4+).
      return defaultTargetPlatform == TargetPlatform.iOS ? WebPushStatus.install : WebPushStatus.unavailable;
    }
    return switch ((await fm.getNotificationSettings()).authorizationStatus) {
      AuthorizationStatus.authorized => WebPushStatus.on,
      AuthorizationStatus.denied => WebPushStatus.denied,
      _ => WebPushStatus.off,
    };
  }

  @override
  Future<String?> token() =>
      FirebaseMessaging.instance.getToken(vapidKey: _vapidKey, serviceWorkerScriptPath: _worker);

  @override
  Future<String?> enable() async {
    // Première action après le geste du joueur : sinon l'iPhone refuse de demander.
    final settings = await FirebaseMessaging.instance.requestPermission();
    if (settings.authorizationStatus != AuthorizationStatus.authorized) return null;
    return token();
  }

  @override
  Stream<PushMessage> get foreground => FirebaseMessaging.onMessage
      .where((m) => m.notification != null)
      .map(
        (m) => (
          text: '${m.notification!.title ?? 'FootProba'} — ${m.notification!.body ?? ''}',
          kind: m.data['kind']?.toString(),
        ),
      );
}
