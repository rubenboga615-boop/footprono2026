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
