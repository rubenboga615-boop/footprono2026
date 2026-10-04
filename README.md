# FootProba 2026

Serveur de probabilités et d'analyses de matchs de football, par abonnement.
Nouveau projet, reconstruit de zéro à partir de l'audit de l'ancienne version
(voir [docs/AUDIT_ANCIEN_PROJET.md](docs/AUDIT_ANCIEN_PROJET.md)).

- **Backend** : FastAPI (async), PostgreSQL, Redis, Celery (worker + beat)
- **Frontend** : Flutter (web + APK Android), client du contrat OpenAPI
- **Déploiement** : Termux natif (développement et tests sur téléphone), serveur distant via Docker Compose

Documentation :

| Document | Contenu |
|---|---|
| [docs/PRINCIPES.md](docs/PRINCIPES.md) | Règles non négociables du projet |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture cible et responsabilités des modules |
| [docs/FEUILLE_DE_ROUTE.md](docs/FEUILLE_DE_ROUTE.md) | Phases, dépendances et critères de validation |
| [docs/MOTEUR.md](docs/MOTEUR.md) | Moteur de prédiction : méthode, réglages, résultats mesurés |
| [docs/BOOKMAKER.md](docs/BOOKMAKER.md) | Comptes, bookmaker virtuel, règlement, montante, notifications (phase 4) |
| [docs/PRODUIT.md](docs/PRODUIT.md) | Formules gratuite / Premium, administration (phase 5) |
| [docs/APPLICATION.md](docs/APPLICATION.md) | Application Flutter : installation (APK, web), écrans (phase 5) |
| [docs/PRODUCTION.md](docs/PRODUCTION.md) | Serveur distant, sauvegardes, supervision, sécurité (phase 6) |
| [docs/MARCHES.md](docs/MARCHES.md) | Marchés couverts par le moteur et leur vérification |
| [docs/DESIGN.md](docs/DESIGN.md) | Direction visuelle retenue (verre violet), couleurs, typographie, écrans |
| [docs/DONNEES.md](docs/DONNEES.md) | Sources, règles d'ingestion, contrôles de qualité, API de lecture |
| [docs/AUDIT_ANCIEN_PROJET.md](docs/AUDIT_ANCIEN_PROJET.md) | Conclusions vérifiées de l'audit de l'ancien projet |

## État actuel

- Phase 0 (fondations) ✅ : serveur d'API, configuration, journalisation structurée,
  gestion d'erreurs unique, PostgreSQL + migrations, Redis, Celery, métriques,
  sondes de santé, tests d'intégration, CI, déploiement Docker et scripts Termux.
- Phase 1 (données) ✅ : ingestion football-data + Understat, référentiel des
  équipes, archivage des fichiers bruts, contrôles de qualité, mise à jour
  quotidienne, API de lecture ; téléchargement réel validé sur le téléphone
  (voir [docs/DONNEES.md](docs/DONNEES.md)).
- Extension de la phase 1 : statistiques par équipe et par mi-temps
  d'API-Football (corners, cartons, tirs… depuis 2024-25), import des fichiers
  du collecteur ou téléchargement avec la clé `FP_API_FOOTBALL_KEY`.

## Démarrage sur Termux (natif)

À lancer dans **Termux**, pas dans Ubuntu/proot : sous proot, PostgreSQL ne
peut pas démarrer (propriété des fichiers simulée).

```bash
git clone https://github.com/rubenboga615-boop/footprono2026.git
cd footprono2026 && git checkout claude/footprono-technical-audit-9gpx2x
bash scripts/termux/setup.sh    # une fois (idempotent) : paquets, PostgreSQL, Redis, venv, migrations
bash scripts/termux/setup.sh --dev   # facultatif : + outils de test (pytest, mypy, ruff via pkg)
bash scripts/termux/start.sh    # PostgreSQL, Redis, API (port 8000), worker, beat
bash scripts/termux/status.sh   # état des services
bash scripts/termux/test.sh     # lint, typage, tests
bash scripts/termux/ingest.sh all   # télécharge l'historique 2016 → saison en cours, puis contrôle la qualité
bash scripts/termux/ingest.sh quality   # contrôles de qualité seuls
bash scripts/termux/stop.sh     # arrête API/worker/beat (--all : aussi PostgreSQL et Redis)
```

FootProba utilise **ses propres instances**, isolées des autres projets Termux :
PostgreSQL dans `$PREFIX/var/lib/footprono/postgresql` (port 5433) et Redis
(port 6380). Les fichiers bruts téléchargés sont archivés dans
`$PREFIX/var/lib/footprono/raw`. Un PostgreSQL ou un Redis existant n'est jamais modifié. Ports
modifiables : `FP_PG_PORT`, `FP_REDIS_PORT`, `FP_PORT` (API).

`start.sh` active `termux-wake-lock` pour empêcher Android de mettre le
serveur en veille. PyPI ne fournit pas de paquets précompilés pour Android :
la première installation compile pydantic-core (Rust) et quelques extensions C,
ce qui prend plusieurs minutes. Les paquets compilés restent dans le cache de
pip, une relance ne recompile rien. ruff est installé précompilé via `pkg`.

API : `http://127.0.0.1:8000/api/v1/health`, documentation interactive :
`http://127.0.0.1:8000/docs` (désactivée en production).

## Déploiement serveur

```bash
cp deploy/.env.example deploy/.env    # remplir domaine, secrets, mots de passe
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
```

Services : `postgres`, `redis`, `migrate` (applique les migrations puis s'arrête),
`api`, `worker`, `beat`, `caddy` (HTTPS automatique).

Historique initial (une fois), ensuite `beat` met à jour la saison en cours chaque matin :

```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/.env run --rm migrate footprono-ingest all
```

## Développement

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.lock && .venv/bin/pip install --no-deps -e .
export FP_TEST_DATABASE_URL=postgresql+asyncpg://footprono:footprono@127.0.0.1:5432/footprono_test
export FP_TEST_REDIS_URL=redis://127.0.0.1:6379/15
.venv/bin/pytest
```

Les dépendances sont verrouillées dans `backend/requirements.lock`,
`backend/requirements-test.lock` et `backend/requirements-dev.lock` (générés par
`uv pip compile --universal` depuis `pyproject.toml`).

Les tests d'ingestion utilisent des copies non modifiées de fichiers réels
(`backend/tests/fixtures`).
