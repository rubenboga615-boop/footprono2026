#!/bin/sh
# Sauvegarde quotidienne de PostgreSQL (service « backup » de docker-compose.yml).
# Une sauvegarde au démarrage, puis chaque jour à BACKUP_HOUR (UTC) ; les
# fichiers de plus de KEEP_DAYS jours sont supprimés. Un échec est écrit dans
# les journaux (docker compose logs backup) et dans /backups/DERNIER_ECHEC.
set -u
dump() {
    name="/backups/footprono-$(date -u +%Y%m%d-%H%M).dump"
    if pg_dump -Fc -f "$name.tmp" && mv "$name.tmp" "$name"; then
        echo "sauvegarde ok : $name ($(du -h "$name" | cut -f1))"
        rm -f /backups/DERNIER_ECHEC
        find /backups -name 'footprono-*.dump' -mtime +"$KEEP_DAYS" -delete
    else
        rm -f "$name.tmp"
        echo "ÉCHEC de la sauvegarde $(date -u)" | tee /backups/DERNIER_ECHEC
    fi
}
dump
while true; do
    now=$(date -u +%s)
    next=$((now - now % 86400 + BACKUP_HOUR * 3600))
    [ "$next" -le "$now" ] && next=$((next + 86400))
    sleep $((next - now))
    dump
done
