# Coupons du jour et fiabilité du moteur : bilan au 6 novembre 2026

Sources : `/smart-coupons/history` (tout l'historique public) et `/reliability`
(pronostics enregistrés avant les matchs, du 08/10 au 06/11/2026), lus le 06/11/2026.

## 1. Résultats des coupons du jour

| Profil | Réglés | Gagnés | Chance annoncée (moyenne) | Réussite |
|---|---|---|---|---|
| Sûr | 3 | 2 | 72 % | 67 % |
| Équilibré | 1 | 1 | 42 % | 100 % |
| Audacieux | 2 | 1 | 35 % | 50 % |
| **Total** | **6** | **4** | | |

**Rien ne peut encore en être conclu.** 9 coupons publiés depuis le 02/11, dont 6 réglés :
il faudrait une centaine de coupons par profil pour juger une chance annoncée à quelques
points près. Ces chiffres ne montrent ni un problème ni une réussite.

## 2. Incohérences dans les coupons publiés

1. **Sélection « en attente » pour toujours** (bogue). 04/11, Audacieux : « Kortrijk –
   Mechelen, buts de Mechelen moins de 1,5 » est toujours « en attente » deux jours après le
   match, alors que le même match, « moins de 2,5 », est marqué perdu dans le coupon Sûr.
   Cause (`settle_pending`, `smart_coupon.py`) : un coupon est réglé dès qu'une sélection est
   perdue (Artis Brno à 17 h), puis n'est plus jamais relu ; le match de 19 h 30 n'est donc
   jamais noté. À corriger : continuer à noter les sélections d'un coupon déjà réglé, ou
   afficher « non joué, coupon déjà perdu ».
2. **Le même match dans plusieurs profils le même jour** (3 jours sur 4) : 02/11 GAIS – AIK
   (Sûr et Équilibré), 04/11 Kortrijk – Mechelen et Artis Brno – Bohemians (Sûr et
   Audacieux), 06/11 Standard – Beveren (Sûr et Équilibré). Le 04/11, c'est presque le même
   pari à deux seuils (Mechelen moins de 2,5 dans Sûr, moins de 1,5 dans Audacieux) : un seul
   but de trop a fait perdre les deux coupons. Le joueur qui suit plusieurs profils prend un
   risque concentré sans le savoir.
3. **Les profils suivent l'avis du moteur, pas la cote.** 16 sélections sur 21 ont une
   probabilité du moteur inférieure à celle de la cote (en moyenne 3 points), et 8 coupons
   sur 9 annoncent moins que leur cote. Exemple : 02/11 Équilibré, « GAIS – AIK plus de 1,5
   but » à **1,14** : 75 % selon le moteur (donc « Équilibré »), 88 % selon la cote. Le
   joueur voit une sélection à 1,14 dans un profil censé être « équilibré ».
4. **Très peu de grands championnats** : 4 sélections sur 21 viennent des 5 grands
   championnats. Or l'audit de tous les marchés (« règle des 3 points ») n'a été fait que
   sur ces 5 championnats. Les autres (Suède, Roumanie, Pologne, Tchéquie, Belgique,
   Croatie, Danemark, Turquie) n'ont pas cet audit par marché.
5. **Surtout des totaux de buts** : 14 sélections sur 21 (plus/moins de buts, buts d'une
   équipe, mi-temps). C'est justement le marché où le moteur est le plus faible en
   conditions réelles (voir 3).
6. **Jours sans coupon** : 03/11, seulement Sûr ; 05/11, aucun coupon. Probablement aucune
   sélection qui respecte les règles (cote minimale 2,00 pour Équilibré et Audacieux),
   mais l'écran n'en dit rien. Le rapport de la tâche (console) donne la raison exacte.
7. Détail : sur l'écran d'un jour passé, « Hier » se rapporte à aujourd'hui, pas à la veille
   du jour affiché.

## 3. Fiabilité du moteur en conditions réelles (379 matchs)

| Marché | Moteur | Référence naïve | Cotes de clôture (225 matchs) |
|---|---|---|---|
| Résultat 1-N-2 (log loss) | 0,962 | 1,035 | 0,931 (moteur 0,941) |
| Plus/moins de 2,5 buts | 0,666 | 0,668 | 0,639 (moteur 0,663) |
| Les deux marquent (105 matchs) | 0,679 | **0,660** | |

- **1-N-2 : bon.** Nettement meilleur que la référence naïve, un peu moins bon que les cotes
  de clôture (attendu, voir l'audit du handicap asiatique).
- **Plus/moins de 2,5 buts : à peine mieux que la référence naïve**, et nettement moins bon
  que les cotes. Les totaux de buts, qui remplissent les coupons du jour, sont donc le point
  faible en réel. 61 % des matchs ont fini à plus de 2,5 buts sur la période.
- **Les deux marquent : moins bon que la référence naïve** (échantillon encore petit).
- **Calibration 1-N-2 hors de la règle des 3 points** : annoncé 40 à 50 %, arrivé **57 %**
  (129 cas, 13 points d'écart) ; annoncé 60 à 70 %, arrivé 72 % (50 cas). Le moteur est
  trop prudent sur les favoris en ce moment. À surveiller ; recalibrer si cela dure.
- **Par championnat** (10 à 27 matchs chacun, trop peu pour conclure) : moins bon que la
  référence naïve en Autriche, Croatie, Tchéquie, Grèce, Pays-Bas, Portugal et Suisse, et
  à égalité en Écosse et en Serie A.

## 4. Recommandations

1. Corriger le règlement des sélections restées « en attente » (bogue 2.1).
2. Coupons du jour : un match ne sert qu'à un seul profil par jour.
3. Limiter les coupons du jour aux championnats et marchés dont la fiabilité est
   démontrée (audit par marché étendu aux championnats de niveau 2), ou l'indiquer
   sur la sélection.
4. Surveiller les totaux de buts et la calibration 1-N-2 chaque semaine ; ne rien changer
   au moteur avant au moins 200 matchs supplémentaires.
5. Dire pourquoi il n'y a pas de coupon un jour donné (« aucune sélection ne respecte
   les règles du profil aujourd'hui »).
