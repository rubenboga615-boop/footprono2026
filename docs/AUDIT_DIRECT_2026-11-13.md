# Audit du direct — version 212 (notifications pendant les matchs, « Encore au moins un but »)

## 12/11, 22 h 12 GMT — Mise en ligne, contrôles hors match

| Point | Constat | Verdict |
|---|---|---|
| Serveur | `/api/v1/health` → commit `c273de8`, qui contient `6caf8da` (seuls des rapports d'audit ont été ajoutés après) | à jour |
| Version web | `main.dart.js` du 12/11 22:08 ; contient « Encore au moins un but », « Au moins un but dans le match », « chances de tenir », « Pendant mes matchs » | 212 en ligne |
| Nouvelle colonne joueur | `/me` renvoie `match_notifications: "all"` | présente |
| Profil → Pendant mes matchs | ligne « Pendant mes matchs · Tout », feuille avec Tout / Validé ou perdu / Rien et la mention « Rien sur le téléphone entre 23 h et 8 h » | conforme |
| Enregistrement du réglage | « Validé ou perdu » → l'API renvoie `results` ; retour à « Tout » → `all` | conforme |
| `/metrics`, en-têtes | 404 ; CSP et HSTS présents | toujours bons |

Pas de match en cours à cette heure : les notifications pendant les matchs et la carte
« Chances en direct » seront vérifiées le 13/11. Matchs prévus :
- Burkina Faso – Mauritanie (16:00, pari 58) ;
- Moldavie – Kazakhstan (17:00, dernier match du pari 58) ;
- Écosse – Macédoine du Nord (19:45, pari 57).

## 12/11, 23 h 06 GMT — Version 213 en ligne

- Serveur : `/api/v1/health` → commit `13f1057` (rappel de chaque match, « C'est parti »,
  but annulé, élision).
- Version web : `main.dart.js` du 12/11 à 23:05. Les textes des notifications viennent du
  serveur, donc l'application ne les contient pas, et c'est normal.
- Test pendant de vrais matchs prévu le 13/11, à partir de 15:24 :
  - rappels de 15:30 (Burkina Faso – Mauritanie) et 16:30 (Moldavie – Kazakhstan) ;
  - « C'est parti » à 16:00 et 17:00 ;
  - pari placé moins de 30 min avant un match ;
  - réglage « Validé ou perdu » pendant Écosse – Macédoine du Nord (19:45).

## 13/11, 15 h 51 – 18 h 55 GMT — Test des versions 212 et 213 pendant de vrais matchs

Serveur `cbc6069`. Compte Premium de test, réglage « Pendant mes matchs : Tout » jusqu'à
18:53. Notifications relevées toutes les 30 s (`/me/notifications`), buts et statuts relevés
dans `/matches/{id}/live`.

### Chronologie

| Heure | Notification | Événement réel | Délai | Verdict |
|---|---|---|---|---|
| 12:30:00 | ⏰ Dans 30 min : Zambie - Burundi (ton coupon n° 68, 0 sur 2 validée) | coup d'envoi 13:00 | — | conforme |
| 13:05:02 | 🟢 C'est parti : Zambie - Burundi | coup d'envoi vers 13:04 | ≤ 1 min | conforme |
| 15:02:03 | « Tes matchs en cours » : ✅ « Burundi (+2) » validé (Zambie 1-1 Burundi), 1 sur 2 / tout se joue sur Moldavie - Kazakhstan (17:00) | fin du match vers 14:58 | ~4 min (attente VAR) | conforme, regroupement OK |
| *15:30* | *aucun rappel* pour Burkina Faso – Mauritanie (pari 58) | — | — | **défaut 1** |
| 16:02:02 | 🟢 C'est parti : Burkina Faso - Mauritanie | 1re minute vue à 16:02 | ≤ 1 min | conforme ; il couvre le **pari 74, placé à 15:52** (moins de 30 min avant, donc sans rappel) |
| 16:30:00 | ⏰ Dans 30 min : Moldavie - Kazakhstan (ton coupon n° 68, 1 sur 2 validée) | — | — | conforme pour le n° 68 ; **le n° 58 n'est pas cité** (défaut 1) |
| *16:48 → 17:07* | rien pendant la pause, puis « Pari perdu — ❌ Burkina Faso 0-0 Mauritanie : « plus de 0,5 but à la mi-temps » est perdu. Ton coupon de 1 000 F CFA est perdu. » à 17:07:02 | mi-temps 0-0 vers 16:48 | **~19 min** | texte conforme, **délai : défaut 2** |
| 17:02:02 | 🟢 C'est parti : Moldavie - Kazakhstan | 1re minute vue à 17:02 | ≤ 1 min | conforme |
| 17:41:02 | ⚽ 40' Moldavie 1-0 Kazakhstan : « nul ou Kazakhstan » est perdante pour l'instant | but à la 39e | ~1 min | conforme |
| 17:52:02 | ⚽ 90' Burkina Faso 1-0 Mauritanie : « Burkina Faso ou Mauritanie » est gagnante pour l'instant | but à la **90+4e** | ~1 min | **minute affichée « 90' » au lieu de « 90+4' »** (défaut 3) |
| 17:56:03 | Pari gagné — Burkina Faso - Mauritanie : 615 F CFA crédités | fin vers 17:55 | ~1 min | conforme (500 × 1,23) |
| 18:09:01 | ⚽ 52' Moldavie 1-1 Kazakhstan : « nul ou Kazakhstan » est gagnante pour l'instant | but à la 51e | ~1 min | conforme |
| 18:35:02 | ⚽ 78' Moldavie 2-1 Kazakhstan : … perdante pour l'instant | but à la 77e | ~1 min | conforme |
| 18:52:02 | Pari perdu — ❌ Moldavie 2-1 Kazakhstan : « nul ou Kazakhstan » est perdu. Ton coupon de 1 500 F CFA est perdu. | fin vers 18:51 | ~1 min | conforme |

**Toucher une notification** (version web, Profil → Notifications → « Tes matchs en
cours ») : ouvre **Mes paris**. Conforme.

**Jamais deux notifications dans la même minute** : conforme. À 15:02, les deux
événements sont partis ensemble sous « Tes matchs en cours ».

**Aucune notification ne propose de parier** : conforme.

### Défauts

1. **Les paris rappelés avant le 13/11 n'ont plus aucun rappel pendant 2 jours.**
   `bookmaker/kickoff.py` met dans `old_bets` tout pari qui a reçu un rappel de l'ancien
   modèle (par pari) depuis moins de 2 jours, et les écarte entièrement.
   - Le pari 58 (rappelé le 12/11 à 19:15) n'a eu de rappel ni pour Burkina Faso –
     Mauritanie (15:30) ni pour Moldavie – Kazakhstan (16:30, où seul le n° 68 est cité).
   - Le pari 57 n'en aura pas non plus pour Écosse – Macédoine du Nord ce soir.

   C'est exactement le cas que la version 213 devait corriger. Le défaut disparaît de
   lui-même après le 14/11, mais il touche tous les joueurs qui avaient des combinés sur
   plusieurs jours. **Suggestion** : n'écarter, pour un ancien rappel, que le match qu'il
   citait (le premier match du pari), pas le pari entier.
2. **Une sélection de 1re mi-temps n'est réglée qu'environ 3 minutes après la reprise**, au
   lieu du coup de sifflet de la pause.
   - Burkina Faso – Mauritanie était à 0-0 à la pause (16:48), mais la notification de
     perte n'est arrivée qu'à 17:07.
   - Pendant la pause, la sélection est restée « en attente » sans état « pour
     l'instant » (`now: null`), alors que le pari 74 sur le même match affichait bien
     « perdant pour l'instant ».

   **Suggestion** : régler les marchés de 1re mi-temps au statut HT, avec la même attente
   VAR de quelques minutes que les autres.
3. **Minute d'un but dans le temps additionnel** : « 90' » au lieu de « 90+4' ». Le
   but a été marqué à la 90+4e. Afficher la minute avec le temps additionnel
   (`live_extra`), comme l'onglet du match.
4. Détail : « ⏰ » apparaît deux fois, dans le titre et au début du texte.

### Coupon en direct pendant ces matchs (relevé chaque minute, 16:48 → 18:35)

- **Rien n'est proposé pendant la pause**, ni pour Burkina Faso – Mauritanie (16:48-17:03)
  ni pour Zambie – Burundi (14:04-14:07). Les propositions n'apparaissent qu'à la reprise
  (46e) : la fenêtre « mi-temps » dure donc de fait 4 à 5 minutes.
- **Sur environ 100 propositions distinctes** (match × profil × sélection) :
  - 38 seulement ont une chance du moteur supérieure d'au moins 3 points à celle de la cote ;
  - 16 sont à égalité ;
  - **46 sont sous la cote** : 19 en Équilibré, 16 en Sûr et 11 en Audacieux.
  
  Exemples :
  - Burkina Faso – Mauritanie, Sûr à la 47e : « moins de 2,5 buts » à 1,083, moteur 79 %,
    cote 92 % ;
  - même match, Audacieux à la 50e : « moins de 1,5 but » à 1,333, moteur 56 %, cote 75 %.
- **Proposition changeante** : le Sûr de Burkina Faso – Mauritanie est passé de « plus de
  0,5 but » (79 % contre 71 %) à « moins de 2,5 buts » (79 % contre 92 %) en une minute.
- **Score en retard sur la cote : Gabon – Lesotho.** Le Gabon a marqué à la 53e, d'après
  les événements du match. Pourtant, de la 60e à la 63e, le coupon en direct affichait
  encore **0-0**.
  - À la 62e, les cotes ont bondi comme après un but : « moins de 2,5 buts » de 1,111 à 1,3,
    « Gabon ou Lesotho » à 1,083.
  - Le moteur, qui calculait encore sur 0-0, a proposé en Équilibré « moins de 1,5 but » à
    **2,25** avec **70 %**, contre 44 % selon la cote.
  - Cette « bonne affaire » est fausse : avec 1-0, la cote était juste. La protection de
    `e0aceb4` (cote gardée seulement au score du relevé) ne l'a pas arrêtée.

  **Suggestions** :
  - appliquer le garde-fou « écart de plus de 20 points = rien » ;
  - suspendre un match quand ses cotes bougent de plus de 15 points entre deux relevés sans
    que notre score ait changé ;
  - vérifier pourquoi le score du Gabon est resté à 0-0 au moins 7 minutes (but de la 53e
    entré en retard par la source, ou relevé en retard chez nous).

## 13/11, 18 h 53 – 21 h 38 GMT — Réglage « Validé ou perdu », matchs de 19:45

Réglage passé sur « Validé ou perdu » à 18:53 (`/me` → `results`), remis sur « Tout » à
21:38. Paris suivis :
- n° 57 : Écosse – Macédoine du Nord ;
- n° 69 : Pays-Bas – Grèce, « Pays-Bas mènent à la mi-temps » ;
- n° 75 : montante n° 7, Slovénie – Suisse, « plus de 0,5 but en 1re mi-temps ».

| Heure | Notification | Événement réel | Verdict |
|---|---|---|---|
| 19:15:00 | ⏰ Dans 30 min : Pays-Bas - Grèce (ton pari n° 69) | — | conforme (le rappel ne dépend pas du réglage) ; **Écosse – Macédoine du Nord absent** (pari 57, défaut 1) |
| *19:47 →* | *aucun « C'est parti »* pour les trois matchs | coups d'envoi vers 19:47 | **conforme au réglage** |
| *19:50 → 21:30* | *aucun « ⚽ »* pour 9 buts (Pays-Bas 5-0 à la pause ; Écosse 54e, 57e, 74e) | — | **conforme au réglage** |
| 20:53:03 | Pari gagné — Pays-Bas - Grèce : 1 970 F CFA crédités | pause vers 20:33 (5-0) | juste ; **~20 min** (défaut 2) |
| 21:00:05 | Pari perdu — ❌ Slovénie 0-0 Suisse : « plus de 0,5 but à la mi-temps » est perdu. Ton coupon de 5 000 F CFA est perdu. **+** Montante perdue — Palier 1 perdu : montante arrêtée. | pause 0-0 vers 20:35, reprise plus tardive | juste ; ~25 min (défaut 2) |
| 21:38:03 | ✅ « Écosse ou Macédoine du Nord » validé (Écosse 2-1 Macédoine du Nord). Ton coupon : 2 sur 3. | fin vers 21:36 | conforme, ~2 min |

**Le réglage « Validé ou perdu » est conforme** : ni « C'est parti » ni « ⚽ », mais les
sélections validées et les résultats arrivent. « Tout se joue sur Belgique – Italie »
(pari 57, dernier match) n'est pas envoyé, ce qui est cohérent avec le réglage.

**Défaut 2 confirmé deux fois de plus.** Les paris 69 et 75 portaient sur la 1re
mi-temps. Ils n'ont été réglés que 20 à 25 min après la pause, et sans état « pour
l'instant » pendant tout le match : le pari 69 menait 4-0 à la 36e, avec `now: null`.

**Défauts 5 et 6 (détails de texte)** :
5. Montante : deux notifications à la même seconde (« Pari perdu » et « Montante perdue »).
   Il vaudrait mieux une seule : « ❌ Palier 1 de ta montante perdu (Slovénie 0-0 Suisse) :
   montante arrêtée. »
6. « Ton coupon de 5 000 F » pour un pari simple : écrire « ton pari », comme le rappel
   (« ton pari n° 69 »).

**Points non vérifiés aujourd'hui** :
- **élision** : aucun libellé « victoire d'… » n'est passé dans mes notifications. Le code
  la gère (`live_alerts.py`, « d'Arménie », « d'Écosse ») ; à revoir à la prochaine
  occasion ;
- **« ↩️ But annulé »** : aucun but annulé dans mes matchs ;
- **carte « Chances en direct »** dans l'écran du match : pas regardée pendant les matchs
  (surveillance par l'API).

### Bilan du test de la version 213

| Point demandé | Résultat |
|---|---|
| 1. ⏰ pour chaque match, « ton coupon n° …, x sur y validée » | conforme pour les nouveaux paris (68, 69) ; **aucun rappel pour les paris rappelés avant le 13/11** (57, 58) |
| 2. 🟢 C'est parti dans la minute du coup d'envoi, une fois | conforme (4 matchs, ≤ 1 min) |
| 3. pari placé moins de 30 min avant : pas de rappel, « C'est parti » | conforme (pari 74) |
| 4. toucher ouvre Mes paris | conforme |
| 5. ✅, ⚽, « tout se joue sur », perte avec sélection et score, regroupement | conformes, ~1 min après le but ; 1re mi-temps réglée 20 min trop tard ; « 90' » au lieu de « 90+4' » |
| 6. élision | non vu |
| 7. réglage « Validé ou perdu » | conforme |
| 8. carte Chances en direct | non vu |

Paris du jour : 74 gagné (+615 F), 69 gagné (+1 970 F) ; 58, 68 et 75 perdus ; 57 : 2 sur 3,
Belgique – Italie le 15/11.
