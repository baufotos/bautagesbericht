"""Word-Dokument nach PDF — über Microsoft Word (Windows) oder LibreOffice (Server).

WARUM DAS EINE SONDERSTELLUNG IST
=================================
Die App erzeugt ihre Dokumente mit python-docx, also ohne Textprogramm. Für
ein PDF braucht es dagegen einen Umbruch-Algorithmus — den hat nur ein
Textprogramm. Deshalb gibt es hier zwei Wege, und welcher genommen wird,
entscheidet der Rechner, auf dem die App gerade läuft:

    Bürorechner (Windows-Paket)   Microsoft Word über PowerShell/COM
    Server (Linux-Container)      LibreOffice Writer, kopflos

Der Word-Weg ist der ältere und bleibt für das Windows-Paket unverändert der
erste Griff — er trifft die Hausvorlagen am genauesten. LibreOffice ist der
Weg für die Website, wo es kein Word gibt; unter Windows springt es nur
zusätzlich ein, wenn Word fehlt (vorher gab es dort eine Fehlermeldung).

Das Word-Dokument bleibt in beiden Fällen die verbindliche Ausgabe. Ist gar
kein Textprogramm erreichbar, sagt die Oberfläche das klar, statt eine kaputte
Datei anzubieten.

SEITENZAHLEN UND VERZEICHNIS
============================
Die Erzeuger setzen ``PAGE``/``NUMPAGES``/``PAGEREF`` als Word-Felder und
stellen das Dokument auf „Felder beim Öffnen aktualisieren"
(``w:updateFields``, siehe projektbericht_generation). Word bekommt zusätzlich
ein ausdrückliches ``Fields.Update()``; LibreOffice wertet ``w:updateFields``
beim Laden selbst aus. Beide Wege liefern deshalb echte Seitenzahlen statt der
Platzhalter aus der Erzeugung.

Angesteuert wird Word über PowerShell und nicht über ``pywin32``: Das Paket
soll keine zusätzliche Abhängigkeit mitschleppen, und PowerShell ist auf jedem
Windows vorhanden.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

#: Wie lange auf das Textprogramm gewartet wird. Ein Bericht mit vielen Fotos
#: braucht durchaus 30 Sekunden; danach stimmt etwas nicht. LibreOffice legt
#: beim allerersten Aufruf zusätzlich sein Benutzerprofil an.
ZEITGRENZE_SEKUNDEN = 180

#: Namen, unter denen LibreOffice auf dem Suchpfad stehen kann.
_LIBREOFFICE_NAMEN = ("soffice", "libreoffice")

#: LibreOffice verträgt keine zwei gleichzeitigen Läufe auf demselben
#: Benutzerprofil — der zweite bricht mit einer Sperrmeldung ab. Die
#: Umwandlung ist selten und dauert Sekunden, deshalb reicht es, sie
#: nacheinander laufen zu lassen, statt je Aufruf ein neues Profil anzulegen
#: (das kostete jedes Mal mehrere Sekunden).
_LIBREOFFICE_SPERRE = threading.Lock()

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


class PdfNichtMoeglich(RuntimeError):
    """Kein Textprogramm erreichbar — mit einem Text für die Oberfläche."""


def _ist_windows() -> bool:
    import sys
    return sys.platform.startswith("win")


# ---------------------------------------------------------------------------
# Was kann dieser Rechner?
# ---------------------------------------------------------------------------

def word_vorhanden() -> bool:
    """Ist Microsoft Word auf diesem Rechner ansteuerbar?

    Absichtlich eng: Diese Frage bedeutet weiterhin genau „Word", nicht
    „irgendein Textprogramm". Die Tests im Backend bauen damit ihre
    Beispiel-PDFs und überspringen sich, wo Word fehlt. Für die Frage, ob die
    Oberfläche einen PDF-Knopf anbieten darf, ist ``pdf_moeglich`` zuständig.
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


def libreoffice_pfad() -> str | None:
    """Pfad zur LibreOffice-Programmdatei — oder None, wenn es sie nicht gibt.

    Im Docker-Image der Website ist LibreOffice installiert (siehe
    ``Dockerfile``); auf dem Bürorechner in aller Regel nicht.
    """
    for name in _LIBREOFFICE_NAMEN:
        pfad = shutil.which(name)
        if pfad:
            return pfad
    return None


def pdf_moeglich() -> bool:
    """Kann dieser Rechner überhaupt ein PDF erzeugen?

    Das ist die Frage, die die Oberfläche stellen muss, bevor sie einen
    PDF-Knopf anbietet — beantwortet von Word **oder** LibreOffice.
    """
    return word_vorhanden() or libreoffice_pfad() is not None


def pdf_weg() -> str:
    """Welches Textprogramm das PDF erzeugen würde — für Hinweise und Prüfung."""
    if word_vorhanden():
        return "word"
    if libreoffice_pfad() is not None:
        return "libreoffice"
    return "keins"


# ---------------------------------------------------------------------------
# Die Umwandlung
# ---------------------------------------------------------------------------

def nach_pdf(docx: bytes) -> bytes:
    """Wandelt ein Word-Dokument in ein PDF. Wirft, wenn kein Weg da ist.

    Reihenfolge: Auf Windows zuerst Word — das ist der Weg, den das
    Bürorechner-Paket seit jeher geht, und er bleibt unangetastet. Erst wenn
    Word dort **nicht** erreichbar ist, wird ein etwa vorhandenes LibreOffice
    versucht; früher gab es an dieser Stelle nur eine Fehlermeldung. Auf dem
    Server gibt es kein Word, dort führt der Weg direkt zu LibreOffice.
    """
    if _ist_windows():
        try:
            return _ueber_word(docx)
        except PdfNichtMoeglich:
            if libreoffice_pfad() is None:
                raise
            return _ueber_libreoffice(docx)

    if libreoffice_pfad() is None:
        raise PdfNichtMoeglich(
            "Auf diesem Server ist kein Textprogramm für die PDF-Erzeugung "
            "eingerichtet (weder Microsoft Word noch LibreOffice). Das "
            "Word-Dokument lässt sich herunterladen und dort als PDF "
            "speichern."
        )
    return _ueber_libreoffice(docx)


def _ueber_word(docx: bytes) -> bytes:
    """Der Windows-Weg: Word über PowerShell fernsteuern.

    Die Felder werden vor dem Export aktualisiert — sonst stünden im
    Inhaltsverzeichnis die Platzhalterzahlen aus der Erzeugung statt der
    echten Seitenzahlen.
    """
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


def _profil_ordner() -> Path:
    """Eigenes LibreOffice-Benutzerprofil für diesen Prozess.

    Ohne eigenes Profil greift LibreOffice auf ``$HOME/.config`` zu — im
    Container gehört das root, und ein zweiter Aufruf stolpert über die
    Sperrdatei des ersten. Die Prozessnummer im Namen hält außerdem mehrere
    uvicorn-Prozesse auseinander, falls der Dienst später mit ``--workers``
    startet.
    """
    return Path(tempfile.gettempdir()) / f"hpp-libreoffice-profil-{os.getpid()}"


def _ueber_libreoffice(docx: bytes) -> bytes:
    """Der Server-Weg: LibreOffice Writer kopflos.

    ``--convert-to pdf`` schreibt die Ausgabe neben die Quelle in ``--outdir``
    und benennt sie nach der Quelle. Der Rückgabewert von LibreOffice ist
    nicht verlässlich (auch nach Fehlern kommt gern 0), deshalb entscheidet
    allein, ob die Zieldatei danach da ist.
    """
    programm = libreoffice_pfad()
    if programm is None:                     # zwischen Prüfung und Aufruf entfernt
        raise PdfNichtMoeglich("LibreOffice ist nicht mehr auffindbar.")

    with tempfile.TemporaryDirectory(prefix="hpp-pdf-") as ordner:
        basis = Path(ordner)
        quelle = basis / "bericht.docx"
        ziel = basis / "bericht.pdf"
        quelle.write_bytes(docx)

        befehl = [
            programm,
            f"-env:UserInstallation={_profil_ordner().as_uri()}",
            "--headless", "--invisible", "--norestore",
            "--nolockcheck", "--nodefault", "--nofirststartwizard",
            "--convert-to", "pdf:writer_pdf_Export",
            "--outdir", str(basis),
            str(quelle),
        ]
        try:
            with _LIBREOFFICE_SPERRE:
                ergebnis = subprocess.run(
                    befehl, capture_output=True, text=True,
                    timeout=ZEITGRENZE_SEKUNDEN,
                )
        except subprocess.TimeoutExpired as fehler:
            raise PdfNichtMoeglich(
                f"LibreOffice hat nach {ZEITGRENZE_SEKUNDEN} Sekunden nicht "
                f"geantwortet. Bitte das Word-Dokument herunterladen."
            ) from fehler
        except OSError as fehler:
            raise PdfNichtMoeglich(
                f"LibreOffice nicht startbar: {fehler}"
            ) from fehler

        if not ziel.is_file():
            meldung = (ergebnis.stderr or ergebnis.stdout or "").strip()
            raise PdfNichtMoeglich(
                "LibreOffice konnte kein PDF erzeugen. "
                + (meldung.splitlines()[-1] if meldung
                   else "Das Word-Dokument steht weiterhin zum Download bereit.")
            )
        return ziel.read_bytes()
