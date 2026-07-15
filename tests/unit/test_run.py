from unittest.mock import Mock

import pytest

from ip_country_api import run

pytestmark = pytest.mark.unit


def test_main_builds_application_with_runtime_settings(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = Mock(app_host="0.0.0.0", app_port=8080)
    application = object()
    create_app = Mock(return_value=application)
    uvicorn_run = Mock()

    monkeypatch.setattr(run, "get_settings", Mock(return_value=settings))
    monkeypatch.setattr(run, "create_app", create_app)
    monkeypatch.setattr(run.uvicorn, "run", uvicorn_run)

    run.main()

    create_app.assert_called_once_with(settings)
    uvicorn_run.assert_called_once_with(
        application,
        host="0.0.0.0",
        port=8080,
        log_config=None,
        log_level="warning",
        access_log=False,
        proxy_headers=False,
    )
