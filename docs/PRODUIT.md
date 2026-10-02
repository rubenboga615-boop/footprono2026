# Produit : formules, administration (phase 5)

Code : `backend/src/footprono/accounts/plans.py`, `accounts/admin.py`,
`accounts/cli.py`, `api/v1/admin.py`.

## Décisions (30/09/2026)

| Sujet | Décision |
|---|---|
| Formules | **7 jours de Premium offerts à l'inscription**, puis version gratuite ; Premium à **2 000 F CFA par mois** |
| Activation de Premium | **Mobile Money** (CinetPay, Profil → Passer Premium, voir `PRODUCTION.md`) ; l'administrateur peut aussi l'accorder |
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

## Phase 5 : terminée (01/10/2026)

- Application Flutter (voir `APPLICATION.md`) : installée et utilisée sur le
  téléphone.
- Notifications téléphone fermé (Firebase) : validées sur le téléphone
  (application fermée, notification dans la barre).

## Coupon intelligent (02/10/2026)

Onglet **Coupon** → carte « Coupon intelligent » (Premium).

- **Profil** : Sûr (75 à 92 % par sélection), Équilibré (60 à 75 %),
  Audacieux (45 à 60 %).
- **Période** : prochaine journée (par défaut : du premier match à venir
  jusqu'au lundi qui suit, même après une trêve internationale), aujourd'hui,
  demain, 3 jours, ce week-end, 7 jours. Sans match sur la période, l'écran
  donne la date des prochains matchs. Inutile
  d'attendre le jour du match : les prédictions couvrent 10 jours ; seules
  les cotes réelles (relevées à 07:30 et 16:30 UTC) limitent l'horizon.
  Fermeture 15 minutes avant le coup d'envoi.
- **1 à 4 sélections**, jamais deux du même match.
- Méthode : dans chaque match, la sélection la plus probable de la tranche du
  profil parmi les marchés retenus avec une vraie cote (≥ 1,10) ; les matchs
  les plus sûrs d'abord ; 3 autres choix proposés. Validée hors échantillon
  (`footprono-engine angles`, `docs/MOTEUR.md`).
- Chaque sélection : cote réelle, probabilité du moteur, deux faits (forme,
  moyennes de la saison, xG, confrontations). Probabilité du coupon et
  probabilité selon la cote affichées côte à côte. Aucune promesse de gain.
- « Mettre dans mon coupon » relit les cotes actuelles ; le pari reste validé
  par le joueur (`GET /smart-coupon?profile=&period=&size=`).

**Coupons du jour** (public, `GET /smart-coupons/history`) : chaque matin à
08:05 UTC (après cotes et prédictions), un coupon par profil (Sûr : 3
sélections, Équilibré et Audacieux : 2) est enregistré **avant** les matchs,
puis réglé avec les paris (mêmes règles). Rien n'est effacé ; bilan par
profil : probabilité annoncée moyenne contre taux de réussite observé.

**Montante** : les suggestions de palier gardent leur plage de cote mais
utilisent les mêmes règles de marchés et les mêmes probabilités. Matchs des
3 prochains jours, ou de la prochaine journée pendant une trêve.
