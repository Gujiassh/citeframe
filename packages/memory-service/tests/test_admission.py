"""Approved finite-policy fixtures, independent of the production regex inventory."""
from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

import pytest

from citeframe_contracts.memory import MemoryConditions, MemoryError, MemoryStatement
from citeframe_memory.admission import admit_statement

TYPES = ("PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY", "DSA PRIVATE KEY",
         "OPENSSH PRIVATE KEY", "ENCRYPTED PRIVATE KEY")
LABELS = (
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
SCHEMES = ("postgres", "postgresql", "postgresql+psycopg", "mysql", "mysql+pymysql",
           "mongodb", "mongodb+srv", "redis", "rediss", "amqp", "amqps",
           "http", "https", "ftp", "sftp")


def placed(value, field):
    clean = MemoryStatement("Preserve exact source.", MemoryConditions("workspace", "manual"))
    if field == "content":
        return replace(clean, content=value)
    return replace(clean, conditions=replace(clean.conditions, **{field: value}))


def policy_pairs():
    for kind in TYPES:
        yield (f"-----BEGIN {kind}-----\nQUJD\n-----END {kind}-----",
               f"-----BEGIN {kind}-----\n \t\n-----END {kind}-----")
    for header in ("Authorization", "Proxy-Authorization"):
        for scheme in ("Bearer", "Basic"):
            yield f"{header}: {scheme} ABCDEFGH", f"{header}: {scheme} ABCDEFG"
    for header in ("Cookie", "Set-Cookie"):
        for quote in ("", "'", '"'):
            value = "synthetic value" if quote else "synthetic"
            yield f"{header}: session={quote}{value}{quote}", f"{header}: session={quote}{quote}"
    for label in LABELS:
        for delimiter in ("=", ":", "："):
            for quote in ("", "'", '"'):
                value = "synthetic value" if quote else "synthetic"
                yield (f"{quote}{label}{quote}{delimiter}{quote}{value}{quote}",
                       f"{quote}{label}{quote}{delimiter}{quote}{quote}")
    for scheme in SCHEMES:
        yield f"{scheme}://demo:synthetic@localhost/db", f"{scheme}://demo:@localhost/db"
    for prefix in ("ghp_", "gho_", "ghu_", "ghs_", "ghr_"):
        yield prefix + "A"*36, prefix + "A"*35
    yield "github_pat_" + "A"*22 + "_" + "A"*59, "github_pat_" + "A"*22 + "_" + "A"*58
    yield "glpat-" + "A"*20, "glpat-" + "A"*19
    for prefix in ("sk-", "sk-proj-", "sk-svcacct-"):
        yield prefix + "A"*32, "sk-" + "A"*31


@pytest.mark.parametrize("positive,negative", list(policy_pairs()))
@pytest.mark.parametrize("field", ("content", "subject", "applicability"))
def test_finite_inventory_and_nearest_negatives(positive, negative, field, caplog):
    with pytest.raises(MemoryError) as exc:
        admit_statement(placed(positive, field))
    assert type(exc.value) is MemoryError
    assert exc.value.args == ("sensitive_content_unsupported",)
    assert str(exc.value) == "sensitive_content_unsupported"
    assert repr(exc.value) == "MemoryError('sensitive_content_unsupported')"
    assert exc.value.__cause__ is None and exc.value.__context__ is None
    assert positive not in caplog.text
    assert sha256(positive.encode()).hexdigest() not in caplog.text
    assert admit_statement(placed(negative, field)) is None


REJECT = [
    "authorization:\tBEARER ABCDEFGH",
    "Authorization: Basic QUJDREVGRw==",
    "Cookie: theme=dark; session=",
    "PASSWORD = synthetic;",
    'password="example"',
    '"api_key": "synthetic"',
    "密码：示例",
    "POSTGRESQL://demo:p%40ss@localhost/db",
    "https://demo:synthetic@localhost",
    "Do not use Authorization: Bearer ABCDEFGH",
    "不要使用 password=synthetic",
    "sk-proj-" + "A"*31,
    "sk-svcacct-" + "A"*31,
    "password=synthetic \t}",
    "password='literal\\backslash'",
    "Authorization: Bearer ABCDEFGH\u2003",
    "-----BEGIN PUBLIC KEY-----\nQUJD\n-----END PUBLIC KEY-----\npassword=synthetic",
]
ALLOW = [
    "-----BEGIN PUBLIC KEY-----\nQUJD\n-----END PUBLIC KEY-----",
    "-----BEGIN CERTIFICATE-----\nQUJD\n-----END CERTIFICATE-----",
    "-----begin private key-----\nQUJD\n-----end private key-----",
    "-----BEGIN PRIVATE KEY-----\nQUJD\n-----END RSA PRIVATE KEY-----",
    "-----BEGIN PRIVATE KEY-----",
    "X-Authorization: Bearer ABCDEFGH",
    "Authorization:\nBearer ABCDEFGH",
    "Authorization: Bearer ABCDEFGH!",
    "Cookie: empty=; session=synthetic",
    "my_password=synthetic", "password_hint=synthetic",
    "password: never store credentials", '"api_key": ""',
    '"api_key": "synthetic\nvalue"',
    "请勿保存密码或 API 密钥。", "令牌预算：4096",
    "token=4096", "token budget: 4096", "tokens: 2000",
    "postgresql://demo@localhost/db",
    "postgresql%3A%2F%2Fdemo%3Asynthetic%40localhost",
    "xhttps://demo:synthetic@localhost", "sqlite://demo:synthetic@localhost",
    "ghp_" + "A"*37, "xghp_" + "A"*36, "GHP_" + "A"*36,
    "glpat-" + "A"*21,
    "Do not retain passwords, API keys or authorization headers.",
    "Prefer concise project notes.", "Authorization:\u2003Bearer ABCDEFGH",
    "paſſword=synthetic", "api＿key=synthetic", "password=\u2003synthetic",
    "Cookie: session =synthetic", "Set-Cookie: session= synthetic",
    "AKIA" + "A"*16, "eyJabc.eyJdef.signature", "A"*128,
]


@pytest.mark.parametrize("value", REJECT)
@pytest.mark.parametrize("field", ("content", "subject", "applicability"))
def test_boundary_reject(value, field):
    with pytest.raises(MemoryError, match="^sensitive_content_unsupported$"):
        admit_statement(placed(value, field))


@pytest.mark.parametrize("value", ALLOW)
@pytest.mark.parametrize("field", ("content", "subject", "applicability"))
def test_boundary_admit(value, field):
    assert admit_statement(placed(value, field)) is None


@pytest.mark.parametrize("prefix", ("sk-", "sk-proj-", "sk-svcacct-"))
@pytest.mark.parametrize("field", ("content", "applicability"))
def test_provider_upper_boundary(prefix, field):
    with pytest.raises(MemoryError):
        admit_statement(placed(prefix + "A"*256, field))
    assert admit_statement(placed(prefix + "A"*257, field)) is None


def test_fields_are_independent_and_source_unchanged():
    statement = MemoryStatement("password", MemoryConditions("=synthetic", "project notes"))
    before = repr(statement)
    assert admit_statement(statement) is None
    assert repr(statement) == before


def test_maximum_size_adversarial_near_matches():
    started = perf_counter()
    for seed in ("sk-", "password: ", "-----BEGIN PRIVATE KEY-----", "https://", "'"*19):
        text = (seed * (4000 // len(seed) + 1))[:4000]
        statement = MemoryStatement(text, MemoryConditions(text[:256], text[:2000]))
        for _ in range(20):
            try:
                admit_statement(statement)
            except MemoryError:
                pass
    # A generous watchdog catches catastrophic backtracking, not a latency SLA.
    assert perf_counter() - started < 10


def test_neutral_admission_import_without_apps():
    root = Path(__file__).resolve().parents[3]
    code = """
import importlib.abc, sys
class DenyApps(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('ai_pdf_api', 'ai_pdf_worker'):
            raise AssertionError(fullname)
sys.meta_path.insert(0, DenyApps())
from citeframe_memory.admission import admit_statement
from citeframe_contracts.memory import MemoryStatement, MemoryConditions
admit_statement(MemoryStatement('clean', MemoryConditions('scope', 'manual')))
print('neutral-admission-pass')
"""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": os.pathsep.join(
        str(root / "packages" / name / "src") for name in
        ("memory-service", "backend-contracts", "backend-persistence"))}
    assert "neutral-admission-pass" in subprocess.check_output(
        [sys.executable, "-c", code], env=env, text=True)


@pytest.mark.parametrize("label", LABELS)
def test_ascii_label_casing(label):
    for variant in (label.upper(), label.lower()):
        with pytest.raises(MemoryError):
            admit_statement(placed(variant + "=synthetic", "content"))


@pytest.mark.parametrize("header", ("Authorization", "Proxy-Authorization"))
@pytest.mark.parametrize("delimiter", (" ", "\t", "\n", "\r", '"', "'", ",", ";", "\u2003"))
def test_auth_terminal_delimiters(header, delimiter):
    with pytest.raises(MemoryError):
        admit_statement(placed(header + ": Bearer ABCDEFGH" + delimiter, "content"))
