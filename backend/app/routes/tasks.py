"""Task endpoints - list/create/update/delete + approve/reject workflow."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, joinedload

from ..core.deps import (
    get_client_ip,
    get_current_user,
    require_admin_or_supervisor,
    require_any_role,
)
from ..database import get_db
from ..models import ChecklistItem, Task, TaskStatus, User, UserRole
from ..schemas import (
    CommentOut,
    MessageResponse,
    TaskCreate,
    TaskOut,
    TaskRejectRequest,
    TaskUpdate,
)
from ..services.audit import Actions, log_action
from ..services.notification import notifier

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ── helpers ──────────────────────────────────────────────────────────────
def _load_task(db: Session, task_id: str) -> Task:
    task = (
        db.query(Task)
        .options(joinedload(Task.checklist), joinedload(Task.comments), joinedload(Task.location), joinedload(Task.assignee))
        .filter(Task.id == task_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _serialize(task: Task) -> TaskOut:
    data = TaskOut.model_validate(task)
    data.location_name = task.location.name if task.location else None
    data.assignee_name = task.assignee.name if task.assignee else None
    data.comments = [
        CommentOut(
            id=c.id,
            task_id=c.task_id,
            author_id=c.author_id,
            author_name=c.author.name if c.author else None,
            text=c.text,
            timestamp=c.timestamp,
        )
        for c in task.comments
    ]
    return data


def _can_view(user: User, task: Task) -> bool:
    if user.role in (UserRole.admin, UserRole.supervisor):
        return True
    return task.assigned_to == user.id


# ── endpoints ────────────────────────────────────────────────────────────
@router.get("", response_model=List[TaskOut])
def list_tasks(
    status_: Optional[TaskStatus] = None,
    assigned_to: Optional[str] = None,
    due_date: Optional[str] = None,
    current: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    q = db.query(Task).options(
        joinedload(Task.checklist),
        joinedload(Task.comments),
        joinedload(Task.location),
        joinedload(Task.assignee),
    )

    # Scope: staff sees only their own
    if current.role == UserRole.staff:
        q = q.filter(Task.assigned_to == current.id)

    if status_:
        q = q.filter(Task.status == status_)
    if assigned_to:
        q = q.filter(Task.assigned_to == assigned_to)
    if due_date:
        q = q.filter(Task.due_date == due_date)

    tasks = q.order_by(Task.due_date.desc().nullslast(), Task.due_time.asc().nullslast()).all()
    return [_serialize(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: str,
    current: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    task = _load_task(db, task_id)
    if not _can_view(current, task):
        raise HTTPException(status_code=403, detail="Forbidden")
    return _serialize(task)


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: Request,
    payload: TaskCreate,
    background: BackgroundTasks,
    current: User = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    task = Task(
        title=payload.title,
        description=payload.description,
        location_id=payload.location_id,
        company_id=current.company_id,
        priority=payload.priority,
        due_date=payload.due_date,
        due_time=payload.due_time,
        assigned_to=payload.assigned_to,
        shift=payload.shift,
        recurrence=payload.recurrence,
        status=TaskStatus.pending,
    )
    db.add(task)
    db.flush()

    for item in payload.checklist:
        db.add(ChecklistItem(task_id=task.id, text=item.text, done=item.done))

    log_action(
        db,
        user_id=current.id,
        action=Actions.TASK_CREATED,
        entity_type="task",
        entity_id=task.id,
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()

    # Reload with relationships
    task = _load_task(db, task.id)

    # Fire-and-forget notify
    if task.assigned_to:
        background.add_task(_send_task_assigned, task.id)

    return _serialize(task)


async def _send_task_assigned(task_id: str) -> None:
    """Background wrapper - open its own session since request scope is gone."""
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task:
            await notifier.task_assigned(db, task)
    finally:
        db.close()


async def _send_task_completed(task_id: str) -> None:
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task:
            await notifier.task_completed(db, task)
    finally:
        db.close()


@router.put("/{task_id}", response_model=TaskOut)
async def update_task(
    request: Request,
    task_id: str,
    payload: TaskUpdate,
    background: BackgroundTasks,
    current: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    task = _load_task(db, task_id)

    # Staff can only update their own task status / proof images
    if current.role == UserRole.staff:
        if task.assigned_to != current.id:
            raise HTTPException(status_code=403, detail="Forbidden")
        if task.status == TaskStatus.approved:
            raise HTTPException(
                status_code=403,
                detail="This task has been approved and can no longer be edited",
            )
        allowed = {"status", "image_proof_before", "image_proof_after"}
        incoming = set(payload.model_dump(exclude_unset=True).keys())
        if not incoming.issubset(allowed):
            raise HTTPException(
                status_code=403,
                detail=f"Staff may only update: {', '.join(sorted(allowed))}",
            )

    prev_status = task.status
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(task, k, v)

    # Auto-stamp completed_at when transitioning to completed
    if payload.status == TaskStatus.completed and prev_status != TaskStatus.completed:
        task.completed_at = datetime.now(timezone.utc)
        log_action(
            db,
            user_id=current.id,
            action=Actions.TASK_COMPLETED,
            entity_type="task",
            entity_id=task.id,
            ip_address=get_client_ip(request),
            commit=False,
        )
        background.add_task(_send_task_completed, task.id)
    else:
        log_action(
            db,
            user_id=current.id,
            action=Actions.TASK_UPDATED,
            entity_type="task",
            entity_id=task.id,
            details=",".join(data.keys()),
            ip_address=get_client_ip(request),
            commit=False,
        )

    db.commit()
    task = _load_task(db, task.id)
    return _serialize(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    request: Request,
    task_id: str,
    current: User = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    task = _load_task(db, task_id)
    db.delete(task)
    log_action(
        db,
        user_id=current.id,
        action=Actions.TASK_DELETED,
        entity_type="task",
        entity_id=task_id,
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    return None


@router.post("/{task_id}/duplicate", response_model=TaskOut)
def duplicate_task(
    request: Request,
    task_id: str,
    current: User = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    original = _load_task(db, task_id)
    copy = Task(
        title=f"Copy of {original.title}",
        description=original.description,
        company_id=original.company_id,
        location_id=original.location_id,
        assigned_to=original.assigned_to,
        priority=original.priority,
        due_date=original.due_date,
        due_time=original.due_time,
        shift=original.shift,
        recurrence=original.recurrence,
        status=TaskStatus.pending,
    )
    db.add(copy)
    db.flush()
    for item in original.checklist:
        db.add(ChecklistItem(task_id=copy.id, text=item.text, done=False))
    log_action(
        db,
        user_id=current.id,
        action=Actions.TASK_CREATED,
        entity_type="task",
        entity_id=copy.id,
        details=f"duplicated from {original.id}",
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    return _serialize(_load_task(db, copy.id))


@router.post("/{task_id}/approve", response_model=TaskOut)
def approve_task(
    request: Request,
    task_id: str,
    current: User = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    task = _load_task(db, task_id)
    if task.status not in (TaskStatus.completed, TaskStatus.rejected):
        raise HTTPException(
            status_code=400,
            detail="Can only approve completed or previously-rejected tasks",
        )
    task.status = TaskStatus.approved
    task.approved_at = datetime.now(timezone.utc)
    task.approved_by = current.id
    task.rejection_reason = None
    log_action(
        db,
        user_id=current.id,
        action=Actions.TASK_APPROVED,
        entity_type="task",
        entity_id=task.id,
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    task = _load_task(db, task.id)
    return _serialize(task)


@router.post("/{task_id}/reject", response_model=TaskOut)
def reject_task(
    request: Request,
    task_id: str,
    payload: TaskRejectRequest,
    current: User = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    task = _load_task(db, task_id)
    task.status = TaskStatus.rejected
    task.rejection_reason = payload.reason
    task.approved_at = None
    task.approved_by = None
    log_action(
        db,
        user_id=current.id,
        action=Actions.TASK_REJECTED,
        entity_type="task",
        entity_id=task.id,
        details=payload.reason,
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    task = _load_task(db, task.id)
    return _serialize(task)
