# Proposition : notifications pendant les matchs d'un coupon, et « Encore au moins un but » — 12 novembre 2026

Demande du fondateur (12/11, soir) : que le joueur soit prévenu de ce qui se passe dans ses
coupons. Rien n'a été modifié dans le code.

## 1. Ce qui existe aujourd'hui

| Notification | Quand |
|---|---|
| « Ton pari commence dans 30 min » | 30 min avant le premier match d'un pari (`bookmaker/kickoff.py`) |
| « Pari gagné / Pari perdu » | au règlement du coupon entier (`bookmaker/settlement.py`) |
| Montante, coupons du jour prêts, Premium, paiement | à part |

Rien **pendant** le match : un but qui fait perdre ou gagner une sélection, une sélection
validée avant la fin, ne sont visibles qu'en ouvrant l'application.

## 2. Notifications proposées (par ordre d'utilité)

| # | Événement | Exemple de texte |
|---|---|---|
| 1 | **Sélection validée** (gagnée, y compris pendant le match) | « ✅ Plus de 1,5 but validé (RD Congo 2-0). Ton coupon : 1 sur 5, chance 31 %. » |
| 2 | **Sélection perdue → coupon perdu** | « ❌ Bénin 3-1 : « moins de 2,5 buts du Bénin » est perdu. Ton coupon de 1 500 F est perdu. » |
| 3 | **But qui change l'état d'une sélection** (gagnante ↔ perdante pour l'instant) | « ⚽ 58' Arménie 1-1 Chypre : ta sélection « Chypre +2 » reste gagnante pour l'instant. » |
| 4 | **Dernier match du coupon, tout le reste validé** | « 4 sur 5 validées : tout se joue sur Albanie – Finlande (19:45). » |
| 5 | Coupon gagné (existe) | avec la somme : « +1 709 F crédités » |
| 6 | Match reporté ou retardé de plus de 30 min | « Guinée – Érythrée n'a pas commencé : heure à confirmer. » |

## 3. Règles pour ne pas noyer le joueur

- **Groupées** : plusieurs événements dans la même minute → une seule notification.
- **Au plus une par match et par quart d'heure**, sauf sélection validée ou perdue.
- **Pas les cartons, corners, tirs** (sauf si une sélection porte dessus).
- Réglages dans Profil → Notifications : « Pendant mes matchs » (tout / seulement
  validé-perdu / rien), et silence de 23 h à 8 h.
- **Jamais de proposition de pari dans une notification**, surtout après une perte
  (« coupon perdu » ne propose rien d'autre).

## 4. « Encore au moins un but » à la place de « Plus de 3,5 buts »

Aujourd'hui (`app/lib/widgets/live_chances.dart` l. 197) la carte « Chances en direct »
affiche toujours « Plus de 3,5 buts », quel que soit le score. Le serveur envoie déjà toutes
les lignes (0,5 à 5,5).

**Proposé** : la ligne qui suit le score.

| Score | Ligne utilisée | Texte affiché |
|---|---|---|
| 0-0 | plus de 0,5 | « Au moins un but dans le match : 62 % » |
| 1-0, 0-1 | plus de 1,5 | « Encore au moins un but : 55 % » |
| 2-0 | plus de 2,5 | « Encore au moins un but : 81 % » |
| 3-1 | plus de 4,5 | « Encore au moins un but : 40 % » |

En dessous, en plus petit : « Encore au moins deux buts : X % » (ligne suivante).

**Mieux encore, quand le joueur a un pari sur ce match** : afficher **sa** sélection d'abord,
avec sa chance de tenir : « Ta sélection : moins de 2,5 buts — 67 % de chances de tenir ».

Au-delà de 5,5 (6 buts ou plus), ne rien afficher plutôt qu'un chiffre faux.

## 5. Après la version 212 : ce qui manque encore (relecture du code, 12/11 22 h 30)

### À corriger
1. **But annulé par la VAR.** L'alerte « ⚽ … gagnante/perdante pour l'instant »
   (`bookmaker/live_alerts.py`, `observe`) part dès que le score change, sans l'attente de
   4 min du règlement. Si le but est annulé, le joueur reçoit une 2e alerte « ⚽ But dans ton
   coupon » qui dit l'inverse, sans explication. Suggestion : quand le score **baisse**,
   envoyer « ↩️ But annulé (Arménie 0-0 Chypre) : « … » redevient perdante pour l'instant ».
2. **« victoire de Arménie »** → « victoire d'Arménie » (élision).
3. **Titre du rappel groupé** : reprend le délai du premier match seulement.

### À ajouter (utile, sans pousser à parier)
4. **Mi-temps d'un coupon** (réglage « Tout » seulement) : « Mi-temps : 2 sur 3 gagnantes
   pour l'instant ».
5. **Compositions officielles** d'un match du coupon (environ 1 h avant) quand un joueur clé
   est absent, si la source le permet.
6. **Sécurité du compte** : « Nouvelle connexion sur un autre téléphone » et « Mot de passe
   changé » (toujours envoyées, sans réglage).
7. **Jeu responsable** : bilan de la semaine (« 5 paris, -2 000 F fictifs ») et alerte
   quand les pertes dépassent un seuil choisi par le joueur.
8. **Résultat des coupons du jour** le soir, pour la transparence (gagné / perdu, même si le
   joueur ne l'a pas joué), avec le même réglage que « Coupons du jour ».

### À réfléchir (décision du fondateur)
- **Carton rouge** dans un match du coupon : exclu aujourd'hui, mais il change beaucoup les
  chances. À envoyer seulement si la chance du coupon baisse fortement ?
- **Heures de silence** fixes (23 h–8 h) : les rendre réglables ?
- **Joueur sur le web (iPhone, ordinateur)** : les notifications sur le navigateur demandent
  une autorisation ; vérifier que l'application la demande au bon moment (après le premier
  pari plutôt qu'à l'ouverture).
- **Limite par jour** : un joueur avec 10 coupons peut en recevoir beaucoup un soir de grand
  match. Plafond, ou résumé à la place au-delà d'un certain nombre ?
