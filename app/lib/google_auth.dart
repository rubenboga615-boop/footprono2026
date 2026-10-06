// Connexion avec Google (Firebase Authentication) : Android et version web.
import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';

import 'firebase_options.dart';
import 'state/app_state.dart';

class FirebaseGoogleAuth implements GoogleAuthBridge {
  FirebaseGoogleAuth._() {
    // Web : Firebase prêt avant le toucher sur « Continuer avec Google », sinon le
    // navigateur bloque la fenêtre (elle doit s'ouvrir juste après le geste).
    if (kIsWeb) unawaited(_auth().then<void>((_) {}, onError: (Object _) {}));
  }

  /// null si Google n'est pas proposé : iPhone en application native (n'existe
  /// pas), ou version web sans application web déclarée dans Firebase.
  static GoogleAuthBridge? start() {
    if (kIsWeb) return firebaseWebReady ? FirebaseGoogleAuth._() : null;
    if (defaultTargetPlatform != TargetPlatform.android) return null;
    return FirebaseGoogleAuth._();
  }

  Future<FirebaseAuth>? _ready;

  // Un échec (web : fichiers de Firebase non chargés, réseau coupé) n'est pas gardé :
  // le prochain appui sur Google réessaie.
  Future<FirebaseAuth> _auth() => _ready ??= () async {
    try {
      if (Firebase.apps.isEmpty) {
        await Firebase.initializeApp(options: kIsWeb ? firebaseWebOptions(Uri.base) : firebaseOptions);
      }
      return FirebaseAuth.instance;
    } catch (_) {
      _ready = null;
      rethrow;
    }
  }();

  /// Web sur téléphone (et iPhone installé sur l'écran d'accueil) : redirection
  /// vers Google, plus fiable que la fenêtre. Ordinateur : fenêtre.
  static bool get _redirect =>
      kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.iOS || defaultTargetPlatform == TargetPlatform.android);

  @override
  Future<String?> idToken() async {
    final auth = await _auth();
    // Choix du compte à chaque fois : un téléphone partagé n'impose pas le dernier compte.
    final provider = GoogleAuthProvider()..setCustomParameters({'prompt': 'select_account'});
    try {
      if (_redirect) {
        // La page part chez Google puis revient : suite dans [redirectResult].
        await auth.signInWithRedirect(provider);
        return null;
      }
      final credential = kIsWeb
          ? await auth.signInWithPopup(provider)
          : await auth.signInWithProvider(provider);
      return await credential.user?.getIdToken(true);
    } on FirebaseAuthException catch (e) {
      // Fenêtre Google fermée par le joueur : rien à signaler.
      if (const {
        'web-context-canceled',
        'canceled',
        'popup-closed-by-user',
        'cancelled-popup-request',
      }.contains(e.code)) {
        return null;
      }
      debugPrint('Connexion Google : ${e.code} ${e.message}');
      rethrow;
    }
  }

  @override
  Future<String?> redirectResult() async {
    if (!_redirect) return null;
    final credential = await (await _auth()).getRedirectResult();
    return credential.user?.getIdToken(true);
  }

  @override
  Future<void> signOut() async {
    if (Firebase.apps.isEmpty) return;
    await FirebaseAuth.instance.signOut();
  }
}
