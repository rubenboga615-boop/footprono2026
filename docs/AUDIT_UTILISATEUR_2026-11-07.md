# Essai en conditions réelles — 7 novembre 2026 (mesures du 06/11 au soir, GMT)

Site : `https://footproba.duckdns.org`. Serveur vérifié : `/api/v1/health` →
`"commit": "cfe4988"`. Compte de test Premium **+225 07 84 89 71 95**. Navigateur Chromium
réglé comme un téléphone (Pixel 7), et appels directs à l'API avec le même compte pour les
durées. Une requête simple (`/health`) prend 0,14 s depuis la machine de test.

## 0. Version de l'application servie : ancienne

| Ce que j'ai fait | Ce que j'ai vu |
|---|---|
| `curl -I /app/main.dart.js` | `last-modified: Fri, 06 Nov 2026 15:10:36 GMT` (version 131) |
| Recherche de textes récents dans `main.dart.js` | absents : « Ajout », « Le moteur étudie », « validées », « la cote la plus basse », « match écarté », « 12 au maximum » ; présent : « 10 au maximum » |

**Conséquence** : tous les changements de l'application depuis 15 h 10 (attente expliquée,
ajout en parallèle, suivi des paris en direct, nouvelle page Fiabilité, libellés « Buts de
Lyngby ») **ne sont pas visibles** sur le site. Les essais d'écran ci-dessous portent donc
sur l'ancienne application ; seuls les changements du serveur sont réellement testés.

**Piste** : publier `footprono-web.zip` construit sur `cfe4988` (console → Versions de
l'app), et l'APK correspondant.

## 1. Coupon intelligent

| Demande (`/smart-coupon`, appel direct) | Durée |
|---|---|
| Grosse cote 25, Prochaine journée — juste après le déploiement | **16,7 s** |
| même demande, juste après | 1,3 s |
| Équilibré, 3 sélections, Prochaine journée | 0,73 s |
| Sûr, 7 jours | 0,71 s |
| Grosse cote 100, 7 jours | 1,06 s |
| Grosse cote 25, Aujourd'hui | 0,66 s |
| Grosse cote 25, Prochaine journée — **à froid**, 10 min plus tard (18 h 53) | **15,2 s** |
| même demande, juste après | 1,3 s |
| Audacieux, Ce week-end | 0,76 s |
| Dans le navigateur (cache chaud) : « Composer le coupon » → coupon affiché | 1,7 s |

**Constat** : une fois les cotes en mémoire, tout répond en moins de 1,5 s. Mais **la
première demande après 10 minutes sans joueur prend encore 15 à 17 s**, toujours sous
la limite de 20 s de l'ancienne application, avec le même risque dès qu'il y a du monde.
L'index des cotes (migration 0029) n'a presque rien changé à froid (16 à 19 s avant).

**Piste** : la préparation dans Redis (`bookmaker/playable.py`) n'est remplie qu'après la
collecte des cotes (toutes les 3 heures, prochaine à 19 h 30) ou un calcul de pronostics :
**après un déploiement, Redis reste vide jusqu'à la collecte suivante**. La lancer aussi au
démarrage du serveur (ou à la fin de `install-server.sh`). À vérifier également sur le
serveur que l'index `ix_bookmaker_odds_match_bookmaker_bet` existe bien et qu'il est
valide (`\d bookmaker_odds` ; un index CONCURRENTLY interrompu reste « INVALID »).
Remesure prévue après la collecte de 19 h 30 (section 6).

## 2. Suggestions de montante avec deux montantes au même palier

| Ce que j'ai fait | Ce que j'ai vu |
|---|---|
| Montante n° 7 (palier 1, cote 1,55 à 1,65) existante ; création de la n° 8 avec le même plan (`POST /montantes`, 0,18 s) | les deux au palier 1 |
| `/montantes/7/suggestions` et `/montantes/8/suggestions`, deux fois chacune | 0,38 à 0,91 s |

- **Matchs différents : oui.** Montante 7 : matchs 29127, 29503, 59728 ; montante 8 :
  89230, 29131, 59729 ; aucun en commun. Mêmes propositions d'un appel à l'autre.
- **Plus de désaccord avec la cote** : moteur 57 à 68 %, cote 64,5 % (avant : 76 % contre 63 %).
- Toutes les propositions sont à **1,55**, le bas de la plage (règle voulue : cote la plus basse).
- **Peu clair** : une suggestion (montante 7, « les deux marquent » à 1,55) a **57 % selon
  le moteur pour 65 % selon la cote**. L'écran « Suggestions du moteur » propose donc un pari
  que le moteur juge moins probable que le bookmaker, sans le dire. **Piste** : l'expliquer
  (« le moteur est moins confiant que la cote ») ou écarter ces cas.

## 3. Ajout de 7 sélections au coupon (ancienne application)

| Ce que j'ai fait | Mesure |
|---|---|
| Coupon intelligent → Grosse cote 25 → Prochaine journée → Composer | 1,7 s |
| « Ajouter au coupon » → message « 7 sélection(s) ajoutée(s) » | **9,3 s, 20 requêtes** (hier 15,5 s, 21 requêtes) |
| Onglet Coupon → « Placer le pari » (1 000 F) | 2,1 s → pari n° 21 |

Le gain vient du serveur (`/matches/{id}/offer` plus rapide). L'ancienne application
envoie toujours les requêtes une par une, sans progression : à revérifier avec la nouvelle
version (« Ajout 3 / 7… », requêtes en parallèle).

## 4. Page Fiabilité (ancienne application)

| Ce que j'ai fait | Ce que j'ai vu |
|---|---|
| Profil → Fiabilité du moteur | page affichée en **6,1 s** (écran vide pendant ce temps) |
| `/reliability?recent=20` en appel direct, 3 fois | **6,8 s, 7,2 s, 6,0 s** (35 Ko) |
| `/health` pendant un `/reliability` | 0,14 s : les autres joueurs ne sont pas bloqués |

- C'est **l'ancienne page** : trois onglets (1 / N / 2, Buts, Les 2 marquent), filtre limité
  aux 5 grands championnats alors que 22 sont en service. La page « sur un seul écran avec
  tous les marchés » n'est pas encore publiée (voir section 0).
- **`/reliability` reste lent (6 à 7 s à chaque appel, sans cache).** Ces chiffres ne
  changent qu'au règlement des matchs. **Piste** : calcul gardé en cache (Redis) et refait
  après chaque règlement, comme les sélections jouables.

## 5. Règlement des sélections au fil des matchs (serveur)

Pari n° 20 (7 sélections, matchs du 06/11 de 18 h à 20 h GMT), lu avec `GET /bets` à 18 h 42 :

| Match | État renvoyé |
|---|---|
| Silkeborg – Lyngby | `live`, 42', 0-0 |
| Argeș Pitești – Dinamo Bucarest | `live`, 9', 0-0 |
| Hammarby – Elfsborg | `live`, **minute absente**, 0-0 |
| Hamburger SV – Mönchengladbach, Venezia – Udinese, Everton – Coventry, Sevilla – Alavés | `upcoming`, avec coup d'envoi |

- État en direct, minute, score et coup d'envoi : **présents dans l'API** (l'ancienne
  application ne les affiche pas encore).
- **Hammarby – Elfsborg sans minute** alors que le match est en cours (Allsvenskan) :
  « en cours · 0-0 » sans la minute. **Piste** : vérifier la minute renvoyée par le suivi
  en direct pour ce championnat.
- Règlement sélection par sélection : relevé prévu après la fin des matchs (section 6).

## 6. Suite de l'essai

(complétée plus tard dans la soirée)
