"""Von den hochgeladenen Blättern zum fertigen Bautagesbericht.

DIE BEIDEN WEGE
===============
Es gibt zwei Einstiege, und das ist der Grund für den Aufbau dieses Moduls:

* ``process_einreichung`` — der Normalfall, direkt nach dem Hochladen.
* ``confirm_and_generate`` — nachdem jemand die Warnungen gesehen und
  bestätigt hat.

Beide brauchen dasselbe: Wetter holen, Blätter auslesen, Firmennamen
zusammenführen, Word erzeugen. Genau deshalb steht das hier **einmal**
(``_wetter_sammeln``, ``_firmen_sammeln``, ``_eintraege_bauen``) und nicht
zweimal. Vorher war es zweimal, und die beiden Fassungen waren
auseinandergelaufen: Der Bestätigungsweg las die Blätter ohne die Firmen der
Baustelle und ohne das Zusammenführen der Schreibweisen, und er merkte sich
die Firmen des fertigen Berichts nicht. Wer also einen Bericht von Hand
freigab — also gerade den zweifelhaften Fall —, bekam das schlechtere
Ergebnis von beiden.
"""

import time
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Einreichung, Projekt, VerarbeitungsLog
from app.schemas import BautagesberichtJSON, FirmaEintrag, WetterBlock, WarnungSchema
from app.services import firmennamen
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


# ─────────────────────────────────────────────────────────────────────────────
# Die Schritte, die sich beide Wege teilen
# ─────────────────────────────────────────────────────────────────────────────


async def _wetter_sammeln(db: Session, einreichung, projekt,
                          warnungen: list[dict]) -> dict | None:
    """Tageswetter zum Projektstandort. ``None``, wenn es keines gibt."""
    t0 = time.time()
    try:
        if not (projekt and projekt.lat and projekt.lon):
            _log_step(db, einreichung.id, "wetterdaten", "warnung",
                      "Projekt hat keine Koordinaten")
            warnungen.append({
                "feld": "wetter",
                "problem": "Projekt hat keine Koordinaten — kein Wetterdaten-Abruf möglich",
                "quelle_datei": "",
            })
            return None

        wetter = await fetch_weather(
            projekt.lat, projekt.lon, einreichung.datum.isoformat())
        if wetter:
            _log_step(db, einreichung.id, "wetterdaten", "erfolg",
                      f"Station: {wetter.get('station', '?')}",
                      int((time.time() - t0) * 1000))
            return wetter

        _log_step(db, einreichung.id, "wetterdaten", "warnung",
                  "Keine Wetterdaten verfügbar", int((time.time() - t0) * 1000))
        warnungen.append({
            "feld": "wetter",
            "problem": "Keine Wetterdaten von Bright Sky erhalten",
            "quelle_datei": "",
        })
        return None
    except Exception as exc:
        _log_step(db, einreichung.id, "wetterdaten", "fehler", str(exc),
                  int((time.time() - t0) * 1000))
        warnungen.append({
            "feld": "wetter",
            "problem": f"Fehler beim Abruf: {exc}",
            "quelle_datei": "",
        })
        return None


async def _firmen_sammeln(db: Session, einreichung,
                          warnungen: list[dict]) -> list[dict]:
    """Liest alle Quelldateien der Einreichung aus und räumt die Namen auf.

    Welche Firmen auf dieser Baustelle arbeiten, ist die stärkste Hilfe für
    die Erkennung eines handschriftlichen Namens — aus "Riedd Bau" wird damit
    "Riedel Bau" statt einer vierten Schreibweise.
    """
    bekannte = firmennamen.bekannte_firmen(db, einreichung.projekt_id)
    alle: list[dict] = []

    for datei_rel in (einreichung.quelle_dateien or []):
        pfad = settings.upload_dir.parent / datei_rel
        if not pfad.exists():
            warnungen.append({
                "feld": "dateien",
                "problem": f"Datei nicht gefunden: {datei_rel}",
                "quelle_datei": datei_rel,
            })
            continue

        t0 = time.time()
        try:
            firmen = await extract_from_file(pfad, einreichung.datum, bekannte)
            alle.extend(firmen)
            _log_step(db, einreichung.id, "pdf_extraktion", "erfolg",
                      f"{len(firmen)} Firmen aus {pfad.name}",
                      int((time.time() - t0) * 1000))
        except Exception as exc:
            _log_step(db, einreichung.id, "pdf_extraktion", "fehler",
                      f"{pfad.name}: {exc}", int((time.time() - t0) * 1000))
            warnungen.append({
                "feld": "dateien",
                "problem": f"Extraktion fehlgeschlagen: {exc}",
                "quelle_datei": datei_rel,
            })

    if not alle:
        warnungen.append({
            "feld": "firmen",
            "problem": "Keine Firmendaten extrahiert",
            "quelle_datei": "",
        })
        return alle

    _namen_pruefen(alle, bekannte, warnungen)
    return alle


def _namen_pruefen(alle: list[dict], bekannte: tuple[str, ...],
                   warnungen: list[dict]) -> None:
    """Schreibweisen zusammenführen und melden, was nachzusehen ist."""
    # Platzhalter erkennen (Scan ohne Schlüssel, unbekanntes Format, Störung
    # der Schnittstelle). Der Grund steht am Eintrag unter "hinweis" — er
    # gehört hierhin und nicht in das Feld "Leistung" des Berichts, in dem
    # vorher die halbe Bedienungsanleitung stand (siehe
    # pdf_extraction.platzhalter).
    gesehen: set[str] = set()
    for eintrag in alle:
        name = str(eintrag.get("firma", ""))
        if not name.startswith("("):
            continue
        grund = str(eintrag.get("hinweis") or "").strip()
        problem = grund or f"Automatische Extraktion unvollständig: {name}"
        if problem in gesehen:
            # Ein Wochenpaket mit fünf unlesbaren Blättern soll nicht fünf
            # Mal denselben Satz an den Bericht hängen.
            continue
        gesehen.add(problem)
        warnungen.append({
            "feld": "firmen",
            "problem": problem,
            "quelle_datei": str(eintrag.get("quelle_datei") or ""),
        })

    # OCR-gelesene Einträge (aus Scans) immer zur manuellen Kontrolle melden.
    if any(e.get("quelle") == "ocr" for e in alle):
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

    # Auf Seite 1 steht "Riedd Bau", auf Seite 2 "Riedel Bau" — im Bericht darf
    # daraus nicht zweimal dieselbe Firma werden. Was sich nicht sicher
    # zuordnen lässt, bleibt stehen und wird als Warnung gemeldet, statt
    # geraten zu werden (siehe services/firmennamen).
    zuordnung, namenswarnungen = firmennamen.vereinheitliche(
        [str(e.get("firma", "")) for e in alle], list(bekannte)
    )
    for eintrag in alle:
        neuer = zuordnung.get(str(eintrag.get("firma", "")), "")
        if neuer:
            eintrag["firma"] = neuer
    for text in namenswarnungen:
        warnungen.append({
            "feld": "firmen",
            "problem": text,
            "quelle_datei": "",
            # Hält den Bericht nicht auf: Der Name steht drin, wie er
            # gelesen wurde, er sollte nur gegengelesen werden.
            "blockiert": False,
        })

    # Nur ein Kürzel gelesen? Auf manchen Formblättern steht der volle
    # Firmenname bloß im Logo, und ein Logo ist ein Bild — die Texterkennung
    # sieht dort nichts. Im Bericht an den Bauherrn steht dann "Firma: RF".
    # Das lässt sich nicht erraten, aber es lässt sich sagen: Wer die Firma
    # einmal beim Projekt hinterlegt, bekommt ab dann den vollen Namen.
    for eintrag in alle:
        name = str(eintrag.get("firma", "")).strip()
        if not name or name.startswith("("):
            continue
        if len(name) <= 3 and not any(
            firmennamen.normalisiere(name) == firmennamen.normalisiere(b)
            for b in bekannte
        ):
            warnungen.append({
                "feld": "firmen",
                "problem": (
                    f"Vom Firmennamen war nur das Kürzel „{name}“ zu lesen "
                    "— der volle Name steht auf diesem Formblatt "
                    "vermutlich nur im Logo. Einmal unter Stammdaten → "
                    "Firmen/Gewerke hinterlegen, dann steht er ab dem "
                    "nächsten Bericht vollständig da."
                ),
                "quelle_datei": "",
                "blockiert": False,
            })


def _eintraege_bauen(alle: list[dict],
                     warnungen: list[dict]) -> list[FirmaEintrag]:
    """Aus den gelesenen Angaben geprüfte Firmeneinträge machen."""
    eintraege: list[FirmaEintrag] = []
    for i, roh in enumerate(alle):
        try:
            personen = int(roh.get("personen", 0))
        except (ValueError, TypeError):
            warnungen.append({
                "feld": f"firmen[{i}].personen",
                "problem": f"'{roh.get('personen')}' ist keine Zahl — auf 0 gesetzt",
                "quelle_datei": "",
            })
            personen = 0

        eintraege.append(FirmaEintrag(
            firma=str(roh.get("firma", "")),
            ort=str(roh.get("ort", "")),
            personen=personen,
            leistung=str(roh.get("leistung", "")),
            besonderes=roh.get("besonderes"),
        ))
    return eintraege


def _tagesnotizen(alle: list[dict]) -> list[str]:
    """Was auf den Blättern unter "Sonstiges" und "Besuche" stand.

    Frost, mit Folie abgehängte Wände, angelieferte Bauheizungen — Angaben,
    die den ganzen Tag betreffen und keiner Firma zuzuordnen sind. Im
    HPP-Bericht gehören sie in das Notizfeld über den Firmenblöcken.

    Bis hierher gingen sie verloren: Die Erkennung liest sie (siehe
    services/seitenlesung), aber der Haupteintrag kam allein aus dem Textfeld
    der Oberfläche. Ein zweimal geprüfter Satz über den Frost am Morgen
    landete also im Papierkorb.

    Doppelte fallen weg: Bei einem Blatt mit drei Nachunternehmern hängt die
    Notiz an allen drei Einträgen.
    """
    gesehen: list[str] = []
    for eintrag in alle:
        notiz = str(eintrag.get("tagesnotiz") or "").strip()
        if notiz and notiz not in gesehen:
            gesehen.append(notiz)
    return gesehen


def _bericht_bauen(einreichung, projekt, wetter: dict | None,
                   eintraege: list[FirmaEintrag],
                   warnungen: list[dict],
                   notizen: list[str] | None = None) -> BautagesberichtJSON:
    # Was jemand von Hand eingetragen hat, steht oben — es ist die Aussage
    # des Bauleiters. Darunter, was von den Blättern kam.
    zeilen = [einreichung.ergaenzende_angaben or ""] + list(notizen or [])
    haupteintrag = "\n".join(z for z in zeilen if z.strip())

    return BautagesberichtJSON(
        projekt=projekt.name if projekt else "",
        datum=einreichung.datum,
        haupteintrag=haupteintrag,
        wetter=WetterBlock(**wetter) if wetter else None,
        firmen=eintraege,
        unterschrift_datum=einreichung.datum,
        warnungen=[WarnungSchema(**w) for w in warnungen],
    )


async def _dokument_erzeugen(db: Session, einreichung, projekt,
                             bericht: BautagesberichtJSON,
                             eintraege: list[FirmaEintrag],
                             schritt: str) -> None:
    """Word erzeugen, Status setzen, Firmen merken, Teams benachrichtigen."""
    t0 = time.time()
    try:
        # Die Kennung der Einreichung gehört in den Dateinamen: Zwei Berichte
        # für denselben Tag desselben Projekts — etwa ein Nachtrag — schrieben
        # sich sonst gegenseitig über, und der Download des älteren lieferte
        # danach den Inhalt des neueren.
        ausgabe = generate_bautagesbericht(bericht, kennung=str(einreichung.id))
        einreichung.ergebnis_dokument_pfad = str(
            ausgabe.relative_to(settings.output_dir.parent))
        einreichung.status = "abgeschlossen"
        einreichung.verarbeitet_am = datetime.now()
        db.commit()

        # Erst jetzt merken, welche Firmen auf dieser Baustelle vorkommen:
        # Das Dokument ist entstanden, jemand hat das Ergebnis vor sich. Was
        # die Erkennung nur vorgeschlagen hat, gehört nicht in den Bestand —
        # sonst richtet sich die nächste Erkennung auf einen Lesefehler aus.
        try:
            firmennamen.merke_firmen(
                db, einreichung.projekt_id,
                [e.firma for e in eintraege if e.firma],
            )
        except Exception:
            # Das Gedächtnis ist Beiwerk; ein fertiger Bericht darf daran
            # nicht scheitern.
            db.rollback()

        _log_step(db, einreichung.id, schritt, "erfolg",
                  f"Datei: {ausgabe.name}", int((time.time() - t0) * 1000))
        await _send_teams(db, einreichung, projekt)
    except Exception as exc:
        einreichung.status = "fehlgeschlagen"
        # Den Grund an den Bericht hängen, nicht nur ins Protokoll.
        #
        # Vorher stand in der Übersicht eine rote Plakette "fehlgeschlagen"
        # und sonst nichts: Der Grund lag im Verarbeitungsprotokoll, das die
        # Oberfläche nicht abruft. Für den Anwender war das eine Sackgasse —
        # er konnte nur alles noch einmal hochladen, ohne zu wissen, ob das
        # etwas ändert.
        warnungen = list(einreichung.warnungen or [])
        problem = (
            f"Das Word-Dokument konnte nicht erzeugt werden: {exc}. "
            "Über „Erneut versuchen“ läuft die Verarbeitung noch einmal — "
            "die hochgeladenen Dateien liegen weiterhin da."
        )
        if not any(w.get("feld") == "dokument" for w in warnungen):
            warnungen.append({
                "feld": "dokument",
                "problem": problem,
                "quelle_datei": "",
            })
        einreichung.warnungen = warnungen
        db.commit()
        _log_step(db, einreichung.id, schritt, "fehler", str(exc),
                  int((time.time() - t0) * 1000))


# ─────────────────────────────────────────────────────────────────────────────
# Die beiden Einstiege
# ─────────────────────────────────────────────────────────────────────────────


async def process_einreichung(einreichung_id: int, db: Session):
    einreichung = db.get(Einreichung, einreichung_id)
    if not einreichung:
        return

    einreichung.status = "wird_verarbeitet"
    db.commit()

    projekt = db.get(Projekt, einreichung.projekt_id)
    warnungen: list[dict] = []

    wetter = await _wetter_sammeln(db, einreichung, projekt, warnungen)
    alle = await _firmen_sammeln(db, einreichung, warnungen)
    eintraege = _eintraege_bauen(alle, warnungen)
    bericht = _bericht_bauen(einreichung, projekt, wetter, eintraege,
                             warnungen, _tagesnotizen(alle))

    einreichung.warnungen = warnungen

    if _haelt_auf(warnungen):
        einreichung.status = "wartet_auf_bestaetigung"
        db.commit()
        _log_step(db, einreichung_id, "validierung", "warnung",
                  f"{len(warnungen)} Warnungen")
        return

    await _dokument_erzeugen(db, einreichung, projekt, bericht, eintraege,
                             "docx_erzeugung")


async def confirm_and_generate(einreichung_id: int, db: Session):
    """Nach der Freigabe durch einen Menschen: Bericht trotz Warnungen bauen.

    Gelesen wird auf demselben Weg wie im Normalfall — mit den Firmen der
    Baustelle und mit dem Zusammenführen der Schreibweisen. Die Warnungen
    bleiben am Bericht stehen; sie sind ja gesehen und abgenickt worden.
    """
    einreichung = db.get(Einreichung, einreichung_id)
    if not einreichung:
        return
    # "fehlgeschlagen" gehört dazu: Über denselben Weg läuft der zweite
    # Versuch nach einem Fehler. Die Dateien liegen ja noch, und der Grund
    # war oft vorübergehend (Schnittstelle überlastet, Netz kurz weg).
    if einreichung.status not in ("wartet_auf_bestaetigung",
                                  "wird_verarbeitet", "fehlgeschlagen"):
        return

    projekt = db.get(Projekt, einreichung.projekt_id)
    warnungen: list[dict] = []

    # Die Meldung des letzten Fehlversuchs gehört weg, bevor es neu losgeht —
    # sonst klebt "konnte nicht erzeugt werden" am gelungenen Bericht.
    einreichung.warnungen = [w for w in (einreichung.warnungen or [])
                             if w.get("feld") != "dokument"]

    wetter = await _wetter_sammeln(db, einreichung, projekt, warnungen)
    alle = await _firmen_sammeln(db, einreichung, warnungen)
    eintraege = _eintraege_bauen(alle, warnungen)

    # Die alten Warnungen bleiben stehen und die neuen kommen dazu, sofern sie
    # nicht dasselbe sagen: Wer den Bericht später ansieht, soll noch erkennen
    # können, was bei der Freigabe zur Debatte stand.
    bestehend = list(einreichung.warnungen or [])
    gesehen = {(w.get("feld"), w.get("problem")) for w in bestehend}
    for warnung in warnungen:
        if (warnung.get("feld"), warnung.get("problem")) not in gesehen:
            bestehend.append(warnung)
    einreichung.warnungen = bestehend

    bericht = _bericht_bauen(einreichung, projekt, wetter, eintraege,
                             bestehend, _tagesnotizen(alle))
    await _dokument_erzeugen(db, einreichung, projekt, bericht, eintraege,
                             "docx_erzeugung_nach_bestaetigung")
