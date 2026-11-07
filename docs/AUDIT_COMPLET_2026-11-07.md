# Essai complet après redéploiement — 7 novembre 2026, 04 h GMT

Serveur : `/api/v1/health` → `"commit": "75f5c20"`. Version web : `main.dart.js` du
07/11 à 03:40:30. Téléphone émulé (Pixel 7). Deux comptes fictifs : gratuit
**+225 07 92 42 49 29**, Premium **+225 07 84 89 71 95**. Rien n'a été modifié dans le code.

**Remarque importante** : les deux derniers commits de l'interface (`73fcc2a` « Matchs :
une ligne par match, chance et cote » et `ab651f0` « accueil, carte Premium, Coupon
intelligent verrouillé ») sont **postérieurs à `75f5c20`** et ne sont ni sur le serveur ni
dans la version web : ils restent à publier. Les recommandations du rapport
`AUDIT_COUPON_INTELLIGENT_2026-11-07.md` (envoyé à 03 h 55) ne sont pas encore traitées :
elles sont listées ici à titre de suivi, sans reproche.

## 1. Vitesse

| Mesure (appel direct, juste après le redéploiement) | Durée |
|---|---|
| Grosse cote 25, Prochaine journée — **1re demande** | **2,1 s** |
| même demande | 1,0 s |
| Équilibré 10 / Grosse cote 10 sur 7 jours | 1,6 s / 0,96 s |
| `/reliability` — **1er appel** | **6,7 s** |
| `/reliability` ensuite ; page Fiabilité dans le navigateur | 0,64 s ; 1,2 s |
| Suggestions de montante | 0,46 s |
| Liste des matchs (`/predictions/upcoming`) | 0,77 s |

Coupon intelligent : **réglé**. Page Fiabilité : le premier visiteur après chaque
redéploiement attend encore près de 7 s. **Piste** : préparer ce calcul au démarrage.

## 2. Corrigé et vérifié

| Point (rapport d'origine) | Constat |
|---|---|
| Matchs rangés par heure (08/11, §7) | **oui** : 10:30, 11:15, 12:00, 12:30, 13:00, 13:00… tous championnats mélangés |
| « 1 chance sur 1 » (UX, §8.1) | **oui** : « Chance selon le moteur 83,5 % — environ 8 fois sur 10 » |
| Analyse verrouillée sans bouton (UX, §3.3) | **oui** : bouton « Passer Premium » |
| Coupon intelligent verrouillé = impasse (UX, §3.2) | **oui** : texte clair (« compose un coupon selon ton profil et la cote que tu vises, avec ses raisons ») + « Passer Premium » ; plus de « bouton historique en haut » |
| Coupons terminés : « Code bientôt disponible », « Ajouter à mon coupon » (UX, §4) | **oui** : seul « Partager en image » reste |
| Pluriels « gagné(s) » | **oui** : « 1 gagné sur 3 » |
| Fiabilité : « Tous les championnats » par défaut (08/11, §9) | **oui** |
| Fiabilité : verdict réel (08/11, §9) | **oui** : bandeau et graphique « **pas encore juste : annoncé 44 % → arrivé 58 %** » sur 395 matchs ; la simulation est présentée à part |
| Paiement | **oui** : « Passer Premium » → Wave → numéro, montant, « Envoyer la capture » |

## 3. Pas encore corrigé (ou pas encore publié)

| Point | Constat du jour | Rapport |
|---|---|---|
| **Grosse cote : dépassement de la cible** | 25 → **37,31 (+49 %)** ; 100 → 138,89 (+39 %) ; 50 → 55,96 (+12 %) ; 10 → 11,42 (+14 %) | 08/11 §4 |
| Liste des matchs : une carte par match, sans cote | inchangée (3 matchs par écran) | UX §8.3 — commit `73fcc2a` à publier |
| Carte « Version gratuite » avec les avantages Premium cochés ✓ | inchangée | UX §3.1 — commit `ab651f0` à publier |
| Accueil : ce que FootProba apporte | inchangé (« calculées sans regarder les cotes ») | UX §1 — commit `ab651f0` à publier |
| « Gain possible » compte la mise | « Gain possible 1 120 F » pour 1 000 F misés à 1,12 ; pas de bénéfice net | UX §7.5 |
| Classement mérité incomplet | Premier League 2026-27 : « Arsenal 24 · 9,8 · +2,2 », inchangé | UX §8.6 |
| Wave : numéro groupé, paiement « en attente » | numéro « +2250500649904 » ; après « Fermer », rien sur le profil | UX §2 (10 h) |
| Onglet « Bookmaker » | inchangé | UX §8.10 |
| Cote visée invalide (1,5) | refusée **sans message** | Coupon intelligent §3 |
| « Retirer sans remplacer » | absent (boutons « Remplacer », « Exclure ») | Coupon intelligent §1 |
| « Vider » | efface le coupon **sans confirmation** | Coupon intelligent §5 |
| Après « Ajouter au coupon » | 6,5 s, message, **pas de bouton « Voir mon coupon »** | Coupon intelligent §5 |
| Équilibré à 75 % partout | Équilibré 10 : toutes les sélections à 75 % | Coupon intelligent §2 |

## 4. Nouveau constat

- **Profil (gratuit)** : nouvelle ligne « Aider à améliorer FootProba — TEST — partage
  anonyme de ton activité… » avec un interrupteur et « Ce qui est partagé › ». Clair.
  Elle n'est **pas activée par défaut**, ce qui est correct ; mais l'Observatoire n'aura de
  données que si les testeurs l'activent : **piste** : le proposer une fois, à la première
  ouverture, avec une phrase simple.

## 5. À faire pour la prochaine mise en ligne

1. Publier les commits `73fcc2a` et `ab651f0` (serveur + version web).
2. Grosse cote : réduire le dépassement de la cible (le point le plus visible pour un
   joueur qui choisit « 25 » et reçoit 37).
3. Les cinq points du Coupon intelligent (cote invalide, retirer sans remplacer, vider,
   voir mon coupon, Équilibré).
4. Bénéfice net dans le coupon, classement mérité incomplet, numéro Wave et paiement en
   attente.
5. Calcul de la page Fiabilité préparé au démarrage.
