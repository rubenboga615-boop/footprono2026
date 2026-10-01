# Production (phase 6)

Serveur distant : **Hetzner CX22** (2 processeurs, 4 Go, Ubuntu 24.04),
adresse **DuckDNS** (sous-domaine gratuit, HTTPS Let's Encrypt), paiement
**CinetPay** (Mobile Money). Tout tourne dans Docker : PostgreSQL 17, Redis,
API, worker, beat, sauvegardes, Caddy (HTTPS).

## 1. Clé SSH (sur le téléphone, dans Termux)

```bash
pkg install -y openssh
ssh-keygen -t ed25519          # Entrée trois fois
cat ~/.ssh/id_ed25519.pub      # à copier dans Hetzner (étape 2)
```

La clé privée reste sur le téléphone ; le serveur n'accepte qu'elle
(connexion par mot de passe désactivée par l'installation).

## 2. Serveur Hetzner

1. Compte sur <https://www.hetzner.com/cloud> (carte bancaire ou PayPal).
2. Nouveau projet → **Ajouter un serveur** :
   emplacement au choix, image **Ubuntu 24.04**, type **CX22**,
   **Clé SSH** : coller la clé de l'étape 1. Le reste par défaut.
3. Noter l'**adresse IPv4** du serveur.

## 3. Adresse DuckDNS

1. <https://www.duckdns.org> → connexion (Google ou GitHub).
2. Choisir un sous-domaine (par ex. `footprono`) → **add domain**.
3. Dans **current ip**, mettre l'IPv4 du serveur → **update ip**.

L'IP d'un serveur Hetzner ne change pas : rien à mettre à jour ensuite.

## 4. Installation

```bash
ssh root@<ip du serveur>
curl -fsSL https://raw.githubusercontent.com/rubenboga615-boop/footprono2026/main/deploy/install-server.sh \
  | bash -s -- <sous-domaine>.duckdns.org
```

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
collectées), la clé Firebase et la clé API-Football ; la base du serveur
est sauvegardée avant d'être remplacée. Ensuite, **arrêter le serveur
Termux** (`bash scripts/termux/stop.sh`) : sinon les deux collectent et le
quota API-Football est consommé deux fois.

## 6. Application

GitHub → dépôt → Settings → Secrets and variables → Actions → **Variables**
→ `FP_SERVER_URL` = `https://<sous-domaine>.duckdns.org`. Les APK construits
ensuite se connectent au serveur. Sur un téléphone déjà installé :
Profil → Serveur → la même adresse.

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
- Surveillance externe gratuite : <https://uptimerobot.com>, moniteur HTTPS
  sur cette adresse toutes les 5 minutes, alerte par e-mail.
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
| Paiement vérifié auprès de CinetPay, jamais sur la seule notification | (à venir) |
| HTTP en clair dans l'APK (Termux) à retirer après la bascule | (à faire) |
