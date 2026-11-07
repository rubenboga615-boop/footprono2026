# Proposition : des coupons différents d'un joueur à l'autre — 7 novembre 2026

Question du fondateur (7/11, après la comparaison `AUDIT_COMPARAISON_COUPONS_2026-11-07.md`) :
avec 1 000 joueurs, si 500 à 800 reçoivent le même coupon, une mauvaise série fait perdre
presque tout le monde en même temps, ce qui peut décourager. Faut-il des coupons
différents ? Rien n'a été modifié dans le code.

## 1. Ce que change un coupon identique pour tous

Proposer des coupons différents **ne fait pas gagner plus en moyenne** : chaque joueur garde
à peu près la même chance. Ce qui change, c'est que les joueurs **ne perdent plus tous le
même jour**.

Exemple avec le coupon Sûr (63 % de chances) :

| | Même coupon pour tous | Coupons différents (peu de matchs en commun) |
|---|---|---|
| Un jour perdu | 37 % des jours, **les 1 000 perdent** | chaque jour, environ 370 perdent et 630 gagnent |
| 3 jours perdus de suite | environ 5 % des séries de 3 jours : **tout le monde** perd 3 fois de suite | environ 50 joueurs sur 1 000 vivent cette série, pas les mêmes à chaque fois |
| Ce qu'on lit dans les groupes WhatsApp | « FootProba a tout raté aujourd'hui » | des gagnants et des perdants chaque jour |

Autres risques d'un coupon unique :
- les 1 000 paris arrivent sur la même sélection chez 1xBet : la cote peut baisser vite, et
  1xBet peut limiter ce pari ;
- l'image partagée vaut pour tout le monde : le coupon n'a plus rien de personnel.

## 2. La limite à respecter

Varier ne doit **jamais** vouloir dire donner un moins bon coupon à certains joueurs sans
le leur dire. Ne garder que des combinaisons **presque aussi bonnes** que la meilleure, par
exemple :
- chance du moteur au moins égale à 95 % de celle du meilleur coupon (63 % → 60 % au moins) ;
- cote dans la fourchette demandée (Grosse cote 10 : entre 9,5 et 11) ;
- mêmes règles de profil (chance minimale par sélection, marchés vérifiés).

Les jours où il y a peu de matchs, il y aura peu de combinaisons valables : les coupons se
ressembleront davantage, et c'est normal.

## 3. Proposition

1. **Plusieurs bons coupons au lieu d'un seul** : pour chaque demande, le moteur garde les
   10 à 20 meilleures combinaisons qui respectent la règle du point 2.
2. **Chaque joueur reçoit toujours le même coupon dans la journée** : le choix dépend du
   joueur et du jour (pas d'un tirage à chaque ouverture). S'il rouvre l'écran, il retrouve
   son coupon.
3. **Personne n'est trop exposé sur une seule sélection** : une même sélection ne doit pas
   apparaître dans plus d'environ un tiers des coupons distribués ce jour-là.
4. **Bouton « Un autre coupon »** : montre la combinaison suivante, avec sa chance (« 61 %
   au lieu de 63 % »), pour que le joueur choisisse en connaissance de cause.
5. **Le dire simplement** : « Ton coupon est composé pour toi parmi les meilleurs du jour.
   Les autres joueurs reçoivent des coupons proches, pas forcément les mêmes. »

## 3 bis. Quelle partie de l'application est concernée

| | Coupon intelligent | Coupons du jour |
|---|---|---|
| Qui le compose | chaque joueur (profil, cote visée, jours, exclusions) | le moteur, une fois par jour, 3 coupons publiés avec un code 1xBet saisi par le fondateur |
| Aujourd'hui | le même pour tous à la même minute (comparaison du 7/11 : 8 coupons sur 8 identiques) | le même pour tous, par principe |
| Proposition | **oui, varier d'un joueur à l'autre** (points 1 à 5 ci-dessus) | **les garder uniques pour l'instant** |
| Travail en plus pour le fondateur | aucun | aucun ; avec 2 versions par profil, il faudrait saisir 6 codes par jour au lieu de 3 |

**Coupons du jour** : le risque y est encore plus fort (tous ceux qui les suivent gagnent ou
perdent ensemble), mais c'est leur principe et le bilan affiché (« 4 gagnés sur 9 ») le
montre honnêtement. Deux choix :
1. **les garder uniques** et l'assumer (conseillé pour l'instant) ;
2. **publier 2 versions par profil** (« Sûr A » et « Sûr B », sans match en commun), à
   envisager seulement quand beaucoup de joueurs les suivront.

**Ordre conseillé** : d'abord le Coupon intelligent ; les Coupons du jour plus tard, selon
le nombre de joueurs qui les suivent.

## 4. À vérifier avant de lancer

- **Sur les jours passés** : simuler 1 000 joueurs et comparer, jour par jour, la part des
  joueurs qui perdent (même coupon contre coupons variés). La chance moyenne doit rester la
  même, à un point près.
- **Dans l'Observatoire** : suivre chaque jour la part des joueurs qui ont perdu et la
  sélection la plus jouée.
- **Ne pas présenter cela comme un moyen de gagner plus.** Le but est d'éviter que tout le
  monde perde en même temps, pas d'augmenter les gains.

## 5. Avis

Utile et pas trop difficile. Le moteur classe déjà les combinaisons : il suffit d'en garder
plusieurs au lieu d'une. Ce n'est pas urgent à 1 testeur, mais il faut le faire **avant**
d'avoir beaucoup de joueurs Premium : un jour où « tout le monde a perdu » sur les réseaux
coûte plus cher que n'importe quelle mauvaise série individuelle.
