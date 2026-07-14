import uvicorn

from ip_country_api.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "ip_country_api.main:app",
        host=settings.app_host,
        port=settings.app_port,
        log_config=None,
        log_level="warning",
        access_log=False,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
