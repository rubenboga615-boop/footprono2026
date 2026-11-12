"""Point d'entrée ASGI : ``uvicorn --factory footprono.main:create_app``."""

import base64
import functools
import hashlib
import html
import re
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

# FlutterFire charge chaque module de Firebase par un petit script inline, toujours le même
# pour une version donnée : autorisé par son empreinte, pas par 'unsafe-inline'.
FIREBASE_MODULES = (
    ("app", "firebase_core"),
    ("auth", "firebase_auth"),
    ("messaging", "firebase_messaging"),
)
FIREBASE_DEFAULT_VERSION = "12.19.0"
_SDK_VERSION = re.compile(rb'flutterfire_web_sdk_version\)[^"]{0,120}"(\d+\.\d+\.\d+)"')


def firebase_script_hashes(version: str) -> list[str]:
    out = []
    for module, name in FIREBASE_MODULES:
        url = f"https://www.gstatic.com/firebasejs/{version}/firebase-{module}.js"
        for pad, inner in (("            ", "              "), ("      ", "        ")):
            # Avec Trusted Types (Chrome) puis sans (Safari, Firefox) : indentation différente.
            text = (
                f"{pad}window.ff_trigger_{name} = async (callback) => {{\n"
                f'{inner}console.debug("Initializing Firebase {name}");\n'
                f'{inner}callback(await import("{url}"));\n'
                f"{pad}}};\n{pad[:-2]}"
            )
            digest = base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()
            out.append(f"'sha256-{digest}'")
    return out


@functools.lru_cache(maxsize=4)
def _firebase_version(main_js: Path, mtime: float) -> str:
    try:
        found = _SDK_VERSION.search(main_js.read_bytes())
    except OSError:
        return FIREBASE_DEFAULT_VERSION
    return found.group(1).decode() if found else FIREBASE_DEFAULT_VERSION


def served_firebase_version(web_dir: Path) -> str:
    """Version de Firebase de la version web servie (main.dart.js), relue à chaque publication."""
    main_js = web_dir / "main.dart.js"
    try:
        mtime = main_js.stat().st_mtime
    except OSError:
        return FIREBASE_DEFAULT_VERSION
    return _firebase_version(main_js.resolve(), mtime)


def web_csp(host: str, firebase_version: str = FIREBASE_DEFAULT_VERSION) -> str:
    """Politique de sécurité de la version web (audit de sécurité du 12/11/2026, n° 3) : le
    jeton de connexion rangé dans le navigateur ne peut pas partir ailleurs. Flutter web :
    'wasm-unsafe-eval' (CanvasKit), styles insérés par le moteur, polices de secours de
    Google ; Firebase (connexion Google, notifications) : gstatic, apis.google.com et les API
    googleapis ; WebSocket des notifications et du direct sur ce domaine."""
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self' 'wasm-unsafe-eval' https://www.gstatic.com https://apis.google.com "
            + " ".join(firebase_script_hashes(firebase_version)),
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "font-src 'self' data: https://fonts.gstatic.com",
            "connect-src 'self' "
            + (f"wss://{host} " if host else "")
            + "https://www.gstatic.com https://fonts.gstatic.com https://*.googleapis.com",
            "frame-src 'self' https://accounts.google.com https://apis.google.com",
            "worker-src 'self' blob:",
            "manifest-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'self'",
        ]
    )


class _WebApp(StaticFiles):
    """Version web : dossier absent tant que rien n'est publié (404), et chaque fichier
    revalidé auprès du serveur (ETag) pour qu'une nouvelle version arrive aussitôt."""

    async def check_config(self) -> None:
        return None

    async def get_response(self, path: str, scope: Any) -> Response:
        response = await super().get_response(path, scope)
        host = dict(scope.get("headers") or []).get(b"host", b"").decode("latin-1")
        # Seulement un nom d'hôte (et un port) : rien d'autre ne passe dans l'en-tête.
        host = host if host.replace(".", "").replace(":", "").replace("-", "").isalnum() else ""
        version = served_firebase_version(Path(str(self.directory)))
        response.headers["Content-Security-Policy"] = web_csp(host, version)
        return response

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Date de la version en vigueur des pages légales (confidentialité, conditions) : à
# changer à chaque modification importante du texte.
LEGAL_EFFECTIVE_DATE = "6 novembre 2026"

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
        # Liste des routes cachée en production (audit de sécurité du 12/11/2026, n° 2).
        openapi_url=None if is_prod else f"{settings.api_prefix}/openapi.json",
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
