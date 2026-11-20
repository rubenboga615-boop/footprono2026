#!/usr/bin/env bash
# Export des données football du serveur pour les études du moteur, SANS données
# personnelles : comptes, portefeuilles, paris, montantes, notifications, appareils,
# paiements, abonnements, mode bêta, journal et réglages de la console sont exportés vides
# (structure seulement). À lancer sur le serveur :
#   ssh root@IP 'bash -s' < deploy/export-data.sh
# Le fichier arrive dans /opt/footprono/exports/ ; le récupérer avec scp.
# Ne jamais le mettre dans le dépôt (public) : le donner à la session par un envoi de fichier.
set -euo pipefail
DIR=/opt/footprono
cd "$DIR/deploy"
mkdir -p "$DIR/exports"
PERSONAL=(users wallets wallet_entries bets bet_selections montantes montante_steps
    notifications push_devices payments subscription_events beta_events
    admin_actions admin_jobs admin_job_lines play_plans odds_alerts odds_alert_hits
    # Réglages de la console : contiennent le nom secret du canal ntfy des alertes (audit
    # du 20/11/2026, point E ; qui l'a peut envoyer de fausses alertes au fondateur).
    app_settings)
args=()
for t in "${PERSONAL[@]}"; do args+=(--exclude-table-data="$t"); done
OUT="footprono-donnees-$(date +%Y%m%d).dump"
echo "Export des données football (sans données personnelles)…"
docker compose -f docker-compose.yml --env-file .env exec -T postgres \
    sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -Z 9 '"${args[*]}" \
    > "$DIR/exports/$OUT"
echo "Fichier prêt : $DIR/exports/$OUT ($(du -h "$DIR/exports/$OUT" | cut -f1))"
