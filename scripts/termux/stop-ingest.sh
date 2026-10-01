#!/usr/bin/env bash
# Arrête une ingestion en cours (lancée par ingest.sh, au premier plan ou avec nohup).
#   bash scripts/termux/stop-ingest.sh
# Le fichier (une ligue, une saison) en cours n'est pas enregistré : il sera repris au
# prochain lancement. Les fichiers déjà terminés restent en base.
set -uo pipefail

pids=$(pgrep -f 'footprono-ingest' || true)
if [ -z "$pids" ]; then
    echo "Aucune ingestion en cours."
    exit 0
fi
echo "Arrêt de l'ingestion (processus : $(echo "$pids" | tr '\n' ' '))"
kill $pids
for _ in 1 2 3 4 5 6 7 8 9 10; do
    pgrep -f 'footprono-ingest' >/dev/null || { echo "Ingestion arrêtée."; exit 0; }
    sleep 1
done
echo "Toujours active après 10 s : arrêt forcé."
pkill -9 -f 'footprono-ingest'
echo "Ingestion arrêtée."
