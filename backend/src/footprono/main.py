"""Point d'entrée ASGI : ``uvicorn --factory footprono.main:create_app``."""

import html
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from footprono import __version__, web_release
from footprono.accounts.plans import PREMIUM_DAYS, PREMIUM_PRICE
from footprono.api.v1.router import api_router
from footprono.cache.redis import create_redis
from footprono.core.config import Environment, Settings, get_settings
from footprono.core.errors import register_error_handlers
from footprono.core.logging import configure_logging
from footprono.core.middleware import RequestContextMiddleware, RouteResolver
from footprono.db.session import create_engine, create_session_factory


class _WebApp(StaticFiles):
    """Version web : dossier absent tant que rien n'est publié (404), et chaque fichier
    revalidé auprès du serveur (ETag) pour qu'une nouvelle version arrive aussitôt."""

    async def check_config(self) -> None:
        return None

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Date de la version en vigueur des pages légales (confidentialité, conditions) : à
# changer à chaque modification importante du texte.
LEGAL_EFFECTIVE_DATE = "6 octobre 2026"

ADMIN_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        redis = create_redis(settings)
        app.state.db_engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.redis = redis
        try:
            yield
        finally:
            await redis.aclose()
            await engine.dispose()

    is_prod = settings.environment is Environment.PRODUCTION
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=None if is_prod else "/docs",
        redoc_url=None,
    )
    app.state.settings = settings

    register_error_handlers(app)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(
        RequestContextMiddleware,
        resolver=RouteResolver(lambda: [*app.openapi()["paths"], "/metrics"]),
    )
    app.include_router(api_router, prefix=settings.api_prefix)

    # Version web (iPhone, ordinateur) : dossier fixe (FP_WEB_APP_DIR, développement et
    # tests de bout en bout) ou version publiée depuis la console (web_release).
    if settings.web_app_dir is not None:
        if not (settings.web_app_dir / "index.html").is_file():
            raise RuntimeError(f"FP_WEB_APP_DIR : index.html absent de {settings.web_app_dir}")
        web_dir = settings.web_app_dir
    else:
        web_dir = web_release.served_dir(settings.web_release_dir)
    app.mount("/app", _WebApp(directory=web_dir, html=True, check_dir=False), name="app")

    @app.get("/", include_in_schema=False)
    async def home() -> Response:
        if not (web_dir / "index.html").is_file():
            return Response(status_code=404)
        return RedirectResponse("/app/")

    # Pages légales publiques (exigées par Google Play et l'App Store) : chiffres et
    # identité tirés du code et de la configuration, jamais recopiés à la main.
    values = {
        "legal_name": settings.legal_name,
        "contact_email": settings.contact_email,
        "hosting": settings.privacy_hosting,
        "payment_provider": settings.privacy_payment_provider,
        "backup_days": str(settings.backup_keep_days),
        "effective_date": LEGAL_EFFECTIVE_DATE,
        "premium_price": f"{PREMIUM_PRICE:,}".replace(",", " "),
        "premium_days": str(PREMIUM_DAYS),
        "starting_balance": f"{settings.starting_balance:,}".replace(",", " "),
    }
    pages = {}
    for route, name in (
        ("/confidentialite", "confidentialite"),
        ("/conditions", "conditions"),
        ("/suppression-compte", "suppression_compte"),
    ):
        text = (Path(__file__).parent / "web" / f"{name}.html").read_text()
        for key, value in values.items():
            text = text.replace("{" + key + "}", html.escape(value))
        pages[route] = text

    async def legal_page(request: Request) -> HTMLResponse:
        return HTMLResponse(pages[request.url.path])

    for route in pages:
        app.add_api_route(route, legal_page, methods=["GET"], include_in_schema=False)

    # Console d'administration (pages statiques ; les données passent par /api/v1/admin,
    # réservé au rôle administrateur). En-têtes stricts : aucun script ni style venu
    # d'ailleurs, pas d'affichage dans un cadre, rien en cache.
    admin_dir = Path(__file__).parent / "web" / "admin"
    app.mount("/admin", StaticFiles(directory=admin_dir, html=True), name="admin")

    @app.get("/admin", include_in_schema=False)
    async def admin_home() -> RedirectResponse:
        return RedirectResponse("/admin/")

    @app.middleware("http")
    async def admin_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        if request.url.path.startswith("/admin"):
            response.headers.update(ADMIN_HEADERS)
        return response

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
