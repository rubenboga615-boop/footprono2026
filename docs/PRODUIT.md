# Produit : formules, administration (phase 5)

Code : `backend/src/footprono/accounts/plans.py`, `accounts/admin.py`,
`accounts/cli.py`, `api/v1/admin.py`.

## Décisions (30/09/2026)

| Sujet | Décision |
|---|---|
| Formules | **7 jours de Premium offerts à l'inscription**, puis version gratuite ; Premium à **2 000 F CFA par mois** |
| Activation de Premium | **Mobile Money** (CinetPay, Profil → Passer Premium, voir `PRODUCTION.md`) ; l'administrateur peut aussi l'accorder |
| Langue | Français seulement |

## Ce que contient chaque formule

| | Gratuit | Premium |
|---|---|---|
| Matchs, résultats, direct | oui | oui |
| Marchés (prédictions, offre, paris) | 1X2, plus/moins de buts (OU), les deux marquent (BTTS) | tous : handicaps, double chance, mi-temps, scores exacts, corners, cartons, tirs… |
| Bookmaker virtuel, coupons, montante | oui (sur les marchés gratuits) | oui |
| Suggestions de montante | non | oui |
| Analyse détaillée (corners/cartons/tirs attendus, contexte des équipes) | non | oui |
| Page publique de fiabilité | oui | oui |

- Le contrôle est fait **par le serveur** : un pari sur un marché Premium par
  un compte gratuit est refusé (`403 premium_required`), un combiné entier est
  refusé dès qu'une sélection est Premium.
- Rien n'est caché en silence : la prédiction d'un match sans Premium indique
  `plan: "free"` et la liste des marchés réservés (`locked_markets`).
- Sans connexion, les routes publiques répondent en version gratuite.
- `GET /me` renvoie le rôle et la formule : `plan.name` (free / premium),
  `premium_until`, `days_left`, marchés gratuits, prix.

## Console d'administration (/admin)

Outil web réservé aux comptes administrateur, servi par le serveur à l'adresse
`/admin`, sur ordinateur et sur téléphone, sans rien installer. Même univers que
l'application (polices Sora et Plus Jakarta Sans, embarquées ; violet FootProba).
Connexion avec le numéro (indicatif compris) et le mot de passe d'un compte
administrateur. L'application des joueurs ne contient **aucun outil ni aucune
information d'administration** : pas de menu Administration (codes 1xBet, comptes :
dans la console), pas d'adresse du serveur, pas de version du moteur, pas de
notification de la console (le suivi des tâches reste dans la console), et des
messages d'erreur simples pour le joueur (le détail technique reste dans le
journal du serveur : `AppError(..., public=...)`).
**Sécurité de la console** (page Sécurité, `api/v1/console_auth.py`) :
- connexion propre à la console (`POST /auth/console-login`) : numéro, mot de passe, puis
  **code de sécurité à 6 chiffres** (Google Authenticator, Microsoft Authenticator… ;
  TOTP RFC 6238, clé chiffrée en base, code déjà utilisé refusé) une fois activé ;
- **sessions de 12 h**, enregistrées dans Redis : « Se déconnecter » ferme la session,
  « Déconnecter toutes mes sessions » les ferme toutes ; un jeton de l'application des
  joueurs (30 jours) n'ouvre jamais la console ;
- **historique des actions** (table `admin_actions`, jamais exportée) : connexions, codes
  refusés, Premium, rôles, numéros, mots de passe provisoires, désactivations, codes 1xBet,
  actions lancées ou arrêtées, fichiers supprimés, versions publiées, code de sécurité ;
- téléphone perdu : sur le serveur, `docker compose -f /opt/footprono/deploy/docker-compose.yml exec api footprono-admin disable-2fa <numéro>`
  (puis réactiver le code dans la console).

**Alertes sur le téléphone de l'administrateur** (page Sécurité, `alerts.py`) : par
l'application gratuite **ntfy** (sans compte), sur un canal au nom aléatoire créé dans la
console (table `app_settings`). Toutes les 10 minutes (tâche `alerts_watchdog`) : la liste
« à traiter » du tableau de bord (service arrêté, quota API-Football bas, sauvegarde
manquante, disque presque plein, codes 1xBet à saisir, cotes non relevées…) et les tâches
planifiées en échec ; immédiatement : une action de la console en échec. Une même alerte
au plus toutes les 12 h ; aucune donnée de joueur ; rien ne passe par l'application des joueurs.

Joueurs : changer son mot de passe (ou un mot de passe provisoire donné par la console)
déconnecte les autres téléphones ; Profil → « Déconnecter mes autres téléphones »
(`POST /me/logout-everywhere`).

Aussi installable sur Android : **FootProba Console** (`console-android/`, artefact
`footproba-console-apk` de la CI), fenêtre dédiée sur `/admin` du serveur.

- **Tableau de bord** : jauges (services, quota API-Football du jour, disque), courbe
  des comptes sur 30 jours, **frise des tâches planifiées sur 24 h** (direct, cotes,
  ingestion, pronostics, coupons, paiements : un bloc par exécution, vert, jaune ou
  rose), dernière sauvegarde de la base, **à traiter** (codes 1xBet, quota bas, cotes
  non relevées, sauvegarde manquante, service arrêté…) et tâches **en cours**.
- **Actions** : catalogue fourni par le serveur (`backend/src/footprono/console/actions.py`),
  filtrable par famille, recherche **Ctrl K** (bouton central sur téléphone). Chaque
  action indique risque, coût en requêtes, durée, fichier produit ; un récapitulatif
  (quota restant, étapes) précède le lancement. **Une action ajoutée par une mise à jour
  du serveur apparaît d'elle-même.**
- **Suivi** : progression, temps restant estimé, étapes cochées, journal coloré avec
  filtre « erreurs », copie, arrêt propre des tâches longues, relance avec les mêmes
  réglages ; notification de l'administrateur à la fin.
- **Fichiers** : exports, archives et rapports produits par les actions, gardés 30 jours,
  téléchargés par lien signé de 5 minutes. Jamais de donnée personnelle ; les
  sauvegardes de la base ne sont pas téléchargeables.
- **Comptes Google** : affichés avec leur adresse Gmail (pas de numéro) ; « Changer le numéro » leur en donne un.
- **Exploitation** : codes du jour (1xBet), comptes (Premium, administrateur, numéro,
  mot de passe provisoire affiché une seule fois, désactivation), paiements, **versions
  de l'application** (dépôt de l'archive `footprono-apk.zip` depuis le navigateur).

Actions disponibles (elles remplacent les scripts Termux) :

| Famille | Action | Ancien script |
|---|---|---|
| Données | Mettre à jour la saison en cours | `ingest.sh all --seasons …` |
| Données | Ingestion sur plusieurs saisons | `ingest.sh all --seasons 2016-2026` |
| Données | Collecter / importer l'historique API-Football | `api-football-history.sh` |
| Données | Relever les cotes · blessés et suspendus | `ingest.sh odds` · `injuries` |
| Données | Exporter les données pour l'étude | `export-data.sh` |
| Données | Équipes d'un championnat (API-Football) | `api-football-teams.sh` |
| Données | Fichiers football-data pour l'étude | `download-football-data.sh` |
| Moteur | Recalculer les pronostics · évaluer le moteur | `engine.sh predict` · `backtest`, `calibration`, `audit`, `counts`, `ah`, `features`, `angles` |
| Application | Créer les coupons du jour | (tâche de 08:05) |
| Comptes | Notification d'essai ; page Comptes | `admin.sh push-test` ; `make-admin`, `grant`, `set-phone`, `reset-password`, `stats` |
| Application | Page Versions de l'app | `publish-apk.sh` |
| Diagnostic | Couverture · qualité · quota · vérifier les cotes | `ingest.sh coverage` · `quality` · `check-odds.sh` |

Restent hors de la console, sur le serveur : mise à jour (`install-server.sh`),
redémarrage, secrets (`deploy/.env`, clés), restauration d'une sauvegarde. Sécurité :
routes `/api/v1/admin/console` réservées au rôle administrateur ; pages servies avec
une politique de contenu stricte (aucun script, style ni police extérieurs, pas
d'affichage dans un cadre, rien en cache) ; jeton gardé le temps de l'onglet ; un
administrateur ne peut pas retirer son propre rôle.

| Route (administrateur seulement) | Rôle |
|---|---|
| `GET /admin/console/actions` · `dashboard` | catalogue · tableau de bord |
| `POST /admin/console/jobs` · `GET jobs` · `GET jobs/{id}?after=n` · `POST jobs/{id}/stop` | lancer, journal, suivi, arrêt |
| `GET /admin/console/files` · `POST files/{nom}/link` · `DELETE files/{nom}` | fichiers, lien signé, suppression |
| `GET`/`POST /admin/console/app-release` | version publiée, publication (corps : l'archive) |
| `GET /admin/console/payments` | derniers paiements |
| `POST /admin/users/{id}/role` · `phone` · `password-reset` | administrateur, numéro, mot de passe provisoire |

## Administration

Chaque changement d'abonnement est inscrit dans `subscription_events`
(essai, activation, retrait ; administrateur, date, durée, note).

Premier administrateur (sur le serveur, une fois le compte créé dans
l'application) :

```bash
bash scripts/termux/admin.sh make-admin +22997000000
bash scripts/termux/admin.sh grant +22997000000 --days 30 --note "paiement reçu"
bash scripts/termux/admin.sh stats
bash scripts/termux/admin.sh users                  # comptes : numéro, rôle, Premium
bash scripts/termux/admin.sh set-phone +22997000000 +22961000000   # changer de numéro
bash scripts/termux/admin.sh reset-password +22997000000           # mot de passe provisoire
bash scripts/termux/admin.sh push-test +22997000000                # notification d'essai
```

| Route (administrateur seulement) | Rôle |
|---|---|
| `GET /admin/stats` | comptes, actifs, Premium (dont essais), nouveaux comptes et paris sur 7 jours |
| `GET /admin/users?q=` | recherche par nom ou numéro |
| `GET /admin/users/{id}` | compte et historique de l'abonnement |
| `POST /admin/users/{id}/premium` | ajouter N jours (à la suite de la période en cours) |
| `POST /admin/users/{id}/premium/revoke` | retirer Premium |
| `POST /admin/users/{id}/active` | désactiver / réactiver un compte |

## Page publique de fiabilité (`GET /reliability`, gratuite, sans connexion)

Code : `backend/src/footprono/predictions/reliability.py`.

- **Seules les prédictions enregistrées avant le coup d'envoi comptent**
  (sans heure connue : avant minuit UTC du jour du match), la dernière pour
  chaque match. Elles ne sont jamais modifiées ni recalculées après coup.
- **Toutes comptent** : aucun match n'est écarté parce que la prédiction était
  mauvaise.
- Marchés : 1X2, plus/moins de 2,5 buts, les deux marquent. Pour chacun :
  log loss, Brier, issue la plus probable trouvée (et probabilité annoncée
  en moyenne pour elle), fréquences observées, **calibration** (probabilité
  annoncée par tranche de 10 % → fréquence observée).
- Références : fréquences observées sur le même échantillon (avantagée, car
  connue après coup) et **cotes de clôture** des bookmakers quand elles
  existent (elles font en général mieux que le moteur ; c'est affiché).
- Par championnat, et les derniers matchs avec la prédiction et le résultat.
- **Moins de 200 matchs : averti « échantillon trop petit pour conclure »**.
- Les chiffres du backtest (7 081 matchs, saisons 2022-2026) sont donnés à
  part, présentés comme une simulation et non comme des prédictions publiées.
- Filtres : `?competition=EPL`, `?since=2026-08-01`, `?recent=20`.

## Phase 5 : terminée (01/10/2026)

- Application Flutter (voir `APPLICATION.md`) : installée et utilisée sur le
  téléphone.
- Notifications téléphone fermé (Firebase) : validées sur le téléphone
  (application fermée, notification dans la barre).

## Coupon intelligent (02/10/2026)

Onglet **Coupon** → carte « Coupon intelligent » (Premium).

- **Profil** : Sûr (75 à 92 % par sélection), Équilibré (60 à 75 %),
  Audacieux (45 à 60 %).
- **Période** : prochaine journée (par défaut : du premier match à venir
  jusqu'au lundi qui suit, même après une trêve internationale), aujourd'hui,
  demain, 3 jours, ce week-end, 7 jours. Sans match sur la période, l'écran
  donne la date des prochains matchs. Inutile
  d'attendre le jour du match : les prédictions couvrent 10 jours ; seules
  les cotes réelles (relevées toutes les 3 heures) limitent l'horizon.
  Fermeture 15 minutes avant le coup d'envoi.
- **1 à 4 sélections**, jamais deux du même match.
- Méthode : dans chaque match, la sélection la plus probable de la tranche du
  profil (Sûr : la plus proche de 83,5 %, milieu de sa tranche, pour une cote
  utile : coupon de 3 ≈ 1,66 pour 60 % de réussite, contre 1,31 au plafond) parmi les marchés retenus avec une vraie cote (≥ 1,10) ; les matchs
  les plus sûrs d'abord ; 3 autres choix proposés. Validée hors échantillon
  (`footprono-engine angles`, `docs/MOTEUR.md`).
- Chaque sélection : cote réelle, probabilité du moteur, deux faits (forme,
  moyennes de la saison, xG, confrontations). Probabilité du coupon et
  probabilité selon la cote affichées côte à côte. Aucune promesse de gain.
- « Mettre dans mon coupon » relit les cotes actuelles ; le pari reste validé
  par le joueur (`GET /smart-coupon?profile=&period=&size=`).

**Coupons du jour** (public, `GET /smart-coupons/history`) : chaque matin à
08:05 UTC (après cotes et prédictions), un coupon par profil (Sûr : 3
sélections, Équilibré et Audacieux : 2) est enregistré **avant** les matchs,
puis réglé avec les paris (mêmes règles). Rien n'est effacé ; bilan par
profil : probabilité annoncée moyenne contre taux de réussite observé.

**Montante** : les suggestions de palier gardent leur plage de cote mais
utilisent les mêmes règles de marchés et les mêmes probabilités. Matchs des
3 prochains jours, ou de la prochaine journée pendant une trêve.

## Suppression du compte (02/10/2026)

Exigée par Google Play et l'App Store.

- Application : Profil → **Supprimer mon compte**, mot de passe redemandé
  (`POST /me/delete`).
- Sans l'application : page publique **`/suppression-compte`** (numéro et mot
  de passe, `POST /account/delete`, mêmes limites de tentatives que la
  connexion). Son adresse est celle à déclarer à Google Play.
- Effacés : numéro, nom, mot de passe, portefeuille fictif et mouvements,
  paris, montantes, notifications, téléphones enregistrés, historique Premium.
- Conservés sans lien avec la personne (obligation comptable) : paiements
  (montant, devise, date, référence du prestataire) ; réponse brute du
  prestataire vidée ; paiement en cours annulé (`cancelled`). Si un
  prestataire confirme ensuite un paiement annulé, le rembourser à la main.
- Le dernier administrateur ne peut pas se supprimer (en nommer un autre).

## Politique de confidentialité (02/10/2026)

Page publique **`/confidentialite`** (lien dans Profil → Confidentialité et
sur `/suppression-compte`) : données collectées et pourquoi, prestataires
(hébergeur, Firebase, paiement), durées (sauvegardes 14 jours, paiements
détachés après suppression, adresse IP au plus 1 heure), droits, ARTCI (loi
n° 2013-450), 18 ans et plus. Identité et contact réglables sans toucher au
code : `FP_LEGAL_NAME`, `FP_CONTACT_EMAIL` (`backend/.env` sur Termux,
`deploy/.env` en production) ; date de version : `PRIVACY_EFFECTIVE_DATE`
(`main.py`), à changer à chaque modification importante du texte.
Texte non relu par un juriste : à faire relire avant la publication sur les
magasins d'applications.

## Conditions d'utilisation (02/10/2026)

Page publique **`/conditions`** : probabilités et non certitudes, aucun pari
en argent réel, argent fictif sans valeur (ni achat, ni retrait, ni lot),
18 ans et plus, compte et usages interdits, Premium (prix, durée et essai
repris du code : `PREMIUM_PRICE`, `PREMIUM_DAYS`, `TRIAL_DAYS`), pas de
renouvellement automatique, remboursement si débité sans activation,
responsabilité, jeu responsable, droit ivoirien. Liens : écran
d'inscription (« En créant un compte, tu acceptes… »), Profil, page de
suppression. Même date de version que la confidentialité
(`LEGAL_EFFECTIVE_DATE`). Texte non relu par un juriste.
