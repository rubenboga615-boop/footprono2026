#!/data/data/com.termux/files/usr/bin/bash
# PostgreSQL natif Termux pour FootProno.
#
# À lancer dans Termux (PAS dans Ubuntu) : sous proot, PostgreSQL ne peut pas
# démarrer (propriété des fichiers simulée). Ubuntu s'y connecte via 127.0.0.1.
#
#   bash postgres.sh setup    # une fois : installe, initialise, crée rôle et bases
#   bash postgres.sh start | stop | status
set -euo pipefail

[ -n "${PREFIX:-}" ] && command -v pkg >/dev/null 2>&1 \
    || { echo "Ce script se lance dans Termux natif, pas dans Ubuntu." >&2; exit 1; }

PGDATA="${FP_PGDATA:-$PREFIX/var/lib/postgresql}"
PGPORT="${FP_PG_PORT:-5432}"
DB_NAME="${FP_DB_NAME:-footprono}"
DB_USER="${FP_DB_USER:-footprono}"
DB_PASSWORD="${FP_DB_PASSWORD:-footprono}"
# Socket Unix explicite dans $PREFIX/tmp (valeur par défaut de Termux) : les
# commandes psql/pg_ctl ci-dessous la trouvent sans dépendre de la compilation.
SOCKET_DIR="$PREFIX/tmp"
export PGPORT PGHOST="$SOCKET_DIR"

running() { pg_ctl -D "$PGDATA" status >/dev/null 2>&1; }

start() {
    if running; then
        echo "PostgreSQL déjà actif (port $PGPORT)"
    else
        mkdir -p "$SOCKET_DIR"
        pg_ctl -D "$PGDATA" -l "$PGDATA/server.log" \
            -o "-p $PGPORT -k $SOCKET_DIR -c listen_addresses=127.0.0.1" -w start
    fi
}

case "${1:-}" in
    setup)
        command -v initdb >/dev/null 2>&1 || pkg install -y postgresql
        if [ ! -f "$PGDATA/PG_VERSION" ]; then
            mkdir -p "$PGDATA"
            # Socket local sans mot de passe (utilisateur Termux uniquement),
            # connexions TCP (Ubuntu, application) avec mot de passe.
            initdb -D "$PGDATA" --auth-local=trust --auth-host=scram-sha-256 -E UTF8
        fi
        start
        psql_admin() { psql -d postgres -v ON_ERROR_STOP=1 -qtA "$@"; }
        if [ "$(psql_admin -c "SELECT 1 FROM pg_roles WHERE rolname = '$DB_USER'")" != "1" ]; then
            psql_admin -c "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD' CREATEDB"
        fi
        for db in "$DB_NAME" "${DB_NAME}_test"; do
            if [ "$(psql_admin -c "SELECT 1 FROM pg_database WHERE datname = '$db'")" != "1" ]; then
                psql_admin -c "CREATE DATABASE $db OWNER $DB_USER"
            fi
        done
        echo "PostgreSQL prêt : 127.0.0.1:$PGPORT, bases $DB_NAME et ${DB_NAME}_test"
        ;;
    start) start ;;
    stop) running && pg_ctl -D "$PGDATA" -m fast stop || echo "PostgreSQL déjà arrêté" ;;
    status) running && echo "PostgreSQL actif (port $PGPORT)" || echo "PostgreSQL arrêté" ;;
    *) echo "usage : bash $0 {setup|start|stop|status}" >&2; exit 2 ;;
esac
