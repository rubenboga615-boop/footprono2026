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
| Écart de buts, total pair / impair | |
| Combinés dans un même match | 1X2 + plus/moins, 1X2 + les deux marquent… (probabilité jointe exacte) |

## 2. Marchés de la mi-temps

Modèle dédié à la première période (scores à la mi-temps disponibles depuis 2016).

| Marché | Détail |
|---|---|
| Résultat à la mi-temps | 1, N, 2 |
| Mi-temps / fin de match | 9 combinaisons |
| Plus/moins de buts à la mi-temps | |
| Les deux équipes marquent en 1re période | |
| Mi-temps la plus prolifique | |

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
