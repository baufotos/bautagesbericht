"""Extraktion von Firmen-/Leistungsdaten aus Unternehmens-Bautagesberichten.

Drei Formate werden erkannt:
1. Lindner-Format (strukturierte Tabellen mit Firma-Index)
2. Einfach-Format ("Fa. X (N Mann)" mit Aufzählung, ein Tag pro Seite)
3. Scans ohne Textlayer  -> Claude Vision (falls API-Key vorhanden)
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pdfplumber

from app.config import settings

#: Modell für das Auslesen eingescannter Bautagesberichte.
#:
#: Modellkennungen laufen ab: Die vorige Fassung (``claude-sonnet-4-20250514``)
#: gibt es nicht mehr, der Zweig wäre beim ersten eingetragenen Schlüssel in
#: einen Fehler gelaufen. Deshalb steht sie hier an EINER Stelle — beim
#: nächsten Wechsel ist nur diese Zeile zu ändern.
CLAUDE_MODELL = "claude-opus-5"


# ---------------------------------------------------------------------------
# Basisfunktionen
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_path: Path) -> str:
    parts: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n\n".join(parts)


def has_text_layer(file_path: Path) -> bool:
    try:
        return len(extract_text_from_pdf(file_path).strip()) > 50
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Format-Erkennung
# ---------------------------------------------------------------------------

_LINDNER_MARKERS = (
    "Baustellentagesbericht",
    "Nachunternehmer/Montagepartner",
    "Firma Personen /Trupp",
)

_SIMPLE_DAY_PATTERN = re.compile(r"^\s*Fa\.\s+.+?\(\s*\d+\s*Mann\s*\)", re.MULTILINE)
_DATE_PATTERN = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _has_real_key() -> bool:
    """Nur ein echt aussehender Anthropic-Key aktiviert den Claude-Pfad."""
    key = (settings.anthropic_api_key or "").strip()
    return key.startswith("sk-ant-")


def _detect_format(text: str) -> str:
    if any(m in text for m in _LINDNER_MARKERS):
        return "lindner"
    if _SIMPLE_DAY_PATTERN.search(text):
        return "simple"
    return "unknown"


# ---------------------------------------------------------------------------
# Format 1: Lindner
# ---------------------------------------------------------------------------

def _parse_lindner(pdf) -> list[dict]:
    """Verknüpft die Firma-Tabelle mit der Arbeiten-Tabelle über den Index."""
    firmen_map: dict[str, dict] = {}

    for page in pdf.pages:
        tables = page.extract_tables()
        if not tables:
            continue

        # Tabelle 0: Firma, Personen /Trupp, Gewerk       (Header)
        # Tabelle 1: Anz. Pers., Uhrzeit von, Uhrzeit bis
        # Tabelle 3: Firma, Beschreibung, Bauteil, Etage, Raum, Achse
        firma_rows: list[dict] = []
        arbeit_rows: list[dict] = []
        behinderung_rows: list[dict] = []

        for t in tables:
            if not t or not t[0]:
                continue
            header = [str(c or "").strip() for c in t[0]]

            if "Firma" in header and any("Gewerk" in c for c in header):
                # Firma-Kopftabelle
                for row in t[1:]:
                    if not row or not row[0]:
                        continue
                    idx = str(row[0]).strip()
                    name = str(row[1] or "").strip() if len(row) > 1 else ""
                    gewerk = str(row[-1] or "").strip() if len(row) > 1 else ""
                    if idx and name:
                        firma_rows.append({"idx": idx, "name": name, "gewerk": gewerk})

            elif "Anz. Pers." in header and "Uhrzeit von" in header:
                # Personen-Tabelle: gleiche Reihenfolge wie Firma-Tabelle
                for i, row in enumerate(t[1:]):
                    if not row:
                        continue
                    try:
                        anz = int(str(row[0] or "0").strip() or "0")
                    except ValueError:
                        anz = 0
                    if i < len(firma_rows):
                        firma_rows[i]["personen"] = anz

            elif "Art" in header and "Beschreibung" in header:
                # Behinderungs-/Unterbrechungstabelle (Firma, Art, Beschreibung, ...)
                b_art = header.index("Art")
                b_besch = header.index("Beschreibung")
                for row in t[1:]:
                    if not row or not row[0]:
                        continue
                    firma_idx = str(row[0]).strip()
                    art = str(row[b_art] or "").strip().replace("\n", " ") if len(row) > b_art else ""
                    besch = str(row[b_besch] or "").strip().replace("\n", " ") if len(row) > b_besch else ""
                    text = " — ".join(x for x in (art, besch) if x)
                    if text:
                        behinderung_rows.append({"idx": firma_idx, "text": text})

            elif "Firma" in header and "Beschreibung" in header:
                # Arbeiten-Tabelle (Firma, Beschreibung, Bauteil, Etage, Raum, Achse)
                for row in t[1:]:
                    if not row or not row[0]:
                        continue
                    firma_idx = str(row[0]).strip()
                    beschreibung = str(row[1] or "").strip().replace("\n", " ")
                    etage = str(row[3] or "").strip() if len(row) > 3 else ""
                    raum = str(row[4] or "").strip().replace("\n", " ") if len(row) > 4 else ""
                    achse = str(row[5] or "").strip() if len(row) > 5 else ""
                    ort_parts = [x for x in (etage, raum, achse) if x]
                    if beschreibung:
                        arbeit_rows.append({
                            "idx": firma_idx,
                            "beschreibung": beschreibung,
                            "ort": " / ".join(ort_parts),
                        })

        # Firmen registrieren
        for f in firma_rows:
            key = f["name"]
            if key not in firmen_map:
                firmen_map[key] = {
                    "idx": f["idx"],
                    "firma": f["name"],
                    "personen": f.get("personen", 0),
                    "ort": "",
                    "leistungen": [],
                    "behinderungen": [],
                    "gewerk": f.get("gewerk", ""),
                }

        # Arbeiten zuordnen
        for a in arbeit_rows:
            for f in firmen_map.values():
                if f["idx"] == a["idx"]:
                    if a["ort"] and not f["ort"]:
                        f["ort"] = a["ort"]
                    f["leistungen"].append(a["beschreibung"])
                    break

        # Behinderungen zuordnen
        for b in behinderung_rows:
            for f in firmen_map.values():
                if f["idx"] == b["idx"]:
                    f["behinderungen"].append(b["text"])
                    break

    # In Zielschema konvertieren
    result: list[dict] = []
    for f in firmen_map.values():
        leistung = " · ".join(f["leistungen"]) if f["leistungen"] else f.get("gewerk", "")
        besonderes = " · ".join(f["behinderungen"]) if f["behinderungen"] else None
        result.append({
            "firma": f["firma"],
            "ort": f["ort"],
            "personen": f["personen"],
            "leistung": leistung,
            "besonderes": besonderes,
        })
    return result


# ---------------------------------------------------------------------------
# Format 2: Einfach-Tageseintrag ("Fa. X (N Mann)" + Aufzählung)
# ---------------------------------------------------------------------------

_FA_LINE = re.compile(r"^Fa\.\s+(?P<firma>.+?)\s*\(\s*(?P<personen>\d+)\s*Mann\s*\)\s*$")
_BULLET_LINE = re.compile(r"^\s*[-•]\s+(?P<txt>.+)$")


def _parse_simple_page(text: str, target_date: date | None) -> list[dict]:
    """Extrahiert Firmen-Einträge einer einzelnen Tagesseite."""
    lines = [l.rstrip() for l in text.splitlines()]

    # Optional: Datum in der Seite prüfen, damit wir das richtige Blatt nehmen
    if target_date is not None:
        page_date = _find_date_in_lines(lines)
        if page_date and page_date != target_date:
            return []

    firmen: list[dict] = []
    current: dict | None = None

    for line in lines:
        m = _FA_LINE.match(line.strip())
        if m:
            if current:
                firmen.append(_finalize_simple(current))
            current = {
                "firma": m.group("firma").strip(),
                "personen": int(m.group("personen")),
                "leistungen": [],
            }
            continue

        b = _BULLET_LINE.match(line)
        if b and current:
            current["leistungen"].append(b.group("txt").strip())

    if current:
        firmen.append(_finalize_simple(current))
    return firmen


def _finalize_simple(entry: dict) -> dict:
    return {
        "firma": entry["firma"],
        "ort": "",
        "personen": entry["personen"],
        "leistung": " · ".join(entry["leistungen"]),
        "besonderes": None,
    }


def _find_date_in_lines(lines: list[str]) -> date | None:
    for l in lines[:5]:
        m = _DATE_PATTERN.search(l)
        if m:
            try:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                continue
    return None


def _parse_simple_all_pages(pdf, target_date: date | None) -> list[dict]:
    """Wochenpaket: eine Tagesseite pro Bericht. Wir nehmen die passende Seite."""
    all_matches: list[dict] = []
    for page in pdf.pages:
        text = page.extract_text() or ""
        firmen = _parse_simple_page(text, target_date)
        all_matches.extend(firmen)

    # Wenn kein Zieldatum angegeben: alle Seiten aggregieren
    if not all_matches and target_date is None:
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_matches.extend(_parse_simple_page(text, None))

    # Duplikate zusammenfassen (gleiche Firma an gleichem Tag)
    dedup: dict[str, dict] = {}
    for f in all_matches:
        key = f["firma"]
        if key not in dedup:
            dedup[key] = f
        else:
            # Personen: Maximum, Leistung: zusammenfügen
            dedup[key]["personen"] = max(dedup[key]["personen"], f["personen"])
            if f["leistung"] and f["leistung"] not in dedup[key]["leistung"]:
                dedup[key]["leistung"] = (
                    dedup[key]["leistung"] + " · " + f["leistung"]
                    if dedup[key]["leistung"] else f["leistung"]
                )
    return list(dedup.values())


# ---------------------------------------------------------------------------
# Format 3a: Scan-Fallback via lokales OCR (kein API-Key)
# ---------------------------------------------------------------------------

_PERSONEN_PATTERNS = [
    re.compile(r"Arbeiter[:\s]+(\d{1,3})", re.IGNORECASE),
    re.compile(r"\(\s*(\d{1,3})\s*Mann\s*\)", re.IGNORECASE),
    re.compile(r"(\d{1,3})\s*Mitarbeiter", re.IGNORECASE),
    re.compile(r"(\d{1,3})\s*Mann", re.IGNORECASE),
]

# Überschriften, ab denen der Leistungstext beginnt bzw. endet.
# "Leistung\w*" schluckt die ganze Überschrift (auch OCR-Varianten wie
# "Leistungserqebnisse"), damit der Text nicht mitten im Wort beginnt.
_LEISTUNG_START = re.compile(
    r"(Ausgef[üu]hrte Arbeiten|Leistung\w*)", re.IGNORECASE
)
_LEISTUNG_END = re.compile(
    r"(Bemerkung|Unterschrift|Besuche|Sonstiges|erstellt|Rev\.)", re.IGNORECASE
)


def _guess_personen(text: str) -> int:
    for pat in _PERSONEN_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return 0


def _guess_leistung(text: str) -> str:
    m = _LEISTUNG_START.search(text)
    if not m:
        # Keine bekannte Überschrift: gesamten Text (begrenzt) verwenden.
        cleaned = " ".join(text.split())
        return cleaned[:1500]
    start = m.end()
    rest = text[start:]
    end_m = _LEISTUNG_END.search(rest)
    section = rest[: end_m.start()] if end_m else rest
    cleaned = " ".join(section.split()).lstrip(":;-–—. \t")
    return cleaned[:1500] or " ".join(text.split())[:1500]


def _ocr_review_entry(text: str) -> dict:
    """Baut aus rohem OCR-Text einen Best-Effort-Eintrag zur manuellen Kontrolle."""
    return {
        "firma": "Nachunternehmer (Scan)",
        "ort": "",
        "personen": _guess_personen(text),
        "leistung": _guess_leistung(text),
        "besonderes": "Automatisch per OCR aus einem Scan gelesen — bitte Angaben prüfen.",
        "quelle": "ocr",
    }


# ---------------------------------------------------------------------------
# Format 4: Formblatt (gedrucktes Firmenformular, meist als Scan)
#
# Die Nachunternehmer schicken ihre Berichte auf eigenen Formblättern: ein
# Kopf mit Kommission und Datum, eine Zeile mit der Zahl der Arbeiter, ein
# Block "Leistungsergebnisse". Solche Blätter kommen fast immer als Scan, also
# ohne Textebene — der Text hier stammt daher meist aus der Texterkennung und
# ist entsprechend fehlerbehaftet ("4.OG" wird zu "406", "Leistungsergebnisse"
# zu "Leistungserqebnisse"). Die Muster unten sind bewusst großzügig.
# ---------------------------------------------------------------------------

_ARBEITER_MUSTER = [
    re.compile(r"Anzahl\s+der\s+Besch\w*\s+Arbeiter[:\s]*(\d{1,3})", re.IGNORECASE),
    re.compile(r"Anzahl\s+\w*\s*Arbeiter[:\s]*(\d{1,3})", re.IGNORECASE),
    re.compile(r"^\s*(\d{1,3})\s+Mitarbeiter\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\b(\d{1,3})\s*Mann\b", re.IGNORECASE),
    re.compile(r"Arbeiter[:\s]+(\d{1,3})", re.IGNORECASE),
]

#: Ab hier beginnt der Leistungstext. "\w*" fängt die OCR-Verhunzungen mit.
_LEISTUNG_AB = re.compile(
    r"^\s*(Leistungs\w*|Ausgef\w*\s+Arbeiten|T\w*tigkeiten|Arbeiten)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

#: Und hier hört er auf.
_LEISTUNG_BIS = re.compile(
    r"^\s*(Bemerkung\w*|Besonder\w*|Unterschrift\w*|Behinderung\w*)\s*:?\s*",
    re.IGNORECASE | re.MULTILINE,
)

_ORT_MUSTER = re.compile(
    r"^\s*(?:Abschnitt|Bauteil|Bereich|Bauabschnitt)\s*[:.\-]?\s*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)

#: Rechtsformen verraten einen Firmennamen zuverlässiger als jede Position.
_RECHTSFORM = re.compile(
    r"^(.{2,60}?\b(?:GmbH(?:\s*&\s*Co\.?\s*KG)?|AG|KG|OHG|GbR|e\.?\s?K\.?|"
    r"Bau\s?GmbH|SE)\b.{0,20})$",
    re.IGNORECASE | re.MULTILINE,
)

#: "Unterschrift RF" — auf vielen Formblättern steht das Firmenkürzel neben der
#: Unterschriftszeile. "Bauherr" und "Stellvertreter" gehören dort nicht hin.
#: Das eingestreute "\s*" fängt Erkennungsfehler wie "Uh erschrift RF".
_UNTERSCHRIFT_FIRMA = re.compile(
    r"^\s*U\w*\s?\w*schrift\s+(?!Bauherr|Stellv|Auftrag)"
    r"([A-ZÄÖÜ][\wÄÖÜäöüß&.\- ]{1,30}?)\s*$",
    re.MULTILINE,
)

#: Zeilen, die zum Formularrahmen gehören und nie Leistungstext sind. Wird
#: gebraucht, weil die Überschrift "Leistungsergebnisse" auf gescannten
#: Blättern regelmäßig verlorengeht — dann muss der Text über das erkannt
#: werden, was er NICHT ist.
_FORMULARZEILE = re.compile(
    r"^\s*(name|vorarb|monteur|uhr|arbeitszeit|von|bis|witterung|sonne|regen|"
    r"frost|wind|schnee|sonstiges|temperatur|bew\w*lkt|bemerkung|"
    r"u\w*\s?\w*schrift|formblatt|bautagesbericht|ident|kommission|"
    r"bauvorhaben|abschnitt|datum|verantwortlich\w*|anzahl|seite|rev\b|"
    r"erstellt|fassaden|leistungs\w*\s*:?\s*$)",
    re.IGNORECASE,
)

#: Ab hier ist der Bericht zu Ende.
_FORMBLATT_ENDE = re.compile(
    r"^\s*(bemerkung|u\w*\s?\w*schrift)", re.IGNORECASE)

#: Woran ein Blatt als Bautagesbericht zu erkennen ist. "\w*" fängt die
#: Verhunzungen der Texterkennung mit ("Leistungserqebnisse").
_IST_BAUTAGESBERICHT = re.compile(
    r"(bautage\w*bericht|bautagebuch|tagesbericht|tagesrapport|"
    r"leistungs\w*ergebnis|leistungserq\w*|arbeitsbericht|"
    r"anzahl\s+der\s+besch\w*|verantwortlicher\s+bauleiter)",
    re.IGNORECASE,
)

#: Letzte Zeile des Kopfbereichs. Alles davor ist Formularrahmen — Kommission,
#: Bauvorhaben, Abschnitt, Witterung, Mitarbeitertabelle. Erst danach beginnt,
#: was jemand über den Tag geschrieben hat. Ohne diesen Anker rutschen
#: "Bauvorhaben" und "Abschnitt" in den Leistungstext, weil ihre Beschriftung
#: auf gescannten Blättern in einer eigenen Zeile steht.
_KOPF_ENDE = re.compile(
    r"^\s*(monteur|vorarb\w*|\d*\s*mitarbeiter|uhr\b|arbeitszeit|"
    r"anzahl\s+der\s+besch\w*|verantwortlich\w*|bew\w*lkt|sonstiges)",
    re.IGNORECASE,
)


def _formblatt_firma(text: str, ersatz: str) -> str:
    for treffer in _RECHTSFORM.finditer(text):
        name = treffer.group(1).strip(" .:-")
        if name and not name.lower().startswith(("bauvorhaben", "bauherr")):
            return name
    treffer = _UNTERSCHRIFT_FIRMA.search(text)
    if treffer:
        return treffer.group(1).strip(" .:-")
    return ersatz


def _formblatt_leistung(text: str) -> str:
    """Der Leistungstext eines Formblatts.

    Erster Versuch über die Überschrift. Fehlt sie — was bei gescannten
    Blättern der Normalfall ist, weil die Erkennung sie verschluckt —, wird
    umgekehrt vorgegangen: alles vor "Bemerkungen"/"Unterschrift" nehmen und
    davon abziehen, was erkennbar zum Formularrahmen gehört. Übrig bleiben die
    Sätze, die jemand eingetragen hat.
    """
    zeilen = [z.strip() for z in text.splitlines()]

    start = _LEISTUNG_AB.search(text)
    if start:
        rest = text[start.end():]
        ende = _LEISTUNG_BIS.search(rest)
        block = rest[: ende.start()] if ende else rest
        gesammelt = [z.strip() for z in block.splitlines() if z.strip()]
        if gesammelt:
            return " · ".join(gesammelt)

    ende_index = len(zeilen)
    for i, zeile in enumerate(zeilen):
        if _FORMBLATT_ENDE.match(zeile):
            ende_index = i
            break

    start_index = 0
    for i, zeile in enumerate(zeilen[:ende_index]):
        if _KOPF_ENDE.match(zeile):
            start_index = i + 1

    gesammelt = []
    for zeile in zeilen[start_index:ende_index]:
        if not zeile or _FORMULARZEILE.match(zeile):
            continue
        # Zahlen, Kürzel und Einzelwörter sind Tabellenzellen, keine Sätze.
        if len(zeile) < 15 or len(zeile.split()) < 3:
            continue
        gesammelt.append(zeile)

    return " · ".join(gesammelt)


def parse_formblatt(text: str, quelle: str = "") -> list[dict]:
    """Liest ein gedrucktes Firmen-Formblatt aus.

    Gibt höchstens einen Eintrag zurück — ein Formblatt gehört zu einer Firma
    und einem Tag. Ohne Leistungstext und ohne Personenzahl wird nichts
    zurückgegeben: Dann ist das Blatt entweder kein Bautagesbericht oder die
    Texterkennung hat zu wenig herausgeholt, und ein leerer Eintrag wäre
    schlimmer als keiner.
    """
    leistung = _formblatt_leistung(text)

    personen = 0
    for muster in _ARBEITER_MUSTER:
        treffer = muster.search(text)
        if treffer:
            try:
                personen = int(treffer.group(1))
            except (TypeError, ValueError):
                personen = 0
            if personen:
                break

    # Ohne Personenzahl braucht es wenigstens ein Merkmal, das dieses Blatt
    # als Bautagesbericht ausweist. Sonst würde jede Rechnung und jedes
    # Anschreiben, das im Ordner liegt, als Tagesbericht durchgehen — mit
    # ihrem Fließtext als "Leistung".
    if not personen and not _IST_BAUTAGESBERICHT.search(text):
        return []
    if not leistung and not personen:
        return []

    ort = ""
    treffer = _ORT_MUSTER.search(text)
    if treffer:
        ort = treffer.group(1).strip(" .:-")
        if not ort:
            # Auf gescannten Formblättern steht der Wert oft in der Zeile
            # NACH der Beschriftung, weil die Erkennung Spalten trennt.
            zeilen = text.splitlines()
            for i, zeile in enumerate(zeilen[:-1]):
                if re.match(r"^\s*(Abschnitt|Bauteil|Bereich)", zeile, re.IGNORECASE):
                    ort = zeilen[i + 1].strip(" .:-")
                    break

    return [{
        "firma": _formblatt_firma(text, quelle or "Firma bitte ergänzen"),
        "ort": ort,
        "personen": personen,
        "leistung": leistung or "Leistungstext nicht lesbar — bitte ergänzen",
        "besonderes": None,
        "quelle": "ocr",
    }]


async def _extract_scan_no_key(file_path: Path) -> list[dict]:
    """Scan ohne Anthropic-Schlüssel: Windows-Texterkennung versuchen.

    Windows bringt seit Windows 10 eine eigene Texterkennung mit. Bei
    gedruckten Formblättern — und das sind die Berichte der Nachunternehmer —
    liest sie zuverlässig genug, um Datum, Arbeiterzahl und Leistungstext zu
    übernehmen. Erst wenn auch das nichts hergibt, bleibt die Bitte um
    manuelle Ergänzung.
    """
    from app.services import windows_ocr

    if windows_ocr.verfuegbar():
        text = _text_per_windows_ocr(file_path)
        if text.strip():
            if _detect_format(text) == "simple":
                firmen = _parse_simple_page(text, None)
                if firmen:
                    for eintrag in firmen:
                        eintrag["quelle"] = "ocr"
                    return firmen
            firmen = parse_formblatt(text)
            if firmen:
                return firmen

    return await _scan_ohne_erkennung(file_path)


def _text_per_windows_ocr(file_path: Path) -> str:
    """Erkennt den Text einer Bild- oder Scan-Datei über Windows."""
    from app.services import windows_ocr

    suffix = file_path.suffix.lower()
    if suffix != ".pdf":
        return windows_ocr.text_aus_bild(file_path)

    from app.services.wochenaufteilung import seiten_lesen

    # seiten_lesen liest die Textebene und lässt fehlende Seiten von der
    # Windows-Erkennung nachtragen — genau das, was hier gebraucht wird.
    return "\n".join(seiten_lesen(file_path))


async def _scan_ohne_erkennung(file_path: Path) -> list[dict]:
    """Letzte Stufe: Es ließ sich nichts lesen."""
    return [{
        "firma": f"(Handschrift/Scan: {file_path.name})",
        "ort": "",
        "personen": 0,
        "leistung": (
            "Aus dieser Datei ließ sich kein Text lesen. Bei gedruckten "
            "Formblättern gelingt das meist; handschriftliche Berichte "
            "brauchen einen Anthropic-Schlüssel (einstellungen.txt neben dem "
            "Programm, Zeile anthropic_key=). Bitte die Angaben hier von Hand "
            "ergänzen."
        ),
        "besonderes": None,
    }]


def handschrift_verfuegbar() -> bool:
    """Können Fotos und Scans überhaupt gelesen werden?

    Zwei Wege führen dahin: die Windows-Texterkennung (gedruckte Formblätter,
    ohne Schlüssel, offline) und die Anthropic-Schnittstelle (auch
    Handschrift, braucht einen Schlüssel). Einer genügt.
    """
    from app.services import windows_ocr

    return _has_real_key() or windows_ocr.verfuegbar()


def erkennung_beschreibung() -> tuple[bool, str]:
    """Was dieser Rechner mit Fotos und Scans anfangen kann — für die Oberfläche."""
    from app.services import windows_ocr

    mit_schluessel = _has_real_key()
    mit_windows = windows_ocr.verfuegbar()

    if mit_schluessel and mit_windows:
        return True, ("Fotos und Scans werden gelesen — gedruckte Formblätter "
                      "über Windows, Handschrift über den hinterlegten "
                      "Anthropic-Schlüssel. Bitte das Ergebnis trotzdem prüfen.")
    if mit_schluessel:
        return True, ("Fotos und Scans werden über den hinterlegten "
                      "Anthropic-Schlüssel gelesen, auch handschriftliche. "
                      "Bitte das Ergebnis trotzdem prüfen.")
    if mit_windows:
        return True, ("Gedruckte Formblätter werden von der Windows-"
                      "Texterkennung gelesen, auch als Scan ohne Textebene. "
                      "Für handschriftliche Berichte wird zusätzlich ein "
                      "Anthropic-Schlüssel gebraucht (einstellungen.txt, "
                      "Zeile anthropic_key=). Bitte das Ergebnis prüfen.")
    return False, ("Fotos und Scans können auf diesem Rechner nicht gelesen "
                   "werden. PDF mit Textebene geht ohne Weiteres; für Scans "
                   "wird ein Anthropic-Schlüssel gebraucht (einstellungen.txt "
                   "neben dem Programm, Zeile anthropic_key=).")


# ---------------------------------------------------------------------------
# Format 3b: Scan-Fallback via Claude Vision (optional, wenn API-Key vorhanden)
# ---------------------------------------------------------------------------

#: Auflösung, mit der gescannte PDF-Seiten für die Erkennung gerendert werden.
#: 200 dpi ist der Punkt, ab dem Handschrift verlässlich lesbar wird, ohne dass
#: die Bilder die Anfrage sprengen.
OCR_DPI = 200

#: Längste Bildkante nach dem Verkleinern. Darüber bringt mehr Auflösung nichts
#: mehr, kostet aber Übertragung und Zeit.
OCR_MAX_KANTE = 2200

#: Mehr Seiten als das in einer Anfrage zu schicken wird unzuverlässig.
OCR_MAX_SEITEN = 12


def _bild_aufbereiten(daten: bytes) -> bytes:
    """Bereitet ein Foto oder eine gescannte Seite für die Erkennung auf.

    Handschriftliche Bautagesberichte kommen als Handyfoto: schief belichtet,
    grauer Schatten über dem Blatt, Bleistift auf weißem Papier. Drei Schritte
    holen daraus deutlich mehr heraus, als das Rohbild zu schicken:

    1. Drehung aus den EXIF-Daten anwenden — ein hochkant fotografiertes Blatt
       liegt sonst quer.
    2. Autokontrast, der die dunkelsten und hellsten 0,5 % abschneidet. Das
       hebt blasse Bleistiftschrift vom vergilbten Papier ab.
    3. Auf eine sinnvolle Größe bringen. Zu klein ist unlesbar, zu groß bringt
       nichts mehr.

    Schlägt etwas davon fehl, werden die Originaldaten zurückgegeben — eine
    misslungene Aufbereitung darf die Erkennung nicht verhindern.
    """
    try:
        import io

        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(daten)) as bild:
            bild = ImageOps.exif_transpose(bild)
            if bild.mode not in ("RGB", "L"):
                bild = bild.convert("RGB")
            bild = ImageOps.autocontrast(bild, cutoff=0.5)

            laengste = max(bild.size)
            if laengste > OCR_MAX_KANTE:
                faktor = OCR_MAX_KANTE / laengste
                neu = (max(1, int(bild.width * faktor)),
                       max(1, int(bild.height * faktor)))
                bild = bild.resize(neu, Image.LANCZOS)

            puffer = io.BytesIO()
            bild.convert("RGB").save(puffer, format="JPEG", quality=88,
                                     optimize=True)
            return puffer.getvalue()
    except Exception:
        return daten


def _scan_seiten_als_bilder(file_path: Path) -> list[bytes]:
    """Seiten eines gescannten PDFs als aufbereitete JPEG-Bilder.

    Ein gescanntes PDF direkt als Dokument zu schicken funktioniert, liefert
    bei Handschrift aber schlechtere Ergebnisse als sauber gerenderte Seiten:
    Der Scan steckt oft in geringer Auflösung im PDF, und die Aufbereitung
    oben greift nur auf Bildern.
    """
    try:
        import pypdfium2 as pdfium

        dokument = pdfium.PdfDocument(str(file_path))
        try:
            bilder: list[bytes] = []
            for nummer in range(min(len(dokument), OCR_MAX_SEITEN)):
                import io

                seite = dokument[nummer].render(scale=OCR_DPI / 72).to_pil()
                puffer = io.BytesIO()
                seite.save(puffer, format="PNG")
                bilder.append(_bild_aufbereiten(puffer.getvalue()))
            return bilder
        finally:
            dokument.close()
    except Exception:
        return []


#: Was Claude über die Vorlage wissen muss. Ohne diese Hinweise werden
#: Spaltenüberschriften als Firmennamen gelesen und Stundenangaben als
#: Personenzahl.
OCR_ANWEISUNG = (
    "Das ist ein Bautagesbericht von einer Baustelle. Er kann handschriftlich "
    "ausgefüllt sein — deutsche Handschrift, oft Druckbuchstaben, teils "
    "Bleistift.\n\n"
    "Trage für jede aufgeführte Firma einen Eintrag ein:\n"
    "  firma      Name der Firma. Rechtsformen wie GmbH, KG, e.K. mitnehmen. "
    "Keine Spaltenüberschriften und keine Wörter wie 'Firma' oder "
    "'Nachunternehmer' als Namen übernehmen.\n"
    "  ort        Wo gearbeitet wurde: Bauteil, Geschoss, Achse, Raum. "
    "Leerer Text, wenn nichts dasteht.\n"
    "  personen   Anzahl der eingesetzten Personen als ganze Zahl. Das ist "
    "NICHT die Stundenzahl und nicht die Uhrzeit. Steht keine Zahl da: 0.\n"
    "  leistung   Was ausgeführt wurde, in ganzen Worten. Abkürzungen der "
    "Baustelle ausschreiben, wenn eindeutig (z. B. 'BW' = Bauwerk, "
    "'OG' = Obergeschoss).\n"
    "  besonderes Behinderungen, Verzögerungen, Unfälle, Anordnungen. "
    "Sonst null.\n\n"
    "REGELN:\n"
    "- Nichts erfinden. Ist ein Wort unleserlich, schreibe den erkennbaren "
    "Teil und setze dahinter [?]. Lieber '[?]' als geraten.\n"
    "- Ist ein Feld nicht ausgefüllt, lass es leer statt es zu erfinden.\n"
    "- Enthält das Bild mehrere Tage, nimm alle Firmen aller Tage auf.\n"
    "- Durchgestrichenes ist zurückgenommen und gehört nicht ins Ergebnis."
)


async def _extract_scan_via_claude(file_path: Path) -> list[dict]:
    if not settings.anthropic_api_key:
        return await _extract_scan_no_key(file_path)

    import base64

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Gescannte PDFs seitenweise rendern — das ist der Schritt, der bei
    # Handschrift den Unterschied macht.
    seitenbilder: list[bytes] = []
    if file_path.suffix.lower() == ".pdf":
        seitenbilder = _scan_seiten_als_bilder(file_path)
    else:
        seitenbilder = [_bild_aufbereiten(file_path.read_bytes())]

    if seitenbilder:
        inhalt: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(bild).decode(),
                },
            }
            for bild in seitenbilder
        ]
        return await _claude_bilder_auswerten(client, inhalt, file_path.name)

    # Rendern nicht möglich: das Dokument unverändert schicken.
    data = base64.standard_b64encode(file_path.read_bytes()).decode()

    media_type_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    media_type = media_type_map.get(file_path.suffix.lower(), "application/octet-stream")

    tool_schema = {
        "name": "report_firms",
        "description": "Gibt die extrahierten Firmeneinträge zurück",
        "input_schema": {
            "type": "object",
            "properties": {
                "firmen": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "firma": {"type": "string"},
                            "ort": {"type": "string"},
                            "personen": {"type": "integer"},
                            "leistung": {"type": "string"},
                            "besonderes": {"type": ["string", "null"]},
                        },
                        "required": ["firma", "ort", "personen", "leistung"],
                    },
                },
            },
            "required": ["firmen"],
        },
    }

    inhalt = [{
        "type": "document" if media_type == "application/pdf" else "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }]
    return await _claude_bilder_auswerten(client, inhalt, file_path.name,
                                          tool_schema=tool_schema)


def _ocr_schema() -> dict:
    return {
        "name": "report_firms",
        "description": "Gibt die extrahierten Firmeneinträge zurück",
        "input_schema": {
            "type": "object",
            "properties": {
                "firmen": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "firma": {"type": "string"},
                            "ort": {"type": "string"},
                            "personen": {"type": "integer"},
                            "leistung": {"type": "string"},
                            "besonderes": {"type": ["string", "null"]},
                        },
                        "required": ["firma", "ort", "personen", "leistung"],
                    },
                },
            },
            "required": ["firmen"],
        },
    }


async def _claude_bilder_auswerten(client, inhalt: list[dict], quelle: str,
                                   tool_schema: dict | None = None) -> list[dict]:
    """Schickt die aufbereiteten Seiten an Claude und räumt das Ergebnis auf."""
    inhalt = list(inhalt) + [{"type": "text", "text": OCR_ANWEISUNG}]

    try:
        antwort = client.messages.create(
            model=CLAUDE_MODELL,
            max_tokens=8192,
            tools=[tool_schema or _ocr_schema()],
            tool_choice={"type": "tool", "name": "report_firms"},
            messages=[{"role": "user", "content": inhalt}],
        )
    except Exception as exc:
        return [{
            "firma": f"(Erkennung fehlgeschlagen: {quelle})",
            "ort": "",
            "personen": 0,
            "leistung": f"Die Texterkennung meldete: {exc}",
            "besonderes": None,
            "quelle": "ocr",
        }]

    for block in antwort.content:
        if block.type == "tool_use" and block.name == "report_firms":
            firmen = block.input.get("firmen", []) or []
            # "quelle" markiert die Einträge als maschinell gelesen. Die
            # Pipeline hängt daran die Warnung "bitte Angaben prüfen" — bei
            # Handschrift ist das keine Förmlichkeit.
            for eintrag in firmen:
                eintrag["quelle"] = "ocr"
            return firmen
    return []


# ---------------------------------------------------------------------------
# Text-Fallback via Claude (nur wenn Regeln greifen nicht)
# ---------------------------------------------------------------------------

async def _extract_text_via_claude(text: str, file_name: str) -> list[dict]:
    if not _has_real_key():
        return []

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    tool_schema = {
        "name": "report_firms",
        "description": "Gibt die extrahierten Firmeneinträge zurück",
        "input_schema": {
            "type": "object",
            "properties": {
                "firmen": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "firma": {"type": "string"},
                            "ort": {"type": "string"},
                            "personen": {"type": "integer"},
                            "leistung": {"type": "string"},
                            "besonderes": {"type": ["string", "null"]},
                        },
                        "required": ["firma", "ort", "personen", "leistung"],
                    },
                },
            },
            "required": ["firmen"],
        },
    }

    response = client.messages.create(
        model=CLAUDE_MODELL,
        max_tokens=4096,
        tools=[tool_schema],
        tool_choice={"type": "tool", "name": "report_firms"},
        messages=[{
            "role": "user",
            "content": (
                "Extrahiere aus dem folgenden Bautagesbericht die Firmeneinträge. "
                "Mappe auf: firma, ort, personen (Zahl), leistung, besonderes.\n\n"
                f"Bautagesbericht ({file_name}):\n{text[:8000]}"
            ),
        }],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "report_firms":
            return block.input.get("firmen", [])
    return []


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

async def extract_from_file(file_path: Path, target_date: date | None = None) -> list[dict]:
    """Hauptfunktion — erkennt Format und wählt den passenden Extraktor."""

    suffix = file_path.suffix.lower()

    # Bilddateien -> Claude Vision (falls Key vorhanden), sonst Warnung
    if suffix in (".jpg", ".jpeg", ".png", ".tiff", ".bmp"):
        if _has_real_key():
            return await _extract_scan_via_claude(file_path)
        return await _extract_scan_no_key(file_path)

    # Reiner Text entsteht, wenn eine Seite mehrere Tage enthielt und je Tag
    # ein Abschnitt ausgeschnitten wurde (siehe services/wochenaufteilung).
    # Ein halbes Blatt lässt sich nicht als PDF schneiden, der Text schon.
    if suffix == ".txt":
        text = file_path.read_text(encoding="utf-8", errors="replace")
        if _detect_format(text) == "simple":
            # Ohne Datumsfilter: Der Abschnitt gehört bereits zum richtigen
            # Tag, eine zweite Prüfung könnte ihn nur fälschlich verwerfen.
            firmen = _parse_simple_page(text, None)
            if firmen:
                return firmen
        firmen = await _extract_text_via_claude(text, file_path.name)
        if firmen:
            return firmen
        return [{
            "firma": f"(Textabschnitt {file_path.name} nicht auswertbar)",
            "ort": "",
            "personen": 0,
            "leistung": "Automatische Extraktion nicht möglich — bitte manuell ergänzen",
            "besonderes": None,
        }]

    if suffix != ".pdf":
        return []

    if not has_text_layer(file_path):
        if _has_real_key():
            return await _extract_scan_via_claude(file_path)
        return await _extract_scan_no_key(file_path)

    with pdfplumber.open(file_path) as pdf:
        full_text = "\n\n".join(p.extract_text() or "" for p in pdf.pages)
        fmt = _detect_format(full_text)

        if fmt == "lindner":
            result = _parse_lindner(pdf)
            if result:
                return result
        elif fmt == "simple":
            result = _parse_simple_all_pages(pdf, target_date)
            if result:
                return result

    # Unbekanntes Textformat -> Claude-Fallback (falls Key vorhanden)
    text = extract_text_from_pdf(file_path)
    result = await _extract_text_via_claude(text, file_path.name)
    if result:
        return result

    return [{
        "firma": f"(Format unbekannt: {file_path.name})",
        "ort": "",
        "personen": 0,
        "leistung": "Automatische Extraktion nicht möglich — bitte manuell ergänzen",
        "besonderes": None,
    }]
