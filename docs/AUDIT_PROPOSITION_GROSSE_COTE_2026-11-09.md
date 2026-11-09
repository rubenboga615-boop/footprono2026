# Proposition : encadrer le profil « Grosse cote » — 9 novembre 2026

Décision du fondateur (9/11) : garder le profil Grosse cote, mais l'encadrer. Ce rapport
décrit les changements à faire ; rien n'a été modifié dans le code.

## 1. Pourquoi

- **Le moteur n'est pas en cause.** « Mon bilan » du fondateur (48 paris) : les chances par
  sélection sont justes (annoncé 60 % → 58 %, 75 % → 76 %, 85 % → 91 %). Les coupons à
  cote 5 et plus perdent **comme annoncé** : 1 gagné sur 13 pour environ 11 % annoncé ;
  0 sur 4 au-delà de 20 (2 % annoncé). Échantillon petit : 17 coupons.
- **La marge du bookmaker se multiplie.** Avec environ 7 % de marge par sélection
  (hypothèse, à vérifier sur les cotes 1xBet relevées), ce qu'un joueur récupère en moyenne
  pour 1 000 F misés baisse vite avec le nombre de sélections :

  | Cote du coupon | Sélections (environ) | Récupéré en moyenne pour 1 000 F |
  |---|---|---|
  | 2 à 3 | 2 à 3 | 800 à 850 F |
  | 10 | 7 à 8 | environ 600 F |
  | 25 et plus | 10 à 12 | 400 à 500 F |

- **Bilan du fondateur par cote** : moins de 2 : **+64 526 F** ; 2 à 5 : +16 467 F ;
  5 à 20 : −87 804 F ; 20 et plus : −13 000 F. Toutes les pertes viennent des grosses cotes.
- Retirer le profil ou le limiter à 5 le ferait disparaître (Audacieux donne déjà environ
  3,6), et les joueurs feraient leurs grands combinés sur 1xBet sans aucune information.

## 2. Changements demandés

| # | Changement | Où (repères) | Comment le vérifier |
|---|---|---|---|
| 1 | **Cote visée de 2 à 10** au lieu de 2 à 1000 | serveur : `TARGET_MIN, TARGET_MAX` dans `bookmaker/smart_coupon.py` (ligne 86) ; application : `targets = [10, 25, 50, 100]` et le message « entre 2 et 1000 » dans `smart_coupon_screen.dart` | `/smart-coupon?profile=grosse&target_odds=25` refusé avec un message clair ; boutons proposés : par exemple **5 · 7 · 10 · Autre** ; « Autre » refuse 12 avec « Écris une cote entre 2 et 10 » |
| 2 | **Phrase de vérité** en haut de chaque coupon Grosse cote | résultat du Coupon intelligent, partage en image, coupon | ex. « **Environ 1 coupon sur 10 passe.** Sur 10 coupons de 1 000 F comme celui-ci, tu récupères en moyenne environ 6 000 F. » (calculé à partir de la chance du moteur et de la cote, pas un chiffre fixe) |
| 3 | **Mise proposée plus petite** pour un coupon Grosse cote | écran Mon coupon, quand le coupon vient du profil Grosse cote | mise par défaut 500 F au lieu de 1 000 F (à décider par le fondateur) |
| 4 | **Vitrine Premium sur Sûr et Équilibré** | écran Coupon intelligent verrouillé, Passer Premium, accueil | l'exemple affiché n'est jamais un coupon Grosse cote |
| 5 | **Suivi** dans l'Observatoire | « Par cote du coupon » existe déjà dans Mon bilan | ajouter la même répartition (moins de 2 / 2 à 5 / 5 à 10) à l'Observatoire bêta |

Les comptes qui ont déjà un coupon Grosse cote au-delà de 10 dans leurs paris ne sont pas
touchés : seul le choix d'un nouveau coupon change.

## 3. Ce que le testeur vérifiera après publication

- cote visée maximale 10 (boutons, « Autre », appel direct au serveur) ;
- phrase de vérité visible sur le résultat, dans le coupon et sur l'image partagée ;
- mise proposée ;
- exemple de la vitrine Premium ;
- dans un mois : bilan par cote dans l'Observatoire, pour décider s'il faut descendre à 5
  ou retirer le profil.
