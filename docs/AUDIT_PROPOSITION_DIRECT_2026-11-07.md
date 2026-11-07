# Proposition : notifications effaçables et paris en direct — 7 novembre 2026

Demandes du fondateur (7/11) : pouvoir effacer les notifications ; un système de paris
en direct (« coupon de rattrapage »), avec des coupons automatiques pendant les matchs, à
partir des statistiques du match en cours et de ses tendances. Ce document dit ce qui
existe, ce qui manque et une façon prudente d'y arriver. Rien n'a été modifié dans le code.

## 1. Effacer les notifications

**Constat** : l'écran Notifications a seulement « Tout lire ». Aucun moyen d'effacer une
notification ni toute la liste (aucune adresse de suppression dans
`api/v1/notifications.py`, à part le retrait d'un téléphone). Sur le compte de test, les
« Pari perdu… » s'accumulent.

**Proposé** :
- glisser une notification vers la gauche pour l'effacer ;
- « **Tout effacer** » en haut, avec confirmation ;
- effacement automatique des notifications lues de plus de 30 jours ;
- grouper par jour (« Aujourd'hui », « Hier », « Plus ancien »), ce qui existe en partie.

## 2. Paris en direct : ce qui existe aujourd'hui

| Élément | État actuel |
|---|---|
| Score, minute, statut pendant le match | **oui**, toutes les 2 minutes (`follow_live`, `/fixtures?ids=`) |
| Cartons rouges pendant le match | non (seulement après le match, via les statistiques) |
| Statistiques en cours (tirs, possession, corners, attaques dangereuses) | **non** : demandées seulement **après** la fin (`/fixtures/statistics?half=true`) |
| Événements (buts, cartons, remplacements, minute exacte) | non collectés pendant le match |
| Cotes en direct | **non** (seules les cotes d'avant-match sont relevées toutes les 3 heures) |
| Moteur | probabilités **d'avant-match** seulement (loi des scores Dixon-Coles) |
| Quota API-Football | 1 500 requêtes par passage au plus (`api_football_budget`) ; le quota journalier du forfait est à vérifier |

Conclusion : **aucun coupon en direct n'est possible aujourd'hui** sans de nouvelles données
et une étude du moteur en cours de match.

## 3. Avis franc sur le « coupon de rattrapage »

- Le mot « **rattrapage** » décrit exactement ce que le jeu responsable demande d'éviter :
  chercher à se refaire après une perte. L'application dit elle-même (Jeu responsable) :
  « ne cherche jamais à te refaire ». Je recommande de **ne pas utiliser ce mot** et de ne
  **jamais** proposer un pari en direct juste après une perte.
- Le direct est l'endroit où le bookmaker est le plus fort : cotes ajustées en quelques
  secondes, marchés suspendus à chaque action, marge souvent plus élevée qu'avant le match.
  Un moteur qui ne bat pas les cotes d'avant-match (page Fiabilité : 1,7 % d'erreur de plus)
  ne battra pas les cotes en direct.
- Ce que FootProba peut apporter d'**honnête et utile** en direct, c'est l'**information** :
  « il reste 20 minutes, 0-0 : le moteur donne 18 % à un but de plus », et « ton combiné
  passe de 12 % à 31 % de chances ».

## 4. Proposition par étapes

### Étape 1 — « Chances en direct » (sans nouvelle donnée)

Avec le score et la minute déjà relevés, recalculer les chances pendant le match : buts
restants attendus = buts attendus du moteur × part du temps restant (loi de Poisson,
corrigée ensuite par l'étude).
- Écran du match : « En direct, 63' · 1-0 : Leeds 78 % · Nul 17 % · Tottenham 5 % ;
  plus de 2,5 buts 24 % ».
- Coupon en cours : « Chance de ton coupon : 12 % au départ → **31 %** maintenant ».
- Notification groupée : « Ton combiné : 3 sur 7 validées, 31 % de chances qu'il passe ».
- **Avant publication** : vérifier la justesse sur les saisons passées (états score/minute
  reconstitués avec les minutes des buts de l'archive API-Football, si elle les contient ;
  sinon les collecter), comme pour tous les marchés (règle des 3 points).

### Étape 2 — Statistiques en direct

Pendant le match, `/fixtures/statistics` (tirs, tirs cadrés, possession, corners, cartons)
et `/fixtures/events` (buts, cartons rouges à la minute).
- Affichage « match en cours » : tirs cadrés, corners, possession, carton rouge.
- Les cartons rouges et le rythme d'occasions corrigent les chances en direct… **seulement
  si** l'étude montre que cela améliore la justesse.
- **Coût** : environ 2 requêtes par match et par passage. Exemple : 60 matchs un samedi,
  un passage toutes les 2 minutes pendant 2 h → 60 × 60 × 2 ≈ **7 200 requêtes**. À
  comparer au quota du forfait API-Football ; sinon, ne suivre que les matchs présents
  dans des coupons ou des paris de joueurs.

### Étape 3 — Cotes en direct

API-Football propose des cotes en direct (`/odds/live`) pour certains matchs et
bookmakers : couverture à vérifier pour 1xBet et nos championnats. Sans cote réelle en
direct, aucune sélection ne peut être proposée (règle actuelle : aucune cote inventée).

### Étape 4 — Coupon en direct (seulement après les étapes 1 à 3)

Si les chances en direct sont justes et les cotes disponibles :
- « Coupon en direct » : 1 à 3 sélections sur des matchs en cours, avec chance du moteur,
  cote réelle et minute, valable quelques minutes (la cote change très vite) ;
- jamais affiché juste après une perte, jamais présenté comme un « rattrapage » ;
- limite : 1 coupon en direct par heure, désactivable ;
- pas de code 1xBet possible pour un pari en direct (à vérifier) : le joueur reproduit
  lui-même la sélection.

## 5. Ordre proposé

1. Notifications effaçables (petit travail, demande des joueurs).
2. Étape 1 « Chances en direct » : utile, honnête, sans nouvelle donnée ; c'est elle qui
   donne l'impression de suivre le match « comme chez un bookmaker ».
3. Étapes 2 et 3 selon le quota API-Football et la couverture des cotes en direct.
4. Étape 4 seulement si les études montrent des chances justes.
