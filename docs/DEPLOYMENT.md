# Deployment Guide

This guide covers two scenarios:

1. **Quickstart on Docker Desktop** (your immediate goal).
2. **Production deployment on a Linux server** (when you move off your laptop).

---

## 1. Docker Desktop quickstart

Prerequisites: Docker Desktop with Compose V2 (ships by default in recent
versions). Tested on Windows, macOS, and Linux hosts.

### 1.1 Unzip & cd into the project

```bash
unzip hobb.zip
cd hobb
```

### 1.2 One-liner setup (recommended)

From the project root:

```bash
bash scripts/setup.sh
```

The script copies `.env.example` → `.env`, generates a strong `JWT_SECRET`
with `openssl`, builds images, and starts the stack.

### 1.3 Manual setup (if you prefer)

```bash
cp .env.example .env
# edit .env: at minimum set a real JWT_SECRET and POSTGRES_PASSWORD
docker compose build
docker compose up -d
```

### 1.4 Verify

```bash
curl http://localhost/api/health
# → {"status":"ok","version":"1.0.0"}
```

Open http://localhost/api/docs — you should see the interactive Swagger UI.
Log in with the seeded admin:

- email: `admin@hobb.com`
- password: `admin123`

### 1.5 Deploy the frontend

The stack bind-mounts `./frontend-build` into nginx. Two paths:

**A — Build from your existing React project:**

```bash
# From your React project directory (the one with hobb-app.tsx):
npm install
npm run build     # or: vite build
# Copy the dist into the hobb stack:
cp -r dist/* /path/to/hobb/frontend-build/
```

Wire the API client in first — see `frontend-integration/FRONTEND_INTEGRATION.md`.

**B — Serve only the API (headless):** leave `frontend-build/` empty;
nginx's `/` will 404 but `/api/*` works fine. Useful if you serve the
React app from Vercel/Netlify/etc.

### 1.6 Common commands

```bash
docker compose logs -f backend        # tail backend logs
docker compose logs -f nginx          # tail nginx logs
docker compose restart backend        # hot-restart after code change
docker compose exec backend bash      # shell inside backend
docker compose exec db psql -U hobb   # psql into the database
docker compose down                   # stop stack (keeps volumes)
docker compose down -v                # stop + wipe DB volume (destroys data)
```

### 1.7 Generate a real Alembic baseline

The container auto-creates tables via `Base.metadata.create_all()` so you
can start immediately. Before your first production schema change, capture
the current state as an Alembic migration:

```bash
docker compose exec backend alembic revision --autogenerate -m "initial"
docker compose exec backend alembic upgrade head
```

From then on, bump the schema via Alembic only.

---

## 2. Production deployment (Linux server)

### 2.1 Prepare the host

```bash
# Ubuntu 22.04+ / Debian 12+
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER
# log out/in, or `newgrp docker`
```

### 2.2 Clone / upload the project

```bash
sudo mkdir -p /opt/hobb && sudo chown $USER /opt/hobb
cd /opt/hobb
# unzip or git clone here
```

### 2.3 Configure `.env`

Copy the template and set real values:

```bash
cp .env.example .env
vi .env
```

**Must change in production:**

| Key                  | Why                                     |
| -------------------- | --------------------------------------- |
| `JWT_SECRET`         | Token signing key - rotate on breach    |
| `POSTGRES_PASSWORD`  | Database auth                            |
| `SEED_ADMIN_PASSWORD`| First-login admin credentials            |
| `CORS_ORIGINS`       | Whitelist your real frontend domain(s)   |
| `SMTP_*`             | Needed for real email notifications      |
| `UPLOAD_VOLUME`      | Point at the NAS mount, e.g. `/mnt/nas/hobb/uploads` |

Generate a strong JWT secret:

```bash
openssl rand -hex 48
```

### 2.4 NAS mount for uploads

If uploads live on a NAS (NFS/SMB), mount it *before* `docker compose up`:

```bash
# /etc/fstab example for NFS:
# 192.168.1.10:/volume1/hobb   /mnt/nas/hobb   nfs   defaults,_netdev   0 0
sudo mkdir -p /mnt/nas/hobb/uploads
sudo mount -a
```

Then in `.env`:

```env
UPLOAD_VOLUME=/mnt/nas/hobb/uploads
```

### 2.5 HTTPS

The included nginx config listens on HTTP only. For TLS, either:

**A — Terminate TLS at an upstream load balancer / Cloudflare / Caddy.**
Keep this stack on port 80 on a private interface.

**B — Add certbot inside this nginx.** Append to `nginx/default.conf`:

```nginx
server {
    listen 443 ssl http2;
    server_name hobb.example.com;

    ssl_certificate     /etc/letsencrypt/live/hobb.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/hobb.example.com/privkey.pem;

    # ... copy everything from the :80 server block here ...
}

server {
    listen 80;
    server_name hobb.example.com;
    return 301 https://$host$request_uri;
}
```

Mount `/etc/letsencrypt` into the nginx container and run `certbot` on the
host (or use the official certbot image).

### 2.6 Start & verify

```bash
docker compose pull           # only effective for base images
docker compose build
docker compose up -d
curl -fsS http://localhost/api/health
```

### 2.7 Systemd unit (auto-start on boot)

Docker Compose V2 starts containers with their per-container restart
policy (`unless-stopped`), so you normally don't need extra systemd. If
you want the stack itself managed by systemd:

```ini
# /etc/systemd/system/hobb.service
[Unit]
Description=HOBB Docker Compose stack
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/hobb
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hobb.service
```

### 2.8 Scaling beyond one host

Two knobs:

1. **Scale uvicorn workers** — raise `--workers` in `backend/Dockerfile`
   (rule of thumb: `2 × CPU + 1`).
2. **Scale containers** — `docker compose up -d --scale backend=4` and
   add `backend:8000` entries to `nginx/default.conf` `upstream`.

At that point, move the scheduler out of the backend (run a dedicated
`backend-worker` service with `SCHEDULER_ENABLED=true`; set `false` on the
others) so jobs don't fire N times per tick.

---

## 3. Upgrading

```bash
cd /opt/hobb
git pull                              # or unzip a new release
docker compose build --no-cache backend
docker compose up -d backend          # rolling restart (nginx & db untouched)
docker compose exec backend alembic upgrade head
```

---

## 4. Rolling back

```bash
git checkout <previous-tag>
docker compose build backend
docker compose up -d backend
docker compose exec backend alembic downgrade <rev>
```

If data is compromised, restore from the latest DB dump (see
`BACKUP.md`).
