import uvicorn

from ip_country_api.config import get_settings
from ip_country_api.main import create_app


def main() -> None:
    settings = get_settings()
    application = create_app(settings)
    uvicorn.run(
        application,
        host=settings.app_host,
        port=settings.app_port,
        log_config=None,
        log_level="warning",
        access_log=False,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
