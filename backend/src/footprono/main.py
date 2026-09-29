"""Point d'entrée ASGI : ``uvicorn --factory footprono.main:create_app``."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from footprono import __version__
from footprono.api.v1.router import api_router
from footprono.cache.redis import create_redis
from footprono.core.config import Environment, Settings, get_settings
from footprono.core.errors import register_error_handlers
from footprono.core.logging import configure_logging
from footprono.core.middleware import RequestContextMiddleware, RouteResolver
from footprono.db.session import create_engine, create_session_factory


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

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
