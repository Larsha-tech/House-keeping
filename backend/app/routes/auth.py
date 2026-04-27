"""Authentication endpoints: login, refresh, me."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.deps import get_client_ip, get_current_user
from ..core.rate_limit import limiter
from ..core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from ..database import get_db
from ..models import User
from ..schemas import LoginRequest, RefreshRequest, TokenResponse, UserOut
from ..services.audit import Actions, log_action

logger = logging.getLogger("hobb.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
def login(
    request: Request,
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    ip = get_client_ip(request)

    if not user or not verify_password(payload.password, user.password_hash):
        log_action(
            db,
            user_id=user.id if user else None,
            action=Actions.LOGIN_FAILED,
            entity_type="user",
            entity_id=user.id if user else None,
            details=f"email={payload.email}",
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    access = create_access_token(user.id, extra={"role": user.role.value, "email": user.email})
    refresh = create_refresh_token(user.id)

    log_action(
        db,
        user_id=user.id,
        action=Actions.LOGIN,
        entity_type="user",
        entity_id=user.id,
        ip_address=ip,
    )

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
def refresh(
    request: Request,
    payload: RefreshRequest,
    db: Session = Depends(get_db),
):
    try:
        data = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    user = db.get(User, data.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access = create_access_token(user.id, extra={"role": user.role.value, "email": user.email})
    new_refresh = create_refresh_token(user.id)

    log_action(
        db,
        user_id=user.id,
        action=Actions.TOKEN_REFRESH,
        entity_type="user",
        entity_id=user.id,
        ip_address=get_client_ip(request),
    )

    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return UserOut.model_validate(current)
