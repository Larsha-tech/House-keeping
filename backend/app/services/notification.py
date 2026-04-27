"""Notification orchestrator.

Designed as a channel-dispatch facade so WhatsApp / push / SMS can be
added later without changing callsites. Current channel: email.
"""
from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from ..models import Task, User, UserRole
from .email import send_email

logger = logging.getLogger("hobb.notify")


class Notifier:
    """Each method is fire-and-forget: failures are logged, never raised."""

    @staticmethod
    async def _admins_and_supervisors(db: Session, company_id: Optional[str]) -> List[User]:
        q = db.query(User).filter(
            User.is_active.is_(True),
            User.role.in_([UserRole.admin, UserRole.supervisor]),
        )
        if company_id:
            q = q.filter(User.company_id == company_id)
        return q.all()

    @staticmethod
    async def task_assigned(db: Session, task: Task) -> None:
        if not task.assigned_to:
            return
        user = db.get(User, task.assigned_to)
        if not user or not user.email:
            return
        subject = f"[HOBB] New task assigned: {task.title}"
        body = (
            f"Hi {user.name},\n\n"
            f"You've been assigned a new task.\n\n"
            f"Title: {task.title}\n"
            f"Priority: {task.priority}\n"
            f"Due: {task.due_date} {task.due_time or ''}\n\n"
            f"Please open the HOBB app to view details.\n"
        )
        await send_email(to=[user.email], subject=subject, body=body)

    @staticmethod
    async def task_overdue(db: Session, task: Task) -> None:
        recipients = await Notifier._admins_and_supervisors(db, task.company_id)
        if not recipients:
            return
        emails = [u.email for u in recipients if u.email]
        subject = f"[HOBB] Task overdue: {task.title}"
        body = (
            f"Task '{task.title}' (id: {task.id}) has been marked as missed.\n"
            f"Due: {task.due_date} {task.due_time or ''}\n"
            f"Assignee: {task.assigned_to}\n"
        )
        await send_email(to=emails, subject=subject, body=body)

    @staticmethod
    async def task_completed(db: Session, task: Task) -> None:
        recipients = await Notifier._admins_and_supervisors(db, task.company_id)
        emails = [u.email for u in recipients if u.email]
        if not emails:
            return
        subject = f"[HOBB] Task completed: {task.title}"
        body = (
            f"'{task.title}' was marked completed and is awaiting review.\n"
            f"Completed at: {task.completed_at}\n"
            f"Assignee: {task.assigned_to}\n"
        )
        await send_email(to=emails, subject=subject, body=body)

    @staticmethod
    async def task_reminder(db: Session, task: Task) -> None:
        if not task.assigned_to:
            return
        user = db.get(User, task.assigned_to)
        if not user or not user.email:
            return
        subject = f"[HOBB] Reminder: {task.title} due soon"
        body = (
            f"Hi {user.name},\n\n"
            f"Reminder: '{task.title}' is due at {task.due_time} on {task.due_date}.\n"
        )
        await send_email(to=[user.email], subject=subject, body=body)


notifier = Notifier()
