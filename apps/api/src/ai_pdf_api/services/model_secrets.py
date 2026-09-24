import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ai_pdf_api.core.settings import settings
from ai_pdf_api.services.model_config_types import ModelConfigurationError


def encryption_key() -> bytes:
    try:
        key = base64.b64decode(settings.model_config_encryption_key or "", validate=True)
        if len(key) != 32:
            raise ValueError()
        return key
    except (ValueError, binascii.Error):
        raise ModelConfigurationError("model_encryption_unavailable", "The server model encryption key is not configured correctly.", 503) from None


def _aad(workspace_id: str, capability: str) -> bytes:
    return f"citeframe-model-key:v1:{workspace_id}:{capability}".encode()


def encrypt_key(value: str, workspace_id: str, capability: str) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(encryption_key()).encrypt(nonce, value.encode(), _aad(workspace_id, capability))
    return "v1:" + base64.b64encode(nonce + ciphertext).decode()


def decrypt_key(value: str | None, workspace_id: str, capability: str) -> str:
    key = encryption_key()
    try:
        if not value or not value.startswith("v1:"):
            raise ValueError()
        data = base64.b64decode(value[3:], validate=True)
        return AESGCM(key).decrypt(data[:12], data[12:], _aad(workspace_id, capability)).decode()
    except (ValueError, InvalidTag, UnicodeError, binascii.Error):
        raise ModelConfigurationError("model_secret_unavailable", "The stored model key cannot be decrypted with this server configuration.", 503) from None
