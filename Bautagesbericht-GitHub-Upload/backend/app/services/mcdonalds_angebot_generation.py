"""Erzeugt das Angebotsdokument zur Beauftragung eines Fachplaners.

╔══════════════════════════════════════════════════════════════════════════╗
║  HIER WIRD SPÄTER DIE ECHTE ANGEBOTSVORLAGE EINGESETZT                   ║
║                                                                          ║
║  TODO McDonald's: Die Vorlage des Büros liegt noch nicht vor (laut        ║
║  Konzeptblatt eine Excel-Vorlage). Bis dahin baut dieses Modul ein        ║
║  schlichtes, aber vollständiges Word-Dokument aus den erfassten Angaben:  ║
║  Kopf, Tabelle der Kernangaben, Abschnitt "Mehrleistungen", Fußzeile.     ║
║                                                                          ║
║  Austausch später, OHNE Änderung an Router, Modell oder Oberfläche:       ║
║    Variante A (Word-Vorlage): ``backend/templates/`` eine Vorlage         ║
║      ablegen, ihren Namen unten in TEMPLATE_NAME eintragen und in         ║
║      ``erzeuge_angebot`` ``Document(pfad)`` statt ``Document()`` laden —  ║
║      Vorbild ist app.services.maengelliste_generation, das genau so mit   ║
║      Platzhaltern ({{PROJEKT}} …) arbeitet.                              ║
║    Variante B (Excel-Vorlage): eine eigene Funktion daneben stellen und   ║
║      in ``erzeuge_angebot`` verzweigen. Der Rückgabewert bleibt           ║
║      (Bytes, Dateiname) — der Versand hängt nur daran.                    ║
╚══════════════════════════════════════════════════════════════════════════╝

Bewusst mit der python-docx-Hochsprache und ohne Vorlage: Was hier entsteht,
ist ein Platzhalter, an dem nichts ausgemessen werden muss. Für die feine
Formatierung an einer echten Vorlage gibt es in diesem Projekt schon zwei
Vorbilder (``docx_generation`` mit rohem XML, ``maengelliste_generation`` mit
Platzhaltern).
"""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

from app.config import settings
from app.models import McdonaldsAngebot

#: TODO McDonald's: Name der echten Vorlage in ``backend/templates``, sobald
#: sie vorliegt. Leer = ohne Vorlage bauen (der heutige Zustand).
TEMPLATE_NAME = ""

FONT = "Arial"
SZ_TITEL = Pt(15)
SZ_KOPF = Pt(10.5)
SZ_WERT = Pt(10)
SZ_LABEL = Pt(8)
SZ_FUSS = Pt(7.5)
GRAU = RGBColor(0x66, 0x66, 0x66)

#: Unterordner in ``storage/output``, in dem die Angebote liegen.
ABLAGE = "mcdonalds"

#: Beschriftungen der Kernangaben-Tabelle. Die Reihenfolge ist die Reihenfolge
#: im Dokument; ``angaben`` des Angebots wird darunter angehängt, was hier
#: nicht schon steht.
KOPF_FELDER = (
    ("Standort", "standort"),
    ("Anschrift", "anschrift"),
    ("Auftraggeber", "auftraggeber"),
    ("Leistungsphase", "leistungsphase"),
    ("Fachplaner", "fachplaner"),
    ("Ansprechpartner", "ansprechpartner"),
)


def _grundschrift(dokument) -> None:
    stil = dokument.styles["Normal"]
    stil.font.name = FONT
    stil.font.size = SZ_WERT


def _absatz(dokument, text: str = "", *, groesse=SZ_WERT, fett=False,
            farbe: RGBColor | None = None, abstand_nach=Pt(4),
            ausrichtung=None):
    absatz = dokument.add_paragraph()
    absatz.paragraph_format.space_after = abstand_nach
    if ausrichtung is not None:
        absatz.alignment = ausrichtung
    if text:
        lauf = absatz.add_run(text)
        lauf.font.name = FONT
        lauf.font.size = groesse
        lauf.bold = fett
        if farbe is not None:
            lauf.font.color.rgb = farbe
    return absatz


def _betrag(wert) -> str:
    """Deutsche Schreibweise: 1.234,50 €. Ohne Betrag ein Gedankenstrich."""
    if wert in (None, ""):
        return "—"
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return str(wert)
    text = f"{zahl:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return f"{text} €"


def _fmt_phase(phase) -> str:
    return f"LPH {phase}" if phase else "—"


def dateiname(angebot: McdonaldsAngebot) -> str:
    """``260904_Angebot_AAH_Aachen Europaplatz_LPH6.docx``.

    Datum voran wie beim Fotosatz-Archiv (siehe ``services.baufotos``): So
    sortiert der Explorer den Projektordner von selbst chronologisch.
    """
    fall = angebot.fall
    kennung = (fall.ordner_name if fall else "") or "Standort"
    phase = f"_LPH{angebot.leistungsphase}" if angebot.leistungsphase else ""
    roh = f"{date.today():%y%m%d}_Angebot_{kennung}{phase}.docx"
    # Dateinamen dürfen unter Windows dieselben Zeichen nicht enthalten wie
    # Ordnernamen — hier dieselbe Regel wie in ``mcdonalds_ordner``.
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", roh).replace("  ", " ").strip()


def kernangaben(angebot: McdonaldsAngebot) -> list[tuple[str, str]]:
    """Die Zeilen der Kernangaben-Tabelle, in der Reihenfolge des Dokuments.

    Getrennt vom Dokumentbau, damit die Oberfläche später dieselbe Vorschau
    zeigen kann, ohne ein Word-Dokument zu erzeugen.
    """
    fall = angebot.fall
    planer = angebot.fachplaner
    bekannt = {
        "standort": (fall.standort_name if fall else "") or "",
        "anschrift": (fall.standort_adresse if fall else "") or "",
        "auftraggeber": (fall.auftraggeber if fall else "") or "",
        "leistungsphase": _fmt_phase(angebot.leistungsphase),
        "fachplaner": (planer.name if planer else "") or "",
        "ansprechpartner": (planer.ansprechpartner if planer else "") or "",
    }

    zeilen = [(label, bekannt[schluessel] or "—")
              for label, schluessel in KOPF_FELDER]

    # Alles, was im Formular zusätzlich erfasst wurde, hinten dran. Bis das
    # endgültige Feldschema vorliegt, ist das der Weg, auf dem neue Felder
    # ohne Codeänderung im Dokument landen.
    for bezeichnung, wert in (angebot.angaben or {}).items():
        text = str(wert or "").strip()
        if text:
            zeilen.append((str(bezeichnung), text))
    return zeilen


def _tabelle(dokument, zeilen: list[tuple[str, str]]) -> None:
    tabelle = dokument.add_table(rows=0, cols=2)
    tabelle.autofit = False
    for label, wert in zeilen:
        zeile = tabelle.add_row()
        links, rechts = zeile.cells
        links.width = Cm(4.6)
        rechts.width = Cm(11.4)

        absatz = links.paragraphs[0]
        absatz.paragraph_format.space_after = Pt(2)
        lauf = absatz.add_run(label)
        lauf.font.name = FONT
        lauf.font.size = SZ_LABEL
        lauf.font.color.rgb = GRAU

        absatz = rechts.paragraphs[0]
        absatz.paragraph_format.space_after = Pt(2)
        lauf = absatz.add_run(wert)
        lauf.font.name = FONT
        lauf.font.size = SZ_WERT


def _mehrleistungen(dokument, angebot: McdonaldsAngebot) -> None:
    eintraege = [
        e for e in (angebot.mehrleistungen or [])
        if isinstance(e, dict) and str(e.get("bezeichnung") or "").strip()
    ]

    _absatz(dokument, "Mehrleistungen", groesse=SZ_KOPF, fett=True,
            abstand_nach=Pt(6))

    if not eintraege:
        _absatz(dokument, "Keine Mehrleistungen vereinbart.", farbe=GRAU)
        return

    tabelle = dokument.add_table(rows=0, cols=2)
    tabelle.autofit = False
    summe = 0.0
    hat_betrag = False

    for eintrag in eintraege:
        zeile = tabelle.add_row()
        links, rechts = zeile.cells
        links.width = Cm(11.4)
        rechts.width = Cm(4.6)

        absatz = links.paragraphs[0]
        absatz.paragraph_format.space_after = Pt(2)
        lauf = absatz.add_run(str(eintrag.get("bezeichnung")).strip())
        lauf.font.name = FONT
        lauf.font.size = SZ_WERT

        betrag = eintrag.get("betrag")
        if betrag not in (None, ""):
            try:
                summe += float(betrag)
                hat_betrag = True
            except (TypeError, ValueError):
                pass

        absatz = rechts.paragraphs[0]
        absatz.paragraph_format.space_after = Pt(2)
        absatz.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        lauf = absatz.add_run(_betrag(betrag))
        lauf.font.name = FONT
        lauf.font.size = SZ_WERT

    if hat_betrag:
        # Die Summe nur, wenn überhaupt Beträge dastehen. Eine "0,00 €"-Zeile
        # unter drei Positionen ohne Preis wäre eine falsche Aussage.
        zeile = tabelle.add_row()
        links, rechts = zeile.cells
        for zelle, text, rechtsbuendig in (
            (links, "Summe Mehrleistungen", False),
            (rechts, _betrag(summe), True),
        ):
            absatz = zelle.paragraphs[0]
            absatz.paragraph_format.space_after = Pt(2)
            if rechtsbuendig:
                absatz.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            lauf = absatz.add_run(text)
            lauf.font.name = FONT
            lauf.font.size = SZ_WERT
            lauf.bold = True


def _fusszeile(dokument, angebot: McdonaldsAngebot) -> None:
    fall = angebot.fall
    text = (
        f"Angebot — {(fall.ordner_name if fall else '') or 'Standort'} — "
        f"{date.today():%d.%m.%Y}"
    )
    absatz = dokument.sections[0].footer.paragraphs[0]
    absatz.alignment = WD_ALIGN_PARAGRAPH.CENTER
    lauf = absatz.add_run(text)
    lauf.font.name = FONT
    lauf.font.size = SZ_FUSS
    lauf.font.color.rgb = GRAU


def erzeuge_angebot(angebot: McdonaldsAngebot) -> tuple[bytes, str]:
    """Baut das Angebotsdokument. Ergebnis: (Word-Datei, Dateiname).

    Gibt Bytes zurück und schreibt nicht selbst — dieselbe Aufteilung wie in
    ``projektbericht_generation``: Der Versand braucht die Bytes, die Ablage
    im Projektordner braucht die Datei, und beides zu trennen erspart ein
    Zwischenspeichern für den Anhang.
    """
    dokument = Document()
    _grundschrift(dokument)

    abschnitt = dokument.sections[0]
    abschnitt.page_width = Cm(21)
    abschnitt.page_height = Cm(29.7)
    abschnitt.left_margin = Cm(2.5)
    abschnitt.right_margin = Cm(2.0)
    abschnitt.top_margin = Cm(2.0)
    abschnitt.bottom_margin = Cm(2.0)

    fall = angebot.fall
    planer = angebot.fachplaner

    # ── Kopf ──
    _absatz(dokument, "Angebot zur Beauftragung", groesse=SZ_TITEL, fett=True,
            abstand_nach=Pt(2))
    _absatz(
        dokument,
        (angebot.betreff or "").strip()
        or f"{(fall.standort_name if fall else '') or 'Standort'} — "
           f"{_fmt_phase(angebot.leistungsphase)}",
        groesse=SZ_KOPF,
        abstand_nach=Pt(2),
    )
    _absatz(dokument, f"Stand: {date.today():%d.%m.%Y}", groesse=SZ_LABEL,
            farbe=GRAU, abstand_nach=Pt(14))

    # ── Empfänger ──
    if planer:
        _absatz(dokument, "An", groesse=SZ_LABEL, farbe=GRAU, abstand_nach=Pt(2))
        for zeile in (planer.name, planer.ansprechpartner, planer.adresse,
                      planer.email):
            if (zeile or "").strip():
                _absatz(dokument, zeile.strip(), abstand_nach=Pt(1))
        _absatz(dokument, abstand_nach=Pt(12))

    # ── Kernangaben ──
    _absatz(dokument, "Angaben zur Beauftragung", groesse=SZ_KOPF, fett=True,
            abstand_nach=Pt(6))
    _tabelle(dokument, kernangaben(angebot))
    _absatz(dokument, abstand_nach=Pt(12))

    # ── Mehrleistungen ──
    _mehrleistungen(dokument, angebot)

    # ── Hinweis, dass dies noch die Platzhalterfassung ist ──
    #
    # Absichtlich im Dokument und nicht nur im Code: Solange die echte
    # Vorlage fehlt, darf niemand dieses Blatt versehentlich für das
    # Bürodokument halten und ohne Prüfung hinausschicken.
    _absatz(dokument, abstand_nach=Pt(18))
    _absatz(
        dokument,
        "Vorläufige Fassung: Die Angebotsvorlage des Büros ist noch nicht "
        "eingearbeitet. Bitte vor dem Versand prüfen.",
        groesse=SZ_LABEL,
        farbe=GRAU,
    )

    _fusszeile(dokument, angebot)

    puffer = io.BytesIO()
    dokument.save(puffer)
    return puffer.getvalue(), dateiname(angebot)


def ablegen(angebot: McdonaldsAngebot, daten: bytes, name: str) -> Path:
    """Legt das Dokument in ``storage/output/mcdonalds`` ab und liefert den Pfad.

    Der Pfad gehört an das Angebot (``dokument_pfad``), damit er später ohne
    erneutes Erzeugen herunterzuladen ist.

    TODO McDonald's: Später soll das Dokument zusätzlich im Projektordner auf
    H: landen (``fall.ordner_pfad_h``). Der Pfad steht am Fall — es fehlt nur
    die Entscheidung, in welchen Unterordner des Musterordners.
    """
    ordner = settings.output_dir / ABLAGE
    ordner.mkdir(parents=True, exist_ok=True)
    ziel = ordner / f"{angebot.id}_{name}"
    ziel.write_bytes(daten)
    return ziel
