"""Checklist item toggle endpoint.

Checklist items are created as part of a Task. This route lets any
authorised viewer toggle done-state or edit text of a single item.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.deps import get_client_ip, require_any_role
from ..database import get_db
from ..models import ChecklistItem, Task, User, UserRole
from ..schemas import ChecklistItemOut, ChecklistItemUpdate
from ..services.audit import Actions, log_action

router = APIRouter(prefix="/checklist", tags=["checklist"])


@router.put("/{item_id}", response_model=ChecklistItemOut)
def update_checklist_item(
    request: Request,
    item_id: str,
    payload: ChecklistItemUpdate,
    current: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    item = db.get(ChecklistItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")

    task = db.get(Task, item.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Parent task not found")

    if current.role == UserRole.staff and task.assigned_to != current.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(item, k, v)

    log_action(
        db,
        user_id=current.id,
        action=Actions.CHECKLIST_UPDATED,
        entity_type="checklist_item",
        entity_id=item.id,
        details=f"task={task.id} done={item.done}",
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    db.refresh(item)
    return ChecklistItemOut.model_validate(item)
