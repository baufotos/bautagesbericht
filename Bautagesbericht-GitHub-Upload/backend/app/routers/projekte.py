from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Projekt
from app.schemas import ProjektCreate, ProjektResponse
from app.services.cleanup import (
    count_einreichungen_for,
    count_fotosaetze_for,
    count_projektberichte_for,
    count_maengel_for,
    delete_einreichungen_for,
    delete_fotosaetze_for,
    delete_projektberichte_for,
    delete_maengel_for,
)
from app.services.geocoding import geocode_address

router = APIRouter(prefix="/projekte", tags=["projekte"])


@router.get("", response_model=list[ProjektResponse])
def list_projekte(db: Session = Depends(get_db)):
    return db.query(Projekt).order_by(Projekt.erstellt_am.desc()).all()


@router.post("", response_model=ProjektResponse, status_code=201)
async def create_projekt(data: ProjektCreate, db: Session = Depends(get_db)):
    lat, lon = await geocode_address(data.adresse)
    projekt = Projekt(
        name=data.name,
        adresse=data.adresse,
        lat=lat,
        lon=lon,
        teams_webhook_url=data.teams_webhook_url.strip(),
    )
    db.add(projekt)
    db.commit()
    db.refresh(projekt)
    return projekt


@router.delete("/{projekt_id}", status_code=204)
def delete_projekt(projekt_id: int, force: bool = False, db: Session = Depends(get_db)):
    """Löscht ein Projekt.

    Hängen noch Einreichungen oder Mängel daran, wird ohne ``force=true`` mit
    409 abgelehnt und die Anzahl gemeldet — so kann die Oberfläche nachfragen,
    bevor Berichts- und Mängelhistorie mitgelöscht werden.
    """
    projekt = db.get(Projekt, projekt_id)
    if not projekt:
        raise HTTPException(404, "Projekt nicht gefunden")

    anzahl = count_einreichungen_for(db, projekt_id=projekt_id)
    anzahl_maengel = count_maengel_for(db, projekt_id=projekt_id)
    anzahl_fotosaetze = count_fotosaetze_for(db, projekt_id=projekt_id)
    anzahl_berichte = count_projektberichte_for(db, projekt_id=projekt_id)
    if (anzahl or anzahl_maengel or anzahl_fotosaetze or anzahl_berichte) and not force:
        teile = []
        if anzahl:
            teile.append(f"{anzahl} Einreichung(en)")
        if anzahl_maengel:
            teile.append(f"{anzahl_maengel} Mangel/Mängel")
        if anzahl_fotosaetze:
            teile.append(f"{anzahl_fotosaetze} Fotosatz/Fotosätze")
        if anzahl_berichte:
            teile.append(f"{anzahl_berichte} Projektbericht(e)")
        raise HTTPException(
            409,
            detail={
                "grund": "abhaengige_daten_vorhanden",
                "anzahl": anzahl + anzahl_maengel + anzahl_fotosaetze + anzahl_berichte,
                "anzahl_einreichungen": anzahl,
                "anzahl_maengel": anzahl_maengel,
                "anzahl_fotosaetze": anzahl_fotosaetze,
                "anzahl_projektberichte": anzahl_berichte,
                "nachricht": (
                    f"Zu diesem Projekt gehören noch {', '.join(teile)}. "
                    "Beim Löschen werden sie mit entfernt."
                ),
            },
        )

    if anzahl:
        delete_einreichungen_for(db, projekt_id=projekt_id)
    if anzahl_fotosaetze:
        delete_fotosaetze_for(db, projekt_id=projekt_id)
    if anzahl_berichte:
        delete_projektberichte_for(db, projekt_id=projekt_id)
    # Immer aufrufen: Auch ein Projekt ohne Mängel kann Gewerke und Pläne
    # haben, die per Fremdschlüssel darauf verweisen und mit weg müssen.
    delete_maengel_for(db, projekt_id=projekt_id)
    db.delete(projekt)
    db.commit()
