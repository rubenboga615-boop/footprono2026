# Nouveau visage de FootProba : suivi des étapes

Plan du 20/11/2026 : `docs/AUDIT_COMPLET_2026-11-20.md`, maquettes
`docs/maquettes/12-nouveau-visage/`. Chaque étape est montrée au fondateur avant la suivante.

## Partie 1 : réparations (20/11/2026)

| Point | Ce qui a changé | Test |
|---|---|---|
| 2. `/reliability` | Hors administrateur, `since` est ignoré, `recent` vaut 20 et seul un championnat connu est accepté (sinon 404). Plus de calcul forcé de 13 à 14 s par un inconnu. | `test_predictions.py` |
| 3. Sélections | La mesure « moteur contre cote » couvre aussi la double chance, plus/moins de 2,5 buts et « les deux marquent » (`nations_vs_odds` → `markets`). Dans l'application, l'écart en faveur du moteur sur une sélection est en ambre (prudence), jamais en vert. | `test_tester_2026_11_17.py`, `gap_badge_test.dart` |
| 5. Comparaison des moteurs | Une proposition par joueur, par moteur, par source et par jour (migration 0044 : `user_id`, `day`) ; propositions sans résultat après 14 jours « expired », hors bilan. | `test_engine2.py` |
| 7. Score corrigé | L'écart part de ce qui a vraiment été versé (gain + corrections sur le solde) : plus de gain payé deux fois. | `test_settlement.py` (le test échoue sur l'ancien code : 18 500 F en trop) |
| 8. Verrou du rattrapage | Verrou de 15 min prolongé à chaque étape, effacé seulement par son propriétaire ; le règlement normal n'attend que pendant l'étape 2. | `test_catch_up.py` |
| 9. Export des données | `app_settings` exportée vide (nom secret du canal ntfy). | — |
| 10. Grands nombres | Identifiant trop grand dans une adresse : 404 au lieu de 500. | `test_big_ids.py` |

Pas fait ici :
- **1**, version web : c'est au fondateur de la publier.
- **4**, avertissement du Coupon intelligent : il existait déjà. Il prend maintenant les nouvelles couleurs et la pastille, avec l'étape A.
- **6**, première mi-temps : à revérifier par le testeur.
- **5**, deux décisions attendent le fondateur :
  - la page `/reliability/engines` reste-t-elle ouverte aux comptes gratuits en mode comparaison ?
  - le profil « Sûr » peut-il montrer la double chance, un marché Premium ?

## Étape A : couleurs, icônes, pastille (version 1.1.0)

- **Couleurs** (`app/lib/theme.dart`, `Fp`) :
  - fond `#0B0F1A`, cartes `#131A2A`, cartes internes `#1B2438`, lignes `#26314A` ;
  - violet `#7C5CFF` ;
  - menthe `#34E0A1`, corail `#FF6B7A`, ambre `#FFC56B`, ciel `#5AB8FF` ;
  - encadrés teintés (`winBg`, `lossBg`, `warningBg`…).
  - Les couleurs codées en dur dans les écrans ont été remplacées par ces jetons.
- **Pastille unique** `GapBadge` (`widgets/engine_vs_odds.dart`) :
  - ▲ +N pts en menthe à partir de +3 points ;
  - ≈ cote en gris de −2 à +2 ;
  - ▼ −N pts en corail à −3 ou moins ;
  - en ambre pour un écart en faveur du moteur sur un match de sélections.
  - Les flèches et le « ≈ » sont dessinés : ces signes ne sont pas dans la police Inter de l'application.
  - Elle est posée sur les sélections du Coupon intelligent, les Coupons du jour, Mon coupon et les suggestions de palier.
- **Plus d'emoji dans l'interface** :
  - faits de match dessinés : ballon, cartons jaune et rouge, remplacement, VAR, penalty manqué ;
  - les buts s'écrivent « 23' Son » et les expulsions « carton rouge 81' X » ;
  - titres et textes des notifications affichés sans emoji (les notifications du téléphone ne changent pas).
- **Confort** :
  - boutons de cote d'au moins 44 px (avant : 35 px) ;
  - chiffres de même largeur partout (cotes, scores, montants alignés).
- **Captures** : `docs/maquettes/14-etape-A/captures-etape-A.png`.

### À vérifier par le testeur (étape A)
1. Fond bleu nuit et cartes bleutées sur tous les écrans : plus de violet en fond, le violet seulement sur les boutons et la case choisie.
2. Pastille sur chaque sélection du Coupon intelligent, sur chaque carte des Coupons du jour, dans Mon coupon et dans les suggestions de palier. Vérifier le signe et la couleur : +3 et plus en vert, ≈ en gris, −3 et moins en rouge.
3. Match de sélections (CAN, Ligue des Nations…) où le moteur dépasse la cote : pastille ambre, et l'info-bulle le dit.
4. Fil d'un match en direct : icônes dessinées, sans emoji. Liste des matchs en direct : « 12' Buteur · carton rouge 81' X ».
5. Notifications dans l'application : titres sans emoji.
6. Boutons de cote faciles à toucher (44 px) sur la fiche d'un match.
7. Sur le web : vérifier que « ✓ » (Fiabilité) et « ★ » (matchs de mes paris, version ordinateur) ne s'affichent pas en carrés vides. Ces deux signes étaient déjà là avant, et la police Inter de l'application ne les contient pas.

## Points du plan à confirmer avant les étapes B et C
- **Écrans « rien de valable » et « Pas d'occasion aujourd'hui »** (écrans 5 et 16 du plan). Le fondateur avait demandé de ne jamais faire d'écran « rien de valable » ni « Attendre un meilleur pari ». Il faut sa confirmation avant de les coder.
- **Premium « 30 jours / 3 mois »** (écran 25) : l'offre 3 mois avait été remise à plus tard avec le point A. À confirmer.
