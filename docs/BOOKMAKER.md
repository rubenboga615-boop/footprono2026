# Bookmaker virtuel, montante, notifications (phase 4)

Argent **fictif**. Code : `backend/src/footprono/accounts/`, `bookmaker/`,
`notifications/`.

## Décisions (30/09/2026)

| Sujet | Décision |
|---|---|
| Cotes des paris | **Cotes réelles** : dernier relevé 1xBet, Bet365 en secours. Sans cote réelle récente (36 h), la sélection n'est pas jouable. Pinnacle : référence interne, jamais jouable. |
| Solde de départ | **100 000 F CFA** ; rechargement gratuit jusqu'au solde de départ si le solde passe sous 1 000 F CFA, une fois par semaine. |
| Connexion | **Téléphone (format international) + mot de passe** ; vérification par SMS ajoutée en phase 5. |

## Comptes et portefeuille

- Inscription : pays de lancement (Bénin, Burkina Faso, Côte d'Ivoire,
  Guinée-Bissau, Mali, Niger, Sénégal, Togo → F CFA), 18 ans ou plus.
- Mots de passe : scrypt (bibliothèque standard) ; jeton JWT de 30 jours
  (`FP_SECRET_KEY`, générée par `setup.sh`).
- Portefeuille : montants en entiers dans la devise, **chaque mouvement au
  journal** (`wallet_entries`, solde après opération), solde jamais négatif
  (verrou + contrainte).

## Paris

- Simple ou combiné (jusqu'à 12 sélections) ; **un combiné ne réunit que des
  matchs différents** : deux sélections du même match sont liées, multiplier
  leurs cotes serait faux (utiliser un marché combiné du bookmaker).
- Seulement avant le coup d'envoi, jamais sur un match reporté ; mise minimale
  100.
- Si la cote a baissé depuis que l'utilisateur l'a vue : refus (« cote
  modifiée »).
- Une cote inchangée reste jouable d'un relevé à l'autre (`last_seen_at`) ;
  une cote absente du dernier relevé a été retirée et n'est plus jouable.
- Chaque sélection garde la cote jouée, le bookmaker, le relevé d'origine et
  la probabilité du moteur au moment du pari.

## Règlement

- Dès la fin du match (suivi en direct toutes les 2 minutes), puis après
  l'ingestion quotidienne.
- **Même calcul que les probabilités** : le match réel devient une
  distribution à 100 % sur le score observé, passée dans `derive_markets` /
  `count_markets`. Handicaps au quart, remboursements, mi-temps, combinés,
  corners, cartons, points de cartons : aucune règle à part.
- Gain = mise × produit des facteurs (gagné : cote ; demi-gagné :
  (1 + cote) / 2 ; remboursé : 1 ; demi-perdu : 0,5 ; perdu : 0), arrondi au
  franc inférieur. Un combiné est perdu dès la première sélection perdue.
- **Pendant le match** (plan du 10/11/2026, étape 2 ; constat du fondateur du 09/11 : un
  pari « moins de 3 buts en 1re mi-temps » attendait la fin du match) : une sélection est
  réglée dès que **plus aucun but, corner, carton ou tir ne peut changer son résultat**.
  Même calcul que le règlement final, essayé sur toutes les suites possibles du match
  (jusqu'à 8 buts de plus par équipe, 15 corners, cartons ou tirs) : si toutes donnent le
  même résultat, il est acquis. Exemples : « plus de 2,5 buts » gagné dès le 3e but,
  « moins de 2,5 » perdu ; « les deux marquent » gagné dès que les deux ont marqué ;
  « gagne sans encaisser » perdu dès le premier but encaissé ; marchés de la 1re mi-temps
  dès la pause (score de la mi-temps enregistré à ce moment) ; « plus de 9,5 corners » au
  10e corner. Le résultat du match (1X2), les handicaps, l'écart de buts attendent la fin.
  - Seuls comptent les relevés pris **il y a au moins 4 minutes** : un but annulé par la
    VAR dans ce délai ne règle rien ; un score plus bas depuis (but annulé) fait foi.
  - Temps réglementaire seulement : en prolongation, on attend la fin du match (les paris
    se jouent sur 90 minutes).
  - Le contrôle par le score final reste : un résultat qui change (VAR tardive, score
    corrigé) règle le pari à nouveau, écart crédité ou débité.
  - Valable pour les paris, les combinés (perdus dès la première sélection perdue), les
    montantes et les Coupons du jour.
- Match reporté ou annulé : remboursé 48 h après le coup d'envoi prévu.
- Score provisoire (API-Football) corrigé par football-data : paris des
  7 derniers jours **réglés à nouveau**, écart crédité ou débité avec une note
  et une notification.

## Montante

- 4 à 8 paliers, mise de départ libre (5 000 F CFA par défaut), une plage de
  cotes par palier, option « sécuriser X % de chaque gain ».
- Chaque palier est un pari ordinaire (1 à 3 sélections) dont la mise est
  imposée : gain précédent moins la part sécurisée. Hors plage : refusé sauf
  confirmation explicite (palier marqué).
- Remboursé : palier rejoué avec la même mise ; perdu : montante arrêtée ;
  « encaisser » entre deux paliers (les gains sont déjà sur le solde).
- Plan : mises et gains réels puis en fourchette, gain final, chance d'aller
  au bout selon les cotes et selon le moteur, somme encaissable. L'exemple de
  référence (6 paliers, 5 000 F CFA, 1,60 → 1,90) redonne **150 582 F CFA**
  et **3,3 %** (test automatique).
- Suggestions : les 3 paris (simple ou combiné de 2 à 3 matchs différents)
  dans la plage, la cote la plus basse d'abord (le plus probable selon le
  bookmaker), puis le moins de sélections, puis le match le plus proche ;
  probabilité du moteur et probabilité déduite de la cote côte à côte. Plus
  jamais classés par probabilité du moteur (06/11/2026, docs/MOTEUR.md).
  Mi-temps la plus prolifique exclue.

## Notifications

- Enregistrées en base : pari réglé, score corrigé, palier validé ou
  remboursé, montante réussie ou perdue.
- **En direct** : WebSocket `/api/v1/ws?token=…`, relayé par Redis ; diffusées
  seulement après validation du règlement.
- **Téléphone fermé (Firebase Cloud Messaging)** : envoyées aux téléphones
  enregistrés après le direct ; un jeton refusé par Firebase (application
  désinstallée) est oublié. Voir `APPLICATION.md`.

## API

| Route | Rôle |
|---|---|
| `POST /auth/register`, `POST /auth/login`, `GET /me` | compte |
| `GET /me/wallet/entries`, `POST /me/wallet/refill` | portefeuille |
| `GET /matches/{id}/offer` | sélections jouables : cote réelle et probabilité du moteur |
| `GET /offers/main?match_ids=…` | cotes des colonnes du tableau des matchs (1, N, 2, +2,5, les deux marquent), 80 matchs au plus |
| `POST /bets`, `GET /bets`, `GET /bets/{id}` | paris |
| `POST /montantes`, `GET /montantes`, `GET /montantes/{id}` | montantes et plan |
| `GET /montantes/{id}/suggestions`, `POST /montantes/{id}/bet`, `POST /montantes/{id}/cash-out` | paliers |
| `GET /me/notifications`, `POST /me/notifications/{id}/read`, `POST /me/notifications/read-all`, `WS /ws` | notifications |
| `POST /me/devices`, `POST /me/devices/remove` | téléphone des notifications push (jeton Firebase) |


## Sélections jouables préparées à l'avance (06/11/2026)

Essai réel du 06/11/2026 (docs/AUDIT_UTILISATEUR_2026-11-06.md) : Coupon intelligent et
suggestions de montante en 15 à 19 secondes sur « Prochaine journée », à la limite du
délai de 20 secondes de l'application. Le temps venait de la lecture des cotes de tous
les matchs de la période, à chaque demande.

`bookmaker/playable.py` : juste après chaque collecte de cotes et chaque calcul de
pronostics (worker et console), les cotes jouables et les probabilités du moteur de tous
les matchs des 15 prochains jours sont préparées dans Redis. Les demandes les lisent
toutes prêtes (volume simulé : 2,7 s → 0,16 s ; suggestions 0,07 s). Jamais de données
fausses : empreinte des données vérifiée à chaque lecture (sinon calcul direct, comme
avant), cotes trop anciennes écartées, Redis en panne sans erreur, cote revérifiée en
direct au moment de miser.

Trois étages, du plus rapide au plus sûr : données préparées dans Redis (à jour par
empreinte) ; sinon cache de 10 minutes par processus (`service.cached_offers_and_probabilities`) ;
sinon lecture en base, accélérée par l'index (match, bookmaker, pari, valeur) de la
migration 0029 (12 bookmakers relevés, 2 jouables).

Application : délai de 60 secondes pour ces calculs (20 ailleurs), attente expliquée
(`SlowWait`), ajout au coupon des matchs en parallèle avec « Ajout 3 / 7… ».

## Montantes : des matchs différents pour chaque montante (06/11/2026)

Constat du fondateur : deux montantes au même palier recevaient exactement les mêmes
suggestions ; les suivre toutes revenait à miser deux fois sur le même événement. Les
suggestions d'une montante écartent maintenant les matchs des paris en cours des autres
montantes actives du joueur, et ceux suggérés aux montantes plus anciennes
(`montante.step_suggestions`). S'il ne reste aucun autre match dans la plage, l'écran le
dit plutôt que de reproposer les mêmes paris.

Combinés : déjà permis (2 ou 3 matchs), mais à cote égale un combiné est un peu moins sûr
qu'un pari simple (marge du bookmaker payée sur chaque match) ; le classement neutre
propose d'abord le moins de sélections.

## Décisions du 07/11/2026

- **Coupons du jour : au plus un pari de buts par coupon** (totaux, buts d'une équipe,
  mi-temps, les deux marquent, pair/impair : `smart_coupon.GOAL_MARKETS`). Ils remplissaient
  14 sélections sur 21, alors qu'en conditions réelles le moteur y fait à peine mieux qu'une
  prévision naïve (379 matchs). Cause : une vingtaine de lignes de buts par match, il y en a
  presque toujours une tout près de la cible du profil. Au-delà du quota, le match garde son
  meilleur angle hors buts (même règle de choix). Dans l'application, un pari de buts est
  marqué « marché en observation ». Rien n'est écrit « fiable » : en réel, le résultat 1-N-2
  n'est pas encore juste non plus (annoncé 44 %, arrivé 58 %, page Fiabilité).
- **Montante : suggestion où le moteur est moins confiant que la cote**, gardée et
  expliquée (« le moteur est moins confiant que le bookmaker sur ce pari »), montrée après
  les autres. Le choix des suggestions ne regarde jamais l'avis du moteur face à la cote :
  préférer les paris où il y croit plus que le bookmaker, c'est choisir là où il se trompe
  le plus (03/10/2026).
- **Grosse cote** : la sélection qui fait passer la cible est la plus petite cote suffisante
  parmi les 5 suivantes les plus probables (25 visé donnait 37,31).

## Coupon intelligent : un coupon par joueur (07/11/2026)

Proposition du 07/11/2026 (`docs/AUDIT_PROPOSITION_DIVERSITE_2026-11-07.md`) : avec le même
coupon pour tous (comparaison du jour : 8 coupons sur 8 identiques entre deux joueurs), un
mauvais jour fait perdre tout le monde en même temps. Les profils étant plafonnés, beaucoup de
sélections sont presque à égalité (Équilibré : juste sous 75 %).

Règle (`smart_coupon.vary`, `shuffle_ties`) :
- parmi les sélections à **1 point au plus** de la dernière du meilleur coupon, chaque joueur a
  son propre tirage (joueur, jour, profil), **le même toute la journée** ;
- jamais en dessous de **97 %** de la chance du meilleur coupon (sinon le meilleur coupon) ;
- Grosse cote : l'ordre des sélections presque à égalité est mélangé de la même façon, puis la
  règle habituelle (cote la plus proche de la cible) ; même plancher de 97 % ;
- « Un autre coupon » : tirage suivant (`variant`) ; l'application dit « Composé pour toi parmi
  les meilleurs de la période » et montre la chance du meilleur coupon quand elle diffère ;
- Coupons du jour : inchangés, les mêmes pour tous (codes 1xBet saisis à la main).

Simulation (1 000 joueurs, un samedi type avec 12 sélections presque à égalité) : 218 coupons
différents, le plus donné à 11 joueurs, la sélection la plus présente dans 27 % des coupons ;
chance moyenne 41,3 % contre 41,9 % pour le meilleur coupon (−0,6 point), la plus basse 40,7 %.
Pas un moyen de gagner plus : le but est que les joueurs ne perdent plus tous le même jour.
À suivre dans l'Observatoire avec de vrais joueurs (part des joueurs perdants par jour).
