"""Stammdaten der Subplaner, gruppiert nach Phase.

Aufbau wie ``routers.empfaenger``, mit einem Unterschied: Die Liste ist nach
Phase und Sortierung geordnet, weil die Oberfläche sie als Phase 1 / 2 / 3
gruppiert anzeigt (siehe components/stammdaten/SubplanerVerwaltung).

Warum die Adressen eine Liste sind und warum sie leer sein dürfen, steht am
Modell (``models.McdonaldsSubplaner``) und in den Startwerten
(``database.MCDONALDS_SUBPLANER_START``).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import McdonaldsBeauftragung, McdonaldsSubplaner
from app.schemas import SubplanerCreate, SubplanerResponse, SubplanerUpdate

router = APIRouter(prefix="/subplaner", tags=["subplaner"])


def _hole(db: Session, subplaner_id: int) -> McdonaldsSubplaner:
    planer = db.get(McdonaldsSubplaner, subplaner_id)
    if not planer:
        raise HTTPException(404, "Subplaner nicht gefunden")
    return planer


@router.get("", response_model=list[SubplanerResponse])
def list_subplaner(
    phase: int | None = Query(default=None, ge=1, le=3),
    db: Session = Depends(get_db),
):
    """Alle Subplaner, nach Phase und Sortierung — oder nur eine Phase."""
    frage = db.query(McdonaldsSubplaner)
    if phase is not None:
        frage = frage.filter(McdonaldsSubplaner.phase == phase)
    return frage.order_by(
        McdonaldsSubplaner.phase,
        McdonaldsSubplaner.sortierung,
        McdonaldsSubplaner.id,
    ).all()


@router.post("", response_model=SubplanerResponse, status_code=201)
def create_subplaner(daten: SubplanerCreate, db: Session = Depends(get_db)):
    planer = McdonaldsSubplaner(
        phase=daten.phase,
        name=daten.name.strip(),
        kuerzel=daten.kuerzel.strip().upper(),
        ordner=daten.ordner.strip(),
        ansprechpartner=daten.ansprechpartner.strip(),
        anrede=daten.anrede.strip(),
        emails=[str(a).strip() for a in daten.emails],
        angebot_datum=daten.angebot_datum,
        textvariante=daten.textvariante.strip().lower(),
        sortierung=daten.sortierung,
    )
    db.add(planer)
    db.commit()
    db.refresh(planer)
    return planer


@router.patch("/{subplaner_id}", response_model=SubplanerResponse)
def update_subplaner(
    subplaner_id: int, daten: SubplanerUpdate, db: Session = Depends(get_db)
):
    """Ändert einen Subplaner. Nicht gesetzte Felder bleiben, wie sie sind.

    Der Weg, auf dem die fehlenden E-Mail-Adressen der mitgelieferten Firmen
    Kocks und RKA hineinkommen.
    """
    planer = _hole(db, subplaner_id)
    werte = daten.model_dump(exclude_unset=True)

    for feld in ("name", "ordner", "ansprechpartner", "anrede"):
        if werte.get(feld) is not None:
            setattr(planer, feld, werte[feld].strip())
    if werte.get("kuerzel") is not None:
        planer.kuerzel = werte["kuerzel"].strip().upper()
    if werte.get("textvariante") is not None:
        planer.textvariante = werte["textvariante"].strip().lower()
    if werte.get("emails") is not None:
        planer.emails = [str(a).strip() for a in werte["emails"]]
    for feld in ("phase", "angebot_datum", "sortierung"):
        if feld in werte and werte[feld] is not None:
            setattr(planer, feld, werte[feld])

    db.commit()
    db.refresh(planer)
    return planer


@router.delete("/{subplaner_id}", status_code=204)
def delete_subplaner(subplaner_id: int, db: Session = Depends(get_db)):
    """Löscht einen Subplaner.

    Hängen Einzelabrufe daran, wird abgelehnt — und zwar auch mit ``force``.
    Ein Einzelabruf ist ein Vertragsdokument: Der Nachweis, an wen es ging,
    darf nicht verschwinden, weil jemand die Stammdaten aufräumt. Wer die
    Firma nicht mehr braucht, ändert ihren Namen oder legt sie auf eine
    andere Phase.
    """
    planer = _hole(db, subplaner_id)

    anzahl = (
        db.query(McdonaldsBeauftragung)
        .filter(McdonaldsBeauftragung.subplaner_id == subplaner_id)
        .count()
    )
    if anzahl:
        raise HTTPException(
            409,
            detail={
                "grund": "beauftragungen_vorhanden",
                "anzahl": anzahl,
                "nachricht": (
                    f"Zu „{planer.name}“ gehören {anzahl} Einzelabruf(e). Der "
                    "Eintrag bleibt deshalb erhalten — sonst wäre nicht mehr "
                    "nachvollziehbar, an wen sie gingen."
                ),
            },
        )

    db.delete(planer)
    db.commit()
