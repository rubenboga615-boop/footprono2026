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
