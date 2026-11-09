# Bilan des Coupons du jour, du premier au dernier — 9 novembre 2026, 21 h GMT

Compte Premium de test, application (Coupon → Coupons du jour → « Voir l'historique des
coupons », défilé jusqu'en bas) et `/smart-coupons/history` + `/smart-coupons/day`.
Serveur `a384c8e`. Rien n'a été modifié dans le code.

## 1. Les 16 coupons publiés (2 au 9 novembre)

| Jour | Sûr | Équilibré | Audacieux |
|---|---|---|---|
| Lun. 2 | 1,45 · 65 % · **gagné** | 2,17 · 42 % · **gagné** | 2,56 · 36 % · **gagné** |
| Mar. 3 | 1,22 · 84 % (1 sélection) · **gagné** | — | — |
| Mer. 4 | 1,23 · 68 % · perdu | — | 2,45 · 33 % · perdu |
| Jeu. 5 | — | — | — |
| Ven. 6 | 1,51 · 63 % · perdu | 2,29 · 42 % · perdu | 2,50 · 36 % · **gagné** |
| Sam. 7 | 1,77 · 64 % · **gagné** | 2,15 · 42 % · **gagné** | 2,17 · 36 % · **gagné** |
| Dim. 8 | 1,40 · 67 % · **gagné** | 2,43 · 42 % · perdu | 2,91 · 21 % · perdu |
| Lun. 9 | 1,20 · 84 % (1 sélection) · **gagné** | — | — |

| Profil | Réglés | Gagnés | Annoncé en moyenne | Réalisé | Mise fixe de 1 000 F par coupon |
|---|---|---|---|---|---|
| Sûr | 7 | 5 | 71 % | 71 % | **+40 F** |
| Équilibré | 4 | 2 | 42 % | 50 % | **+320 F** |
| Audacieux | 5 | 3 | 32 % | 60 % | **+2 230 F** |
| **Total** | **16** | **10** | | | **+2 590 F pour 16 000 F misés (+16 %)** |

- **Tout est juste** : chaque sélection recalculée à partir des scores (dont le
  « Remboursé si nul » de CFR Cluj – Craiova, compté remboursé) donne le même résultat que
  l'application. Les chiffres de l'écran (« Bilan depuis le lancement : Sûr 5 gagnés sur 7,
  71 % → 71 % ; Équilibré 2 sur 4 ; Audacieux 3 sur 5 ») sont exacts.
- **16 coupons, c'est trop peu pour conclure** : l'Audacieux à 60 % pour 32 % annoncé, c'est
  surtout de la chance (l'écran le dit : « l'écart est surtout du hasard »).
- Le Sûr gagne comme annoncé, mais rapporte presque rien (+40 F sur 7 coupons) : à cote
  1,20–1,50, un seul échec efface plusieurs gains.

## 2. Ce qui va bien

- Historique complet, du plus récent au 2 novembre, rien d'effacé ; chaque sélection a son
  état, son marché en français et l'explication des handicaps (« Gagné si Rio Ave gagne,
  fait match nul ou perd d'un seul but. Sinon perdu. »).
- Les jours sans coupon sont expliqués sur l'écran du jour : « Pas de coupon Équilibré
  aujourd'hui : aucune combinaison de 3 sélections au plus, chacune entre 60 et 75 %,
  n'atteignait une cote de 2,00. »
- Règlement rapide (en général 2 à 5 min après le dernier match) ; perte réglée dès la
  première sélection perdue (Audacieux du 8/11 réglé à 14:54, après Elche – Betis).

## 3. À corriger

| # | Constat | Piste |
|---|---|---|
| 1 | **Aucun code 1xBet** sur les 16 coupons (`booking_codes` vide partout, y compris le coupon du jour 9/11 avant son règlement d'après l'historique) | vérifier dans la console si les codes sont saisis puis effacés au règlement, ou jamais saisis ; c'est la promesse n° 2 de l'accueil |
| 2 | **Audacieux du 7/11 réglé avec 24 h de retard** (matchs finis vers 17 h 30 le 7/11 ; réglé le 8/11 à 17:24). Le joueur l'a vu « en cours » toute la nuit | chercher quel résultat est arrivé en retard (Nacional – Academico Viseu, Liga Portugal ?) |
| 3 | **Deux bilans différents pour la même période** : « 30 derniers jours » Sûr 4 sur 6, et « Bilan depuis le lancement » Sûr 5 sur 7 (le premier n'inclut pas le coupon réglé aujourd'hui) | un seul chiffre, ou préciser « jusqu'à hier » |
| 4 | **Jours entiers sans coupon dans l'historique** (jeudi 5 : aucun ; mar. 3 et lun. 9 : seulement Sûr) : rien ne l'indique dans l'historique, le joueur croit à un oubli | une ligne « Jeu. 5 nov. : pas de coupon (trop peu de matchs) » |
| 5 | **Coupons Sûr d'une seule sélection** (3/11 et 9/11, cote 1,20–1,22) | les annoncer comme tels (« un seul pari ce jour-là ») ; peu d'intérêt à cette cote |
| 6 | **Mêmes matchs dans plusieurs coupons du même jour** : 4/11, Sûr et Audacieux tous deux sur Kortrijk – Mechelen et Artis Brno – Bohemians, **perdus ensemble** ; 2/11 GAIS – AIK dans Sûr et Équilibré ; 6/11 Standard – Beveren dans Sûr et Équilibré | éviter qu'un match soit dans deux coupons du même jour (voir `AUDIT_PROPOSITION_DIVERSITE`) |
| 7 | Pas de score par sélection dans l'historique (seulement « Gagné / Perdu ») | ajouter le score final (« 2-2 ») |
| 8 | Fin de l'historique sans repère | « Premiers coupons : lundi 2 novembre » en bas |
