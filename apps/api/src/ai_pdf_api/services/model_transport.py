"""Origin-scoped HTTP transport: validate DNS, dial numeric IP, preserve TLS hostname."""
import socket
import ssl
from time import monotonic
import certifi
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from threading import BoundedSemaphore
from collections.abc import Iterator
from urllib.parse import urlsplit

import httpcore
import httpx

from ai_pdf_api.services.model_config_types import ModelConfigurationError
from ai_pdf_api.services.model_endpoint import endpoint_origin, normalized_ip, require_address, validate_base_url

_DNS_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="model-dns")
_DNS_SLOTS = BoundedSemaphore(8)

def _resolve(host, port, timeout):
    deadline = min(timeout or 10, 10)
    if not _DNS_SLOTS.acquire(timeout=deadline):
        raise httpcore.ConnectTimeout("Model DNS capacity unavailable.")
    future = _DNS_POOL.submit(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    future.add_done_callback(lambda _: _DNS_SLOTS.release())
    try:
        return future.result(timeout=deadline)
    except FutureTimeout:
        future.cancel()
        raise httpcore.ConnectTimeout("Model DNS lookup timed out.") from None


class PolicyNetworkBackend(httpcore.NetworkBackend):
    def __init__(self, base_url: str):
        self.base_url = validate_base_url(base_url)
        parts = urlsplit(self.base_url)
        self.host, self.port = parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)
        self.backend = httpcore.SyncBackend()

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host != self.host or port != self.port:
            raise ModelConfigurationError("model_endpoint_denied", "Provider origin changed.")
        try:
            addresses = list(dict.fromkeys(item[4][0] for item in _resolve(host, port, timeout)))
        except OSError:
            raise httpcore.ConnectError("Model DNS lookup failed.") from None
        if not addresses:
            raise httpcore.ConnectError("Model DNS lookup returned no addresses.")
        for address in addresses:
            require_address(self.base_url, address)
        last_error = None
        for address in addresses:
            try:
                stream = self.backend.connect_tcp(address, port, timeout, local_address, socket_options)
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as error:
                last_error = error
                continue
            peer = stream.get_extra_info("server_addr")
            if not peer or normalized_ip(peer[0]) != normalized_ip(address):
                stream.close()
                raise ModelConfigurationError("model_endpoint_denied", "Provider connection destination changed.")
            return stream
        raise httpcore.ConnectError("Model connection failed.") from last_error

    def connect_unix_socket(self, *args, **kwargs):
        raise ModelConfigurationError("model_endpoint_denied", "Local sockets are not model endpoints.")


class _ResponseStream(httpx.SyncByteStream):
    def __init__(self, stream, deadline):
        self.stream = stream
        self.deadline = deadline

    def __iter__(self) -> Iterator[bytes]:
        try:
            total = 0
            for chunk in self.stream:
                total += len(chunk)
                if total > 16 * 1024 * 1024:
                    self.close()
                    raise httpx.ReadError("Model response exceeded the byte limit.")
                if monotonic() > self.deadline:
                    self.close()
                    raise httpx.ReadTimeout("Model response exceeded its deadline.")
                yield chunk
        except httpcore.TimeoutException:
            raise httpx.ReadTimeout("Model response timed out.") from None
        except httpcore.NetworkError:
            raise httpx.ReadError("Model response failed.") from None
        except httpcore.ProtocolError:
            raise httpx.RemoteProtocolError("Model response protocol failed.") from None

    def close(self):
        if hasattr(self.stream, "close"):
            self.stream.close()


class ModelTransport(httpx.BaseTransport):
    def __init__(self, base_url: str):
        self.backend = PolicyNetworkBackend(base_url)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=certifi.where())
        self.pool = httpcore.ConnectionPool(ssl_context=context, network_backend=self.backend,
                                          http2=False, retries=0, max_connections=2)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if endpoint_origin(str(request.url)) != endpoint_origin(self.backend.base_url):
            raise ModelConfigurationError("model_endpoint_denied", "Provider origin changed.")
        timeout = request.extensions.get("timeout", {})
        deadline = monotonic() + min(float(timeout.get("read") or 120), 300)
        try:
            result = self.pool.handle_request(httpcore.Request(method=request.method,
                url=httpcore.URL(scheme=request.url.raw_scheme, host=request.url.raw_host, port=request.url.port, target=request.url.raw_path),
                headers=[(k, v) for k, v in request.headers.raw if k.lower() != b"accept-encoding"] + [(b"Accept-Encoding", b"identity")], content=request.stream, extensions={"timeout": request.extensions.get("timeout", {})}))
        except httpcore.TimeoutException:
            raise httpx.ConnectTimeout("Model request timed out.") from None
        except (httpcore.NetworkError, httpcore.ProtocolError):
            raise httpx.ConnectError("Model request failed.") from None
        encodings = [v.strip().lower() for k, v in result.headers if k.lower() == b"content-encoding"]
        if any(value != b"identity" for value in encodings):
            result.close()
            raise httpx.ReadError("Compressed model responses are not supported.")
        return httpx.Response(result.status, headers=result.headers, stream=_ResponseStream(result.stream, deadline), extensions=result.extensions)

    def close(self):
        self.pool.close()


def model_client(base_url: str, timeout: float) -> httpx.Client:
    return httpx.Client(transport=ModelTransport(base_url), trust_env=False, follow_redirects=False,
                        timeout=httpx.Timeout(timeout, connect=min(timeout, 10), pool=min(timeout, 10)))
