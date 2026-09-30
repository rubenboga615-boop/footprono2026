# Moteur de prédiction (phase 2)

Code : `backend/src/footprono/engine/` (indépendant du serveur web et de Celery).

## Méthode

1. **Historique** (`history.py`) : un match par ligne, valeurs absentes = `nan`
   (jamais complétées). Exclus de l'apprentissage : matchs annulés (Ligue 1
   2019-20) et matchs sur tapis vert (`AWARDED_MATCHES`).
2. **Modèle des buts** (`goals.py`), par championnat :
   `log λ_dom = μ + avantage_domicile + attaque_dom + défense_ext`,
   `log λ_ext = μ + attaque_ext + défense_dom`.
   - Vraisemblance de Poisson pondérée dans le temps (demi-vie 180 jours,
     fenêtre de 3 ans).
   - Cible = 0,3 × buts + 0,7 × xG Understat : les xG décrivent mieux la
     qualité réelle des équipes que les buts, plus aléatoires.
   - Pénalité vers un a priori : 0 pour les équipes connues, le quart le plus
     faible du championnat pour les promus sans historique.
   - Correction de Dixon-Coles (petits scores) et part des buts en 1re période
     estimées sur les vrais buts.
   - **Causalité stricte** : un modèle estimé « au » jour J n'utilise que les
     matchs joués avant J (test automatique : changer les résultats futurs ne
     change rien).
3. **Distribution des scores** (`scores.py`) : loi jointe (score à la
   mi-temps, score final) dont la marge « score final » est exactement la loi
   Dixon-Coles. Tous les marchés en découlent (principe n° 5).
4. **Marchés** (`markets.py`) : tous les marchés des groupes 1 et 2 de
   `MARCHES.md`, avec les issues de règlement (gagné, demi-gagné, remboursé,
   demi-perdu, perdu) et la cote juste. Cohérence testée automatiquement.

## Réglages

Choisis sur les saisons de **validation** 2019-20 → 2021-22, jamais sur les
saisons de test : demi-vie 180 j, poids des xG 0,7, pénalité 2, a priori des
promus activé (`footprono-engine backtest --seasons 2019-2021 …`).

## Résultats sur les saisons de test 2022-23 → 2025-26 (vérifié le 30/09/2026)

7 081 matchs, jamais vus pendant le réglage. Chaque match est prédit avec les
seuls matchs joués avant lui (modèle réestimé chaque semaine).
Log loss : plus bas = meilleur.

| Championnat | Matchs | 1X2 modèle | 1X2 référence naïve | 1X2 cotes de clôture |
|---|---|---|---|---|
| Premier League | 1 520 | 0,9764 | 1,0696 | 0,9605 |
| Liga | 1 520 | 0,9734 | 1,0633 | 0,9595 |
| Serie A | 1 520 | 0,9869 | 1,0872 | 0,9670 |
| Bundesliga | 1 223 | 0,9867 | 1,0753 | 0,9691 |
| Ligue 1 | 1 298 | 0,9961 | 1,0700 | 0,9784 |
| **Total** | **7 081** | **0,9834** | **1,0731** | **0,9665** |

| Marché | Modèle | Référence naïve | Cotes de clôture |
|---|---|---|---|
| 1X2 (RPS) | 0,1992 | 0,2302 | — |
| Plus/moins 2,5 buts | 0,6769 | 0,6873 | 0,6677 |
| Résultat à la mi-temps | 1,0355 | 1,0820 | — |
| Les deux équipes marquent | 0,6848 | 0,6884 | — |

Calibration 1X2 (probabilité annoncée → fréquence observée) :

| Tranche | Matchs × issues | Annoncé | Observé |
|---|---|---|---|
| 0,0-0,1 | 436 | 0,075 | 0,067 |
| 0,1-0,2 | 2 897 | 0,160 | 0,144 |
| 0,2-0,3 | 8 554 | 0,250 | 0,255 |
| 0,3-0,4 | 3 287 | 0,346 | 0,332 |
| 0,4-0,5 | 2 543 | 0,448 | 0,453 |
| 0,5-0,6 | 1 849 | 0,546 | 0,555 |
| 0,6-0,7 | 1 069 | 0,646 | 0,659 |
| 0,7-0,8 | 468 | 0,741 | 0,761 |
| 0,8-0,9 | 132 | 0,837 | 0,886 |

## Lecture

- Le modèle **bat nettement la référence naïve** sur tous les championnats
  (principe n° 6) et il est **bien calibré** au centre ; il est un peu trop
  prudent aux extrémités (les grands favoris gagnent un peu plus souvent
  qu'annoncé).
- Il reste **derrière les cotes de clôture** (0,9834 contre 0,9665) : c'est
  attendu, le marché de clôture intègre les compositions, blessures et
  informations de dernière minute que le modèle n'a pas. Conformément au
  principe n° 4, aucune « value » n'est affichée.
- « Les deux équipes marquent » : gain faible sur la référence naïve, à
  améliorer.

## Suite de la phase 2

1. Correction de calibration (réglée sur les saisons de validation).
2. Modèles des corners, cartons (avec l'arbitre dès qu'il est en base) et tirs.
3. Évaluation du handicap asiatique face aux cotes.
4. Enregistrement des prédictions (version du modèle, date), route d'API et
   tâche quotidienne.

## Commandes

```bash
footprono-engine backtest                                   # saisons de test 2022-2025
footprono-engine backtest --seasons 2019-2021 --grid        # comparaison de réglages
bash scripts/termux/engine.sh backtest                      # sur le téléphone
```
