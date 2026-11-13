# Relecture du coupon en direct (travail de la nuit du 12 au 13/11/2026) — avant mise en ligne

Relu à 02:45 GMT, sur le code seulement : le serveur en ligne est `7338327` (étude), qui ne
contient pas encore `f9c472a` (serveur du coupon en direct) ni `9b572cc` (écrans).

## Ce qui a été fait

| Commit | Contenu |
|---|---|
| `0ed00e6`, `15b248d` | maquettes D8 à D15 (fenêtres pause → 50e, 60e-63e, 75e-78e ; Sûr gratuit) |
| `7338327`, `39853b6` | étude sur 13 347 matchs : chances justes aux trois moments, combinés compris ; 2 exclusions |
| `93b74ad` | console aux couleurs de l'application |
| `f9c472a` | serveur : cotes en direct, `/live/coupons`, pari placé en direct, publication par la console |
| `9b572cc` | application : écrans D8 à D14 |

Points bons :
- l'étude est solide : annoncé et gagné à moins de 2 points partout, y compris pour les
  combinés ;
- rien n'est publié d'office : il faut une action de la console ;
- les cotes suspendues sont écartées ;
- une cote qui a baissé est refusée ;
- les marchés retirés du direct ne sont jamais proposés.

## Défaut à corriger avant la mise en ligne : pari sur une cote d'avant un but

**Ce que j'ai lu.** `bookmaker/live_coupons.py` garde les cotes en direct jusqu'à 150 s
(`ODDS_MAX_AGE`). `live_offer` les réutilise pour placer un pari (`bookmaker/service.py`,
`place_bet`) sans vérifier que **le score n'a pas changé depuis le relevé**.

**Ce qui peut arriver.** À la 61e, le relevé donne « plus de 1,5 but » à 2,10, avec un score de
1-0. À la 62e, but : 2-0. L'application montre le but dans la minute (WebSocket), mais la
cote gardée vaut encore 2,10 pendant 2 min 30. Un joueur place alors un pari déjà gagné
(ou presque) à une cote d'avant le but.

L'argent est fictif, mais ce gain fausse :
- le **Classement mérité** ;
- la **Fiabilité** (les coupons en direct par moment, D15) ;
- la confiance des autres joueurs.

Les vrais bookmakers suspendent les cotes à chaque but pour cette raison.

**Suggestion :**
1. Garder avec chaque relevé de cotes le score (et les cartons rouges) du moment.
2. Dans `live_offer`, refuser le pari si le score ou le nombre de cartons rouges a changé
   depuis le relevé (« La cote a changé après un but : attends la prochaine cote »).
3. Refuser aussi pendant 1 à 2 minutes après un but, le temps que la VAR confirme, comme
   l'attente de 4 min du règlement.
4. Ajouter un test : relevé à 1-0, but à 2-0, pari refusé.

## À garder en tête

La comparaison des cotes `/odds/live` avec l'application 1xBet, à la même minute, n'a pas
encore été faite par le fondateur. Tant qu'elle ne l'est pas, publier en mode « cote
indicative » (D11), pas « cote 1xBet ».

## Corrigé le 13/11/2026

- Chaque relevé `/odds/live` n'est gardé que s'il porte le même score que le relevé des
  matchs du même passage, et s'il n'est pas suspendu par la source (`blocked`, `stopped`,
  `finished`).
- Chaque relevé gardé porte le score et les cartons rouges du moment (`state`).
- Propositions et pari : une cote relevée à un autre score ou avec un autre nombre de
  cartons rouges n'est plus proposée ; le pari est refusé (« la cote a changé après un but
  ou un carton rouge : attends la prochaine cote »), et aussi dans les 2 minutes qui suivent
  un but (ou un but annulé).
- Test : relevé à 1-0, but à 2-0 → refusé ; nouvelle cote mais but récent → refusé ;
  2 minutes après → accepté ; carton rouge → refusé.

## 14 h 07 GMT — Premier coupon en direct publié, vu en production

`/live/coupons` → `published: true`, `odds_source: "indicative"` (décision après la
comparaison avec 1xBet, `docs/COMPARAISON_COTES_DIRECT_2026-11-13.md`).

**Ce qui marche** : à 14:07, Mozambique – Éthiopie (2e mi-temps, 47e, 0-0) est proposé dans la
fenêtre « mi-temps » (fermeture à la 50e), avec une sélection et un combiné pour chaque profil.

**Défaut 1 — les trois propositions sont moins sûres que leur cote, selon le moteur lui-même.**

| Profil | Sélection | Cote | Moteur | Selon la cote |
|---|---|---|---|---|
| Sûr | moins de 2,5 buts | 1,111 | 84 % | 90 % |
| Équilibré | plus de 0,5 but | 1,363 | 73 % | 73 % |
| Audacieux | Mozambique ou Éthiopie | 1,50 | 59 % | **67 %** |

Le moteur propose donc des paris qu'il juge lui-même plus mauvais que le prix offert : pour
le Sûr, 84 % de chances à une cote qui en suppose 90 % ; pour l'Audacieux, 8 points sous la
cote. Le profil choisit la sélection d'après sa chance (fourchette du profil), sans regarder
la cote.

**Suggestion** :
- ne proposer en direct que des sélections où la chance du moteur est au moins égale à
  la chance donnée par la cote (au besoin 2 points de marge pour les cotes indicatives) ;
- sinon, afficher « aucune proposition intéressante pour l'instant », plutôt qu'un pari
  perdant à long terme ;
- à défaut, l'avertissement « le moteur est moins confiant que la cote » sur la
  proposition.

**Défaut 2 — Zambie – Burundi à la mi-temps (14:04-14:07, statut HT) n'est pas proposé.**
Le match était bien dans la fenêtre « mi-temps », et les chances en direct étaient publiées.
La cause probable : pas de cote en direct pour ce match à la pause (cote suspendue par la
source, ou match absent de `/odds/live`). Ce n'est pas faux en soi : sans cote, il n'y a pas
de proposition. Mais c'est à confirmer avec « Tester le direct » à la prochaine mi-temps. Si
la source suspend toutes ses cotes pendant la pause, la fenêtre « mi-temps » ne s'ouvrira
qu'à la reprise, et ne durera alors que 46e-50e.

## Quelles données font le coupon en direct ? (question du fondateur, 13/11 après-midi)

Lu dans `engine/live.py`, `predictions/live_chances.py` et `bookmaker/live_coupons.py` :

| Utilisé | Détail |
|---|---|
| Prévision d'avant-match | buts attendus de chaque équipe et part des buts en 1re période. Clubs : modèle de Poisson / Dixon-Coles sur 3 ans de résultats, 70 % xG Understat, demi-vie 180 jours. Sélections : note Elo et buts sur 2 ans de matchs officiels |
| État du match | statut (1H, HT, 2H), minute, temps additionnel (moyenne fixe de 2 et 5 min), score, score de la pause |
| Effet du score | l'équipe menée accélère un peu, celle qui mène ralentit (5 coefficients appris sur 2019-2022) |
| Cartons rouges | seulement pour **se taire** : pas de chance calculée après un rouge |
| Cotes en direct (`/odds/live`) | seulement pour savoir si la sélection est jouable et à quel prix ; **jamais pour choisir** |

**Non utilisé** :
- les statistiques du match en cours (tirs, tirs cadrés, xG du direct, possession, corners,
  attaques dangereuses) ;
- les compositions et absences ;
- les remplacements et cartons jaunes ;
- ce que disent les cotes du marché.

**Conséquence.** À la 47e, le moteur sait seulement « 0-0, 47e, et ce qu'on pensait avant le
match ». Si une équipe écrase l'autre (12 tirs à 1), le moteur ne le voit pas, alors que le
bookmaker le voit et ajuste sa cote. C'est pourquoi les propositions tombent souvent sous la
cote. Le filtre de valeur (chance du moteur ≥ 1/cote + 3 points) devient indispensable : il
évite de proposer quand le marché en sait plus que le moteur.

**Piste à étudier.** Ajouter les tirs cadrés et les xG du direct (API-Football les donne
pendant le match ; l'onglet Statistiques les affiche déjà). Mais l'archive n'a pas ces
statistiques minute par minute. Il faudrait commencer à les **enregistrer à chaque fenêtre
dès maintenant** (mi-temps, 60e, 75e) pour pouvoir le vérifier dans quelques semaines.
### Suite donnée (13/11/2026)

- **Défaut 1** : pas de filtre « chance du moteur ≥ 1/cote ». `docs/MOTEUR.md` (Grosse cote,
  03/10 ; montante, 06/11) : choisir sur un désaccord avec la cote retient surtout les cas
  où la cote a raison ; et 1/cote contient la marge du bookmaker, si bien que le filtre ne
  laisserait presque que ces désaccords. Si le marché en sait plus que le moteur (section
  précédente : tirs, xG du direct), une chance du moteur au-dessus de la cote signale
  plutôt ce que le moteur ne voit pas : le filtre garderait justement ces cas-là. Le
  remède à « le marché en sait plus » est d'ajouter ces données au moteur (piste
  ci-dessus), pas de choisir sur le désaccord. Retenu : l'avertissement, comme pour la
  montante.
  Chaque sélection et chaque combiné portent `below_odds` ; l'application affiche « moteur
  < cote » sur la tuile, les deux chances côte à côte sur chaque sélection, et « Le moteur
  est moins confiant que la cote : X % contre Y % selon la cote ». Le filtre reste possible
  si le fondateur le décide.
- **Défaut 2** : à la mi-temps, des cotes « stopped » (jeu arrêté) ne sont plus écartées
  (aucun but possible pendant la pause) ; « blocked » le reste. La raison de chaque match
  écarté est notée dans le rapport du suivi du direct (`live_odds_dropped` : absent de
  /odds/live, cotes bloquées, score différent, aucune cote ouverte). À confirmer à la
  mi-temps de Burkina Faso – Mauritanie.

### Décision du fondateur (13/11/2026, après-midi) — appliquée

L'objectif du coupon en direct devient de proposer des paris rentables, pas un pari sur
chaque match. Cela remplace, pour le seul coupon en direct, la règle « moteur indépendant
des cotes ». Le risque relevé plus haut (`docs/MOTEUR.md` : ce filtre garde surtout les cas
où la cote a raison) sera tranché par le bilan en argent.

- `pick` : chance du moteur ≥ 1/cote + 0,03, et écart ≤ 0,20 (garde-fou) ; combinés :
  sélections ajoutées tant que la chance du combiné reste ≥ 1/cote totale + 0,03.
- Sélections nationales : match écarté si une équipe a joué moins de 8 matchs en 2 ans
  (seuil choisi par nous, à revoir).
- Fenêtre sans proposition : « Aucun coupon intéressant pendant cette fenêtre » (`open`
  compte les matchs dans une fenêtre).
- Fiabilité D15 : bilan d'une mise de 1 000 F sur chaque proposition réglée, par profil et
  moment, et au total.
- « En test » tant qu'il y a moins de 200 propositions réglées, ou si le bilan est négatif.
- Étude future : cotes du direct gardées à chaque fenêtre (`live_window_odds`) ; les
  statistiques du match (tirs, tirs cadrés, xG, corners, possession, attaques
  dangereuses) le sont déjà à chaque minute dans `live_snapshots` depuis le 10/11.
