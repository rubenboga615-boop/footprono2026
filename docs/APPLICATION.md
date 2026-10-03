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

Puis ouvrir `http://127.0.0.1:8000/app/` dans le navigateur. L'API sert la page elle-même
(`FP_WEB_APP_DIR`) : même adresse, aucun réglage CORS.

La disposition dépend de la largeur de la fenêtre :

- **Téléphone** (jusqu'à 760 pixels) : barre de navigation flottante en bas, rien de changé.
- **Fenêtre moyenne** (760 à 1100 pixels) : la même application dans une colonne centrée de
  680 pixels (`WideFrame`, `lib/theme.dart`).
- **Ordinateur** (1100 pixels et plus, `lib/desktop/`) :
  - menu à gauche (Jouer, Comprendre, Compte) et barre du haut (recherche, Premium, solde) ;
  - zone centrale avec sa propre navigation : un match ou une fiche s'ouvre dedans, le menu reste ;
  - **Matchs** en tableau : une ligne par match ; 1, N, 2, +2,5 buts et « les deux marquent »
    colorés selon la probabilité du moteur, avec la cote réelle dessous (`GET /offers/main`,
    80 matchs au plus par appel) ; buts attendus. Un clic sur une cote l'ajoute au coupon, un
    clic ailleurs ouvre le match ;
  - **Montante** : le plan devient un escalier (une marche par palier, plus haute à mesure que
    le gain grandit ; gagné en vert, perdu en rose, en cours en violet) ;
  - **coupon à droite** pendant qu'on parcourt les matchs (cote totale, chances selon le moteur et
    selon la cote), avec un lien vers la mise ;
  - **recherche** (Ctrl K ou la barre du haut) : matchs, équipes et rubriques, sans tenir compte
    des accents ;
  - écrans riches sur deux colonnes (`deskColumns`, `deskSplit` dans `lib/desktop/layout.dart`) :
    match, coupon, Coupon intelligent (réglages à gauche, coupon proposé à droite), Mon bilan,
    fiche arbitre, fiabilité, profil ;
  - connexion : présentation à gauche, formulaire à droite (`lib/desktop/welcome.dart`).

## Mises à jour (hors Play Store)

Chaque APK porte son numéro de construction (numéro de l'exécution GitHub
Actions). À l'ouverture et au retour dans l'application, elle demande
`GET /app/version` ; si le serveur a publié une version plus récente, une
fenêtre « Nouvelle version disponible » propose de la télécharger.
Depuis la version 47, l'application télécharge elle-même l'APK
(`GET /app/download`, APK arm64) avec une barre de progression, vérifie son
empreinte SHA-256 (celle de `/app/version`) puis ouvre directement l'écran
d'installation d'Android (même clé de signature : compte et paris conservés).
La première fois, Android demande d'autoriser FootProno à installer des
applications (réglage ouvert par l'application). Une confirmation reste
toujours nécessaire : hors Play Store, aucune application ne peut
s'installer en silence. En cas d'échec (connexion coupée, fichier altéré),
rien n'est installé et le navigateur est proposé en secours. Code :
`lib/update/`, canal `footprono/installer` dans `MainActivity.kt`.

Publier une version (Termux) : télécharger l'archive `footprono-apk.zip`
depuis GitHub Actions, puis
`bash scripts/termux/publish-apk.sh "Nouveautés"` (prend l'archive `footprono-apk*.zip` la plus récente des Téléchargements ; `--archive CHEMIN` pour en choisir une).
`--minimum N` rend la mise à jour obligatoire pour les versions sous N
(correctif important). Sur le serveur de production :
`docker compose -f /opt/footprono/deploy/docker-compose.yml exec api footprono-admin publish-apk …`
après avoir copié l'archive dans le conteneur. L'avant-dernière version est
gardée ; on ne publie jamais un numéro plus ancien.

Une installation manuelle reste nécessaire une fois : les APK construits
avant cette fonction n'ont pas de numéro et ne vérifient rien.

## Clé de signature de production

Sans clé de production, l'APK est signé avec la clé de développement du
dépôt (n'importe qui peut la copier) : à remplacer avant toute diffusion.

1. Sur le téléphone, une seule fois : `bash scripts/termux/keystore.sh`
   (crée `~/footprono-release.jks`, alias `footprono`, RSA 4096, 27 ans ;
   copie de sauvegarde et texte base64 dans Téléchargements).
2. **Sauvegarde** : copier `footprono-release.jks` hors du téléphone (Google
   Drive, e-mail à soi-même) et noter le mot de passe. Perdus, l'application
   ne peut plus jamais être mise à jour chez les utilisateurs.
3. GitHub → dépôt → Settings → Secrets and variables → Actions → **New
   repository secret**, quatre secrets :
   `FP_KEYSTORE_BASE64` (contenu de `footprono-release-base64.txt`),
   `FP_KEYSTORE_PASSWORD` (le mot de passe), `FP_KEY_ALIAS` (`footprono`),
   `FP_KEY_PASSWORD` (le même mot de passe : clé PKCS12).
4. Supprimer `footprono-release-base64.txt` des Téléchargements.
5. La construction suivante signe avec la clé de production et affiche
   l'empreinte SHA-256 du certificat dans le journal (étape « Clé de
   signature »). Sans les secrets : avertissement, clé de développement.

Changement de clé : Android refuse d'installer un APK signé autrement par
dessus l'ancien. Désinstaller une fois l'application (le compte, le solde et
les paris sont sur le serveur : rien n'est perdu), puis installer le nouvel APK.

## Écrans

| Onglet / écran | Contenu | Données |
|---|---|---|
| Connexion, inscription | téléphone + mot de passe, pays (F CFA), case 18 ans | `/auth/*` |
| Matchs | jours, championnats, direct, carte par match (1 / N / 2, +2,5 buts, les deux marquent) | `/predictions/upcoming`, `/live` |
| Match · Probabilités | « Les choix du moteur » en tête (une sélection par profil, Sûr gratuit, les trois en Premium, jamais présentée comme une bonne affaire) ; 1 / N / 2, scores les plus probables, tous les marchés (Premium) avec cote juste et cote réelle jouable | `/matches/{id}/picks`, `/matches/{id}/prediction`, `/offer` |
| Match · Cotes | cotes réelles 1xBet (Bet365 en secours) et probabilité du moteur ; si la cote a bougé, « ▼ 2,04 → 1,91 · historique » ouvre la liste des relevés (seuls les changements sont enregistrés), sans conseil | `/matches/{id}/offer` (`opening_odds`, `opened_at`), `/matches/{id}/odds-history?market=&line=&selection=` |
| Match · Analyse (Premium) | forme sur 5 matchs (G/N/P), moyennes de la saison, confrontations directes ; buts attendus, classement, repos, enjeu, corners / cartons / tirs attendus | `/matches/{id}/analysis` (faits, matchs antérieurs seulement), prédiction (`counts`, `context`) |
| Fiche équipe (toucher une équipe dans un match) | forme, points et buts domicile / extérieur / saison ; Premium : xG créés et concédés, xPts, pressing (PPDA), passes dangereuses, tirs cadrés, corners, cartons, possession, arrêts, passes réussies ; phrase si les buts s'écartent des xG de 0,2 ou plus ; « — » si la source n'a pas la donnée | `/teams/{id}/profile?competition=&season=` (champs avancés à `null` et `locked: true` en gratuit) |
| Classement mérité (icône classement des Matchs ou d'une fiche) | points réels contre xPts d'Understat par championnat et saison ; écart vert ≥ +3, rose ≤ −3, gris sinon ; rang mérité entre parenthèses ; avertissement si des xPts manquent | `/competitions/{code}/seasons/{année}/merited` |
| Fiche arbitre (« Arbitre : … » sous l'en-tête d'un match) | jaunes et rouges par match contre la moyenne du même championnat sur les mêmes saisons, domicile / extérieur, saison par saison, 5 derniers matchs ; sévérité jugée seulement à partir de 15 matchs (écart de 0,5 jaune) ; noms regroupés (« Stuart Attwell » = « S. Attwell » = « S Attwell ») | `/referees/profile?name=` |
| Les arbitres (icône classement de la fiche arbitre) | arbitres d'une saison du plus sévère au plus clément, non classés sous 15 matchs, matchs sans arbitre connu signalés | `/competitions/{code}/seasons/{année}/referees` |
| Coupon | jusqu'à 12 sélections, une par match (si une autre sélection du même match existe, l'application demande laquelle garder), « 1 chance sur N » ; sélections, probabilité combinée, cote totale, mise, gain ; utilisation pour un palier de montante | `/bets`, `/montantes/{id}/bet` |
| Coupon intelligent (Premium) | profils Sûr / Équilibré / Audacieux et **Grosse cote** (cote visée 10, 25, 50, 100 ou libre : sélections les plus probables ajoutées jusqu'à l'atteindre, jamais choisies sur un désaccord avec la cote, 12 au plus) ; période (raccourcis, un seul jour, plusieurs jours), championnats, heure minimum ; 1 à 12 sélections ; « 1 chance sur N », rappel de la marge au-delà de 6 sélections ; remplacer ou exclure une sélection (match, ou équipe mémorisée sur le téléphone) ; partage du coupon en image (argent fictif) | `/smart-coupon` (`target_odds`, `day`, `date_from`, `date_to`, `after_hour`, `competitions`, `exclude_matches`, `exclude_teams`) |
| Coupons du jour (public) | coupons enregistrés chaque matin avant les matchs, gagnés ou perdus, bilan annoncé / observé | `/smart-coupons/history` |
| Montante | création (mise, paliers, plages, part sécurisée), tableau, chances, encaisser, historique | `/montantes*` |
| Pari du palier (Premium) | 3 suggestions, probabilité du modèle et selon la cote, côte à côte (aucun « bon plan ») | `/montantes/{id}/suggestions` |
| Bookmaker | solde fictif, en jeu, rendement, paris en cours / réglés, mouvements | `/bets`, `/me/wallet/*` |
| Mon bilan (icône du Bookmaker, visible par le joueur seul) | paris réglés, gagnés / perdus, misé, récupéré, résultat net, rendement ; annoncé (moteur) contre selon la cote contre réalisé par tranche de probabilité, « peu de paris » sous 20 sélections ; réussite par marché et par championnat  ; bilan par cote du coupon (moins de 2, 2 à 5, 5 à 20, 20 et plus : gagnés, annoncé, net) ; rappel de jeu responsable si les mises de la semaine doublent | `/me/record` |
| Profil | formule et prix, notifications, fiabilité, mot de passe, jeu responsable, serveur, administration ; numéro de version en bas | `/me`, `/me/password` |
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
