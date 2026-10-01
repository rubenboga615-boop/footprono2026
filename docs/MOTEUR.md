# Moteur de prédiction (phase 2, terminée)

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
4. **Couche de correction** (`context.py`, `correction.py`) : voir plus bas.
5. **Marchés** (`markets.py`) : tous les marchés des groupes 1 et 2 de
   `MARCHES.md`, avec les issues de règlement (gagné, demi-gagné, remboursé,
   demi-perdu, perdu) et la cote juste. Cohérence testée automatiquement.

## Réglages

Choisis sur les saisons de **validation** 2019-20 → 2021-22, jamais sur les
saisons de test : demi-vie 180 j, poids des xG 0,7, pénalité 2, a priori des
promus activé (`footprono-engine backtest --seasons 2019-2021 …`).

## Couche de correction : contexte du match (vérifié le 30/09/2026)

Au-dessus de Dixon-Coles, une correction ajuste les buts attendus avant de
passer par la même loi des scores (les marchés restent cohérents) :

- **calibration** : écarte légèrement favoris et outsiders (le modèle brut
  était trop prudent sur les matchs déséquilibrés) ;
- **indicateurs de contexte**, tous **dérivés** des résultats déjà en base et
  connus avant le match : classement, avancement de la saison, enjeu, repos,
  dynamique, réussite (définitions dans `context.py`).

La correction de la saison S est apprise uniquement sur les prévisions hors
échantillon des saisons antérieures à S.

**Sélection des indicateurs** sur les saisons de validation 2019-20 → 2021-22
(5 376 matchs), un indicateur à la fois contre la calibration seule. Gain =
baisse de la log loss (positif = mieux), ± 2 erreurs types :

| Ajout | 1X2 | +2,5 buts | Les deux marquent | Décision |
|---|---|---|---|---|
| Calibration seule (contre le modèle brut) | +0,0005 ± 0,0005 | +0,0001 ± 0,0002 | 0,0000 ± 0,0001 | retenue |
| Sans enjeu (ne peut plus franchir aucune ligne) | +0,0008 ± 0,0008 | +0,0007 ± 0,0008 | +0,0005 ± 0,0006 | **retenu** |
| Lutte pour le maintien | +0,0002 ± 0,0006 | 0,0000 ± 0,0002 | −0,0001 ± 0,0001 | rejeté |
| Lutte pour le titre / la 4e place | −0,0001 ± 0,0002 | +0,0001 ± 0,0002 | −0,0001 ± 0,0002 | rejeté |
| Repos (jours depuis le dernier match) | −0,0001 ± 0,0002 | −0,0001 ± 0,0001 | −0,0001 ± 0,0001 | rejeté |
| Dynamique (5 derniers − 20 derniers, xG) | −0,0001 ± 0,0010 | +0,0001 ± 0,0003 | 0,0000 ± 0,0002 | rejeté |
| Réussite (buts − xG sur la saison) | −0,0002 ± 0,0004 | −0,0001 ± 0,0002 | 0,0000 ± 0,0001 | rejeté |

Effet estimé de « sans enjeu » : l'équipe concède environ **17 % de buts en
plus** (stable d'un apprentissage à l'autre). Une variante avec une constante
et l'avancement de la saison a aussi été essayée : rejetée, une constante figée
suit mal les ruptures (saisons sans public) alors que le modèle des buts
réestime déjà l'avantage du terrain chaque semaine.

Conclusion honnête : le contexte apporte peu, comme attendu (le niveau des
équipes, bien estimé, explique déjà l'essentiel). Les gains sont petits mais
réels sur les matchs de fin de saison concernés.

### Profil « équipe qui démarre fort » : testé, rejeté

Part des buts marqués et encaissés en 1re période propre à chaque équipe
(pondérée dans le temps, rétrécie vers celle du championnat), sur 12 457
matchs 2019-2025 : la log loss du résultat à la mi-temps **se dégrade**
(−0,0011 ± 0,0013 sans rétrécissement, −0,0004 ± 0,0010 avec). Ce profil est
surtout du bruit ; la part du championnat est conservée. En conséquence, la
collecte des tirs Understat minute par minute (≈ 18 000 pages, plusieurs
heures) n'est pas lancée : elle servirait surtout ce profil. Elle pourra
servir au direct (phase 3).

### Mi-temps la plus prolifique : pas mieux que les fréquences

Test 2022-2025 (7 081 matchs) : log loss 1,0709 contre 1,0700 pour les
fréquences observées (1re 29 %, 2e 45 %, égalité 26 %). Les probabilités
varient très peu d'un match à l'autre ; elles sont justes en moyenne, avec une
légère surestimation de la 1re période en 2023-24 et après (part réelle des
buts en 1re période tombée de 45,2 % à 43,6 %, probablement avec
l'allongement des temps additionnels ; le modèle suit avec retard).

Corrections essayées, toutes **rejetées** car elles dégradent la validation
2019-2021 (et le test) : réduire la part de 1re période de 2 à 6 %, estimer
cette part avec une mémoire plus courte (demi-vie 60, 90, 120 jours au lieu de
180). Décision : marché conservé (coupons, règlement), **exclu des
suggestions automatiques de la montante**, car le moteur n'y apporte rien de
plus que les fréquences.

## « Angle du match » et coupons (`footprono-engine angles`, à mesurer)

Question du Coupon intelligent : si l'on choisit, dans chaque match, le
marché le plus probable d'une tranche (« sûr » 75-90 %, « équilibré »
60-75 %, « audacieux » 45-60 %), la probabilité annoncée reste-t-elle juste ?
Prendre un maximum parmi des dizaines de marchés favorise les erreurs du
modèle (malédiction du gagnant). Mesures, hors échantillon : calibration de
toutes les sélections (référence), de l'angle choisi (au total et par
famille de marché), des coupons du jour de 2 à 4 angles, et rendement aux
cotes de clôture réelles (1X2 et plus/moins 2,5 : seules cotes historiques).
Méthode vérifiée sur données simulées : moteur exact → angle juste ;
moteur bruité → surestimation détectée (`tests/test_angles.py`).
Résultats sur les vraies données : à compléter.

## Résultats sur les saisons de test 2022-23 → 2025-26 (vérifié le 30/09/2026)

7 081 matchs, jamais vus pendant le réglage ni la sélection. Chaque match est
prédit avec les seuls matchs joués avant lui (modèle réestimé chaque semaine,
correction apprise sur les saisons antérieures). Log loss : plus bas = meilleur.

| Championnat | Matchs | 1X2 modèle | 1X2 référence naïve | 1X2 cotes de clôture |
|---|---|---|---|---|
| Premier League | 1 520 | 0,9746 | 1,0696 | 0,9605 |
| Liga | 1 520 | 0,9716 | 1,0633 | 0,9595 |
| Serie A | 1 520 | 0,9865 | 1,0872 | 0,9670 |
| Bundesliga | 1 223 | 0,9870 | 1,0753 | 0,9691 |
| Ligue 1 | 1 298 | 0,9969 | 1,0700 | 0,9784 |
| **Total** | **7 081** | **0,9827** | **1,0731** | **0,9665** |

Sans correction (Dixon-Coles brut) : 0,9834.

| Marché | Modèle | Référence naïve | Cotes de clôture |
|---|---|---|---|
| 1X2 (RPS) | 0,1990 | 0,2302 | — |
| Plus/moins 2,5 buts | 0,6768 | 0,6873 | 0,6677 |
| Résultat à la mi-temps | 1,0353 | 1,0820 | — |
| Les deux équipes marquent | 0,6844 | 0,6884 | — |

Calibration 1X2 (probabilité annoncée → fréquence observée) :

| Tranche | Matchs × issues | Annoncé | Observé | Avant correction |
|---|---|---|---|---|
| 0,0-0,1 | 549 | 0,074 | 0,060 | 0,075 → 0,067 |
| 0,1-0,2 | 3 040 | 0,160 | 0,153 | 0,160 → 0,144 |
| 0,2-0,3 | 8 366 | 0,250 | 0,256 | 0,250 → 0,255 |
| 0,3-0,4 | 3 164 | 0,346 | 0,335 | 0,346 → 0,332 |
| 0,4-0,5 | 2 498 | 0,448 | 0,447 | 0,448 → 0,453 |
| 0,5-0,6 | 1 832 | 0,547 | 0,550 | 0,546 → 0,555 |
| 0,6-0,7 | 1 076 | 0,647 | 0,648 | 0,646 → 0,659 |
| 0,7-0,8 | 538 | 0,742 | 0,764 | 0,741 → 0,761 |
| 0,8-0,9 | 168 | 0,840 | 0,851 | 0,837 → 0,886 |

## Corners, cartons et tirs (`counts.py`, vérifié le 30/09/2026)

Même principe que les buts : pour chaque statistique, niveau « pour » et
« contre » de chaque équipe et avantage du terrain, pondérés dans le temps
(demi-vie 180 jours), pénalisés, avec les seuls matchs antérieurs. Dispersion
par une loi binomiale négative (les cartons varient plus qu'une loi de
Poisson ; les corners non). Données : football-data, 100 % des matchs depuis
2016-17.

Réglages choisis sur la validation 2019-20 → 2021-22 (pénalité 60 pour
corners et tirs, 30 pour les cartons). Saisons de test 2022-23 → 2025-26,
7 081 matchs, log loss (plus bas = mieux) :

| Statistique | Total exact : modèle | naïf | Plus/moins | modèle | naïf |
|---|---|---|---|---|---|
| Corners | 2,6106 | 2,6635 | 9,5 | 0,6840 | 0,6909 |
| Cartons (jaunes + rouges) | 2,1884 | 2,2573 | 4,5 | 0,6603 | 0,6799 |
| Tirs | 3,1456 | 3,2328 | 24,5 | 0,6634 | 0,6929 |
| Tirs cadrés | 2,5165 | 2,6005 | 8,5 | 0,6728 | 0,6940 |

Référence naïve : distribution des totaux du championnat sur la même
fenêtre. Calibration du plus/moins correcte (écarts de 1 à 4 points par
tranche) ; les cartons sont un peu trop annoncés au-dessus de 50 %.
Aucune cote corners/cartons dans nos sources : pas de comparaison au marché.

**Arbitre** (Premier League seulement pour l'instant : football-data ne donne
l'arbitre que pour elle) : facteur observé / attendu, rétréci vers 1 avec
10 matchs fictifs. Validation : log loss du total des cartons 2,0079 → 1,9944
(net gain). Test 2022-2025 : 2,1322 → 2,1341 (nul). Conservé, à réévaluer
quand API-Football aura rempli l'arbitre des 5 championnats. Les noms
d'arbitre API-Football sont préférés (ce sont ceux connus avant le match) ;
tant qu'ils manquent, le nom football-data est utilisé.

Marchés produits : total, par équipe, « le plus de » (1X2) pour corners,
cartons, tirs et tirs cadrés ; handicap corners ; points de cartons (jaune 10,
rouge 25 ; un 2e jaune suivi du rouge compte 35 ici, 25 chez certains
bookmakers). Par mi-temps : pas encore (historique API-Football depuis
2024-25 seulement).

## Handicap asiatique face aux cotes (`footprono-engine ah`, vérifié le 30/09/2026)

À la ligne proposée par le bookmaker (Pinnacle en priorité, sinon moyenne du
marché), saisons de test 2022-23 → 2025-26, 7 081 matchs. Log loss pondérée
sur le règlement réel (remboursement ignoré, demi-gain et demi-perte comptés
pour moitié), en probabilité « équivalente » (1 / cote juste) :

| | Modèle | Marché (marge retirée) | Pile ou face |
|---|---|---|---|
| Cotes d'avant-match | 0,7037 | 0,6919 | 0,6931 |
| Cotes de clôture | 0,7057 | 0,6920 | 0,6931 |

Simulation de mise fixe (on joue le côté dont l'espérance calculée par le
modèle, à la vraie cote, dépasse le seuil ; ± 2 erreurs types) :

| Espérance du modèle | Paris (clôture) | Rendement clôture | Rendement avant-match |
|---|---|---|---|
| > 0 % | 5 914 | −3,5 % ± 2,3 | −5,1 % ± 2,4 |
| > 5 % | 3 625 | −4,8 % ± 3,0 | −5,3 % ± 3,1 |
| > 10 % | 2 043 | −6,3 % ± 4,0 | −7,3 % ± 4,4 |

**Lecture honnête** : à la ligne du bookmaker, le modèle fait *moins bien que
pile ou face*. Le bookmaker place sa ligne là où les deux côtés se valent ; le
modèle s'en écarte en moyenne de 6,6 points de probabilité, et ces écarts
sont surtout ses propres erreurs (il ignore compositions, blessures,
informations de dernière minute). Plus le modèle croit tenir une « value »,
plus on perd. Confirmation du principe n° 4 : **aucune value n'est affichée**
face aux cotes ; les cotes justes du modèle servent à expliquer une
probabilité, pas à battre le bookmaker. Même validation 2019-2021 : modèle
0,7028, marché 0,6927 (clôture).

## Lecture

- Le modèle **bat nettement la référence naïve** sur tous les championnats
  (principe n° 6) et il est **bien calibré**, y compris désormais pour les
  grands favoris.
- Il reste **derrière les cotes de clôture** (0,9827 contre 0,9665) : c'est
  attendu, le marché de clôture intègre les compositions, blessures et
  informations de dernière minute que le modèle n'a pas. Conformément au
  principe n° 4, aucune « value » n'est affichée.
- « Les deux équipes marquent » : gain faible sur la référence naïve, à
  améliorer.

## Suite de la phase 2

1. ~~Correction de calibration~~ et ~~indicateurs de contexte~~ (fait).
2. ~~Parts de mi-temps par équipe~~ (testé, rejeté ; collecte des tirs
   Understat reportée).
3. ~~Corners, cartons (avec l'arbitre) et tirs~~ (fait ; par mi-temps
   quand l'historique API-Football sera suffisant).
4. ~~Évaluation du handicap asiatique face aux cotes~~ (fait : le marché
   est nettement meilleur à sa propre ligne).
5. ~~Enregistrement des prédictions, route d'API et tâche quotidienne~~
   (fait, voir ci-dessous).

## Prédictions enregistrées

`footprono-engine predict` (et la tâche Celery `footprono.predict_upcoming`,
chaque jour à 07:45 et 16:45 UTC) prédit les matchs non joués des 10
prochains jours, avec le même code que le backtest :

- modèle des buts estimé avec les matchs joués avant le jour J ;
- correction (calibration + « sans enjeu ») apprise sur toutes les
  prévisions hors échantillon des saisons passées ;
- corners, cartons, tirs, tirs cadrés, jaunes et rouges (points de cartons),
  avec l'arbitre quand il est connu.

Horaires (UTC) : 07:45 après les résultats de la nuit (06:15) et les cotes et
le calendrier (07:30) ; 16:45 avant les matchs du soir (arbitres désignés,
matchs ajoutés dans la journée). Rattrapage (`footprono.predict_if_needed`) :
au démarrage du worker, toutes les heures et après chaque collecte des cotes,
le calcul est relancé si la dernière exécution a plus de 12 h (serveur éteint
aux heures prévues) ou si un match à venir n'a jamais été examiné (ajouté au
calendrier depuis). Un match examiné mais non prédit (erreur au rapport) ne
relance pas le calcul en boucle.

Chaque exécution (`prediction_runs`) garde la version du moteur
(`ENGINE_VERSION`, actuellement 2.0), ses réglages et les coefficients de
correction ; chaque prédiction (`match_predictions`) garde les buts attendus,
tous les marchés (gagné, demi-gagné, remboursé, demi-perdu), les moyennes
corners/cartons/tirs et le contexte (classement, points, enjeu). Rien n'est
écrasé : on saura toujours ce qui avait été annoncé **avant** chaque match,
base de la future page publique de fiabilité.

API :

| Route | Contenu |
|---|---|
| `GET /api/v1/predictions/upcoming` | matchs à venir avec 1X2, +2,5 buts, les deux marquent (probabilité et cote juste) |
| `GET /api/v1/matches/{id}/prediction?market=AH` | dernière prédiction complète d'un match (filtre de marché facultatif) |
| `GET /api/v1/predictions/runs` | exécutions du moteur, réglages et rapport |

Durée : environ 30 s ici, quelques minutes sur le téléphone (l'essentiel est
l'apprentissage de la correction).

## Commandes

```bash
footprono-engine backtest                                   # saisons de test 2022-2025
footprono-engine backtest --seasons 2019-2021 --grid        # comparaison de réglages
footprono-engine backtest --no-correction                   # Dixon-Coles brut
footprono-engine features                                   # gain de chaque indicateur
footprono-engine counts                                     # corners, cartons, tirs
footprono-engine ah                                         # handicap asiatique contre les cotes
footprono-engine predict                                    # prédit et enregistre les 10 prochains jours
bash scripts/termux/engine.sh backtest                      # sur le téléphone
```
