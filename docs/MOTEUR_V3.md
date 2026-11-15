# Moteur 3.0 : loi des scores calée sur la cote de référence

> **Dans `footprono2026` : « moteur 2 », en mode comparaison seulement** (maquettes K1-K6
> validées le 15/11/2026). Il est servi **à côté** du moteur 1, jamais à sa place : le
> moteur 1, ses chances et ses choix ne changent pas. Code : `engine/market_fit.py`,
> `predictions/calibration.py`, `bookmaker/price.py`, `service.engine2_probabilities`,
> paramètre `engine=2` du Coupon intelligent, réglage du compte `compare_engines`.
> Suite (K4-K6) : suggestions de palier `engine=2` (le palier joué garde son moteur,
> `montante_steps.engine`), coupons du jour du moteur 2 (`smart_coupons.engine`, jamais dans
> l'historique public), et le juge `bookmaker/engine_compare.py` : chances 1-N-2 des deux
> moteurs relevées avant chaque match (log loss sur les mêmes matchs), chaque proposition
> enregistrée et réglée à 1 000 F (`engine_proposals`), verdict seulement à partir de 300
> matchs et 200 propositions réglées par moteur (`GET /reliability/engines`).

Version 2 de FootProba (dépôt `R-A-`), construite à partir de l'application d'origine
(`footprono2026`) et de ses données. Ce document décrit ce qui change dans le moteur et
ce qui a été mesuré. Études détaillées : [ETUDE_MOTEUR_V3_2026-11-15.md](ETUDE_MOTEUR_V3_2026-11-15.md).

## Ce qui avait échappé à la première version

1. **Le moteur était opposé à la cote au lieu de s'en servir.** Sur le 1-N-2 et les buts,
   la cote d'avant-match contient déjà tout ce que sait le modèle des buts : dans une
   combinaison moteur + cote, le poids appris du moteur est de 0,00 à 0,06 (25 000 matchs,
   avec ou sans xG).
2. **La marge du bookmaker était retirée à parts égales.** Les bookmakers en prennent plus
   sur les outsiders ; la méthode puissance le corrige (log loss 0,9547 contre 0,9561,
   favoris annoncés à 75 % : 77 % au lieu de 75 %, pour 79 % observés).
3. **Le prix payé n'était jamais regardé.** À cote égale, une sélection payée près de sa
   cote juste gagne plus souvent et perd moins qu'une sélection chère ; la première
   version choisissait sans cette information.
4. **Les grosses cotes perdent par construction** (−18 % entre 5 et 10, −39 % au-delà de
   10 chez Bet365, 15 001 matchs).

## Méthode

1. **Modèle des buts inchangé** (`engine/goals.py`) : estimé sans aucune cote. Il donne
   (λ domicile, λ extérieur), ρ et les parts de buts en première mi-temps.
2. **Cote de référence** (`predictions/calibration.py`) : dernières cotes Pinnacle du
   match (1-N-2 et plus/moins), marge retirée par la méthode puissance
   (`engine/market_fit.power_devig`).
3. **Calage** (`engine/market_fit.fit_rates`) : (λ domicile, λ extérieur) sont ajustés pour
   que la loi Dixon-Coles reproduise le 1-N-2 et le plus/moins de la référence ; ρ et les
   parts de mi-temps restent ceux du moteur. Sans plus/moins coté, le total de buts du
   moteur est gardé. Calage refusé si l'écart restant dépasse 0,03 (0,05 % des matchs).
4. **Tous les marchés de buts** sortent de cette loi calée (même code `derive_markets`,
   cohérence exacte entre marchés). **Corners et tirs** gardent le modèle du moteur.
5. **Sans cote de référence récente** (36 heures) : le moteur seul, comme avant. Aucune
   probabilité n'est inventée.
6. **Prix** (`bookmaker/price.py`) : probabilité calée fois cote proposée, en quatre
   tranches : bien payé (0,97 à 1,03), neutre (0,94 à 0,97, ou match non calé), cher
   (moins de 0,94), suspect (plus de 1,03 : cote qui n'a pas suivi le marché).
7. **Coupon intelligent et suggestions de montante** : les sélections de la meilleure
   tranche de prix d'abord, puis les critères d'origine (probabilité pour les coupons,
   cote la plus basse pour la montante).

## Résultats mesurés

### Probabilités, sur des marchés qui n'ont pas servi au calage

Archive football-data, prévisions hors échantillon, calage sur la cote moyenne
d'avant-match. Écart = calé − moteur, en log loss (négatif = meilleur), ± 2 erreurs types.

| Période | Matchs | Les deux équipes marquent | Résultat à la mi-temps | 1-N-2 |
|---|---|---|---|---|
| 2022-23 → 2026-27 | 15 019 | 0,6871 → 0,6844 (−0,0027 ± 0,0012) | 1,0292 → 1,0225 (−0,0066 ± 0,0017) | 0,9692 → 0,9552 |
| dont 5 grands (xG) | 7 581 | 0,6853 → 0,6824 (−0,0029 ± 0,0017) | 1,0336 → 1,0284 (−0,0053 ± 0,0023) | 0,9802 → 0,9672 |
| 2019-20 → 2021-22 | 10 440 | 0,6857 → 0,6829 (−0,0028 ± 0,0014) | 1,0351 → 1,0293 (−0,0058 ± 0,0021) | 0,9830 → 0,9732 |

Matchs réels du serveur (239 matchs calés, 14 260 sélections de buts réglées) : log loss
0,4790 → 0,4713 ; mieux sur 11 marchés sur 12 (seule exception : les deux équipes
marquent, 196 sélections).

### Prix, avec les cotes réellement jouables (1xBet, Bet365 en secours)

| Prix (p calée × cote) | Sélections | Réussite | Rendement |
|---|---|---|---|
| < 0,90 | 5 651 | 18,5 % | −24,5 % ± 5,7 |
| 0,90 à 0,94 | 3 419 | 52,6 % | −9,9 % ± 3,8 |
| 0,94 à 0,97 | 3 169 | 67,2 % | −5,1 % ± 3,1 |
| 0,97 à 1,00 | 1 703 | 72,6 % | −3,6 % ± 3,7 |

Cotes de 1,20 à 2,20 : < 0,94 → 59,1 %, −6,9 % ± 3,6 ; 0,94 à 0,97 → 65,5 %, −4,4 % ± 3,7 ;
0,97 à 1,00 → 68,5 %, +2,5 % ± 5,8. Le même découpage avec la probabilité du moteur seul
ne classe rien (−3 % à −7 % dans toutes les tranches).

### Coupons : une sélection par match, par profil (240 matchs réels)

| Profil | Version 1 : réussite, rendement | Version 2 : réussite, rendement |
|---|---|---|
| Sûr | 83,3 %, −2,3 % ± 5,7 | 84,0 %, −1,6 % ± 5,6 |
| Équilibré | 71,8 %, −7,1 % ± 7,6 | 72,4 %, +0,4 % ± 8,1 |
| Audacieux | 58,2 %, −3,7 % ± 10,7 | 55,2 %, −2,2 % ± 11,5 |

## Limites, dites telles quelles

- **Six semaines de cotes réelles** (30/09 → 14/11/2026) et 240 matchs pour le rejeu des
  coupons : les écarts entre versions vont dans le bon sens mais restent dans la marge
  d'erreur. Les gains sur les probabilités, eux, sont établis sur 25 000 matchs.
- **Aucune promesse de gain** : le rendement mesuré d'une sélection bien payée est proche
  de zéro, pas nettement positif. La version 2 perd moins et gagne plus souvent ; elle ne
  « bat » pas le bookmaker.
- **Dépendance à Pinnacle** : sans ses cotes (matchs peu suivis, trêve), le match n'est
  pas calé et la version 2 se comporte comme la version 1 pour ce match (28 matchs calés
  sur 47 prédits au 14/11/2026, pendant la trêve internationale).
- **Corners et cartons** : le moteur y fait jeu égal avec Pinnacle (≈ 550 sélections) ;
  pas encore assez de matchs pour en tirer une règle.

## Dans l'application (version 2)

| Écran | Ce qui change | Code |
|---|---|---|
| Onglet « Aujourd'hui » (ex-Matchs) | En tête : « Les paris bien payés du moment », une sélection par match (cotes 1,20 à 2,50, tranche « bien payé »), ajout au coupon d'un geste, mesures de réussite ; puis la liste des matchs | `GET /picks` (`bookmaker/picks.py`), `app/lib/widgets/good_picks.dart` |
| Fiche du match | « Les mieux payés de ce match » : chance, cote, marge, meilleur bookmaker (cotes 1,10 à 4,00) | `app/lib/widgets/price_table.dart` |
| Mon coupon | Jauge de la marge totale (1 − produit des prix) ; mise en garde au-delà de 10 % avant de miser | `app/lib/widgets/margin_gauge.dart` |
| Coupon intelligent, montante | Pastille de prix sur chaque sélection ; marge du coupon expliquée au lieu de « moteur moins confiant » | `app/lib/widgets/price_badge.dart` |
| Partout | Design « Braise » (brun nuit, orange, Sora et Plus Jakarta Sans), logo « Cadran », onglet « Moi » | `app/lib/theme.dart`, icônes `app/web`, `app/android` |

Maquettes validées le 15/11/2026 : `docs/maquettes-v2/`.

## Suite possible

1. Page de fiabilité par tranche de prix, mise à jour chaque jour à partir des paris réglés
   (aujourd'hui, les mesures de l'accueil sont celles de l'étude du 15/11/2026).
2. Corners et cartons : règle de choix quand l'échantillon le permettra.
3. Rejouer l'étude des coupons après quelques semaines de cotes supplémentaires.
