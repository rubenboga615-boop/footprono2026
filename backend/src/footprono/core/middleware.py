"""Middleware ASGI : identifiant de requête, journal d'accès et métriques."""

import logging
import re
import time
import uuid
from collections.abc import Callable, Iterable

from starlette.routing import compile_path
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from footprono.core.logging import request_id_var
from footprono.core.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS

logger = logging.getLogger("footprono.access")

REQUEST_ID_HEADER = "x-request-id"
# Un identifiant fourni par le client n'est repris que s'il est court et sûr,
# pour ne jamais injecter de contenu arbitraire dans les logs.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RouteResolver:
    """Associe un chemin concret à son gabarit (``/matchs/{id}``) pour les métriques.

    Les gabarits viennent du contrat OpenAPI de l'application (API publique et
    stable), compilés au premier usage. Tout chemin inconnu devient
    ``unmatched`` : le nombre de labels Prometheus reste borné.
    """

    def __init__(self, templates: Callable[[], Iterable[str]]) -> None:
        self._templates = templates
        self._compiled: list[tuple[re.Pattern[str], str]] | None = None

    def resolve(self, path: str) -> str:
        if self._compiled is None:
            self._compiled = [(compile_path(t)[0], t) for t in self._templates()]
        for pattern, template in self._compiled:
            if pattern.match(path):
                return template
        return "unmatched"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, resolver: RouteResolver) -> None:
        self.app = app
        self.resolver = resolver

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.encode(), b"").decode("latin-1")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        status_code = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            path_template = self.resolver.resolve(scope["path"])
            method = scope["method"]
            HTTP_REQUESTS.labels(method, path_template, str(status_code)).inc()
            HTTP_REQUEST_DURATION.labels(method, path_template).observe(duration)
            logger.info(
                "request",
                extra={
                    "method": method,
                    "path": scope["path"],
                    "status": status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )
            request_id_var.reset(token)
