"""User management endpoints. Admin-only except self-listing."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..core.deps import get_client_ip, get_current_user, require_admin, require_any_role
from ..core.security import hash_password
from ..database import get_db
from ..models import User, UserRole
from ..schemas import UserCreate, UserOut, UserUpdate
from ..services.audit import Actions, log_action

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=List[UserOut])
def list_users(
    role: Optional[UserRole] = None,
    company_id: Optional[str] = None,
    current: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    q = db.query(User)
    # Staff can only see themselves; admin/supervisor see everyone (scoped to company if set)
    if current.role == UserRole.staff:
        q = q.filter(User.id == current.id)
    else:
        if current.company_id:
            q = q.filter((User.company_id == current.company_id) | (User.company_id.is_(None)))
        if role:
            q = q.filter(User.role == role)
        if company_id:
            q = q.filter(User.company_id == company_id)
    return [UserOut.model_validate(u) for u in q.order_by(User.created_at.desc()).all()]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    request: Request,
    payload: UserCreate,
    current: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        name=payload.name,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        avatar=payload.avatar or payload.name[:2].upper(),
        company_id=payload.company_id or current.company_id,
    )
    db.add(user)
    db.flush()
    log_action(
        db,
        user_id=current.id,
        action=Actions.USER_CREATED,
        entity_type="user",
        entity_id=user.id,
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: str,
    current: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    if current.role == UserRole.staff and user_id != current.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut.model_validate(user)


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    request: Request,
    user_id: str,
    payload: UserUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Users can edit their own name/email/password/avatar; admin can edit everything.
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    is_admin = current.role == UserRole.admin
    if not is_admin and target.id != current.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    data = payload.model_dump(exclude_unset=True)
    if "role" in data and not is_admin:
        raise HTTPException(status_code=403, detail="Only admin can change role")
    if "is_active" in data and not is_admin:
        raise HTTPException(status_code=403, detail="Only admin can change active state")

    if "password" in data and data["password"]:
        target.password_hash = hash_password(data.pop("password"))
    if "email" in data and data["email"]:
        data["email"] = data["email"].lower()

    for k, v in data.items():
        setattr(target, k, v)

    log_action(
        db,
        user_id=current.id,
        action=Actions.USER_UPDATED,
        entity_type="user",
        entity_id=target.id,
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    db.refresh(target)
    return UserOut.model_validate(target)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    request: Request,
    user_id: str,
    current: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == current.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    db.delete(target)
    log_action(
        db,
        user_id=current.id,
        action=Actions.USER_DELETED,
        entity_type="user",
        entity_id=user_id,
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    return None
