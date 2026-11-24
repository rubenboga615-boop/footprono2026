# Vérification du 24/11/2026 — nouveau visage côté serveur, construction de l'application

Rien n'a été modifié dans le code. Compte Premium de test, argent fictif.

## 1. Le serveur en ligne a déjà les nouvelles fonctions (étapes B à D)

| Fonction | Vérification | Verdict |
|---|---|---|
| Tableau de bord `/me/dashboard` | 200 en 0,9 s : solde 95 129 F, courbe, 30 jours (20 paris réglés, 12 gagnés, misé 35 000 F, rendement −13,9 %), moteur annoncé 73 % / réalisé 70 % sur 53 sélections, marchés, mises, occasions, plan de jeu | répond |
| Plan de jeu `/me/play-plan` | mise max 3 000 F, budget 20 000 F/sem. réglés ; pari de 3 500 F → **refusé** : « Ton plan de jeu limite la mise à 3 000 F CFA par pari. » | **conforme** |
| Équipes suivies `/me/followed-teams` | suivre une équipe → 204, liste à jour | conforme |
| Alerte d'écart `/me/odds-alerts/gap` | 8 points, active → 200 | conforme (déclenchement à vérifier) |

Mais **la version web en ligne date toujours du 17/11 à 02:22** : aucun joueur web ne voit ces
écrans.

## 2. 🔴 « Occasions » du tableau de bord : des écarts absurdes en Ligue des champions

`engine_above_odds`, c'est-à-dire ce que le tableau de bord montre comme occasions (25/11) :

| Match | Sélection | Cote | Moteur | Selon la cote | Écart |
|---|---|---|---|---|---|
| Club Brugge – Liverpool | victoire de Bruges | 4,72 | **50 %** | 21 % | **+29** |
| Atlético Madrid – Viking | Viking ou nul | 7,90 | **38 %** | 13 % | **+25** |
| Sporting – Manchester United | victoire du Sporting | 2,56 | 62 % | 39 % | +23 |
| Lille – Bayern | victoire du Bayern | 1,65 | 82 % | 61 % | +22 |
| Sabah – Barcelone | moins de 1,5 but à la mi-temps | 2,80 | 54 % | 36 % | +18 |
| Slavia Prague – Villarreal | victoire de Slavia | 3,21 | 49 % | 31 % | +17 |

**Toutes les occasions viennent de la Ligue des champions, avec 17 à 29 points d'écart.** Un
moteur qui donne une chance sur deux à Bruges contre Liverpool, ou 38 % à Viking de ne pas
perdre à Madrid, se trompe très probablement. C'est le même genre d'erreur que celle des
sélections nationales (écart de +5 à +15 : 21 à 33 % de réussite seulement). Les clubs de
championnats différents, mal comparés, semblent être en cause.

**Risque** : ce bloc est en tête du nouveau tableau de bord. Un joueur va jouer « Bruges
gagne à 4,72 » parce que FootProba le présente comme une occasion.

**À faire avant de publier le tableau de bord** :
1. Garde-fou : ne jamais présenter comme occasion un écart de plus de 15 points (20 au
   plus), et exclure les compétitions où la mesure « annoncé contre réalisé » contre la cote
   n'est pas faite ou est mauvaise (coupes d'Europe, sélections).
2. Mesurer le moteur des coupes contre la cote (comme `nations_vs_odds`), par tranche d'écart.
3. Seulement ensuite, rouvrir ces compétitions aux occasions.

## 3. Deux définitions de « semaine »

- `stakes.week` du tableau de bord = **4 000 F** (7 derniers jours glissants : paris 105, 110 et
  111).
- `play_plan.week.staked` = **0 F** (semaine civile qui commence le lundi 23/11).

Le joueur verra deux montants « misé cette semaine » différents. Il faut garder une seule
définition, de préférence la semaine civile du plan de jeu, et l'écrire à l'écran.

## 4. Construction automatique : le test de bout en bout ne tourne plus depuis le 20/11

Workflow « Application » (runs 259 et 260) : la construction de l'application, de la version
web et de l'APK **réussit** (archives `footprono-web` et `footprono-apk` du run 260, commit
`acff9b2`). C'est le job **e2e** qui échoue en 2 s :

> Playwright does not support chromium on ubuntu26.04-x64 (Playwright 1.56.1)

GitHub est passé à Ubuntu 26.04 pour `ubuntu-latest`. Le parcours dans Chromium n'est donc
plus fait du tout : le filet de sécurité de l'application est coupé, pile au moment du
nouveau visage.

**Correction** : mettre `runs-on: ubuntu-24.04` pour le job e2e de `.github/workflows/app.yml`
(ou monter Playwright à une version qui gère Ubuntu 26.04), puis relancer.

## 5. Pour le fondateur

La version web du nouveau visage existe déjà : c'est l'archive **footprono-web** du run
« Application » n° 260 (20/11, commit `acff9b2`). Il ne faut pas la publier telle quelle
avant la correction du point 2 (occasions de Ligue des champions).
