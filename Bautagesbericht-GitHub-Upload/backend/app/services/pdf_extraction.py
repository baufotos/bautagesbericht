"""Extraktion von Firmen-/Leistungsdaten aus Unternehmens-Bautagesberichten.

Drei Formate werden erkannt:
1. Lindner-Format (strukturierte Tabellen mit Firma-Index)
2. Einfach-Format ("Fa. X (N Mann)" mit Aufzählung, ein Tag pro Seite)
3. Scans ohne Textlayer  -> Claude Vision (falls API-Key vorhanden)
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pdfplumber

from app.config import settings
from app.services import bautext, bildformate, firmennamen, schnittstelle

# HEIC/HEIF bei Pillow anmelden, bevor das erste Bild geöffnet wird. Ein
# handschriftlicher Bericht kommt als Handyfoto, und ein iPhone fotografiert
# in HEIC.
bildformate.registriere()

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
                    "orte": [],
                    "leistungen": [],
                    "behinderungen": [],
                    "gewerk": f.get("gewerk", ""),
                }

        # Arbeiten zuordnen
        for a in arbeit_rows:
            for f in firmen_map.values():
                if f["idx"] == a["idx"]:
                    # Alle Orte sammeln, nicht nur den ersten. Eine Firma
                    # arbeitet an einem Tag im 2., 3. und 4. OG; stand bisher
                    # nur "3.OG" im Bericht, fehlten zwei Geschosse.
                    ort = " ".join((a["ort"] or "").split())
                    if ort and ort not in f["orte"]:
                        f["orte"].append(ort)
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
            "ort": " · ".join(f["orte"]),
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


#: Ein Firmenname mit weniger Zeichen ist ein Kürzel, kein Name. "RF" steht so
#: auf dem Formblatt der RF Fassaden — im Bericht an den Bauherrn hilft das
#: niemandem weiter.
MIN_FIRMENLAENGE = 4

#: Formularnummern sehen aus wie Firmenkürzel: "FO377_RF", "F-0377/RF".
#: Daraus darf nie ein Firmenname werden.
_FORMULARNUMMER = re.compile(r"\b[A-Z]{1,3}[-_ ]?\d{2,5}[-_/][A-Z0-9]{1,6}\b")

#: Dieselbe Kennung, aber von der anderen Seite gelesen: Der Buchstabenteil
#: HINTER der Nummer gehört der Firma, die den Vordruck herausgibt
#: ("FO377_RF" -> RF). Als Trenner ist hier auch ein Leerzeichen erlaubt —
#: die Texterkennung macht aus dem Unterstrich gern eines.
_KENNUNG_FIRMA = re.compile(r"\b[A-Z]{1,3}[-_ ]?\d{2,5}[-_/ ]([A-Z]{2,4})\b")


def _kuerzel_ausschreiben(kuerzel: str, text: str) -> str:
    """Aus "RF" wird "RF Fassaden", wenn das Blatt den Zusatz hergibt.

    Firmenkürzel stehen auf Formblättern neben dem Logo, und das Logo trägt
    den ausgeschriebenen Namen: "RF" groß, "FASSADEN" klein daneben. Die
    Texterkennung liest beides, nur eben in getrennten Kästchen.
    """
    if len(kuerzel) > 3:
        return kuerzel
    muster = re.compile(
        rf"{re.escape(kuerzel)}[\s\-–|]*([A-ZÄÖÜ][A-ZÄÖÜa-zäöüß]{{3,20}})",
    )
    for treffer in muster.finditer(text):
        zusatz = treffer.group(1)
        # Nur echte Zusätze, keine Formularwörter ("RF Bautagesbericht").
        if zusatz.lower().strip() in bautext.VORDRUCK_WOERTER:
            continue
        return f"{kuerzel} {zusatz.capitalize()}"
    return kuerzel


def _formblatt_firma(text: str, ersatz: str,
                     bekannte: tuple[str, ...] = ()) -> str:
    """Der Firmenname eines Formblatts.

    Reihenfolge der Quellen, absteigend nach Verlässlichkeit:

    1. Eine Firma aus den Projektstammdaten, die im Blatt vorkommt. Dort hat
       jemand den Namen von Hand richtig eingetragen — besser wird es nicht.
    2. Eine Zeile mit Rechtsform ("… GmbH & Co. KG").
    3. Das Kürzel neben der Unterschriftszeile, nach Möglichkeit ausgeschrieben.
    """
    kandidaten: list[str] = []

    for treffer in _RECHTSFORM.finditer(text):
        name = treffer.group(1).strip(" .:-")
        if name and not name.lower().startswith(("bauvorhaben", "bauherr")):
            kandidaten.append(name)

    treffer = _UNTERSCHRIFT_FIRMA.search(text)
    if treffer:
        kuerzel = treffer.group(1).strip(" .:-")
        if kuerzel and not _FORMULARNUMMER.search(kuerzel):
            kandidaten.append(_kuerzel_ausschreiben(kuerzel, text))

    # Letzte Rückfallebene: das Kürzel in der Formularkennung. Firmen nummerieren
    # ihre Vordrucke als "FO377_RF" — die Nummer gehört dem Formular, der
    # Buchstabenteil dahinter der Firma, die es herausgibt.
    #
    # Warum das gebraucht wird: Auf einem Blatt derselben Woche hatte die
    # Erkennung neben "Unterschrift" das "RF" verschluckt. Vier Tage trugen
    # die Firma, der fünfte den Platzhalter "Firma bitte ergänzen" — im
    # selben Stapel, vom selben Unternehmen. Die Kennung steht dagegen im
    # Kopf jedes Blattes und wird zuverlässig gelesen.
    if not kandidaten:
        treffer = _KENNUNG_FIRMA.search(text)
        if treffer:
            kandidaten.append(treffer.group(1).upper())

    if not kandidaten:
        return ersatz

    # Bekannte Firma schlägt alles. Auch ein Kürzel findet so zu seinem vollen
    # Namen: "RF" trifft "RF Fassaden GmbH" aus den Stammdaten. Die Zuordnung
    # macht ``firmennamen`` — dort sitzen auch die Sicherungen, damit bei zwei
    # ähnlichen Firmen nicht geraten wird.
    if bekannte:
        zuordnung, _ = firmennamen.vereinheitliche(kandidaten, list(bekannte))
        for kandidat in kandidaten:
            zugeordnet = zuordnung.get(kandidat, "")
            if zugeordnet and any(
                firmennamen.normalisiere(zugeordnet) == firmennamen.normalisiere(b)
                for b in bekannte
            ):
                return zugeordnet

    # Sonst der längste brauchbare Kandidat — ein Name mit Rechtsform ist
    # aussagekräftiger als ein Kürzel.
    brauchbar = [k for k in kandidaten if len(k) >= MIN_FIRMENLAENGE]
    if brauchbar:
        return max(brauchbar, key=len)
    return kandidaten[0]


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


def parse_formblatt(text: str, quelle: str = "",
                    bekannte: tuple[str, ...] = ()) -> list[dict]:
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
        "firma": _formblatt_firma(text, quelle or "Firma bitte ergänzen", bekannte),
        # Geschossangaben geraderücken: "406. Ost" ist "4.OG. Ost", und das
        # steht sonst genauso im Bericht an den Bauherrn (siehe bautext).
        "ort": bautext.geraderuecken(ort),
        "personen": personen,
        "leistung": (bautext.geraderuecken(leistung)
                     or "Leistungstext nicht lesbar — bitte ergänzen"),
        "besonderes": None,
        "quelle": "ocr",
    }]


async def _extract_scan_no_key(file_path: Path,
                               bekannte: tuple[str, ...] = ()) -> list[dict]:
    """Scan ohne Anthropic-Schlüssel: Windows-Texterkennung versuchen.

    Windows bringt seit Windows 10 eine eigene Texterkennung mit. Bei
    gedruckten Formblättern — und das sind die Berichte der Nachunternehmer —
    liest sie zuverlässig genug, um Datum, Arbeiterzahl und Leistungstext zu
    übernehmen. Erst wenn auch das nichts hergibt, bleibt die Bitte um
    manuelle Ergänzung.
    """
    from app.services import windows_ocr
    from app.services.wochenaufteilung import datum_der_seite

    if windows_ocr.verfuegbar():
        text = _text_per_windows_ocr(file_path)
        if text.strip():
            # Zuerst die Frage, ob überhaupt etwas Ausgefülltes angekommen ist.
            # Bei Schreibschrift liest Windows nur den gedruckten Vordruck —
            # daraus entstand bisher ein Eintrag, dessen "Leistung" die Liste
            # "Polier · Werkpolier · Vorarbeiter …" war. Ein Feld, das gefüllt
            # aussieht, prüft niemand nach; deshalb wird hier lieber offen
            # gemeldet, dass nichts gelesen wurde.
            seiten = text.split(chr(10) + chr(10))
            if bautext.handschrift_unlesbar(
                seiten, any(datum_der_seite(s) for s in seiten)
            ):
                return await _scan_ohne_erkennung(file_path, nur_vordruck=True)

            if _detect_format(text) == "simple":
                firmen = _parse_simple_page(text, None)
                if firmen:
                    for eintrag in firmen:
                        eintrag["quelle"] = "ocr"
                    return firmen
            firmen = parse_formblatt(text, bekannte=bekannte)
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


async def _scan_ohne_erkennung(file_path: Path, *,
                               nur_vordruck: bool = False) -> list[dict]:
    """Letzte Stufe: Es ließ sich nichts Ausgefülltes lesen.

    ``nur_vordruck=True`` heißt: Der gedruckte Rahmen kam durch, die
    Eintragungen nicht. Das ist die typische Lage bei Schreibschrift und
    verdient eine andere Erklärung als "gar nichts gelesen" — es sagt dem
    Nutzer nämlich genau, woran es liegt.
    """
    if nur_vordruck:
        text = bautext.unlesbar_hinweis(file_path.name,
                                        _wo_der_schluessel_hingehoert())
    else:
        text = (
            "Aus dieser Datei ließ sich kein Text lesen. Bei gedruckten "
            "Formblättern gelingt das meist; handschriftliche Berichte "
            "brauchen einen Anthropic-Schlüssel ("
            + _wo_der_schluessel_hingehoert()
            + "). Bitte die Angaben hier von Hand ergänzen."
        )
    return [{
        "firma": f"(Handschrift/Scan: {file_path.name})",
        "ort": "",
        "personen": 0,
        "leistung": text,
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


def _wo_der_schluessel_hingehoert() -> str:
    """Wo der Anthropic-Schlüssel einzutragen ist — je nach Betriebsart.

    Dieselbe App läuft auf dem Bürorechner aus einem Ordner und im Web in
    einem Container. Ein Hinweis auf "einstellungen.txt neben dem Programm"
    ist online schlicht falsch: Dort gibt es keine solche Datei, sondern eine
    Umgebungsvariable im Render-Dashboard.
    """
    import sys

    if sys.platform.startswith("win"):
        return "einstellungen.txt neben dem Programm, Zeile anthropic_key="
    return ("Umgebungsvariable BTB_ANTHROPIC_API_KEY — bei Render unter "
            "Environment einzutragen")


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
                      "Anthropic-Schlüssel gebraucht ("
                      + _wo_der_schluessel_hingehoert()
                      + "). Bitte das Ergebnis prüfen.")
    return False, ("Fotos und Scans können auf diesem Rechner nicht gelesen "
                   "werden. PDF mit Textebene geht ohne Weiteres; für Scans "
                   "wird ein Anthropic-Schlüssel gebraucht ("
                   + _wo_der_schluessel_hingehoert() + ").")


# ---------------------------------------------------------------------------
# Format 3b: Scan-Fallback via Claude Vision (optional, wenn API-Key vorhanden)
# ---------------------------------------------------------------------------

#: Auflösung, mit der gescannte PDF-Seiten für die Erkennung gerendert werden.
#: 300 dpi: Das Blatt wird anschließend ohnehin verkleinert, und ein Bild aus
#: einem 300-dpi-Rendering hat nach dem Verkleinern sichtbar sauberere Kanten
#: als eines aus 200 dpi.
OCR_DPI = 300

#: Längste Bildkante nach dem Verkleinern — dieselbe Begründung wie in
#: services/seitenlesung: Die Modelle rechnen alles über 1568 Pixel selbst
#: herunter. Vorher standen hier 2200, die also nie ankamen.
OCR_MAX_KANTE = 1540

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
    4. Leicht nachschärfen. Das Verkleinern verwischt genau die dünnen
       Striche, auf die es hier ankommt.

    Schlägt etwas davon fehl, werden die Originaldaten zurückgegeben — eine
    misslungene Aufbereitung darf die Erkennung nicht verhindern.
    """
    try:
        import io

        from PIL import Image, ImageFilter, ImageOps

        with Image.open(io.BytesIO(daten)) as bild:
            bild = ImageOps.exif_transpose(bild)
            if bild.mode not in ("RGB", "L"):
                bild = bild.convert("RGB")

            laengste = max(bild.size)
            if laengste > OCR_MAX_KANTE:
                faktor = OCR_MAX_KANTE / laengste
                neu = (max(1, int(bild.width * faktor)),
                       max(1, int(bild.height * faktor)))
                bild = bild.resize(neu, Image.LANCZOS)

            bild = ImageOps.autocontrast(bild, cutoff=0.5)
            bild = bild.filter(ImageFilter.UnsharpMask(radius=1.2, percent=80,
                                                       threshold=3))

            puffer = io.BytesIO()
            bild.convert("RGB").save(puffer, format="JPEG", quality=92,
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


def _ocr_anweisung(bekannte: tuple[str, ...] = (),
                   ziel: date | None = None) -> str:
    """Die Anweisung für diesen einen Aufruf.

    Zwei Zusätze, die je Aufruf verschieden sind:

    * **Der Tag.** Ohne ihn galt die Regel "nimm alle Firmen aller Tage auf"
      auch dann, wenn dieses Blatt für EINEN Tag hochgeladen wurde. Im Bericht
      vom Montag stand dann die Arbeit der ganzen Woche.
    * **Die Firmen der Baustelle.** Derselbe Hebel wie beim seitenweisen Lesen
      (services/seitenlesung): Wer weiß, welche Firmen hier arbeiten, liest
      eine krakelige Schleife richtig. Im Bilderzweig fehlte er bisher.
    """
    text = OCR_ANWEISUNG
    if ziel is not None:
        text += (
            "\n\nDER TAG DIESES BERICHTS\n"
            f"Dieses Blatt gehört zum {ziel.strftime('%d.%m.%Y')}. Stehen "
            "darauf mehrere Tage, nimm NUR die Firmen dieses einen Tages auf "
            "— die anderen Tage bekommen ihren eigenen Bericht. Ist auf dem "
            "Blatt kein Datum zu lesen, nimm auf, was dasteht."
        )
    if bekannte:
        text += (
            "\n\nAUF DIESER BAUSTELLE BEKANNT\n"
            f"Diese Firmen kommen auf diesem Projekt vor: "
            f"{', '.join(bekannte[:15])}.\n"
            "Das ist eine Lesehilfe, keine Auswahlliste: Passt ein Name "
            "erkennbar zu einem davon, nimm die bekannte Schreibweise. Steht "
            "dort eine andere Firma, schreib sie so ab, wie sie dasteht."
        )
    return text


def _tage_fuer(tage: list, ziel: date | None) -> list:
    """Von den erkannten Tagen die, die zu diesem Bericht gehören.

    WOZU DAS NÖTIG IST
    Ein handschriftliches Bautagebuch enthält meist die ganze Woche. Bisher
    wurde das Zieldatum in diesem Zweig nicht beachtet: Aus einem Dokument mit
    sechs Tagen wurden ALLE Firmen aller Tage in EINEN Bericht geschrieben.
    Bei einem Wochenpaket, das seitenweise getrennt wurde, fiel das nicht auf;
    beim direkten Hochladen eines Tagebuchs für einen Tag stand im Bericht vom
    Montag die Arbeit der ganzen Woche — mit doppelten Firmen und
    aufaddierten Personenzahlen.

    Passt kein Tag zum Zieldatum, wird nicht gefiltert: Dann ist entweder das
    Datum auf dem Blatt nicht zu lesen gewesen oder das Blatt gehört zu genau
    einem Tag, dessen Datum verlesen wurde. In beiden Fällen ist der Inhalt
    besser als ein leerer Bericht — die Warnung "aus einem Scan gelesen" steht
    ohnehin daran.
    """
    if ziel is None:
        return tage
    passend = [t for t in tage if t.datum == ziel]
    return passend or tage


async def _extract_scan_via_claude(
    file_path: Path, bekannte_firmen: tuple[str, ...] = (),
    target_date: date | None = None,
) -> list[dict]:
    if not settings.anthropic_api_key:
        return await _extract_scan_no_key(file_path, bekannte_firmen)

    # Seitenweise lesen, mit zweitem Durchgang zur Prüfung. Der frühere Weg —
    # alle Seiten in einer Anfrage — reichte für gedruckte Formblätter, nicht
    # für ein handschriftliches Bautagebuch über eine ganze Woche. Warum,
    # steht ausführlich in services/seitenlesung.
    from app.services import seitenlesung

    if seitenlesung.verfuegbar():
        befunde = []
        try:
            befunde = await seitenlesung.lies_seiten(file_path, bekannte_firmen)
        except Exception as fehler:
            befunde = [seitenlesung.SeitenBefund(
                seite=1, fehler=seitenlesung.fehlertext(fehler))]

        # Scheitert die Schnittstelle, muss das im Bericht stehen. Vorher
        # verschwand ein abgelehnter Schlüssel lautlos und der Anwender sah
        # nur einen leeren Bericht.
        probleme = seitenlesung.fehlermeldungen(befunde)
        if probleme and not any(not b.fehler for b in befunde):
            return [{
                "firma": f"(Erkennung fehlgeschlagen: {file_path.name})",
                "ort": "",
                "personen": 0,
                "leistung": " ".join(probleme),
                "besonderes": None,
                "quelle": "ocr",
            }]

        alle_tage = seitenlesung.zu_tagen(befunde, bekannte_firmen)
        eintraege: list[dict] = []
        for tag in _tage_fuer(alle_tage, target_date):
            eintraege.extend(seitenlesung.als_firmeneintraege(tag))
        if eintraege:
            return eintraege
        # Nichts herausgekommen: unten weiter mit dem einfachen Weg. Ein
        # gedrucktes Formblatt ohne Nachunternehmertabelle fällt hier heraus.

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

    anweisung = _ocr_anweisung(bekannte_firmen, target_date)

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
        return await _claude_bilder_auswerten(client, inhalt, file_path.name,
                                              anweisung=anweisung)

    # Rendern nicht möglich — dann ist es ein PDF, das pypdfium2 nicht
    # aufbekommen hat (beschädigt, verschlüsselt). Bilder landen hier nie:
    # ``_bild_aufbereiten`` gibt im Zweifel die Rohdaten zurück, nie nichts.
    # Also das Dokument unverändert schicken und die Gegenseite entscheiden
    # lassen, ob sie es lesen kann.
    inhalt = [{
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": base64.standard_b64encode(file_path.read_bytes()).decode(),
        },
    }]
    return await _claude_bilder_auswerten(client, inhalt, file_path.name,
                                          anweisung=anweisung)


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
                                   anweisung: str | None = None) -> list[dict]:
    """Schickt die aufbereiteten Seiten an Claude und räumt das Ergebnis auf.

    Die Anfrage läuft in einem eigenen Thread und wird bei vorübergehenden
    Störungen wiederholt (services/schnittstelle). Das Anthropic-Paket wird
    hier synchron benutzt, und eine Bilderkennung dauert zehn Sekunden und
    mehr — direkt in der Ereignisschleife stünde der ganze Webserver so lange
    still. Wer in derselben Zeit die Mängelliste öffnet, bekäme eine Seite,
    die sich nicht lädt.
    """
    inhalt = list(inhalt) + [
        {"type": "text", "text": anweisung or OCR_ANWEISUNG}
    ]

    def ruf():
        return client.messages.create(
            model=CLAUDE_MODELL,
            max_tokens=8192,
            tools=[_ocr_schema()],
            tool_choice={"type": "tool", "name": "report_firms"},
            messages=[{"role": "user", "content": inhalt}],
        )

    try:
        antwort = await schnittstelle.mit_wiederholung(ruf)
    except Exception as exc:
        return [{
            "firma": f"(Erkennung fehlgeschlagen: {quelle})",
            "ort": "",
            "personen": 0,
            # Klartext statt der englischen Rohmeldung — sonst sucht der
            # Anwender den Fehler beim Scan, während der Grund ein falscher
            # Schlüssel oder ein leeres Konto ist.
            "leistung": schnittstelle.fehlertext(exc),
            "besonderes": None,
            "quelle": "ocr",
        }]

    for block in (antwort.content if antwort else []):
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

async def _extract_text_via_claude(text: str, file_name: str,
                                   bekannte_firmen: tuple[str, ...] = (),
                                   target_date: date | None = None) -> list[dict]:
    """Letzte Stufe für Text, den keine Regel erkannt hat.

    Auch hier laufen die Firmen der Baustelle mit: Es ist derselbe Hebel wie
    bei der Bilderkennung, und der Text kommt in diesem Zweig oft genug aus
    einer Texterkennung, ist also genauso fehlerbehaftet.
    """
    if not _has_real_key():
        return []

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    hinweise = [
        "Extrahiere aus dem folgenden Bautagesbericht die Firmeneinträge. "
        "Mappe auf: firma, ort, personen (Zahl), leistung, besonderes.",
        "Der Text stammt oft aus einer Texterkennung und enthält deshalb "
        "Verlesungen. Nichts erfinden: Ist ein Wort unleserlich, den "
        "erkennbaren Teil schreiben und [?] anhängen.",
    ]
    if target_date is not None:
        hinweise.append(
            f"Dieser Bericht gehört zum {target_date.strftime('%d.%m.%Y')}. "
            "Stehen im Text mehrere Tage, nimm nur die Firmen dieses Tages auf."
        )
    if bekannte_firmen:
        hinweise.append(
            "Auf dieser Baustelle kommen diese Firmen vor: "
            + ", ".join(bekannte_firmen[:15])
            + ". Das ist eine Lesehilfe, keine Auswahlliste."
        )

    def ruf():
        return client.messages.create(
            model=CLAUDE_MODELL,
            max_tokens=4096,
            tools=[_ocr_schema()],
            tool_choice={"type": "tool", "name": "report_firms"},
            messages=[{
                "role": "user",
                "content": (
                    "\n\n".join(hinweise)
                    + f"\n\nBautagesbericht ({file_name}):\n{text[:8000]}"
                ),
            }],
        )

    try:
        response = await schnittstelle.mit_wiederholung(ruf)
    except Exception:
        # Der Aufrufer hat für diesen Fall einen Platzhalter mit klarem Text;
        # hier zu werfen würde die ganze Einreichung scheitern lassen.
        return []

    for block in (response.content if response else []):
        if block.type == "tool_use" and block.name == "report_firms":
            # Auch hier als maschinell gelesen kennzeichnen: Die Pipeline
            # hängt daran die Bitte ums Gegenlesen. Vorher fehlte die Marke
            # in diesem Zweig — ein aus fehlerbehaftetem Erkennungstext
            # gedeuteter Bericht sah damit so verlässlich aus wie einer aus
            # einer sauberen PDF-Textebene.
            firmen = block.input.get("firmen", []) or []
            for eintrag in firmen:
                eintrag.setdefault("quelle", "ocr")
            return firmen
    return []


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

async def extract_from_file(
    file_path: Path,
    target_date: date | None = None,
    bekannte_firmen: tuple[str, ...] = (),
) -> list[dict]:
    """Hauptfunktion — erkennt Format und wählt den passenden Extraktor.

    ``bekannte_firmen`` sind die Firmen, die für dieses Projekt in den
    Stammdaten stehen. Sie sind die verlässlichste Quelle für einen
    Firmennamen, weil sie jemand von Hand eingetragen hat: Aus dem gelesenen
    Kürzel "RF" wird damit "RF Fassaden GmbH", und aus den drei Schreibweisen
    einer Woche wird eine.
    """

    suffix = file_path.suffix.lower()

    # Bilddateien -> Claude Vision (falls Key vorhanden), sonst Warnung.
    #
    # Welche Endungen als Bild gelten, steht in services/bildformate und
    # nicht hier: Dort ist die Liste, die auch die Baufotos und die
    # Mängelfotos benutzen. Vorher stand an dieser Stelle eine eigene, kürzere
    # Aufzählung ohne HEIC, HEIF, AVIF, WEBP und ".tif" — und die Oberfläche
    # lässt genau diese Dateien zur Auswahl zu. Ein mit dem iPhone
    # abfotografierter Bericht kam damit an, wurde stillschweigend verworfen
    # und der Bericht entstand ohne eine einzige Firma.
    if suffix in bildformate.BILD_ENDUNGEN:
        if _has_real_key():
            return await _extract_scan_via_claude(file_path, bekannte_firmen,
                                                  target_date)
        return await _extract_scan_no_key(file_path, bekannte_firmen)

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
        # Ohne Zieldatum: Der Abschnitt gehört schon zum richtigen Tag, und
        # ein zweiter Datumsfilter könnte ihn nur fälschlich leeren.
        firmen = await _extract_text_via_claude(text, file_path.name,
                                                bekannte_firmen)
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
            return await _extract_scan_via_claude(file_path, bekannte_firmen,
                                                  target_date)
        return await _extract_scan_no_key(file_path, bekannte_firmen)

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

    # Unbekanntes Textformat: erst die Formblatt-Regeln, dann Claude.
    # Das gedruckte RF-Formblatt hat eine Textebene und fällt hier herein —
    # es ohne Rückfrage an die Schnittstelle zu schicken wäre langsamer und
    # teurer als nötig.
    text = extract_text_from_pdf(file_path)
    result = parse_formblatt(text, bekannte=bekannte_firmen)
    if result:
        return result
    result = await _extract_text_via_claude(text, file_path.name,
                                            bekannte_firmen, target_date)
    if result:
        return result

    return [{
        "firma": f"(Format unbekannt: {file_path.name})",
        "ort": "",
        "personen": 0,
        "leistung": "Automatische Extraktion nicht möglich — bitte manuell ergänzen",
        "besonderes": None,
    }]
