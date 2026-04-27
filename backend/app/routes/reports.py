"""Reports endpoint — attendance & task summaries for admin/supervisor."""
from calendar import monthrange
from collections import Counter
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.deps import require_admin_or_supervisor
from ..database import get_db
from ..models import Attendance, Task, User, UserRole

router = APIRouter(prefix="/reports", tags=["reports"])


def _date_range(period: str, ref: date):
    if period == "daily":
        return ref, ref
    if period == "weekly":
        start = ref - timedelta(days=ref.weekday())
        return start, start + timedelta(days=6)
    if period == "monthly":
        start = ref.replace(day=1)
        _, last = monthrange(ref.year, ref.month)
        return start, ref.replace(day=last)
    return ref.replace(month=1, day=1), ref.replace(month=12, day=31)


@router.get("/summary")
def get_summary(
    period: str = Query("weekly", pattern="^(daily|weekly|monthly|yearly)$"),
    ref_date: Optional[date] = None,
    current: User = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    ref = ref_date or date.today()
    date_from, date_to = _date_range(period, ref)
    calendar_days = (date_to - date_from).days + 1

    staff = (
        db.query(User)
        .filter(
            User.company_id == current.company_id,
            User.role == UserRole.staff,
            User.is_active.is_(True),
        )
        .order_by(User.name)
        .all()
    )
    staff_ids = [u.id for u in staff]

    # Name map for all users (tasks can be assigned to non-staff too)
    all_users = db.query(User).filter(User.company_id == current.company_id).all()
    name_map = {u.id: u.name for u in all_users}

    att_rows = (
        db.query(Attendance)
        .filter(
            Attendance.user_id.in_(staff_ids),
            Attendance.date >= date_from,
            Attendance.date <= date_to,
        )
        .order_by(Attendance.date, Attendance.start_time)
        .all()
    )

    att_by_user: dict[str, list] = {uid: [] for uid in staff_ids}
    for r in att_rows:
        att_by_user[r.user_id].append(r)

    attendance_summary = []
    for u in staff:
        recs = att_by_user[u.id]
        total_minutes = sum(
            round((r.end_time - r.start_time).total_seconds() / 60)
            for r in recs if r.start_time and r.end_time
        )
        attendance_summary.append({
            "user_id": u.id,
            "user_name": u.name,
            "days_present": sum(1 for r in recs if r.start_time),
            "total_minutes": total_minutes,
            "records": [
                {
                    "date": str(r.date),
                    "start_time": r.start_time.isoformat() if r.start_time else None,
                    "end_time": r.end_time.isoformat() if r.end_time else None,
                    "minutes": round((r.end_time - r.start_time).total_seconds() / 60)
                    if r.start_time and r.end_time else None,
                }
                for r in recs
            ],
        })

    task_rows = (
        db.query(Task)
        .filter(
            Task.company_id == current.company_id,
            Task.due_date >= date_from,
            Task.due_date <= date_to,
        )
        .order_by(Task.due_date, Task.due_time)
        .all()
    )

    task_by_user: dict[str, list] = {uid: [] for uid in staff_ids}
    for t in task_rows:
        if t.assigned_to in task_by_user:
            task_by_user[t.assigned_to].append(t)

    task_by_user_summary = [
        {
            "user_id": u.id,
            "user_name": u.name,
            "total": len(task_by_user[u.id]),
            "pending": sum(1 for t in task_by_user[u.id] if t.status.value == "pending"),
            "in_progress": sum(1 for t in task_by_user[u.id] if t.status.value == "in_progress"),
            "completed": sum(1 for t in task_by_user[u.id] if t.status.value == "completed"),
            "missed": sum(1 for t in task_by_user[u.id] if t.status.value == "missed"),
            "approved": sum(1 for t in task_by_user[u.id] if t.status.value == "approved"),
            "rejected": sum(1 for t in task_by_user[u.id] if t.status.value == "rejected"),
        }
        for u in staff
    ]

    status_counts = Counter(t.status.value for t in task_rows)

    task_list = [
        {
            "id": t.id,
            "title": t.title,
            "due_date": str(t.due_date) if t.due_date else None,
            "user_name": name_map.get(t.assigned_to, "Unassigned") if t.assigned_to else "Unassigned",
            "status": t.status.value,
            "priority": t.priority.value,
        }
        for t in task_rows
    ]

    return {
        "period": period,
        "date_from": str(date_from),
        "date_to": str(date_to),
        "calendar_days": calendar_days,
        "attendance": attendance_summary,
        "task_list": task_list,
        "tasks": {
            "total": len(task_rows),
            "pending": status_counts.get("pending", 0),
            "in_progress": status_counts.get("in_progress", 0),
            "completed": status_counts.get("completed", 0),
            "missed": status_counts.get("missed", 0),
            "approved": status_counts.get("approved", 0),
            "rejected": status_counts.get("rejected", 0),
            "by_user": task_by_user_summary,
        },
    }
