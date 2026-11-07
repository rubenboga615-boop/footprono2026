# Coupon intelligent : toutes les actions essayées — 7 novembre 2026

Serveur `b364d55`, application version 142, compte Premium **+225 07 84 89 71 95**,
téléphone émulé (Pixel 7). Pour chaque action, j'ai relevé la requête envoyée au serveur
et le coupon reçu, afin de comparer les coupons avant et après chaque action. Rien n'a été
modifié dans le code.

## Résumé

| Action | Résultat |
|---|---|
| Profils Sûr / Équilibré / Audacieux / Grosse cote | fonctionnent |
| Nombre de sélections 1 à 12 (« Plus de réglages ») | fonctionne |
| Remplacer une sélection | **fonctionne bien** : les 9 autres sont gardées |
| Exclure un match (« Seulement ce match ») | fonctionne, même effet que Remplacer |
| Exclure une équipe (« Toujours exclure … ») | fonctionne ; gardé d'une demande à l'autre |
| Retirer une exclusion (croix des pastilles) | fonctionne au toucher |
| Heure (après 18 h) | respectée (aucun match avant 18 h) |
| Championnat (Premier League seule) | respecté ; message clair s'il manque des matchs |
| Périodes (Aujourd'hui, Demain, 3 jours, Week-end, 7 jours, Un seul jour, Plusieurs jours) | fonctionnent ; **3 jours, Week-end et 7 jours donnent le même coupon** |
| Cote visée « Autre… » | fonctionne (7 → 7,87 ; 12,5 → 14,39) ; **valeur invalide refusée sans message** |
| Grosse cote impossible (100 en 3 sélections) | message clair, avec quoi changer |
| Partager en image | **bien** ; manquent la date et un lien vers l'application |
| Ajouter au coupon (10 sélections) | 6,1 s, « 10 sélections ajoutées au coupon » |
| Ajouter un « autre choix » | « 1 sélection ajoutée au coupon » |
| Onglet Coupon : Retirer, Vider | fonctionnent (10 → 9, puis coupon vide) |

Durée de chaque calcul vue dans l'application : **3 à 4,5 s** (serveur 1 à 2 s).

## 1. Ton cas : un coupon de 10, puis retirer ou remplacer un événement

| Étape | Coupon reçu |
|---|---|
| Équilibré, 10 sélections, Prochaine journée | 10 sélections, cote **11,42**, moteur 5,6 % (« 1 chance sur 18 ») |
| « Remplacer » la 3e (Olympiakos – PAOK) | 10 sélections, cote 12,40 ; **9 gardées**, 1 nouvelle ; pastille « 1 match écarté » |
| « Exclure » la 1re → « Seulement ce match » | 10 sélections, cote 10,72 ; 9 gardées, 1 nouvelle |
| « Exclure » → « Toujours exclure Novi Pazar » | 10 sélections, cote 10,39 ; 9 gardées, 1 nouvelle ; pastille « Novi Pazar ✕ » |

**Ce qui marche bien** : Remplacer et Exclure ne refont pas tout le coupon, ils changent
seulement l'événement visé. Le choix « Seulement ce match / Toujours exclure l'équipe A /
Toujours exclure l'équipe B » est clair.

**Ce qui n'est pas clair pour un joueur :**
1. **On ne peut pas simplement retirer un événement** (garder un coupon de 9). « Remplacer »
   et « Exclure » remettent toujours un autre match à la place, puisque le nombre de
   sélections est fixé à 10. Pour retirer vraiment, il faut : ajouter tout le coupon,
   aller dans l'onglet Coupon, puis toucher « Retirer ». Personne ne le devine.
   **Piste** : un 3e choix dans la fenêtre « Exclure » : « **Retirer sans remplacer** »
   (coupon de 9).
2. **Remplacer et Exclure → Seulement ce match font exactement la même chose**. Deux
   boutons pour une seule action. **Piste** : garder un seul bouton « Changer » avec les
   choix (remplacer / retirer / exclure l'équipe pour toujours).
3. **La même croix ✕ a deux sens** : sur une sélection, elle ouvre « Exclure » ; sur une
   pastille d'exclusion, elle retire l'exclusion. À côté de chaque sélection, l'icône ↻
   (Remplacer) et la croix ne disent rien sans libellé.
4. **Les exclusions ne s'affichent que dans « Plus de réglages »**, et elles sont gardées
   d'un coupon à l'autre (même en changeant de profil ou de période ; l'équipe exclue est
   gardée sur le téléphone). Un joueur qui a exclu une équipe un jour l'oubliera, et ses
   coupons l'ignoreront sans qu'il le voie. **Piste** : afficher les exclusions actives
   au-dessus de « Composer le coupon », même réglages fermés (« 2 exclusions · voir »).
5. La 1re et la 3e sélection d'origine (Novi Pazar – Mladost, Olympiakos – PAOK) sont des
   championnats serbe et grec : pour un joueur ivoirien, « Exclure » sert surtout à retirer
   les championnats qu'il ne connaît pas. **Piste** : proposer aussi « Toujours exclure ce
   championnat ».

## 2. Contenu des coupons proposés

18 coupons reçus pendant l'essai, analysés :
- **aucune équipe en double**, filtres d'heure et de championnat respectés ;
- **Équilibré : toutes les sélections sont à 75 %** (le haut de la tranche « 60 à 75 % »),
  dans les 13 coupons Équilibré. La règle prend « la plus probable de la tranche » : la
  tranche affichée « 60 à 75 % » ne correspond donc pas à ce que le joueur reçoit.
  **Piste** : afficher « environ 75 % chacune », ou viser le milieu de la tranche comme le
  fait déjà le profil Sûr.
- **Le moteur est nettement plus pessimiste que la cote** sur ces coupons : Équilibré 10,
  après 18 h : 5,4 % selon le moteur, **13,7 %** selon la cote ; Équilibré 10 « Aujourd'hui » :
  5,5 % contre 11,8 %. Le joueur lit « le moteur donne moins de chances que le
  bookmaker » sur un coupon que le moteur lui propose : c'est déroutant.
- **3 jours, Ce week-end et 7 jours donnent le même coupon** que « Prochaine journée »
  (cote 10,39, matchs du samedi et du dimanche seulement) : toutes les sélections étant à
  75 %, l'égalité est départagée par l'heure du match, donc les premiers matchs gagnent.
  « 7 jours » ne sert à rien. **Piste** : le dire (« les matchs les plus proches sont
  choisis à chance égale ») ou mieux répartir.
- **Sûr, 12 sélections** : cote 5,65 (« 1 chance sur 6 »), **aucun match des 5 grands
  championnats**, 6 « plus/moins de buts » sur 12 (surtout « moins de 4,5 buts »).
- **Audacieux, 1 sélection** : « Inter ou nul »… sous l'étiquette « Audacieux 45 à 60 % »,
  alors que la sélection est à 60 % (le plafond).
- **Grosse cote 50** (valeur par défaut) : 9 sélections, cote **55,96**, moteur 1,0 %
  (« 1 chance sur 100 »), dépassement +12 %. Cote visée 7 → 7,87 ; 12,5 → 14,39 (+15 %).

## 3. « Autre… » (cote visée personnalisée)

| Saisie | Résultat |
|---|---|
| 7 | pastille « Autre : 7,0 », coupon 8 sélections, cote 7,87 |
| 15 | « Autre : 15,0 » |
| 12,5 | « Autre : 12,5 », coupon 11 sélections, cote 14,39 |
| **1,5**, **0**, **2000**, **abc** | la fenêtre se ferme, **l'ancienne valeur reste, aucun message** |

**Piste** : laisser la fenêtre ouverte avec « Entre 2 et 1000 » en rouge. Autres détails :
le champ s'ouvre avec « 50 » qu'il faut effacer ; « Autre : 7,0 » au lieu de « 7 ».

## 4. Périodes « Un seul jour » et « Plusieurs jours »

- **Un seul jour** : une rangée de jours s'affiche (« Jour : Sam. 7 nov., Dim. 8 nov., … »),
  le lendemain est choisi par défaut. Fonctionne.
- **Plusieurs jours** : « Du … » puis « Au … » ; par défaut **du 8 au 8 novembre**, soit un
  seul jour. **Piste** : proposer par défaut « du jour J au jour J+2 ».
- Le titre de la période reçue (« Prochaine journée », « 7 prochains jours ») n'est pas
  rappelé au-dessus du coupon : après plusieurs essais, on ne sait plus quel réglage a
  donné quel coupon.

## 5. Ajouter au coupon, puis modifier dans l'onglet Coupon

| Action | Résultat |
|---|---|
| « Ajouter au coupon » (10 sélections) | 6,1 s ; « 10 sélections ajoutées au coupon (onglet Coupon) » |
| « + » d'un « autre choix (moins sûrs) » | « 1 sélection ajoutée au coupon (onglet Coupon) » |
| Onglet Coupon → « Retirer » sur la 3e | 10 → 9 sélections, cote recalculée |
| « Vider » | coupon vide aussitôt, **sans confirmation** |

- **« Vider » efface 10 sélections sans demander confirmation** (et sans « Annuler »).
  **Piste** : confirmation, ou un message « Coupon vidé · Annuler » pendant quelques secondes.
- Après l'ajout, l'application reste sur le Coupon intelligent : il faut trouver soi-même
  l'onglet Coupon (le message le dit). **Piste** : un bouton « Voir mon coupon » dans le
  message.
- Rappel : dans l'onglet Coupon, « 1 chance sur 1 » pour un pari à 75 % (rapport UX du
  7/11, 8.1).

## 6. Partager en image

Fenêtre « Partager le coupon » : FootProba, profil, 10 sélections avec cote et chance,
cote totale, chances du moteur, mention « argent fictif ». **Réussi.**
**Pistes** : ajouter la **date et l'heure** des matchs, et un **lien ou un QR code** vers
FootProba (le partage sur WhatsApp est le meilleur moyen de faire venir des joueurs) ;
ajouter le **code 1xBet** quand il existe.

## 7. Ce que je proposerais pour cet écran

1. Un bouton par sélection, « **Changer** », avec : Remplacer · Retirer sans remplacer ·
   Exclure l'équipe · Exclure le championnat.
2. Exclusions actives toujours visibles au-dessus de « Composer le coupon ».
3. Message d'erreur pour une cote visée invalide.
4. Confirmation (ou « Annuler ») pour « Vider ».
5. Tranche réelle des profils (Équilibré ≈ 75 %), et explication quand le moteur donne
   moins de chances que la cote.
6. Date, heure et lien dans l'image partagée.
