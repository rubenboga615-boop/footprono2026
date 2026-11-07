# Revue de toute l'interface — 7 novembre 2026, 10 h GMT

Serveur `7288ee3`, version web du 07/11 à 09:47 (version 163). Téléphone émulé (Pixel 7).
Compte gratuit **+225 07 92 42 49 29** (39 captures) et compte Premium
**+225 07 84 89 71 95** (66 captures). Rien n'a été modifié dans le code.

## Verdict

L'application a **franchement changé de niveau** depuis hier : le message (accueil), la
vente de Premium (profil, écrans verrouillés), la liste des matchs et le Coupon intelligent
sont devenus clairs. Il reste surtout des **détails de disposition** et quelques
informations mal placées.

## 1. Corrigé et réussi

| Écran | Avant | Maintenant |
|---|---|---|
| **Accueil** | « calculées sans regarder les cotes » | « **Parie mieux informé. Perds moins bêtement.** », 4 avantages numérotés, « On ne promet pas de gains », « Créer mon compte gratuit » / « J'ai déjà un compte ». Clair, honnête, convaincant. |
| **Première ouverture** | — | fenêtre « Aider à améliorer FootProba » : ce qui est partagé / jamais partagé, « J'accepte » / « Pas maintenant ». Exemplaire. |
| **Matchs** | grandes cartes, 3 par écran, dans le désordre | **une ligne par match**, triées par heure, 1 / N / 2 en %, l'issue la plus probable encadrée : **11 matchs par écran** |
| **Profil (gratuit)** | « Version gratuite » avec les avantages Premium cochés | **tableau Gratuit / Premium** avec cadenas, « Passer Premium · 2 000 F / mois », « Payé une fois, 30 jours, sans renouvellement automatique » |
| **Coupon intelligent verrouillé** | écran vide | **exemple réel** (coupon d'hier, 3e ligne floutée) + « Débloquer · 2 000 F / mois » + « Voir le bilan de tous les coupons » |
| **Analyse verrouillée** | une phrase | « Inclus dans Premium … » + « Débloquer · 2 000 F / mois » |
| **Wave** | numéro collé | « **+225 05 00 64 99 04** », « numéro officiel de FootProba (le même que l'aide WhatsApp) » |
| **Coupon intelligent** | Remplacer + Exclure, croix ambiguë | un seul bouton **« Changer »** : Remplacer par un autre match · **Retirer sans remplacer** · Toujours exclure l'équipe A / B · **Exclure ce championnat** |
| Cote visée invalide | refusée sans rien dire | message rouge « Écris une cote entre 2 et 1000 (par exemple 15 ou 12,5) », la fenêtre reste ouverte |
| Profils | « 60 à 75 % chacune » | « Équilibré : près de 75 % », « Audacieux : près de 60 % » |
| Grosse cote 25 | 37,31 (+49 %) | **28,33 (+13 %)**, 8 sélections, 3,8 s |
| Après « Ajouter au coupon » | rien | bouton **« Voir mon coupon »** |
| « Vider » | sans confirmation | confirmation « Annuler / Vider » |
| Coupon | « Gain possible » | « **Tu récupères** 31 724 F CFA » ; alerte « 9 sélections : même des choix sûrs, une fois multipliés, font un coupon risqué » |
| Onglet | « Bookmaker » | « **Mes paris** » |
| Classement mérité | colonnes fausses quand des xPts manquent | seulement les points réels dans ce cas |

## 2. À corriger (disposition, textes)

1. **Matchs : noms d'équipes coupés.** « Korona Kielce – Rado… », « Zemun – IMT Novi
   Beo… », « Hapoel Petah Tikva – H… », « Csíkszereda – Universi… » : l'équipe à
   l'extérieur disparaît. **Piste** : les deux équipes sur deux lignes (domicile au-dessus,
   extérieur en dessous), le championnat en petit à côté de l'heure.
2. **Matchs : aucune cote dans la liste.** Le commit annonce « chance et cote », l'écran ne
   montre que les %. Un parieur choisit d'abord sur la cote. **Piste** : la cote en petit
   sous chaque %.
3. **Matchs : plus de cloche ni de classement en haut.** Les notifications ne sont plus
   accessibles que par Profil → Notifications ; le badge « 2 » est sur Profil. **Piste** :
   remettre une petite cloche à côté de « Tous championnats ».
4. **Matchs : la légende « encadré : l'issue la plus probable (pas un conseil de pari) »**
   existe pour le lecteur d'écran mais n'est pas visible à l'écran. Le joueur ne sait pas
   pourquoi un % est encadré. **Piste** : une ligne grise sous « Match 1 N 2 ».
5. **Barre du bas** : la dernière ligne de chaque liste passe toujours sous la barre de
   navigation (Matchs, Coupon, Montante, Profil) : prévoir de l'espace en bas.
6. **Montante** : « Chance d'aller au bout : 3,8 % selon les cotes » est toujours en petit
   sous le tableau. Pour un joueur, c'est le chiffre qui compte : à mettre dans la carte du
   haut, à côté de l'objectif (« Objectif 132 400 F · environ 4 montantes sur 100 vont au
   bout »). Rien n'explique ce qu'est une montante.
7. **Exemple du Coupon intelligent verrouillé** : c'est le coupon « Sûr » d'hier, **perdu**.
   Honnête, mais c'est la vitrine de l'abonnement. **Piste** : montrer le bilan des 7
   derniers jours (« 4 gagnés sur 9 ») et un coupon au hasard, pas toujours le même profil.
8. **Coupons du jour (Premium, 10 h)** : les trois coupons d'aujourd'hui affichent
   « Code bientôt disponible ». C'est normal le matin, mais c'est la promesse n° 2 de
   l'accueil (« avec le code 1xBet à coller ») : les saisir le plus tôt possible.
9. **Notifications** : seulement « Pari perdu… ». Aucune notification de pari gagné, de
   coupon du jour publié ou de match qui commence n'a été vue : l'application ne parle au
   joueur que quand il perd.
10. **Coupon intelligent** : toutes les sélections Grosse cote restent à « moteur 60 % »
    (près du plafond Audacieux) ; sans explication, la colonne de 60 % répétés paraît
    figée.
11. **Lecteur d'écran** : fenêtres annoncées « Dialog », « Dismiss », « Scrim » (anglais).

## 3. Rapidité vue dans l'application

| Action | Durée |
|---|---|
| Ouverture jusqu'à l'accueil | ≈ 5 s |
| Grosse cote 25, Prochaine journée | 3,8 s |
| Ajouter 8 sélections au coupon | 5,4 s |
| Page Fiabilité | ≈ 1 à 2,5 s |

## 4. Priorités proposées

1. Matchs : noms complets, cote visible, légende de l'encadré, cloche.
2. Montante : chance d'aller au bout en haut, une phrase d'explication.
3. Notifications aussi pour les bonnes nouvelles (pari gagné, coupon du jour publié).
4. Espace sous la barre de navigation.
5. Vitrine du Coupon intelligent : bilan de la semaine plutôt qu'un seul coupon perdu.
