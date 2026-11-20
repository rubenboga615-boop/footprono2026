# Audit complet de FootProba, version B — 20 novembre 2026

Fait seul, sans rien modifier dans le code. Maquettes du nouveau visage :
`docs/maquettes/13-nouveau-visage-b/` (`index.html`, une image par partie).

> Une autre session (celle du testeur) a fait la même demande à 01:42 :
> `docs/AUDIT_COMPLET_2026-11-20.md` et `docs/maquettes/12-nouveau-visage/` (34 écrans).
> Cette version B est faite séparément, pour comparer les deux propositions. Elle relève
> aussi deux points vus seulement par l'autre étude :
> - `/reliability` peut être forcée à recalculer (13 à 14 s par appel) ;
> - la comparaison des moteurs enregistre chaque coupon sans limite.
>
> Je ne les ai pas revérifiés ici, ils sont à traiter avec ses conclusions.

## En 5 lignes

1. **Sécurité : aucune faille grave trouvée.** Les corrections du 12/11, du 14/11 et du 17/11 tiennent.
2. **Le problème n° 1 n'est pas technique, il est visible par le joueur.** Depuis 3 jours, les Coupons intelligents sont **tous sous la cote**. Le moteur leur donne moins de chances que le bookmaker, et l'écran ne le dit pas clairement.
3. **Les sélections nationales** : le moteur se montre trop sûr de lui face au marché. Mesuré sur 92 matchs, il annonçait 47 % là où seulement 21 % ont gagné.
4. **Trois défauts du 14/11 sont toujours là** : boutons de cote trop petits, carte « Moyennes attendues » vide, et « matchs de championnat » écrit pour des sélections.
5. **La version web n'a pas été republiée depuis le 17/11 à 02:22.** Mon bilan, l'annoncé par marché et « pour 30 jours » ne sont donc pas visibles sur le web.

## 🔴 À faire en premier

### 1. Dire clairement quand un coupon est sous la cote
- **Constat** : depuis le 17/11, les testeurs n'ont vu que des coupons sous la cote :
  - Sûr : 64 % contre 72 % ;
  - Équilibré : 41 % contre 53 % ;
  - Audacieux : 21 % contre 30 %.
- **Effet** : le joueur prend des coupons qui, à la longue, perdent de l'argent fictif sans qu'on le prévienne.
- **À faire, sans toucher au moteur** :
  - garder la façon de choisir du moteur intacte (règle du fondateur) ;
  - afficher le duel Moteur / Cote et l'encadré ambre (maquettes C20 et C21) ;
  - les propositions P1 et P2 du designer attendent toujours une décision.
- **Décision du fondateur** : oui, valider la maquette.

### 2. Republier la version web
- **Constat** : l'application web date du 17/11 (testeur, 18 et 19/11).
- **À faire** : mettre à jour le serveur, puis publier la version web et l'APK. Ces nouveautés attendent :
  - Mon bilan avec la colonne « annoncé » ;
  - les corrections de paiement ;
  - « pour 30 jours ».
- **Décision du fondateur** : non, c'est une action de déploiement.

### 3. Sélections nationales : ne pas présenter l'écart moteur / cote comme un avantage
- **Constat** (`AUDIT_VERIF_2026-11-18.md`) : quand le moteur dépasse la cote de 5 à 15 points sur un match de sélections, ces paris gagnent moins souvent que ce que disait le bookmaker :

  | Le moteur dépasse la cote de… | Moteur annonçait | Gagné en vrai |
  |---|---|---|
  | +5 à +10 points | 47 % | 21 % |
  | +10 à +15 points | 50 % | 33 % |

- **À faire, sans toucher au moteur** :
  - sur les matchs de sélections, afficher « sur les sélections, le moteur surestime souvent ses chances » ;
  - en parallèle, étudier les sélections africaines (déjà notée dans la feuille de route).
- **Décision du fondateur** : oui, sur le texte affiché.

## 🟠 À corriger (petit effort, pas de décision)

| # | Défaut | Où | Constaté |
|---|---|---|---|
| 4 | Boutons de cote trop petits : environ 35 px de haut au lieu de 44 px (marge interne verticale de 7 px) | `app/lib/screens/match_screen.dart`, `OddsButton` | code lu le 20/11 |
| 5 | Carte « Moyennes attendues » affichée même quand elle est vide | `match_screen.dart` (vers la ligne 755) | idem |
| 6 | « matchs de championnat joués » écrit aussi pour les sélections | `match_screen.dart` (vers la ligne 873) | idem |
| 7 | La fenêtre « Aider à améliorer FootProba » et le bandeau d'installation arrivent tôt dans le parcours (point I4 du 14/11) | `profile_screen.dart`, `install_tip.dart` | à revérifier sur téléphone |

## Ce qui a été vérifié et va bien

- **Adresses publiques du serveur** : les 44 adresses sans connexion ont été passées en revue.
  - Les données internes sont réservées à l'administrateur : `/predictions/runs`, `/ingestion/runs`, `/data/quality`.
  - La suppression de compte par téléphone demande le mot de passe et a les mêmes limites de tentatives que la connexion.
  - Les téléchargements de la console passent par des liens signés qui expirent.
- **Premium** :
  - les chances des marchés Premium ne sont pas envoyées aux comptes gratuits (`/matches/{id}/prediction`, offres) ;
  - un compte gratuit ne peut pas parier sur un marché Premium (`require_market`) ;
  - le Coupon intelligent et les suggestions de montante sont réservés à Premium.
- **Paris** :
  - le serveur utilise sa propre cote, jamais celle envoyée par le téléphone ;
  - si la cote a baissé, le pari est refusé ;
  - on ne peut pas jouer une cote d'avant-match une fois le match commencé.
- **Comptes** :
  - mots de passe protégés par scrypt ;
  - « déconnecter mes autres téléphones » fonctionne ;
  - la console demande un code de connexion à deux étapes (TOTP) et limite les tentatives.
- **Web** : en-têtes de sécurité en place (CSP, X-Frame-Options, HSTS par Caddy).
- **Paiements** (corrigés le 17/11) :
  - Wave est revérifié automatiquement ;
  - les adresses de retour et de notification ont une limite d'appels ;
  - un paiement en attente est repris au lieu d'en créer un nouveau.
- **Notifications** : silence de nuit de 23 h à 8 h dans le code des notifications pendant les matchs.
- **Vérifications automatiques** : vertes sur la branche de travail (CI n° 492).

## Points à surveiller (faible risque)

- **Clés Firebase « client »** :
  - elles sont dans l'application (`firebase_options.dart`, `firebase.xml`, service web), comme le prévoit Firebase ;
  - ce ne sont pas des secrets, mais il faut les restreindre dans la console Google Cloud : clé Android limitée à l'empreinte de l'application, clé web limitée au domaine `footproba.duckdns.org`.
- **`/health/tasks`** : public, il indique seulement si le suivi du direct tourne. C'est voulu, pour la surveillance extérieure.
- **`/live/chances`** : public, mais vide tant que la console ne l'a pas publié.

## Nouveau visage et idées

Voir `docs/maquettes/13-nouveau-visage-b/index.html` : **45 écrans refaits** et **8 idées** avec leur maquette.

- **Couleurs** :
  - fond « stade de nuit » ;
  - une seule couleur d'action, le vert lime ;
  - bleu = le moteur, ambre = la cote.
- **Disposition** :
  - barre du bas Matchs · Direct · Coupon (au centre) · Montante · Moi ;
  - le coupon devient un ticket permanent, qu'on ouvre par le bas depuis n'importe quel écran.
- **Idées** :
  - I1 suivre mes équipes ;
  - I2 ligue entre amis ;
  - I3 ma semaine en une image ;
  - I4 « pourquoi ce chiffre ? » ;
  - I5 économie de données ;
  - I6 paiement Mobile Money (Wave, Orange, MTN, Moov) ;
  - I7 widget écran d'accueil ;
  - I8 défi de la semaine, qui ne demande jamais de miser plus.

Les règles restent respectées :
- le moteur reste intact ;
- pas d'assistant IA ;
- aucune notification ne propose un pari ;
- silence de nuit ;
- pas d'écran « rien de valable » ;
- ni « value » ni « bon plan ».
