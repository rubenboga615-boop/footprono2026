# Maquettes du direct (10 novembre 2026) — à valider

Où le direct se place, sans nouvel onglet dans la barre du bas (elle est pleine sur
téléphone) : chaque nouveauté va dans l'écran où le joueur la cherche déjà. Même style que
`2-corrigees/`. Les chiffres sont des exemples.

| Maquette | Écran | Ce qui change | Étape du plan (`docs/PLAN_2026-11-10.md`) |
|---|---|---|---|
| `D1` | Matchs | pastille « ● En direct 5 » devant les jours ; matchs en cours avec minute, score, buts et cartons rouges, chances en direct et chances d'avant le match ; ★ les matchs de tes paris et coupons en haut | 1 (données), 6 (chances) |
| `D2` | Écran d'un match | onglet « En direct » en premier quand le match a commencé, sous-onglets Résumé · Statistiques · Compositions ; Résumé : chronologie (buts, passeur, cartons, remplacements, VAR, mi-temps) et chances en direct | 1, 6, 7 |
| `D3` | Écran d'un match | Statistiques : barres face à face, match / 1re / 2e mi-temps | 7 |
| `D4` | Écran d'un match | Compositions : terrain, numéros, systèmes, entraîneurs, remplaçants (entrées à la minute) | 7 |
| `D5` | Coupon | 3e carte « Coupon en direct », visible seulement pendant les matchs | 9 |
| `D6` | Coupon en direct | propositions sur les matchs à la mi-temps et en cours : chance du moteur, vraie cote 1xBet en direct, minute ; avertissement ; une proposition par heure au plus, désactivable ; Premium | 8 et 9 (seulement si l'étude et les cotes en direct le permettent) |
| `D7` | Mes paris | fiche d'un pari : « Chance de ton coupon : 12 % au départ → 31 % maintenant », sélection réglée à la mi-temps, « Suivre › » ouvre l'onglet En direct du match | 2 (règlement), 6 (chance) |

Après le match, l'onglet « En direct » devient « Résumé du match » (mêmes sous-onglets). Les
onglets Probabilités, Cotes et Analyse restent ceux d'avant le match.

## Coupon en direct (13 novembre 2026, version 2) — à valider

`coupon-en-direct.html` : maquettes **D8 à D15**, dans l'hypothèse où le coupon en direct
fonctionne ; remplacent D5 et D6. Après l'étude sur 13 347 matchs
(`docs/ETUDE_COUPONS_DIRECT_2026-11-13.md`) : trois fenêtres (pause → 50e, 60e-63e,
75e-78e), une sélection par match et combinés de plusieurs matchs, deux exclusions
(« plus ou moins de buts » en Audacieux à la 60e et en Équilibré à la 75e), Sûr gratuit,
aucune notification qui propose un coupon, cote 1xBet ou « indicative » selon la
comparaison des cotes.

| Maquette | Écran |
|---|---|
| `D8` | Mon coupon : carte « Coupon en direct », seulement pendant une fenêtre |
| `D9` | Coupon en direct : combinés du moteur (Sûr, Équilibré, Audacieux), puis match par match avec sa fenêtre |
| `D10` | Détail d'un combiné : une sélection par match, chances, cote 1xBet, chemin dans 1xBet |
| `D11` | Variante « cote indicative » si la source n'est pas 1xBet |
| `D12` | Mon coupon : compte à rebours de la fenêtre qui ferme la première, cote relue avant de placer |
| `D13` | Écran du match : carte « Coupon en direct » sous les chances en direct |
| `D14` | Mes paris : coupon placé en direct, chance de départ prise à ce moment |
| `D15` | Fiabilité : coupons en direct par moment, annoncé contre gagné |
