# Étude « moteur v3 » : taux de réussite et rentabilité (15/11/2026)

Étude seule : **aucun code de l'application n'est modifié**. Scripts et sorties brutes
dans [`docs/etudes/2026-11-15/`](etudes/2026-11-15/).

## Données et méthode

- Historique football-data 2016-17 → 2026-27 téléchargé le 15/11/2026 : 11 championnats
  (5 grands, Belgique, Pays-Bas, Portugal, Écosse, Grèce, Turquie), 35 850 matchs, cotes
  1X2 et plus/moins 2,5 de B365, Pinnacle, moyenne et meilleure cote du marché.
- **Sans xG** : Understat affiche « We will come back soon » ; les xG d'API-Football et
  les cotes relevées par le serveur ne sont pas dans cette étude (clé et export absents).
- Moteur actuel, prévisions strictement hors échantillon (`run_backtest`, réestimation
  hebdomadaire) : 28 914 matchs. Validation 2018-19 → 2021-22, test 2022-23 → 2026-27.
- Rendement = gain moyen par unité misée, ± 2 erreurs types.

## Constats

1. **Le moteur n'ajoute rien à la cote d'avant-match sur le 1X2.** Combinaison
   log-linéaire moteur × cote, poids appris sur la validation : poids du moteur **0,000**.
   Log loss test (15 001 matchs) : moteur 0,9735, cote d'avant-match 0,9561, clôture 0,9525.
   Plus/moins 2,5 : moteur 0,6804, cote 0,6705.
2. **Les « values » du moteur perdent** : p moteur × meilleure cote > 1 → −7,4 % ± 2,5
   (20 206 paris) ; > 1,10 → −12,9 % ± 3,8. Confirme le principe n° 4.
3. **Biais favori / outsider, net et stable** (1X2, test, chez B365 puis à la meilleure cote) :

   | Cote B365 | Paris | Réussite | Rendement B365 | Rendement meilleure cote |
   |---|---|---|---|---|
   | < 1,30 | 1 407 | 83,7 % | +0,2 % ± 2,4 | +2,4 % ± 2,4 |
   | 1,30-1,50 | 1 870 | 71,4 % | −1,1 % ± 2,9 | +1,6 % ± 3,0 |
   | 1,50-1,70 | 2 057 | 62,8 % | −0,4 % ± 3,4 | +3,0 % ± 3,5 |
   | 1,70-2,00 | 3 218 | 52,3 % | −4,8 % ± 3,2 | −1,0 % ± 3,3 |
   | 2,00-2,50 | 5 033 | 43,4 % | −4,1 % ± 3,1 | −0,2 % ± 3,2 |
   | 2,50-3,50 | 11 517 | 30,7 % | −7,0 % ± 2,6 | −2,8 % ± 2,7 |
   | 3,50-5 | 12 256 | 23,6 % | −8,4 % ± 3,0 | −3,9 % ± 3,2 |
   | 5-10 | 6 253 | 13,4 % | −17,7 % ± 5,4 | −11,3 % ± 5,9 |
   | ≥ 10 | 1 392 | 4,9 % | −38,9 % ± 14,9 | −28,9 % ± 17,7 |

   Cotes < 1,70 regroupées, meilleure cote : validation +1,7 % ± 2,3 (3 697 paris),
   test +2,3 % ± 1,8 (5 334 paris), positif 7 saisons sur 8. Chez B365 seul : −2,7 % puis
   −0,5 %. La « meilleure cote » est une borne haute (tous bookmakers confondus).
4. **Retirer la marge par la méthode puissance** (p = (1/cote)^k, somme = 1) au lieu de
   la normalisation proportionnelle : log loss test 0,95470 contre 0,95605
   (−0,00135 ± 0,00058), et calibration nettement meilleure aux extrêmes (tranche
   0,7-0,8 : annoncé 0,746 → 0,774 pour 0,791 observé ; tranche 0-0,1 : 0,075 → 0,061
   pour 0,045 observé).
5. **Plus/moins 2,5 moins favorable que le 1X2 aux mêmes cotes** : 1,50-1,70 → −3,6 % ± 2,1
   chez B365 (1X2 : −0,4 %).
6. **Pinnacle comme référence + meilleure cote** (cote < 3) : test +4,6 % ± 2,6, mais
   validation +0,2 % ± 2,4 : non confirmé, à ne pas retenir en l'état.

## Lecture

- Sur le 1X2 et le plus/moins 2,5, la meilleure probabilité disponible est celle de la
  cote, marge retirée par la méthode puissance — pas celle du moteur.
- Le taux de réussite et le rendement dépendent surtout de **la tranche de cote** et du
  **bookmaker**, pas de l'avis du moteur : favoris 1X2 sous 1,70 ≈ 70 % de réussite et
  rendement proche de zéro ; au-delà de 3,50 les pertes sont structurelles.
- Coupons combinés : les marges se multiplient ; un coupon « Grosse cote » hérite des
  pertes des cotes longues.

## Pistes proposées (non appliquées)

1. Afficher la probabilité « selon la cote » avec la méthode puissance.
2. Montante et coupon « Sûr » : sélections 1X2 de favoris sous 1,70 en priorité sur le
   plus/moins ; mesurer avec les cotes réelles du serveur.
3. Montrer le bookmaker qui paie le mieux (écart moyen de 3 à 4 points de rendement).
4. Refaire l'étude avec l'export du serveur (xG, statistiques API-Football, cotes relevées)
   pour les marchés où le moteur peut apporter quelque chose : corners, cartons, mi-temps.
