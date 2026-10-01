# Tests de bout en bout

Vraie API (PostgreSQL, Redis) + vraie application web Flutter, pilotées dans
Chromium : inscription, matchs, match, coupon et pari, bookmaker, profil,
fiabilité, montante. Lancés par GitHub Actions (workflow **Application**,
tâche `e2e`).

En local (base dédiée `footprono_e2e`, jamais la base de production) :

```bash
# base vide, migrée, puis données d'essai (saison 2024-25 du dépôt)
FP_DATABASE_URL=postgresql+asyncpg://…/footprono_e2e alembic upgrade head
FP_DATABASE_URL=postgresql+asyncpg://…/footprono_e2e python e2e/seed.py
# API + version web (construite avec --base-href /app/)
FP_WEB_APP_DIR=app/build/web uvicorn footprono.main:create_app --factory --port 8000
# parcours
cd e2e && npm install && npx playwright install chromium
E2E_URL=http://127.0.0.1:8000/app/ E2E_SHOTS=shots node app.test.mjs
```

L'application est ouverte avec `?e2e` : l'arbre d'accessibilité est activé et
les éléments sont trouvés par leur libellé, comme un lecteur d'écran.
