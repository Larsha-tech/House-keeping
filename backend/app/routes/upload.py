"""File upload endpoint - returns structured path under /storage/uploads/."""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from ..core.deps import get_client_ip, require_any_role
from ..database import get_db
from ..models import User
from ..schemas import UploadResponse
from ..services.audit import Actions, log_action
from ..services.file_storage import save_upload
from sqlalchemy.orm import Session

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("", response_model=UploadResponse)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    task_id: Optional[str] = Form(default=None),
    kind: str = Form(default="general"),
    current: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    kind_norm = kind if kind in ("before", "after", "general") else "general"
    result = await save_upload(file, task_id=task_id, kind=kind_norm)  # type: ignore[arg-type]

    log_action(
        db,
        user_id=current.id,
        action=Actions.FILE_UPLOADED,
        entity_type="file",
        entity_id=result["filename"],
        details=f"task={task_id} kind={kind_norm} size={result['size_bytes']}",
        ip_address=get_client_ip(request),
    )

    return UploadResponse(
        url=result["url"],
        filename=result["filename"],
        size_bytes=result["size_bytes"],
        content_type=result["content_type"],
    )
