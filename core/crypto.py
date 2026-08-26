# core/crypto.py
import json
import base64
import hashlib
import logging
from typing import Dict, Any, Union, Optional
from cryptography.fernet import Fernet, InvalidToken
from core.config import settings

logger = logging.getLogger("core.crypto")

_FERNET_PREFIX = "enc:"

def _get_fernet_key() -> bytes:
    """
    Derives a standard 32-byte URL-safe base64 Fernet key from
    DB_ENCRYPTION_KEY or ENTERPRISE_SECRET_KEY.
    """
    explicit_key = settings.DB_ENCRYPTION_KEY or ""
    if explicit_key.strip():
        raw_bytes = explicit_key.strip().encode("ascii")
        try:
            # Validate if it's already a valid Fernet key
            Fernet(raw_bytes)
            return raw_bytes
        except Exception:
            # If not valid 32-byte base64, hash it into one
            key_hash = hashlib.sha256(raw_bytes).digest()
            return base64.urlsafe_b64encode(key_hash)

    # Derive from ENTERPRISE_SECRET_KEY
    secret_bytes = (settings.ENTERPRISE_SECRET_KEY or "enterprise-secure-jwt-secret-key-production-32-chars").encode("utf-8")
    derived_hash = hashlib.sha256(b"localmind-db-crypto:" + secret_bytes).digest()
    return base64.urlsafe_b64encode(derived_hash)


def get_fernet() -> Fernet:
    """Returns an initialized Fernet cipher instance."""
    return Fernet(_get_fernet_key())


def encrypt_connection_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Encrypts a connection configuration dictionary into an encrypted wrapper dict.
    Returns: {"_encrypted_payload": "enc:<fernet_ciphertext>"}
    """
    if not isinstance(config, dict):
        raise TypeError("Connection config must be a dictionary")

    # If already encrypted, return as-is
    if "_encrypted_payload" in config:
        return config

    json_bytes = json.dumps(config, separators=(',', ':')).encode("utf-8")
    cipher_bytes = get_fernet().encrypt(json_bytes)
    token_str = f"{_FERNET_PREFIX}{cipher_bytes.decode('ascii')}"
    return {"_encrypted_payload": token_str}


def decrypt_connection_config(encrypted_val: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Decrypts a connection configuration token/dict back to the original dictionary.
    Handles legacy/unencrypted dictionary payloads seamlessly.
    """
    if not encrypted_val:
        return {}

    # Check if dict with _encrypted_payload wrapper
    if isinstance(encrypted_val, dict):
        if "_encrypted_payload" in encrypted_val:
            raw_token = encrypted_val["_encrypted_payload"]
            return decrypt_connection_config(raw_token)
        # Unencrypted legacy dict
        return encrypted_val

    if not isinstance(encrypted_val, str) or not encrypted_val.strip():
        return {}

    val = encrypted_val.strip()

    if val.startswith(_FERNET_PREFIX):
        cipher_part = val[len(_FERNET_PREFIX):]
        try:
            decrypted_bytes = get_fernet().decrypt(cipher_part.encode("ascii"))
            return json.loads(decrypted_bytes.decode("utf-8"))
        except InvalidToken:
            logger.error("Failed to decrypt connection config: Invalid or corrupt encryption token.")
            raise ValueError("Unable to decrypt stored connection credentials. Key mismatch or corrupt data.")
        except Exception as e:
            logger.error(f"Failed to decode decrypted connection config: {e}")
            raise ValueError(f"Malformed connection config payload: {e}")

    # Fallback for plain JSON strings
    try:
        parsed = json.loads(val)
        if isinstance(parsed, dict) and "_encrypted_payload" in parsed:
            return decrypt_connection_config(parsed["_encrypted_payload"])
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        raise ValueError("Invalid connection config string format")
