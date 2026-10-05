# FootProba Console (Android)

Application Android de la console d'administration : une fenêtre dédiée sur
`<serveur>/admin/`, sans dépendance (WebView du système, ≈ 100 Ko).

- **Construction** : par la CI (workflow « Application », tâche `console`),
  artefact `footproba-console-apk`. Le serveur vient de la variable du dépôt
  `FP_SERVER_URL`, signée avec la même clé que l'application.
  En local : `./gradlew assembleRelease -Pfp.server=https://… -Pfp.build=1`.
- **Installation** : à côté de l'application des joueurs (identifiant distinct
  `com.footproba.console`). Se connecter avec un compte administrateur.
- **Sécurité** : seule l'adresse du serveur s'ouvre dans la fenêtre (le reste
  part dans le navigateur) ; la session est perdue à la fermeture de
  l'application, comme un onglet fermé ; sauvegarde Android désactivée.
- **Fichiers** : les téléchargements (exports, rapports) arrivent dans le
  dossier *Téléchargements* (Android 10 et plus) ; « Choisir un fichier »
  (publication d'une version) ouvre le sélecteur d'Android.
- Safe Browsing est coupé pour cette fenêtre : il signale à tort les
  sous-domaines duckdns.org, et la fenêtre n'ouvre que notre serveur.
