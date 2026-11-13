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

## 14 h 07 GMT — Premier coupon en direct publié, vu en production

`/live/coupons` → `published: true`, `odds_source: "indicative"` (décision après la
comparaison avec 1xBet, `docs/COMPARAISON_COTES_DIRECT_2026-11-13.md`).

**Ce qui marche** : à 14:07, Mozambique – Éthiopie (2e mi-temps, 47e, 0-0) est proposé dans la
fenêtre « mi-temps » (fermeture à la 50e), avec une sélection et un combiné pour chaque profil.

**Défaut 1 — les trois propositions sont moins sûres que leur cote, selon le moteur lui-même.**

| Profil | Sélection | Cote | Moteur | Selon la cote |
|---|---|---|---|---|
| Sûr | moins de 2,5 buts | 1,111 | 84 % | 90 % |
| Équilibré | plus de 0,5 but | 1,363 | 73 % | 73 % |
| Audacieux | Mozambique ou Éthiopie | 1,50 | 59 % | **67 %** |

Le moteur propose donc des paris qu'il juge lui-même plus mauvais que le prix offert : pour
le Sûr, 84 % de chances à une cote qui en suppose 90 % ; pour l'Audacieux, 8 points sous la
cote. Le profil choisit la sélection d'après sa chance (fourchette du profil), sans regarder
la cote.

**Suggestion** :
- ne proposer en direct que des sélections où la chance du moteur est au moins égale à
  la chance donnée par la cote (au besoin 2 points de marge pour les cotes indicatives) ;
- sinon, afficher « aucune proposition intéressante pour l'instant », plutôt qu'un pari
  perdant à long terme ;
- à défaut, l'avertissement « le moteur est moins confiant que la cote » sur la
  proposition.

**Défaut 2 — Zambie – Burundi à la mi-temps (14:04-14:07, statut HT) n'est pas proposé.**
Le match était bien dans la fenêtre « mi-temps », et les chances en direct étaient publiées.
La cause probable : pas de cote en direct pour ce match à la pause (cote suspendue par la
source, ou match absent de `/odds/live`). Ce n'est pas faux en soi : sans cote, il n'y a pas
de proposition. Mais c'est à confirmer avec « Tester le direct » à la prochaine mi-temps. Si
la source suspend toutes ses cotes pendant la pause, la fenêtre « mi-temps » ne s'ouvrira
qu'à la reprise, et ne durera alors que 46e-50e.
