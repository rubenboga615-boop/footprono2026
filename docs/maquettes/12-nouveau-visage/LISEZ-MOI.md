# Nouveau visage de FootProba — proposition du testeur (20/11/2026), à valider

`nouveau-visage.html` : 36 écrans (tous les écrans de l'application, 9 nouveaux dont le tableau de
bord), captures `e01.png` à `e36.png`. Les chiffres sont des exemples. Rien n'est codé.
Explications et liste des problèmes : `docs/AUDIT_COMPLET_2026-11-20.md`.

**Les 4 idées** : fond bleu nuit (#0B0F1A) et violet réservé aux actions ; une pastille unique
« moteur contre cote » (▲ vert / ≈ / ▼ rouge) partout ; une barre du bas Aujourd'hui · Matchs ·
**Créer** · Paris · Moi ; le gain et le risque toujours côte à côte.

| N° | Écran | N° | Écran |
|---|---|---|---|
| 1 | Bienvenue | 18 | Mes paris |
| 2 | Inscription avec code (nouveau) | 19 | Fiche d'un pari (histoire du pari) |
| 3 | Premiers pas (nouveau) | 20 | Moi |
| 4 | Aujourd'hui (nouveau) | 21 | Mon bilan |
| 5 | Aujourd'hui sans occasion (nouveau) | 22 | Fiabilité |
| 6 | Matchs | 23 | Classement mérité |
| 7 | Match avant le coup d'envoi | 24 | Notifications |
| 8 | Match en direct | 25 | Premium |
| 9 | Analyse d'un match | 26 | Fiche d'une équipe |
| 10 | Créer (nouveau) | 27 | Historique des cotes |
| 11 | Coupon intelligent | 28 | Partager un coupon |
| 12 | Coupons du jour | 29 | Alerte de cote (nouveau) |
| 13 | Mon coupon | 30 | Mon plan de jeu (nouveau) |
| 14 | Coupon en direct | 31 | Pourquoi ce choix ? (nouveau) |
| 15 | Montante | 32 | Bilan de la semaine (nouveau) |
| 16 | Montante, rien de valable | 33 | Inviter un ami (nouveau) |
| 17 | Nouvelle montante | 34 | Mode simple (nouveau) |
| 35 | **Tableau de bord complet, téléphone** (nouveau) | 36 | **Tableau de bord, ordinateur** (nouveau) |

## Révision du 20/11 (retour du fondateur)

- **Plus aucune icône emoji** (cloche, ballon, cadeau, horloge…), qui faisaient « site généré
  par une IA ». Elles sont remplacées par un jeu d'icônes dessinées au même trait (`icons.py`
  dans la proposition : accueil, terrain, ticket, profil, cloche avec pastille de compteur,
  recherche, étoile, etc.). La barre du bas utilise ces icônes.
- **Vrai tableau de bord** (35 et 36) : solde et courbe sur 30 jours, 4 indicateurs
  (rendement, paris gagnés, moteur annoncé contre réalisé, plan de jeu), matchs en direct de
  mes paris, mes paris avec leur chance, agenda, occasions du jour avec alerte de cote,
  coupons du jour, montante (paliers, gain et risque), justesse du moteur par marché. La
  version ordinateur a un menu à gauche et une recherche.
