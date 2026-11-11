# Bilan général, essai de bout en bout et outils d'audit de sécurité — 11 novembre 2026

Serveur `9115349`, version web du 11/11 à 00:32. Téléphone émulé (Pixel 7), compte gratuit
et compte Premium, environ 130 captures ; contrôles directs du serveur. Rien n'a été
modifié dans le code.

## 1. Verdict

L'application a beaucoup progressé en cinq jours : interface refaite d'après les maquettes,
messages honnêtes partout, règlement rapide et juste, Grosse cote encadrée, Observatoire.
**Elle est prête pour un petit groupe de vrais joueurs (30 à 100).** Elle n'est pas prête
pour un lancement public : il reste des oublis qui ne sont pas dans le code (section 4) et
tout le « direct » n'a encore été vérifié par personne pendant de vrais matchs.

## 2. Vérifié cette nuit

| Point | Constat |
|---|---|
| Grosse cote | **fait** : 5, 7 et 10 acceptés, 12 et 25 refusés (« cote visée : de 2 à 10 ») |
| Cotes trop anciennes | **fait** : onglet Cotes « mises à jour le 10/11 à 12:30 » (c'était le 06/10) |
| Mes paris et Mon bilan | **fait** : « trop peu de paris (3 sur 20) » aux deux endroits |
| Coupons du jour | **fait** : « Aucun coupon ce jour-là : aucun match ne respectait les règles… » ; historique avec le score final et « pas de coupon Équilibré ni Audacieux ce jour-là » |
| Accueil | **fait** : « à reproduire dans 1xBet en un geste » (plus de promesse de code) |
| Notifications | **fait** : Tout lire, Tout effacer, glisser |
| Montante | **fait** : chance d'aller au bout, explication, suggestions |
| Vitesse | `/bets` 0,36 s ; `/predictions/upcoming` 0,64 s ; `/reliability` 0,15 s ; Coupon intelligent ≈ 1 s ; **`/offers/main` 3,7 s pour 60 matchs** (8,5 s le 7/11 : mieux, encore lent) |
| Parcours complet | pari n° 64 placé dans l'application le 10/11 : composer, ajouter, mise, confirmation, « Pari placé » |

## 3. Défauts encore présents

| # | Gravité | Constat | Piste |
|---|---|---|---|
| 1 | moyenne | **Noms des pays toujours en anglais** en production (Ghana, Somalia, Congo DR, Ivory Coast, Central African Republic, Türkiye, Belgium, « FYR Macedonia »). Le correctif (`5c06fcf`) renomme « à la mise à jour des sélections » : cette mise à jour n'a pas été lancée | console : lancer la mise à jour des sélections ; vérifier ensuite |
| 2 | moyenne | **Étapes 6 à 8 (chances en direct, onglet En direct, règlement pendant le match) jamais vérifiées en conditions réelles** : aucun match depuis leur publication. Le plan prévoyait « étape suivante seulement après la vérification du testeur » ; les étapes 1 à 8 ont été publiées à la suite | vérification pendant les matchs du jeudi 12 (CAN, Ligue des Nations) avant d'aller plus loin |
| 3 | moyenne | **Double chance** : l'étude (étape 5) la trouve juste sur les saisons passées ; les paris réels donnent 48 % pour 71 % (33 sélections). Les deux peuvent être vrais (peu de paris), mais elle reste dans les profils Sûr | suivre dans l'Observatoire ; revoir à 100 sélections |
| 4 | faible | `/offers/main` : 3,7 s | préparer ces cotes à l'avance |
| 5 | faible | Match déplacé (Cameroun – Namibie, du 11 au 12) sans aucun avertissement dans un pari en cours | mention « horaire modifié » |
| 6 | faible | Écran Wave, lien Google, Langue, « Ce qui est partagé », historique d'une cote : non vérifiés dans la nouvelle interface (mes scripts ne les atteignent pas) | à voir à la main par le fondateur |

## 4. Ce qui a été oublié (hors écrans)

1. **Mentions légales incomplètes en ligne** : « Contact : **[adresse e-mail à compléter]** »
   apparaît 2 fois dans les Conditions d'utilisation et 4 fois dans la Politique de
   confidentialité publiées. À compléter avant tout joueur réel.
2. **Aucun audit de sécurité** n'a été fait (voir sections 5 et 6).
3. **Aucun vrai joueur** : 3 testeurs, dont le fondateur et le compte de test.
4. **Fin d'abonnement jamais essayée** : ce que voit un joueur quand Premium expire, le
   rappel avant la fin, le renouvellement par Wave.
5. **Suppression de compte, mot de passe oublié (WhatsApp), connexion Google** : jamais
   essayés de bout en bout.
6. **Alerte en cas de panne** : rien ne prévient le fondateur si le serveur, le suivi des
   matchs ou la collecte des cotes s'arrêtent.
7. **Restauration d'une sauvegarde** : testée en CI, jamais sur le vrai serveur.
8. **Charge** : jamais essayé avec 100 ou 1 000 joueurs en même temps.
9. **Une seule source de données** (API-Football) : quota et panne à prévoir ; message
   clair dans l'application si la source ne répond plus.
10. **Adresse `duckdns.org`** et numéro Wave personnel : à remplacer avant un lancement public.
11. **Règles locales** sur les applications liées aux paris (Côte d'Ivoire) : à vérifier
    par le fondateur.

## 5. Premiers contrôles de sécurité (depuis l'extérieur, sans rien casser)

| Contrôle | Résultat |
|---|---|
| Lire le pari ou la montante d'un autre joueur | **refusé** (404) |
| Console et routes d'administration sans droit | **refusé** (401) |
| Sans jeton, jeton faux | **refusé** (401) |
| Fonctions Premium avec un compte gratuit | **refusé** (403) |
| Mise négative, mise supérieure au solde | **refusé** (422, 409) |
| Cote inventée (50 au lieu de 1,20) | **refusé** (« la cote a baissé : 50 → 1,20 ») |
| Origine web inconnue (CORS) | non autorisée |
| HTTPS forcé (HSTS), `nosniff`, `referrer-policy` | présents |
| Secrets dans le dépôt | aucun fichier `.env` ni clé suivi par git (historique non vérifié) |
| **`/api/v1/openapi.json` public** | **à corriger** : la liste complète des routes (administration comprise) est lisible par tous |
| **Pas de `Content-Security-Policy` ni `X-Frame-Options`** sur `/app/` | **à corriger** : la page peut être affichée dans le cadre d'un autre site |

Ces contrôles sont superficiels : ils ne remplacent pas un audit du code.

## 6. Outils d'audit de sécurité recommandés (vérifiés sur GitHub le 11/11)

| Rang | Dépôt | Étoiles, dernière activité, licence | À quoi il sert |
|---|---|---|---|
| 1 | `cloudflare/security-audit-skill` | 69 000 · 14/09/2026 · MIT | **audit complet du dépôt** en 6 phases (cartographie, chasse, vérification indépendante de chaque faille, rapport) ; les auteurs conseillent plusieurs passes (une passe trouve environ la moitié) |
| 2 | `trailofbits/skills` | 8 100 · 06/11/2026 · CC-BY-SA | boîte à outils d'un cabinet d'audit reconnu ; pour FootProba : `insecure-defaults`, `static-analysis` (Semgrep, CodeQL), `supply-chain-risk-auditor` (dépendances PyPI), `sharp-edges`, `differential-review`, `fp-check`, `firebase-apk-scanner` (APK Android) |
| 3 | `anthropics/claude-code-security-review` | 6 800 · 11/02/2026 · MIT | commande `/security-review` (changements en cours) et action GitHub qui relit chaque modification |
| — | `NVIDIA/SkillSpector` | 25 000 · 10/11/2026 · Apache-2.0 | **à passer avant d'installer un outil tiers** : vérifie qu'il n'est pas lui-même malveillant |

Outils classiques à ajouter (ce ne sont pas des « skills ») : **Gitleaks** (secrets dans tout
l'historique git), **pip-audit** et **Bandit** (Python), **Semgrep**, **Trivy** (image Docker
et configuration du serveur), **OWASP ZAP** ou **Nuclei** (attaque du site en ligne,
uniquement sur son propre site), **MobSF** (APK Android). Référence : **OWASP ASVS**.

Écartés : les petits dépôts peu suivis (10 à 80 étoiles) trouvés par la recherche. Aucun
outil dédié à Dart / Flutter n'existe dans ces collections : l'application sera couverte par
Semgrep, MobSF et la revue manuelle.

### Ordre conseillé

1. Gitleaks sur tout l'historique ; pip-audit ; Trivy sur l'image.
2. `cloudflare/security-audit-skill` : 2 ou 3 passes sur `backend/`.
3. Trail of Bits `insecure-defaults` et `static-analysis` ; `supply-chain-risk-auditor`.
4. Corriger, puis ZAP ou Nuclei sur un serveur de test (pas la production en journée).
5. Action `claude-code-security-review` sur chaque modification, en permanence.

Zones à regarder en premier : connexion et jetons, mot de passe provisoire, console
d'administration, activation de Premium après un paiement Wave, argent fictif (solde, mises,
règlements), limitation des tentatives, envoi d'événements bêta.
