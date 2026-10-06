// Notifications de la version web (iPhone : FootProba ajouté à l'écran d'accueil ;
// ordinateur). Firebase affiche les notifications reçues quand la page est fermée ;
// les toucher ouvre FootProba (lien donné par le serveur). Identifiants publics,
// ceux de l'application web du projet Firebase (lib/firebase_options.dart).
importScripts('https://www.gstatic.com/firebasejs/12.19.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: 'AIzaSyDuIa5vo_tSbsouKLsSYBHXAk7ihf5kK0c',
  appId: '1:265990154612:web:a17f6736747e46c494e421',
  messagingSenderId: '265990154612',
  projectId: 'footprono-56616',
});
firebase.messaging();
