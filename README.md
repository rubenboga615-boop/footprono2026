# FootProno 2026

Serveur de probabilités et d'analyses de matchs de football, par abonnement.
Nouveau projet, reconstruit de zéro à partir de l'audit de l'ancienne version
(voir [docs/AUDIT_ANCIEN_PROJET.md](docs/AUDIT_ANCIEN_PROJET.md)).

- **Backend** : FastAPI (async), PostgreSQL, Redis, Celery (worker + beat)
- **Frontend** : Flutter (web + APK Android), client du contrat OpenAPI
- **Déploiement** : Ubuntu/Debian — y compris Ubuntu dans Termux (proot-distro) pour le développement sur téléphone — et serveur distant via Docker Compose

Documentation :

| Document | Contenu |
|---|---|
| [docs/PRINCIPES.md](docs/PRINCIPES.md) | Règles non négociables du projet |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture cible et responsabilités des modules |
| [docs/FEUILLE_DE_ROUTE.md](docs/FEUILLE_DE_ROUTE.md) | Phases, dépendances et critères de validation |
| [docs/AUDIT_ANCIEN_PROJET.md](docs/AUDIT_ANCIEN_PROJET.md) | Conclusions vérifiées de l'audit de l'ancien projet |

## État actuel

Phase 0 (fondations) : serveur d'API, configuration, journalisation structurée,
gestion d'erreurs unique, PostgreSQL + migrations, Redis, Celery, métriques,
sondes de santé, tests d'intégration, CI, déploiement Docker et Termux.

## Démarrage local (Ubuntu, y compris Ubuntu dans Termux)

```bash
bash scripts/local/setup.sh    # une fois (idempotent) : paquets, PostgreSQL, Redis, Python 3.12, migrations
bash scripts/local/start.sh    # PostgreSQL, Redis, API (port 8000), worker, beat
bash scripts/local/status.sh   # état des services
bash scripts/local/test.sh     # lint, typage, tests
bash scripts/local/stop.sh     # arrête API/worker/beat (--all : aussi PostgreSQL et Redis)
```

Sous Ubuntu dans Termux, lancer `termux-wake-lock` dans Termux (hors Ubuntu)
pour empêcher Android de mettre le serveur en veille. PostgreSQL est configuré
avec `dynamic_shared_memory_type = mmap`, requis sous proot.

API : `http://127.0.0.1:8000/api/v1/health`, documentation interactive :
`http://127.0.0.1:8000/docs` (désactivée en production).

## Déploiement serveur

```bash
cp deploy/.env.example deploy/.env    # remplir domaine, secrets, mots de passe
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
```

Services : `postgres`, `redis`, `migrate` (applique les migrations puis s'arrête),
`api`, `worker`, `beat`, `caddy` (HTTPS automatique).

## Développement

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.lock && .venv/bin/pip install --no-deps -e .
export FP_TEST_DATABASE_URL=postgresql+asyncpg://footprono:footprono@127.0.0.1:5432/footprono_test
export FP_TEST_REDIS_URL=redis://127.0.0.1:6379/15
.venv/bin/pytest
```

Les dépendances sont verrouillées dans `backend/requirements.lock` et
`backend/requirements-dev.lock` (générés par `uv pip compile --universal`
depuis `pyproject.toml`).
