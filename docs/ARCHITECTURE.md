# Architecture

```
                      ┌─────────────┐
                      │   Browser   │
                      └──────┬──────┘
                             │ HTTP (80) / HTTPS (443, via your cert)
                      ┌──────▼──────┐
                      │    nginx    │   ◄── serves built React SPA,
                      │  (reverse   │        rate-limits /api/auth/login,
                      │    proxy)   │        serves /storage/uploads directly
                      └──┬───────┬──┘
                         │       │
                   /api  │       │  /
                         │       └──► static SPA (index.html + assets)
                 ┌───────▼──────┐
                 │  FastAPI     │   ◄── uvicorn, 2 workers
                 │  (uvicorn)   │
                 │              │
                 │  routes/     │   ◄── auth, tasks, checklist, comments,
                 │  services/   │        attendance, upload, users, etc.
                 │  core/       │   ◄── config, security, deps, logging
                 │  APScheduler │   ◄── missed-task, recurring, reminders
                 └──┬────────┬──┘
                    │        │
                    │        └────► /storage/uploads  (bind mount / NAS)
                    ▼
               ┌──────────┐
               │ Postgres │   ◄── SQLAlchemy ORM + Alembic migrations
               └──────────┘
```

## Layer responsibilities

* **nginx** — TLS termination (your cert goes here), static SPA hosting,
  reverse proxy for `/api/*`, direct file serving for `/storage/uploads/*`,
  and edge rate-limiting on `/api/auth/login`.

* **FastAPI / uvicorn** — stateless HTTP service. Holds no session state
  beyond JWTs the client carries. Two uvicorn workers by default; scale
  with `--workers` or by running multiple replicas behind a load balancer.

* **APScheduler** — runs in-process on worker 0. Jobs:
  - `mark_missed_tasks` (every 5 min) — flips overdue tasks to `missed`.
  - `generate_recurring_tasks` (00:05 UTC) — clones daily/weekly/monthly
    templates into today's actionable list.
  - `send_due_reminders` (every minute) — emails assignees
    `REMINDER_LEAD_MINUTES` before `due_time`.

  For multi-replica deployments, move these to a single dedicated worker
  container or replace with Celery Beat + Redis.

* **Postgres 16** — primary datastore. Schema uses string UUIDs (12 chars)
  for all PKs; all FKs cascade or null on delete deliberately; compound
  indexes on `(company_id, status)` and `(due_date, status)` keep list
  endpoints fast.

* **Storage** — images written under `/storage/uploads/YYYY-MM-DD/`.
  The container mount `UPLOAD_VOLUME` is what you repoint at a NAS path
  (e.g. `/mnt/nas/hobb/uploads`) in production.

## Security posture

* **Passwords**: bcrypt via passlib, cost factor 12.
* **JWT**: HS256, 8-hour access tokens, 14-day refresh tokens. Tokens carry
  `sub` (user id), `role`, `email`, `type`, `iat`, `exp`.
* **RBAC**: three roles - admin / supervisor / staff. Enforced via
  `require_admin`, `require_admin_or_supervisor`, `require_any_role`
  dependencies. Staff can only see/modify tasks assigned to them, and
  can only set a narrow allow-list of fields via `PUT /tasks/{id}`.
* **Rate limiting**: slowapi (in-process, IP-keyed) + nginx
  `limit_req_zone` on `/api/auth/login` as a belt-and-braces edge limit.
* **Input validation**: Pydantic v2 across every request/response.
* **Audit log**: every sensitive action (logins, task state changes,
  approvals, uploads, CRUD) goes into `audit_logs` with user, IP, entity,
  and timestamp.

## Extensibility

The notification system is a single facade (`services/notification.py`).
Adding WhatsApp / push / SMS means one new module in `services/` and an
`await` at the call-site — no route changes needed.

The scheduler jobs are plain functions registered in
`services/scheduler.py`. Adding new periodic work is a one-line addition.
