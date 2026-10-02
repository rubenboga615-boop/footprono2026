# Application Flutter (phase 5)

Code : `app/` (Flutter 3.47, Dart 3.13). Français seulement. Direction visuelle
« Verre violet » (`DESIGN.md`) : valeurs reprises des maquettes validées
(fond, halos et rubans lumineux, cartes en verre aux coins coupés, barre de
navigation flottante, boutons arrondis).

## Obtenir l'application

À chaque modification de `app/`, GitHub Actions (workflow **Application**)
vérifie le code (format, analyse, tests), puis construit :

| Artefact | Contenu |
|---|---|
| `footprono-apk` | APK Android (`app-arm64-v8a-release.apk` pour la plupart des téléphones récents ; `armeabi-v7a` pour les anciens) |
| `footprono-web` | version web, servie par l'API sur `/app` |

Téléchargement : GitHub → onglet **Actions** → workflow **Application** →
dernière exécution verte → **Artifacts** (compte GitHub connecté).

### APK sur le téléphone

1. Décompresser `footprono-apk.zip`, ouvrir `app-arm64-v8a-release.apk`,
   autoriser l'installation depuis cette source.
2. Le serveur Termux doit tourner (`bash scripts/termux/start.sh`).
3. Adresse par défaut : `http://127.0.0.1:8000` (serveur sur le même
   téléphone). Modifiable dans **Profil → Serveur** (bouton « Tester »).

Signature : une clé **de développement** versionnée
(`app/android/keystore/footprono-dev.jks`) signe tous les APK, pour qu'une
nouvelle version s'installe par-dessus l'ancienne. Avant toute publication
(phase 6), elle sera remplacée par une clé gardée en secret
(`FP_KEYSTORE_FILE`, `FP_KEYSTORE_PASSWORD`, `FP_KEY_ALIAS`, `FP_KEY_PASSWORD`).

### Version web sur le téléphone

```bash
termux-setup-storage     # une fois : accès aux Téléchargements
bash scripts/termux/install-web.sh ~/storage/downloads/footprono-web.zip
bash scripts/termux/stop.sh && bash scripts/termux/start.sh
```

Puis ouvrir `http://127.0.0.1:8000/app/` dans le navigateur. L'API sert la
page elle-même (`FP_WEB_APP_DIR`) : même adresse, aucun réglage CORS.

## Écrans

| Onglet / écran | Contenu | Données |
|---|---|---|
| Connexion, inscription | téléphone + mot de passe, pays (F CFA), case 18 ans | `/auth/*` |
| Matchs | jours, championnats, direct, carte par match (1 / N / 2, +2,5 buts, les deux marquent) | `/predictions/upcoming`, `/live` |
| Match · Probabilités | 1 / N / 2, scores les plus probables, tous les marchés (Premium) avec cote juste et cote réelle jouable | `/matches/{id}/prediction`, `/offer` |
| Match · Cotes | cotes réelles 1xBet (Bet365 en secours) et probabilité du moteur | `/matches/{id}/offer` |
| Match · Analyse (Premium) | forme sur 5 matchs (G/N/P), moyennes de la saison, confrontations directes ; buts attendus, classement, repos, enjeu, corners / cartons / tirs attendus | `/matches/{id}/analysis` (faits, matchs antérieurs seulement), prédiction (`counts`, `context`) |
| Coupon | sélections, probabilité combinée, cote totale, mise, gain ; utilisation pour un palier de montante | `/bets`, `/montantes/{id}/bet` |
| Coupon intelligent (Premium) | profil Sûr / Équilibré / Audacieux, période (aujourd'hui → 7 jours), 1 à 4 sélections ; cotes réelles, probabilité, deux faits par sélection, 3 autres choix ; « Mettre dans mon coupon » | `/smart-coupon` |
| Coupons du jour (public) | coupons enregistrés chaque matin avant les matchs, gagnés ou perdus, bilan annoncé / observé | `/smart-coupons/history` |
| Montante | création (mise, paliers, plages, part sécurisée), tableau, chances, encaisser, historique | `/montantes*` |
| Pari du palier (Premium) | 3 suggestions, probabilité du modèle et selon la cote, côte à côte (aucun « bon plan ») | `/montantes/{id}/suggestions` |
| Bookmaker | solde fictif, en jeu, rendement, paris en cours / réglés, mouvements | `/bets`, `/me/wallet/*` |
| Profil | formule et prix, notifications, fiabilité, mot de passe, jeu responsable, serveur, administration | `/me`, `/me/password` |
| Fiabilité | annoncé contre réalisé par marché et championnat, références, backtest séparé | `/reliability` |
| Notifications | en direct (WebSocket) et historique | `/ws`, `/me/notifications` |
| Administration | statistiques, recherche, Premium, désactivation | `/admin/*` |

Règles respectées dans l'application :

- Aucune donnée inventée : sans prédiction ou sans cote, l'écran le dit.
- Aucune « value » : la probabilité du moteur est une information, affichée
  à côté de celle de la cote ; aucun badge d'écart ni « bon plan » (face au
  marché, le moteur ne gagne pas : `MOTEUR.md`, handicap asiatique).
- Argent fictif rappelé sur le bookmaker, le coupon et le profil.
- Marchés Premium signalés (verrou), jamais masqués en silence.

## Notifications push (téléphone fermé)

Projet Firebase « footprono-56616 », application Android `com.footprono.footprono`.

- À la connexion, l'application demande l'autorisation d'afficher des
  notifications (Android 13 et plus) et enregistre le téléphone
  (`POST /me/devices`) ; à la déconnexion, il est retiré.
- Le serveur envoie chaque notification (pari réglé, palier de montante…) en
  direct dans l'application **et** sur les téléphones enregistrés (Firebase
  Cloud Messaging, API HTTP v1), canal Android « Paris et montantes ».
- Toucher la notification ouvre l'écran des notifications.
- Côté serveur : clé du compte de service, secrète, hors du dépôt
  (`FP_FCM_CREDENTIALS_FILE`). Sur Termux :
  `bash scripts/termux/install-firebase.sh ~/storage/downloads/<clé>.json`,
  redémarrer, puis `bash scripts/termux/admin.sh push-test <numéro>`.
- Sans clé, rien n'est envoyé et `/admin/stats` l'indique (`push.enabled`) ;
  les notifications restent visibles dans l'application.
- Version web : pas de notifications push (Android seulement).

## Pas encore disponible

- Paiement Mobile Money : en place (Profil → Passer Premium) dès que CinetPay est configuré sur le serveur.
- Vérification du numéro par SMS.

## Développement

```bash
cd app
flutter pub get
dart format -l 110 lib test && flutter analyze && flutter test
flutter build web --release --base-href /app/ --no-web-resources-cdn
flutter build apk --release --split-per-abi   # nécessite le SDK Android
```

Les tests (`app/test/`) couvrent les formats français, les libellés des
marchés et les parcours connexion, inscription, match → coupon → pari et
Premium, contre un faux serveur qui renvoie les mêmes réponses que l'API.

**Bout en bout** (`e2e/`, tâche `e2e` du workflow Application) : vraie API
(PostgreSQL, Redis, saison 2024-25 du dépôt prédite par le moteur) et vraie
version web dans Chromium — inscription, matchs, match, coupon et pari,
bookmaker, profil, fiabilité, montante et suggestions. Les éléments sont
trouvés par leur libellé d'accessibilité, comme un lecteur d'écran : ce test
a déjà révélé des champs sans nom et un bouton annoncé « désactivé ».

Changer de mot de passe ne déconnecte pas les autres appareils déjà
connectés (jeton valable 30 jours) : à traiter avec la sécurité (phase 6).
