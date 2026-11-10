# Nouvelle interface : essai complet — 10 novembre 2026, 2 h GMT

Version web du 09/11 à 22:40 (« version 185 »), serveur inchangé (`a384c8e`). Téléphone
émulé (Pixel 7), compte gratuit et compte Premium, environ 200 captures comparées aux
maquettes (`docs/maquettes/`). Rien n'a été modifié dans le code.

## Verdict

**Très bon travail : l'application ressemble maintenant aux maquettes**, et la plupart des
corrections demandées sont faites. Il reste un défaut d'accessibilité, des noms de pays en
anglais, des cotes trop anciennes pour les matchs de la CAN, et tout ce qui dépend du
serveur (Grosse cote, Double chance), qui n'a pas été republié.

## 1. Maquettes : fait / pas fait

| Maquette | État | Remarque |
|---|---|---|
| C1 Liste des matchs | **fait en partie** | cartes, drapeaux, % et cote 1xBet dessous, légende de l'encadré, « Championnats ▾ », cloche avec badge ; mais **environ 3 matchs par écran** (cartes encore hautes, visé 4 à 5) |
| C2 Ma montante | **fait** | chance d'aller au bout en haut, « C'est quoi, une montante ? » |
| C3 Mon coupon | **fait** | chance du moteur, « selon la cote », alerte « 11 sélections… coupon risqué », mise, Vider avec confirmation ; en plus « Utiliser pour le palier 1 de ma montante » |
| C4 Coupon intelligent, résultat | **fait** | « 28,26 · Chance selon le moteur 4,1 % · 1 chance sur 24 », avertissement de marge ; **coupons différents d'un joueur à l'autre** (« Composé pour toi parmi les meilleurs… », bouton « Un autre coupon ») |
| C5 Fiabilité | **fait** | s'ouvre sur « Depuis le lancement (551) » ; le bandeau commence encore par la simulation, le verdict réel (« pas encore juste : 45 % → 54 % ») vient en second |
| C6 Profil | **fait** | Se déconnecter, Conditions, Confidentialité, « Aider à améliorer FootProba » |
| C7 Pari en cours | non vérifiable | aucun match en cours pendant l'essai (2 h du matin) |
| C8 Wave | non vérifié | bouton Wave non atteint par le script ; à revoir |
| C9 Passer Premium | **fait** | tableau complet, 7 lignes |
| N1 Coupon intelligent verrouillé | **fait** | « 7 derniers jours : 6 coupons gagnés sur 12 (le moteur en annonçait 6,0) », exemple flouté |
| N2 Analyse verrouillée | **fait** | aperçu flouté |
| N4 Profil gratuit | **fait** | |
| N7 Nouvelle montante | **fait** | objectif et chance d'aller au bout |
| N8 Suggestions de montante | **fait** | et chaque suggestion dit « Le moteur est moins confiant que le bookmaker sur ce pari » quand c'est le cas |
| N9 Mouvements | **fait** | |
| N12 Mot de passe oublié | **fait** | |
| Notifications | **fait** | « Tout lire », « Tout effacer », glisser pour effacer |
| Mes paris | **fait** | « Rendement : trop peu de paris réglés pour conclure (3 sur 20) » |
| N3, N5, N6, N10, N11, N13 à N16 | non vus | pas de coupon du jour à 2 h, pas de match commencé, pas d'erreur réseau ; historique de cote et arbitre non trouvés |

## 2. À corriger

| # | Gravité | Constat | Piste |
|---|---|---|---|
| 1 | **forte** | **Cotes des matchs de la CAN vieilles d'un mois** : onglet Cotes d'Algérie – Togo : « mises à jour le 06/10/2026 à 16:22 selon API-Football… Attention : la source n'a pas mis ces cotes à jour depuis plus de 2 jours ». Le Coupon intelligent, les suggestions de montante et mon pari n° 58 s'appuient sur ces cotes | ne pas utiliser une cote de plus de 2 jours dans le Coupon intelligent, les Coupons du jour et les montantes ; l'avertissement est bien, mais il faut aussi l'exclusion |
| 2 | forte | **Cartes de la liste des matchs invisibles pour un lecteur d'écran** : rôle « group », pas « bouton » ; on ne peut plus ouvrir un match sans voir l'écran (au doigt, ça marche) | rendre la carte « bouton » avec un libellé (« Algérie – Togo, mercredi 17:00, ouvrir le match ») |
| 3 | moyenne | **Noms des pays en anglais** partout (« Algeria », « South Sudan », « Central African Republic », « Cape Verde Islands », « Norway », « Wales ») | traduire les sélections nationales |
| 4 | moyenne | **Montante : « Un problème est survenu. Réessaie dans un instant. »** une fois (5 captures de suite), non reproduit ensuite (3 essais) alors que `/montantes` répond 200 | écran d'erreur plus précis (« pas de connexion » / « le serveur ne répond pas ») et nouvel essai automatique |
| 5 | moyenne | **Mon bilan** affiche encore « Rendement −48,1 % » en rouge après 3 paris (Mes paris, lui, dit « trop peu de paris ») | même règle dans Mon bilan |
| 6 | moyenne | Suggestions de montante : les 3 propositions sont « moins confiantes que le bookmaker » (moteur 39 % à 56 % pour 64,5 % selon la cote) ; l'une contient une sélection à **cote 1,02** | si aucune suggestion ne vaut la cote, le dire au lieu d'en proposer ; exclure les cotes < 1,10 |
| 7 | faible | Détail d'un coupon du jour : « marché en observation » sous une sélection, sans explication | une phrase (« ce marché est suivi avant d'être confirmé ») ou un « ? » |
| 8 | faible | Liste des matchs : environ 3 matchs par écran | cartes moins hautes (maquette C1) |
| 9 | faible | Fiabilité : le bandeau commence par « Simulation… » | verdict réel en premier |

## 3. Encore à faire côté serveur (non republié, `a384c8e`)

- Grosse cote : boutons 10 / 25 / 50 / 100 et « De 2 à 1000 » toujours là ; un coupon
  Grosse cote 25 donne 11 sélections, toutes de la CAN et de la Ligue des Nations, presque
  toutes sur les buts en 1re mi-temps (marché non vérifié pour les sélections).
- Double chance, marchés des sélections nationales : voir `AUDIT_OBSERVATOIRE_2026-11-09.md`
  et `AUDIT_JEU_2026-11-09.md`.
