# Ein-Container-Image: FastAPI-Backend UND Next.js-Frontend zusammen.
#
# Entscheidung Basis-Image: python:3.12-slim (Debian bookworm).
#   - Garantiert Python 3.12 (pyproject verlangt >=3.12). Ein Node-Basis-Image
#     mit nachinstalliertem Debian-Python läge bei 3.11 -> Versionskonflikt.
#   - Node 22 wird als Binärdatei aus dem offiziellen Node-Image übernommen
#     (COPY --from). Das ist robuster als ein Netz-Installskript zur Build-Zeit
#     und pinnt die Version. Beide Images sind bookworm-basiert (glibc passt).
#   - LibreOffice wird NICHT installiert: Der Code nutzt es nirgends (reine
#     python-docx-Erzeugung) — das spart ~400 MB und beschleunigt den Build.
#
# Laufzeit: start.sh startet uvicorn intern auf 127.0.0.1:8000 und next start
# nach außen auf $PORT. next.config.ts proxyt /api/* an BACKEND_URL (=8000),
# daher kein CORS und nur eine öffentliche URL.

FROM python:3.12-slim

# --- Node 22 aus dem offiziellen Node-Image übernehmen ---
COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# --- uv (Python-Paketmanager, spiegelt lokales Setup) ---
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && curl -LsSf https://astral.sh/uv/install.sh | sh \
 && ln -s /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app

# --- Backend-Abhängigkeiten zuerst (Docker-Layer-Cache) ---
# --no-install-project: nur Abhängigkeiten in backend/.venv, das Paket selbst
# wird nicht gebaut (zur Laufzeit reicht PYTHONPATH, siehe start.sh).
COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN cd backend && (uv sync --no-dev --frozen --no-install-project 2>/dev/null || uv sync --no-dev --no-install-project)

# --- Frontend-Abhängigkeiten zuerst (Docker-Layer-Cache) ---
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

# --- Restlicher Quellcode ---
COPY backend ./backend
COPY frontend ./frontend

# --- Frontend bauen, danach Dev-Abhängigkeiten entfernen (kleineres Image) ---
RUN cd frontend && npm run build && npm prune --omit=dev

# --- Startskript ---
COPY start.sh ./start.sh
RUN chmod +x ./start.sh

# Backend-Adresse für den Next.js-Proxy (beide Prozesse im selben Container).
ENV BACKEND_URL=http://127.0.0.1:8000
ENV PYTHONUNBUFFERED=1

# Render gibt $PORT vor; lokal ist 10000 der Fallback.
EXPOSE 10000

CMD ["./start.sh"]
