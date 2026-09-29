"""Métriques Prometheus exposées sur /metrics."""

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "footprono_http_requests_total",
    "Nombre de requêtes HTTP",
    ["method", "route", "status"],
)
HTTP_REQUEST_DURATION = Histogram(
    "footprono_http_request_duration_seconds",
    "Durée des requêtes HTTP",
    ["method", "route"],
)
