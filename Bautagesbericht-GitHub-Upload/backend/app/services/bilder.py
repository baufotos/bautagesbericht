"""Bildverarbeitung für die Mängelfotos.

Zwei Aufgaben:

1. **Normalisieren beim Upload.** Handy-Fotos kommen mit 8–12 Megapixel und
   4–8 MB an. Das Frontend verkleinert bereits vor dem Upload (siehe
   ``frontend/src/lib/bildkompression.ts``), damit die Übertragung auf der
   Baustelle mit schlechtem Netz überhaupt durchläuft. Serverseitig wird
   trotzdem noch einmal begrenzt — als Sicherheitsnetz für Uploads, die nicht
   über die App kommen, und weil der kostenlose Render-Container nur eine
   kleine Festplatte hat.

2. **Vorschaubilder.** Die Übersichtsliste zeigt pro Mangel ein kleines
   Vorschaubild. Es wird beim ersten Abruf erzeugt und daneben abgelegt, damit
   nicht jedes Laden der Liste die Vollbilder durchs Netz schickt.

Pillow kommt als Abhängigkeit von ``pdfplumber`` ohnehin mit und ist in
``pyproject.toml`` zusätzlich direkt eingetragen, weil hier direkt damit
gearbeitet wird.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

from app.services import bildformate

# HEIC/HEIF bei Pillow anmelden, bevor das erste Foto geöffnet wird.
bildformate.registriere()

# Längste Kante, auf die ein Foto beim Upload begrenzt wird. 2000 px reichen
# für eine formatfüllende Abbildung im Word-Dokument (A4-Breite bei 300 dpi
# entspricht rund 2000 px) und für das Hineinzoomen am Bildschirm.
MAX_KANTE_UPLOAD = 2000
JPEG_QUALITAET = 82

# Kantenlänge der Vorschaubilder für Liste und Galerie.
MAX_KANTE_THUMBNAIL = 480
JPEG_QUALITAET_THUMBNAIL = 74

#: Angenommene Formate — die Liste steht zentral in ``bildformate``, damit
#: Baufotos, Mängelfotos und Berichtsfotos denselben Bestand annehmen.
BILD_ENDUNGEN = bildformate.BILD_ENDUNGEN


def ist_bilddatei(dateiname: str) -> bool:
    return bildformate.ist_bilddatei(dateiname)


def normalisiere_foto(rohdaten: bytes, dateiname: str) -> tuple[bytes, str]:
    """Dreht das Foto laut EXIF, begrenzt die Größe und speichert als JPEG.

    Gibt ``(bytes, dateiname)`` zurück. Kann Pillow das Bild nicht lesen
    (z. B. HEIC ohne passendes Plugin), bleiben Daten und Name unverändert —
    ein nicht verarbeitbares Foto soll die Erfassung auf der Baustelle nicht
    scheitern lassen.
    """
    try:
        with Image.open(io.BytesIO(rohdaten)) as bild:
            # EXIF-Orientierung anwenden: Hochformat-Fotos vom Handy liegen
            # sonst im Word-Dokument und im Browser gedreht.
            bild = ImageOps.exif_transpose(bild)
            # Transparenz auf Weiß legen statt auf Schwarz — ein PNG mit
            # durchsichtigem Hintergrund würde sonst zum dunklen Klotz.
            if bild.mode in ("RGBA", "LA", "P"):
                mit_alpha = bild.convert("RGBA")
                hintergrund = Image.new("RGB", mit_alpha.size, (255, 255, 255))
                hintergrund.paste(mit_alpha, mask=mit_alpha.split()[-1])
                bild = hintergrund
            else:
                bild = bild.convert("RGB")
            bild.thumbnail(
                (MAX_KANTE_UPLOAD, MAX_KANTE_UPLOAD), Image.Resampling.LANCZOS
            )
            puffer = io.BytesIO()
            bild.save(puffer, format="JPEG", quality=JPEG_QUALITAET, optimize=True)
    except Exception:
        return rohdaten, dateiname

    neuer_name = f"{Path(dateiname).stem or 'foto'}.jpg"
    return puffer.getvalue(), neuer_name


def _thumbnail_pfad(original: Path) -> Path:
    return original.with_name(f"{original.stem}.thumb.jpg")


def thumbnail(original: Path) -> Path | None:
    """Pfad zum Vorschaubild; wird beim ersten Aufruf erzeugt.

    Gibt ``None`` zurück, wenn kein Vorschaubild erzeugt werden konnte — der
    Aufrufer liefert dann das Original aus.
    """
    if not original.is_file():
        return None

    ziel = _thumbnail_pfad(original)
    if ziel.is_file() and ziel.stat().st_mtime >= original.stat().st_mtime:
        return ziel

    try:
        with Image.open(original) as bild:
            bild = ImageOps.exif_transpose(bild)
            bild = bild.convert("RGB")
            bild.thumbnail(
                (MAX_KANTE_THUMBNAIL, MAX_KANTE_THUMBNAIL), Image.Resampling.LANCZOS
            )
            bild.save(ziel, format="JPEG", quality=JPEG_QUALITAET_THUMBNAIL, optimize=True)
    except Exception:
        return None

    return ziel


def thumbnail_bytes(daten: bytes) -> bytes | None:
    """Vorschaubild aus Bytes — für Fotos, die im Objektspeicher liegen.

    Dort gibt es keinen Pfad, an dem sich eine Vorschau zwischenspeichern
    ließe; sie wird bei jedem Abruf frisch berechnet. Das ist vertretbar, weil
    die Galerie ohnehin nur die sichtbaren Kacheln lädt und der Browser das
    Ergebnis einen Tag lang behält (Cache-Control im Router).

    ``None``, wenn sich nichts erzeugen ließ — dann liefert der Aufrufer das
    Bild in voller Größe aus.
    """
    try:
        with Image.open(io.BytesIO(daten)) as bild:
            bild = ImageOps.exif_transpose(bild)
            bild = bild.convert("RGB")
            bild.thumbnail(
                (MAX_KANTE_THUMBNAIL, MAX_KANTE_THUMBNAIL), Image.Resampling.LANCZOS
            )
            puffer = io.BytesIO()
            bild.save(puffer, format="JPEG",
                      quality=JPEG_QUALITAET_THUMBNAIL, optimize=True)
            return puffer.getvalue()
    except Exception:
        return None


def loesche_mit_thumbnail(original: Path) -> None:
    """Entfernt Foto und zugehöriges Vorschaubild."""
    for pfad in (original, _thumbnail_pfad(original)):
        try:
            if pfad.is_file():
                pfad.unlink()
        except OSError:
            # Dateisystemfehler dürfen das Löschen des Datensatzes nicht
            # verhindern (gleiche Haltung wie in app.services.cleanup).
            pass
