"""Konfigurierbare Wertelisten des Mängelmoduls.

Typ, Status, Rückmeldestatus und Bearbeiter sind Stammdaten und werden in der
App gepflegt, nicht im Code (siehe Kommentar in app.models). Beim ersten Start
legt ``app.database._seed_mangel_stammdaten`` die üblichen Werte an.

Eigener Prefix ``/mangel-stammdaten`` und nicht ``/maengel/stammdaten``: So
kann kein Konflikt mit der Detailroute ``/maengel/{mangel_id}`` entstehen.

Ein Listeneintrag darf gelöscht werden, auch wenn Mängel ihn verwenden — im
Mangel steht die Bezeichnung als Text, der Datensatz bleibt also lesbar. Der
Wert verschwindet dann nur aus der Auswahlliste.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Bearbeiter,
    MangelRueckmeldungStatus,
    MangelStatus,
    MangelTyp,
)
from app.schemas import (
    BearbeiterCreate,
    BearbeiterResponse,
    MangelRueckmeldungStatusCreate,
    MangelRueckmeldungStatusResponse,
    MangelStammdaten,
    MangelStatusCreate,
    MangelStatusResponse,
    MangelTypCreate,
    MangelTypResponse,
)

router = APIRouter(prefix="/mangel-stammdaten", tags=["mangel-stammdaten"])


def _sortiert(db: Session, modell):
    return db.query(modell).order_by(modell.sortierung, modell.id).all()


def _naechste_sortierung(db: Session, modell, gewuenscht: int) -> int:
    """0 bedeutet "ans Ende" — sonst zählen alle neuen Einträge bei 0 los."""
    if gewuenscht:
        return gewuenscht
    return (db.query(modell).count() or 0) + 1


@router.get("", response_model=MangelStammdaten)
def alle_stammdaten(db: Session = Depends(get_db)):
    return MangelStammdaten(
        typen=[MangelTypResponse.model_validate(t) for t in _sortiert(db, MangelTyp)],
        status=[
            MangelStatusResponse.model_validate(s) for s in _sortiert(db, MangelStatus)
        ],
        rueckmeldung_status=[
            MangelRueckmeldungStatusResponse.model_validate(r)
            for r in _sortiert(db, MangelRueckmeldungStatus)
        ],
        bearbeiter=[
            BearbeiterResponse.model_validate(b)
            for b in db.query(Bearbeiter).order_by(Bearbeiter.name).all()
        ],
    )


# ───────── Typ ─────────


@router.post("/typen", response_model=MangelTypResponse, status_code=201)
def create_typ(data: MangelTypCreate, db: Session = Depends(get_db)):
    eintrag = MangelTyp(
        bezeichnung=data.bezeichnung.strip(),
        sortierung=_naechste_sortierung(db, MangelTyp, data.sortierung),
    )
    db.add(eintrag)
    db.commit()
    db.refresh(eintrag)
    return eintrag


@router.delete("/typen/{typ_id}", status_code=204)
def delete_typ(typ_id: int, db: Session = Depends(get_db)):
    _loeschen(db, MangelTyp, typ_id, "Typ")


# ───────── Status ─────────


@router.post("/status", response_model=MangelStatusResponse, status_code=201)
def create_status(data: MangelStatusCreate, db: Session = Depends(get_db)):
    eintrag = MangelStatus(
        bezeichnung=data.bezeichnung.strip(),
        sortierung=_naechste_sortierung(db, MangelStatus, data.sortierung),
        farbe=data.farbe,
        ist_abgeschlossen=data.ist_abgeschlossen,
    )
    db.add(eintrag)
    db.commit()
    db.refresh(eintrag)
    return eintrag


@router.delete("/status/{status_id}", status_code=204)
def delete_status(status_id: int, db: Session = Depends(get_db)):
    _loeschen(db, MangelStatus, status_id, "Status")


# ───────── Rückmeldestatus ─────────


@router.post("/rueckmeldung-status",
             response_model=MangelRueckmeldungStatusResponse, status_code=201)
def create_rueckmeldung_status(data: MangelRueckmeldungStatusCreate,
                              db: Session = Depends(get_db)):
    eintrag = MangelRueckmeldungStatus(
        bezeichnung=data.bezeichnung.strip(),
        sortierung=_naechste_sortierung(
            db, MangelRueckmeldungStatus, data.sortierung
        ),
    )
    db.add(eintrag)
    db.commit()
    db.refresh(eintrag)
    return eintrag


@router.delete("/rueckmeldung-status/{eintrag_id}", status_code=204)
def delete_rueckmeldung_status(eintrag_id: int, db: Session = Depends(get_db)):
    _loeschen(db, MangelRueckmeldungStatus, eintrag_id, "Rückmeldestatus")


# ───────── Bearbeiter ─────────


@router.post("/bearbeiter", response_model=BearbeiterResponse, status_code=201)
def create_bearbeiter(data: BearbeiterCreate, db: Session = Depends(get_db)):
    eintrag = Bearbeiter(name=data.name.strip(), email=data.email)
    db.add(eintrag)
    db.commit()
    db.refresh(eintrag)
    return eintrag


@router.delete("/bearbeiter/{bearbeiter_id}", status_code=204)
def delete_bearbeiter(bearbeiter_id: int, db: Session = Depends(get_db)):
    """Löscht einen Bearbeiter und löst ihn aus den Mängeln.

    ``zustaendiger_user_id`` ist ein echter Fremdschlüssel — er muss zuerst
    geleert werden, sonst verweigert die Datenbank das Löschen.
    """
    from app.models import Mangel

    eintrag = db.get(Bearbeiter, bearbeiter_id)
    if not eintrag:
        raise HTTPException(404, "Bearbeiter nicht gefunden")
    db.query(Mangel).filter(Mangel.zustaendiger_user_id == bearbeiter_id).update(
        {"zustaendiger_user_id": None}, synchronize_session=False
    )
    db.delete(eintrag)
    db.commit()


def _loeschen(db: Session, modell, eintrag_id: int, bezeichnung: str) -> None:
    eintrag = db.get(modell, eintrag_id)
    if not eintrag:
        raise HTTPException(404, f"{bezeichnung} nicht gefunden")
    db.delete(eintrag)
    db.commit()
