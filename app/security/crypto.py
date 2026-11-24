"""Encryption at rest (step 17): AES-256-GCM for sensitive database fields and for LangGraph checkpoints.

Key management
  DATA_ENCRYPTION_KEY       base64 of 32 random bytes; the active key (generate: python -m app.security.crypto)
  DATA_ENCRYPTION_OLD_KEYS  comma-separated base64 keys kept only to decrypt data written before a rotation
Ciphertext carries the key id (first 8 hex of SHA-256 of the key), so rotation is: put the old key in
DATA_ENCRYPTION_OLD_KEYS, set a new DATA_ENCRYPTION_KEY, and run `python -m app.security.crypto --reencrypt`.

Field format: "enc:v1:<key id>:<base64(nonce || ciphertext+tag)>". Values without the prefix are legacy plaintext
and are returned unchanged (and re-encrypted by --reencrypt), so encryption can be switched on for existing data.
"""

import base64
import hashlib
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

PREFIX = "enc:v1:"


class EncryptionKeyError(RuntimeError):
    pass


def _kid(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:8]


@lru_cache
def keyring() -> tuple[str, dict[str, bytes]]:
    """(active key id, {key id: key}). Reads settings so tests and deployments can set their own keys."""
    from app.config import get_settings

    s = get_settings()
    if not s.data_encryption_key:
        raise EncryptionKeyError("DATA_ENCRYPTION_KEY is not set (generate one with `python -m app.security.crypto`)")
    keys = {}
    for k in [s.data_encryption_key, *[x for x in s.data_encryption_old_keys.split(",") if x.strip()]]:
        raw = base64.b64decode(k.strip())
        if len(raw) != 32:
            raise EncryptionKeyError("Encryption keys must be 32 bytes (AES-256), base64-encoded")
        keys[_kid(raw)] = raw
    return _kid(base64.b64decode(s.data_encryption_key.strip())), keys


def encrypt_bytes(data: bytes, aad: bytes = b"") -> tuple[str, bytes]:
    kid, keys = keyring()
    nonce = os.urandom(12)
    return kid, nonce + AESGCM(keys[kid]).encrypt(nonce, data, aad or None)


def decrypt_bytes(kid: str, blob: bytes, aad: bytes = b"") -> bytes:
    keys = keyring()[1]
    if kid not in keys:
        raise EncryptionKeyError(f"No key with id {kid} (was it removed from DATA_ENCRYPTION_OLD_KEYS?)")
    return AESGCM(keys[kid]).decrypt(blob[:12], blob[12:], aad or None)


def encrypt_str(value: str | None) -> str | None:
    if value is None or value.startswith(PREFIX):
        return value
    kid, blob = encrypt_bytes(value.encode("utf-8"))
    return f"{PREFIX}{kid}:{base64.b64encode(blob).decode()}"


def decrypt_str(value: str | None) -> str | None:
    if value is None or not value.startswith(PREFIX):
        return value  # legacy plaintext
    kid, b64 = value[len(PREFIX):].split(":", 1)
    return decrypt_bytes(kid, base64.b64decode(b64)).decode("utf-8")


class EncryptedText(TypeDecorator):
    """A Text column stored encrypted. Not searchable or indexable by design: use it for content, not keys."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_str(value)

    def process_result_value(self, value, dialect):
        return decrypt_str(value)


class AesGcmCipher:
    """LangGraph CipherProtocol: checkpoints (full graph state) are encrypted with the active data key."""

    def encrypt(self, plaintext: bytes) -> tuple[str, bytes]:
        kid, blob = encrypt_bytes(plaintext)
        return f"aesgcm-{kid}", blob

    def decrypt(self, ciphername: str, ciphertext: bytes) -> bytes:
        return decrypt_bytes(ciphername.removeprefix("aesgcm-"), ciphertext)


def checkpoint_serializer():
    from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
    return EncryptedSerializer(AesGcmCipher())


# Columns stored with EncryptedText: (table, column)
ENCRYPTED_COLUMNS = [("sources", "masked_text"), ("users", "totp_secret")]


def reencrypt() -> dict:
    """Encrypt legacy plaintext and re-encrypt values written with an old key (run after a key rotation)."""
    from sqlalchemy import text

    from app.db import engine

    active = keyring()[0]
    counts: dict[str, int] = {}
    with engine.begin() as conn:
        for table, column in ENCRYPTED_COLUMNS:
            exists = conn.execute(text("SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c"),
                                  {"t": table, "c": column}).first()
            if not exists:
                continue
            n = 0
            for row_id, stored in conn.execute(text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL")).all():
                if stored.startswith(f"{PREFIX}{active}:"):
                    continue
                conn.execute(text(f"UPDATE {table} SET {column} = :v WHERE id = :id"),
                             {"v": encrypt_str(decrypt_str(stored)), "id": row_id})
                n += 1
            counts[f"{table}.{column}"] = n
    return counts


if __name__ == "__main__":
    import sys

    if "--reencrypt" in sys.argv:
        from app.db import init_db
        init_db()
        print(reencrypt())
    else:
        print("DATA_ENCRYPTION_KEY=" + base64.b64encode(os.urandom(32)).decode())
