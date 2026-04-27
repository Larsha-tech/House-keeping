"""FastAPI dependencies - JWT auth, role gating, rate-limit helpers."""
from typing import Callable, List

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole
from .config import settings
from .security import decode_token

# tokenUrl is informational; we do custom JSON login but this lets FastAPI docs render.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/login", auto_error=False)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exc
    try:
        payload = decode_token(token)
    except JWTError:
        raise credentials_exc

    if payload.get("type") != "access":
        raise credentials_exc

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exc

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise credentials_exc
    return user


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    """Factory dependency - returns a checker that enforces role membership."""
    allowed: List[str] = [r.value if hasattr(r, "value") else str(r) for r in roles]

    def checker(user: User = Depends(get_current_user)) -> User:
        user_role = user.role.value if hasattr(user.role, "value") else str(user.role)
        if user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(allowed)}",
            )
        return user

    return checker


# Shorthand deps
require_admin = require_roles(UserRole.admin)
require_admin_or_supervisor = require_roles(UserRole.admin, UserRole.supervisor)
require_any_role = require_roles(UserRole.admin, UserRole.supervisor, UserRole.staff)


def get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
