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
