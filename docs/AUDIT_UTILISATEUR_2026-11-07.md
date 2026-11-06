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

## 6. Suite de l'essai (soirée du 06/11)

### 6.1 Coupon intelligent après la collecte des cotes de 19 h 30

| Heure (GMT) | Demande | Durée |
|---|---|---|
| 19 h 50, **première demande** depuis plus d'une heure | Grosse cote 25, Prochaine journée | **2,2 s** |
| 19 h 50 | même demande, juste après | 1,8 s |
| 19 h 50 | Équilibré, Prochaine journée | 1,7 s |
| 19 h 50 | Grosse cote 50, 7 jours | 1,9 s |
| 22 h 02, première demande | Grosse cote 25, Prochaine journée | **1,8 s** |
| 22 h 02 | Équilibré / Grosse cote 50, 7 jours | 1,8 s / 1,9 s |

- **Corrigé** : une fois la préparation faite, la première demande passe de 15 à 17 s à
  environ 2 s. Le problème de la section 1 ne concerne donc que la période entre un
  déploiement et la collecte suivante (jusqu'à 3 heures).
- **Remarque** : avec la préparation Redis, chaque demande prend **environ 1,8 s**, même
  répétée, alors que le cache en mémoire répondait en 0,7 à 1,3 s. **Piste** : une partie
  du temps vient sans doute de la relecture et du décodage des cotes de tous les matchs de
  la période à chaque demande ; à mesurer côté serveur.

### 6.2 Suggestions de montante, deux montantes au même palier

| Heure | Montante 7 | Montante 8 | Durée |
|---|---|---|---|
| 19 h 50 | matchs 28164, 28492, 29131 | 28162, 59729, 74283 | 1,7 s / 2,7 s |
| 22 h 02 | mêmes | mêmes | 1,4 s / 2,5 s |

**Conforme** : toujours des matchs différents, et les mêmes d'un appel à l'autre. Durée
plus longue qu'à 18 h 50 (0,4 à 0,9 s), comme le coupon (voir 6.1).

### 6.3 Règlement des sélections au fil des matchs (pari n° 20, 7 sélections)

| Sélection (coup d'envoi) | 18 h 54 | 19 h 50 | 20 h 45 | 22 h 02 |
|---|---|---|---|---|
| Hammarby – Elfsborg, Elfsborg −2 (18 h 00) | en cours 11', 0-0 | en cours **50'**, 1-0 | **perdu**, 4-1 | perdu |
| Silkeborg – Lyngby, Lyngby moins de 1,5 (18 h 00) | en cours 45', 0-0 | en cours 90', 1-0 | **gagné**, 1-0 | gagné |
| Argeș – Dinamo, Argeș plus de 0,5 (18 h 30) | en cours 21', 0-0 | en cours 59', 1-0 | **gagné**, 2-1 | gagné |
| Hambourg – Gladbach, plus de 8,5 corners (19 h 30) | à venir | en cours 20', 1-0 | en cours 56', 1-1 | **perdu**, « 3-1 » |
| Venezia – Udinese, nul ou Udinese (19 h 45) | à venir | en cours 2' | en cours 45' | **perdu**, 2-1 |
| Everton – Coventry, moins de 2,5 buts (20 h 00) | à venir | à venir | en cours 42' | **perdu**, 3-1 |
| Séville – Alavés, plus de 7,5 corners (20 h 00) | à venir | à venir | en cours 43' | **gagné**, « 0-0 » |

Pari réglé **perdu à 20 h 34**, dès la première sélection perdue.

- **Corrigé** : chaque sélection est notée dès la fin de son match. Les sélections jouées
  après la perte du pari sont aussi notées ensuite (gagné ou perdu, plus jamais « en
  attente »). Même chose sur le pari n° 24 : Everton – Coventry noté perdu à 21 h 56.
- **Délai de règlement** : environ 5 minutes après la fin du match (Everton – Coventry,
  coup d'envoi 20 h, noté à 21 h 56). Correct.
- **Problème 1 — Hammarby – Elfsborg décalé d'environ 45 minutes.** Coup d'envoi annoncé à
  18 h 00, comme Silkeborg – Lyngby, mais 11' à 18 h 54 (Silkeborg : 45'), 50' à 19 h 50
  (Silkeborg : 90') et pari réglé à 20 h 34, soit une fin de match vers 20 h 30. Soit le
  coup d'envoi enregistré est faux (vrai coup d'envoi vers 18 h 45 ?), soit le suivi en
  direct de ce match a pris 45 minutes de retard. **Piste** : comparer l'heure du match en
  base avec celle d'API-Football (fixture Hammarby – Elfsborg du 06/11). Si l'heure en base
  est fausse, le joueur voit « à venir 18:00 », puis un match qui ne bouge pas.
- **Problème 2 — score en buts affiché pour un pari sur les corners.** « Séville – Alavés,
  plus de 7,5 corners : gagné, 0-0 » et « Hambourg – Gladbach, plus de 8,5 corners : perdu,
  3-1 ». Le joueur lit « 0-0 » à côté d'un pari gagné et ne comprend pas. **Piste** : pour
  les marchés corners, cartons et tirs, afficher le nombre de corners (par exemple
  « 11 corners ») au lieu du score, ou les deux.
- L'API renvoie tout ce qu'il faut (état, minute, score, résultat), mais **l'application
  en ligne ne l'affiche pas encore** : elle n'a pas été republiée (section 0).

### 6.4 Relevé automatique

Le relevé programmé jusqu'à 22 h 10 a été arrêté par un redémarrage de la session ; le
dernier relevé a été fait à la main à 22 h 02 (tous les matchs du pari n° 20 étaient
terminés).

## 7. Résumé pour le fondateur

| Point demandé | Résultat |
|---|---|
| Grosse cote 25, Prochaine journée | **≈ 2 s** après la collecte des cotes ; **15 à 17 s** entre un déploiement et la collecte suivante |
| Profil Équilibré | 0,7 à 1,8 s |
| Suggestions, deux montantes au même palier | **conforme** : matchs différents, 0,4 à 2,7 s |
| Ajout de 7 sélections | 9,3 s ; à revérifier avec la nouvelle application (non publiée) |
| Nouvelle page Fiabilité | **non testable** : application non publiée ; `/reliability` 6 à 7 s |
| Règlement au fil des matchs | **conforme côté serveur** ; deux défauts (heure d'un match, score des paris corners) |

**Changements urgents à transmettre :**
1. Publier la version web (et l'APK) construite sur `cfe4988` : sans elle, aucune
   amélioration de l'application n'est visible.
2. Préparer les sélections jouables (Redis) au démarrage du serveur, pas seulement après
   la collecte des cotes.
3. Mettre en cache le calcul de `/reliability` (6 à 7 s à chaque ouverture de la page).

## 8. Écrans de la nouvelle version web (publiée à 19 h 24, essai à 22 h 05)

Vérification : `main.dart.js` du 06/11 à 19:24:40 ; contient « Ajout … / … »,
« Le moteur étudie », « 12 au maximum », « matchs écartés », « à venir », « terminé ».

### 8.1 Coupon intelligent et ajout au coupon

| Ce que j'ai fait | Mesure / ce que j'ai vu |
|---|---|
| Onglet Coupon vide | « Un combiné réunit des matchs différents (**12 au maximum**) » : corrigé |
| Grosse cote 25 → Prochaine journée → Composer | coupon affiché en **2,7 s** ; « Recherche… » seulement (le message d'attente n'apparaît qu'après 4 s : normal) |
| « Ajouter au coupon » (8 sélections) | **4,5 s, 16 requêtes** (hier 15,5 s, ce soir 9,3 s avec l'ancienne version) |
| Bouton pendant l'ajout | « Ajout 0 / 8… » (0,3 s) → « 1 / 8 » (2,6 s) → « 3 / 8 » → « 5 / 8 » → « 7 / 8 » (4,0 s) |

**Conforme.** Détail : le message final dit encore « 8 sélection(s) ajoutée(s) » (avec
« (s) »). Le premier retour arrive à 2,6 s : un des 16 appels est plus lent que les autres.

### 8.2 Suivi des paris (Bookmaker → Réglés → fiche d'un pari)

| Pari | Ce qui est affiché pour chaque sélection |
|---|---|
| n° 24 (perdu) | « Ven. 6 nov. 20:00 · perdu · 3-1 » (rouge, croix) ; les 6 autres : « Sam. 7 nov. 13:00 · à venir », etc. (horloge) |
| n° 20 (perdu) | « Ven. 6 nov. 18:00 · perdu · 4-1 », « … · gagné · 1-0 », etc. pour les 7 |

**Conforme** : date, heure, état et score par sélection, lisibles (capture : fiche du pari
n° 24). Restent :
- **Score en buts sur les paris corners** (déjà vu en 6.3) : « Total de corners · Plus de
  7,5 corners — gagné · 0-0 ». **Piste** : afficher le nombre de corners.
- **Pari perdu avec 6 sélections « à venir »** (n° 24) : rien ne dit que le pari est déjà
  perdu à cause de la première sélection et que les autres ne comptent plus. **Piste** :
  une phrase « Pari perdu sur Everton – Coventry ; les autres matchs restent affichés pour
  information ».
- Avancement « x sur 7 validées · y en cours » non vérifiable ce soir : aucun pari ouvert
  avec des matchs en cours au moment de l'essai. À revérifier demain après-midi.
- Lecteur d'écran : la fiche est annoncée avec des mots anglais de Flutter (« Dialog »,
  « Dismiss », « Scrim »).

### 8.3 Coupons du jour

| Ce que j'ai fait | Ce que j'ai vu |
|---|---|
| Aujourd'hui (06/11) | Sûr perdu (2/3 validées), Équilibré perdu (1/3), Audacieux **gagné** (2/2) |
| Hier (05/11, aucun coupon) | « Aucun coupon ce jour-là : aucun match ne respectait les règles des profils (sélections dans leur tranche de probabilité, vraie cote, cote totale minimale). » |

**Conforme** : la journée sans coupon est expliquée. Le message par profil absent n'a pas
pu être vu (les trois profils étaient présents le 06/11).

### 8.4 Nouvelle page Fiabilité

| Ce que j'ai fait | Mesure / ce que j'ai vu |
|---|---|
| Profil → Fiabilité du moteur | page affichée en **6,5 s** (`/reliability` toujours 6 à 7 s) |
| Écran | **tient sur un seul écran** : bandeau, choix du marché et du championnat, graphique, deux chiffres clés (7,9 % d'erreur en moins que la moyenne, 1,7 % de plus que les bookmakers) |
| « Marché » | liste de **29 marchés** par famille, chacun avec son écart (« Résultat du match ✓ 3 pts » … « Cartons : le plus de ✓ 4 pts ») |
| « Championnat » | « 5 grands » + 20 championnats |
| Onglet « Depuis le lancement (394) » | calibration réelle par tranche |

**Conforme dans l'ensemble.** Incohérences à corriger :
1. **3 ou 4 points ?** Le bandeau dit « justes à **4** points près », la carte juste en
   dessous « ✓ juste à **3** points près », et « Cartons : le plus de » a un ✓ avec
   **4 pts** alors que la règle publiée est 3 points. Le joueur ne sait plus quelle est la
   règle. **Piste** : une seule règle, et pas de ✓ au-delà.
2. **Onglet « Depuis le lancement » sans avertissement** : 44 % annoncé → **58 %** arrivé,
   64 % → **73 %** (écarts de 14 et 9 points), sans aucune mention, alors que l'onglet
   Simulation affiche « ✓ juste à 3 points près ». **Piste** : afficher aussi le verdict sur
   les résultats réels (« pas encore juste : trop prudent sur les favoris »), avec le nombre
   de cas par tranche.
3. **Filtre et note contradictoires** : le filtre indique « Championnat : 5 grands », la note
   sous le graphique dit « Pronostics publiés avant les matchs, **tous les championnats** ».
4. **Serbie et Israël absents** de la liste des championnats (22 en service, 20 listés).
5. Les deux chiffres clés (7,9 % et 1,7 %) ne changent pas entre « Simulation » et « Depuis
   le lancement » : on ne sait pas à quoi ils se rapportent.

### 8.5 Suggestions de montante (écran)

| Ce que j'ai fait | Mesure / ce que j'ai vu |
|---|---|
| Montante → carte « Suggestions du moteur » | écran affiché en **4,35 s** (`/suggestions` 3,6 s, puis 3 matchs en parallèle 0,5 s) |
| Écran | « Suggestions — la cote la plus basse d'abord » ; 3 paris simples à 1,55 ; « Modèle 60 % / 68 % / 62 % — Selon la cote 64,5 % » |

**Conforme.** Restent :
- `/suggestions` à **3,6 s** ici (0,4 à 2,7 s plus tôt dans la soirée) : à surveiller.
- La carte « Suggestions du moteur » **n'est pas un bouton pour le lecteur d'écran** (déjà
  noté le 06/11) : je l'ai touchée par sa position.
- Badge rouge **« 2 » sur l'onglet Profil** sans explication visible à l'ouverture du profil
  (notifications ?). À vérifier.

## 9. Bilan des écrans

| Écran | Verdict |
|---|---|
| Ajout de 7 à 8 sélections | **corrigé** : 4,5 s avec progression |
| Suivi des paris (date, état, score) | **corrigé** ; reste le score des paris corners |
| Coupons du jour (libellés, jours sans coupon) | **corrigé** |
| Page Fiabilité sur un seul écran | **en place** ; règle 3 / 4 points et résultats réels à clarifier ; 6,5 s de chargement |
| Suggestions de montante | **corrigé** (matchs différents, tri neutre) ; 3,6 s |
