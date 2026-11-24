# Bulletin de réussite réelle n° 1 — 24 novembre 2026

Ce que FootProba a réellement proposé, et ce qui s'est passé. Données lues dans l'application
(`/smart-coupons/history`, mes paris de testeur), mise fictive de 1 000 F par coupon.
Rien n'a été modifié dans le code. Bulletin suivant : chaque lundi.

## 1. Coupons du jour (publics), du 2/11 au 23/11 — 40 coupons réglés

| Profil | Coupons | Gagnés | Chance annoncée | Chance selon la cote | **Réalisé** | Bilan à 1 000 F |
|---|---|---|---|---|---|---|
| Sûr | 17 | 13 | 65 % | 65 % | **76 %** | **+3 730 F** |
| Équilibré | 8 | 5 | 42 % | 45 % | **62 %** | **+2 870 F** |
| Audacieux | 15 | 8 | 39 % | 43 % | **53 %** | **+3 100 F** |
| **Total** | **40** | **26** | | | **65 %** | **+9 700 F** (+24 % sur 40 000 F) |

Par sélection : Sûr 41 sur 46 (89 %, annoncé 85 %), Équilibré 18 sur 23 (78 %, annoncé 74 %),
Audacieux 18 sur 27 (67 %, annoncé 59 %).

**Lecture honnête** :
- **C'est un bon début** : les trois profils ont fait mieux qu'annoncé et mieux que la cote,
  et le bilan est positif.
- **Mais c'est beaucoup trop tôt pour conclure.** Sur 17 coupons Sûr annoncés à 65 %, on en
  attendait environ 11 gagnés. 13, c'est dans les limites du hasard. Avec 40 coupons, l'écart
  peut encore s'inverser. Il faut au moins 200 coupons, environ 2 mois, pour parler d'un vrai
  taux de réussite.
- **La chance annoncée est proche de celle de la cote** (65 % contre 65 %, 42 % contre 45 %,
  39 % contre 43 %). Les coupons du jour ne « battent » donc pas le bookmaker sur le papier. Ils
  ont simplement eu de bons résultats ces 3 semaines.
- **L'Équilibré manque souvent** : il n'a pas été publié 9 jours sur 14 (« missing »), et
  aucun coupon n'a été publié les 11, 18 et 19/11. À expliquer aux joueurs (« aucun coupon
  assez sûr aujourd'hui »), et à vérifier.

## 2. Mes paris de testeur, du 9/11 au 23/11 — 17 paris réglés

| Paris | Gagnés | Misé | Rendu | Bilan | Chance annoncée (moyenne) | Selon la cote | Réalisé |
|---|---|---|---|---|---|---|---|
| 17 | 11 | 32 000 F | 28 573 F | **−3 427 F (−10,7 %)** | 60 % | 54 % | 65 % |

J'ai gagné plus souvent qu'annoncé, mais j'ai perdu de l'argent. Les deux paliers de montante
perdus (5 000 F chacun) et les combinés sur les sélections nationales ont coûté plus que les
gains des paris sûrs. Les paris choisis par moi dans les grands championnats, avec un écart
de 9 points (n° 110 et 111), ont gagné tous les deux.

## 3. Battre la cote de clôture : impossible à mesurer aujourd'hui

C'est la seule vraie preuve qu'on bat le bookmaker : avoir pris une meilleure cote que celle
juste avant le coup d'envoi.
- `/matches/{id}/odds-history` ne garde l'historique que des matchs récents. Sur mes
  36 sélections, je n'ai trouvé la cote de clôture que pour 2.
- Sur ces 2 : une égale (Darmstadt 1,76) et une moins bonne (Athletic – Espanyol, moins de
  2,5 buts : pris à 2,02, clôture à 2,34). Le marché est allé **contre** le moteur, c'est
  exactement le signal d'un faux écart.

**Demande** : enregistrer systématiquement la **cote de clôture** de chaque sélection
proposée (coupons du jour, Coupon intelligent, alertes, paris des joueurs), et l'ajouter au
bilan public. Sans elle, on ne pourra jamais prouver qu'on bat le bookmaker.

## 4. Ce qu'il faut suivre chaque semaine

| Indicateur | Aujourd'hui | Objectif avant commercialisation |
|---|---|---|
| Coupons du jour réglés | 40 | ≥ 200 |
| Réalisé contre annoncé (par profil) | +11 à +20 points | à ± 3 points, ou mieux |
| Bilan à 1 000 F par coupon | +24 % | positif sur 200 coupons |
| Part des sélections qui battent la cote de clôture | non mesurable | > 50 % |
| « Bonnes affaires » affichées sans preuve | alertes et occasions encore visibles | aucune |
