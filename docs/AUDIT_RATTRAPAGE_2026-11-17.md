# Vérification de la dernière modification — 17 novembre 2026

Relu à 02:35 GMT : commits `def884a` (« Tout rattraper »), `c2097e5`, `d1fc8e0`
(2. Bundesliga) et `8da1cee` (moteur du pari). Serveur en ligne à jour (`/health` ne donne
plus de commit). Rien n'a été modifié dans le code.

## « Tout rattraper » : fait et efficace

Ce qui a été fait (`worker/catchup.py`, 318 lignes, 255 lignes de tests) correspond point
par point à la demande du 17/11 :
- bilan avant de commencer, refusé s'il entame la réserve du direct ;
- matchs en retard des 7 derniers jours par lots de 20 ;
- règlement, cotes, prédictions, coupons du jour, Fiabilité ;
- verrou, arrêtable, relancé sans effet ;
- tous les jours à 00:10 GMT, et dès que le direct retrouve du quota ;
- remboursement après 48 h seulement si la source a confirmé le report ;
- réserve de collecte d'au moins 1 000, avec le calcul affiché ;
- « Résultats en retard » au lieu de « heure à confirmer » ;
- alerte sous 2 000 requêtes avant 18 h.

**Vu en vrai sur mes paris** (premier rattrapage dans la nuit, 211 requêtes d'après
`c2097e5`) :

| Match du 16/11 | Avant | Après le rattrapage |
|---|---|---|
| Somalie – Ghana | NS, bloqué | 0-1, réglé |
| Îles Féroé – Moldavie | NS, bloqué | 1-0, réglé |
| Macédoine du Nord – Slovénie | NS, bloqué | 0-3, réglé |

- **Pari 87 gagné**, réglé à 00:46:49 : 3 203 F crédités. La notification est marquée
  `silent: true`, donc elle a été gardée dans l'application, sans sonner pendant la nuit.
  Conforme.
- Pari 89 : 2 sur 3, puis « tout se joue sur Bosnie-Herzégovine - Roumanie (19:45) » à
  00:48. Pari 94 : 1 sur 3.
- Aucun « ⚽ » ni « 🟢 » envoyé après coup. Conforme.

## Défaut qui revient : 1 F de moins que le gain annoncé

Pari 87 : « gain possible » **3 204 F**, mais **3 203 F** payés. C'est le deuxième cas, après
le pari 80 (3 518 annoncés, 3 517 payés).
- **Cause** (lue dans le code) : le gain annoncé utilise la cote arrondie à 3 décimales
  (`odds_math.combined_odds`, 1,11 × 1,11 × 1,30 = 1,6017 → 1,602). Le règlement utilise la
  cote exacte, arrondie vers le bas (`settlement.py`, `math.floor(stake × factor)`).
- **Suggestion** : au règlement d'un pari tout gagné, payer exactement `potential_payout`
  (mise × cote affichée). Garder le calcul exact seulement pour les cas mêlés (remboursé,
  demi-gagné).

## Détail

Le message du commit `8da1cee` parle d'une « demande du fondateur du **18**/11/2026 »,
alors qu'il a été écrit le 17/11 à 02:10. C'est sans effet, mais l'historique sera trompeur.
