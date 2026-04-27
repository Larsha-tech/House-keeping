"""Task comment endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..core.deps import get_client_ip, require_any_role
from ..database import get_db
from ..models import Comment, Task, User, UserRole
from ..schemas import CommentCreate, CommentOut
from ..services.audit import Actions, log_action

router = APIRouter(prefix="/tasks", tags=["comments"])


@router.post(
    "/{task_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
def add_comment(
    request: Request,
    task_id: str,
    payload: CommentCreate,
    current: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if current.role == UserRole.staff and task.assigned_to != current.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    comment = Comment(task_id=task_id, author_id=current.id, text=payload.text)
    db.add(comment)
    db.flush()

    log_action(
        db,
        user_id=current.id,
        action=Actions.COMMENT_ADDED,
        entity_type="comment",
        entity_id=comment.id,
        details=f"task={task_id}",
        ip_address=get_client_ip(request),
        commit=False,
    )
    db.commit()
    db.refresh(comment)
    return CommentOut(
        id=comment.id,
        task_id=comment.task_id,
        author_id=comment.author_id,
        author_name=current.name,
        text=comment.text,
        timestamp=comment.timestamp,
    )
