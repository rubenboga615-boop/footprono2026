#!/usr/bin/env bash
# Installation (ou mise à jour) du serveur FootProno sur Ubuntu 24.04, lancée
# depuis Termux (le dépôt est privé : le script part du téléphone) :
#   ssh root@<ip> 'bash -s -- monsousdomaine.duckdns.org' < deploy/install-server.sh
# La première fois, le serveur crée sa clé de lecture du dépôt (« deploy key »)
# et l'affiche : l'ajouter sur GitHub, puis relancer la même commande.
# Relancer met à jour le code et redémarre (secrets et base conservés).
# Voir docs/PRODUCTION.md.
set -euo pipefail

DOMAIN="${1:-}"
BRANCH="${FP_BRANCH:-main}"
REPO="${FP_REPO:-git@github.com:rubenboga615-boop/footprono2026.git}"
DEPLOY_KEY=/root/.ssh/footprono_deploy
DIR=/opt/footprono

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mAttention :\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mErreur :\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "lancer en root (ssh root@<ip du serveur>)"
[ -n "$DOMAIN" ] || die "adresse manquante : bash install-server.sh monsousdomaine.duckdns.org"

log "Système à jour, Docker, pare-feu"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -yq
apt-get install -yq git curl ca-certificates ufw fail2ban unattended-upgrades \
    docker.io docker-compose-v2
systemctl enable --now docker fail2ban unattended-upgrades

# 2 Go d'échange : marge pour le moteur de prédiction (4 Go de mémoire).
if ! swapon --show | grep -q /swapfile; then
    fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null
    swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Seuls SSH et le site (HTTP pour le certificat, HTTPS) sont ouverts.
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw allow 443/udp >/dev/null
ufw --force enable >/dev/null

# Connexion SSH par clé uniquement, si une clé est installée (sinon on ne
# risque pas de bloquer l'accès).
if [ -s /root/.ssh/authorized_keys ]; then
    printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\n' \
        > /etc/ssh/sshd_config.d/50-footprono.conf
    systemctl reload ssh || systemctl reload sshd || true
else
    warn "aucune clé SSH : la connexion par mot de passe reste active"
fi

# Dépôt privé : clé SSH du serveur, en lecture seule, déclarée sur GitHub.
mkdir -p /root/.ssh && chmod 700 /root/.ssh
if [ ! -f "$DEPLOY_KEY" ]; then
    ssh-keygen -q -t ed25519 -N "" -C "serveur-footprono" -f "$DEPLOY_KEY"
fi
if ! grep -q "footprono_deploy" /root/.ssh/config 2>/dev/null; then
    printf 'Host github.com\n  IdentityFile %s\n  IdentitiesOnly yes\n' "$DEPLOY_KEY" >> /root/.ssh/config
fi
ssh-keyscan -q github.com >> /root/.ssh/known_hosts 2>/dev/null
sort -u -o /root/.ssh/known_hosts /root/.ssh/known_hosts
if ! git ls-remote -q "$REPO" >/dev/null 2>&1; then
    echo
    warn "le serveur n'a pas encore accès au dépôt privé. Sur GitHub : dépôt footprono2026"
    echo "  → Settings → Deploy keys → Add deploy key (titre : serveur, « Allow write » décoché),"
    echo "  coller cette clé :"
    echo
    cat "$DEPLOY_KEY.pub"
    echo
    echo "Puis relancer exactement la même commande."
    exit 2
fi

log "Code ($BRANCH)"
if [ -d "$DIR/.git" ]; then
    git -C "$DIR" fetch -q origin "$BRANCH"
    git -C "$DIR" checkout -q "$BRANCH"
    git -C "$DIR" reset -q --hard "origin/$BRANCH"
else
    git clone -q --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR/deploy"

if [ ! -f .env ]; then
    log "Secrets générés (deploy/.env, lisible par root seul)"
    cp .env.example .env
    sed -i \
        -e "s|^FP_SECRET_KEY=.*|FP_SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n/+=')|" \
        -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" \
        .env
fi
sed -i "s|^FP_DOMAIN=.*|FP_DOMAIN=$DOMAIN|" .env
chmod 600 .env
[ -f secrets/firebase.json ] && sed -i \
    "s|^FP_FCM_CREDENTIALS_FILE=.*|FP_FCM_CREDENTIALS_FILE=/secrets/firebase.json|" .env

# Le certificat HTTPS n'est délivré que si l'adresse pointe vers ce serveur.
ip="$(curl -fsS4 https://api.ipify.org || true)"
dns="$(getent ahostsv4 "$DOMAIN" | awk 'NR==1 {print $1}' || true)"
if [ -n "$ip" ] && [ "$dns" != "$ip" ]; then
    warn "$DOMAIN pointe vers « ${dns:-rien} », ce serveur est $ip : corriger l'IP sur duckdns.org"
fi

log "Construction et démarrage (première fois : quelques minutes)"
docker compose -f docker-compose.yml --env-file .env up -d --build --remove-orphans

log "Attente de https://$DOMAIN/api/v1/ready"
for _ in $(seq 1 60); do
    if curl -fsS "https://$DOMAIN/api/v1/ready" >/dev/null 2>&1; then
        log "Serveur prêt : https://$DOMAIN"
        docker compose -f docker-compose.yml --env-file .env ps --format 'table {{.Service}}\t{{.Status}}'
        exit 0
    fi
    sleep 5
done
warn "pas de réponse en HTTPS après 5 minutes. Diagnostic :"
echo "  docker compose -f $DIR/deploy/docker-compose.yml logs --tail 50 caddy api"
exit 1
