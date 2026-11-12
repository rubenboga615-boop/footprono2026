# Revue de sécurité du code — 12 novembre 2026

Revue en lecture seule du serveur (`backend/`), du déploiement (`deploy/`) et de quelques
points de l'application (`app/`), au commit `36fc52b`, plus des contrôles sur le site en
ligne (`9115349`). Outils : lecture du code, **pip-audit 2.10** (failles connues des
bibliothèques), **Bandit 1.9** (analyse du code Python), **Gitleaks 8.28** (secrets dans les
316 commits de l'historique). Rien n'a été modifié dans le code.

## Verdict

**Le code est sérieux et bien protégé sur l'essentiel.** Je n'ai trouvé aucune faille
critique : pas de moyen de se connecter sans mot de passe, d'entrer dans la console, de
devenir Premium sans payer ou de toucher au solde d'un autre joueur. Il reste un défaut de
fond (règlement en double possible) et des réglages à resserrer avant d'avoir de vrais
joueurs.

Limite : une seule passe, faite par une personne ; un audit complet (outils de la section 4
du bilan du 11/11, plusieurs passes) reste nécessaire avant un lancement public.

## 1. Ce qui est bien fait (vérifié dans le code)

| Domaine | Constat |
|---|---|
| Mots de passe | scrypt avec sel aléatoire, comparaison à temps constant (`accounts/security.py`) |
| Jetons | JWT HS256, clé d'au moins 32 caractères obligatoire en production ; jetons annulés après changement de mot de passe ou « déconnecter partout » |
| Tentatives | 10 échecs par numéro et 50 par adresse en 15 min (connexion, console, changement et suppression de compte) ; 10 inscriptions par adresse et par heure |
| Console | jeton séparé (12 h), session enregistrée et annulable, rôle `admin` vérifié, **code de sécurité à 6 chiffres obligatoire**, code déjà utilisé refusé, journal des actions ; en-têtes stricts (CSP, `DENY`) |
| Fichiers de la console | noms filtrés (pas de `../`), liens de téléchargement signés et limités dans le temps |
| Paiements | un « paiement reçu » n'est **jamais cru** : revérifié auprès de Wave, Paystack ou CinetPay, montant et devise contrôlés, ligne verrouillée, Premium accordé une seule fois ; signature HMAC pour Paystack |
| Connexion Google | jeton vérifié (certificats de Google, projet, émetteur, expiration, e-mail vérifié) |
| Argent fictif | solde verrouillé à chaque mouvement ; mise supérieure au solde refusée ; cote inventée refusée (« la cote a baissé ») |
| Données des autres | pari, montante, paiement d'un autre joueur : 404 |
| Mot de passe provisoire | aléatoire (12 caractères), jamais enregistré en clair, téléphones déconnectés |
| Secrets | aucun secret réel dans les 316 commits (Gitleaks) : seulement des clés de test et les clés Firebase, publiques par nature |
| Code Python | Bandit : aucun problème réel (2 fausses alertes) |
| Application | serveur figé dans la version publiée (réglage « Serveur » caché) ; pas de trafic en clair |

## 2. À corriger

| # | Gravité | Problème | Où | Ce qui peut arriver | Correction proposée |
|---|---|---|---|---|---|
| 1 | **moyenne** | **Règlement en double possible.** Le règlement des paris tourne dans `follow_live` (toutes les 2 min) et dans `ingest_current_season` (6 h 15). Le worker Celery exécute plusieurs tâches en parallèle (aucune option `--concurrency`), et `settle_bets` lit les paris « open » **sans verrou** | `worker/tasks.py` (`_settle`, l. 37 et 191), `bookmaker/settlement.py` (`settle_bets`, l. 443) | si deux règlements se chevauchent (journée chargée, relevé de plus de 2 min, action de la console), un pari gagné est **payé deux fois**, la montante avance deux fois, deux notifications | verrou Redis autour de `_settle` (une seule exécution à la fois), ou `SELECT … FOR UPDATE SKIP LOCKED` sur les paris ; même chose pour `smart_coupon.settle_pending` et `follow_live` (deux relevés simultanés = quota gaspillé) |
| 2 | moyenne | **Liste complète des routes publique** : `/api/v1/openapi.json` répond à tout le monde en production (111 routes, dont 36 d'administration) | `main.py` l. 79 (`openapi_url` toujours défini ; seul `/docs` est coupé) | carte toute faite pour un attaquant | `openapi_url=None` en production |
| 3 | moyenne | **Configuration du serveur en ligne en retard sur le dépôt** : le `Caddyfile` du dépôt ajoute `X-Frame-Options` et `Permissions-Policy`, absents du site en ligne. Et il n'y a **pas de `Content-Security-Policy` sur `/app/`** | `deploy/Caddyfile` | page affichable dans le cadre d'un autre site (clics piégés) ; sans CSP, une faille d'injection volerait le jeton de 30 jours rangé dans le navigateur | redéployer Caddy ; ajouter une CSP adaptée à Flutter web (`script-src 'self'`, sources de Firebase et de Google seulement) |
| 4 | moyenne | **Bibliothèque `certifi` vulnérable** (PYSEC-2026-4320 : certificats d'une autorité compromise encore acceptés) | `backend/requirements.lock` (2026.7.22) | interception des connexions sortantes (API-Football, Wave…) par un attaquant placé sur le réseau | passer à certifi 2026.10.19 ou plus, reconstruire l'image |
| 5 | faible à moyenne | **Inscription sans vérification du numéro** : n'importe qui peut créer un compte avec le numéro d'un autre ; le vrai propriétaire ne peut plus s'inscrire | `accounts/service.py` (`register`) | numéro « squatté » ; et la réinitialisation par WhatsApp repose sur ce numéro | code par SMS ou WhatsApp à l'inscription (plus tard) ; en attendant, procédure écrite : ne donner un mot de passe provisoire **que si le message WhatsApp vient du numéro du compte** |
| 6 | faible | Jeton de connexion de **30 jours** rangé en clair (`SharedPreferences` sur Android, `localStorage` sur le web) | `app/lib/state/app_state.dart` l. 442 | un téléphone volé ou une injection donne 30 jours d'accès | stockage chiffré sur Android (`flutter_secure_storage`), jeton plus court renouvelé automatiquement |
| 7 | faible | Les adresses de notification des paiements (Wave, CinetPay) n'ont **aucune limite de fréquence** et déclenchent un appel au prestataire | `api/v1/payments.py` | appels répétés vers Wave avec notre clé (blocage par Wave possible) | limite par adresse, comme la connexion |
| 8 | faible | La connexion de la console répond « ce compte n'est pas administrateur » **après un mot de passe juste**, et la connexion est plus rapide quand le numéro n'existe pas | `api/v1/console_auth.py` l. 125, `accounts/service.py` l. 150 | confirme qu'un numéro existe ou qu'un mot de passe de joueur est juste (dans la limite des 10 essais) | même message pour tous les échecs ; calcul du mot de passe même si le numéro n'existe pas |
| 9 | faible | Clés Firebase dans l'application (normal) : à **restreindre** dans Google Cloud | `app/lib/firebase_options.dart` | utilisation de la clé par un autre site ou une autre application | restreindre la clé web au domaine, la clé Android au paquet et à l'empreinte de signature |

## 3. Non vérifié (à faire avec les outils d'audit)

- Image Docker et système du serveur (Trivy), ports ouverts, mises à jour du système.
- Application Android compilée (MobSF, `firebase-apk-scanner` de Trail of Bits).
- Règles de sécurité Firebase.
- Charge (beaucoup de joueurs en même temps) et attaque du site en ligne (ZAP, Nuclei), à faire sur un serveur de test.
- Plusieurs passes de `cloudflare/security-audit-skill`.

## 4. Ordre conseillé

1. **Tout de suite** : n° 1 (verrou du règlement), n° 2 (openapi), n° 3 (redéployer Caddy + CSP), n° 4 (certifi).
2. **Avant de vrais joueurs** : n° 5 (procédure WhatsApp écrite), n° 7, n° 8, n° 9.
3. **Avant un lancement public** : n° 6, vérification du numéro, section 3.

## 3. Contrôle après recréation de Caddy (12/11, 17 h 43)

Le fondateur a recréé le conteneur Caddy (`docker compose … up -d --force-recreate caddy`).

| Point | Constat |
|---|---|
| `X-Frame-Options` | **présent** : `SAMEORIGIN` sur le site et l'API, `DENY` sur la console |
| `Permissions-Policy` | **présent** (caméra, micro, position, paiement interdits) |
| HSTS, `nosniff`, `Referrer-Policy`, CSP | présents |
| `openapi.json` | 404 |

### Nouvelle faille : `/metrics` est public

`https://footproba.duckdns.org/metrics` répond **200** avec les métriques Prometheus de
l'API : chaque route appelée (console comprise), nombre de requêtes et d'erreurs par route,
temps de réponse, mémoire, heure de démarrage du serveur. Au fil de la journée, cela révèle
l'activité du site, les routes d'administration utilisées et les pannes.

**Cause** (Caddyfile) : `respond @metrics 404` est écrit avant `handle { reverse_proxy api:8000 }`,
mais Caddy **trie les directives dans son propre ordre**, où `handle` passe **avant**
`respond` : le `handle` qui attrape tout envoie `/metrics` à l'API avant que le `respond`
soit atteint. Le commentaire « Les métriques ne sont jamais exposées publiquement » est donc
faux depuis le début.

**Correction** : mettre la règle dans un `handle` à elle, placé avant le `handle` général :

```
handle /metrics {
	respond 404
}
```

(ou faire écouter les métriques sur un port interne seulement). Puis recréer Caddy comme
ci-dessus, et vérifier que `/metrics` répond 404.
