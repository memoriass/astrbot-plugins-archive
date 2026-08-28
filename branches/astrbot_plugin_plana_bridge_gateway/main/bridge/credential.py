from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import json
import os
import secrets
import stat
from abc import ABC, abstractmethod
from ctypes import wintypes
from pathlib import Path

class CredentialError(RuntimeError):
    pass


class CredentialProvider(ABC):
    @abstractmethod
    def get(self, credential_ref: str) -> dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    def put(self, credential_ref: str, secret: dict[str, str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, credential_ref: str) -> bool:
        raise NotImplementedError


class ProtectedFileCredentialProvider(CredentialProvider):
    """Encrypted local store with an OS-protected master key."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        _restrict_directory(self.root)
        self._key_path = self.root / "master.key"
        self._store_path = self.root / "credentials.enc"
        self._key = self._load_or_create_key()

    def get(self, credential_ref: str) -> dict[str, str]:
        secret = self._read_all().get(_clean_ref(credential_ref))
        if not isinstance(secret, dict):
            raise CredentialError("credential_not_found")
        return {str(key): str(value) for key, value in secret.items()}

    def put(self, credential_ref: str, secret: dict[str, str]) -> None:
        values = self._read_all()
        values[_clean_ref(credential_ref)] = _clean_secret(secret)
        self._write_all(values)

    def delete(self, credential_ref: str) -> bool:
        values = self._read_all()
        existed = values.pop(_clean_ref(credential_ref), None) is not None
        if existed:
            self._write_all(values)
        return existed

    def _load_or_create_key(self) -> bytes:
        if self._key_path.is_file():
            return _unprotect_key(self._key_path.read_bytes())
        key = secrets.token_bytes(32)
        _atomic_write(self._key_path, _protect_key(key))
        return key

    def _read_all(self) -> dict[str, dict[str, str]]:
        if not self._store_path.is_file():
            return {}
        try:
            plaintext = _decrypt(self._key, self._store_path.read_bytes())
            data = json.loads(plaintext.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CredentialError("credential_store_unreadable") from exc
        if not isinstance(data, dict):
            raise CredentialError("credential_store_invalid")
        return data

    def _write_all(self, values: dict[str, dict[str, str]]) -> None:
        plaintext = json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8")
        _atomic_write(self._store_path, _encrypt(self._key, plaintext))


def _clean_ref(value: str) -> str:
    clean = str(value or "").strip()
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    if not clean or len(clean) > 128 or any(char not in allowed for char in clean):
        raise CredentialError("credential_ref_invalid")
    return clean


def _clean_secret(secret: dict[str, str]) -> dict[str, str]:
    if not isinstance(secret, dict) or not secret or len(secret) > 16:
        raise CredentialError("credential_invalid")
    clean: dict[str, str] = {}
    for key, value in secret.items():
        clean_key = str(key or "").strip()
        clean_value = str(value or "")
        if not clean_key or len(clean_key) > 64 or len(clean_value) > 16384:
            raise CredentialError("credential_invalid")
        clean[clean_key] = clean_value
    return clean


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_bytes(data)
    _restrict_file(temporary)
    temporary.replace(path)
    _restrict_file(path)


def _encrypt(key: bytes, plaintext: bytes) -> bytes:
    nonce = secrets.token_bytes(16)
    ciphertext = _xor_stream(key, nonce, plaintext)
    body = b"PLANA-CRED-1\0" + nonce + ciphertext
    return body + hmac.new(key, body, hashlib.sha256).digest()


def _decrypt(key: bytes, token: bytes) -> bytes:
    prefix = b"PLANA-CRED-1\0"
    if not token.startswith(prefix) or len(token) < len(prefix) + 16 + 32:
        raise ValueError("credential_ciphertext_invalid")
    body, supplied_mac = token[:-32], token[-32:]
    expected_mac = hmac.new(key, body, hashlib.sha256).digest()
    if not hmac.compare_digest(supplied_mac, expected_mac):
        raise ValueError("credential_ciphertext_invalid")
    nonce = body[len(prefix) : len(prefix) + 16]
    ciphertext = body[len(prefix) + 16 :]
    return _xor_stream(key, nonce, ciphertext)


def _xor_stream(key: bytes, nonce: bytes, value: bytes) -> bytes:
    output = bytearray(len(value))
    offset = 0
    counter = 0
    while offset < len(value):
        block = hmac.new(
            key,
            b"stream\0" + nonce + counter.to_bytes(8, "big"),
            hashlib.sha256,
        ).digest()
        chunk = value[offset : offset + len(block)]
        output[offset : offset + len(chunk)] = bytes(
            left ^ right for left, right in zip(chunk, block)
        )
        offset += len(chunk)
        counter += 1
    return bytes(output)


def _restrict_directory(path: Path) -> None:
    if os.name != "nt":
        path.chmod(stat.S_IRWXU)


def _restrict_file(path: Path) -> None:
    if os.name != "nt":
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _protect_key(key: bytes) -> bytes:
    if os.name != "nt":
        return key
    return b"DPAPI\0" + base64.b64encode(_dpapi(key, protect=True))


def _unprotect_key(stored: bytes) -> bytes:
    if os.name != "nt":
        return stored
    if not stored.startswith(b"DPAPI\0"):
        raise CredentialError("credential_master_key_invalid")
    try:
        protected = base64.b64decode(stored[6:], validate=True)
    except ValueError as exc:
        raise CredentialError("credential_master_key_invalid") from exc
    return _dpapi(protected, protect=False)


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    source_buffer = ctypes.create_string_buffer(data)
    source = _DataBlob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    target = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    result = function(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target))
    if not result:
        raise CredentialError("credential_master_key_protection_failed")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(target.pbData)
