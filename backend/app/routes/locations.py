"""Locations and Companies management."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..core.deps import get_client_ip, require_admin, require_admin_or_supervisor, require_any_role
from ..database import get_db
from ..models import Company, Location, User
from ..schemas import CompanyCreate, CompanyOut, LocationCreate, LocationOut, LocationUpdate
from ..services.audit import Actions, log_action

router = APIRouter(tags=["locations"])


# ── Companies ────────────────────────────────────────────────────────────
@router.get("/companies", response_model=List[CompanyOut])
def list_companies(
    current: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    return [CompanyOut.model_validate(c) for c in db.query(Company).order_by(Company.name).all()]


@router.post("/companies", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    request: Request,
    payload: CompanyCreate,
    current: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    company = Company(name=payload.name)
    db.add(company)
    db.flush()
    log_action(
        db,
        user_id=current.id,
        action=Actions.COMPANY_CREATED,
        entity_type="company",
        entity_id=company.id,
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    db.refresh(company)
    return CompanyOut.model_validate(company)


# ── Locations ────────────────────────────────────────────────────────────
@router.get("/locations", response_model=List[LocationOut])
def list_locations(
    current: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    q = db.query(Location)
    if current.company_id:
        q = q.filter((Location.company_id == current.company_id) | (Location.company_id.is_(None)))
    return [LocationOut.model_validate(l) for l in q.order_by(Location.name).all()]


@router.post("/locations", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(
    request: Request,
    payload: LocationCreate,
    current: User = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    loc = Location(
        name=payload.name,
        company_id=payload.company_id or current.company_id,
    )
    db.add(loc)
    db.flush()
    log_action(
        db,
        user_id=current.id,
        action=Actions.LOCATION_CREATED,
        entity_type="location",
        entity_id=loc.id,
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    db.refresh(loc)
    return LocationOut.model_validate(loc)


@router.put("/locations/{location_id}", response_model=LocationOut)
def update_location(
    request: Request,
    location_id: str,
    payload: LocationUpdate,
    current: User = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    loc = db.get(Location, location_id)
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(loc, k, v)

    log_action(
        db,
        user_id=current.id,
        action=Actions.LOCATION_UPDATED,
        entity_type="location",
        entity_id=loc.id,
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    db.refresh(loc)
    return LocationOut.model_validate(loc)


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(
    request: Request,
    location_id: str,
    current: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    loc = db.get(Location, location_id)
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    db.delete(loc)
    log_action(
        db,
        user_id=current.id,
        action=Actions.LOCATION_DELETED,
        entity_type="location",
        entity_id=location_id,
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    return None
