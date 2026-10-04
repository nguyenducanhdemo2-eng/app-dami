import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, status

from .config import Settings


class TokenCipher:
    def __init__(self, settings: Settings):
        raw_key = settings.token_encryption_key
        if raw_key and raw_key != "CHANGE_ME":
            try:
                key = raw_key.encode("ascii")
                Fernet(key)
            except (ValueError, TypeError):
                key = base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode()).digest())
        else:
            fallback = settings.session_secret or "unsafe-development-only"
            key = base64.urlsafe_b64encode(hashlib.sha256(fallback.encode()).digest())
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("Không thể giải mã access token. Kiểm tra TOKEN_ENCRYPTION_KEY.") from exc


def password_matches(candidate: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(candidate.encode(), expected.encode())


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def require_admin(request: Request) -> None:
    """Đã bỏ yêu cầu đăng nhập: luôn cho phép truy cập."""
    pass


def require_csrf(request: Request) -> None:
    """Đã bỏ yêu cầu CSRF: luôn cho phép gửi dữ liệu."""
    pass

