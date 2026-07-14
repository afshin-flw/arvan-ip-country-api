import json

import pytest

from ip_country_api.observability.logging import redact_secrets
from ip_country_api.observability.metrics import ApplicationMetrics

pytestmark = pytest.mark.unit


def test_secret_fields_are_redacted() -> None:
    event = redact_secrets(
        None, "info", {"token": "sensitive", "database_url": "sensitive", "safe": "ok"}
    )
    assert event == {"token": "[REDACTED]", "database_url": "[REDACTED]", "safe": "ok"}
    assert "sensitive" not in json.dumps(event)


def test_metric_label_policy_excludes_sensitive_and_high_cardinality_values() -> None:
    assert ApplicationMetrics.ALLOWED_LABELS == {
        "method",
        "route",
        "status_code",
        "source",
        "result",
        "provider",
        "operation",
        "error_type",
    }
    assert (
        not {"ip", "country_code", "country_name", "request_id", "url"}
        & ApplicationMetrics.ALLOWED_LABELS
    )
