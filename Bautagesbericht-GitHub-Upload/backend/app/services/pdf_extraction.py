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


async def _extract_scan_no_key(file_path: Path) -> list[dict]:
    """Fallback, wenn kein Anthropic-Key konfiguriert ist.

    Auf dem Server gibt es kein lokales OCR mehr (EasyOCR/torch sprengen die
    freie Speicherstufe). Scans werden dann als Warnung gemeldet, damit der
    Nutzer die Angaben manuell ergänzen kann.
    """
    return [{
        "firma": f"(Scan {file_path.name} — kein OCR verfügbar)",
        "ort": "",
        "personen": 0,
        "leistung": "Kein Textlayer erkannt und kein Anthropic-API-Key konfiguriert — bitte Angaben manuell ergänzen.",
        "besonderes": None,
    }]


# ---------------------------------------------------------------------------
# Format 3b: Scan-Fallback via Claude Vision (optional, wenn API-Key vorhanden)
# ---------------------------------------------------------------------------

async def _extract_scan_via_claude(file_path: Path) -> list[dict]:
    if not settings.anthropic_api_key:
        return [{
            "firma": f"(Scan-PDF {file_path.name} — kein API-Key für OCR)",
            "ort": "",
            "personen": 0,
            "leistung": "Kein Textlayer und kein Anthropic-Key konfiguriert",
            "besonderes": None,
        }]

    import base64
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
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

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        tools=[tool_schema],
        tool_choice={"type": "tool", "name": "report_firms"},
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document" if media_type == "application/pdf" else "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data},
                },
                {
                    "type": "text",
                    "text": (
                        "Extrahiere alle Firmeneinträge aus diesem Bautagesbericht.\n"
                        "Mappe auf: firma (Name), ort (Bauteil/Etage/Raum), "
                        "personen (Zahl der eingesetzten Personen), leistung "
                        "(Beschreibung der ausgeführten Arbeiten), besonderes."
                    ),
                },
            ],
        }],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "report_firms":
            return block.input.get("firmen", [])
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
        model="claude-sonnet-4-20250514",
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
