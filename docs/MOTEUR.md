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
     qualité réelle des équipes que les buts, plus aléatoires. Les xG sont
     remis au niveau des vrais buts du championnat (voir plus bas).
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

## xG remis au niveau des vrais buts (vérifié le 02/10/2026)

La calibration détaillée a montré une surestimation des buts en 2024-2025
(+2,5 buts : annoncé 55,5 %, observé 53,4 % ; +3,5 : 33,9 % / 30,9 %), en
Liga, Serie A et Ligue 1. Cause : le rapport buts / xG Understat est passé
de 1,00 (2019-2021) à 0,91 (2025) ; le moteur apprenant à 70 % sur les xG en
héritait. Correction (`GoalsConfig.xg_rescale`) : dans chaque championnat,
les xG de la fenêtre d'apprentissage sont multipliés par le rapport buts / xG
de cette fenêtre (mêmes poids) ; ils gardent leur information relative.

| Log loss / écart observé - annoncé | Validation 2019-21 avant | après | Test 2022-25 avant | après |
|---|---|---|---|---|
| +1,5 buts | 0,5229 / +0,7 % | 0,5229 / +0,7 % | 0,5258 / −1,2 % | 0,5253 / +0,5 % |
| +2,5 buts | 0,6758 / +0,4 % | 0,6759 / +0,3 % | 0,6768 / −2,1 % | 0,6758 / +0,3 % |
| +3,5 buts | 0,6040 / −0,2 % | 0,6039 / −0,3 % | 0,6022 / −3,0 % | 0,5999 / −0,7 % |
| Domicile +1,5 | 0,6377 / −0,6 % | 0,6380 / −0,6 % | 0,6421 / −2,1 % | 0,6411 / −0,3 % |
| Mi-temps +1,5 | 0,6451 / +0,5 % | 0,6453 / +0,4 % | 0,6420 / −2,3 % | 0,6406 / −0,7 % |
| Les deux marquent | 0,6846 / +1,2 % | 0,6843 / +1,1 % | 0,6844 / −0,3 % | 0,6850 / +1,4 % |
| 1X2 (3 issues) | inchangé à ±0,0002 | | inchangé à ±0,0003 | |

Neutre en validation (pas de dérive à l'époque), nette amélioration en test.
Honnêteté : le problème a été repéré sur les saisons de test ; la saison
2026-27 en cours servira de vraie vérification hors échantillon.
Autres pistes essayées, rejetées : poids des xG 0,5 ou 0,3 (moins bons en
validation, corrigent moins en test). Les nuls (+0,9 % après correction,
dans la marge d'erreur) ne demandent pas de correction propre.

## Cartons : surestimés au-dessus de 50 %, correction non retenue (02/10/2026)

Plus/moins 4,5 cartons : au-dessus de 50 % annoncés, le moteur surestime de
plus en plus (test 2022 → 2025 : −1,2 ; −3,7 ; −5,6 ; −6,4 points). Essais :
- plus de rétrécissement (pénalité 60 ou 120, arbitre 40 matchs fictifs) :
  écart réduit en test, mais log loss dégradée en validation 2019-21
  (réglage actuel le meilleur : 0,6288 contre 0,6295 à 0,6358) ;
- recalibration glissante (apprise sur les saisons précédentes) : gain
  négligeable (≈ 0,0003) et irrégulier, la dérive grandit plus vite.

Décision : modèle inchangé ; les cartons restent affichés mais **exclus des
choix automatiques** (Coupon intelligent, suggestions de montante) tant
qu'aucune correction n'est prouvée. Corners : calibrés (écarts de −0,8 à
+2,0 points), rien à corriger.

## Calibration détaillée (`footprono-engine calibration`)

Pour chaque marché suivi (1X2, double chance, +1,5/2,5/3,5 buts, les deux
marquent, buts de chaque équipe, mi-temps, corners +9,5, cartons +4,5), par
championnat et par saison : log loss et score de Brier du moteur contre une
référence naïve **causale** (fréquence de l'issue dans le championnat sur les
3 saisons précédentes), écart observé - annoncé avec son erreur type, courbe
de calibration par tranches de 10 points, et alertes sur les cases
(championnat, saison) qui dérivent de plus de 3 erreurs types (seuil large :
sur des centaines de cases, 2 erreurs types donneraient des fausses alertes).
Méthode vérifiée sur données simulées (`tests/test_calibration.py`) : moteur
exact → aucune alerte et gain sur la référence ; moteur biaisé dans une seule
case → cette case est signalée, et elle seule.

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

## Handicap asiatique contre le marché, données réelles (02/10/2026)

`footprono-engine ah` après chargement des cotes football-data du handicap
(2022-2025, environ 7 080 matchs, ligne du bookmaker) :

| Cotes | Log loss moteur | Log loss marché | Pile ou face |
|---|---|---|---|
| Avant-match | 0,7038 | 0,6919 | 0,6931 |
| Clôture | 0,7058 | 0,6920 | 0,6931 |

Rendement en jouant quand le moteur voit une espérance positive : −3,6 à
−6,5 % (± 2,3 à 4,4), pire quand l'écart annoncé est grand. À la ligne du
bookmaker, les écarts du moteur avec le marché sont du bruit. Décisions :
handicap asiatique retiré des choix automatiques (`bookmaker/rules.py`) ;
plus aucun badge d'écart avec la cote dans l'application.

## Coupon intelligent : plafond ou milieu de la tranche (02/10/2026)

Hors échantillon (12 457 matchs 2019-2025, moteur actuel), sélection la plus
probable de la tranche (« plafond ») ou la plus proche de son milieu. Test
2022-2025, coupons de 3 :

| Profil | Règle | Annoncé | Observé | Cote juste |
|---|---|---|---|---|
| Sûr | plafond | 76,4 % | 78,5 % | 1,31 |
| Sûr | milieu | 60,2 % | 61,5 % | 1,66 |
| Équilibré | plafond | 41,1 % | 40,0 % | 2,44 |
| Équilibré | milieu | 32,0 % | 33,6 % | 3,13 |
| Audacieux | plafond | 20,5 % | 20,3 % | 4,90 |
| Audacieux | milieu | 15,9 % | 13,3 % | 6,32 |

Les deux règles sont justes (écarts dans la marge, mêmes conclusions sur
2019-2021) : seul change le compromis chances / gain. Retenu : milieu pour
Sûr (cote enfin utile), plafond pour Équilibré et Audacieux (au milieu, ils
se confondraient).

## Études du 02/10/2026 sur les données réelles (export du serveur)

Méthode habituelle : réglage choisi sur les saisons 2019-20 → 2021-22, puis
confirmé sans retouche sur 2022-23 → 2025-26 (7 081 matchs). Log loss : plus
bas = mieux.

### Arbitres regroupés (adopté, moteur 2.2)

Un même arbitre était écrit « Stuart Attwell » (API-Football), « S. Attwell »
(API-Football, saisons récentes) ou « S Attwell » (football-data) : 520
« arbitres » au lieu de 324. Clé unique initiale + nom
(`football/referees.py`, `referee_key`). Cartons, plus/moins 4,5 :

| | 2019-22 | 2022-26 |
|---|---|---|
| sans arbitre | 0,63811 | 0,66027 |
| arbitre, noms bruts | 0,62878 | 0,65710 |
| arbitre, noms regroupés | **0,62817** | **0,65637** |

Poids de l'arbitre (`referee_prior`) : 10 reste le meilleur sur 2019-22
(5 et 20 testés).

### Passes dangereuses dans le signal d'occasions (adopté, moteur 2.2)

Cible du modèle des buts : `0,3 × buts + 0,7 × signal`, où le signal était
le xG ; il devient `0,7 × xG + 0,3 × deep` (passes réussies près de la
surface, Understat, ramenées au niveau des xG sur la fenêtre). Poids 0,15 /
0,3 / 0,45 / 0,6 / 0,8 / 1 testés sur 2019-22 : 0,3 le meilleur.

Chaîne complète (corrections comprises), 2022-26 :

| | 1X2 | RPS | +2,5 buts | les deux marquent |
|---|---|---|---|---|
| sans deep | 0,98274 | 0,19908 | 0,67583 | 0,68496 |
| avec deep 0,3 | **0,98133** | **0,19875** | **0,67429** | **0,68466** |

1X2 et plus/moins 2,5 meilleurs dans les 5 championnats ; « les deux
marquent » très légèrement moins bon en Serie A et Bundesliga, meilleur
ailleurs.

Rejetés : xG hors penalty (npxG) à la place du xG, aucun gain (1X2 0,98855
contre 0,98863 sur 2019-22, « les deux marquent » moins bon) ; pressing
(PPDA) non retenu comme signal de force : il décrit un style de jeu, pas la
qualité des occasions.

### Corners et cartons de la 1re mi-temps : pas encore

Statistiques par mi-temps disponibles depuis 2024-25 seulement. Modèle :
moyenne du match × part de la 1re mi-temps du championnat (apprise sur
2024-25), testé sur 2025-26 (1 751 matchs). Corners : pas mieux que la
fréquence seule (plus de 3,5 : 0,6576 contre 0,6575). Cartons : mieux que la
fréquence (plus de 1,5 : 0,6490 contre 0,6620) mais surestimés (plus de
0,5 : annoncé 74,1 %, réalisé 72,0 %). Une seule saison de test : marchés
non ajoutés, à refaire après 2026-27.

## Coupon « Grosse cote » : ne jamais choisir sur un désaccord avec la cote (03/10/2026)

Première version : parmi les angles des trois profils, la combinaison qui
atteint la cote visée avec la plus grande probabilité selon le moteur.
Essayée sur les données réelles (prochaine journée, cotes du serveur), elle
choisissait les sélections où le moteur contredit le plus le bookmaker
(exemple : 74 % annoncés pour une cote de 1,90, soit 53 % selon la cote) :
coupon de cote 10 annoncé à 23 % par le moteur contre 9,7 % selon la cote.
Or quand ils ne sont pas d'accord, la cote a le plus souvent raison
(handicap asiatique, ci-dessus). Même biais avec « la plus probable des
sélections dont la cote suffit » pour finir le coupon (12,9 % contre 9,8 %).

Retenu : pour chaque profil, ses angles ajoutés du plus probable au moins
probable jusqu'à la cote visée (ordre de probabilité pur, la cote ne sert
qu'à savoir quand s'arrêter) ; entre les trois coupons, celui dont la cote
est la plus proche de la cible. Résultat sur les mêmes données : cote 10,07,
moteur 9,6 %, cote 9,9 % ; aux cotes de 25 à 100, le moteur est plus prudent
que la cote. L'application affiche toujours les deux.

## Championnats sans xG : le moteur sans xG, et des xG « maison » tirés des tirs (03/10/2026)

Expérience préalable à l'ouverture d'autres championnats : sur nos 5 championnats
(export réel du 02/10/2026), on retire les xG et on mesure ce que le moteur perd.
Les réglages sont choisis sur 2019-20 → 2021-22, puis figés pour le test 2022-23 → 2025-26
(7 081 matchs). Script : `scratchpad/exp_tiers.py` (hors dépôt).

- **A, moteur actuel** : xG Understat + passes dangereuses.
- **B, buts seuls** : ce que le moteur fait sans aucune statistique.
- **C, xG « maison »** : relation apprise là où on a les deux (saisons ≤ 2021) :
  `xG ≈ 0,018 + 0,218 × tir cadré + 0,060 × tir non cadré − 0,016 × corner`.
  Les tirs resserrent l'écart entre équipes (l'équipe menée tire plus, celle qui mène
  moins) : sans correction, les favoris sont sous-estimés (48,8 % annoncés pour 52,2 %
  réalisés, validation). Correction : chaque valeur est écartée de la moyenne du
  championnat (domicile et extérieur à part) d'un facteur 1,5 ; poids 0,5 dans le signal.

| Test 2022-26 (log loss, plus bas = mieux) | 1-N-2 | +2,5 buts | Les deux marquent | Calibration 1-N-2 |
|---|---|---|---|---|
| A, moteur actuel | 0,9818 | 0,6749 | 0,6853 | 1,1 pt |
| C, xG « maison » | 0,9842 | 0,6783 | 0,6870 | 0,7 pt |
| B, buts seuls | 0,9902 | 0,6838 | 0,6904 | 0,4 pt |
| Référence naïve | 1,0731 | | | |
| Cotes de clôture | 0,9665 | | | |

Lecture : sans xG, le moteur reste nettement meilleur que la référence naïve et bien
calibré (B). Les xG « maison » regagnent **71 %** de l'écart entre B et A sur le 1-N-2,
**61 %** sur +2,5 buts et **66 %** sur « les deux marquent », sans dégrader la calibration.

Transfert vers un championnat jamais vu (relation apprise sur 4 championnats, testée sur
le 5e) : R² de 0,50 à 0,57 selon le championnat, biais moyen de −0,04 à +0,05 xG par
équipe et par match (le moteur remet de toute façon les xG au niveau des vrais buts du
championnat). La relation devrait donc se transposer aux championnats qui publient les tirs.

Conséquence : niveaux de données par championnat (1 : xG + passes dangereuses ; 2 : tirs,
xG « maison » ; 3 : buts seuls), chaque nouveau championnat étant mesuré sur ses saisons
passées avant publication, avec sa fiabilité affichée. Rien n'est encore changé dans le
moteur en service.

## Étude Portugal et Belgique (football-data, 03/10/2026)

Fichiers football-data.co.uk 2010-11 → 2026-27 envoyés depuis le serveur
(`scripts/termux/download-football-data.sh`). Tirs disponibles depuis 2017-18
(niveau 2), cotes Pinnacle depuis 2012-13, pas d'arbitre. Étude hors application
(`scratchpad/exp_newleagues.py`) : historique construit en mémoire avec le lecteur
football-data du serveur. xG « maison » : relation apprise sur les 5 grands
championnats seulement (jamais sur P1/B1), étirement 1,5, poids 0,5.

Validation 2019-22 : le 1-N-2 bat nettement la référence naïve, mais « plus/moins
2,5 » et « les deux marquent » font à peine aussi bien qu'elle. Le niveau moyen
de buts est juste ; le moteur sépare trop les matchs « à buts » des matchs
« fermés » (pente 0,4 à 0,6 : forces d'attaque et de défense plus bruitées, moins
de matchs par équipe). Renforcer la régularisation aide ces marchés mais écrase
les favoris. Retenu : **profil de buts modéré** (chaque équipe garde sa force,
attaque − défense ; son profil, attaque + défense, est rapproché de la moyenne
du championnat de moitié) et mémoire d'un an (demi-vie 365 jours).

| Test 2022-26, 2 465 matchs (log loss) | 1-N-2 | +2,5 buts | Les deux marquent |
|---|---|---|---|
| Buts seuls, réglage d'origine | 0,9673 | 0,6885 | 0,6976 |
| xG « maison », réglage d'origine | 0,9591 | 0,6834 | 0,6941 |
| xG « maison », réglage retenu | 0,9602 | 0,6798 | 0,6912 |
| Référence naïve | 1,0741 | 0,6923 | 0,6915 |
| Cotes de clôture | 0,9432 | | |

Écart au marché de clôture (1-N-2, xG « maison », réglage d'origine) : Portugal
0,019, Belgique 0,013, du même ordre que les 5 grands (0,015 à 0,018).
Calibration 1-N-2 : 1,9 à 2,4 points (1,1 dans les 5 grands).

Limites constatées sur le test :
- « Les deux marquent » n'apporte rien de plus que la fréquence du championnat
  (0,6912 contre 0,6915) : à ne pas présenter comme un avis du moteur.
- Portugal : buts sous-estimés en 2022-26 (+2,5 annoncé 47,8 % pour 51,5 % réalisé) ;
  le niveau de buts du championnat a monté et la mémoire d'un an le suit lentement.
  Piste : mémoire courte pour le niveau du championnat, longue pour les équipes.
- Favoris un peu sous-estimés au Portugal (54 % annoncé pour 56 % réalisé).

Le profil de buts modéré n'a pas été essayé sur les 5 grands championnats.

### Portugal : buts sous-estimés en 2022-26, deux corrections essayées, aucune retenue

1. **Niveau de buts recalé sur les matchs récents** (mémoire courte de 45, 90 ou 180
   jours pour le niveau du championnat, mémoire d'un an pour les équipes) : aucun gain
   sur la validation 2019-22 ni sur une période jamais regardée, 2012-19 (1-N-2, +2,5 et
   les deux marquent égaux ou un peu moins bons).
2. **Décalage par championnat appris sur les 3 saisons précédentes** (+2,5 et les deux
   marquent) : moins bon sur la validation, égal sur le test, mitigé sur 2016-19.

Explication : avec environ 306 matchs par saison, la part réelle de « plus de 2,5 buts »
varie d'environ ±3 points d'une saison à l'autre par simple hasard (Portugal : 44 %, 55 %,
49 %, 54 % sur 2020-26 ; annoncé constamment autour de 47-49 %). Sur 2013-26, l'annonce
moyenne reste proche de la réalité. Courir après le niveau récent ajoute du bruit au lieu
d'en retirer. Réglage conservé pour ces championnats : xG « maison », mémoire d'un an,
profil de buts modéré de moitié, sans recalage du niveau.

## Moteur 2.3 : Portugal et Belgique en service (niveau 2, 03/10/2026)

Niveaux de données par championnat : `engine/tiers.py`. Niveau 1 (5 grands) inchangé,
au chiffre près sur 2022-26. Niveau 2 (`POR`, `BEL`) :

- xG « maison » tirés des tirs (relation des 5 grands, étirement 1,5), poids 0,5,
  mémoire d'un an, profil de buts modéré de moitié ;
- **écart favori / outsider** recalé : au niveau 2, le modèle des buts sous-estime les
  favoris (favoris à 60 % ou plus : 70,7 % annoncé pour 76,5 % réalisé sur 2022-26),
  y compris avec les buts seuls (ce ne sont donc pas les xG « maison »). Ni la
  régularisation, ni l'étirement des xG, ni la couche de correction des 5 grands ne
  le corrigent. Retenu : `log λ_dom + s·d`, `log λ_ext − s·d` (d = écart de niveau),
  `s` choisi parmi 0 à 0,40 par la log loss du 1-N-2 sur toutes les prévisions hors
  échantillon antérieures, **championnat par championnat** (`fit_level_stretch`) :
  Portugal 0,10 à 0,15, Belgique 0. Validation 2019-22 : 1-N-2 0,9793 → 0,9797 ;
  test 2022-26 : 0,9551 → 0,9525, plus/moins 2,5 0,6789 → 0,6764, favoris 73,9 %
  annoncé pour 75,0 % réalisé. Appris sur les deux championnats ensemble, l'écart
  donnait 0,9782 et 0,9538 ; il est appris par championnat pour une raison de
  structure : un championnat équilibré (deuxième division) l'efface pour tous (0 sur
  les 9 candidats ci-dessous réunis, alors que la Grèce prend 0,10 seule) ;
- pas de corners, cartons ni tirs (non mesurés) ; pas de « les deux marquent ».

Belgique : la phase finale (après la 30e journée) n'est pas chargée. La base n'admet
qu'une affiche par saison et API-Football n'est lu que pour la saison régulière ; les
matchs de la phase finale (de fin mars à mai) ne sont donc pas prédits.

Backtest de bout en bout (données chargées par le serveur, 2022-26, 2 250 matchs) :
1-N-2 0,9525 (naïf 1,0731, clôture 0,9389), plus/moins 2,5 0,6764 (naïf 0,6928,
clôture 0,6711). Affiché sur la page Fiabilité quand le Portugal ou la Belgique est choisi.

## Championnats candidats (archive football-data, 03/10/2026)

Réglages du niveau 2 appliqués tels quels (rien n'est réglé sur ces championnats),
écart favori / outsider appris par championnat sur les saisons précédentes, une affiche
par saison (comme le serveur). Script : `scratchpad/study_candidates.py` (hors dépôt).
Test 2022-26 ; « gain » = log loss naïve − log loss du moteur (1-N-2), « retard » =
log loss du moteur − log loss des cotes de clôture.

| Championnat | Matchs | Gain | Retard | +2,5 / naïf | Calibration |
|---|---|---|---|---|---|
| Grèce | 728 | 0,157 | 0,012 | 0,6869 / 0,6950 | 2,8 pts |
| Pays-Bas | 1 224 | 0,120 | 0,019 | 0,6670 / 0,6743 | 1,7 pt |
| Écosse | 528 | 0,112 | 0,020 | 0,6972 / 0,6969 | 2,0 pts |
| Turquie | 1 370 | 0,093 | 0,035 | 0,6758 / 0,6893 | 1,1 pt |
| Championship | 2 208 | 0,032 | 0,011 | 0,6882 / 0,6927 | 0,9 pt |
| 2. Bundesliga | 1 224 | 0,026 | 0,011 | 0,6760 / 0,6775 | 1,1 pt |
| Liga 2 | 1 848 | 0,016 | 0,021 | 0,6725 / 0,6808 | 0,5 pt |
| Ligue 2 | 1 370 | 0,016 | 0,025 | 0,6904 / 0,6919 | 0,7 pt |
| Serie B | 1 520 | 0,018 | 0,027 | 0,6937 / 0,6902 | 1,2 pt |
| *Repères : 5 grands* | 7 081 | 0,091 | 0,015 | | 1,1 pt |
| *Portugal* | 1 224 | 0,155 | 0,017 | 0,6787 / 0,6935 | 1,8 pt |

Lecture : les premières divisions (Grèce, Pays-Bas, Turquie, Écosse) se comportent
comme le Portugal. La Turquie reste loin des cotes de clôture (0,035). Les deuxièmes
divisions sont très équilibrées : le moteur y apporte peu face à la référence naïve
(gain de 0,016 à 0,032), tout en restant bien calibré ; Serie B : plus/moins 2,5 moins
bon que la référence naïve. Écosse : la phase finale (deuxième partie de saison) rejoue
des affiches ; avec une affiche par saison, une grande partie des matchs n'est ni
chargée ni prédite (528 matchs en 4 saisons, environ 230 par saison en réalité).

## Pays-Bas, Grèce et Turquie en service (niveau 2, 03/10/2026)

Recentrage demandé : premières divisions des pays des coupes d'Europe, pas les
deuxièmes divisions des 5 grands (abandonnées). Les trois meilleurs candidats ci-dessus
entrent au niveau 2 avec ses réglages, sans rien régler sur eux. L'Écosse attend que
la base accepte plusieurs matchs par affiche et par saison (sa seconde phase).

Backtest sur les données chargées par le vrai chargeur (saison régulière seulement,
matchs sur tapis vert exclus), écart favori / outsider appris par championnat, chaque
saison sur les saisons précédentes ; test 2022-26, log loss :

| Championnat | Matchs | 1-N-2 | naïf | clôture | +2,5 | naïf | clôture | écart appris |
|---|---|---|---|---|---|---|---|---|
| Portugal | 1 224 | 0,9158 | 1,0703 | 0,8984 | 0,6741 | 0,6935 | 0,6667 | 0,10 à 0,15 |
| Belgique | 1 026 | 0,9962 | 1,0765 | 0,9873 | 0,6791 | 0,6920 | 0,6763 | 0 |
| Pays-Bas | 1 224 | 0,9515 | 1,0713 | 0,9321 | 0,6670 | 0,6743 | 0,6582 | 0 |
| Grèce | 728 | 0,9250 | 1,0822 | 0,9130 | 0,6860 | 0,6950 | 0,6812 | 0,10 |
| Turquie | 1 341 | 0,9762 | 1,0672 | 0,9459 | 0,6760 | 0,6903 | 0,6631 | 0,05 à 0,10 |
| **Niveau 2** | 5 543 | 0,9544 | 1,0725 | 0,9357 | 0,6755 | 0,6884 | 0,6676 | |

Partout mieux que la référence naïve sur les deux marchés, partout derrière les cotes
de clôture (la Turquie le plus : 0,030). Calibration du 1-N-2 : écart de 1 à 3 points
par tranche, sauf au-delà de 90 % (annoncé 92,3 %, observé 86,8 %, 68 cas). La page
Fiabilité montre ce backtest groupé pour tout championnat de niveau 2.

Calcul des pronostics : l'écart est réappris pour chaque championnat de niveau 2 à
chaque exécution (une simulation des saisons passées par championnat) : 56 s ici pour
quatre championnats, quelques minutes sur le téléphone, deux fois par jour.

## Niveau 3 : résultats seuls (fichiers « autres » de football-data, 03/10/2026)

Suisse, Norvège, Suède, Danemark, Autriche, Pologne, Roumanie : résultats et cotes de
clôture seulement (ni tirs, ni mi-temps). Modèle des buts du niveau 2 sur les buts
seuls, tous les matchs gardés (phases finales comprises). Script :
`scratchpad/study_level3.py` (hors dépôt). Test 2022-26 :

| Championnat | Matchs | Gain | Retard | +2,5 / naïf | Favoris ≥ 60 % annoncé / observé |
|---|---|---|---|---|---|
| Norvège | 966 | 0,060 | 0,029 | 0,6696 / 0,6717 | 69,2 / 66,9 |
| Autriche | 774 | 0,063 | 0,010 | 0,6973 / 0,6934 | 69,2 / 66,9 |
| Suède | 964 | 0,050 | 0,029 | 0,6849 / 0,6916 | 67,4 / 64,6 |
| Danemark | 770 | 0,045 | 0,020 | 0,6817 / 0,6847 | 66,6 / 56,8 |
| Roumanie | 1 278 | 0,040 | 0,022 | 0,6850 / 0,6874 | 67,3 / 65,4 |
| Suisse | 868 | 0,024 | 0,021 | 0,6797 / 0,6825 | 66,9 / 63,3 |
| Pologne | 1 224 | 0,017 | 0,022 | 0,6857 / 0,6936 | 66,0 / 59,8 |

Lecture : sans les tirs, le moteur reste meilleur que la référence naïve sur le 1-N-2,
mais bien moins qu'au niveau 2 ; il surestime un peu les favoris ; sur +2,5 il n'apporte
presque rien (Autriche : moins bon que la référence ; Suisse et Danemark aussi sur
2019-22). Décision : pas de niveau 3 en service. Ces championnats passeront au niveau 2
avec les statistiques de match d'API-Football (tirs, corners), après deux travaux :
plusieurs matchs par affiche et par saison (Suisse : trois tours ; Danemark, Autriche,
Roumanie : seconde phase), et un téléchargement de l'historique API-Football.

## Plusieurs rencontres d'une même affiche ; Écosse en service (03/10/2026)

La base accepte maintenant qu'une affiche revienne dans la saison (`matches.leg` : 1re,
2e, 3e rencontre par date ; migration 0019). Les phases finales belge et grecque sont
chargées, l'Écosse (deux groupes de six après 33 journées, jusqu'à trois rencontres
d'une affiche) entre au niveau 2 avec ses réglages, sans rien régler sur elle.

Backtest 2022-26 sur les données chargées par le vrai chargeur, secondes phases
comprises (log loss) :

| Championnat | Matchs | 1-N-2 | naïf | clôture | +2,5 | naïf | clôture |
|---|---|---|---|---|---|---|---|
| Portugal | 1 224 | 0,9158 | 1,0703 | 0,8984 | 0,6741 | 0,6935 | 0,6667 |
| Belgique | 1 241 | 0,9991 | 1,0779 | 0,9875 | 0,6810 | 0,6912 | 0,6759 |
| Pays-Bas | 1 224 | 0,9515 | 1,0713 | 0,9321 | 0,6670 | 0,6743 | 0,6582 |
| Grèce | 949 | 0,9437 | 1,0835 | 0,9280 | 0,6856 | 0,6963 | 0,6777 |
| Turquie | 1 341 | 0,9762 | 1,0672 | 0,9459 | 0,6760 | 0,6903 | 0,6631 |
| Écosse | 912 | 0,9444 | 1,0591 | 0,9324 | 0,6816 | 0,6919 | 0,6734 |
| **Niveau 2** | 6 891 | 0,9565 | 1,0716 | 0,9382 | 0,6770 | 0,6892 | 0,6685 |

Les matchs de seconde phase sont plus durs à prévoir. Par différence (approchée) avec la saison
régulière seule (section précédente), sur les 215 matchs de phase finale belges le
moteur est à 1,013 contre 0,988 pour la clôture (retard 0,025, contre 0,009 en saison
régulière) ; sur les 221 grecs, 1,005 contre 0,977 (retard 0,028, contre 0,012), tout en
restant meilleur que la référence naïve (1,088). Rien n'est corrigé pour l'instant
(enjeux propres à ces phases : points divisés par deux en Belgique, places européennes).
Calibration du 1-N-2 (6 891 matchs) : écart de 0 à 2 points par tranche, sauf au-delà de
90 % (annoncé 92,1 %, observé 88,3 %, 77 cas).
