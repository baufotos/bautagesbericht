"""PDF-Seiten als Bilder rendern — eine Seite zur Zeit.

WARUM ES DIESES MODUL GIBT
==========================
``pypdfium2`` hält jede Seite, die über ``dokument[i]`` geöffnet wurde, bis
zum ``dokument.close()`` im Speicher. Wer in einer Schleife rendert, sammelt
also das ganze Dokument an, ohne es zu merken — der Code sieht aus, als würde
er Seite für Seite arbeiten.

Gemessen an einem zwölfseitigen Scan (A4, 300 dpi), Grundlast des Backends
104 MB:

    ohne Schließen   +12 MB je Seite, linear   ->  238 MB nach 12 Seiten
    mit  Schließen   flach                     ->  136 MB nach 12 Seiten

Auf Render (kostenloser Plan) hat der ganze Container **512 MB**, und darin
läuft neben dem Backend auch noch Next.js mit rund 100 MB. Bei
``seitenlesung.MAX_SEITEN`` = 40 Seiten wären es hochgerechnet über 580 MB
allein für das Backend: Der Linux-Speicherwächter hat uvicorn abgeräumt,
Next.js lief weiter und beantwortete jeden ``/api``-Aufruf mit seinem eigenen
``Internal Server Error`` — genau die Meldung, die beim Erkennen der Tage in
der Oberfläche stand. Der Container fuhr danach neu hoch (siehe
``start.sh``), weshalb hinterher alles wieder in Ordnung schien.

Deshalb geht ab jetzt **jedes** seitenweise Rendern durch ``seiten()``.

WIE ES BENUTZT WIRD
===================
::

    for nummer, bild in seiten(pfad, dpi=300, max_seiten=12):
        puffer = io.BytesIO()
        bild.save(puffer, format="JPEG")

**Das Bild gilt nur innerhalb des Schleifendurchlaufs.** Danach werden Seite
und Bildpuffer von pdfium freigegeben; ``to_pil()`` kann auf denselben
Speicher zeigen. Wer ein Bild behalten will, behält eine eigene Kopie —
Speichern, ``crop()``, ``resize()`` und ``convert()`` in einen anderen Modus
liefern ohnehin eigene Daten. Genau so arbeiten alle Aufrufer.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


def _schliesse(gegenstand) -> None:
    """Gibt eine pdfium-Seite oder einen Bildpuffer frei.

    Über ``getattr`` und nicht direkt, weil ``pypdfium2`` nur mit
    ``>=4.18`` festgelegt ist (siehe ``pyproject.toml``): Die Fassungen 4 und
    5 räumen unterschiedlich auf, und ein fehlendes ``close`` darf das
    Rendern nicht zum Fehler machen — dann bliebe der Speicher eben stehen,
    wie vorher.
    """
    schliessen = getattr(gegenstand, "close", None)
    if callable(schliessen):
        try:
            schliessen()
        except Exception:
            pass


def seitenzahl(pfad: Path) -> int:
    """Wie viele Seiten das PDF hat. ``0``, wenn es nicht zu lesen ist."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return 0
    try:
        dokument = pdfium.PdfDocument(str(pfad))
    except Exception:
        return 0
    try:
        return len(dokument)
    finally:
        _schliesse(dokument)


def seiten(pfad: Path, dpi: float = 200,
           max_seiten: int | None = None,
           nummern: list[int] | None = None) -> Iterator[tuple[int, object]]:
    """Rendert die Seiten des PDFs und gibt ``(nummer, bild)`` zurück.

    ``nummer`` ist nullbasiert und bezeichnet die Seite im Dokument — bei
    ``nummern`` also nicht die Position in der Schleife.

    ``nummern`` wählt einzelne Seiten aus (nullbasiert); ohne Angabe werden
    alle gerendert, höchstens aber ``max_seiten``. Seiten, die außerhalb des
    Dokuments liegen, werden übergangen; eine Seite, an der pdfium selbst
    scheitert, beendet den Lauf nicht — ein einzelnes kaputtes Blatt darf
    einen Wochenstapel nicht wertlos machen.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return
    try:
        dokument = pdfium.PdfDocument(str(pfad))
    except Exception:
        return

    try:
        vorhanden = len(dokument)
        if nummern is None:
            gewaehlt = range(vorhanden if max_seiten is None
                             else min(vorhanden, max_seiten))
        else:
            gewaehlt = [n for n in nummern if 0 <= n < vorhanden]
            if max_seiten is not None:
                gewaehlt = gewaehlt[:max_seiten]

        for nummer in gewaehlt:
            seite = bildpuffer = None
            try:
                seite = dokument[nummer]
                bildpuffer = seite.render(scale=dpi / 72)
                bild = bildpuffer.to_pil()
            except Exception:
                _schliesse(bildpuffer)
                _schliesse(seite)
                continue
            try:
                yield nummer, bild
            finally:
                # Erst NACH dem Durchlauf des Aufrufers — bis dahin kann das
                # Bild auf diesen Speicher zeigen.
                _schliesse(bildpuffer)
                _schliesse(seite)
    finally:
        _schliesse(dokument)
