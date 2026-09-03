from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import (
    anmeldung,
    baufotos,
    besprechungsprotokolle,
    einreichungen,
    empfaenger,
    gewerke,
    health,
    maengel,
    maengelanzeige,
    mangel_stammdaten,
    plaene,
    projekte,
    projektberichte,
)
from app.security import pruefe_seitenpasswort


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(
    title="Bautagesbericht API",
    version="0.1.0",
    lifespan=lifespan,
    # Gilt für jede Route — auch für neue, die später dazukommen. Ohne
    # gesetztes BTB_SEITEN_PASSWORT lässt die Prüfung alles durch; die
    # Ausnahmen (Gesundheitscheck, Abholung) stehen in app.security.
    dependencies=[Depends(pruefe_seitenpasswort)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(anmeldung.router, prefix="/api")
app.include_router(projekte.router, prefix="/api")
app.include_router(empfaenger.router, prefix="/api")
app.include_router(einreichungen.router, prefix="/api")

# Mängelmanagement
app.include_router(mangel_stammdaten.router, prefix="/api")
app.include_router(gewerke.router, prefix="/api")
app.include_router(plaene.router, prefix="/api")
app.include_router(projektberichte.router, prefix="/api")
app.include_router(maengel.router, prefix="/api")
app.include_router(maengelanzeige.router, prefix="/api")

# Baubesprechungsprotokolle
app.include_router(besprechungsprotokolle.router, prefix="/api")

# Baufotos
app.include_router(baufotos.router, prefix="/api")


# ─────────────────────────────────────────────────────────────────────────────
# Oberfläche mit ausliefern (nur im Windows-Paket)
#
# Auf Render liefert Next.js die Oberfläche aus und leitet /api hierher weiter;
# dort gibt es kein statisches Verzeichnis und dieser Block tut nichts.
#
# Im Windows-Paket ist es umgekehrt: Die Oberfläche wurde statisch exportiert
# (``NEXT_EXPORT=1 npm run build``, siehe frontend/next.config.ts) und wird von
# diesem Prozess mitgeliefert. Genau deshalb braucht das Paket auf dem
# Bürorechner kein Node.js — es ist ein Prozess statt zwei.
#
# Die Einbindung steht bewusst NACH allen /api-Routern: Sonst würde die
# Dateiauslieferung die Schnittstelle verdecken.
# ─────────────────────────────────────────────────────────────────────────────

_oberflaeche = settings.static_dir
if _oberflaeche is not None and _oberflaeche.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(_oberflaeche), html=True),
        name="oberflaeche",
    )
