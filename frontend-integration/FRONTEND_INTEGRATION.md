# Frontend Integration Guide

This guide shows how to wire the existing `hobb-app.tsx` React frontend into the
new backend **without rewriting the UI**. Every change is local — you swap the
in-memory seed data (`USERS_INIT`, `TASKS_INIT`) and hand-rolled handlers for
calls into `api.ts`.

---

## 1. Install

Drop `api.ts` into your frontend source tree — e.g. `src/api.ts`.

Point it at your backend. If the frontend and backend are served from the same
nginx origin (the default in `docker-compose.yml`), nothing is needed:
`api.ts` defaults to `/api`. For Vite dev with the backend on a different host,
set before the app mounts:

```ts
// main.tsx (Vite) or index.tsx (CRA)
(window as any).__HOBB_API_BASE__ = import.meta.env.VITE_API_BASE || "/api";
```

---

## 2. Model field mapping

The original UI uses camelCase; the API uses snake_case. Only these fields are
renamed on the way in/out:

| UI (old)          | API (new)             |
| ----------------- | --------------------- |
| `desc`            | `description`         |
| `dueDate`         | `due_date`            |
| `dueTime`         | `due_time`            |
| `assignedTo`      | `assigned_to`         |
| `location` (str)  | `location_name` (read-only) / `location_id` (write) |
| `imageProof`      | `image_proof_after`   |
| `createdAt`       | `created_at`          |
| `completedAt`     | `completed_at`        |
| `author`          | `author_id` (+ `author_name` on read) |
| `time` (comment)  | `timestamp`           |

Everything else (`id`, `title`, `priority`, `status`, `shift`, `recurrence`,
`checklist`, `done`, `text`) stays the same.

If you want a single normaliser so the rest of your UI code never changes:

```ts
import type { Task } from "./api";

export function toUiTask(t: Task) {
  return {
    id: t.id,
    title: t.title,
    desc: t.description ?? "",
    location: t.location_name ?? "",
    priority: t.priority,
    dueDate: t.due_date ?? "",
    dueTime: t.due_time?.slice(0, 5) ?? "",
    assignedTo: t.assigned_to ?? "",
    status: t.status,
    shift: t.shift,
    recurrence: t.recurrence,
    checklist: t.checklist.map(c => ({ id: c.id, text: c.text, done: c.done })),
    comments: t.comments.map(c => ({
      id: c.id,
      author: c.author_id,
      authorName: c.author_name,
      text: c.text,
      time: new Date(c.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    })),
    imageProof: t.image_proof_after,
    imageProofBefore: t.image_proof_before,
    createdAt: t.created_at,
    completedAt: t.completed_at,
  };
}
```

---

## 3. Worked examples

Line numbers below refer to the current `hobb-app.tsx`.

### 3.1 Login (replaces lines ~151–157 inside `Login.go`)

**Before:**

```tsx
const go=()=>{
  setBusy(true);setErr("");
  setTimeout(()=>{
    const u=USERS_INIT.find(u=>u.email===email&&u.password===pw);
    if(u) onLogin(u); else {setErr("Invalid email or password.");setBusy(false);}
  },500);
};
```

**After:**

```tsx
import { authApi } from "./api";

const go = async () => {
  setBusy(true); setErr("");
  try {
    const { user } = await authApi.login(email, pw);
    onLogin(user);
  } catch (e: any) {
    setErr(e.message || "Invalid email or password.");
  } finally {
    setBusy(false);
  }
};
```

### 3.2 Top-level state (replaces lines 1001–1002)

**Before:**

```tsx
const [users,setUsers]=useState(USERS_INIT);
const [tasks,setTasks]=useState(TASKS_INIT);
```

**After:**

```tsx
import { useEffect, useState } from "react";
import { tasksApi, usersApi, tokenStore, type Task, type User } from "./api";

const [users, setUsers] = useState<User[]>([]);
const [tasks, setTasks] = useState<Task[]>([]);
const [loading, setLoading] = useState(true);

// Refresh tasks - useful after mutations
const reloadTasks = async () => setTasks(await tasksApi.list());
const reloadUsers = async () => setUsers(await usersApi.list());

// Restore session + initial load
useEffect(() => {
  const cached = tokenStore.getUser();
  if (!cached) { setLoading(false); return; }
  (async () => {
    try {
      await Promise.all([reloadTasks(), reloadUsers()]);
    } finally { setLoading(false); }
  })();
}, []);
```

### 3.3 Toggle a checklist item

**Before (in-memory):**

```tsx
const toggle = (itemId: string) => setTasks(ts =>
  ts.map(t => t.id !== taskId ? t : {
    ...t,
    checklist: t.checklist.map(c => c.id === itemId ? { ...c, done: !c.done } : c),
  })
);
```

**After:**

```tsx
import { checklistApi } from "./api";

const toggle = async (itemId: string, currentDone: boolean) => {
  // Optimistic update
  setTasks(ts => ts.map(t => ({
    ...t,
    checklist: t.checklist.map(c =>
      c.id === itemId ? { ...c, done: !currentDone } : c),
  })));
  try {
    await checklistApi.toggle(itemId, !currentDone);
  } catch {
    // Revert on failure
    reloadTasks();
  }
};
```

### 3.4 Upload before/after image, then mark complete

```tsx
import { uploadApi, tasksApi } from "./api";

const submitProof = async (taskId: string, file: File) => {
  const { url } = await uploadApi.image(file, { task_id: taskId, kind: "after" });
  await tasksApi.update(taskId, {
    image_proof_after: url,
    status: "completed",
  });
  reloadTasks();
};
```

The image is already compressed & downsized by the backend, so no client-side
resizing is needed.

### 3.5 Admin approve / reject

```tsx
await tasksApi.approve(taskId);         // marks status = approved
await tasksApi.reject(taskId, "Rework the floor near the entrance");
```

### 3.6 Add a comment

```tsx
import { commentsApi } from "./api";

const comment = await commentsApi.add(taskId, "Started mopping!");
// Append locally or simply reloadTasks()
```

### 3.7 Attendance

```tsx
import { attendanceApi } from "./api";

await attendanceApi.start();        // clock in
await attendanceApi.end();          // clock out
const history = await attendanceApi.mine(30);
```

### 3.8 Displaying uploaded images

Uploads are served at `/storage/uploads/YYYY-MM-DD/<filename>.jpg`. Since the
`api.ts` default base is `/api` and uploads live on the same nginx origin, the
URL returned by the API is already correct for `<img src>`:

```tsx
{task.image_proof_after && <img src={task.image_proof_after} alt="proof" />}
```

If your frontend dev server runs on a different host, configure Vite's proxy:

```ts
// vite.config.ts
export default {
  server: {
    proxy: {
      "/api": "http://localhost",
      "/storage": "http://localhost",
    },
  },
};
```

---

## 4. Default credentials (seeded)

| Role        | Email                  | Password     |
| ----------- | ---------------------- | ------------ |
| admin       | admin@hobb.com         | admin123     |
| supervisor  | supervisor@hobb.com    | super123     |
| staff       | priya@hobb.com         | staff123     |
| staff       | rajan@hobb.com         | staff123     |
| staff       | meena@hobb.com         | staff123     |

**Change these before you put the system in front of real users.** Edit
`SEED_ADMIN_*` in `.env`, or rotate credentials via `PUT /api/users/{id}`.

---

## 5. Error handling quick reference

```ts
import { ApiError } from "./api";

try {
  await tasksApi.update(id, { status: "completed" });
} catch (e) {
  if (e instanceof ApiError) {
    if (e.status === 403) alert("You don't have permission to do that.");
    else if (e.status === 422) console.warn("Validation:", e.body.detail);
    else alert(e.message);
  }
}
```

`ApiError` is thrown for every non-2xx response; `.status` and `.body` let you
branch cleanly. On `401`, the client transparently attempts one refresh before
surfacing the error — you only see a 401 if the refresh token is gone/expired.
