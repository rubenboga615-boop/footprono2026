# Vérification des corrections du 17/11 — 18 novembre 2026, 05 h GMT

Commits relus : `41487f6` (retour du testeur), `a33ef73` (Coupon intelligent gardé),
`3c31835` (paiement), `99c0ea0` (Mon bilan : annoncé contre réalisé). Rien n'a été modifié
dans le code.

## Ce qui est en ligne

| Point | Vérification | Verdict |
|---|---|---|
| Serveur à jour | les nouvelles réponses de l'API sont là (voir ci-dessous) | oui |
| **Version web** | `main.dart.js` du **17/11 à 02:22**, donc **avant** `41487f6`, `a33ef73`, `3c31835` et `99c0ea0` | **à publier** |
| Montante terminée | `GET /montantes/8/suggestions` → 400 « montante terminée : plus de pari possible, crée une nouvelle montante » | conforme |
| Mon bilan | `/me/record` renvoie `announced` | conforme (écran : après publication du web) |
| Fiabilité, sélections nationales | `/reliability` renvoie `nations_vs_odds` | conforme (écran : après publication du web) |
| « Rep. Of Ireland » | aucune équipe irlandaise dans les matchs à venir en ce moment | à revoir au prochain match de l'Irlande |
| Gain exact | paris 89 (3 836 F) et 105 (1 995 F) payés exactement le gain annoncé, mais leurs cotes ne demandaient pas d'arrondi | à revoir sur un combiné à cote arrondie |
| 90+X' | aucun but dans le temps additionnel dans mes matchs | à revoir |

**Paris réglés cette nuit** : n° 89 gagné (3 836 F ; Bosnie-Herzégovine 2-1 Roumanie) et
n° 105 gagné (1 995 F ; Ukraine 1-0 Géorgie). Les notifications 🟢, ⚽ (perdante, puis
gagnante pour l'instant) et les gains sont toutes conformes.

## Constat important : la nouvelle mesure des sélections nationales

C'est la première fois qu'on peut lire la mesure demandée le 16/11. Sur 92 matchs de
sélections (résultat du match, mise de 1 000 F par sélection) :

| Le moteur dépasse la cote de… | Sélections | Moteur annonçait | Cote annonçait | **Gagné en vrai** | Bilan à 1 000 F |
|---|---|---|---|---|---|
| +5 à +10 points | 14 | 47 % | 40 % | **21 %** | **−9 030 F** |
| +10 à +15 points | 15 | 50 % | 38 % | **33 %** | **−2 610 F** |
| +15 points et plus | 18 | 62 % | 41 % | **50 %** | **+8 620 F** |

**Lecture simple** :
- Quand le moteur des sélections dépasse la cote de 5 à 15 points, il se trompe : ces
  paris gagnent **moins souvent que ce que disait même le bookmaker**, et ils perdent de
  l'argent.
- Au-delà de 15 points, ils ont gagné plus souvent que la cote ne le disait, mais sur 18
  sélections seulement, ce qui peut être de la chance (Tunisie – Libye en fait partie).
- Partout, le moteur annonce bien plus que ce qui arrive vraiment : 47 % contre 21 %,
  50 % contre 33 %, 62 % contre 50 %. **Le moteur des sélections est trop sûr de lui face
  au marché.**

**Suggestions** :
1. Tant que la mesure n'a pas au moins 100 sélections par tranche, ne pas présenter un
   écart moteur > cote sur un match de sélections comme une « bonne affaire ». Afficher
   plutôt : « sur les sélections, le moteur surestime souvent ses chances ».
2. Dans le Coupon intelligent et les coupons du jour, pour les sélections nationales,
   rapprocher la chance du moteur de celle de la cote (par exemple la moyenne des deux),
   ou en tout cas ne pas classer les coupons sur cet écart.
3. Refaire cette mesure sur tous les marchés des sélections (buts, handicaps), pas
   seulement le résultat du match : la plupart de mes coupons portaient sur ces marchés.
