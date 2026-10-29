"""Các hàm mật mã dùng chung: băm mật khẩu, TOTP, chữ ký Ed25519, HMAC, JSON chuẩn hoá."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import struct

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

_ph = PasswordHasher()  # Argon2id, tham số mặc định của thư viện


# ---------- Mật khẩu ----------
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# ---------- JSON chuẩn hoá + băm ----------
def canonical(obj) -> bytes:
    """Biểu diễn JSON duy nhất cho một đối tượng: cùng dữ liệu -> cùng chuỗi byte -> cùng chữ ký."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hmac_hex(key: bytes, data: bytes) -> str:
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def const_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def random_hex(nbytes: int = 16) -> str:
    return secrets.token_hex(nbytes)


# ---------- TOTP (RFC 6238) ----------
TOTP_STEP = 30


def new_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode()


def totp_at(secret: str, counter: int, digits: int = 6) -> str:
    key = base64.b32decode(secret)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % 10 ** digits
    return f"{code:0{digits}d}"


def totp_now(secret: str, now: float) -> str:
    return totp_at(secret, int(now // TOTP_STEP))


def match_totp(secret: str, code: str, now: float, window: int = 1):
    """Trả về bộ đếm (counter) khớp với mã, hoặc None. Cho phép lệch ±window bước thời gian."""
    current = int(now // TOTP_STEP)
    for c in range(current - window, current + window + 1):
        if hmac.compare_digest(totp_at(secret, c), str(code)):
            return c
    return None


# ---------- Chữ ký số Ed25519 ----------
class DeviceKey:
    """Khoá riêng nằm trên thiết bị người dùng (điện thoại / khoá bảo mật). Máy chủ chỉ giữ khoá công khai."""

    def __init__(self, private_key: Ed25519PrivateKey | None = None):
        self._sk = private_key or Ed25519PrivateKey.generate()

    @property
    def public_key_b64(self) -> str:
        raw = self._sk.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return base64.b64encode(raw).decode()

    def sign(self, message: bytes) -> str:
        return base64.b64encode(self._sk.sign(message)).decode()


def verify_signature(public_key_b64: str, message: bytes, signature_b64: str) -> bool:
    try:
        pk = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        pk.verify(base64.b64decode(signature_b64), message)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
