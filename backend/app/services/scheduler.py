"""Background scheduler powered by APScheduler.

Jobs:
  * mark_missed_tasks     - every N minutes, flags overdue pending/in_progress tasks
  * generate_recurring    - daily at 00:00 server time, clones daily/weekly/monthly templates
  * send_reminders        - every minute, emails assignees N minutes before due_time

The scheduler shares the SQLAlchemy engine via SessionLocal.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from ..core.config import settings
from ..database import SessionLocal
from ..models import ChecklistItem, Recurrence, Task, TaskStatus
from .audit import Actions, log_action
from .notification import notifier

logger = logging.getLogger("hobb.scheduler")
_scheduler: AsyncIOScheduler | None = None


# ── Jobs ─────────────────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


async def mark_missed_tasks() -> None:
    """Flip pending/in_progress tasks past their due_time to 'missed'."""
    db: Session = SessionLocal()
    try:
        today = date.today()
        now_t = datetime.now().time()

        candidates: List[Task] = (
            db.query(Task)
            .filter(
                Task.status.in_([TaskStatus.pending, TaskStatus.in_progress]),
                Task.due_date.isnot(None),
            )
            .all()
        )
        flipped: List[Task] = []
        for t in candidates:
            overdue = (
                t.due_date < today
                or (t.due_date == today and t.due_time is not None and t.due_time < now_t)
            )
            if not overdue:
                continue
            t.status = TaskStatus.missed
            log_action(
                db,
                user_id=None,
                action=Actions.TASK_MISSED,
                entity_type="task",
                entity_id=t.id,
                details="auto-marked by scheduler",
                commit=False,
            )
            flipped.append(t)
        if flipped:
            db.commit()
            logger.info("mark_missed_tasks: flipped %d task(s)", len(flipped))
            # Notify after commit so we don't alert on a rolled-back change
            for t in flipped:
                try:
                    await notifier.task_overdue(db, t)
                except Exception:
                    logger.exception("notification failed for task %s", t.id)
    except Exception:
        db.rollback()
        logger.exception("mark_missed_tasks failed")
    finally:
        db.close()


def _needs_instance_today(template: Task, today: date, db: Session) -> bool:
    """Does this recurring template already have a concrete instance for today?"""
    exists = (
        db.query(Task.id)
        .filter(Task.parent_task_id == template.id, Task.due_date == today)
        .first()
    )
    return exists is None


async def generate_recurring_tasks() -> None:
    """Clone daily/weekly/monthly templates into today's task list if needed.

    A 'template' is any task whose recurrence != none. For each template
    whose cadence lines up with today, create a fresh instance whose
    parent_task_id points back at the template.
    """
    db: Session = SessionLocal()
    try:
        today = date.today()
        templates = (
            db.query(Task)
            .filter(Task.recurrence != Recurrence.none, Task.parent_task_id.is_(None))
            .all()
        )
        created: List[Task] = []
        for tmpl in templates:
            # Cadence check
            if tmpl.recurrence == Recurrence.daily:
                should_run = True
            elif tmpl.recurrence == Recurrence.weekly:
                ref = tmpl.due_date or tmpl.created_at.date()
                should_run = today.weekday() == ref.weekday()
            elif tmpl.recurrence == Recurrence.monthly:
                ref = tmpl.due_date or tmpl.created_at.date()
                should_run = today.day == ref.day
            else:
                should_run = False

            if not should_run:
                continue
            if not _needs_instance_today(tmpl, today, db):
                continue

            clone = Task(
                title=tmpl.title,
                description=tmpl.description,
                location_id=tmpl.location_id,
                company_id=tmpl.company_id,
                priority=tmpl.priority,
                due_date=today,
                due_time=tmpl.due_time,
                assigned_to=tmpl.assigned_to,
                status=TaskStatus.pending,
                shift=tmpl.shift,
                recurrence=Recurrence.none,   # instance itself doesn't recur
                parent_task_id=tmpl.id,
            )
            db.add(clone)
            db.flush()
            # Clone checklist
            for item in tmpl.checklist:
                db.add(ChecklistItem(task_id=clone.id, text=item.text, done=False))

            log_action(
                db,
                user_id=None,
                action=Actions.TASK_RECURRING_GENERATED,
                entity_type="task",
                entity_id=clone.id,
                details=f"spawned from template {tmpl.id}",
                commit=False,
            )
            created.append(clone)

        if created:
            db.commit()
            logger.info("generate_recurring_tasks: created %d instance(s)", len(created))
            for clone in created:
                try:
                    await notifier.task_assigned(db, clone)
                except Exception:
                    logger.exception("notification failed for task %s", clone.id)
    except Exception:
        db.rollback()
        logger.exception("generate_recurring_tasks failed")
    finally:
        db.close()


async def send_due_reminders() -> None:
    """Email assignees ~REMINDER_LEAD_MINUTES before due_time."""
    db: Session = SessionLocal()
    try:
        today = date.today()
        now_dt = datetime.now()
        lead = timedelta(minutes=settings.REMINDER_LEAD_MINUTES)
        window = timedelta(minutes=1)

        tasks = (
            db.query(Task)
            .filter(
                Task.due_date == today,
                Task.due_time.isnot(None),
                Task.status.in_([TaskStatus.pending, TaskStatus.in_progress]),
                Task.assigned_to.isnot(None),
            )
            .all()
        )
        for t in tasks:
            if t.due_time is None:
                continue
            due_dt = datetime.combine(today, t.due_time)
            delta = due_dt - now_dt
            if lead - window <= delta <= lead + window:
                try:
                    await notifier.task_reminder(db, t)
                except Exception:
                    logger.exception("reminder failed for task %s", t.id)
    except Exception:
        logger.exception("send_due_reminders failed")
    finally:
        db.close()


# ── Lifecycle ────────────────────────────────────────────────────────────
def start_scheduler() -> None:
    global _scheduler
    if not settings.SCHEDULER_ENABLED:
        logger.info("scheduler disabled by config")
        return
    if _scheduler is not None:
        return

    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        mark_missed_tasks,
        IntervalTrigger(minutes=settings.MISSED_TASK_CHECK_INTERVAL_MINUTES),
        id="mark_missed_tasks",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.add_job(
        generate_recurring_tasks,
        CronTrigger(hour=settings.RECURRING_TASK_GENERATION_HOUR, minute=5),
        id="generate_recurring_tasks",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.add_job(
        send_due_reminders,
        IntervalTrigger(minutes=1),
        id="send_due_reminders",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info("scheduler started with %d job(s)", len(_scheduler.get_jobs()))


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler stopped")
