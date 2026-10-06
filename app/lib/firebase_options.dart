// Projet Firebase « FootProno » (notifications push), tiré de google-services.json.
// Ces identifiants ne sont pas secrets : ils sont livrés dans l'application et
// ne permettent que de recevoir des notifications. La clé secrète (compte de
// service, pour envoyer) reste sur le serveur.
import 'package:firebase_core/firebase_core.dart';

const firebaseOptions = FirebaseOptions(
  apiKey: 'AIzaSyCI56ibjiN7i2-gMmoYcLPPQLnFpQof6FI',
  appId: '1:265990154612:android:d813700c88240d7394e421',
  messagingSenderId: '265990154612',
  projectId: 'footprono-56616',
  storageBucket: 'footprono-56616.firebasestorage.app',
);

// Application web déclarée dans le même projet Firebase (identifiants publics eux
// aussi). Vides : la version web ne propose pas Google (connexion par numéro).
const _webApiKey = '';
const _webAppId = '';

bool get firebaseWebReady => _webApiKey.isNotEmpty && _webAppId.isNotEmpty;

/// [authDomain] : notre propre domaine, qui relaie les pages de connexion de
/// Firebase (/__/auth, voir deploy/Caddyfile). Safari sur iPhone bloque sinon la
/// session pendant la redirection vers Google (stockage tiers partitionné).
FirebaseOptions firebaseWebOptions(Uri page) => FirebaseOptions(
  apiKey: _webApiKey,
  appId: _webAppId,
  messagingSenderId: '265990154612',
  projectId: 'footprono-56616',
  authDomain: const {'localhost', '127.0.0.1'}.contains(page.host)
      ? 'footprono-56616.firebaseapp.com'
      : page.authority,
  storageBucket: 'footprono-56616.firebasestorage.app',
);
