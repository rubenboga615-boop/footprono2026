# Essai en conditions réelles — 8 novembre 2026 (mesures du 06/11, 23 h 48 à 00 h 30 GMT)

Serveur vérifié : `/api/v1/health` → `"commit": "b364d55"`. Application web :
`main.dart.js` du 06/11 à 23:41:45. Compte de test Premium **+225 07 84 89 71 95**,
Chromium réglé comme un téléphone (Pixel 7), plus appels directs à l'API avec le même compte.

## Résumé

| Point vérifié | Verdict |
|---|---|
| Paris sur les corners : nombre de corners | **corrigé** |
| Pari perdu tôt : explication | **corrigé** |
| Raisons du coupon intelligent dans le sujet | **corrigé** (détail : mi-temps) |
| Règle du coupon expliquée | **corrigé** ; dépassement de la cible encore grand (+45 %) |
| Nombre de matchs de la fiche équipe | **corrigé** |
| Objectif de la montante | **corrigé** |
| Matchs rangés par heure | **non corrigé** |
| Coupon dès la première demande après la mise à jour | **1,6 s** |
| Fiabilité : une seule règle | **corrigé** |
| Fiabilité : verdict sur les résultats réels | **trompeur** (voir 9) |
| Fiabilité : chargement rapide | **0,76 s** (6,2 s au tout premier appel après la mise à jour) |

## 1. Paris sur les corners

| Ce que j'ai fait | Ce que j'ai vu |
|---|---|
| Bookmaker → Réglés → pari n° 20 | « Hambourg – Gladbach · Total de corners · Plus de 8,5 corners — perdu · **8 corners (5-3)** » ; « Séville – Alavés · Plus de 7,5 corners — gagné · **9 corners (5-4)** » |
| `GET /bets` | champs `count: [5,3]`, `count_label: "corners"` à côté de `score` |

**Corrigé.** Le joueur voit pourquoi le pari est gagné ou perdu.

## 2. Pari perdu tôt

| Ce que j'ai fait | Ce que j'ai vu |
|---|---|
| Bookmaker → Réglés → pari n° 24 (perdu sur le 1er match, 6 matchs encore à venir) | sous les sélections : « **Pari perdu sur Everton – Coventry : les autres matchs ne comptent plus. Ils restent affichés pour information.** » |

**Corrigé.**

## 3. Raisons du coupon intelligent

Demandes `/smart-coupon` Grosse cote 25, Équilibré, Sûr et Audacieux (Prochaine journée),
lecture de toutes les raisons (27 sélections) :

- **Corners** : « Corners par match (obtenus + concédés) cette saison : Fulham 10,8,
  Newcastle 9,9 » et « Corners obtenus par match : Fulham 6,2, Newcastle 4,4 ». Plus aucune
  raison en buts pour un pari corners.
- **Buts** : « Buts attendus par le moteur : Malaga 1,5, Racing 1,4 (3,0 au total) » et
  « Buts par match (marqués + encaissés) cette saison ». Cohérent avec le pari.
- **Résultat / double chance / handicap** : buts attendus + « Forme (5 derniers, le plus
  récent à droite) » : l'ordre de la forme est maintenant indiqué.

**Corrigé.** Détails restants :
- **Mi-temps** (« Mi-temps : moins de 2,5 buts », Osijek – Hajduk ; « Mi-temps : plus de
  0,5 but », Çorum – Fenerbahçe) : les raisons portent sur **tout le match** (buts attendus
  2,6 ; buts par match 3,2). **Piste** : donner les buts attendus en première mi-temps.
- **Buts d'une équipe** (« Buts de VfB Stuttgart · moins de 2,5 ») : la 2e raison est le
  total « marqués + encaissés » des deux équipes, moins parlant que les buts marqués par
  l'équipe concernée.

## 4. Règle du coupon expliquée

| Ce que j'ai fait | Ce que j'ai vu |
|---|---|
| Grosse cote 25, Prochaine journée → Composer (1,9 s) | 8 sélections, cote **36,28** |
| Bas du coupon | « Règle : les sélections les plus sûres de la période selon le moteur (une par match), ajoutées une à une jusqu'à dépasser la cote visée. Cote obtenue 36,28 pour 25,00 visée : la dernière sélection ajoutée fait dépasser la cible. » |

**Corrigé** : la règle et le dépassement sont expliqués. Restent :
- **Dépassement de +45 %** (36,28 pour 25) : la 8e sélection fait passer de ≈ 20 à 36. Le
  joueur qui vise 25 obtient un coupon nettement plus risqué (1 chance sur 60 selon le
  moteur). **Piste** : proposer aussi le coupon à 7 sélections s'il est plus proche de la
  cible, ou terminer par la sélection dont la cote rapproche le plus de la cible (sans
  regarder l'avis du moteur, règle de `MOTEUR.md`).
- La règle est en bas, après les 8 sélections : il faut faire défiler tout le coupon pour
  la voir. Rien sur l'écran de réglages n'explique ce que fait « Grosse cote ».

## 5. Fiche équipe

| Ce que j'ai fait | Ce que j'ai vu |
|---|---|
| Match Arsenal – Hull → Analyse | « 9 et 9 matchs de championnat joués avant celui-ci » |
| Fiche Arsenal | « Premier League 2026-27 · **9 matchs joués (dont 4 à domicile)** » |
| Fiche Hull | « … · **9 matchs joués (dont 5 à domicile)** » |

**Corrigé** : même nombre partout, et le détail domicile est précisé.

## 6. Objectif de la montante

| Ce que j'ai fait | Ce que j'ai vu |
|---|---|
| Onglet Montante | en tête : « Objectif **132 400 F environ** — entre 109 562 et 155 281 F » ; dernier palier du tableau : « 71 300 → **132 400 F environ** » |

**Corrigé** : un seul chiffre principal, identique au tableau.

## 7. Matchs rangés par heure — non corrigé

| Ce que j'ai fait | Ce que j'ai vu |
|---|---|
| Onglet Matchs, samedi 7 novembre, « Toutes » | Premier League **15:00**, 15:00, **12:30**, 17:30, puis Liga 15:15… |
| `GET /predictions/upcoming?limit=400`, matchs du 07/11 | même ordre : EPL 15:00, 15:00, 12:30, 17:30 ; LA_LIGA 15:15, 13:00, 17:30, 20:00 ; SERIE_A 19:45, 17:00, 14:00, 14:00 |

Les matchs restent groupés par championnat, **et pas même triés par heure à l'intérieur
d'un championnat**. L'application garde l'ordre de l'API. **Piste** : trier par coup
d'envoi (dans l'API ou dans l'application), ou au moins par heure dans chaque championnat.

## 8. Coupon intelligent dès la première demande après la mise à jour

| Heure (GMT) | Demande | Durée |
|---|---|---|
| 23 h 48 (application publiée à 23 h 41) | Grosse cote 25, Prochaine journée — **1re demande** | **1,58 s** |
| 23 h 48 | même demande | 1,18 s |
| 23 h 48 | Équilibré, Prochaine journée | 0,82 s |
| 23 h 48 | Grosse cote 50, 7 jours | 1,05 s |
| 23 h 49 | `/montantes/7/suggestions`, `/montantes/8/suggestions` | 0,84 s / 0,75 s |
| 00 h 0x, dans le navigateur | Composer Grosse cote 25 | 1,9 s |

**Corrigé.** Réserve : je ne connais pas l'heure exacte du redémarrage du serveur ;
quelqu'un a pu faire une demande avant moi.

## 9. Page Fiabilité

| Ce que j'ai fait | Mesure / ce que j'ai vu |
|---|---|
| `/reliability?recent=20`, 1er appel après la mise à jour | **6,2 s** |
| mêmes appels ensuite | 0,63 s ; 0,16 s ; avec le filtre 5 grands 0,39 à 0,67 s |
| Profil → Fiabilité du moteur (navigateur) | page affichée en **0,76 s** |
| Bandeau | « Les 29 marchés publiés respectent la règle de justesse sur 7 081 matchs passés : écart de 3 points au plus entre annoncé et arrivé, ou dans la marge du hasard (au plus 4 points). » |
| Onglet Simulation | « ✓ règle respectée · écart max 3 pts » |
| Onglet « Depuis le lancement (110) », 5 grands | « **✓ règle respectée** » ; tranches 25 → 18 % et 35 → 28 % (−7 points, 134 et 61 cas), 44 → 66 %, 55 → 70 % (peu de cas) ; note : « Seulement 110 matchs : échantillon trop petit pour conclure (il en faut au moins 200) » |
| Liste des championnats | « 5 grands championnats » puis 20 championnats ; **pas de « Tous »**, ni Serbie ni Israël |

- **Une seule règle : corrigé.** Le « 4 points » du bandeau est maintenant expliqué (marge
  du hasard), et « Cartons : le plus de ✓ 4 pts » est cohérent avec cette phrase.
- **Chargement rapide : corrigé** (cache), sauf le tout premier appel après une mise à
  jour (6,2 s). **Piste** : calculer la page au démarrage, comme les sélections jouables.
- **Verdict sur les résultats réels : trompeur.**
  1. Sur les 5 grands championnats (110 matchs), l'écran affiche « ✓ règle respectée »
     **et**, juste en dessous, « échantillon trop petit pour conclure ». Deux tranches bien
     remplies (en gras) sont à 7 points d'écart, au-delà des « 4 points au plus » du bandeau.
     **Piste** : afficher « pas encore assez de matchs pour conclure » tant qu'il y en a
     moins de 200, au lieu d'un ✓.
  2. Sur **tous les championnats** (`/reliability` sans filtre : 395 matchs, assez pour
     conclure), la tranche 40 à 50 % est à **44 → 58 % (+13,5 points, 138 cas)** et 60 à 70 %
     à 64 → 73 % (+8,3 points, 51 cas) : la règle n'est **pas** respectée. Or cette vue n'est
     plus accessible : la liste des championnats ne propose plus « Tous ». Le joueur ne voit
     que la vue « 5 grands », où le verdict est positif. **Piste** : remettre « Tous les
     championnats » (par défaut, puisque les coupons prennent surtout des matchs hors des 5
     grands) avec son verdict réel.
  3. Deuxième chiffre clé de l'onglet réel : « **0,0 %** d'erreur en moins que les
     bookmakers » : formulation étrange pour une égalité (« autant d'erreur que les
     bookmakers »).
- **Serbie et Israël** toujours absents de la liste des championnats (22 en service).

## 10. Autres remarques

- La sélection par défaut de « Cote visée » à l'ouverture du coupon intelligent est **50**,
  alors que le profil choisi par défaut est Équilibré : à l'ouverture de Grosse cote, 50 est
  déjà coché.
- Lecteur d'écran : fiches de pari toujours annoncées avec « Dialog », « Dismiss », « Scrim ».
- Badge **« 2 »** sur l'onglet Profil, toujours sans explication visible.

## 11. À transmettre en priorité

1. **Fiabilité, résultats réels** : pas de « ✓ règle respectée » sous 200 matchs ; remettre
   la vue « tous les championnats », qui montre aujourd'hui un écart de +13,5 points.
2. **Matchs rangés par heure** (API et application).
3. **Grosse cote** : réduire le dépassement de la cible (+45 % ici).
