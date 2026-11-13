# Relecture du coupon en direct (travail de la nuit du 12 au 13/11/2026) — avant mise en ligne

Relu à 02:45 GMT, sur le code seulement : le serveur en ligne est `7338327` (étude), qui ne
contient pas encore `f9c472a` (serveur du coupon en direct) ni `9b572cc` (écrans).

## Ce qui a été fait

| Commit | Contenu |
|---|---|
| `0ed00e6`, `15b248d` | maquettes D8 à D15 (fenêtres pause → 50e, 60e-63e, 75e-78e ; Sûr gratuit) |
| `7338327`, `39853b6` | étude sur 13 347 matchs : chances justes aux trois moments, combinés compris ; 2 exclusions |
| `93b74ad` | console aux couleurs de l'application |
| `f9c472a` | serveur : cotes en direct, `/live/coupons`, pari placé en direct, publication par la console |
| `9b572cc` | application : écrans D8 à D14 |

Points bons :
- l'étude est solide : annoncé et gagné à moins de 2 points partout, y compris pour les
  combinés ;
- rien n'est publié d'office : il faut une action de la console ;
- les cotes suspendues sont écartées ;
- une cote qui a baissé est refusée ;
- les marchés retirés du direct ne sont jamais proposés.

## Défaut à corriger avant la mise en ligne : pari sur une cote d'avant un but

**Ce que j'ai lu.** `bookmaker/live_coupons.py` garde les cotes en direct jusqu'à 150 s
(`ODDS_MAX_AGE`). `live_offer` les réutilise pour placer un pari (`bookmaker/service.py`,
`place_bet`) sans vérifier que **le score n'a pas changé depuis le relevé**.

**Ce qui peut arriver.** À la 61e, le relevé donne « plus de 1,5 but » à 2,10, avec un score de
1-0. À la 62e, but : 2-0. L'application montre le but dans la minute (WebSocket), mais la
cote gardée vaut encore 2,10 pendant 2 min 30. Un joueur place alors un pari déjà gagné
(ou presque) à une cote d'avant le but.

L'argent est fictif, mais ce gain fausse :
- le **Classement mérité** ;
- la **Fiabilité** (les coupons en direct par moment, D15) ;
- la confiance des autres joueurs.

Les vrais bookmakers suspendent les cotes à chaque but pour cette raison.

**Suggestion :**
1. Garder avec chaque relevé de cotes le score (et les cartons rouges) du moment.
2. Dans `live_offer`, refuser le pari si le score ou le nombre de cartons rouges a changé
   depuis le relevé (« La cote a changé après un but : attends la prochaine cote »).
3. Refuser aussi pendant 1 à 2 minutes après un but, le temps que la VAR confirme, comme
   l'attente de 4 min du règlement.
4. Ajouter un test : relevé à 1-0, but à 2-0, pari refusé.

## À garder en tête

La comparaison des cotes `/odds/live` avec l'application 1xBet, à la même minute, n'a pas
encore été faite par le fondateur. Tant qu'elle ne l'est pas, publier en mode « cote
indicative » (D11), pas « cote 1xBet ».

## Corrigé le 13/11/2026

- Chaque relevé `/odds/live` n'est gardé que s'il porte le même score que le relevé des
  matchs du même passage, et s'il n'est pas suspendu par la source (`blocked`, `stopped`,
  `finished`).
- Chaque relevé gardé porte le score et les cartons rouges du moment (`state`).
- Propositions et pari : une cote relevée à un autre score ou avec un autre nombre de
  cartons rouges n'est plus proposée ; le pari est refusé (« la cote a changé après un but
  ou un carton rouge : attends la prochaine cote »), et aussi dans les 2 minutes qui suivent
  un but (ou un but annulé).
- Test : relevé à 1-0, but à 2-0 → refusé ; nouvelle cote mais but récent → refusé ;
  2 minutes après → accepté ; carton rouge → refusé.
