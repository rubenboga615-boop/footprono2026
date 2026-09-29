# Architecture

## Vue d'ensemble

```
Sources                    Serveur FootProno                               Clients
───────                    ─────────────────                               ───────
football-data.co.uk ─┐
Understat ───────────┼─► ingestion ─► données normalisées (PostgreSQL)
API-Football ────────┘        │                 │
                              │                 ▼
                              │         moteur de features (unique)
                              │                 │
                              │      ┌──────────┴──────────┐
                              │      ▼                     ▼
                              │  entraînement +       service de prédiction
                              │  backtest +           (version d'artefact
                              │  calibration          journalisée)
                              │      │                     │
                              │      ▼                     ▼
                              │  artefacts versionnés   distribution de scores
                              │                            │
                              │                            ▼
                              │                  marchés cohérents, analyses
                              │                            │
                              ▼                            ▼
                     résultats réels ─► règlement ◄── coupons, montante,
                                        des paris        bookmaker virtuel
                                            │
                                            ▼
                                API REST /api/v1 + WebSocket ─────► Flutter (web + APK)
```

## Composants d'exécution

| Composant | Rôle |
|---|---|
| `api` | FastAPI (uvicorn). Sert l'API REST `/api/v1`, le contrat OpenAPI, les WebSocket. Sans état : peut être répliqué. |
| `worker` | Celery. Exécute les tâches : ingestion, calcul des prédictions, règlement, notifications. |
| `beat` | Celery beat. Planifie les tâches récurrentes. Une seule instance. |
| `postgres` | Source de vérité : données sportives, prédictions, comptes, paris. |
| `redis` | Broker Celery, cache, limitation de débit, verrous distribués. |
| `caddy` | Reverse proxy HTTPS (serveur distant uniquement). |

Sur téléphone, les mêmes processus tournent dans Termux natif
(`scripts/termux/`), avec le pool de threads Celery (Android ne fournit pas les
sémaphores POSIX nommés du pool « prefork »).

## Organisation du code backend (`backend/src/footprono`)

| Module | Responsabilité | Phase |
|---|---|---|
| `core/` | Configuration, journalisation JSON, erreurs, middleware, métriques | 0 ✅ |
| `db/` | Base SQLAlchemy, sessions async, migrations Alembic | 0 ✅ |
| `cache/` | Client Redis | 0 ✅ |
| `api/` | Routes HTTP versionnées, dépendances, schémas de réponse | 0 ✅ (santé) |
| `worker/` | Application Celery, tâches, planification | 0 ✅ |
| `ingestion/` | Connecteurs sources, normalisation des noms, contrôles qualité, cache et quotas | 1, 3 |
| `features/` | Moteur de features unique (état des équipes à l'instant *t*) | 2 |
| `ml/` | Entraînement, backtest temporel, calibration, registre d'artefacts | 2 |
| `markets/` | Dérivation des marchés depuis la distribution de scores | 2 |
| `predictions/` | Génération, stockage et service des prédictions | 3 |
| `analysis/` | Textes d'analyse générés depuis des données réelles | 3 |
| `results/` | Résultats réels des matchs | 4 |
| `bookmaker/` | Paris virtuels, soldes, règlement | 4 |
| `coupons/` | Combinés construits sur les probabilités validées | 4 |
| `montante/` | Sessions par paliers | 4 |
| `notifications/` | Notifications en base, WebSocket, push FCM | 4 |
| `auth/` | Comptes, rôles, JWT, abonnements | 5 |
| `admin/` | Supervision, gestion des abonnés, santé des modèles | 5 |

Règle de dépendance : `api` → services métier → `db`/`cache`. Les modules métier
n'importent jamais `api`. Le moteur (`features`, `ml`, `markets`) ne dépend ni
de FastAPI ni de Celery : il est utilisable seul pour l'entraînement et le
backtest.

## Contrats

- **API** : OpenAPI généré par FastAPI (`/api/v1/openapi.json`), source unique
  des clients Flutter générés. Toute rupture de contrat passe par une nouvelle
  version d'API.
- **Données** : chaque table documente l'origine et l'horodatage d'ingestion
  de ses lignes.
- **Modèles** : chaque artefact embarque sa version, la version du moteur de
  features, la période d'entraînement et ses métriques de validation.

## Observabilité

- Journal JSON sur stdout, identifiant de requête (`x-request-id`) propagé.
- `/api/v1/health` (processus vivant), `/api/v1/ready` (base et Redis joignables,
  sinon 503 avec le détail), `/metrics` (Prometheus, non exposé publiquement).

## Frontend

Application Flutter unique (`mobile/`, phase 5) compilée en web et en APK
Android, consommant exclusivement l'API `/api/v1`.
