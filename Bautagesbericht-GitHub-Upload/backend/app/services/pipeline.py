import time
from datetime import datetime, date
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Einreichung, Projekt, VerarbeitungsLog
from app.schemas import BautagesberichtJSON, FirmaEintrag, WetterBlock, WarnungSchema
from app.services.pdf_extraction import extract_from_file
from app.services.weather import fetch_weather
from app.services.docx_generation import generate_bautagesbericht
from app.services.email_sender import send_bautagesbericht


def _log_step(db: Session, einreichung_id: int, schritt: str, ergebnis: str, details: str = "", dauer_ms: int = 0):
    log = VerarbeitungsLog(
        einreichung_id=einreichung_id,
        schritt=schritt,
        ergebnis=ergebnis,
        details=details,
        dauer_ms=dauer_ms,
    )
    db.add(log)
    db.commit()


def _send_email(db: Session, einreichung, output_path: Path, projekt) -> None:
    """Versendet den fertigen Bericht per E-Mail. Fehler werden protokolliert,
    aber der Abschluss-Status bleibt erhalten (Download bleibt immer möglich)."""
    empfaenger = einreichung.empfaenger
    if not empfaenger or not empfaenger.email:
        _log_step(db, einreichung.id, "email_versand", "warnung",
                  "Kein Empfänger hinterlegt")
        return

    t0 = time.time()
    try:
        send_bautagesbericht(
            empfaenger_email=empfaenger.email,
            projekt_name=projekt.name if projekt else "",
            datum=einreichung.datum,
            anhang_pfad=output_path,
        )
        _log_step(db, einreichung.id, "email_versand", "erfolg",
                  f"Gesendet an {empfaenger.email}",
                  int((time.time() - t0) * 1000))
    except Exception as exc:
        _log_step(db, einreichung.id, "email_versand", "fehler",
                  str(exc), int((time.time() - t0) * 1000))
        warnungen = list(einreichung.warnungen or [])
        warnungen.append({
            "feld": "email",
            "problem": f"Versand fehlgeschlagen ({exc}). Dokument kann heruntergeladen werden.",
            "quelle_datei": "",
        })
        einreichung.warnungen = warnungen
        db.commit()


async def process_einreichung(einreichung_id: int, db: Session):
    einreichung = db.query(Einreichung).get(einreichung_id)
    if not einreichung:
        return

    einreichung.status = "wird_verarbeitet"
    db.commit()

    projekt = db.query(Projekt).get(einreichung.projekt_id)
    warnungen: list[dict] = []
    all_firmen: list[dict] = []

    # Step 1: Weather
    wetter_data = None
    t0 = time.time()
    try:
        if projekt and projekt.lat and projekt.lon:
            wetter_data = await fetch_weather(
                projekt.lat, projekt.lon, einreichung.datum.isoformat()
            )
            if wetter_data:
                _log_step(db, einreichung_id, "wetterdaten", "erfolg",
                          f"Station: {wetter_data.get('station', '?')}",
                          int((time.time() - t0) * 1000))
            else:
                _log_step(db, einreichung_id, "wetterdaten", "warnung",
                          "Keine Wetterdaten verfügbar",
                          int((time.time() - t0) * 1000))
                warnungen.append({
                    "feld": "wetter",
                    "problem": "Keine Wetterdaten von Bright Sky erhalten",
                    "quelle_datei": "",
                })
        else:
            _log_step(db, einreichung_id, "wetterdaten", "warnung",
                      "Projekt hat keine Koordinaten")
            warnungen.append({
                "feld": "wetter",
                "problem": "Projekt hat keine Koordinaten — kein Wetterdaten-Abruf möglich",
                "quelle_datei": "",
            })
    except Exception as exc:
        _log_step(db, einreichung_id, "wetterdaten", "fehler", str(exc),
                  int((time.time() - t0) * 1000))
        warnungen.append({
            "feld": "wetter",
            "problem": f"Fehler beim Abruf: {exc}",
            "quelle_datei": "",
        })

    # Step 2: PDF Extraction
    for file_rel_path in (einreichung.quelle_dateien or []):
        file_path = settings.upload_dir.parent / file_rel_path
        if not file_path.exists():
            warnungen.append({
                "feld": "dateien",
                "problem": f"Datei nicht gefunden: {file_rel_path}",
                "quelle_datei": file_rel_path,
            })
            continue

        t0 = time.time()
        try:
            firmen = await extract_from_file(file_path, einreichung.datum)
            all_firmen.extend(firmen)
            _log_step(db, einreichung_id, "pdf_extraktion", "erfolg",
                      f"{len(firmen)} Firmen aus {file_path.name}",
                      int((time.time() - t0) * 1000))
        except Exception as exc:
            _log_step(db, einreichung_id, "pdf_extraktion", "fehler",
                      f"{file_path.name}: {exc}",
                      int((time.time() - t0) * 1000))
            warnungen.append({
                "feld": "dateien",
                "problem": f"Extraktion fehlgeschlagen: {exc}",
                "quelle_datei": file_rel_path,
            })

    if not all_firmen:
        warnungen.append({
            "feld": "firmen",
            "problem": "Keine Firmendaten extrahiert",
            "quelle_datei": "",
        })

    # Platzhalter erkennen (Scan ohne OCR / unbekanntes Format) und als Warnung melden
    for f in all_firmen:
        name = str(f.get("firma", ""))
        if name.startswith("("):
            warnungen.append({
                "feld": "firmen",
                "problem": f"Automatische Extraktion unvollständig: {name}",
                "quelle_datei": "",
            })

    # OCR-gelesene Einträge (aus Scans) immer zur manuellen Kontrolle melden
    if any(f.get("quelle") == "ocr" for f in all_firmen):
        warnungen.append({
            "feld": "firmen",
            "problem": "Mindestens ein Bericht wurde per OCR aus einem Scan gelesen "
                       "— bitte Firmenangaben und Leistungstext prüfen.",
            "quelle_datei": "",
        })

    # Step 3: Build validated JSON
    firmen_entries = []
    for i, f in enumerate(all_firmen):
        try:
            personen = int(f.get("personen", 0))
        except (ValueError, TypeError):
            warnungen.append({
                "feld": f"firmen[{i}].personen",
                "problem": f"'{f.get('personen')}' ist keine Zahl — auf 0 gesetzt",
                "quelle_datei": "",
            })
            personen = 0

        firmen_entries.append(FirmaEintrag(
            firma=str(f.get("firma", "")),
            ort=str(f.get("ort", "")),
            personen=personen,
            leistung=str(f.get("leistung", "")),
            besonderes=f.get("besonderes"),
        ))

    wetter_block = None
    if wetter_data:
        wetter_block = WetterBlock(**wetter_data)

    bericht_json = BautagesberichtJSON(
        projekt=projekt.name if projekt else "",
        datum=einreichung.datum,
        haupteintrag=einreichung.ergaenzende_angaben or "",
        wetter=wetter_block,
        firmen=firmen_entries,
        unterschrift_datum=einreichung.datum,
        warnungen=[WarnungSchema(**w) for w in warnungen],
    )

    einreichung.warnungen = warnungen

    if warnungen:
        einreichung.status = "wartet_auf_bestaetigung"
        db.commit()
        _log_step(db, einreichung_id, "validierung", "warnung",
                  f"{len(warnungen)} Warnungen")
        return

    # Step 4: Generate Word doc
    t0 = time.time()
    try:
        output_path = generate_bautagesbericht(bericht_json)
        rel_path = str(output_path.relative_to(settings.output_dir.parent))
        einreichung.ergebnis_dokument_pfad = rel_path
        einreichung.status = "abgeschlossen"
        einreichung.verarbeitet_am = datetime.now()
        db.commit()
        _log_step(db, einreichung_id, "docx_erzeugung", "erfolg",
                  f"Datei: {output_path.name}",
                  int((time.time() - t0) * 1000))
        _send_email(db, einreichung, output_path, projekt)
    except Exception as exc:
        einreichung.status = "fehlgeschlagen"
        db.commit()
        _log_step(db, einreichung_id, "docx_erzeugung", "fehler",
                  str(exc), int((time.time() - t0) * 1000))


async def confirm_and_generate(einreichung_id: int, db: Session):
    einreichung = db.query(Einreichung).get(einreichung_id)
    if not einreichung:
        return
    if einreichung.status not in ("wartet_auf_bestaetigung", "wird_verarbeitet"):
        return

    projekt = db.query(Projekt).get(einreichung.projekt_id)

    wetter_block = None
    wetter_data = None
    if projekt and projekt.lat and projekt.lon:
        wetter_data = await fetch_weather(
            projekt.lat, projekt.lon, einreichung.datum.isoformat()
        )
    if wetter_data:
        wetter_block = WetterBlock(**wetter_data)

    all_firmen = []
    for file_rel_path in (einreichung.quelle_dateien or []):
        file_path = settings.upload_dir.parent / file_rel_path
        if file_path.exists():
            try:
                firmen = await extract_from_file(file_path, einreichung.datum)
                all_firmen.extend(firmen)
            except Exception:
                pass

    firmen_entries = []
    for f in all_firmen:
        try:
            personen = int(f.get("personen", 0))
        except (ValueError, TypeError):
            personen = 0
        firmen_entries.append(FirmaEintrag(
            firma=str(f.get("firma", "")),
            ort=str(f.get("ort", "")),
            personen=personen,
            leistung=str(f.get("leistung", "")),
            besonderes=f.get("besonderes"),
        ))

    bericht_json = BautagesberichtJSON(
        projekt=projekt.name if projekt else "",
        datum=einreichung.datum,
        haupteintrag=einreichung.ergaenzende_angaben or "",
        wetter=wetter_block,
        firmen=firmen_entries,
        unterschrift_datum=einreichung.datum,
    )

    try:
        output_path = generate_bautagesbericht(bericht_json)
        rel_path = str(output_path.relative_to(settings.output_dir.parent))
        einreichung.ergebnis_dokument_pfad = rel_path
        einreichung.status = "abgeschlossen"
        einreichung.verarbeitet_am = datetime.now()
        db.commit()
        _log_step(db, einreichung_id, "docx_erzeugung_nach_bestaetigung", "erfolg",
                  f"Datei: {output_path.name}")
        _send_email(db, einreichung, output_path, projekt)
    except Exception as exc:
        einreichung.status = "fehlgeschlagen"
        db.commit()
        _log_step(db, einreichung_id, "docx_erzeugung_nach_bestaetigung", "fehler", str(exc))
