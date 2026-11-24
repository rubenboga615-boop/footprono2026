# Sources de données possibles : vérification du 24/11/2026

Demande du fondateur : regarder la liste « public-apis » (GitHub) pour trouver des sources qui manquent à FootProba (actualité des clubs, des joueurs, cotes…).

## Ce que j'ai fait
- J'ai téléchargé la liste à jour (3 072 lignes) et extrait tout ce qui touche au football, aux cotes et à l'actualité.
- J'ai essayé d'appeler les API directement : **impossible depuis mon environnement** (réseau bloqué). Les chiffres ci-dessous viennent donc des pages officielles et de comparatifs trouvés par recherche web. Il faudra les tester depuis le serveur avant de décider.
- J'ai vérifié dans le code quels services d'API-Football (déjà payé) FootProba utilise.

## Constat n°1 : une partie de ce qui manque est déjà dans API-Football
| Donnée d'API-Football | Utilisée par FootProba ? |
|---|---|
| Blessures (`/injuries`) | Oui (ingestion/live.py) |
| Statistiques de match (`/fixtures/statistics`) | Oui |
| Cotes (`/odds`, `/odds/live`) | Oui |
| **Compositions officielles** (`/fixtures/lineups`, environ 1 h avant le match) | **Non** |
| **Joueurs suspendus ou absents longtemps** (`/sidelined`) | **Non** |
| **Transferts** (`/transfers`), entraîneurs (`/coachs`) | **Non** |
| **Statistiques de saison des équipes** (`/teams/statistics`) | **Non** |
| **Face-à-face** (`/fixtures/headtohead`) | **Non** |

Suggestion : avant d'ajouter une autre source, utiliser d'abord les compositions et les absences. Elles sont incluses dans l'abonnement, couvrent l'Afrique et ne coûtent que quelques requêtes. La **cote de clôture** peut aussi se garder avec `/odds` déjà utilisé, sans nouveau fournisseur.

## Constat n°2 : les nouvelles sources football intéressantes de la liste
| Source | Ce qu'elle apporte | Réserves |
|---|---|---|
| **football-data.org** | Deuxième source de scores (secours, vérification) | Gratuit : 12 compétitions européennes seulement, 10 requêtes/min, pas d'Afrique ; cotes payantes |
| **The Odds API** | Cotes de plusieurs bookmakers, CAN incluse (`soccer_africa_cup_of_nations`) | Gratuit : 500 crédits/mois (peu) ; historique des cotes réservé aux offres payantes ; pas trouvé de clé pour les éliminatoires CAF |
| **Odds-API.io** | Cotes de 450+ bookmakers | Nouvelles clés gratuites suspendues depuis le 27/08/2026 ; offre d'entrée environ 49 £/mois |
| **PlayerElo** | Niveau de chaque joueur, 176 championnats | Payant ; utile pour « force des clubs entre ligues » ; à évaluer |
| **OpenFoot API / StrikerAPI / KickoffAPI** | xG (qualité des occasions), compositions | Surtout l'Europe ; couverture Afrique non prouvée |
| **Football Charts** | Probabilités de modèle sur 93 ligues | Utile pour **comparer** notre moteur à un autre modèle |
| **Touchline Wire** | Compositions probables et blessures | Premier League seulement |

## Constat n°3 : actualité des clubs et des joueurs
La liste ne contient **aucune API d'actualité spécifique au football africain**. Les API générales (GNews, Currents, NewsData, Mediastack, TheNews) permettent de chercher « ASEC Mimosas » ou « Sébastien Haller » dans les articles. Leurs limites :
- les résultats sont en texte libre. Pour en tirer « joueur forfait », il faut une analyse automatique du texte, qui peut se tromper ;
- les offres gratuites interdisent souvent l'usage commercial.

Suggestion : pour les absences, `/injuries` + `/sidelined` + `/fixtures/lineups` d'API-Football sont plus fiables que la lecture d'articles. L'actualité pourrait servir plus tard, pour un **affichage** (« dernières nouvelles du club »), pas pour le calcul des chances.

## Météo
Open-Meteo est gratuit, sans clé, jusqu'à 10 000 appels par jour, mais **uniquement pour un usage non commercial**. Avec Premium, FootProba devrait prendre l'offre payante. L'effet de la météo sur les buts est faible, donc seulement si un test sur les anciens matchs le justifie (principe n°4).

## Ordre que je recommande
1. Compositions officielles + absences (`/fixtures/lineups`, `/sidelined`) : déjà payé, mesurer l'effet sur la réussite.
2. Garder la cote de clôture avec `/odds` (déjà payé).
3. Tester The Odds API gratuit (500 crédits) sur la CAN et les grands championnats pour la « meilleure cote ».
4. football-data.org comme source de secours pour les scores européens.
5. Actualité et météo : plus tard, pour l'affichage seulement.

Sources : football-data.org (docs.football-data.org/general/v4/policies.html), the-odds-api.com (page tarifs, historical-odds-data, africa-cup-of-nations-odds), odds-api.io (pricing/free, blog free-odds-api), open-meteo.com/en/terms, liste github.com/public-apis/public-apis.
