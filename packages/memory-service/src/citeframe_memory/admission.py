"""Finite lexical credential admission; no decoding, logging or source rewriting."""
from __future__ import annotations

import re

from citeframe_contracts.memory import MemoryError, MemoryStatement

_PRIVATE_TYPES = (
    "PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY", "DSA PRIVATE KEY",
    "OPENSSH PRIVATE KEY", "ENCRYPTED PRIVATE KEY",
)
_LABELS = (
    "password", "passwd", "pwd", "secret",
    "api_key", "api-key", "api key", "apikey",
    "access_token", "access-token", "access token", "accesstoken",
    "refresh_token", "refresh-token", "refresh token", "refreshtoken",
    "client_secret", "client-secret", "client secret", "clientsecret",
    "secret_key", "secret-key", "secret key", "secretkey",
    "private_key", "private-key", "private key", "privatekey",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "GITHUB_TOKEN",
    "GITLAB_TOKEN", "DATABASE_PASSWORD", "DB_PASSWORD", "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN", "密码", "口令", "API密钥", "API 密钥", "访问令牌",
    "刷新令牌", "客户端密钥", "密钥", "私钥",
)
_SCHEMES = (
    "postgres", "postgresql", "postgresql+psycopg", "mysql", "mysql+pymysql",
    "mongodb", "mongodb+srv", "redis", "rediss", "amqp", "amqps", "http",
    "https", "ftp", "sftp",
)


def _ascii_choice(values: tuple[str, ...]) -> str:
    return "(?ai:" + "|".join(re.escape(value) for value in values) + ")"


# Scope ASCII case-insensitivity to labels; whitespace elsewhere stays Unicode.
_HEADER = r"(?<![A-Za-z0-9_-])"
_QUOTED = r"""(?:"[^"\r\n]+"|'[^'\r\n]+')"""
_LABEL = _ascii_choice(_LABELS)
_LABEL_FORM = rf"""(?:"{_LABEL}"|'{_LABEL}'|{_LABEL})"""
_PATTERNS = tuple(re.compile(pattern) for pattern in (
    _HEADER + _ascii_choice(("Authorization", "Proxy-Authorization"))
    + r":[ \t]*" + _ascii_choice(("Bearer", "Basic"))
    + r"""[ \t]+[A-Za-z0-9._~+/-]{8,}=*(?=[\s"',;]|$)""",
    _HEADER + _ascii_choice(("Cookie", "Set-Cookie"))
    + r":[ \t]*[A-Za-z0-9_.-]+="
    + rf"""(?:{_QUOTED}|[^\s;,'"]+)""",
    r"(?<![A-Za-z0-9_])" + _LABEL_FORM + r"(?![A-Za-z0-9_])[ \t]*[=:：][ \t]*"
    + rf"""(?:{_QUOTED}|[^\s,;{{}}\[\]'"]+(?=[ \t]*(?:[\r\n,;}}\]]|$)))""",
    r"(?<![A-Za-z0-9+.-])" + _ascii_choice(_SCHEMES)
    + r"://[^\s/:@?#]+:[^\s/@?#]+@[^\s/?#]+",
    r"(?<![A-Za-z0-9_-])(?:gh[pousr]_[A-Za-z0-9]{36}"
    r"|github_pat_[A-Za-z0-9]{22}_[A-Za-z0-9]{59}"
    r"|glpat-[A-Za-z0-9_-]{20}"
    r"|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,256})(?![A-Za-z0-9_-])",
))


def _has_private_pem(value: str) -> bool:
    for kind in _PRIVATE_TYPES:
        begin, end = f"-----BEGIN {kind}-----", f"-----END {kind}-----"
        cursor = 0
        while (start := value.find(begin, cursor)) != -1:
            body_start = start + len(begin)
            finish = value.find(end, body_start)
            if finish == -1:
                break
            if value[body_start:finish].strip():
                return True
            cursor = finish + len(end)
    return False


def admit_statement(statement: MemoryStatement) -> None:
    """Reject only the reviewed finite patterns in independently scanned fields."""
    for value in (statement.content, statement.conditions.subject,
                  statement.conditions.applicability):
        if _has_private_pem(value) or any(pattern.search(value) for pattern in _PATTERNS):
            raise MemoryError("sensitive_content_unsupported")
