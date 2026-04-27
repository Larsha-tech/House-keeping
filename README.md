# HOBB — Housekeeping Management System

Production-ready backend for the existing HOBB React frontend. FastAPI +
SQLAlchemy + Postgres + Docker + Nginx. Drop-in replacement for the
in-memory seed data; the UI stays as-is.

## Feature checklist

- ✅ JWT auth (access + refresh), bcrypt password hashing
- ✅ Role-based access control: **admin / supervisor / staff**
- ✅ Scalable multi-company / multi-location schema
- ✅ Full task lifecycle: pending → in_progress → completed → approved/rejected, plus auto-`missed`
- ✅ Checklist items, comments, attendance, image proofs (before/after)
- ✅ Upload endpoint with size/type validation + EXIF-strip + JPEG re-encode
- ✅ APScheduler background jobs: auto-miss overdue, clone recurring, send reminders
- ✅ Notification facade (email via SMTP, pluggable for WhatsApp/push later)
- ✅ Structured audit log for every sensitive action
- ✅ Rate limiting (slowapi + nginx edge)
- ✅ CORS, gzip, Pydantic v2 validation, global error handlers
- ✅ Env-based config (`.env`), non-root Docker image, nginx reverse proxy
- ✅ Alembic-ready; `create_all` for frictionless first boot
- ✅ DB + uploads backup scripts with retention

## Quickstart

```bash
unzip hobb.zip && cd hobb
bash scripts/setup.sh
```

Then open:

- http://localhost/api/docs — interactive API reference
- http://localhost/api/health — health check

Default credentials (change immediately in production):

| Role        | Email                  | Password     |
| ----------- | ---------------------- | ------------ |
| admin       | admin@hobb.com         | admin123     |
| supervisor  | supervisor@hobb.com    | super123     |
| staff       | priya@hobb.com         | staff123     |
| staff       | rajan@hobb.com         | staff123     |
| staff       | meena@hobb.com         | staff123     |

## Project layout

```
hobb/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI factory + lifespan
│   │   ├── database.py          Engine / SessionLocal / Base
│   │   ├── models.py            SQLAlchemy ORM models
│   │   ├── schemas.py           Pydantic DTOs
│   │   ├── seed.py              Idempotent startup seed
│   │   ├── core/
│   │   │   ├── config.py        Settings (pydantic-settings)
│   │   │   ├── security.py      bcrypt + JWT encode/decode
│   │   │   ├── deps.py          get_current_user, require_roles
│   │   │   ├── logging.py       console / JSON formatter
│   │   │   └── rate_limit.py    slowapi limiter
│   │   ├── routes/
│   │   │   ├── auth.py          /auth/login, /refresh, /me
│   │   │   ├── users.py         /users CRUD
│   │   │   ├── tasks.py         /tasks CRUD + approve/reject
│   │   │   ├── checklist.py     /checklist/{id}
│   │   │   ├── comments.py      /tasks/{id}/comments
│   │   │   ├── attendance.py    /attendance start/end/me
│   │   │   ├── upload.py        /upload (multipart)
│   │   │   ├── locations.py     /locations + /companies
│   │   │   └── audit.py         /audit/logs (admin)
│   │   └── services/
│   │       ├── audit.py         Audit-log writer + action constants
│   │       ├── email.py         aiosmtplib SMTP sender
│   │       ├── notification.py  Notification facade
│   │       ├── file_storage.py  Upload save/validate/compress
│   │       └── scheduler.py     APScheduler jobs
│   ├── alembic/                 Migrations (versions/ starts empty)
│   ├── alembic.ini
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .dockerignore
├── nginx/
│   ├── nginx.conf               Worker config, gzip, logging
│   └── default.conf             Proxy /api, serve SPA, serve /storage/uploads
├── frontend-integration/
│   ├── api.ts                   Drop into React src/
│   └── FRONTEND_INTEGRATION.md  Worked examples mapping to hobb-app.tsx
├── scripts/
│   ├── setup.sh                 First-run bootstrap
│   ├── backup_db.sh             pg_dump + prune
│   ├── backup_uploads.sh        tar.gz + prune
│   └── restore_db.sh            pipe dump back in
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   └── BACKUP.md
├── storage/
│   └── uploads/                 Bind-mounted at /storage/uploads
├── docker-compose.yml
├── .env.example
└── README.md
```

## API surface (summary)

| Method | Path                            | Roles               | Purpose                                      |
| ------ | ------------------------------- | ------------------- | -------------------------------------------- |
| POST   | `/api/auth/login`               | public              | Email+password → JWT pair                    |
| POST   | `/api/auth/refresh`             | public              | Trade refresh token for a new access token   |
| GET    | `/api/auth/me`                  | any                 | Current user                                 |
| GET    | `/api/users`                    | any                 | List users (staff sees self only)            |
| POST   | `/api/users`                    | admin               | Create user                                  |
| PUT    | `/api/users/{id}`               | any (self) / admin  | Update user; only admin can change role      |
| DELETE | `/api/users/{id}`               | admin               | Delete user                                  |
| GET    | `/api/tasks`                    | any                 | List tasks (staff scoped to assigned_to=self)|
| POST   | `/api/tasks`                    | admin, supervisor   | Create task                                  |
| GET    | `/api/tasks/{id}`               | any (scoped)        | Read task (with checklist + comments)        |
| PUT    | `/api/tasks/{id}`               | any (scoped)        | Update task (staff field allow-list)         |
| DELETE | `/api/tasks/{id}`               | admin, supervisor   | Delete task                                  |
| POST   | `/api/tasks/{id}/approve`       | admin, supervisor   | Approve completed task                       |
| POST   | `/api/tasks/{id}/reject`        | admin, supervisor   | Reject with optional reason                  |
| PUT    | `/api/checklist/{id}`           | any (scoped)        | Toggle or edit a checklist item              |
| POST   | `/api/tasks/{id}/comments`      | any (scoped)        | Add comment                                  |
| POST   | `/api/attendance/start`         | any                 | Clock in                                     |
| POST   | `/api/attendance/end`           | any                 | Clock out                                    |
| GET    | `/api/attendance/me`            | any                 | My attendance history                        |
| POST   | `/api/upload`                   | any                 | Upload image (multipart)                     |
| GET    | `/api/locations`                | any                 | List locations                               |
| POST   | `/api/locations`                | admin, supervisor   | Create location                              |
| PUT    | `/api/locations/{id}`           | admin, supervisor   | Update location                              |
| DELETE | `/api/locations/{id}`           | admin               | Delete location                              |
| GET    | `/api/companies`                | any                 | List companies                               |
| POST   | `/api/companies`                | admin               | Create company                               |
| GET    | `/api/audit/logs`               | admin               | Read audit log                               |
| GET    | `/api/health`                   | public              | Liveness probe                               |
| GET    | `/api/docs`                     | public              | Swagger UI                                   |

## Next steps

1. Read **[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)** for the full
   install + Linux production walkthrough.
2. Read **[`frontend-integration/FRONTEND_INTEGRATION.md`](frontend-integration/FRONTEND_INTEGRATION.md)**
   for the exact edits to make in `hobb-app.tsx` — login, tasks, checklist
   toggle, image upload, comments, attendance.
3. Read **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** for how the
   pieces fit together and where to plug in WhatsApp / push later.
4. Read **[`docs/BACKUP.md`](docs/BACKUP.md)** for backup automation and
   the cron table you should install.


Private / unlicensed. Adjust to taste before distributing.
