// Notifications sur le téléphone fermé (Firebase Cloud Messaging), Android seulement.
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
  Stream<void> get opened => FirebaseMessaging.onMessageOpenedApp.map((_) {});

  @override
  Future<bool> openedAtLaunch() async => await _fm.getInitialMessage() != null;
}
