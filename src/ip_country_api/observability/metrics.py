from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


class ApplicationMetrics:
    """Application metrics with a deliberately bounded label vocabulary."""

    ALLOWED_LABELS = frozenset(
        {
            "method",
            "route",
            "status_code",
            "source",
            "result",
            "provider",
            "operation",
            "error_type",
        }
    )

    def __init__(self, version: str, enabled: bool = True) -> None:
        self.enabled = enabled
        self.registry = CollectorRegistry(auto_describe=True)
        self.http_requests = Counter(
            "ip_country_http_requests_total",
            "Application HTTP requests",
            ["method", "route", "status_code"],
            registry=self.registry,
        )
        self.http_duration = Histogram(
            "ip_country_http_request_duration_seconds",
            "Application HTTP request duration",
            ["method", "route"],
            registry=self.registry,
        )
        self.lookups = Counter(
            "ip_country_lookup_total",
            "Country lookup outcomes",
            ["source", "result"],
            registry=self.registry,
        )
        self.provider_requests = Counter(
            "ip_country_provider_requests_total",
            "Provider request outcomes",
            ["provider", "result"],
            registry=self.registry,
        )
        self.provider_duration = Histogram(
            "ip_country_provider_request_duration_seconds",
            "Provider request duration",
            ["provider"],
            registry=self.registry,
        )
        self.provider_errors = Counter(
            "ip_country_provider_errors_total",
            "Provider errors",
            ["provider", "error_type"],
            registry=self.registry,
        )
        self.database_operations = Counter(
            "ip_country_database_operations_total",
            "Database operations",
            ["operation"],
            registry=self.registry,
        )
        self.database_duration = Histogram(
            "ip_country_database_operation_duration_seconds",
            "Database operation duration",
            ["operation"],
            registry=self.registry,
        )
        self.database_errors = Counter(
            "ip_country_database_errors_total",
            "Database errors",
            ["operation", "error_type"],
            registry=self.registry,
        )
        self.build_info = Gauge(
            "ip_country_build_info",
            "Build information",
            ["version"],
            registry=self.registry,
        )
        self.build_info.labels(version=version).set(1)

    def http_request(self, method: str, route: str, status: int, duration: float) -> None:
        if self.enabled:
            self.http_requests.labels(method, route, str(status)).inc()
            self.http_duration.labels(method, route).observe(duration)

    def lookup(self, source: str, result: str) -> None:
        if self.enabled:
            self.lookups.labels(source, result).inc()

    def provider_request(self, provider: str, result: str, duration: float) -> None:
        if self.enabled:
            self.provider_requests.labels(provider, result).inc()
            self.provider_duration.labels(provider).observe(duration)

    def provider_error(self, provider: str, error_type: str) -> None:
        if self.enabled:
            self.provider_errors.labels(provider, error_type).inc()

    def database_operation(self, operation: str, duration: float) -> None:
        if self.enabled:
            self.database_operations.labels(operation).inc()
            self.database_duration.labels(operation).observe(duration)

    def database_error(self, operation: str, error_type: str) -> None:
        if self.enabled:
            self.database_errors.labels(operation, error_type).inc()

    def render(self) -> bytes:
        return generate_latest(self.registry)
