# Ein-Container-Image: FastAPI-Backend UND Next.js-Frontend zusammen.
#
# Entscheidung Basis-Image: python:3.12-slim (Debian bookworm).
#   - Garantiert Python 3.12 (pyproject verlangt >=3.12). Ein Node-Basis-Image
#     mit nachinstalliertem Debian-Python läge bei 3.11 -> Versionskonflikt.
#   - Node 22 wird als Binärdatei aus dem offiziellen Node-Image übernommen
#     (COPY --from). Das ist robuster als ein Netz-Installskript zur Build-Zeit
#     und pinnt die Version. Beide Images sind bookworm-basiert (glibc passt).
#   - LibreOffice wird NUR beim vollen Umfang installiert (siehe ARG
#     APP_UMFANG weiter unten). Die Dokumente entstehen zwar mit python-docx,
#     also ohne Textprogramm — fuer die Umwandlung nach PDF braucht es aber
#     einen Umbruch-Algorithmus. Auf dem Buerorechner macht das Word; im
#     Linux-Container gibt es kein Word, dort springt LibreOffice ein (siehe
#     backend/app/services/word_pdf.py). Die Baufoto-Website kennt keine
#     PDF-Funktion und bleibt als einzige ohne LibreOffice: ~400 MB kleiner
#     und deutlich schneller gebaut.
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

# --- Umfang der Weboberfläche (Bauzeit-Schalter) ---
#
# "fotos"  = Baustellen-Website: Dashboard, Baufotos, Stammdaten · Projekte.
# "buero"  = Büro-Website: alle Bereiche AUSSER Baufotos — dafür gibt es die
#            Baustellen-Website, und beide teilen dieselbe Datenbank.
# "voll"   = Windows-Paket: alles. Es ist der Notweg ohne Netz und darf
#            deshalb nicht weniger können als die Websites.
#
# Steht hier oben, weil schon der naechste Schritt davon abhaengt. Render
# reicht die Umgebungsvariablen eines Dienstes automatisch als Build-Argument
# durch — der Buero-Dienst setzt in render.yaml also APP_UMFANG=buero,
# ohne dass diese Datei angefasst werden muss. Ohne Angabe gilt "fotos": die
# Website hat damit nie versehentlich den vollen Umfang.
ARG APP_UMFANG=fotos

# --- LibreOffice: überall außer bei der Baufoto-Website (PDF-Ausgabe) ---
#
# "-nogui" spart die Oberflaechen-Abhaengigkeiten; existiert das Paket in der
# Distribution nicht, wird auf das normale libreoffice-writer zurueckgefallen.
# fonts-liberation ist kein Beiwerk: Die Vorlagen sind in Arial gesetzt, und
# Liberation Sans ist der masshaltige Ersatz dafuer — ohne dieses Paket
# verschieben sich Umbrueche und Seitenzahlen gegenueber dem Word-PDF.
#
# Der Prueflauf am Ende ist Absicht und bewusst eine echte Umwandlung, nicht
# nur ein "--version": Er beweist, dass Programmdatei, Suchpfad, Schriften und
# Benutzerprofil zusammenspielen. Scheitert das, soll der BUILD scheitern —
# nicht erst der erste PDF-Versuch eines Kollegen Wochen spaeter.
RUN if [ "$APP_UMFANG" != "fotos" ]; then \
      apt-get update \
   && ( apt-get install -y --no-install-recommends libreoffice-writer-nogui fonts-liberation \
     || apt-get install -y --no-install-recommends libreoffice-writer      fonts-liberation ) \
   && rm -rf /var/lib/apt/lists/* \
   && ( command -v soffice >/dev/null 2>&1 \
     || ln -s /usr/lib/libreoffice/program/soffice /usr/bin/soffice ) \
   && printf 'Probeumwandlung\n' > /tmp/probe.txt \
   && soffice --headless --norestore --convert-to pdf --outdir /tmp /tmp/probe.txt \
   && test -s /tmp/probe.pdf \
   && head -c 5 /tmp/probe.pdf | grep -q '%PDF-' \
   && rm -f /tmp/probe.txt /tmp/probe.pdf \
   && echo "LibreOffice einsatzbereit: $(soffice --headless --version | head -1)" ; \
    else \
      echo "APP_UMFANG=$APP_UMFANG - keine PDF-Ausgabe, LibreOffice uebersprungen." ; \
    fi

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

# --- Umfang ins Frontend durchreichen ---
#
# Der Wert wird beim Bauen ins JavaScript-Buendel eingesetzt (siehe
# frontend/src/lib/umfang.ts) und MUSS deshalb vor "npm run build" stehen;
# eine Umgebungsvariable am laufenden Dienst kaeme zu spaet. Die Begruendung
# und die moeglichen Werte stehen oben beim ARG.
ENV APP_UMFANG=${APP_UMFANG}

# Den Wert, mit dem WIRKLICH gebaut wurde, ins Image schreiben.
#
# Warum das noetig ist: Render reicht Umgebungsvariablen zwar als
# Build-Argument durch, aendert man sie aber spaeter allein am Dienst,
# wird nur neu GESTARTET und nicht neu GEBAUT. Der Server meldet dann den
# neuen Wert, waehrend im JavaScript-Buendel noch der alte steckt — die
# Oberflaeche zeigt also etwas anderes, als die Auskunft behauptet. Genau
# darauf bin ich am 08.09.2026 hereingefallen. Diese Datei kann sich nicht
# nachtraeglich aendern; /api/health/dokumente liest sie und meldet eine
# Abweichung ausdruecklich.
RUN printf %s "$APP_UMFANG" > /app/umfang-beim-bauen.txt

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
