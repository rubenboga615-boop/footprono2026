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
