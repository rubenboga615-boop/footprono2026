# Lecture de l'Observatoire bêta, de « Mon bilan » et de la Fiabilité — 9 novembre 2026

Trois captures du fondateur (9/11, 20 h 56 à 20 h 58) : console → Observatoire bêta,
« Mon bilan » de son compte, page Fiabilité. Mesures de contrôle à 21 h GMT (serveur
`a384c8e`). Rien n'a été modifié dans le code.

## 1. « Problèmes par écran » : ce n'est pas le serveur, c'est le téléphone en veille

| Requête (Observatoire, 7 jours) | Attente moyenne | > 20 s | Erreurs | Mesure directe du 9/11, 21 h (3 essais) |
|---|---|---|---|---|
| Écran « Bookmaker » (Mes paris) | 1,4 s | 11 | 33 | `/bets` 0,21 à 0,27 s |
| `/me/wallet/entries` | 7,1 s | 10 | 32 | 0,16 à 0,18 s |
| `/me/bets-summary` | 7,0 s | 10 | 32 | 0,16 à 0,19 s |
| `/me` | 12,7 s | 3 | 2 | 0,16 à 0,77 s |
| `/app/status` | 6,4 s | 3 | 9 | 0,66 à 0,95 s |
| `/app/version` | 6,9 s | 3 | 8 | 0,15 s |

Le serveur répond en moins d'une seconde. Les trois premières lignes ont **presque les mêmes
nombres** (10–11 attentes, 32–33 erreurs) : ce sont les trois requêtes de l'écran Mes paris,
qui se recharge **toutes les minutes** (`bookmaker_screen.dart`, `Timer.periodic` d'une
minute), **même quand l'application est en arrière-plan ou l'écran éteint**. Le téléphone
suspend le réseau de l'application : la requête attend jusqu'au délai maximal (20 s,
`client.dart`) puis échoue, et l'Observatoire la compte comme un problème. Le « dernier
problème » du testeur n° 1 (« /me/bets-summary : attente 20,4 s ») correspond exactement à
ce délai.

**Pistes** :
1. Arrêter les rechargements automatiques (Mes paris, Coupons du jour) quand l'application
   passe en arrière-plan ; recharger une fois au retour.
2. Dans l'Observatoire, ne pas compter une requête commencée ou finie pendant que
   l'application était en arrière-plan, et séparer le type d'erreur (délai dépassé, pas de
   réseau, erreur du serveur).
3. Sinon, le chiffre « Problèmes (7 jours) : 40 · 123 » fera croire à des pannes qui n'en
   sont pas, et cachera les vraies.

## 2. Réussite par marché (paris des testeurs)

Rappel : un seul testeur actif (48 paris) ; les sélections d'un même combiné ne sont pas
indépendantes. Écart « normal dû au hasard » ≈ 2 × √(p(1−p)/n).

| Marché | Sélections | Annoncé → arrivé | Marge du hasard | Lecture |
|---|---|---|---|---|
| **Double chance** | 31 | 71 % → **52 %** | ± 16 points | **au-delà du hasard** (−19) ; même sens que le 7/11 (7 sélections, 66 % → 43 %) : à étudier |
| Mi-temps : buts | 17 | 70 % → 53 % | ± 22 | à surveiller |
| Buts du match | 44 | 73 % → 82 % | ± 13 | dans la marge |
| Corners : total | 12 | 69 % → 83 % | ± 27 | trop peu |
| Handicap européen | 19 | 76 % → 84 % | ± 20 | trop peu |

**Piste** : vérifier la Double chance sur les saisons passées (étude « angle du match ») ;
si l'écart se confirme, la retirer des profils Sûr / Équilibré en attendant.

## 3. « Mon bilan » du fondateur : les pertes viennent des grosses cotes

| Cote du coupon | Paris | Gagnés | Annoncé | Net |
|---|---|---|---|---|
| moins de 2 | 18 | 15 (83 %) | 65 % | **+64 526** |
| 2 à 5 | 13 | 5 (38 %) | 31 % | +16 467 |
| 5 à 20 | 13 | 1 (8 %) | 11 % | **−87 804** |
| 20 et plus | 4 | 0 | 2 % | −13 000 |

- Les chances par sélection sont **justes** (annoncé 60 % → 58 % ; 75 % → 76 % ; 85 % → 91 %).
  Le résultat net (−19 811 F, −4,5 %) vient **entièrement des coupons à cote 5 et plus**,
  qui perdent comme annoncé (1 sur 13 pour 11 % annoncé).
- L'alerte « Tes mises de la semaine (326 404 F) ont au moins doublé » s'affiche bien.
- **Pistes** :
  - dans « Par cote du coupon », une phrase : « Les gains viennent des petites cotes, les
    pertes des grosses : c'est normal, une cote de 10 passe environ 1 fois sur 10 » ;
  - « 21 · 26 · 1 autres » → « 21 · 26 · 1 autre (remboursé) ».

## 4. Fiabilité (551 matchs)

- Verdict réel : « pas encore juste : annoncé 45 % → arrivé 54 % » (404 matchs le 7/11 :
  44 % → 58 %). L'écart diminue avec plus de matchs, mais reste au-dessus de 3 points.
- Résultat du match : écart moyen **4,0 points** ; issue la plus probable trouvée 58 % pour
  52 % annoncé (le moteur reste trop prudent sur les favoris).
- Plus/moins de 2,5 buts : **0,9 point** d'écart (551 matchs) : juste.
- Les deux marquent : 2,0 points (153 matchs).
- Liste « Derniers matchs » : claire (✓ / ✗ sur l'issue la plus probable). Petit détail :
  « 1 44 % · N 28 % · 2 29 % » se lit mal ; « 1 : 44 % · N : 28 % · 2 : 29 % ».

## 5. Coupons intelligents et montantes

37 demandés, 17 ajoutés au coupon, 20 non ajoutés ; 2 montantes perdues, au palier 2 (sur 2
lancées). Rien d'anormal ; il faudra plus de testeurs (testeur n° 2 : 0 pari).

## 6. Réussite par marché et par championnat (« Mon bilan » du fondateur + compte de test)

Sélections gagnées · perdues (remboursées à part). Fondateur : 48 paris ; compte de test :
3 paris. Marge du hasard ≈ 2 × √(p(1−p)/n).

### Par marché

| Marché | Fondateur | Compte de test | Ensemble | Annoncé (Observatoire) | Lecture |
|---|---|---|---|---|---|
| Plus/moins de buts | 36 · 8 (82 %) | 1 · 2 | 37 · 10 (79 %) | 73 % | bien |
| **Double chance** | 16 · 15 (52 %) | 0 · 2 | **16 · 17 (48 %)** | **71 %** | **écart de 23 points, au-delà du hasard (± 16)** |
| Buts d'une équipe (domicile + extérieur) | 25 · 10 (71 %) | 3 · 1 | 28 · 11 (72 %) | 70 % | juste |
| Handicap européen | 16 · 3 (84 %) | 1 · 1 | 17 · 4 (81 %) | 76 % | bien |
| **Buts en 1re mi-temps** | 9 · 8 (53 %) | — | 9 · 8 (53 %) | 70 % | à surveiller (± 22) |
| Total de corners | 10 · 2 (83 %) | 2 · 2 | 12 · 4 (75 %) | 69 % | bien |
| Les deux marquent | 7 · 5 (58 %) | 1 · 0 | 8 · 5 (62 %) | 60 % | juste |
| Remboursé si nul | 8 · 0 | — | 8 · 0 | 62 % | bien (peu) |
| Résultat du match | 5 · 2 | 0 · 1 | 5 · 3 | 63 % | trop peu |

**Conclusion par marché** : tout est juste ou meilleur qu'annoncé, **sauf la Double chance**
(48 % pour 71 % annoncé, 33 sélections) et, à surveiller, les buts en 1re mi-temps. La Double
chance revient souvent dans les profils Sûr et Équilibré (et dans les coupons de sélections
de cette semaine) : la vérifier en priorité sur les saisons passées.

### Par championnat (fondateur)

| Bien au-dessus de 70 % | Autour de 50–70 % | En dessous |
|---|---|---|
| Premier League 22 · 3 (88 %), Bundesliga 16 · 1 (94 %), Liga 19 · 5 (79 %), Ekstraklasa 7 · 1, Ligue 1 7 · 0, Liga I roumaine 7 · 0, HNL croate 4 · 0, Süper Lig 3 · 0 | Serie A 13 · 9 (59 %), Allsvenskan 5 · 3, Superliga danoise 4 · 3, Liga Portugal 5 · 2, Eredivisie 4 · 2, Pro League belge 5 · 5, Super League suisse 4 · 4 | **Bundesliga autrichienne 2 · 5 (29 %)**, **Ligat ha'Al israélienne 2 · 5 (29 %)**, Premiership écossaise 0 · 2, Eliteserien 0 · 2 |

- Aucun championnat n'a assez de sélections pour conclure (2 à 25). Avec 22 championnats,
  en trouver un ou deux très bas par hasard est attendu (2 sur 7 pour ≈ 65 % annoncé :
  environ 6 chances sur 100 par championnat).
- **Pistes** : ne rien retirer pour l'instant ; suivre ce tableau dans l'Observatoire à partir
  de 30 sélections par championnat ; Serie A (13 · 9) et Autriche / Israël en premier.
- Compte de test : trop peu (1 à 3 sélections par championnat), non interprété.
