"""Zuständige Firmen / Büros (Gewerke) eines Projekts.

Ein Gewerk gehört immer zu genau einem Projekt — dieselbe Firma kann in zwei
Bauvorhaben unterschiedliche Vergabeeinheiten und Ansprechpartner haben.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BesprechungsKapitel, Gewerk, Mangel, Projekt
from app.schemas import GewerkCreate, GewerkResponse, GewerkUpdate
from app.services.mangel_logik import gewerk_anzeige

router = APIRouter(prefix="/gewerke", tags=["gewerke"])


def _to_response(gewerk: Gewerk) -> GewerkResponse:
    antwort = GewerkResponse.model_validate(gewerk)
    antwort.anzeige_name = gewerk_anzeige(gewerk)
    return antwort


@router.get("", response_model=list[GewerkResponse])
def list_gewerke(projekt_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(Gewerk)
    if projekt_id is not None:
        query = query.filter(Gewerk.projekt_id == projekt_id)
    rows = query.order_by(Gewerk.vergabeeinheit_code, Gewerk.firma_name).all()
    return [_to_response(g) for g in rows]


@router.post("", response_model=GewerkResponse, status_code=201)
def create_gewerk(data: GewerkCreate, db: Session = Depends(get_db)):
    if not db.get(Projekt, data.projekt_id):
        raise HTTPException(400, "Projekt nicht gefunden")

    gewerk = Gewerk(
        projekt_id=data.projekt_id,
        firma_name=data.firma_name.strip(),
        vergabeeinheit_code=data.vergabeeinheit_code.strip(),
        vergabeeinheit_bezeichnung=data.vergabeeinheit_bezeichnung.strip(),
        email=data.email,
        # Postanschrift für den Adressblock der Mängelanzeige.
        ansprechpartner=data.ansprechpartner.strip(),
        strasse=data.strasse.strip(),
        plz=data.plz.strip(),
        ort=data.ort.strip(),
        teams_webhook_url=data.teams_webhook_url.strip(),
    )
    db.add(gewerk)
    db.commit()
    db.refresh(gewerk)
    return _to_response(gewerk)


@router.patch("/{gewerk_id}", response_model=GewerkResponse)
def update_gewerk(gewerk_id: int, data: GewerkUpdate, db: Session = Depends(get_db)):
    gewerk = db.get(Gewerk, gewerk_id)
    if not gewerk:
        raise HTTPException(404, "Gewerk nicht gefunden")

    # exclude_unset: Nur mitgesendete Felder werden geschrieben — so kann die
    # Oberfläche eine einzelne Angabe nachtragen (z. B. die fehlende
    # E-Mail-Adresse), ohne den Rest mitzuschicken.
    for feld, wert in data.model_dump(exclude_unset=True).items():
        setattr(gewerk, feld, wert)
    db.commit()
    db.refresh(gewerk)
    return _to_response(gewerk)


@router.delete("/{gewerk_id}", status_code=204)
def delete_gewerk(gewerk_id: int, force: bool = False, db: Session = Depends(get_db)):
    """Löscht ein Gewerk.

    Hängen noch Mängel daran, wird ohne ``force=true`` mit 409 abgelehnt und
    die Anzahl gemeldet. Mit ``force=true`` bleiben die Mängel erhalten und
    verlieren nur die Firmenzuordnung — eine Mängelhistorie darf nicht
    verschwinden, weil eine Firma aus den Stammdaten entfernt wird.
    """
    gewerk = db.get(Gewerk, gewerk_id)
    if not gewerk:
        raise HTTPException(404, "Gewerk nicht gefunden")

    anzahl = db.query(Mangel).filter(Mangel.gewerk_id == gewerk_id).count()
    if anzahl and not force:
        raise HTTPException(
            409,
            detail={
                "grund": "maengel_vorhanden",
                "anzahl": anzahl,
                "anzahl_maengel": anzahl,
                "nachricht": (
                    f"Zu dieser Firma gehören noch {anzahl} Mangel/Mängel. "
                    "Beim Löschen bleiben sie erhalten, verlieren aber die "
                    "Firmenzuordnung."
                ),
            },
        )

    if anzahl:
        db.query(Mangel).filter(Mangel.gewerk_id == gewerk_id).update(
            {"gewerk_id": None}, synchronize_session=False
        )

    # Kapitel der Besprechungsprotokolle verweisen ebenfalls auf das Gewerk.
    #
    # Ohne diese Zeile scheiterte das Löschen mit
    # "FOREIGN KEY constraint failed" — für den Anwender ein Serverfehler ohne
    # Erklärung, und die Firma blieb in den Stammdaten stehen. Genau das steht
    # im Protokoll der laufenden App.
    #
    # Gemeldet wird das NICHT als Konflikt: Anders als beim Mangel ist der
    # Verweis hier beiläufig. Ein Kapitel überlebt das Gewerk ausdrücklich
    # (siehe models.BesprechungsKapitel) — die Firma wechselt, die Themen
    # bleiben —, und ``gewerk_id`` merkt sich nur, woher der Vorschlag kam.
    db.query(BesprechungsKapitel).filter(
        BesprechungsKapitel.gewerk_id == gewerk_id
    ).update({"gewerk_id": None}, synchronize_session=False)

    db.delete(gewerk)
    db.commit()
