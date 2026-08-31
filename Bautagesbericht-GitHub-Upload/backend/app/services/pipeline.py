import time
from datetime import datetime, date

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Einreichung, Projekt, VerarbeitungsLog
from app.schemas import BautagesberichtJSON, FirmaEintrag, WetterBlock, WarnungSchema
from app.services.pdf_extraction import extract_from_file
from app.services.weather import fetch_weather
from app.services.docx_generation import generate_bautagesbericht
from app.services.teams_notifier import send_teams_notification


def _haelt_auf(warnungen: list[dict]) -> bool:
    """Muss vor dem Erzeugen jemand hinsehen?

    Nicht jede Warnung ist ein Grund, den Bericht liegen zu lassen. Zwei Arten
    sind zu unterscheiden:

    * **Aufhaltend** — es fehlt etwas, das im Dokument stehen müsste: keine
      Firmendaten gefunden, ein unlesbares Format, eine fehlende Datei. Hier
      wäre das Ergebnis unbrauchbar, also wartet der Bericht auf eine
      Bestätigung.
    * **Nur ein Hinweis** (``blockiert: False``) — der Bericht ist vollständig,
      man sollte ihn aber gegenlesen. Typisch für gescannte Berichte: Die
      Texterkennung hat alles gelesen, kann sich aber verlesen haben.

    Ohne diese Unterscheidung stand jeder Tag einer gescannten Woche auf
    "Prüfung nötig" — fünf Mal derselbe Knopf, obwohl nichts fehlte.
    """
    return any(w.get("blockiert", True) for w in warnungen)


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


async def _send_teams(db: Session, einreichung, projekt) -> None:
    """Postet eine Benachrichtigung mit Download-Link in Microsoft Teams.

    Nutzt den persönlichen Kanal-Webhook des Empfängers (Feld
    ``teams_webhook_url``, in den Stammdaten hinterlegt), ersatzweise den
    globalen BTB_TEAMS_WEBHOOK_URL. Ist keiner von beiden gesetzt, passiert
    nichts — siehe app.services.teams_notifier. Fehler werden protokolliert,
    aber der Abschluss-Status bleibt erhalten (Download bleibt immer möglich).
    """
    empfaenger = einreichung.empfaenger
    t0 = time.time()
    try:
        await send_teams_notification(
            einreichung_id=einreichung.id,
            projekt_name=projekt.name if projekt else "",
            datum=einreichung.datum,
            webhook_url=(empfaenger.teams_webhook_url if empfaenger else "") or "",
        )
        _log_step(db, einreichung.id, "teams_benachrichtigung", "erfolg",
                  "", int((time.time() - t0) * 1000))
    except Exception as exc:
        _log_step(db, einreichung.id, "teams_benachrichtigung", "fehler",
                  str(exc), int((time.time() - t0) * 1000))
        warnungen = list(einreichung.warnungen or [])
        warnungen.append({
            "feld": "teams",
            "problem": f"Teams-Benachrichtigung fehlgeschlagen ({exc}). Dokument kann heruntergeladen werden.",
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
            "problem": "Aus einem Scan gelesen — bitte Firmenangaben und "
                       "Leistungstext im fertigen Bericht gegenlesen.",
            "quelle_datei": "",
            # Hält den Bericht NICHT auf. Gescannte Firmenberichte sind der
            # Normalfall, nicht die Ausnahme; jeden davon von Hand freizugeben
            # hieße, fünf Mal pro Woche denselben Knopf zu drücken. Der Hinweis
            # bleibt am Bericht stehen, das Dokument entsteht trotzdem.
            "blockiert": False,
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

    if _haelt_auf(warnungen):
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
        await _send_teams(db, einreichung, projekt)
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
        await _send_teams(db, einreichung, projekt)
    except Exception as exc:
        einreichung.status = "fehlgeschlagen"
        db.commit()
        _log_step(db, einreichung_id, "docx_erzeugung_nach_bestaetigung", "fehler", str(exc))
