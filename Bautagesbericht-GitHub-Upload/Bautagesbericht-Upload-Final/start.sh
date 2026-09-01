#!/usr/bin/env bash
# Startet Backend (FastAPI/uvicorn) und Frontend (Next.js) in EINEM Container.
# - Backend: nur containerintern auf 127.0.0.1:8000
# - Frontend: nach außen auf $PORT (von Render vorgegeben)
# next.config.ts proxyt /api/* serverseitig an BACKEND_URL (=127.0.0.1:8000),
# daher kein CORS und nur eine öffentliche URL nötig.
set -uo pipefail

# 1) FastAPI-Backend, nur intern erreichbar.
#    PYTHONPATH statt Projekt-Installation -> "import app.main" findet den Code.
cd /app/backend
PYTHONPATH=/app/backend .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# 2) Next.js-Frontend nach außen auf dem von Render vorgegebenen Port.
cd /app/frontend
node_modules/.bin/next start --hostname 0.0.0.0 --port "${PORT:-10000}" &
FRONTEND_PID=$!

# Sobald einer der beiden Prozesse endet, den Container beenden, damit Render
# ihn sauber neu startet (statt mit einem toten Teil weiterzulaufen).
wait -n "$BACKEND_PID" "$FRONTEND_PID"
EXIT=$?
echo "Ein Prozess endete (Code $EXIT) — Container faehrt herunter."
kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
exit "$EXIT"
