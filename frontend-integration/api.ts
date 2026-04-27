/**
 * HOBB API client
 * ----------------
 * Drop this file into your frontend project (e.g. `src/api.ts`) and replace
 * your in-memory USERS_INIT / TASKS_INIT calls with these helpers.
 *
 * Token handling is done here via localStorage. 401 responses automatically
 * try to refresh once before giving up.
 *
 * See FRONTEND_INTEGRATION.md for worked examples matching the existing
 * hobb-app.tsx component structure.
 */

const API_BASE: string =
  (typeof window !== "undefined" &&
    (window as any).__HOBB_API_BASE__) ||
  "/api";

const TOKEN_KEY = "hobb_access_token";
const REFRESH_KEY = "hobb_refresh_token";
const USER_KEY = "hobb_user";

// ─────────────────────────────────────────────────────────────────────────
// Types (mirror backend Pydantic schemas)
// ─────────────────────────────────────────────────────────────────────────
export type Role = "admin" | "supervisor" | "staff";

export type TaskStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "missed"
  | "approved"
  | "rejected";

export type Priority = "low" | "medium" | "high";
export type Shift = "morning" | "afternoon" | "evening" | "night";
export type Recurrence = "none" | "daily" | "weekly" | "monthly";

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  avatar?: string | null;
  is_active: boolean;
  company_id?: string | null;
  created_at: string;
}

export interface ChecklistItem {
  id: string;
  task_id: string;
  text: string;
  done: boolean;
  created_at: string;
}

export interface Comment {
  id: string;
  task_id: string;
  author_id: string;
  author_name?: string | null;
  text: string;
  timestamp: string;
}

export interface Task {
  id: string;
  title: string;
  description?: string | null;
  location_id?: string | null;
  location_name?: string | null;
  company_id?: string | null;
  priority: Priority;
  due_date?: string | null;         // "YYYY-MM-DD"
  due_time?: string | null;         // "HH:MM:SS"
  assigned_to?: string | null;
  assignee_name?: string | null;
  status: TaskStatus;
  shift: Shift;
  recurrence: Recurrence;
  image_proof_before?: string | null;
  image_proof_after?: string | null;
  created_at: string;
  completed_at?: string | null;
  approved_at?: string | null;
  approved_by?: string | null;
  rejection_reason?: string | null;
  checklist: ChecklistItem[];
  comments: Comment[];
}

export interface Location {
  id: string;
  name: string;
  company_id?: string | null;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

// ─────────────────────────────────────────────────────────────────────────
// Token helpers
// ─────────────────────────────────────────────────────────────────────────
export const tokenStore = {
  getAccess: (): string | null => localStorage.getItem(TOKEN_KEY),
  getRefresh: (): string | null => localStorage.getItem(REFRESH_KEY),
  getUser: (): User | null => {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  },
  set: (t: LoginResponse): void => {
    localStorage.setItem(TOKEN_KEY, t.access_token);
    localStorage.setItem(REFRESH_KEY, t.refresh_token);
    localStorage.setItem(USER_KEY, JSON.stringify(t.user));
  },
  clear: (): void => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
  },
};

// ─────────────────────────────────────────────────────────────────────────
// Core fetch wrapper with auto-refresh on 401
// ─────────────────────────────────────────────────────────────────────────
export class ApiError extends Error {
  status: number;
  body: any;
  constructor(status: number, body: any, message: string) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  isRetry = false,
): Promise<T> {
  const token = tokenStore.getAccess();
  const headers = new Headers(init.headers || {});
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (res.status === 401 && !isRetry && tokenStore.getRefresh()) {
    const ok = await tryRefresh();
    if (ok) return request<T>(path, init, true);
    tokenStore.clear();
    throw new ApiError(401, null, "Unauthorized");
  }

  if (!res.ok) {
    let body: any = null;
    try { body = await res.json(); } catch { /* non-JSON */ }
    const msg =
      (body && (body.detail || body.message)) ||
      res.statusText ||
      `HTTP ${res.status}`;
    throw new ApiError(res.status, body, typeof msg === "string" ? msg : JSON.stringify(msg));
  }

  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}

async function tryRefresh(): Promise<boolean> {
  const refresh_token = tokenStore.getRefresh();
  if (!refresh_token) return false;
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token }),
    });
    if (!res.ok) return false;
    const data = (await res.json()) as LoginResponse;
    tokenStore.set(data);
    return true;
  } catch {
    return false;
  }
}

// ─────────────────────────────────────────────────────────────────────────
// Auth
// ─────────────────────────────────────────────────────────────────────────
export const authApi = {
  async login(email: string, password: string): Promise<LoginResponse> {
    const data = await request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    tokenStore.set(data);
    return data;
  },

  me(): Promise<User> {
    return request<User>("/auth/me");
  },

  logout(): void {
    tokenStore.clear();
  },
};

// ─────────────────────────────────────────────────────────────────────────
// Users
// ─────────────────────────────────────────────────────────────────────────
export const usersApi = {
  list: () => request<User[]>("/users"),
  get: (id: string) => request<User>(`/users/${id}`),
  create: (payload: {
    name: string;
    email: string;
    password: string;
    role: Role;
    avatar?: string;
    company_id?: string;
  }) =>
    request<User>("/users", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  update: (id: string, payload: Partial<User> & { password?: string }) =>
    request<User>(`/users/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  delete: (id: string) => request<void>(`/users/${id}`, { method: "DELETE" }),
};

// ─────────────────────────────────────────────────────────────────────────
// Tasks
// ─────────────────────────────────────────────────────────────────────────
export const tasksApi = {
  list: (params: {
    status?: TaskStatus;
    assigned_to?: string;
    due_date?: string;
  } = {}) => {
    const q = new URLSearchParams();
    // Backend uses `status_` to avoid shadowing the reserved word in Python.
    if (params.status) q.set("status_", params.status);
    if (params.assigned_to) q.set("assigned_to", params.assigned_to);
    if (params.due_date) q.set("due_date", params.due_date);
    const suffix = q.toString() ? `?${q}` : "";
    return request<Task[]>(`/tasks${suffix}`);
  },

  get: (id: string) => request<Task>(`/tasks/${id}`),

  create: (payload: {
    title: string;
    description?: string;
    location_id?: string;
    priority?: Priority;
    due_date?: string;
    due_time?: string;
    assigned_to?: string;
    shift?: Shift;
    recurrence?: Recurrence;
    checklist?: { text: string; done?: boolean }[];
  }) =>
    request<Task>("/tasks", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  update: (id: string, payload: Partial<{
    title: string;
    description: string;
    location_id: string;
    priority: Priority;
    due_date: string;
    due_time: string;
    assigned_to: string;
    status: TaskStatus;
    shift: Shift;
    recurrence: Recurrence;
    image_proof_before: string;
    image_proof_after: string;
  }>) =>
    request<Task>(`/tasks/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  delete: (id: string) => request<void>(`/tasks/${id}`, { method: "DELETE" }),

  approve: (id: string) =>
    request<Task>(`/tasks/${id}/approve`, { method: "POST", body: "{}" }),

  reject: (id: string, reason?: string) =>
    request<Task>(`/tasks/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  // Convenience wrappers
  markComplete: (id: string) =>
    request<Task>(`/tasks/${id}`, {
      method: "PUT",
      body: JSON.stringify({ status: "completed" }),
    }),
  markInProgress: (id: string) =>
    request<Task>(`/tasks/${id}`, {
      method: "PUT",
      body: JSON.stringify({ status: "in_progress" }),
    }),
};

// ─────────────────────────────────────────────────────────────────────────
// Checklist
// ─────────────────────────────────────────────────────────────────────────
export const checklistApi = {
  update: (id: string, payload: { text?: string; done?: boolean }) =>
    request<ChecklistItem>(`/checklist/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  toggle: (id: string, done: boolean) =>
    request<ChecklistItem>(`/checklist/${id}`, {
      method: "PUT",
      body: JSON.stringify({ done }),
    }),
};

// ─────────────────────────────────────────────────────────────────────────
// Comments
// ─────────────────────────────────────────────────────────────────────────
export const commentsApi = {
  add: (taskId: string, text: string) =>
    request<Comment>(`/tasks/${taskId}/comments`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
};

// ─────────────────────────────────────────────────────────────────────────
// Attendance
// ─────────────────────────────────────────────────────────────────────────
export interface AttendanceRecord {
  id: string;
  user_id: string;
  date: string;
  start_time?: string | null;
  end_time?: string | null;
  notes?: string | null;
}

export const attendanceApi = {
  start: (notes?: string) =>
    request<AttendanceRecord>("/attendance/start", {
      method: "POST",
      body: JSON.stringify({ notes }),
    }),
  end: (notes?: string) =>
    request<AttendanceRecord>("/attendance/end", {
      method: "POST",
      body: JSON.stringify({ notes }),
    }),
  mine: (limit = 30) =>
    request<AttendanceRecord[]>(`/attendance/me?limit=${limit}`),
};

// ─────────────────────────────────────────────────────────────────────────
// Upload
// ─────────────────────────────────────────────────────────────────────────
export interface UploadResult {
  url: string;
  filename: string;
  size_bytes: number;
  content_type: string;
}

export const uploadApi = {
  async image(
    file: File,
    opts: { task_id?: string; kind?: "before" | "after" | "general" } = {},
  ): Promise<UploadResult> {
    const form = new FormData();
    form.append("file", file);
    if (opts.task_id) form.append("task_id", opts.task_id);
    if (opts.kind) form.append("kind", opts.kind);
    return request<UploadResult>("/upload", { method: "POST", body: form });
  },
};

// ─────────────────────────────────────────────────────────────────────────
// Locations
// ─────────────────────────────────────────────────────────────────────────
export const locationsApi = {
  list: () => request<Location[]>("/locations"),
  create: (name: string, company_id?: string) =>
    request<Location>("/locations", {
      method: "POST",
      body: JSON.stringify({ name, company_id }),
    }),
  update: (id: string, payload: { name?: string; company_id?: string }) =>
    request<Location>(`/locations/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  delete: (id: string) =>
    request<void>(`/locations/${id}`, { method: "DELETE" }),
};

// Default aggregate export for convenience
export default {
  auth: authApi,
  users: usersApi,
  tasks: tasksApi,
  checklist: checklistApi,
  comments: commentsApi,
  attendance: attendanceApi,
  upload: uploadApi,
  locations: locationsApi,
  tokenStore,
};
