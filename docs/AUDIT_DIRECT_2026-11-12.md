# Le direct en conditions réelles — 12 novembre 2026

Première vérification des étapes 6 à 8 du plan du 10/11 (chances en direct, onglet « En
direct », règlement pendant le match) sur de vrais matchs. Serveur `9115349`, version web du
11/11 à 00:32, compte Premium. Rien n'a été modifié dans le code.

## 15 h 07 GMT — Ghana – Somalie (CAN, éliminatoires), 2e minute, 0-0

| Élément | Constat |
|---|---|
| Liste des matchs | puce « ● En direct 1 » en tête des jours ; carte « 2' · 0 – 0 » avec « Chances en direct · avant le match : 84 % · 13 % · 4 % » ; **★ devant les matchs de mes paris** (« ★ en haut : les matchs de tes paris en cours ») |
| Lecteur d'écran | « Ghana – Somalie, en direct 2', 1 83 %, N 13 %, 2 4 %, ouvrir le match » |
| Écran du match | « 0 – 0 · ● En direct 2' » ; nouvel onglet **En direct** en premier, avec **Résumé · Statistiques · Compositions** |
| Résumé | « Pas encore d'événement dans ce match. » puis **Chances en direct** (2') : Ghana 83 %, nul 13 %, Somalie 4 %, plus de 3,5 buts 34 % ; « Avant le match : 84 % · 13 % · 4 %. Recalculé avec le score et la minute ; ce n'est pas un conseil de pari. » |
| Probabilités, Cotes | bandeau « Chances calculées avant le coup d'envoi… Paris fermés sur ce match » ; chaque cote marquée « fermé » |

Premier constat : **tout ce qui était demandé le 7/11 est là et clair.** Suite pendant les
matchs de 16 h (pari n° 66), de 17 h (pari n° 64) et le soir.

## Retour du fondateur (15 h 10) : il faut sans cesse actualiser, et le direct arrive tard

Le fondateur a suivi Ghana – Somalie : il a dû **actualiser à la main sans arrêt**, et le
match n'est passé « en direct » que vers **15 h 05** (coup d'envoi prévu à 15 h).

### Causes trouvées dans le code

| # | Cause | Où | Effet pour le joueur |
|---|---|---|---|
| 1 | **La liste des matchs ne se recharge jamais seule** : seulement en tirant l'écran vers le bas | `app/lib/screens/matches_screen.dart` (aucun minuteur) | un match qui commence, un but, la minute : rien ne bouge tant qu'on n'actualise pas |
| 2 | **L'écran d'un match ne se recharge pas seul** (score, minute, onglets Probabilités et Cotes) | `match_screen.dart` (rechargement seulement en tirant l'écran) | idem sur l'écran du match |
| 3 | **L'onglet « En direct » se recharge chaque minute seulement si le match était déjà commencé quand on a ouvert l'écran** | `live_tab.dart` l. 54 (`if (widget.match.isLive)`) | écran ouvert à 14 h 58 : rien ne se met à jour après le coup d'envoi |
| 4 | Le serveur relève les matchs **toutes les 2 minutes** | `worker/celery_app.py` (`follow_live`, `*/2`) | jusqu'à 2 min de retard sur la source, plus le retard d'API-Football |
| 5 | Le WebSocket déjà ouvert par l'application ne transporte que les notifications, **pas les scores** | `app_state.dart`, `ingestion/live.py` | l'application doit redemander au lieu de recevoir |
| 6 | Le match ne devient « en direct » que quand API-Football le dit commencé : à 15 h 05 l'écran montrait « 2' », le vrai coup d'envoi était donc vers 15 h 03 | — | normal, mais rien n'indique « coup d'envoi imminent » entre 15 h et 15 h 03 |

### Corrections proposées (par ordre d'effet)

1. **Envoyer chaque relevé par le WebSocket** (score, minute, événements, chances en direct)
   à l'application ouverte : la liste et l'écran du match changent **sans actualiser**, sans
   requête de plus.
2. En attendant ou en secours : **rechargement automatique toutes les 30 secondes** de la
   liste des matchs et de l'écran d'un match **quand un match est en cours ou commence dans
   les 10 minutes**, **seulement application ouverte** (pas en arrière-plan : voir
   `AUDIT_OBSERVATOIRE_2026-11-09.md`). L'onglet « En direct » doit démarrer son minuteur
   aussi quand le match commence après l'ouverture de l'écran.
3. **Relevé toutes les minutes au lieu de 2** pendant les matchs (`/fixtures?ids=`, 20 matchs
   par requête : environ 60 requêtes par heure de match ; vérifier le quota du forfait).
4. Entre l'heure prévue et le vrai coup d'envoi : « Coup d'envoi imminent » sur la carte.
5. Indiquer l'heure du dernier relevé (« mis à jour il y a 40 s ») pour que le joueur sache
   que c'est vivant.

## 16 h 07 — comparaison avec une application de scores (captures du fondateur)

Serveur `4d22991` (mis à jour pendant l'après-midi), version web inchangée (11/11, 00:32).

| Match | Autre application (16:07) | Serveur FootProba (relevé de 16:08:00) |
|---|---|---|
| Ghana – Somalie | Mi-temps, 1-0 | HT, 45', 1-0 ; événements (penalty manqué 14', carton…) |
| RD Congo – Sierra Leone | 6', 1-0 | 1H, 6', 1-0 ; but de Wissa à la 4e (passe de Mbuku) ; statistiques présentes |
| Guinée équatoriale – Zimbabwe | 4', 0-0 | 1H, 4', 0-0 |
| Madagascar – Guinée-Bissau | 7', 0-0 | 1H, 8', 0-0 |
| **Guinée – Érythrée** | **17:00** (pas commencé) | **prévu 16:00**, NS ; l'application affiche « Coup d'envoi imminent » et « Paris fermés » |

**Le serveur est à l'heure** : minute à 1 près, buts, buteurs, cartons et statistiques
présents dans le relevé de 16:08. Le retard ressenti vient de l'**application, qui ne se
recharge pas seule** (section précédente) : sur la capture, le fondateur tire l'écran pour
actualiser.

**Guinée – Érythrée** : l'heure diffère d'une heure entre les deux sources. API-Football
indique encore 16:00 (le serveur relit l'heure à chaque relevé). Si le match est bien à
17:00, FootProba affiche « Coup d'envoi imminent » et ferme les paris **une heure trop tôt**.
**Piste** : 10 minutes après l'heure prévue sans coup d'envoi, afficher « Coup d'envoi
retardé (heure à confirmer) » au lieu de « imminent » ; garder les paris fermés (prudent).

## 16 h 17 – 16 h 25 — nouvelle version web (12/11, 16:16), serveur `4d22991`

Essai : application ouverte, **jamais actualisée à la main** pendant 8 minutes ; captures du
fondateur à 16 h 18 comparées à une autre application de scores.

| Point | Constat |
|---|---|
| Mise à jour seule | **oui** : écran de Guinée équatoriale – Zimbabwe 17' → 18' → 19' → 20' sans rien toucher ; « Mis à jour il y a 30 s / 1 min » ; chances en direct recalculées (47 % → 46 %, plus de 3,5 buts 14 % → 12 %) |
| WebSocket | un message `live` chaque minute (16:18:03, 16:19:03, 16:20:04, 16:21:03) avec minute, score et statut de chaque match |
| Cartes de la liste (capture du fondateur) | minute, score, **buteur** (« ⚽ 4' Yoane Wissa », « ⚽ 45+2' Jonas Adjetey »), chances en direct (RD Congo 90 % après le but, Ghana 93 %), « Mis à jour il y a 57 s », ★ sur le match d'un pari |
| Retard sur l'autre application (16 h 18) | Ghana 52' contre 54' ; RD Congo 15' contre 17' ; Guinée éq. 13' contre 14' : **1 à 2 minutes** (relevé chaque minute + retard de la source). Acceptable pour suivre un match ; à dire au joueur (« relevé chaque minute ») |

**Nouveau défaut — trop de requêtes** : pendant ces 8 minutes, l'application a envoyé
**158 requêtes** au serveur (environ 20 par minute), dont `/predictions/upcoming?limit=400`
(tous les matchs) toutes les 45 secondes environ, et à chaque fois `prediction`, `offer`,
`analysis`, `picks` de l'écran du match. Avec 1 000 joueurs devant un match, cela ferait
environ **20 000 requêtes par minute**. **Piste** : le message `live` du WebSocket contient
déjà minute, score et statut : mettre à jour l'écran à partir de ce message, et ne recharger
que ce qui change (`/live/summary`, `/live/chances` des matchs en cours), pas toute la liste
ni l'analyse.

## 16 h 37 — pari n° 66 pendant Guinée équatoriale – Zimbabwe (33', 0-0)

| Écran | Constat |
|---|---|
| Fiche du pari | « **Chance de ton coupon : 41 % au départ → 46 % maintenant** · D'après le score et la minute de chaque match » ; sélection « En direct 33' · 0-0 · **gagnante pour l'instant** » avec un point vert ; « 0 sur 3 validée · 1 en cours · 2 à venir » ; « Pour l'instant d'après le score actuel ; le règlement se fait à la fin du match » |
| « Suivre › » | ouvre directement l'onglet En direct du match |
| Résumé | carton jaune « Kelvin Njabulo Moyo 🟨 24' » ; chances en direct 43 % · 37 % · 20 % (avant le match 50 · 28 · 21) ; plus de 3,5 buts 8 % |
| Statistiques | tirs cadrés 1-0, tirs 1-0, corners 1-0, possession 61-39 %, xG 0,2-0, fautes 5-9, cartons 0-1, arrêts 0-1 |
| Compositions | les deux équipes en 4-4-2 sur un terrain, numéros et noms, entraîneur (« V. Annese ») |

Tout est conforme à la proposition du 7/11. Un seul détail : sous les statistiques, « Mis à
jour toutes les 2 minutes (API-Football) » — c'est désormais chaque minute.

## 16 h 40 — « Plus de 3,5 buts » affiché sur tous les matchs (question du fondateur)

**Cause** : la ligne est **fixée dans l'application**, quel que soit le score :
`app/lib/widgets/live_chances.dart` l. 197, `p('OU|3.5|over')`. Le serveur envoie pourtant
toutes les lignes (0,5 à 5,5) pour chaque match.

**Effet** : sur Madagascar – Guinée-Bissau, 0-0 à la 40e, « Plus de 3,5 buts : 8 % » ne dit
rien d'utile ; sur RD Congo – Sierra Leone (2-0), la question intéressante est « y aura-t-il
encore un but ? » (plus de 2,5 : 81 % au relevé de 16:39).

**Piste** : afficher la ligne « **encore un but** » = buts déjà marqués + 0,5
(« Encore au moins un but : 81 % »), et éventuellement la ligne suivante. Ce chiffre change
après chaque but et parle à tout le monde.

## 16 h 50 — Comment savoir si la source donne des cotes 1xBet en direct ?

**Méthode prévue** : console → Diagnostic → **« Tester le direct »** (`console/actions.py`,
`live_probe` ; `ingestion/live.py`, `probe_live`). Deux requêtes API-Football :
`/fixtures?ids=<match>` et `/odds/live?fixture=<match>`, sur un match en cours (le plus
récent si le champ est vide). Rien n'est enregistré. Résultat : « cotes en direct : N
marchés » ou « aucune », avec la liste des noms de marchés (40 au plus).

**Limites de ce test** (lecture du code) :

1. **Il ne dit pas de quel bookmaker viennent les cotes.** Il ne garde que le nombre de
   marchés et leurs noms. Or la question du plan (point 0.3) est « 1xBet est-il présent ? ».
   D'après ce que je connais du format d'API-Football (à confirmer sur une vraie réponse),
   `/odds/live` ne donne **pas** de bookmaker par cote, contrairement aux cotes d'avant-match :
   la réponse seule ne permettra peut-être pas de répondre.
2. Il ne montre **aucune valeur de cote**, ni l'état des marchés (suspendu, bloqué), ni
   l'heure de mise à jour : impossible de comparer avec l'application 1xBet.
3. Un seul match à la fois.
4. L'exemple de réponse utilisé par les tests (`tests/test_live_details.py` l. 85) est
   inventé (noms de marchés seulement) : le format réel n'a jamais été regardé.

**Proposé** :

- Enrichir le test : garder **la réponse brute** (fichier téléchargeable dans la console),
  et afficher pour le résultat du match et le plus/moins de 2,5 buts les **valeurs des
  cotes**, l'état « suspendu », l'heure de mise à jour et le champ bookmaker s'il existe.
- Le lancer sur **deux ou trois matchs en cours**, et au même moment noter les cotes de
  l'application 1xBet pour les mêmes marchés : si elles sont identiques (à 0,02 près), la
  source suit 1xBet ; sinon non.
- Écrire au support d'API-Football : « De quel bookmaker viennent les cotes de
  `/odds/live` ? 1xBet est-il disponible en direct ? »

## 16 h 55 — Résultat de « Tester le direct » (lancé par le fondateur)

RD Congo – Sierra Leone, mi-temps (45') :
- Blocs : events, fixture, goals, league, lineups, players, score, statistics, teams ;
  3 événements (Card, Goal), 2 compositions, 46 joueurs, **17 statistiques** (dont
  `expected_goals`).
- **Cotes en direct : oui, 27 marchés**, dont ceux du Coupon intelligent : Fulltime Result
  (1X2), Match Goals et Over/Under Line (plus/moins de buts), Both Teams to Score, Home /
  Away Team Goals, Asian Handicap, 3-Way Handicap, corners ; et des marchés propres au
  direct (« Which team will score the 3rd goal? », « Race to the 7th corner? », « Last
  Corner »…).

**Ce que ça établit** : la source **fournit des cotes en direct, y compris à la mi-temps**
(le seul moment vérifié par l'étude de l'étape 8). L'étape 9 est donc possible côté
données.

**Ce que ça n'établit pas** : **de quel bookmaker** viennent ces cotes. Les noms des
marchés (« Match Goals », « Asian Corners », « Race to the 7th corner? », « Last Team to
Score (3 way) ») sont ceux qu'emploie **Bet365** en direct ; c'est un indice, pas une
preuve. Si ce n'est pas 1xBet, un coupon en direct affichera des cotes **différentes** de
celles que le joueur trouvera dans 1xBet.

**Étape suivante** (avant tout développement du coupon en direct) : améliorer le test pour
afficher les **valeurs** des cotes du 1X2 et du plus/moins de 2,5 buts et l'heure de mise
à jour ; le lancer pendant un match et, à la même minute, noter les cotes de l'application
1xBet. Mêmes cotes à 0,02 près : la source suit 1xBet. Sinon : coupon en direct affiché
avec « cote indicative, à vérifier dans 1xBet », ou pas de coupon en direct.

## 17 h 04 — Guinée – Érythrée toujours « à venir », et règlement anticipé confirmé

Capture du fondateur à 17 h 03 (pari n° 56 et montante « simple » sur ce match) et contrôle
du serveur à 17:04.

1. **Règlement pendant le match : confirmé.** Le pari n° 62 du fondateur affiche « **1 sur 5
   validée** » : la sélection « RD Congo – Sierra Leone, plus de 1,5 but » (2-0 à la 35e) a été
   validée avant la fin du match, environ 4 minutes après le but, comme prévu.
2. **Guinée – Érythrée bloqué.** À 17:04, le serveur relit le match chaque minute (dernier
   relevé 17:04:00) mais API-Football répond toujours **« NS » (pas commencé) avec un
   coup d'envoi à 16:00**, alors qu'une autre application de scores l'annonçait à 17:00.
   Deux explications possibles : le match a pris encore plus de retard, ou API-Football a
   créé une **nouvelle fiche** pour le match déplacé et l'ancienne (n° 1545874), que suit
   FootProba, ne bougera plus.
   - Effet pour le joueur : « Jeu. 12 nov. 16:00 · à venir » une heure après l'heure
     affichée, « Coup d'envoi imminent » sur l'écran du match, pari et montante bloqués.
   - Si la fiche ne bouge plus, la sélection ne sera **remboursée qu'après 48 heures**
     (`VOID_AFTER`, `bookmaker/settlement.py` l. 79) : le coupon et la montante du joueur
     restent bloqués deux jours.

**Pistes** :
- **Alerte au fondateur** quand un match d'un pari ou d'un coupon en cours est encore « NS »
  30 minutes après l'heure prévue.
- Console : « **Rechercher le match chez API-Football** » (mêmes équipes, même semaine) pour
  rattacher la nouvelle fiche si elle existe.
- Écran du match et fiche du pari : « Coup d'envoi retardé, heure à confirmer » au lieu de
  « imminent » / « à venir » quand l'heure prévue est dépassée.

**17 h 06 (mise à jour)** : Guinée – Érythrée est passé « En direct 2' · 0-0 · gagnante pour
l'instant » dans le pari n° 56 du fondateur (« Chance de ton coupon : 7 % au départ → … »).
C'était donc **un retard d'environ une heure, pas une fiche en double** : la même fiche
API-Football s'est mise à jour au coup d'envoi réel (vers 17 h 04). Restent valables :
l'affichage « Coup d'envoi retardé, heure à confirmer » quand l'heure prévue est dépassée
(une heure de « Coup d'envoi imminent » et « à venir 16:00 » ici), et l'alerte au fondateur
au-delà de 30 minutes. La recherche d'une nouvelle fiche devient secondaire.

## 17 h 20 – 17 h 31 — Vérification de la version 209 (serveur avec `292a01b`, web du 12/11 à 17:20)

| Point annoncé | Constat | Verdict |
|---|---|---|
| Serveur à jour | `/health` : commit `93e0e86`, qui contient `292a01b`, `5c25d89` et `df84829` | **oui** |
| Écran d'un match : environ 1 requête par minute | Turquie – Belgique, 2 minutes : **2 requêtes** (`/matches/110474/live`), score passé de 1-0 à 1-1 **sans requête** (message `live` du WebSocket) | **oui** (158 en 8 min avant) |
| Liste des matchs | 2 minutes : **6 requêtes**, toutes `/bets`, `/me/wallet/entries`, `/me/bets-summary` (une série par minute) | **non** : ce sont les données de **Mes paris**, onglet caché, qui se rechargent encore chaque minute alors que la liste est affichée |
| `openapi.json` coupé | `/api/v1/openapi.json` : 404 | **oui** |
| CSP sur `/app/` | présente (scripts du domaine, Firebase par empreinte, `frame-ancestors 'self'`) ; **aucun blocage** dans la console du navigateur pendant l'essai | **oui** (connexion Google non essayée) |
| Caddy rechargé | **`X-Frame-Options` et `Permissions-Policy` toujours absents** (sur `/app/` et `/api/v1/health`) | **non** : Caddy garde l'ancienne configuration ; sans gravité immédiate (la CSP de l'application interdit déjà l'affichage dans un autre site) |
| certifi | `requirements.lock` : 2026.10.23 | **oui** (dans le dépôt) |
| Verrou du règlement | lu dans le commit `5c25d89` (verrou PostgreSQL, test 4 règlements → 1 paiement) | **oui** (lecture, pas d'essai) |
| Rappel avant le coup d'envoi | notifications « Ton pari commence dans 30 min » (15:30) et « 2 de tes paris commencent bientôt — Arménie - Chypre commence dans 30 min » (16:30) | **oui** ; la seconde ne cite qu'un match sur deux (Turquie – Belgique manque) |

Autres remarques :
- **RD Congo – Sierra Leone 3-0 à la 66e : la carte affiche « 1 100 % · N < 1 % · 2 0 % ».**
  À la 66e, rien n'est certain : écrire « > 99 % » et « < 1 % », jamais 100 % ni 0 %.
- Le coupon en direct reste suspendu à la comparaison des cotes avec 1xBet (« Tester le
  direct » enrichi, à lancer par le fondateur pendant un match).

## 17 h 40 — Après la mise à jour du serveur (`f7d15ae`)

- Serveur `f7d15ae` (« Tester le direct : score de la source et minute de chaque but »).
  Version web inchangée (17:20). `openapi.json` : 404. CSP présente.
- **`X-Frame-Options` et `Permissions-Policy` toujours absents** malgré le `caddy reload`
  ajouté à `install-server.sh`.

**Cause probable** : `docker-compose.yml` monte **un seul fichier**
(`./Caddyfile:/etc/caddy/Caddyfile:ro`). Quand `git pull` remplace le Caddyfile, il crée un
nouveau fichier ; le conteneur garde l'**ancien** (montage d'un fichier = lien vers l'ancien
fichier sur le disque). `caddy reload` relit donc l'ancienne version **et réussit**, si bien
que le `restart` de secours ne se lance jamais.

**Correction** : remplacer le rechargement par une recréation du conteneur
(`docker compose … up -d --force-recreate caddy`), ou monter le **dossier**
(`./caddy:/etc/caddy:ro`) plutôt que le fichier. Contournement immédiat sur le serveur :
`cd /opt/footprono/deploy && docker compose --env-file .env up -d --force-recreate caddy`.

Les points 1, 3 et 4 de la section précédente (Mes paris caché, 100 %, notification) ne
sont pas encore dans cette version.
