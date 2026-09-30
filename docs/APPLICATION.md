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
| Match · Analyse (Premium) | buts attendus, classement, repos, forme, enjeu, corners / cartons / tirs attendus | prédiction (`counts`, `context`) |
| Coupon | sélections, probabilité combinée, cote totale, mise, gain ; utilisation pour un palier de montante | `/bets`, `/montantes/{id}/bet` |
| Montante | création (mise, paliers, plages, part sécurisée), tableau, chances, encaisser, historique | `/montantes*` |
| Pari du palier (Premium) | 3 suggestions, écart modèle / cote, « déconseillé » | `/montantes/{id}/suggestions` |
| Bookmaker | solde fictif, en jeu, rendement, paris en cours / réglés, mouvements | `/bets`, `/me/wallet/*` |
| Profil | formule et prix, notifications, fiabilité, jeu responsable, serveur, administration | `/me` |
| Fiabilité | annoncé contre réalisé par marché et championnat, références, backtest séparé | `/reliability` |
| Notifications | en direct (WebSocket) et historique | `/ws`, `/me/notifications` |
| Administration | statistiques, recherche, Premium, désactivation | `/admin/*` |

Règles respectées dans l'application :

- Aucune donnée inventée : sans prédiction ou sans cote, l'écran le dit.
- Aucune « value » : la probabilité du moteur est une information ; les
  suggestions de montante indiquent l'écart et « déconseillé », rien de plus.
- Argent fictif rappelé sur le bookmaker, le coupon et le profil.
- Marchés Premium signalés (verrou), jamais masqués en silence.

## Pas encore disponible

- Notifications téléphone fermé (Firebase) : il faut créer le projet Firebase.
- Paiement Mobile Money (phase 6) ; Premium est activé par l'administrateur.
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
