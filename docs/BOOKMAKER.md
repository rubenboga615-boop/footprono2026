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
  dans la plage, classés par probabilité du moteur, avec l'écart à la
  probabilité déduite de la cote ; « déconseillé » si le moteur juge le pari
  moins probable que sa cote. Mi-temps la plus prolifique exclue.

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
