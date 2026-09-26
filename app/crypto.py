import base64
import hashlib
import logging
from cryptography.fernet import Fernet, InvalidToken
from app.config import settings

logger = logging.getLogger("crypto")

def _get_fernet() -> Fernet:
    """
    Derives a deterministic 32-byte URL-safe base64 key from settings.SECRET_KEY.
    Provides robust symmetric AES-128-CBC encryption with SHA256 HMAC authentication.
    """
    secret = settings.SECRET_KEY.encode("utf-8")
    derived_32b = hashlib.sha256(secret).digest()
    key = base64.urlsafe_b64encode(derived_32b)
    return Fernet(key)

def is_encrypted(value: str) -> bool:
    """Checks whether a given string is already an encrypted Fernet token."""
    if not value or not isinstance(value, str):
        return False
    if not (value.startswith("gAAAAA") and len(value) >= 60):
        return False
    try:
        f = _get_fernet()
        f.decrypt(value.encode("utf-8"))
        return True
    except Exception:
        return False

def encrypt_value(value: str) -> str:
    """
    Encrypts a plaintext string.
    If value is already encrypted or empty, returns it directly to avoid double encryption.
    """
    if not value or not isinstance(value, str):
        return ""
    if is_encrypted(value):
        return value
    try:
        f = _get_fernet()
        return f.encrypt(value.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"Error encrypting value: {e}")
        return value

def decrypt_value(value: str) -> str:
    """
    Decrypts an encrypted string.
    If value is legacy plain text or not encrypted with this key, returns value as-is.
    """
    if not value or not isinstance(value, str):
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        # Fallback to plain text if not a valid Fernet token
        return value
