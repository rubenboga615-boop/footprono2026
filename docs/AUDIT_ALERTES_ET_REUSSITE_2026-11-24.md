# Alertes de cote, « occasions » et taux de réussite — 24 novembre 2026

Demande du fondateur (24/11) : avis sincère sur « Mes alertes de cote », puis réfléchir à ce
qui manque pour que FootProba ait un vrai taux de réussite avant d'être commercialisé.
Rien n'a été modifié dans le code.

## 1. Verdict : en l'état, la page fait plus de mal que de bien

Captures du fondateur (24/11, 08:27) :
- une vingtaine d'alertes en 2 jours (alerte « tous les championnats, écart de 8 points ») ;
- 78 notifications non lues ;
- un gros bouton « Ajouter au coupon » sur chaque carte.

| Alerte | Moteur | Selon la cote | Écart |
|---|---|---|---|
| Club Brugge – Liverpool, victoire de Bruges (4,72) | 50 % | 21 % | +29 |
| Atlético Madrid – Viking, nul ou Viking (7,90) | 38 % | 13 % | +25 |
| Sporting – Manchester United, victoire du Sporting (2,56) | 62 % | 39 % | +23 |
| Lille – Bayern, victoire du Bayern (1,65) | 82 % | 61 % | +22 |
| Sabah – Barcelone, moins de 1,5 but à la mi-temps (2,80) | 54 % | 36 % | +18 |
| Slavia Prague – Villarreal, victoire de Slavia (3,21) | 49 % | 31 % | +17 |
| Paris SG – Roma, victoire du PSG (1,45) | 85 % | 69 % | +16 |

## 2. Ce que disent nos propres règles et nos propres mesures

**`docs/PRINCIPES.md`, principe n° 4** : « Aucune “value” n'est affichée sans backtest
démontrant un résultat positif avec intervalle de confiance. »

**`docs/MOTEUR.md`, handicap asiatique face aux cotes (7 081 matchs, 2022-2026)** : quand le
modèle croit tenir une value, le rendement est **négatif**, et plus il y croit, plus on perd :

| Le modèle croit à une espérance | Paris | Rendement |
|---|---|---|
| > 0 % | 5 914 | −3,5 % |
| > 5 % | 3 625 | −4,8 % |
| > 10 % | 2 043 | −6,3 % |

> « Ces écarts sont surtout ses propres erreurs (il ignore compositions, blessures,
> informations de dernière minute). Plus le modèle croit tenir une “value”, plus on perd. »
> (`MOTEUR.md`)

**Sélections nationales (mesure du 18/11, 92 matchs)** : avec des écarts de +5 à +15 points,
21 % et 33 % de réussite, −11 640 F pour 1 000 F par pari.

**Conclusion** : les alertes de cote, les « occasions » du tableau de bord et la pastille
« ▲ au-dessus de la cote » présentée comme une bonne affaire **contredisent le principe n° 4
et nos mesures.** Un grand écart entre le moteur et le bookmaker signifie presque toujours
que le moteur ne sait pas quelque chose (blessure, composition, niveau réel d'une équipe d'un
autre championnat), pas que le bookmaker se trompe.

**Ma part** : l'alerte de cote, les « occasions » et la pastille ▲ venaient de mes maquettes du
20/11 (`docs/maquettes/12-nouveau-visage/`, écrans 4, 29 et 35). Je les retire comme
« bonnes affaires ». La pastille ne doit servir que dans un sens : **prévenir** quand le
moteur est plus optimiste que le marché, parce qu'alors la vraie chance est probablement plus
proche de celle du marché.

## 3. Demandes au développement

1. **Tout de suite** :
   - cacher aux joueurs la page « Mes alertes de cote », ses notifications et le bloc
     « Occasions » du tableau de bord ;
   - dans le Coupon intelligent, les coupons du jour et le coupon en direct, ne plus jamais
     présenter « moteur au-dessus de la cote » comme un argument pour jouer.
2. **Mesurer en silence** : continuer à calculer les alertes et les occasions sans les montrer.
   Enregistrer pour chacune la cote, la chance du moteur, la chance selon la cote, la cote de
   clôture et le résultat. Faire le bilan à 1 000 F par alerte, par tranche d'écart, par
   compétition et par marché.
3. **Ne rouvrir que sur preuve** (principe n° 4) : sur au moins 300 alertes réglées, un
   rendement positif avec intervalle de confiance, et une **cote de clôture battue** en
   moyenne. Même dans ce cas :
   - écart limité à environ 3-10 points ;
   - seulement les compétitions validées ;
   - au plus 3 alertes par jour ;
   - « Voir le match » au lieu de « Ajouter au coupon » ;
   - fonction désactivée par défaut ;
   - le bilan réel affiché en tête de page.
4. **Ce qui aide vraiment le joueur dès maintenant**, sans prétendre battre le bookmaker :
   - **la chance la plus juste** : afficher par défaut la chance tirée de la cote (sans
     marge), ou un mélange moteur + cote si une étude montre qu'il est mieux calibré que
     chacun des deux seuls ;
   - **la meilleure cote disponible** (1xBet, Bet365, Betclic…) : c'est le seul avantage
     certain et mesurable ;
   - **éviter les mauvais paris** : marges élevées, combinés trop longs, marchés où le
     moteur est mal calibré ;
   - **la gestion de la mise** (plan de jeu), qui protège déjà le joueur.

## 4. Ce qui manque pour améliorer les pronostics (à discuter avec le fondateur)

Le moteur ne connaît que les résultats passés, les xG, le calendrier et le terrain. Le
marché, lui, sait beaucoup plus de choses. Ce qui nous manque, du plus utile au moins utile :

| Donnée manquante | Pourquoi elle compte | Où la trouver | Déjà là ? |
|---|---|---|---|
| **Compositions et absences** (blessés, suspendus, titulaires) | c'est la principale raison pour laquelle le marché nous bat | API-Football (compositions, blessures) | collectées depuis le 10/11, étude prévue début 2027 |
| **Niveau des équipes entre championnats** (coupes d'Europe) | Bruges, Viking, Sabah… comparés à tort aux grands clubs | Elo des clubs (par exemple clubelo), coefficient UEFA, valeur des effectifs | non |
| **Niveau réel des sélections** (où jouent les joueurs) | les sélections sont mal évaluées par le seul Elo des résultats | Elo des sélections, effectifs convoqués | partiel |
| **Mouvement des cotes** (ouverture → clôture, plusieurs bookmakers) | une cote qui baisse fortement signale une information (blessure, composition) | historique des cotes, référence Pinnacle | partiel (relevés toutes les 3 h) |
| **xG de tous les championnats** | seuls 5 championnats ont les xG Understat | xG « maison » à partir des tirs (déjà fait pour certains), API-Football | partiel |
| **Rotation, fatigue, coupes en semaine** | les clubs européens font tourner leur effectif | calendrier (déjà), compositions | partiel (« repos » testé, rejeté seul) |
| **Changement d'entraîneur, crise, motivation** | effet réel mais difficile à mesurer | actualités | non |
| **Météo, terrain, altitude, voyages** | surtout pour l'Afrique (CAN) | services météo, lieux des matchs | non |
| **Statistiques du direct** (tirs, xG du match) | pour le coupon en direct | API-Football (déjà affiché) | à enregistrer |

**Question de fond pour le fondateur** : « faire gagner l'utilisateur » contre un bookmaker
qui prend une marge est très difficile, même pour des professionnels. La promesse réaliste,
et vérifiable, est la suivante :
- donner la chance la plus juste possible ;
- aider à choisir les paris les moins mauvais et la meilleure cote ;
- protéger la bankroll du joueur.

Pour viser un vrai « taux de réussite », il faut d'abord fixer une mesure honnête : battre
la cote de clôture, et un bilan positif sur plusieurs centaines de paris. Il faut ensuite
ajouter en priorité les compositions et absences, et le niveau des équipes entre
championnats.
