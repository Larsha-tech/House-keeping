# Backup & Maintenance

Two things need protecting: the **Postgres database** and the **uploads
directory**. Helpers are in `scripts/`.

## 1. Database

### Manual dump

```bash
./scripts/backup_db.sh /var/backups/hobb
# -> /var/backups/hobb/hobb_db_20260425_020000.sql.gz
```

The script shells into the `hobb-db` container, pipes `pg_dump` through
`gzip -9`, and automatically prunes backups older than `HOBB_BACKUP_KEEP_DAYS`
(default 14).

### Restore

```bash
./scripts/restore_db.sh /var/backups/hobb/hobb_db_20260425_020000.sql.gz
```

Warns before overwriting. If the app is running it can stay up, but expect
a brief window of inconsistency - safest to `docker compose stop backend`
first and restart after.

### Point-in-time backups (heavy-traffic deployments)

For RPO < 1 day, enable WAL archiving. Easiest path: replace the
`postgres:16-alpine` image with a managed Postgres (RDS, Cloud SQL,
Supabase) that does this out of the box.

---

## 2. Uploads

### Manual archive

```bash
./scripts/backup_uploads.sh /var/backups/hobb
# -> /var/backups/hobb/hobb_uploads_20260425_023000.tar.gz
```

### Restore

```bash
cd /
tar -xzf /var/backups/hobb/hobb_uploads_20260425_023000.tar.gz \
    -C "$(dirname "$UPLOAD_VOLUME")"
```

If uploads live on a NAS, you may already have snapshot-based backups at
the storage layer (Synology/TrueNAS/etc.) - then these archives are just
an extra safety net.

---

## 3. Suggested cron schedule

```cron
# /etc/cron.d/hobb
# Daily DB dump at 02:00, uploads archive at 02:30
0  2 * * *  root  cd /opt/hobb && ./scripts/backup_db.sh      /var/backups/hobb >> /var/log/hobb-backup.log 2>&1
30 2 * * *  root  cd /opt/hobb && ./scripts/backup_uploads.sh /var/backups/hobb >> /var/log/hobb-backup.log 2>&1

# Optional: weekly offsite sync (adjust for your remote)
0  3 * * 0  root  rsync -az /var/backups/hobb/ backup-user@offsite.example.com:/srv/hobb-backups/
```

Don't forget: **test your restore path** at least once per quarter. A
backup you've never restored is a hope, not a backup.

---

## 4. Log rotation

Uvicorn logs go to container stdout, captured by Docker. Keep them bounded:

```yaml
# docker-compose.yml - add per-service:
services:
  backend:
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"
```

On the host, also set `/etc/docker/daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "50m", "max-file": "5" }
}
```

---

## 5. Routine maintenance tasks

| Task                          | Cadence   | Command                                                  |
| ----------------------------- | --------- | -------------------------------------------------------- |
| Pull latest base images       | Monthly   | `docker compose pull && docker compose up -d`            |
| Apply OS security updates     | Weekly    | `sudo unattended-upgrade -d` (host)                      |
| Verify last DB backup exists  | Daily     | Monitoring / alerting on `/var/backups/hobb` mtime       |
| Run Alembic migrations        | On deploy | `docker compose exec backend alembic upgrade head`       |
| Vacuum + analyze Postgres     | Weekly    | `docker compose exec db vacuumdb -U hobb -a -z`          |
| Rotate JWT secret             | Quarterly | Edit `.env`, `docker compose restart backend` (forces all users to re-login) |
| Audit admin users             | Quarterly | Review `GET /api/users?role=admin` + `audit_logs` table  |

---

## 6. Monitoring hooks

Minimum health check (what nginx / your uptime probe should hit):

```
GET http://your-host/api/health
→ 200 {"status":"ok","version":"1.0.0"}
```

For richer monitoring, scrape the Docker stats API or add
`prometheus-fastapi-instrumentator` to `requirements.txt` and expose
`/metrics`. Past that, send uvicorn JSON logs (`LOG_JSON=true` in `.env`)
to Loki / Elasticsearch.
