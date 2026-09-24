import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import monotonic

import httpcore
import httpx
import pytest

from ai_pdf_api.core.settings import settings
from ai_pdf_api.services.model_config_types import ModelConfigurationError
from ai_pdf_api.services.model_endpoint import require_address, validate_base_url
from ai_pdf_api.services.model_transport import ModelTransport, PolicyNetworkBackend, _ResponseStream, model_client


@pytest.mark.parametrize("url", [
    "https://user:password@example.com/v1", "https://example.com/v1?", "https://example.com/v1#",
    "https://example.com/v1?key=secret", "https://example.com/v1#secret", "file:///etc/passwd",
    "https://example.com/\npath", "https://example.com/\tpath", "https://example.com/\\path",
    "https://%31%32%37.0.0.1/v1", "https://2130706433/v1", "https://0177.0.0.1/v1",
    "https://0x7f000001/v1", "https://[fe80::1%25eth0]/v1", "https://metadata.google.internal/v1",
])
def test_invalid_urls(url):
    with pytest.raises(ModelConfigurationError):
        validate_base_url(url)


def test_exact_base_and_public_https_need_no_whitelist(monkeypatch):
    monkeypatch.setattr(settings, "model_private_origins", {})
    assert validate_base_url("https://EXAMPLE.com/gateway/custom/") == "https://example.com/gateway/custom"
    require_address("https://example.com/gateway/custom", "8.8.8.8")
    with pytest.raises(ModelConfigurationError):
        require_address("https://example.com/gateway/custom", "127.0.0.1")


@pytest.mark.parametrize("address", ["169.254.169.254", "fd00:ec2::254", "100.100.100.200", "0.0.0.0", "224.0.0.1", "::ffff:169.254.169.254"])
def test_metadata_denied_even_with_allowlist(monkeypatch, address):
    monkeypatch.setattr(settings, "model_private_origins", {"https://example.com:443": ["0.0.0.0/0", "::/0"]})
    with pytest.raises(ModelConfigurationError):
        require_address("https://example.com/v1", address)


def test_private_allowance_is_exact_origin_and_address(monkeypatch):
    monkeypatch.setattr(settings, "model_private_origins", {"http://localhost:18136": ["127.0.0.1/32"]})
    require_address("http://localhost:18136/a/v1", "::ffff:127.0.0.1")
    for url, address in [("https://localhost:18136/a", "127.0.0.1"), ("http://localhost:18137/a", "127.0.0.1"), ("http://localhost:18136/a", "192.168.1.1")]:
        with pytest.raises(ModelConfigurationError):
            require_address(url, address)


class PeerStream:
    def __init__(self, peer):
        self.peer, self.closed = peer, False
    def get_extra_info(self, key):
        assert key == "server_addr"
        return self.peer
    def close(self):
        self.closed = True


def test_dns_pin_numeric_and_peer(monkeypatch):
    calls = []
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
    stream = PeerStream(("8.8.8.8", 443))
    backend = PolicyNetworkBackend("https://example.com/v1")
    def dial(host, *args):
        calls.append(host)
        return stream
    monkeypatch.setattr(backend.backend, "connect_tcp", dial)
    assert backend.connect_tcp("example.com", 443) is stream
    assert calls == ["8.8.8.8"]
    for peer in (None, ("127.0.0.1", 443)):
        stream.peer = peer
        with pytest.raises(ModelConfigurationError):
            backend.connect_tcp("example.com", 443)
        assert stream.closed


def test_mixed_dns_answers_never_dial(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ("8.8.8.8", "127.0.0.1")])
    backend = PolicyNetworkBackend("https://example.com/v1")
    monkeypatch.setattr(backend.backend, "connect_tcp", lambda *args: pytest.fail("must not connect"))
    with pytest.raises(ModelConfigurationError):
        backend.connect_tcp("example.com", 443)


def test_transport_rejects_scheme_and_sni_extension(monkeypatch):
    transport = ModelTransport("https://example.com/v1")
    with pytest.raises(ModelConfigurationError):
        transport.handle_request(httpx.Request("POST", "http://example.com:443/v1"))
    def handle(request):
        assert "sni_hostname" not in request.extensions
        return httpcore.Response(200, content=b"ok")
    monkeypatch.setattr(transport.pool, "handle_request", handle)
    response = transport.handle_request(httpx.Request("POST", "https://example.com/v1", extensions={"sni_hostname": "evil.example"}))
    assert response.read() == b"ok"
    response.close()
    transport.close()


class Stream:
    closed = False
    def __init__(self, size=16 * 1024 * 1024 + 1):
        self.size = size
    def __iter__(self):
        yield b"x" * self.size
    def close(self):
        self.closed = True


def test_response_byte_limit_and_deadline_close_stream():
    stream = Stream()
    with pytest.raises(httpx.ReadError):
        list(_ResponseStream(stream, monotonic() + 20))
    assert stream.closed
    stream = Stream(1)
    try:
        with pytest.raises(httpx.ReadTimeout):
            list(_ResponseStream(stream, monotonic() - 1))
        assert stream.closed
    finally:
        del stream


def test_real_socket_redirect_and_proxy_not_followed(monkeypatch):
    hits = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            hits.append(self.path)
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/stolen")
            self.send_header("Content-Length", "0")
            self.end_headers()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(settings, "model_private_origins", {base: ["127.0.0.1/32"]})
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    try:
        with model_client(base, 3) as client:
            response = client.post(base + "/first", headers={"Authorization": "Bearer fixture"})
            assert response.status_code == 302
        assert hits == ["/first"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_real_tls_preserves_hostname_pins_dns_and_rejects_wrong_certificate(monkeypatch, tmp_path):
    import ssl
    import certifi
    from datetime import UTC, datetime, timedelta
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fixture.test")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
            .not_valid_after(datetime.now(UTC) + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("fixture.test")]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    hits, names, resolutions = [], [], []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            hits.append((self.path, self.headers["Host"]))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    context.set_servername_callback(lambda sock, name, ctx: names.append(name))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    original = socket.getaddrinfo
    def dns(host, port, *args, **kwargs):
        resolutions.append(host)
        if host in {"fixture.test", "wrong.test"}:
            # A second hostname lookup would rebind; the dial must use a numeric IP.
            ip = "127.0.0.1" if resolutions.count(host) == 1 else "169.254.169.254"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
        return original(host, port, *args, **kwargs)
    monkeypatch.setattr(socket, "getaddrinfo", dns)
    monkeypatch.setattr(certifi, "where", lambda: str(cert_path))
    monkeypatch.setattr(settings, "model_private_origins", {f"https://{host}:{port}": ["127.0.0.1/32"] for host in ("fixture.test", "wrong.test")})
    try:
        base = f"https://fixture.test:{port}"
        with model_client(base, 3) as client:
            assert client.post(base + "/custom/v1/responses").text == "ok"
        assert names == ["fixture.test"]
        assert resolutions.count("fixture.test") == 1 and "127.0.0.1" in resolutions
        assert hits == [("/custom/v1/responses", f"fixture.test:{port}")]
        base = f"https://wrong.test:{port}"
        with model_client(base, 3) as client, pytest.raises(httpx.ConnectError):
            client.post(base + "/never-sent")
        assert len(hits) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_compressed_response_rejected_before_httpx_decode(monkeypatch):
    import gzip
    transport = ModelTransport("https://example.com/v1")
    def handle(request):
        assert (b"Accept-Encoding", b"identity") in request.headers
        return httpcore.Response(200, headers=[(b"Content-Encoding", b"gzip")], content=gzip.compress(b"x" * (17 * 1024 * 1024)))
    monkeypatch.setattr(transport.pool, "handle_request", handle)
    with pytest.raises(httpx.ReadError, match="Compressed"):
        transport.handle_request(httpx.Request("POST", "https://example.com/v1"))
    transport.close()
