# Essai en conditions réelles — 6 novembre 2026

Site testé : `https://footproba.duckdns.org/app/` (version web **98**), navigateur Chromium
émulant un téléphone Android (Pixel 7, 412 × 915, tactile, fuseau Africa/Abidjan),
en passant par l'arbre d'accessibilité comme les tests `e2e/`.
Compte de test : **+225 07 84 89 71 95** (« Testeur Claude »), Premium offert depuis la console.
Les durées sont mesurées depuis le navigateur. Une requête simple prend 0,3 à 0,7 s depuis
la machine de test : au-delà, le temps vient du serveur.

## 1. Coupon intelligent « Grosse cote » à 25 (priorité)

### Ce qu'on voit

1. Grosse cote → 25 → période par défaut **Prochaine journée** → « Composer le coupon ».
2. Le bouton devient « Recherche… » **pendant 17 à 19 secondes**, sans autre message.
3. Coupon proposé : cote **29,07** pour 25 visés, 8 sélections, chance 1,7 % selon le
   moteur, 3,4 % selon la cote (« 1 chance sur 60 »).

| Requête `/smart-coupon` (mesures directes, même compte) | Durée |
|---|---|
| Grosse cote 25, Prochaine journée (dans l'application) | **18,7 s** |
| Grosse cote 25, Prochaine journée (2 nouveaux essais) | 17,2 s, 16,2 s |
| Grosse cote 25, 3 jours / Ce week-end / 7 jours | 16,0 s / 15,0 s / 16,8 s |
| Grosse cote 25, Demain | 6,5 s |
| Grosse cote 25, Aujourd'hui | 2,1 à 2,6 s |
| Grosse cote 25, Prochaine journée, Premier League seule | 1,8 s |
| **Équilibré**, 3 sélections, Prochaine journée | **16,3 s** |

### Analyse

- **On est à 1 à 4 secondes du délai de 20 s** (`ApiClient.timeout`, `app/lib/api/client.dart`).
  Avec deux ou trois joueurs en même temps, le message « FootProba n'a pas répondu à temps »
  apparaîtra alors que le réseau du joueur va bien. Ce message est honnête, mais il arrivera
  souvent dès qu'il y aura du monde.
- **Le profil Grosse cote n'est pas en cause** : Équilibré prend le même temps. La durée suit
  le **nombre de matchs de la période** (week-end chargé, 22 championnats). Un second essai
  n'est pas plus rapide : rien n'est mis en cache entre deux demandes.
- Le dernier commit (0727f11, « 8 s → 2,8 s » sur un volume simulé) ne suffit pas sur les
  vraies données, ou il n'est pas encore en service : `/health` donne seulement
  `version 0.1.0` et ne permet pas de savoir quel commit tourne. → **Ajouter le commit
  à `/health`**.
- **Pendant l'attente, le joueur n'a aucune explication** : « Recherche… » pendant 18 s,
  sans message comme « le moteur étudie N matchs, cela peut prendre une vingtaine de secondes ».
  Le « message de lenteur » n'apparaît **jamais avant** la fin du délai.

### Pistes

1. Côté serveur : mettre en cache, pour quelques minutes, les cotes et les pronostics
   de la période (partagés par tous les joueurs et tous les profils), ou les précalculer
   avec la collecte des cotes.
2. Côté application : délai propre au coupon intelligent et aux suggestions (45 à 60 s),
   puis un message progressif (« Le moteur étudie les matchs du week-end… » après 5 s,
   « Encore quelques secondes… » après 15 s).
3. Proposer « Aujourd'hui » ou « Demain » par défaut : 2 à 6 s au lieu de 17 à 19 s.

### Autres remarques sur le coupon proposé

- **Cote obtenue loin de la cible** : 29,07 pour 25 (+16 %), et 39,66 après un « Remplacer »
  (+59 %). La dernière sélection fait souvent dépasser nettement la cible.
- **Toutes les sélections sont annoncées à « Moteur 57 à 60 % »** : le joueur ne comprend pas
  pourquoi tout est à 60 %. Il faut expliquer la règle (« sélections les plus probables
  jusqu'à atteindre la cote ») sur l'écran.
- **Raisons hors sujet** : pour « Moins de 11,5 corners », la deuxième raison est
  « 4 dernières confrontations : 3,5 buts par match » (des buts, pas des corners) ;
  pour « Moins de 2,5 buts Everton – Coventry », la raison donnée est « xG créés : Everton 1,7,
  Coventry 1,0 » (2,7 au total, ce qui va plutôt dans l'autre sens).
- **Code brut « ISR »** au lieu de « Ligat ha'Al israélienne » (Ironi Tiberias – Beitar
  Jerusalem) : voir le point 3, version web en retard.
- « **1 match(s) écarté(s)** » : écrire « 1 match écarté » ou « 2 matchs écartés ».
- Après « Remplacer », le match remplacé apparaît dans « match(s) écarté(s) » : le mot
  « écarté » surprend le joueur, qui a seulement demandé un autre choix.

## 2. « Ajouter au coupon » depuis le coupon intelligent : 15 s sans retour

- 7 sélections ajoutées en **15,5 s**, avec **21 requêtes** : pour chaque sélection, l'une
  après l'autre, `/matches/{id}` puis `/matches/{id}/offer` (≈ 100 Ko et 2 s chacune en
  Premium) (`addSelectionsToCoupon`, `app/lib/screens/smart_coupon_screen.dart:884`).
- Pendant ce temps, le bouton est seulement grisé : pas de compteur, pas de roue. On croit
  que rien ne se passe et on appuie ailleurs. Avec 12 sélections, on approche 25 s.
- Piste : lancer les requêtes en parallèle (`Future.wait`), ou mieux, renvoyer avec
  `/smart-coupon` tout ce qu'il faut pour remplir le coupon (match et offre), ce qui supprime
  toutes ces requêtes. Afficher « Ajout 3 / 7… ».
- Le reste fonctionne : message « 7 sélection(s) ajoutée(s) au coupon (onglet Coupon) »,
  pari placé en 2 s, solde 100 000 → 99 000, pari visible au Bookmaker.

## 3. Version web en retard sur l'APK

- `/app/version` annonce l'APK **112** (publié le 05/11 à 23 h 14), alors que la version web
  servie affiche **version 98** en bas du profil.
- Conséquence visible : Serbie et Israël, en service côté serveur (`/competitions`), ne
  figurent pas dans les filtres du coupon intelligent ni dans la fiabilité, et une sélection
  israélienne s'affiche « ISR ». Le code du dépôt contient déjà ces noms (commit c1c7339).
- iPhone et ordinateur utilisent donc une application plus ancienne qu'Android.
  → Publier `footprono-web.zip` à chaque publication d'APK (ou ajouter une alerte dans la
  console quand les deux numéros divergent).

## 4. Suggestions de montante : lentes et contraires à la règle du moteur

- `/montantes/{id}/suggestions` : **18,9 s**, à nouveau juste sous le délai de 20 s.
- Les 3 suggestions du palier 1 (cote 1,55 à 1,65) sont toutes « **Modèle 76 %, selon la
  cote 63 à 64 %** », soit 12 à 13 points d'écart, triées « par probabilité du modèle ».
  Dans une plage de cote fixe, trier par probabilité du moteur revient à choisir **les plus
  gros désaccords avec la cote**, exactement le biais écarté pour la Grosse cote
  (`MOTEUR.md`, « ne jamais choisir sur un désaccord avec la cote », la cote ayant le plus
  souvent raison). Ces sélections ne passeront pas 76 % du temps. À revoir avec la même règle.

## 5. Autres lenteurs

| Écran / requête | Durée |
|---|---|
| Démarrage de l'application (page vide → écran de connexion) | 4,8 à 5,4 s |
| `/predictions/upcoming?limit=400` à chaque ouverture | 1,1 à 2,3 s, **208 Ko** |
| `/matches/{id}/offer` (Premium) | 2,3 s, **100 Ko** (17 Ko en gratuit) |
| `/reliability?recent=20` (Fiabilité du moteur) | **5,6 s**, écran vide pendant ce temps |
| `/montantes` | appelé **2 fois au démarrage** et à **chaque changement d'onglet** (12 fois en 30 s) |

## 6. Écrans : ce qui est cassé ou peu clair

**Textes faux ou incohérents**

- Onglet Coupon vide : « Un combiné réunit des matchs différents (**10 au maximum**) », alors
  que le serveur et le coupon intelligent acceptent **12** sélections
  (`app/lib/screens/coupon_screen.dart:240`, `MAX_SELECTIONS = 12`).
- Liste des matchs : les matchs sont rangés par championnat (Premier League, Liga, Serie A,
  Bundesliga, Ligue 1), donc pas par heure (20:00, 20:00, 19:45, 19:30, 19:45). C'est voulu,
  mais rien ne l'indique : un joueur qui cherche « le prochain match » est perdu.
- Fiche équipe Alavés : « Liga 2026-27 · **6 matchs joués** », alors que l'Analyse du même
  match dit « **11** matchs de championnat joués » (le 6 semble être le nombre de matchs à
  domicile).
- Forme sur 5 matchs : l'Analyse l'écrit du plus ancien au plus récent (« N P P N P »), la
  fiche équipe du plus récent au plus ancien (P, N, P, P, N). Choisir un seul ordre et
  l'indiquer (« le plus récent à droite »).
- Montante : « Objectif 109 562 à 155 281 F » en tête (bas et haut des plages), mais le
  tableau finit à « 132 400 F environ » (milieu des plages) : deux chiffres pour le même
  objectif, sans explication.
- Montante : le message « Montante lancée : choisis le pari du palier 1 » recouvre la carte
  « Suggestions du moteur », juste à l'endroit où il faut appuyer.

**Accessibilité (lecteur d'écran, et tests automatiques)**

- Bouton retour : sur Notifications, Coupon intelligent et Fiabilité, il est fusionné avec
  le titre (« Retour Notifications ») et n'est **pas annoncé comme un bouton**.
- Coupon intelligent : les sélections du coupon proposé ne sont pas lues ; seuls
  « Remplacer » et « Exclure », répétés 7 fois, sans dire quelle sélection ils visent.
- Onglet Coupon : seulement « Retirer » répété 7 fois, sans le nom de la sélection.
- Libellés anglais de Flutter : « Delete » (puce des matchs écartés), « Dialog », « Scrim ».
- La carte « Suggestions du moteur » de la montante n'est pas annoncée comme un bouton.

**Fonctionne bien**

Inscription (2,3 s jusqu'aux matchs, indicatif +225 prérempli, case 18 ans claire),
connexion, Matchs, détail d'un match (Probabilités, Cotes avec historique, Analyse
Premium très complète), Classement mérité, fiche équipe, Notifications (vide),
Bookmaker, Mon bilan (vide, message clair), Profil (Premium et date de fin visibles),
Fiabilité (honnête : 80-90 % annoncés, 73 % réalisés), Coupons du jour (trois profils, état
en direct, « Code bientôt disponible »), Remplacer / Exclure (choix « Seulement ce
match / Toujours exclure l'équipe » clair), placement d'un pari, lancement d'une montante.
Aucune erreur JavaScript de l'application (seul Firebase, bloqué sur la machine de test).

## 7. Priorités proposées

1. Coupon intelligent et suggestions : passer sous 5 s (cache serveur), délai plus long et
   message d'attente dans l'application. **Risque immédiat d'échec dès qu'il y aura du monde.**
2. Publier la version web 112.
3. Suggestions de montante : ne plus trier sur un désaccord avec la cote.
4. « Ajouter au coupon » : requêtes en parallèle ou données incluses, avec une progression.
5. Petits textes : 10 → 12, ordre des matchs expliqué, « match(s) », forme, objectif de montante.
6. Accessibilité : boutons retour, libellés des sélections et des boutons Retirer / Remplacer.
