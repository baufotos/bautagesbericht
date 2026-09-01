"""Texterkennung mit der OCR-Maschine, die in Windows steckt.

WARUM DAS DIE RICHTIGE STELLE IST
=================================
Die Berichte der Firmen kommen oft als Scan: ein PDF, in dem jede Seite ein
Bild ist. Für die App ist so eine Datei stumm — kein Text, also auch kein
Datum, keine Firma, keine Leistung. Bis hierher gab es dafür nur einen Weg,
die Anthropic-Schnittstelle, und die braucht einen Schlüssel, den auf der
Baustelle niemand hat.

Windows bringt seit Windows 10 eine eigene Texterkennung mit
(``Windows.Media.Ocr``), auf deutschen Systemen mit deutschem Sprachmodell.
Sie ist bei **gedrucktem** Text sehr gut — und genau das sind die Formblätter
der Nachunternehmer, auch wenn sie als Bild ankommen. Sie kostet nichts, läuft
ohne Internet und ist auf jedem Bürorechner schon da.

Angesteuert über PowerShell, genau wie Word in ``word_pdf`` — das Paket soll
keine zusätzliche Abhängigkeit mitschleppen.

WAS SIE NICHT KANN
==================
Handschrift. Dafür ist die Windows-Maschine nicht gebaut; sie liefert dann
Buchstabensalat oder gar nichts. Handschriftliche Berichte brauchen weiterhin
die Anthropic-Schnittstelle (siehe ``pdf_extraction``). Die Reihenfolge ist
deshalb: erst Textebene, dann Anthropic (falls Schlüssel da), dann Windows-OCR.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

#: Eine Seite braucht auf einem Bürorechner ein bis zwei Sekunden. Dauert es
#: länger als das hier, stimmt etwas nicht und der Aufruf wird abgebrochen.
ZEITGRENZE_SEKUNDEN = 90

#: Ergebnis von ``verfuegbar()`` — die Prüfung startet PowerShell und soll
#: nicht bei jedem Bild erneut laufen.
_verfuegbar: bool | None = None

# Die WinRT-Aufrufe sind asynchron; in PowerShell braucht es dafür den
# AsTask-Umweg. Die Zeilen werden nach oberer Kante sortiert ausgegeben:
# Windows liefert Textblöcke in der Reihenfolge, in der es sie findet, nicht
# von oben nach unten — für "Datum:" und den Wert daneben ist die Reihenfolge
# aber genau das, worauf es ankommt.
_SKRIPT = r"""
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Warte($vorgang, $typ) {
  $asTask = $asTaskGeneric.MakeGenericMethod($typ)
  $aufgabe = $asTask.Invoke($null, @($vorgang))
  $aufgabe.Wait(-1) | Out-Null
  $aufgabe.Result
}

$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]

$maschine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $maschine) {
  $maschine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage(
    (New-Object Windows.Globalization.Language "de-DE"))
}
if (-not $maschine) { throw "Keine OCR-Sprache verfuegbar" }

$ausgabe = New-Object System.Text.StringBuilder
foreach ($pfad in Get-Content -LiteralPath "__LISTE__" -Encoding UTF8) {
  if (-not $pfad) { continue }
  $datei = Warte ([Windows.Storage.StorageFile]::GetFileFromPathAsync($pfad)) ([Windows.Storage.StorageFile])
  $strom = Warte ($datei.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $dekoder = Warte ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($strom)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bitmap = Warte ($dekoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $ergebnis = Warte ($maschine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

  $zeilen = @()
  foreach ($zeile in $ergebnis.Lines) {
    # Words ist eine WinRT-Sammlung; @(...) macht daraus ein PowerShell-Array,
    # ohne das liefert der Indexzugriff das ganze Objekt statt eines Wortes.
    $woerter = @($zeile.Words)
    $oben = 0
    $links = 0
    if ($woerter.Count -gt 0) {
      $ecke = $woerter[0].BoundingRect
      $oben = [int][math]::Round($ecke.Top)
      $links = [int][math]::Round($ecke.Left)
    }
    $zeilen += [PSCustomObject]@{ Oben = $oben; Links = $links; Text = $zeile.Text }
  }
  foreach ($z in ($zeilen | Sort-Object Oben, Links)) {
    $null = $ausgabe.AppendLine($z.Text)
  }
  $null = $ausgabe.AppendLine("__SEITENENDE__")
  $strom.Dispose()
}
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::Out.Write($ausgabe.ToString())
"""

SEITENTRENNER = "__SEITENENDE__"


def _ist_windows() -> bool:
    return sys.platform.startswith("win")


def verfuegbar() -> bool:
    """Kann dieser Rechner Text aus Bildern lesen?

    Das Ergebnis wird gemerkt: Die Prüfung startet PowerShell und würde sonst
    bei jedem Seitenbild erneut laufen.
    """
    global _verfuegbar
    if _verfuegbar is not None:
        return _verfuegbar
    if not _ist_windows():
        _verfuegbar = False
        return False
    try:
        ergebnis = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "try { $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, "
             "ContentType=WindowsRuntime]; "
             "if ([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages.Count "
             "-gt 0) { 'ja' } else { 'nein' } } catch { 'nein' }"],
            capture_output=True, text=True, timeout=60,
        )
        _verfuegbar = "ja" in (ergebnis.stdout or "")
    except (OSError, subprocess.SubprocessError):
        _verfuegbar = False
    return _verfuegbar


def sprachen() -> list[str]:
    """Welche Sprachen die Windows-Erkennung anbietet — für Hinweistexte."""
    if not _ist_windows():
        return []
    try:
        ergebnis = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, "
             "ContentType=WindowsRuntime]; "
             "[Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | "
             "ForEach-Object { $_.LanguageTag }"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [z.strip() for z in (ergebnis.stdout or "").splitlines() if z.strip()]


def text_aus_bildern(bilder: list[Path]) -> list[str]:
    """Erkennt den Text mehrerer Bilder in einem PowerShell-Start.

    Ein Aufruf je Seite würde bei einem zwanzigseitigen Scan zwanzig Mal
    PowerShell hochfahren — das dauert länger als die Erkennung selbst.
    Gibt je Bild einen Text zurück, in derselben Reihenfolge; bei einem Fehler
    eine Liste leerer Zeichenketten.
    """
    if not bilder or not verfuegbar():
        return ["" for _ in bilder]

    with tempfile.TemporaryDirectory(prefix="hpp-ocr-") as ordner:
        basis = Path(ordner)
        liste = basis / "seiten.txt"
        liste.write_text("\n".join(str(p) for p in bilder), encoding="utf-8")

        skript = basis / "ocr.ps1"
        skript.write_text(
            _SKRIPT.replace("__LISTE__", str(liste).replace("\\", "\\\\")),
            encoding="utf-8",
        )

        try:
            ergebnis = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-File", str(skript)],
                capture_output=True, timeout=ZEITGRENZE_SEKUNDEN * max(1, len(bilder)),
            )
        except (OSError, subprocess.SubprocessError):
            return ["" for _ in bilder]

    roh = (ergebnis.stdout or b"").decode("utf-8", errors="replace")
    # PowerShell schreibt CRLF. Ohne das Vereinheitlichen haengt an jeder
    # Zeile ein Wagenruecklauf, der spaeter in Ortsangaben und
    # Leistungstexten wieder auftaucht ("4.OG Ost" mit Steuerzeichen).
    roh = roh.replace(chr(13) + chr(10), chr(10)).replace(chr(13), chr(10))
    seiten = [t.strip(chr(10)) for t in roh.split(SEITENTRENNER)]
    # Der letzte Abschnitt hinter dem letzten Trenner ist leer.
    seiten = seiten[:len(bilder)]
    while len(seiten) < len(bilder):
        seiten.append("")
    return seiten


def text_aus_bild(bild: Path) -> str:
    ergebnis = text_aus_bildern([bild])
    return ergebnis[0] if ergebnis else ""
