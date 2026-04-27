"""Attendance endpoints - clock-in, clock-out, list-mine, list-all."""
from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.deps import get_client_ip, get_current_user, require_admin_or_supervisor, require_any_role
from ..database import get_db
from ..models import Attendance, User
from ..schemas import AttendanceEnd, AttendanceOut, AttendanceStart
from ..services.audit import Actions, log_action

router = APIRouter(prefix="/attendance", tags=["attendance"])


def _today_record(db: Session, user_id: str) -> Attendance | None:
    return (
        db.query(Attendance)
        .filter(Attendance.user_id == user_id, Attendance.date == date.today())
        .order_by(Attendance.start_time.desc().nullslast())
        .first()
    )


@router.post("/start", response_model=AttendanceOut)
def start_attendance(
    request: Request,
    payload: AttendanceStart,
    current: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    existing = _today_record(db, current.id)
    if existing and existing.start_time and not existing.end_time:
        raise HTTPException(status_code=400, detail="Attendance already started today")

    rec = Attendance(
        user_id=current.id,
        date=date.today(),
        start_time=datetime.now(timezone.utc),
        notes=payload.notes,
    )
    db.add(rec)
    db.flush()
    log_action(
        db,
        user_id=current.id,
        action=Actions.ATTENDANCE_START,
        entity_type="attendance",
        entity_id=rec.id,
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    db.refresh(rec)
    return AttendanceOut.model_validate(rec)


@router.post("/end", response_model=AttendanceOut)
def end_attendance(
    request: Request,
    payload: AttendanceEnd,
    current: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    rec = _today_record(db, current.id)
    if not rec or not rec.start_time:
        raise HTTPException(status_code=400, detail="No active attendance to end")
    if rec.end_time:
        raise HTTPException(status_code=400, detail="Attendance already ended")

    rec.end_time = datetime.now(timezone.utc)
    if payload.notes:
        rec.notes = (rec.notes + " | " + payload.notes) if rec.notes else payload.notes

    log_action(
        db,
        user_id=current.id,
        action=Actions.ATTENDANCE_END,
        entity_type="attendance",
        entity_id=rec.id,
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    db.refresh(rec)
    return AttendanceOut.model_validate(rec)


@router.get("/all", response_model=List[AttendanceOut])
def list_all_attendance(
    filter_date: Optional[date] = None,
    limit: int = 300,
    current: User = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    company_user_ids = [
        u.id for u in db.query(User).filter(User.company_id == current.company_id).all()
    ]
    q = (
        db.query(Attendance)
        .filter(Attendance.user_id.in_(company_user_ids))
        .order_by(Attendance.date.desc(), Attendance.start_time.desc().nullslast())
    )
    if filter_date:
        q = q.filter(Attendance.date == filter_date)
    rows = q.limit(min(limit, 500)).all()
    user_ids = {r.user_id for r in rows}
    name_map = {u.id: u.name for u in db.query(User).filter(User.id.in_(user_ids)).all()}
    result = []
    for r in rows:
        out = AttendanceOut.model_validate(r)
        out.user_name = name_map.get(r.user_id)
        result.append(out)
    return result


@router.get("/me", response_model=List[AttendanceOut])
def list_my_attendance(
    limit: int = 30,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Attendance)
        .filter(Attendance.user_id == current.id)
        .order_by(Attendance.date.desc(), Attendance.start_time.desc().nullslast())
        .limit(min(limit, 200))
        .all()
    )
    return [AttendanceOut.model_validate(r) for r in rows]
