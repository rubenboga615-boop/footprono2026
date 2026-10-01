# Produit : formules, administration (phase 5)

Code : `backend/src/footprono/accounts/plans.py`, `accounts/admin.py`,
`accounts/cli.py`, `api/v1/admin.py`.

## Décisions (30/09/2026)

| Sujet | Décision |
|---|---|
| Formules | **7 jours de Premium offerts à l'inscription**, puis version gratuite ; Premium à **2 000 F CFA par mois** |
| Activation de Premium | **Par l'administrateur** en attendant le paiement Mobile Money (phase 6) |
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

## Reste à faire en phase 5

- Application Flutter : faite (voir `APPLICATION.md`) ; reste à valider sur
  le téléphone.
- Notifications téléphone fermé (Firebase) : faites ; reste à installer la
  clé du compte de service sur le serveur et à valider sur le téléphone.
