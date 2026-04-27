"""Idempotent seed script run at startup (when SEED_ON_STARTUP is true).

Creates:
  - One company (if none exists)
  - Admin user (credentials from .env)
  - Default locations (if none exist)
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .core.config import settings
from .core.security import hash_password
from .models import Company, Location, User, UserRole

logger = logging.getLogger("hobb.seed")


def _ensure_user(db: Session, *, email: str, name: str, password: str, role: UserRole,
                 avatar: str, company_id: str) -> User:
    user = db.query(User).filter(User.email == email.lower()).first()
    if user:
        return user
    user = User(
        name=name,
        email=email.lower(),
        password_hash=hash_password(password),
        role=role,
        avatar=avatar,
        company_id=company_id,
        is_active=True,
    )
    db.add(user)
    db.flush()
    logger.info("seeded user %s (%s)", email, role.value)
    return user


def _ensure_location(db: Session, *, name: str, company_id: str) -> Location:
    loc = db.query(Location).filter(Location.name == name, Location.company_id == company_id).first()
    if loc:
        return loc
    loc = Location(name=name, company_id=company_id)
    db.add(loc)
    db.flush()
    return loc


def seed(db: Session) -> None:
    if not settings.SEED_ON_STARTUP:
        logger.info("SEED_ON_STARTUP=false - skipping seed")
        return

    # --- Company ---
    company = db.query(Company).first()
    if not company:
        company = Company(name="HOBB")
        db.add(company)
        db.flush()
        logger.info("seeded company id=%s", company.id)

    # --- Admin user ---
    admin_name = settings.SEED_ADMIN_EMAIL.split("@")[0].capitalize()
    _ensure_user(
        db,
        email=settings.SEED_ADMIN_EMAIL,
        name=admin_name,
        password=settings.SEED_ADMIN_PASSWORD,
        role=UserRole.admin,
        avatar=admin_name[:2].upper(),
        company_id=company.id,
    )

    # --- Default locations ---
    for name in ("Ground Floor", "Floor 1", "Floor 2", "Floor 3", "Basement"):
        _ensure_location(db, name=name, company_id=company.id)

    db.commit()
    logger.info("seed complete")
