# Contrôle du moteur principal et retrait du moteur 2 — 24/11/2026

## 1. Moteur 2 retiré

Décision du fondateur (24/11/2026) : le moteur 2 (moteur 1 calé sur la cote de référence,
docs/MOTEUR_V3.md) n'apportait rien de mieux. Il est retiré de partout :

- serveur : calcul (`predictions/calibration.py`, `bookmaker/price.py`,
  `bookmaker/engine_compare.py`), paramètres `engine=2` des routes, coupons du jour du moteur 2,
  tâche `engine_chances`, route `/reliability/engines`, réglage `compare_engines` ;
- application : réglage « Comparer les deux moteurs », pastilles MOTEUR 1 / MOTEUR 2,
  coupons, suggestions et coupons du jour du moteur 2, écran de comparaison.

Rien n'est effacé dans la base : les anciennes tables (`engine_proposals`,
`engine_match_chances`), les coupons du jour du moteur 2 (`engine` = 2) et la colonne
`compare_engines` restent, simplement plus lus.

## 2. Contrôle du moteur 1

### En vrai (compte de test Premium, vérification du 24/11/2026)

- Sélections jouées sur 30 jours : chance annoncée **73 %**, réalisée **70 %** sur 53
  sélections. L'écart reste dans le hasard pour 53 sélections.
- Coupon intelligent : le moteur est **sous la cote** pour le profil Équilibré depuis 6 jours
  (41 % contre 57 % le 24/11). L'écran le dit déjà (encadré ambre, « Ajouter quand même »).
- **Défaut grave trouvé** : des « occasions » de 17 à 29 points en Ligue des champions (Bruges
  à 50 % contre Liverpool, cote 4,72). Le moteur des coupes compare mal des clubs de
  championnats différents.

### Sur l'historique (hors échantillon, données locales : Championship anglaise)

| Mesure | Moteur | Naïf |
|---|---|---|
| 1X2, log loss (2 208 matchs) | 1,0436 | 1,0763 |
| 1X2, RPS | 0,2174 | 0,2287 |
| Plus de 2,5 buts | 0,6882 | 0,6927 |
| Les deux marquent | 0,6892 | 0,6929 |

Calibration 1X2 (annoncé → observé) : juste de 20 % à 70 %, mais **les issues annoncées entre
10 et 20 % arrivent moins souvent** (16,9 % annoncés, 12,1 % observés, 305 cas) : le moteur
surestime un peu les grosses surprises.

Audit de tous les marchés : toutes les familles proposées sont validées, sauf « buts du match
(plus/moins) », « mi-temps : les deux marquent », « mi-temps la plus prolifique » et « pair /
impair » (sans apport par rapport au naïf, inchangé depuis l'audit précédent).

Les grands championnats ne sont pas dans les données locales : le même contrôle se lance sur
le serveur depuis la console (Études du moteur → « Backtest » et « Audit de tous les
marchés »).

## 3. Corrections faites

- Occasions du tableau de bord et alertes d'écart : **jamais au-delà de 15 points**, et
  **jamais en coupes d'Europe** (en plus des sélections nationales).
- Pastille « moteur contre cote » en ambre (« non mesuré ») pour les coupes d'Europe.
- Tableau de bord : « misé cette semaine » compte depuis lundi, comme le plan de jeu.
- Outil de mesure (`footprono-engine backtest`) : ne plante plus quand un championnat n'a aucun
  match prédit.
- Test de bout en bout de la construction automatique : relancé sur Ubuntu 24.04.
