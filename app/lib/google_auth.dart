// Connexion avec Google (Firebase Authentication), Android seulement pour l'instant :
// la version web demande une application web déclarée dans Firebase.
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';

import 'firebase_options.dart';
import 'state/app_state.dart';

class FirebaseGoogleAuth implements GoogleAuthBridge {
  FirebaseGoogleAuth._();

  /// null hors Android : le bouton Google n'est pas proposé (connexion par numéro).
  static GoogleAuthBridge? start() {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) return null;
    return FirebaseGoogleAuth._();
  }

  Future<FirebaseAuth> _auth() async {
    if (Firebase.apps.isEmpty) await Firebase.initializeApp(options: firebaseOptions);
    return FirebaseAuth.instance;
  }

  @override
  Future<String?> idToken() async {
    final auth = await _auth();
    // Choix du compte à chaque fois : un téléphone partagé n'impose pas le dernier compte.
    final provider = GoogleAuthProvider()..setCustomParameters({'prompt': 'select_account'});
    try {
      final credential = await auth.signInWithProvider(provider);
      return await credential.user?.getIdToken(true);
    } on FirebaseAuthException catch (e) {
      // Fenêtre Google fermée par le joueur : rien à signaler.
      if (e.code == 'web-context-canceled' || e.code == 'canceled') return null;
      debugPrint('Connexion Google : ${e.code} ${e.message}');
      rethrow;
    }
  }

  @override
  Future<void> signOut() async {
    if (Firebase.apps.isEmpty) return;
    await FirebaseAuth.instance.signOut();
  }
}
