"""Pydantic schemas - request/response DTOs.

Field names use snake_case. The frontend integration layer maps between
snake_case (API) and camelCase (existing UI props).
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import Recurrence, Shift, TaskPriority, TaskStatus, UserRole


# ── Base / common ────────────────────────────────────────────────────────
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


# ── Auth ─────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: "UserOut"


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Users ────────────────────────────────────────────────────────────────
class UserBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    role: UserRole = UserRole.staff
    avatar: Optional[str] = Field(default=None, max_length=8)


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=200)
    company_id: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    avatar: Optional[str] = Field(default=None, max_length=8)
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=200)


class UserOut(ORMBase):
    id: str
    name: str
    email: EmailStr
    role: UserRole
    avatar: Optional[str] = None
    is_active: bool
    company_id: Optional[str] = None
    created_at: datetime


# ── Company / Location ───────────────────────────────────────────────────
class CompanyBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CompanyCreate(CompanyBase):
    pass


class CompanyOut(ORMBase):
    id: str
    name: str
    created_at: datetime


class LocationBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    company_id: Optional[str] = None


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    company_id: Optional[str] = None


class LocationOut(ORMBase):
    id: str
    name: str
    company_id: Optional[str] = None
    created_at: datetime


# ── Checklist ────────────────────────────────────────────────────────────
class ChecklistItemIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    done: bool = False


class ChecklistItemUpdate(BaseModel):
    text: Optional[str] = Field(default=None, min_length=1, max_length=500)
    done: Optional[bool] = None


class ChecklistItemOut(ORMBase):
    id: str
    task_id: str
    text: str
    done: bool
    created_at: datetime


# ── Comments ─────────────────────────────────────────────────────────────
class CommentCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class CommentOut(ORMBase):
    id: str
    task_id: str
    author_id: str
    author_name: Optional[str] = None
    text: str
    timestamp: datetime


# ── Tasks ────────────────────────────────────────────────────────────────
class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = Field(default=None, max_length=5000)
    location_id: Optional[str] = None
    priority: TaskPriority = TaskPriority.medium
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    assigned_to: Optional[str] = None
    shift: Shift = Shift.morning
    recurrence: Recurrence = Recurrence.none


class TaskCreate(TaskBase):
    checklist: List[ChecklistItemIn] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    description: Optional[str] = Field(default=None, max_length=5000)
    location_id: Optional[str] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    assigned_to: Optional[str] = None
    status: Optional[TaskStatus] = None
    shift: Optional[Shift] = None
    recurrence: Optional[Recurrence] = None
    image_proof_before: Optional[str] = None
    image_proof_after: Optional[str] = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskRejectRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1000)


class TaskOut(ORMBase):
    id: str
    title: str
    description: Optional[str] = None
    location_id: Optional[str] = None
    location_name: Optional[str] = None
    company_id: Optional[str] = None
    priority: TaskPriority
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    assigned_to: Optional[str] = None
    assignee_name: Optional[str] = None
    status: TaskStatus
    shift: Shift
    recurrence: Recurrence
    image_proof_before: Optional[str] = None
    image_proof_after: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    checklist: List[ChecklistItemOut] = Field(default_factory=list)
    comments: List[CommentOut] = Field(default_factory=list)


# ── Attendance ───────────────────────────────────────────────────────────
class AttendanceStart(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500)


class AttendanceEnd(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500)


class AttendanceOut(ORMBase):
    id: str
    user_id: str
    user_name: Optional[str] = None
    date: date
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    notes: Optional[str] = None


# ── Upload ───────────────────────────────────────────────────────────────
class UploadResponse(BaseModel):
    url: str
    filename: str
    size_bytes: int
    content_type: str


# ── Audit ────────────────────────────────────────────────────────────────
class AuditLogOut(ORMBase):
    id: str
    user_id: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    details: Optional[str] = None
    timestamp: datetime


# ── Misc ─────────────────────────────────────────────────────────────────
class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    version: str


# Resolve forward references
TokenResponse.model_rebuild()
