import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

from ai_pdf_api.core.settings import settings
from ai_pdf_api.services.model_config_types import ModelConfigurationError


def validate_base_url(value: str) -> str:
    try:
        if value != value.strip() or re.search(r"[\s\\%]", value):
            raise ValueError()
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username is not None or parts.password is not None or "?" in value or "#" in value:
            raise ValueError()
        host = parts.hostname.lower()
        if host.endswith(".") or host in {"metadata.google.internal", "metadata", "instance-data"}:
            raise ValueError()
        host = host.encode("idna").decode()
        if re.fullmatch(r"[0-9.]+", host) or host.startswith("0x"):
            try:
                if str(ipaddress.IPv4Address(host)) != host:
                    raise ValueError()
            except ValueError:
                raise ValueError() from None
        port = parts.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError()
        authority = f"[{host}]" if ":" in host else host
        if port is not None:
            authority += f":{port}"
        base = urlunsplit((parts.scheme, authority, parts.path.rstrip("/"), "", ""))
        origin = endpoint_origin(base)
        if parts.scheme == "http" and origin not in settings.model_private_origins:
            raise ModelConfigurationError("model_endpoint_denied", "HTTP model endpoints require a server-approved private origin.")
        return base
    except (ValueError, UnicodeError):
        raise ModelConfigurationError("model_endpoint_invalid", "Enter an absolute HTTP(S) API base without credentials, query, fragment or encoded host/path.") from None


def endpoint_origin(value: str) -> str:
    p = urlsplit(value)
    host = p.hostname or ""
    authority = f"[{host}]" if ":" in host else host
    return f"{p.scheme}://{authority}:{p.port or (443 if p.scheme == 'https' else 80)}"


def normalized_ip(value: str):
    ip = ipaddress.ip_address(value)
    return ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped else ip


def require_address(base_url: str, address: str) -> None:
    ip = normalized_ip(address)
    if ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved or str(ip) in {"100.100.100.200", "168.63.129.16", "fd00:ec2::254"}:
        raise ModelConfigurationError("model_endpoint_denied", "The model destination is not allowed.")
    if ip.is_global and urlsplit(base_url).scheme == "https":
        return
    networks = settings.model_private_origins.get(endpoint_origin(base_url), [])
    if not ip.is_global and any(ip in ipaddress.ip_network(cidr) for cidr in networks):
        return
    raise ModelConfigurationError("model_endpoint_denied", "The model destination requires server approval.")
