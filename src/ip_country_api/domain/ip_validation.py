import ipaddress

from ip_country_api.domain.errors import InvalidIPError, NonPublicIPError
from ip_country_api.domain.models import IPAddress


def validate_public_ip(value: str) -> IPAddress:
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise InvalidIPError from exc

    if (
        not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    ):
        raise NonPublicIPError
    return address
