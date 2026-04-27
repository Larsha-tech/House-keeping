#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────
# First-time setup: copy .env.example -> .env, generate a JWT secret,
# build images, start the stack.
#
# Usage:  ./scripts/setup.sh
# ────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "[setup] creating .env from .env.example"
  cp .env.example .env

  if command -v openssl >/dev/null 2>&1; then
    SECRET="$(openssl rand -hex 48)"
    # macOS / BSD sed vs GNU sed
    if sed --version >/dev/null 2>&1; then
      sed -i "s|^JWT_SECRET=.*$|JWT_SECRET=${SECRET}|" .env
    else
      sed -i '' "s|^JWT_SECRET=.*$|JWT_SECRET=${SECRET}|" .env
    fi
    echo "[setup] generated JWT_SECRET"
  else
    echo "[setup] openssl not found - please set JWT_SECRET in .env manually"
  fi
else
  echo "[setup] .env already present - leaving untouched"
fi

echo "[setup] building images"
docker compose build

echo "[setup] starting stack"
docker compose up -d

echo
echo "[setup] waiting for backend to be ready..."
for i in {1..30}; do
  if curl -fsS http://localhost/api/health >/dev/null 2>&1; then
    echo "[setup] backend is up!"
    break
  fi
  sleep 2
done

echo
echo "─────────────────────────────────────────────────────────"
echo " HOBB is running."
echo "   API docs:   http://localhost/api/docs"
echo "   Health:     http://localhost/api/health"
echo "   Default login: admin@hobb.com / admin123"
echo "─────────────────────────────────────────────────────────"
