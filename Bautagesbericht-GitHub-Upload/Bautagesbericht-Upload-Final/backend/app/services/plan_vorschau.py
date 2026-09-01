"""Plan-Vorschau als Bild — Grundlage für das Setzen der Stecknadel.

Ein Plan wird als PDF oder als Bild hochgeladen. Damit im Browser auf jeden
Plan getippt werden kann (auch auf eine Seite eines mehrseitigen PDF), liefert
das Backend jede Planseite als **Bild** aus. Der Browser zeigt nur dieses Bild
und rechnet die Tippposition in Prozent der Bildfläche um — deshalb braucht das
Frontend keinen PDF-Betrachter und die Markierung sitzt auf jedem Gerät an
derselben Stelle des Plans.

Gerendert wird mit ``pypdfium2`` (kommt als Abhängigkeit von ``pdfplumber``
mit, reines Wheel ohne Systempakete — wichtig, weil das Docker-Image bewusst
schlank bleibt und z. B. kein Poppler/LibreOffice enthält). Fertige Vorschauen
werden neben dem Plan zwischengespeichert, damit das Blättern flüssig bleibt.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

from app.services.bilder import ist_bilddatei

# Zielbreite der Vorschau. Groß genug, um im Plan hineinzuzoomen und eine
# Position genau zu treffen, klein genug für den Abruf über Mobilfunk.
VORSCHAU_BREITE = 1600
JPEG_QUALITAET = 82
# Obergrenze für den Renderfaktor, damit ein sehr kleinformatiges PDF
# (z. B. A5-Detailplan) nicht in ein riesiges Bild gerendert wird.
MAX_SKALIERUNG = 6.0


def _vorschau_pfad(plan: Path, seite: int, breite: int) -> Path:
    ordner = plan.parent / "_vorschau"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner / f"{plan.stem}_s{seite}_b{breite}.jpg"


def seitenzahl(plan: Path) -> int:
    """Seitenzahl eines Plans. Bilder haben immer eine Seite."""
    if ist_bilddatei(plan.name):
        return 1
    try:
        import pypdfium2 as pdfium

        dokument = pdfium.PdfDocument(str(plan))
        try:
            return max(1, len(dokument))
        finally:
            dokument.close()
    except Exception:
        return 1


def rendere_seite(plan: Path, seite: int = 1,
                  breite: int = VORSCHAU_BREITE) -> Path | None:
    """Liefert den Pfad zur Vorschau einer Planseite (erzeugt sie bei Bedarf).

    Gibt ``None`` zurück, wenn der Plan nicht gelesen werden konnte.
    """
    if not plan.is_file():
        return None

    ziel = _vorschau_pfad(plan, seite, breite)
    if ziel.is_file() and ziel.stat().st_mtime >= plan.stat().st_mtime:
        return ziel

    if ist_bilddatei(plan.name):
        return _vorschau_aus_bild(plan, ziel, breite)
    return _vorschau_aus_pdf(plan, ziel, seite, breite)


def _vorschau_aus_bild(plan: Path, ziel: Path, breite: int) -> Path | None:
    try:
        with Image.open(plan) as bild:
            bild = ImageOps.exif_transpose(bild).convert("RGB")
            if bild.width > breite:
                hoehe = round(bild.height * breite / bild.width)
                bild = bild.resize((breite, hoehe), Image.Resampling.LANCZOS)
            bild.save(ziel, format="JPEG", quality=JPEG_QUALITAET, optimize=True)
    except Exception:
        return None
    return ziel


def _vorschau_aus_pdf(plan: Path, ziel: Path, seite: int,
                      breite: int) -> Path | None:
    try:
        import pypdfium2 as pdfium

        dokument = pdfium.PdfDocument(str(plan))
        try:
            index = min(max(seite, 1), len(dokument)) - 1
            pdf_seite = dokument[index]
            breite_punkte = pdf_seite.get_size()[0] or 1
            skalierung = min(breite / breite_punkte, MAX_SKALIERUNG)
            bitmap = pdf_seite.render(scale=skalierung)
            bild = bitmap.to_pil().convert("RGB")
            bild.save(ziel, format="JPEG", quality=JPEG_QUALITAET, optimize=True)
        finally:
            dokument.close()
    except Exception:
        return None
    return ziel
