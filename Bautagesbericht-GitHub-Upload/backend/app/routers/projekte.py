from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Projekt
from app.schemas import ProjektCreate, ProjektResponse
from app.services.cleanup import count_einreichungen_for, delete_einreichungen_for
from app.services.geocoding import geocode_address

router = APIRouter(prefix="/projekte", tags=["projekte"])


@router.get("", response_model=list[ProjektResponse])
def list_projekte(db: Session = Depends(get_db)):
    return db.query(Projekt).order_by(Projekt.erstellt_am.desc()).all()


@router.post("", response_model=ProjektResponse, status_code=201)
async def create_projekt(data: ProjektCreate, db: Session = Depends(get_db)):
    lat, lon = await geocode_address(data.adresse)
    projekt = Projekt(name=data.name, adresse=data.adresse, lat=lat, lon=lon)
    db.add(projekt)
    db.commit()
    db.refresh(projekt)
    return projekt


@router.delete("/{projekt_id}", status_code=204)
def delete_projekt(projekt_id: int, force: bool = False, db: Session = Depends(get_db)):
    """Löscht ein Projekt.

    Hängen noch Einreichungen daran, wird ohne ``force=true`` mit 409 abgelehnt
    und die Anzahl gemeldet — so kann die Oberfläche nachfragen, bevor
    Berichtshistorie mitgelöscht wird.
    """
    projekt = db.get(Projekt, projekt_id)
    if not projekt:
        raise HTTPException(404, "Projekt nicht gefunden")

    anzahl = count_einreichungen_for(db, projekt_id=projekt_id)
    if anzahl and not force:
        raise HTTPException(
            409,
            detail={
                "grund": "einreichungen_vorhanden",
                "anzahl_einreichungen": anzahl,
                "nachricht": (
                    f"Zu diesem Projekt gehören noch {anzahl} Einreichung(en). "
                    "Beim Löschen werden sie mit entfernt."
                ),
            },
        )

    if anzahl:
        delete_einreichungen_for(db, projekt_id=projekt_id)
    db.delete(projekt)
    db.commit()
