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

## Suite : export du serveur du 15/11/2026 (xG, cotes réelles, prévisions publiées)

Export sans données personnelles restauré dans une base locale (jamais copié dans ce
dépôt) : 70 539 matchs, 36 compétitions, 2,49 millions de cotes relevées (Bet365, 1xBet,
Pinnacle, du 30/09 au 14/11/2026), 61 236 prévisions enregistrées. Scripts `s3.py`,
`s4.py` ; seuls des résultats agrégés figurent ici.

7. **Référence reproduite** : 5 grands championnats, 7 081 matchs de test, 1X2 log loss
   **0,9813** (cotes de clôture 0,9665), plus/moins 2,5 0,6743 (0,6677).
8. **Même avec les xG, le moteur ne pèse rien face à la cote** (cote moyenne
   d'avant-match, marge retirée par la méthode puissance) :

   | | Poids du moteur (appris 2018-21) | Moteur | Cote | Combiné | Combiné − cote |
   |---|---|---|---|---|---|
   | 1X2, 5 grands (xG), 7 581 matchs | 0,046 | 0,9802 | 0,9666 | 0,9668 | +0,0002 ± 0,0001 |
   | 1X2, autres, 7 439 matchs | 0,000 | 0,9581 | 0,9426 | 0,9426 | 0 |
   | +/−2,5, 5 grands | 0,050 | 0,6743 | 0,6691 | 0,6692 | +0,0000 ± 0,0001 |
   | +/−2,5, autres | 0,061 | 0,6776 | 0,6711 | 0,6712 | +0,0001 ± 0,0001 |

9. **Marges réelles par marché** (avant-match, moyenne) :

   | Marché | Pinnacle | Bet365 | 1xBet |
   |---|---|---|---|
   | Vainqueur du match | 4,5 % | 7,7 % | 4,7 % |
   | Double chance | — | 5,8 % | 5,5 % |
   | Les deux équipes marquent | — | 7,3 % | 7,9 % |
   | Plus/moins de buts | 4,8 % | 5,6 % | 7,3 % |
   | Vainqueur à la mi-temps | 5,2 % | 8,3 % | 9,6 % |
   | Corners plus/moins | 6,5 % | 6,9 % | 10,7 % |
   | Cartons plus/moins | 6,1 % | 7,9 % | 7,9 % |

   Sur 7 223 sélections cotées par les trois : Pinnacle paie le mieux dans 55 % des cas,
   1xBet 23 %, Bet365 22 % ; la meilleure cote dépasse Bet365 de 3,6 % en moyenne.
10. **Moteur publié contre Pinnacle** (477 matchs avec prévision avant le coup d'envoi ;
    log loss par sélection, écart = moteur − Pinnacle) : vainqueur +0,0081 ± 0,0076,
    plus/moins de buts +0,0105 ± 0,0052, mi-temps +0,0055 ± 0,0058 → le moteur est
    moins bon. **Corners −0,0026 ± 0,0113 et cartons +0,0030 ± 0,0177 → à égalité.**
    Corners et cartons : quand le moteur est au-dessus de la cote d'au moins 3 points,
    +5,1 % ± 13,6 et +2,5 % ± 15,4 (≈ 200 paris chacun) ; au-dessous, −19,7 % ± 13,0 et
    −17,8 % ± 13,7. Indice d'une information propre au moteur, échantillon trop petit
    pour conclure.
11. **Le prix payé par rapport à Pinnacle ordonne le rendement** (tous marchés ci-dessus,
    pari à la meilleure cote Bet365/1xBet, p = probabilité Pinnacle marge retirée) :

    | p Pinnacle × cote | Paris | Réussite | Rendement |
    |---|---|---|---|
    | < 0,90 | 4 109 | 33,3 % | −11,1 % ± 4,4 |
    | 0,90-0,95 | 5 677 | 46,8 % | −8,6 % ± 2,8 |
    | 0,95-0,98 | 3 762 | 57,3 % | −6,3 % ± 2,9 |
    | 0,98-1,00 | 1 290 | 61,2 % | −0,2 % ± 4,9 |
    | 1,00-1,03 | 562 | 57,7 % | +5,0 % ± 8,6 |

    Cotes de 1,25 à 2,00 : < 0,95 → 57,0 % de réussite, −8,5 % ± 2,9 (3 210 paris) ;
    0,95-1,00 → 62,4 %, −3,6 % ± 2,6 (3 375) ; ≥ 1,00 → 64,8 %, +8,0 % ± 7,5 (471).
    Six semaines de cotes seulement : tendance nette, niveau encore incertain.

## Lecture d'ensemble

- 1X2, buts, mi-temps : aucune amélioration du moteur ne rattrape la cote ; la
  probabilité à afficher et à utiliser pour choisir est celle de Pinnacle, marge retirée
  par la méthode puissance.
- Ce qui améliore à la fois le taux de réussite et le rendement d'une sélection, à cote
  égale : **le prix** (cote proposée × probabilité Pinnacle), donc le choix du bookmaker
  et du marché, et l'abandon des cotes longues.
- Corners et cartons : seul endroit où le moteur tient tête au marché ; à suivre avec
  plus de matchs.

## Proposition (non appliquée)

Pour les suggestions de montante et les coupons : dans la plage de cote demandée, ne
garder que les sélections dont « cote × probabilité Pinnacle » ≥ 0,98, classées par ce
prix décroissant ; afficher le bookmaker qui paie le mieux ; probabilité « selon la
cote » par la méthode puissance. Le principe n° 4 reste respecté (le moteur sportif
n'utilise aucune cote) mais la sélection des paris s'appuierait sur les cotes : décision
du fondateur.
