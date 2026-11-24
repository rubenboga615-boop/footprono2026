# Coupon manuel du testeur : méthode « la cote d'abord » (depuis le 24/11/2026)

Demande du fondateur (24/11) : chaque jour, le testeur compose lui-même un coupon, avec sa propre méthode, pour comparer avec les coupons du jour et les Coupons intelligents. Argent fictif, compte de test Premium.

## Pourquoi cette méthode
Les études du développeur (docs/ETUDE_MOTEUR_V3_2026-11-15.md, MOTEUR.md « Mélange moteur + marché ») montrent :
- la cote du bookmaker, marge retirée par la **méthode puissance**, prévoit mieux que le moteur ;
- choisir les sélections selon la cote : 79 % de réussite contre 76 % selon le moteur ; un coupon de 3 passe 50 fois sur 100 contre 44 ;
- les favoris sous 1,70 sont les seules cotes proches de l'équilibre ; au-delà de 3,50, les pertes sont structurelles.

C'est exactement l'idée mise en attente par le fondateur jusqu'au 18/12 : ce coupon manuel sert de **test en conditions réelles**, sans rien changer dans l'application.

## Règles
1. **Matchs** : championnats européens suivis par FootProba, coup d'envoi dans 2 à 36 h. Pas de coupes d'Europe ni de sélections nationales (non mesurées).
2. **Marchés** : 1X2, double chance, plus/moins 2,5 buts (les seuls étudiés).
3. **Chance de référence** = celle de la cote, marge retirée par la méthode puissance (double chance tirée du 1X2).
4. **Filtre** : cote de 1,25 à 1,70 ; chance du marché ≥ 60 % ; moteur pas plus de 3 points sous le marché (désaccord = on évite) et pas plus de 10 points au-dessus (optimisme suspect).
5. **Coupon** : 2 ou 3 sélections, un seul pari par match, championnats différents si possible, cote totale de 1,80 à 3,00. Rangement par chance du marché.
6. **Mise fixe** : 2 000 F (1 000 F si le solde passe sous 80 000 F). Pas de rattrapage après une perte.
7. **On ne force pas** : pas assez de sélections → pas de coupon ce jour-là, et on le note.

## Suivi
Pour chaque coupon : réussite, gain, chance annoncée (marché) contre réalisé, cote obtenue contre cote de clôture (nouveauté `a060f37`). Comparaison chaque lundi dans le bulletin de réussite avec le coupon du jour et les Coupons intelligents. Rien n'est concluant avant environ 100 coupons : c'est une observation, pas une preuve.

Outil : `docs/outils-testeur/coupon-manuel.mjs` (lecture seule de l'API publique, puis `POST /bets` avec `--place`).

## Journal
| Date | Pari | Sélections | Cote | Chance (marché) | Mise | Résultat |
|---|---|---|---|---|---|---|
| 24/11 | n° 133 | Bolton – West Brom double chance 12 @1,26 · Radnicki Niš – Železničar Pančevo 12 @1,30 · Burnley – Birmingham 12 @1,27 | 2,08 | 40 % | 2 000 F | en cours |
