"""Auskunft über den Zustand des Dienstes.

``/health`` ist knapp, weil Render es zum Aufwecken benutzt. ``/health/speicher``
beantwortet die eine Frage, die man von außen sonst nicht klären kann: Wo
liegen die hochgeladenen Fotos gerade, und übersteht das einen Neustart?
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import fotospeicher

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/speicher")
def speicher(db: Session = Depends(get_db)):
    """Wo die Fotos liegen und wie viel Platz sie belegen.

    Gebraucht beim Einrichten: Auf einem Server mit flüchtigem Dateisystem
    muss hier ``dauerhaft: true`` stehen — sonst sind über Nacht hochgeladene
    Fotos am Morgen verschwunden.
    """
    art = fotospeicher.art()
    belegt = fotospeicher.belegung_bytes(db)
    return {
        "art": art,
        "dauerhaft": art in ("db", "objekt"),
        "belegt_bytes": belegt,
        "belegt_mb": round(belegt / (1024 * 1024), 1),
        "erklaerung": fotospeicher.beschreibung(),
    }
