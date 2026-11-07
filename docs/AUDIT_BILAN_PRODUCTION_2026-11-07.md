# Bilan avant mise en production — 7 novembre 2026, 15 h GMT

Demande du fondateur : à quel point l'application est-elle terminée et prête pour la
production, le paiement manuel (Wave) étant considéré comme au point. Bilan fait à partir
de tous les essais du 6 et du 7 novembre et de mesures prises à 15 h. Serveur `45039a7`
(corrections du direct), version web du 07/11 à 10:43. Rien n'a été modifié dans le code.

## Verdict

**Environ 85 % terminée.** Prête pour un **lancement restreint** (quelques dizaines à une
centaine de joueurs invités, présentés comme « version bêta ») dès que la version web
contenant les corrections du direct est publiée. **Pas encore** pour un lancement large
(publicité, milliers de joueurs) : il reste 4 points à régler avant (voir 3).

## 1. Partie par partie

| Partie | État | Note |
|---|---|---|
| Inscription, connexion, accueil, consentement | clair, honnête, rapide (≈ 5 s à l'ouverture) | 9/10 |
| Liste des matchs | une ligne par match, triés par heure ; **noms coupés, cotes 8,5 s après la liste sans signe de chargement** | 6/10 |
| Écran d'un match, analyse, marchés | complet ; direct corrigé côté serveur (`45039a7`), **pas encore dans la version web** | 7/10 |
| Coupon intelligent | rapide (0,7 à 1,2 s), toutes les actions marchent, cote visée respectée (+13 % au plus) ; le même coupon pour tous (`AUDIT_PROPOSITION_DIVERSITE`) | 8/10 |
| Coupons du jour | fonctionnent ; codes 1xBet saisis à la main chaque jour par le fondateur | 7/10 |
| Coupon, pari, Mes paris | règlement sélection par sélection, « Tu récupères », confirmation de Vider | 8/10 |
| Montante | fonctionne ; la chance d'aller au bout est en petit, rien n'explique la montante | 7/10 |
| Notifications | arrivent ; **seulement les pertes**, impossibles à effacer | 4/10 |
| Fiabilité | honnête (« pas encore juste ») ; 0,15 s | 9/10 |
| Profil, Premium, jeu responsable, conditions, confidentialité, 18 ans | présents et clairs | 9/10 |
| Console | marche dans Chrome ; export cassé depuis l'icône de l'écran d'accueil | 7/10 |
| Serveur | redémarrage automatique, sauvegardes, rapide sauf `/offers/main` | 8/10 |

## 2. Mesures de 15 h (compte Premium, appel direct)

| Requête | Durée |
|---|---|
| `/predictions/upcoming` (100 matchs) | 1,0 s |
| `/offers/main` (66 matchs du jour, 120 Ko) | **8,5 s**, puis 8,3 s (aucun cache) |
| Coupon intelligent Grosse cote 25, Aujourd'hui | 1,2 s |
| Coupon intelligent Sûr, Aujourd'hui | 0,7 s |
| `/reliability` | 0,15 s |
| `/bets` | 0,18 s |

## 3. À régler avant un lancement large

1. **Publier la version web** avec les corrections du direct (`45039a7`) et la revérifier
   pendant des matchs réels (samedi ou dimanche).
2. **Cotes de la liste des matchs** : 8,5 s à chaque fois, le premier écran. À préparer à
   l'avance (comme les sélections jouables) et afficher « … » en attendant.
3. **Notifications** : pouvoir les effacer, et envoyer aussi les bonnes nouvelles (pari
   gagné, coupon du jour publié, coup d'envoi). Aujourd'hui l'application ne parle au joueur
   que quand il perd.
4. **Noms d'équipes coupés** dans la liste des matchs.

## 4. Risques à connaître (pas bloquants pour un lancement restreint)

- **Le moteur ne bat pas les cotes** (page Fiabilité : « pas encore juste »). L'application
  le dit honnêtement ; la communication ne doit jamais promettre de gains.
- **Dépendance au fondateur** : les codes 1xBet des Coupons du jour et la vérification des
  paiements Wave sont faits à la main. S'il est absent un jour, pas de codes et des Premium
  en attente.
- **Le même coupon pour tous** : sans importance avec peu de joueurs, à corriger avant d'en
  avoir beaucoup.
- **Adresse `footproba.duckdns.org`** : gratuite et suffisante pour une bêta ; pour un
  lancement public, un vrai nom de domaine inspire plus confiance et ne dépend pas d'un
  service gratuit.
- **Surveillance** : je n'ai vu aucune alerte qui préviendrait le fondateur si le serveur
  ou le suivi des matchs s'arrête (à vérifier avec la session de développement).
- **Quota API-Football** un gros samedi, avec le suivi en direct.
- Les règles locales sur les applications liées aux paris sportifs sont à vérifier par le
  fondateur (je ne peux pas les vérifier moi-même).

## 5. Conseil

1. Publier la version web avec les corrections du direct, revérifier ce week-end.
2. Lancer auprès d'un **petit groupe** (30 à 100 joueurs), avec l'Observatoire activé, pendant
   2 à 3 semaines.
3. Pendant ce temps : cotes de la liste, notifications, noms d'équipes, puis coupons variés.
4. Lancement large ensuite, une fois les points du 3 réglés et les retours du groupe lus.
