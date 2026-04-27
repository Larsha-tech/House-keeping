"""Audit log writer - persists action records for every sensitive operation."""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from ..models import AuditLog

logger = logging.getLogger("hobb.audit")


def log_action(
    db: Session,
    *,
    user_id: Optional[str],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
    commit: bool = True,
) -> AuditLog:
    """Create an audit log entry.

    When called inside a route handler that will commit its own session,
    pass commit=False to fold this insert into that transaction.
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    else:
        db.flush()
    logger.info(
        "audit action=%s user=%s entity=%s:%s",
        action, user_id, entity_type, entity_id,
    )
    return entry


# Standard action identifiers (keep stable — dashboards / reports depend on these)
class Actions:
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"

    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"

    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_DELETED = "task_deleted"
    TASK_COMPLETED = "task_completed"
    TASK_APPROVED = "task_approved"
    TASK_REJECTED = "task_rejected"
    TASK_MISSED = "task_missed"
    TASK_RECURRING_GENERATED = "task_recurring_generated"

    CHECKLIST_UPDATED = "checklist_updated"
    COMMENT_ADDED = "comment_added"

    ATTENDANCE_START = "attendance_start"
    ATTENDANCE_END = "attendance_end"

    FILE_UPLOADED = "file_uploaded"

    LOCATION_CREATED = "location_created"
    LOCATION_UPDATED = "location_updated"
    LOCATION_DELETED = "location_deleted"

    COMPANY_CREATED = "company_created"
