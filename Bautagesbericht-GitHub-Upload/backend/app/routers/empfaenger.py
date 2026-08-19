from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Empfaenger
from app.schemas import EmpfaengerCreate, EmpfaengerResponse
from app.services.cleanup import count_einreichungen_for, delete_einreichungen_for

router = APIRouter(prefix="/empfaenger", tags=["empfaenger"])


@router.get("", response_model=list[EmpfaengerResponse])
def list_empfaenger(db: Session = Depends(get_db)):
    return db.query(Empfaenger).order_by(Empfaenger.erstellt_am.desc()).all()


@router.post("", response_model=EmpfaengerResponse, status_code=201)
def create_empfaenger(data: EmpfaengerCreate, db: Session = Depends(get_db)):
    emp = Empfaenger(label=data.label, email=data.email)
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@router.delete("/{empfaenger_id}", status_code=204)
def delete_empfaenger(empfaenger_id: int, force: bool = False, db: Session = Depends(get_db)):
    """Löscht einen Empfänger.

    Hängen noch Einreichungen daran, wird ohne ``force=true`` mit 409 abgelehnt
    und die Anzahl gemeldet — die Oberfläche fragt dann nach.
    """
    emp = db.get(Empfaenger, empfaenger_id)
    if not emp:
        raise HTTPException(404, "Empfänger nicht gefunden")

    anzahl = count_einreichungen_for(db, empfaenger_id=empfaenger_id)
    if anzahl and not force:
        raise HTTPException(
            409,
            detail={
                "grund": "einreichungen_vorhanden",
                "anzahl_einreichungen": anzahl,
                "nachricht": (
                    f"Zu diesem Empfänger gehören noch {anzahl} Einreichung(en). "
                    "Beim Löschen werden sie mit entfernt."
                ),
            },
        )

    if anzahl:
        delete_einreichungen_for(db, empfaenger_id=empfaenger_id)
    db.delete(emp)
    db.commit()
