# Marchés couverts (validés le 29/09/2026, choix « C »)

## 1. Marchés tirés de la distribution des scores (match complet)

Un seul modèle donne la probabilité de chaque score ; tous ces marchés en sont
déduits et sont donc cohérents entre eux par construction.

| Marché | Détail |
|---|---|
| 1X2 | domicile, nul, extérieur |
| Double chance | 1X, X2, 12 |
| Remboursé si nul | équipe 1 ou 2 |
| Plus/moins de buts (total) | lignes 0,5 à 5,5 |
| Plus/moins de buts par équipe | lignes 0,5 à 3,5 |
| Les deux équipes marquent | oui / non |
| Score exact | jusqu'à 5-5, plus « autre » |
| Handicap européen et asiatique | lignes −3 à +3, quarts de but compris |
| Clean sheet, gagner sans encaisser | par équipe |
| Écart de buts | |
| Combinés dans un même match | 1X2 + plus/moins, 1X2 + les deux marquent… (probabilité jointe exacte) |

## 2. Marchés de la mi-temps

Modèle dédié à la première période (scores à la mi-temps disponibles depuis 2016).

| Marché | Détail |
|---|---|
| Résultat à la mi-temps | 1, N, 2 |
| Mi-temps / fin de match | 9 combinaisons |
| Plus/moins de buts à la mi-temps | |

## 3. Marchés statistiques (modèles séparés)

| Marché | Match complet | Par mi-temps |
|---|---|---|
| Corners : total, par équipe, handicap | football-data et API-Football depuis 2016 | API-Football depuis 2024-25 (« historique court ») |
| Cartons : total, points de cartons (arbitre pris en compte) | football-data et API-Football depuis 2016 | API-Football depuis 2024-25 (« historique court ») |
| Tirs et tirs cadrés : total, par équipe | football-data et API-Football depuis 2016 | API-Football depuis 2024-25 (« historique court ») |

« Historique court » : affiché tant que moins de 3 saisons complètes ont été
testées.

## Données disponibles (vérifié le 30/09/2026, matchs joués 2016-17 → 2026-27)

| Donnée | EPL | Liga | Serie A | Bundesliga | Ligue 1 |
|---|---|---|---|---|---|
| Score final et mi-temps | 100 % | 100 % | 100 % | 100 % | 100 % |
| Corners, cartons, tirs, tirs cadrés | 100 % | 100 % | 100 % | 100 % | 100 % |
| Arbitre (football-data) | 100 % | 0 % | 0 % | 0 % | 0 % |

À faire pour la phase 2 :
- **Arbitre** des 4 autres championnats : disponible dans la liste des matchs
  d'API-Football (`fixture.referee`), environ 55 requêtes pour tout
  l'historique ; en attendant, le modèle des cartons tourne sans l'arbitre.
- **Cotes du handicap asiatique** : présentes dans les fichiers football-data
  archivés, à charger en base.
- Statistiques par mi-temps : modélisées comme la part de la 1re période dans
  le total prévu du match, estimée sur 2024-25 et après.
- Combinés dans un même match : probabilité jointe exacte pour les marchés de
  buts (même distribution des scores) ; un combiné buts + corners ou cartons
  n'est pas couvert en V1 (modèles distincts, dépendance non modélisée).

## Audit de tous les marchés (vérifié le 02/10/2026, `footprono-engine audit`)

Saisons de test 2022-23 → 2025-26 (7 081 matchs, jamais vus), moteur avec
xG remis au niveau des buts. Gain = part de la log loss d'une référence
causale (fréquence de l'issue dans le championnat, 3 saisons précédentes)
gagnée par le moteur. « À corriger » = au moins une tranche de probabilité
écartée de plus de 3,5 erreurs types (calculées par match).

**Validés** (meilleurs que la référence, bien calibrés) :

| Famille | Gain | Famille | Gain |
|---|---|---|---|
| Tirs : le plus de | +12,8 % | Combiné résultat + buts | +5,2 % |
| Tirs : par équipe | +11,1 % | Corners : par équipe | +4,9 % |
| Tirs cadrés : par équipe | +8,1 % | Combiné résultat + les deux marquent | +4,5 % |
| Résultat (1X2) | +7,8 % | Mi-temps / fin de match | +4,1 % |
| Double chance | +7,8 % | Tirs cadrés : total | +3,9 % |
| Gagner sans encaisser | +7,2 % | Mi-temps : résultat | +3,7 % |
| Corners : handicap | +6,6 % | Score exact | +3,3 % |
| Clean sheet | +5,5 % | Cartons : par équipe | +2,8 % |
| Corners : le plus de | +5,5 % | Buts du match (plus/moins) | +1,9 % |
| Combiné buts + les deux marquent | +1,1 % | Mi-temps : buts | +1,0 % |
| Les deux marquent | +0,6 % | | |

**Utiles, calibration à corriger** (écarts faibles sauf mention) :

| Famille | Gain | Écart repéré |
|---|---|---|
| Handicap asiatique (lignes x,5) | +10,8 % | trop prudent : 85,4 % annoncé → 86,8 % observé |
| Tirs cadrés : le plus de | +9,5 % | **trop prudent** : 74 % → 82 % (tranche 70-80 %) |
| Handicap européen | +8,8 % | trop prudent : +1,4 point vers 80-90 % |
| Buts d'une équipe | +6,8 % | extrêmes : ±0,7 point |
| Tirs : total | +4,9 % | trop prudent : ±1,9 à 2,4 points |
| Écart de buts | +4,3 % | +1,9 point vers 20-30 % |
| Cartons : total | +2,9 % | trop sûr aux extrêmes : ±1,6 point |
| Cartons : le plus de | +1,3 % | +2,5 points vers 10-20 % |
| Corners : total | +1,0 % | trop prudent : ±1,6 à 1,8 point |

**Sans apport** (pas mieux que la fréquence du championnat) : mi-temps
« les deux marquent », mi-temps la plus prolifique, total pair / impair.
**Retirés le 02/10/2026** (`engine/markets.py`, `WITHDRAWN_MARKETS`) : ni
prédits, ni affichés, ni proposés au bookmaker virtuel. Le règlement des
paris déjà placés reste assuré.

Non évalués ici : remboursé si nul et handicap asiatique à ligne entière ou
quart de but (remboursements ; le handicap asiatique est comparé aux cotes
dans `MOTEUR.md`), points de cartons, corners / cartons / tirs par mi-temps
(historique API-Football depuis 2024-25 seulement).

## Non couverts en V1

- Buteurs, statistiques de joueurs, minute du premier but, penalty : pas de
  données par joueur ni par minute sur l'historique.
- Hors-jeu, arrêts, possession : données disponibles mais peu proposés par les
  bookmakers ; non prioritaires.

## Vérification

- Tous les marchés : calibration sur des saisons jamais vues par le modèle
  (60 % annoncé ≈ 6 fois sur 10).
- Comparaison avec les cotes des bookmakers sur l'historique : **1X2, plus/moins
  2,5 buts et handicap asiatique** uniquement (cotes football-data ; celles du
  handicap asiatique sont à ajouter en base). Pour les autres marchés, la
  comparaison deviendra possible avec les cotes d'avant-match d'API-Football
  (phase 3), à partir de leur collecte.

## Usages dans l'application

- Coupon : une ou plusieurs sélections.
- Montante : 1 à 3 sélections par palier, cote totale dans la plage du palier.
- Choix automatiques (Coupon intelligent, suggestions de montante) : mêmes
  règles (`bookmaker/rules.py`). Exclus : score exact, mi-temps / fin de
  match, combinés dans un même match (surestimés par l'étude des angles),
  marge de victoire, cartons et points de cartons (trop sûrs au-dessus de
  50 % depuis 2022). Ces marchés restent jouables à la main.
