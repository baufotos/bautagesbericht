"""Projektpläne (Grundrisse) für die Plan-Markierung.

Entspricht "Plan öffnen" / "Dateibaum öffnen" / "Plan auswählen" im
Mangel-Formular: Pläne werden einmal pro Projekt hochgeladen, danach wählt man
im Mangel einen Plan aus und tippt die Stelle an.

Jede Planseite wird als Bild ausgeliefert (siehe app.services.plan_vorschau) —
so braucht die Oberfläche keinen PDF-Betrachter und kann die Tippposition
zuverlässig in Prozent der Planfläche umrechnen.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import MangelPlanMarkierung, Projekt, ProjektPlan
from app.schemas import ProjektPlanResponse
from app.services.bilder import ist_bilddatei
from app.services.plan_vorschau import rendere_seite, seitenzahl
from app.utils.file_storage import get_absolute_path, save_upload_in

router = APIRouter(prefix="/plaene", tags=["plaene"])

ERLAUBTE_ENDUNGEN = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


@router.get("", response_model=list[ProjektPlanResponse])
def list_plaene(projekt_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(ProjektPlan)
    if projekt_id is not None:
        query = query.filter(ProjektPlan.projekt_id == projekt_id)
    return query.order_by(ProjektPlan.dateiname).all()


@router.post("", response_model=ProjektPlanResponse, status_code=201)
async def upload_plan(
    projekt_id: Annotated[int, Form()],
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not db.get(Projekt, projekt_id):
        raise HTTPException(400, "Projekt nicht gefunden")

    name = Path(datei.filename or "plan").name
    endung = Path(name).suffix.lower()
    if endung not in ERLAUBTE_ENDUNGEN:
        raise HTTPException(
            400,
            "Nur PDF- oder Bilddateien sind als Plan möglich "
            f"(erlaubt: {', '.join(sorted(ERLAUBTE_ENDUNGEN))})",
        )

    inhalt = await datei.read()
    grenze = settings.max_file_size_mb * 1024 * 1024
    if len(inhalt) > grenze:
        raise HTTPException(400, f"Plan ist größer als {settings.max_file_size_mb} MB")

    rel_pfad = await save_upload_in(f"plaene/{projekt_id}", datei, inhalt=inhalt)
    plan = ProjektPlan(
        projekt_id=projekt_id,
        dateiname=name,
        dateipfad=rel_pfad,
        seiten=seitenzahl(get_absolute_path(rel_pfad)),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/{plan_id}/vorschau")
def plan_vorschau(plan_id: int, seite: int = 1, db: Session = Depends(get_db)):
    """Eine Planseite als JPEG — die Fläche, auf die getippt wird."""
    plan = db.get(ProjektPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan nicht gefunden")

    bild = rendere_seite(get_absolute_path(plan.dateipfad), seite=max(1, seite))
    if bild is None:
        raise HTTPException(422, "Plan konnte nicht als Bild dargestellt werden")
    return FileResponse(
        bild,
        media_type="image/jpeg",
        # Vorschauen sind unveränderlich (Dateiname enthält Seite und Breite);
        # der Browser darf sie behalten, das schont die Baustellenverbindung.
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/{plan_id}/datei")
def plan_datei(plan_id: int, db: Session = Depends(get_db)):
    """Originaldatei des Plans zum Herunterladen."""
    plan = db.get(ProjektPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan nicht gefunden")
    pfad = get_absolute_path(plan.dateipfad)
    if not pfad.is_file():
        raise HTTPException(404, "Datei nicht gefunden")
    medientyp = "application/pdf" if not ist_bilddatei(plan.dateiname) else None
    return FileResponse(pfad, filename=plan.dateiname, media_type=medientyp)


@router.delete("/{plan_id}", status_code=204)
def delete_plan(plan_id: int, force: bool = False, db: Session = Depends(get_db)):
    """Löscht einen Plan; vorhandene Markierungen werden mit entfernt."""
    plan = db.get(ProjektPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan nicht gefunden")

    anzahl = (
        db.query(MangelPlanMarkierung)
        .filter(MangelPlanMarkierung.plan_datei_id == plan_id)
        .count()
    )
    if anzahl and not force:
        raise HTTPException(
            409,
            detail={
                "grund": "markierungen_vorhanden",
                "anzahl": anzahl,
                "nachricht": (
                    f"Auf diesem Plan sitzen {anzahl} Mangel-Markierung(en). "
                    "Beim Löschen gehen sie verloren; die Mängel selbst bleiben."
                ),
            },
        )

    if anzahl:
        db.query(MangelPlanMarkierung).filter(
            MangelPlanMarkierung.plan_datei_id == plan_id
        ).delete(synchronize_session=False)

    pfad = get_absolute_path(plan.dateipfad)
    try:
        if pfad.is_file():
            pfad.unlink()
        # Zwischengespeicherte Seitenvorschauen mit entfernen.
        for vorschau in (pfad.parent / "_vorschau").glob(f"{pfad.stem}_s*.jpg"):
            vorschau.unlink()
    except OSError:
        # Wie in app.services.cleanup: Dateisystemfehler dürfen das Löschen
        # des Datensatzes nicht blockieren.
        pass

    db.delete(plan)
    db.commit()
