import io
import re
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models import Einreichung, Empfaenger, Projekt
from app.schemas import (
    EinreichungResponse,
    WochenAnalyse,
    WochenEinreichung,
    WochenErgebnis,
    WochenQuelle,
    WochenTag,
)
from app.services import firmennamen
from app.services import wochenaufteilung as wa
from app.services import wochenpaket_ablage as ablage
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
    # 200 statt vorher 20 — die Übersichtsseite soll wirklich alle offenen
    # und kürzlich fertigen Berichte zeigen, nicht nur die letzten paar.
    rows = (
        db.query(Einreichung)
        .order_by(Einreichung.eingereicht_am.desc())
        .limit(200)
        .all()
    )
    return [_to_response(e) for e in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Wochenpaket: einmal hochladen, für jeden Tag ein Bericht
#
# ACHTUNG REIHENFOLGE: Diese Routen müssen vor "/{einreichung_id}" stehen.
# FastAPI probiert von oben nach unten; "/woche/analyse" würde sonst an der
# Zahlen-Route hängenbleiben und mit 422 statt mit einer Antwort enden.
#
# Der Ablauf ist bewusst zweistufig:
#   1. hochladen und sehen, welche Tage im Paket stecken
#   2. bestätigen — dann entsteht je Tag eine ganz normale Einreichung
# Schritt 2 nutzt danach dieselbe Verarbeitung wie ein einzelner Tag. Es gibt
# also keinen zweiten Weg durch Wetterabruf, Extraktion und Word-Erzeugung,
# der irgendwann auseinanderlaufen könnte.
# ─────────────────────────────────────────────────────────────────────────────


def _quellen_aus(block: wa.Tagesblock) -> list[WochenQuelle]:
    return [
        WochenQuelle(datei=Path(datei).name, seiten=sorted(seiten))
        for datei, seiten in block.seiten_je_datei.items()
    ]


def _abschnitte_auslagern(funde: list[wa.Seitenfund],
                          ordner: Path) -> list[wa.Seitenfund]:
    """Schreibt Tage, die sich eine Seite teilen, in eigene Textdateien.

    Stehen mehrere Tagesberichte auf einem Blatt, lässt sich das Blatt nicht
    zerschneiden — der Text schon. Je Tag entsteht deshalb eine ``.txt``, die
    von da an wie jede andere Quelldatei behandelt wird. Die Extraktion hat
    dafür einen eigenen Zweig (siehe services/pdf_extraction).
    """
    ergebnis: list[wa.Seitenfund] = []
    for fund in funde:
        if fund.herkunft != "abschnitt" or not fund.abschnitt:
            ergebnis.append(fund)
            continue

        quelle = Path(fund.datei)
        name = f"{quelle.stem}_S{fund.seite}_{fund.datum.isoformat()}.txt"
        ziel = ordner / name
        ziel.write_text(fund.abschnitt, encoding="utf-8")
        ergebnis.append(
            wa.Seitenfund(datei=str(ziel), seite=1, datum=fund.datum,
                          herkunft="abschnitt")
        )
    return ergebnis


@router.get("/faehigkeiten")
def faehigkeiten():
    """Was die App auf diesem Rechner kann — für Hinweise in der Oberfläche."""
    from app.services.pdf_extraction import erkennung_beschreibung

    kann, hinweis = erkennung_beschreibung()
    return {"handschrift": kann, "hinweis": hinweis}


@router.post("/woche/analyse", response_model=WochenAnalyse)
async def woche_analysieren(
    dateien: list[UploadFile] = File(...),
    woche_von: Annotated[str, Form()] = "",
    woche_bis: Annotated[str, Form()] = "",
    # Optional: Ist das Projekt schon gewählt, können die dort bekannten
    # Firmen beim Lesen helfen. Ohne Angabe funktioniert alles wie bisher.
    projekt_id: Annotated[int | None, Form()] = None,
    db: Session = Depends(get_db),
):
    """Nimmt die Berichte eines Zeitraums entgegen und meldet, welche Tage drinstecken.

    Legt noch nichts an. ``woche_von`` und ``woche_bis`` grenzen die zulässigen
    Daten ein — damit werden Vertragsfristen und Termine im Fließtext nicht
    versehentlich für das Berichtsdatum gehalten. Der Zeitraum ist außerdem das
    Signal, an dem sich mehrere Tage auf EINEM Blatt trennen lassen.
    """
    if len(dateien) > settings.max_files_per_submission:
        raise HTTPException(400, f"Maximal {settings.max_files_per_submission} Dateien")

    ablage.aufraeumen()

    kennung = ablage.neue_kennung()
    ordner = ablage.ordner(kennung)
    ordner.mkdir(parents=True, exist_ok=True)

    gespeichert: list[Path] = []
    for hochgeladen in dateien:
        name = Path(hochgeladen.filename or "datei").name
        ziel = ordner / name
        zaehler = 1
        while ziel.exists():
            ziel = ordner / f"{Path(name).stem}_{zaehler}{Path(name).suffix}"
            zaehler += 1
        ziel.write_bytes(await hochgeladen.read())
        gespeichert.append(ziel)

    erlaubt: set[date] | None = None
    if woche_von:
        try:
            von = date.fromisoformat(woche_von)
        except ValueError:
            raise HTTPException(400, "Startdatum muss ein Datum sein (JJJJ-MM-TT)")
        if woche_bis:
            try:
                bis = date.fromisoformat(woche_bis)
            except ValueError:
                raise HTTPException(400, "Enddatum muss ein Datum sein (JJJJ-MM-TT)")
        else:
            # Ohne Ende: die Arbeitswoche ab dem Startdatum. Sieben Tage, damit
            # Samstagsarbeit nicht herausfällt.
            bis = von + timedelta(days=6)
        if bis < von:
            raise HTTPException(400, "Das Enddatum liegt vor dem Startdatum")
        if (bis - von).days > 92:
            raise HTTPException(400, "Der Zeitraum darf höchstens ein Quartal umfassen")
        erlaubt = {von + timedelta(days=i) for i in range((bis - von).days + 1)}

    # Handschriftliche Blätter werden hier seitenweise angesehen, wenn aus dem
    # Text kein Datum kam. Das dauert — bei einer Woche Bautagebuch gut eine
    # Minute — ist aber der einzige Weg, Schreibschrift überhaupt zu lesen.
    bekannte = firmennamen.bekannte_firmen(db, projekt_id) if projekt_id else ()
    funde, lese_hinweise = await wa.finde_seitendaten_genau(
        gespeichert, erlaubt, bekannte)
    funde = _abschnitte_auslagern(funde, ordner)
    bloecke = wa.gruppiere_nach_tag(funde)
    geteilte_seiten = sum(1 for f in funde if f.herkunft == "abschnitt")

    tage: list[WochenTag] = []
    ohne_datum: WochenTag | None = None
    for block in bloecke:
        eintrag = WochenTag(
            datum=block.datum,
            quellen=_quellen_aus(block),
            anzahl_seiten=block.anzahl_seiten,
        )
        if block.datum is None:
            ohne_datum = eintrag
        else:
            tage.append(eintrag)

    hinweise: list[str] = list(lese_hinweise)
    if tage:
        hinweise.append(
            f"{len(tage)} Tag(e) erkannt: "
            + ", ".join(f"{wa.wochentag(t.datum)}, {t.datum.strftime('%d.%m.')}"
                        for t in tage)
        )
    else:
        hinweise.append(
            "In den hochgeladenen Dateien wurde kein Datum gefunden. Bitte "
            "jeder Datei unten von Hand einen Tag zuweisen."
        )
    if ohne_datum:
        hinweise.append(
            f"{ohne_datum.anzahl_seiten} Seite(n) ohne erkennbares Datum — "
            "das sind meist Scans oder Fotos ohne Textebene."
        )
    if geteilte_seiten:
        hinweise.append(
            f"{geteilte_seiten} Tagesbericht(e) standen zusammen auf einem "
            "Blatt und wurden je Tag getrennt."
        )
    wochenende = [t for t in tage if t.datum and t.datum.weekday() >= 5]
    if wochenende:
        hinweise.append(
            "Darunter ist Wochenendarbeit: "
            + ", ".join(f"{wa.wochentag(t.datum)}, {t.datum.strftime('%d.%m.')}"
                        for t in wochenende)
        )

    return WochenAnalyse(
        kennung=kennung,
        dateien=[p.name for p in gespeichert],
        tage=tage,
        ohne_datum=ohne_datum,
        hinweise=hinweise,
    )


@router.post("/woche", response_model=WochenErgebnis, status_code=201)
def woche_einreichen(
    daten: WochenEinreichung,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Erzeugt aus den bestätigten Tagen je einen ganz normalen Bautagesbericht."""
    if not db.query(Projekt).get(daten.projekt_id):
        raise HTTPException(400, "Projekt nicht gefunden")
    if not db.query(Empfaenger).get(daten.empfaenger_id):
        raise HTTPException(400, "Empfänger nicht gefunden")

    try:
        paketordner = ablage.ordner(daten.kennung)
    except ValueError:
        raise HTTPException(400, "Ungültige Paketkennung")
    if not paketordner.is_dir():
        raise HTTPException(
            404,
            "Das hochgeladene Paket ist nicht mehr da. Bitte die Dateien "
            "erneut hochladen.",
        )

    mit_datum = [t for t in daten.tage if t.datum is not None and t.quellen]
    if not mit_datum:
        raise HTTPException(400, "Kein Tag mit Datum und Dateien angegeben")

    doppelte = {t.datum for t in mit_datum if
                sum(1 for x in mit_datum if x.datum == t.datum) > 1}
    if doppelte:
        raise HTTPException(
            400,
            "Ein Tag darf nur einmal vorkommen: "
            + ", ".join(d.strftime("%d.%m.%Y") for d in sorted(doppelte)),
        )

    hinweise: list[str] = []
    angelegt: list[Einreichung] = []

    for tag in sorted(mit_datum, key=lambda t: t.datum):
        einreichung = Einreichung(
            projekt_id=daten.projekt_id,
            empfaenger_id=daten.empfaenger_id,
            datum=tag.datum,
            ergaenzende_angaben=tag.ergaenzende_angaben or "",
            status="eingereicht",
            quelle_dateien=[],
        )
        db.add(einreichung)
        db.commit()
        db.refresh(einreichung)

        zielordner = settings.upload_dir / str(einreichung.id)
        zielordner.mkdir(parents=True, exist_ok=True)

        pfade: list[str] = []
        for quelle in tag.quellen:
            try:
                herkunft = ablage.datei_im_paket(daten.kennung, quelle.datei)
            except ValueError:
                continue
            if not herkunft.is_file():
                hinweise.append(f"Datei fehlt im Paket: {quelle.datei}")
                continue

            marke = tag.datum.isoformat()
            ziel = zielordner / f"{herkunft.stem}_{marke}{herkunft.suffix}"
            try:
                if herkunft.suffix.lower() == ".pdf" and quelle.seiten:
                    wa.schreibe_teil_pdf(herkunft, quelle.seiten, ziel)
                else:
                    # Bild oder ganze Datei: unverändert übernehmen.
                    import shutil

                    shutil.copy2(herkunft, ziel)
            except Exception as exc:
                hinweise.append(f"{quelle.datei}: {exc}")
                continue
            pfade.append(str(ziel.relative_to(settings.upload_dir.parent)))

        einreichung.quelle_dateien = pfade
        db.commit()
        db.refresh(einreichung)

        if pfade:
            background_tasks.add_task(_run_process, einreichung.id)
        else:
            einreichung.status = "fehlgeschlagen"
            db.commit()
            hinweise.append(
                f"{tag.datum.strftime('%d.%m.%Y')}: keine verwertbare Datei — "
                "der Bericht wurde angelegt, aber nicht verarbeitet."
            )

        angelegt.append(einreichung)

    ablage.verwerfen(daten.kennung)

    hinweise.insert(
        0,
        f"{len(angelegt)} Bericht(e) angelegt. Die Verarbeitung läuft im "
        "Hintergrund — Wetterdaten und Firmenangaben je Tag getrennt.",
    )

    return WochenErgebnis(
        einreichungen=[_to_response(e) for e in angelegt],
        hinweise=hinweise,
    )


@router.get("/dokumente.zip")
def dokumente_als_zip(ids: str, db: Session = Depends(get_db)):
    """Mehrere fertige Berichte in einem Archiv — der Sammelabruf einer Woche."""
    kennungen = [int(t) for t in re.findall(r"\d+", ids or "")]
    if not kennungen:
        raise HTTPException(400, "Keine Berichte angegeben")

    rows = (
        db.query(Einreichung)
        .filter(Einreichung.id.in_(kennungen))
        .order_by(Einreichung.datum)
        .all()
    )

    puffer = io.BytesIO()
    aufgenommen = 0
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as archiv:
        vergeben: set[str] = set()
        for e in rows:
            if not e.ergebnis_dokument_pfad:
                continue
            pfad = settings.output_dir.parent / e.ergebnis_dokument_pfad
            if not pfad.is_file():
                continue
            name = pfad.name
            zaehler = 1
            while name in vergeben:
                name = f"{pfad.stem}_{zaehler}{pfad.suffix}"
                zaehler += 1
            vergeben.add(name)
            archiv.write(pfad, name)
            aufgenommen += 1

    if aufgenommen == 0:
        raise HTTPException(
            404,
            "Für die gewählten Tage ist noch kein Dokument fertig. Bitte kurz "
            "warten und erneut versuchen.",
        )

    puffer.seek(0)
    dateiname = f"Bautagesberichte_{rows[0].datum.isoformat()}.zip" if rows else "Bautagesberichte.zip"
    return StreamingResponse(
        puffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )


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
