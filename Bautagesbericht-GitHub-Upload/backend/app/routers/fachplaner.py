"""Stammdaten der Fachplaner-Unternehmen — Aufbau wie ``routers.empfaenger``."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Fachplaner, McdonaldsAngebot
from app.schemas import FachplanerCreate, FachplanerResponse

router = APIRouter(prefix="/fachplaner", tags=["fachplaner"])


@router.get("", response_model=list[FachplanerResponse])
def list_fachplaner(db: Session = Depends(get_db)):
    """Alphabetisch — anders als bei den Empfängern.

    Diese Liste steht in einem Auswahlfeld, in dem man einen Namen sucht.
    Nach Anlagedatum sortiert wäre sie beim zwanzigsten Eintrag unbenutzbar.
    """
    return db.query(Fachplaner).order_by(Fachplaner.name).all()


@router.post("", response_model=FachplanerResponse, status_code=201)
def create_fachplaner(data: FachplanerCreate, db: Session = Depends(get_db)):
    planer = Fachplaner(
        name=data.name.strip(),
        ansprechpartner=data.ansprechpartner.strip(),
        email=str(data.email).strip(),
        adresse=data.adresse.strip(),
    )
    db.add(planer)
    db.commit()
    db.refresh(planer)
    return planer


@router.delete("/{fachplaner_id}", status_code=204)
def delete_fachplaner(fachplaner_id: int, db: Session = Depends(get_db)):
    """Löscht ein Fachplaner-Unternehmen.

    Hängen Angebote daran, wird abgelehnt — und zwar auch mit ``force``.
    Anders als bei den Empfängern (wo mitgelöscht werden kann) ist ein Angebot
    ein Schreiben nach außen: Der Nachweis, an wen es ging, darf nicht
    verschwinden, weil jemand die Stammdaten aufräumt. Wer das Unternehmen
    nicht mehr braucht, benennt es um.
    """
    planer = db.get(Fachplaner, fachplaner_id)
    if not planer:
        raise HTTPException(404, "Fachplaner nicht gefunden")

    anzahl = (
        db.query(McdonaldsAngebot)
        .filter(McdonaldsAngebot.fachplaner_id == fachplaner_id)
        .count()
    )
    if anzahl:
        raise HTTPException(
            409,
            detail={
                "grund": "angebote_vorhanden",
                "anzahl": anzahl,
                "nachricht": (
                    f"Zu „{planer.name}“ gehören {anzahl} Angebot(e). Der "
                    "Eintrag bleibt deshalb erhalten — sonst wäre nicht mehr "
                    "nachvollziehbar, an wen sie gingen."
                ),
            },
        )

    db.delete(planer)
    db.commit()
