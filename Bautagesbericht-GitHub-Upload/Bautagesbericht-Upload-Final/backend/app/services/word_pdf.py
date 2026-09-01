"""Word-Dokument nach PDF — nur dort, wo Word installiert ist.

WARUM DAS EINE SONDERSTELLUNG IST
=================================
Die App erzeugt ihre Dokumente mit python-docx, also ohne Word. Für ein PDF
braucht es dagegen einen Umbruch-Algorithmus — den hat nur ein Textprogramm.
Auf dem Bürorechner läuft die App im Windows-Paket, dort **ist** Word; auf dem
Server (Linux) nicht.

Deshalb: Das Word-Dokument ist immer die verbindliche Ausgabe. Ein PDF gibt es
zusätzlich, wenn Word erreichbar ist. Fehlt es, sagt die Oberfläche das klar,
statt eine kaputte Datei anzubieten.

Angesteuert wird Word über PowerShell und nicht über ``pywin32``: Das Paket
soll keine zusätzliche Abhängigkeit mitschleppen, und PowerShell ist auf jedem
Windows vorhanden.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

#: Wie lange auf Word gewartet wird. Ein Bericht mit vielen Fotos braucht
#: durchaus 30 Sekunden; danach stimmt etwas nicht.
ZEITGRENZE_SEKUNDEN = 180

#: 17 = wdExportFormatPDF.
_SKRIPT = r"""
$ErrorActionPreference = "Stop"
$quelle = "{quelle}"
$ziel = "{ziel}"
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {{
  $dok = $word.Documents.Open($quelle, $false, $false)
  $null = $dok.Fields.Update()
  $dok.ExportAsFixedFormat($ziel, 17)
  $dok.Close(0)
}} finally {{
  $word.Quit()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}}
"""


def word_vorhanden() -> bool:
    """Ist Word auf diesem Rechner ansteuerbar?

    Wird von der Oberfläche gefragt, damit der PDF-Knopf gar nicht erst
    erscheint, wo er nicht funktionieren kann.
    """
    if not _ist_windows():
        return False
    try:
        ergebnis = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "try { $w = New-Object -ComObject Word.Application; $w.Quit(); "
             "'ja' } catch { 'nein' }"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return "ja" in (ergebnis.stdout or "")


def _ist_windows() -> bool:
    import sys
    return sys.platform.startswith("win")


class PdfNichtMoeglich(RuntimeError):
    """Word steht nicht zur Verfügung — mit einem Text für die Oberfläche."""


def nach_pdf(docx: bytes) -> bytes:
    """Wandelt ein Word-Dokument in ein PDF. Wirft, wenn Word fehlt.

    Die Felder werden vor dem Export aktualisiert — sonst stünden im
    Inhaltsverzeichnis die Platzhalterzahlen aus der Erzeugung statt der
    echten Seitenzahlen.
    """
    if not _ist_windows():
        raise PdfNichtMoeglich(
            "PDF entsteht über Microsoft Word; auf diesem Server läuft kein "
            "Windows. Das Word-Dokument lässt sich herunterladen und dort "
            "als PDF speichern."
        )

    with tempfile.TemporaryDirectory(prefix="hpp-pdf-") as ordner:
        quelle = Path(ordner) / "bericht.docx"
        ziel = Path(ordner) / "bericht.pdf"
        quelle.write_bytes(docx)

        skript = _SKRIPT.format(quelle=str(quelle), ziel=str(ziel))
        try:
            ergebnis = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", skript],
                capture_output=True, text=True, timeout=ZEITGRENZE_SEKUNDEN,
            )
        except subprocess.TimeoutExpired as fehler:
            raise PdfNichtMoeglich(
                f"Word hat nach {ZEITGRENZE_SEKUNDEN} Sekunden nicht geantwortet. "
                f"Läuft vielleicht noch ein Word-Fenster mit einem Dialog?"
            ) from fehler
        except OSError as fehler:
            raise PdfNichtMoeglich(f"PowerShell nicht startbar: {fehler}") from fehler

        if ergebnis.returncode != 0 or not ziel.is_file():
            meldung = (ergebnis.stderr or ergebnis.stdout or "").strip()
            raise PdfNichtMoeglich(
                "Word konnte kein PDF erzeugen. "
                + (meldung.splitlines()[-1] if meldung else "Ist Word installiert?")
            )
        return ziel.read_bytes()
