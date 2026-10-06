# Production (phase 6)

Serveur distant : **Hetzner CX22** (2 processeurs, 4 Go, Ubuntu 24.04),
adresse **DuckDNS** (sous-domaine gratuit, HTTPS Let's Encrypt), paiement
**Paystack** (Mobile Money). Tout tourne dans Docker : PostgreSQL 17, Redis,
API, worker, beat, sauvegardes, Caddy (HTTPS).

## 1. Clé SSH (sur le téléphone, dans Termux)

```bash
pkg install -y openssh
ssh-keygen -t ed25519          # Entrée trois fois
cat ~/.ssh/id_ed25519.pub      # à copier dans Hetzner (étape 2)
```

La clé privée reste sur le téléphone ; le serveur n'accepte qu'elle
(connexion par mot de passe désactivée par l'installation).

**Dépôt privé** : la même clé donne à Termux l'accès au dépôt.
GitHub → photo de profil → Settings → **SSH and GPG keys** → New SSH key →
coller la même clé. Puis, une fois :

```bash
cd ~/footprono2026
git remote set-url origin git@github.com:rubenboga615-boop/footprono2026.git
git pull    # répondre « yes » à la première connexion
```

## 2. Serveur Hetzner

1. Compte sur <https://www.hetzner.com/cloud> (carte bancaire ou PayPal).
2. Nouveau projet → **Ajouter un serveur** :
   emplacement au choix, image **Ubuntu 24.04**, type **CX22** (ou le plus petit type
   « CX » à 4 Go de mémoire proposé au moment de l'achat, par ex. CX23),
   **Clé SSH** : coller la clé de l'étape 1. Le reste par défaut.
3. Noter l'**adresse IPv4** du serveur.

## 3. Adresse DuckDNS

1. <https://www.duckdns.org> → connexion (Google ou GitHub).
2. Choisir un sous-domaine (par ex. `footproba`) → **add domain**.
3. Dans **current ip**, mettre l'IPv4 du serveur → **update ip**.

L'IP d'un serveur Hetzner ne change pas : rien à mettre à jour ensuite.

## 4. Installation

Depuis Termux (le script part du téléphone, le dépôt étant privé) :

```bash
cd ~/footprono2026 && git pull
ssh root@<ip du serveur> 'bash -s -- <sous-domaine>.duckdns.org' < deploy/install-server.sh
```

Branche installée : `main` par défaut. Pour une autre branche, la première fois :
`ssh root@<ip> 'FP_BRANCH=<branche> bash -s -- <sous-domaine>.duckdns.org' < deploy/install-server.sh`
(les mises à jour suivantes gardent la branche installée).

La première fois, le script s'arrête et affiche la **clé du serveur** :
GitHub → dépôt footprono2026 → Settings → **Deploy keys** → Add deploy key
(titre « serveur », « Allow write access » **décoché**), coller la clé,
puis relancer la même commande. Le serveur ne peut que lire le dépôt.

Le script : mises à jour automatiques de sécurité, pare-feu (SSH, HTTP,
HTTPS seulement), fail2ban, 2 Go d'échange, Docker, secrets générés
(`/opt/footprono/deploy/.env`, lisible par root seul), démarrage, puis
vérification de `https://<sous-domaine>.duckdns.org/api/v1/ready`.
Le relancer met à jour le code (les secrets et la base sont gardés).

## 5. Transfert des données de Termux

Sur le téléphone :

```bash
cd ~/footprono2026 && git pull
bash scripts/termux/send-to-server.sh <ip du serveur>
```

Copie la base complète (comptes, paris, montantes, matchs, statistiques
collectées), la clé Firebase, la clé API-Football et l'historique API-Football
déjà collecté (la collecte de la console reprend sur le serveur, rien n'est
retéléchargé) ; la base du serveur
est sauvegardée avant d'être remplacée. Ensuite, **arrêter le serveur
Termux** (`bash scripts/termux/stop.sh`) : sinon les deux collectent et le
quota API-Football est consommé deux fois.

## 6. Application

GitHub → dépôt → Settings → Secrets and variables → Actions → **Variables**
→ `FP_SERVER_URL` = `https://<sous-domaine>.duckdns.org`. Les APK construits
ensuite se connectent au serveur (adresse intégrée, invisible pour les joueurs) :
installer le nouvel APK par-dessus l'ancien.

Publier une version sur le serveur (proposée aux téléphones à l'ouverture), depuis
Termux, avec l'archive `footprono-apk.zip` téléchargée dans GitHub Actions :

```bash
FP_SERVEUR=<ip du serveur> bash scripts/termux/publish-apk.sh "Nouveautés…"
```

## 7. Paiement Mobile Money (Paystack)

Paystack (Côte d'Ivoire : **Wave, Orange Money, MTN MoMo**, cartes). Catégorie
confirmée par Paystack : **Gaming → Prediction Services** (argent fictif, ni mise
ni gain réels). Pas de prélèvement automatique : un paiement = 30 jours, et le
joueur est prévenu 3 jours avant la fin, puis la veille.

1. Tableau de bord Paystack → **Settings → API Keys & Webhooks** :
   - **Webhook URL** : `https://<domaine>/api/v1/payments/paystack/notify`
   - **Callback URL** : laisser vide (le serveur la donne à chaque paiement :
     `https://<domaine>/api/v1/payments/paystack/return`).
2. Copier la **Secret Key** (`sk_test_…` pour essayer, puis `sk_live_…`) et la
   coller **sur le serveur seulement**, jamais dans un message ni dans le dépôt :
   `ssh root@<ip>` → `nano /opt/footprono/deploy/.env` → ligne
   `FP_PAYSTACK_SECRET_KEY=…` → enregistrer, puis relancer `install-server.sh`.
3. Essai : avec la clé `sk_test_…`, acheter Premium depuis l'application (paiement
   d'essai Paystack), vérifier que Premium s'active, puis passer à `sk_live_…`.

Fonctionnement :

- Profil → **Passer Premium** (2 000 F CFA, 30 jours) : le serveur crée le
  paiement (`POST /payments/premium`, montant envoyé à Paystack multiplié par 100
  comme Paystack l'exige, y compris en francs CFA) et l'application ouvre la page
  de paiement Paystack.
- Premium n'est accordé qu'après **vérification auprès de Paystack**
  (`/transaction/verify`), montant et devise contrôlés, une seule fois. Le webhook
  n'est qu'un signal (signature HMAC SHA-512 contrôlée) ; le retour dans
  l'application et une vérification toutes les 10 minutes (24 h) couvrent un
  webhook perdu.
- Adresse e-mail demandée par Paystack : celle du compte Google, sinon une adresse
  technique `joueur<numéro>@<domaine>` (aucune donnée personnelle).
- Payer pendant une période Premium la prolonge de 30 jours.
- CinetPay reste possible (sans clé Paystack : `FP_CINETPAY_API_KEY` et
  `FP_CINETPAY_SITE_ID`) ; un paiement est toujours vérifié auprès du prestataire
  qui l'a créé.

## Sauvegardes

- Chaque jour à 3 h (UTC) : `deploy/backups/footprono-AAAAMMJJ-HHMM.dump`,
  gardées 14 jours. Échec : fichier `deploy/backups/DERNIER_ECHEC` et
  `docker compose logs backup`.
- Copie hors du serveur (une panne de disque n'emporte pas tout), depuis
  Termux, par exemple chaque semaine :
  `scp root@<ip>:/opt/footprono/deploy/backups/$(ssh root@<ip> ls -t /opt/footprono/deploy/backups | head -1) ~/storage/downloads/`
- Restauration : `bash /opt/footprono/deploy/restore.sh <fichier.dump>`
  (la base actuelle est d'abord sauvegardée).

## Supervision

- `https://<sous-domaine>.duckdns.org/api/v1/ready` : base et Redis.
- `https://<sous-domaine>.duckdns.org/api/v1/health/tasks` : 503 si les tâches
  planifiées (worker + beat) n'ont pas tourné depuis 10 minutes.
- Surveillance externe gratuite : <https://uptimerobot.com>, deux moniteurs HTTPS
  (`/api/v1/ready` et `/api/v1/health/tasks`) toutes les 5 minutes, alerte par
  e-mail ou par l'application UptimeRobot : elle prévient même si le serveur entier
  est éteint (les alertes ntfy de la console, elles, partent du serveur).
- État des services : `docker compose -f /opt/footprono/deploy/docker-compose.yml ps`
- Journaux : `… logs --tail 100 api` (worker, beat, caddy, backup) ;
  limités à 30 Mo par service.

## Sécurité

| Point | État |
|---|---|
| HTTPS (Let's Encrypt, HSTS) | Caddy |
| Pare-feu : SSH, 80, 443 seulement ; base et Redis non exposés | install-server.sh |
| SSH par clé uniquement, fail2ban | install-server.sh |
| Mises à jour de sécurité automatiques | unattended-upgrades |
| Secrets hors dépôt (`deploy/.env`, `deploy/secrets/`) | .gitignore |
| Clé des jetons ≥ 32 caractères, refus de démarrer sinon | config.py |
| Tentatives de connexion limitées (10 échecs / 15 min / numéro) | ratelimit.py |
| Métriques non publiques (`/metrics` → 404) | Caddyfile |
| Sauvegardes quotidiennes + copie hors serveur | backup, scp |
| Paiement vérifié auprès du prestataire (Paystack, CinetPay), jamais sur la seule notification | payments/service.py |
| HTTP en clair dans l'APK (Termux) à retirer après la bascule | (à faire) |
