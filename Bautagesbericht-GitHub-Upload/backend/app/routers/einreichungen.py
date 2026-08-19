from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models import Einreichung, Empfaenger, Projekt
from app.schemas import EinreichungResponse
from app.services.pipeline import confirm_and_generate, process_einreichung
from app.utils.file_storage import save_upload

router = APIRouter(prefix="/einreichungen", tags=["einreichungen"])


def _run_process(einreichung_id: int):
    import asyncio
    db = SessionLocal()
    try:
        asyncio.run(process_einreichung(einreichung_id, db))
    finally:
        db.close()


def _run_confirm(einreichung_id: int):
    import asyncio
    db = SessionLocal()
    try:
        asyncio.run(confirm_and_generate(einreichung_id, db))
    finally:
        db.close()


def _to_response(e: Einreichung) -> EinreichungResponse:
    return EinreichungResponse(
        id=e.id,
        projekt_id=e.projekt_id,
        projekt_name=e.projekt.name if e.projekt else "",
        empfaenger_id=e.empfaenger_id,
        empfaenger_label=e.empfaenger.label if e.empfaenger else "",
        empfaenger_email=e.empfaenger.email if e.empfaenger else "",
        datum=e.datum,
        ergaenzende_angaben=e.ergaenzende_angaben,
        status=e.status,
        quelle_dateien=e.quelle_dateien or [],
        warnungen=e.warnungen or [],
        eingereicht_am=e.eingereicht_am,
        verarbeitet_am=e.verarbeitet_am,
    )


@router.get("", response_model=list[EinreichungResponse])
def list_einreichungen(db: Session = Depends(get_db)):
    rows = (
        db.query(Einreichung)
        .order_by(Einreichung.eingereicht_am.desc())
        .limit(20)
        .all()
    )
    return [_to_response(e) for e in rows]


@router.get("/{einreichung_id}", response_model=EinreichungResponse)
def get_einreichung(einreichung_id: int, db: Session = Depends(get_db)):
    e = db.query(Einreichung).get(einreichung_id)
    if not e:
        raise HTTPException(404, "Einreichung nicht gefunden")
    return _to_response(e)


@router.post("", response_model=EinreichungResponse, status_code=201)
async def create_einreichung(
    background_tasks: BackgroundTasks,
    projekt_id: Annotated[int, Form()],
    empfaenger_id: Annotated[int, Form()],
    datum: Annotated[date, Form()],
    dateien: list[UploadFile] = File(...),
    ergaenzende_angaben: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    if not db.query(Projekt).get(projekt_id):
        raise HTTPException(400, "Projekt nicht gefunden")
    if not db.query(Empfaenger).get(empfaenger_id):
        raise HTTPException(400, "Empfänger nicht gefunden")
    if len(dateien) > settings.max_files_per_submission:
        raise HTTPException(400, f"Maximal {settings.max_files_per_submission} Dateien")

    einreichung = Einreichung(
        projekt_id=projekt_id,
        empfaenger_id=empfaenger_id,
        datum=datum,
        ergaenzende_angaben=ergaenzende_angaben,
        status="eingereicht",
        quelle_dateien=[],
    )
    db.add(einreichung)
    db.commit()
    db.refresh(einreichung)

    saved_paths = []
    for f in dateien:
        path = await save_upload(einreichung.id, f)
        saved_paths.append(path)

    einreichung.quelle_dateien = saved_paths
    db.commit()
    db.refresh(einreichung)

    background_tasks.add_task(_run_process, einreichung.id)

    return _to_response(einreichung)


@router.post("/{einreichung_id}/bestaetigen", response_model=EinreichungResponse)
def bestaetigen_einreichung(
    einreichung_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    e = db.query(Einreichung).get(einreichung_id)
    if not e:
        raise HTTPException(404, "Einreichung nicht gefunden")
    if e.status != "wartet_auf_bestaetigung":
        raise HTTPException(400, f"Bestätigung nur im Status 'wartet_auf_bestaetigung' möglich (aktuell: {e.status})")

    e.status = "wird_verarbeitet"
    db.commit()
    background_tasks.add_task(_run_confirm, einreichung_id)
    db.refresh(e)
    return _to_response(e)


@router.get("/{einreichung_id}/dokument")
def download_dokument(einreichung_id: int, db: Session = Depends(get_db)):
    e = db.query(Einreichung).get(einreichung_id)
    if not e:
        raise HTTPException(404, "Einreichung nicht gefunden")
    if not e.ergebnis_dokument_pfad:
        raise HTTPException(404, "Noch kein Dokument erzeugt")
    file_path = settings.output_dir.parent / e.ergebnis_dokument_pfad
    if not file_path.exists():
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(
        file_path,
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
