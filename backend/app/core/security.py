"""Security primitives: bcrypt password hashing and JWT encode/decode."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings

# bcrypt via passlib. Rounds=12 is a sane production default.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def _create_token(
    subject: str,
    expires_minutes: int,
    token_type: str,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
        "type": token_type,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str, extra: Optional[Dict[str, Any]] = None) -> str:
    return _create_token(
        subject,
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        "access",
        extra,
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(
        subject,
        settings.JWT_REFRESH_TOKEN_EXPIRE_MINUTES,
        "refresh",
    )


def decode_token(token: str) -> Dict[str, Any]:
    """Raises JWTError on failure."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "JWTError",
]
