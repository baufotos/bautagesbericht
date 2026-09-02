# Baut das verteilbare Windows-Paket "HPP-Baumanagement-App".
#
# HINWEIS ZUR KODIERUNG: UTF-8 MIT BOM. Windows PowerShell 5.1 liest .ps1 ohne
# BOM als ANSI — Umlaute zerbrechen dann die Zeichenketten.
#
# WAS ENTSTEHT
# ============
# Ein Ordner, den man kopieren kann und der ohne Installation läuft:
#
#   HPP-Baumanagement-App\
#     HPP-Baumanagement.exe      Startprogramm (Doppelklick)
#     einstellungen.txt          leer = alles lokal; für das Team ausfüllen
#     Zuerst-lesen.txt           Kurzanleitung
#     laufzeit\python\           portables Python (kein Setup nötig)
#     laufzeit\pakete\           die Python-Pakete des Backends
#     laufzeit\backend\          Anwendungscode, Word-Vorlagen, Oberfläche
#     daten\                     entsteht beim ersten Start
#
# WARUM SO
# ========
# Die Oberfläche ist statisch exportiert und wird von FastAPI mit ausgeliefert,
# deshalb enthält das Paket KEIN Node.js — das spart mehrere hundert Megabyte.
# Python liegt als portable Fassung daneben; auf dem Zielrechner muss nichts
# installiert werden und es sind keine Administratorrechte nötig.
#
# Nutzung:
#   .\erstellen.ps1                 baut nach ..\HPP-Baumanagement-App
#   .\erstellen.ps1 -Zip            packt zusätzlich ein ZIP zum Verteilen
#   .\erstellen.ps1 -Ziel D:\Temp\X anderer Ausgabeort

[CmdletBinding()]
param(
  [string]$Ziel = "",
  [switch]$Zip,
  # Nur Anwendung und Oberflaeche austauschen, Python und Pakete stehen lassen.
  # Dafuer gedacht, eine BENUTZTE Installation zu aktualisieren: Es werden
  # weder Daten angefasst noch 156 MB neu geladen, und gesperrte Dateien der
  # laufenden App (python .pyd) stoeren nicht.
  [switch]$NurAnwendung
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # sonst ueberdeckt der Download-Balken alles

$paketQuelle = $PSScriptRoot
$desktopDir  = Split-Path $paketQuelle -Parent
$projekt     = Split-Path $desktopDir -Parent
$frontend    = Join-Path $projekt "frontend"
$backend     = Join-Path $projekt "backend"

if ($Ziel -eq "") { $Ziel = Join-Path $desktopDir "HPP-Baumanagement-App" }

# Portables Python (schlanke Fassung ohne Debugsymbole, ~21 MB).
$pythonVersion = "3.12.14"
$pythonTag     = "20260814"
$pythonDatei   = "cpython-$pythonVersion+$pythonTag-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
$pythonUrl     = "https://github.com/astral-sh/python-build-standalone/releases/download/$pythonTag/" +
                 [uri]::EscapeDataString($pythonDatei)

# Nur die Pakete, die der Code wirklich importiert (plus psycopg fuer den
# gemeinsamen Betrieb mit zentraler Datenbank und anthropic fuer das Auslesen
# eingescannter Berichte). docxtpl ist im Projekt nicht in Benutzung.
$pakete = @(
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "sqlalchemy>=2.0",
  "pydantic[email]>=2.0",
  "pydantic-settings>=2.0",
  "python-multipart>=0.0.9",
  "httpx>=0.27",
  "pdfplumber>=0.11",
  "python-docx>=1.1",
  "pillow>=10.0",
  # HEIC/HEIF lesen zu koennen ist keine Kuer: iPhones fotografieren so, und
  # ohne dieses Paket landen deren Fotos unverarbeitet im Projektordner.
  "pillow-heif>=0.18",
  "pypdfium2>=4.18",
  "psycopg[binary]>=3.2",
  "anthropic>=0.40"
)

function Schritt($text) { Write-Host "==> $text" -ForegroundColor Cyan }

function Verkleinern($paketZiel) {
  # Aufraeumen: Testdaten, Zwischenspeicher und mitgelieferte Programme
  # brauchen wir im Paket nicht. Die 234 __pycache__-Ordner allein sind 35 MB,
  # die Python bei Bedarf selbst wieder anlegt - im Verteil-ZIP sind sie nur
  # Ballast fuer die Kollegen.
  Schritt "Paket verkleinern"
  $vorher = (Get-ChildItem $paketZiel -Recurse -File | Measure-Object -Property Length -Sum).Sum
  Get-ChildItem $paketZiel -Recurse -Directory -Include "__pycache__","tests","test" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  Get-ChildItem $paketZiel -Recurse -Include "*.pyc","*.pdb" -File -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
  $binOrdner = Join-Path $paketZiel "bin"
  if (Test-Path $binOrdner) { Remove-Item -Recurse -Force $binOrdner }
  $nachher = (Get-ChildItem $paketZiel -Recurse -File | Measure-Object -Property Length -Sum).Sum
  Write-Host ("   {0:N0} MB -> {1:N0} MB" -f ($vorher / 1MB), ($nachher / 1MB))
}

function PruefeImporte($laufzeit) {
  # Nach dem Installieren einmal wirklich importieren. Ein abgebrochenes
  # "pip install --target" hinterlaesst einen Ordner, der vollstaendig aussieht,
  # aber beim Doppelklick auf dem Buerorechner mit ModuleNotFoundError endet.
  # Genau das ist einmal passiert (annotated_doc, anyio) - deshalb pruefen wir
  # hier und nicht beim Kollegen.
  Schritt "Laufzeit pruefen (Importe)"
  $pythonExe = Join-Path $laufzeit "python\python.exe"
  $skript = Join-Path $PSScriptRoot "importe_pruefen.py"
  & $pythonExe $skript $laufzeit
  if ($LASTEXITCODE -ne 0) {
    throw "Die Laufzeit ist nicht startfaehig - siehe Liste oben. Das Paket wurde NICHT fertiggestellt."
  }
}

function EinstellungenBeilegen($ziel) {
  # Die einstellungen.txt ist die einzige Datei im Paket, die der Anwender
  # SELBST ausfuellt (zentrale Datenbank, Netzlaufwerk, Postausgangsserver).
  # Ein Neubau darf sie deshalb niemals blind ueberschreiben - fruehere
  # Fassungen taten das und haetten eine eingerichtete Team-Installation
  # stillschweigend auf Einzelplatz zurueckgesetzt.
  $vorlage = Join-Path $PSScriptRoot "einstellungen.txt"
  $vorhanden = Join-Path $ziel "einstellungen.txt"

  if (-not (Test-Path $vorhanden)) {
    Copy-Item $vorlage $ziel
    return
  }

  # Ausgefuellt heisst: mindestens ein Schluessel hat einen Wert.
  $werte = @{}
  foreach ($zeile in Get-Content $vorhanden -Encoding UTF8) {
    $text = $zeile.Trim()
    if ($text -eq "" -or $text.StartsWith("#") -or -not $text.Contains("=")) { continue }
    $teile = $text.Split("=", 2)
    $werte[$teile[0].Trim()] = $teile[1].Trim()
  }
  $gesetzt = @($werte.GetEnumerator() | Where-Object { $_.Value -ne "" } | ForEach-Object { $_.Key })

  if ($gesetzt.Count -eq 0) {
    # Nichts eingetragen - dann darf die aktuelle Vorlage nachruecken, damit
    # neu hinzugekommene Schluessel im Paket auftauchen.
    Copy-Item $vorlage $ziel -Force
    return
  }

  # Eingerichtet: Datei bleibt, wie sie ist. Nur melden, was die neue Vorlage
  # zusaetzlich anbietet - sonst merkt niemand, dass es neue Schalter gibt.
  $vorlagenSchluessel = @()
  foreach ($zeile in Get-Content $vorlage -Encoding UTF8) {
    $text = $zeile.Trim()
    if ($text -eq "" -or $text.StartsWith("#") -or -not $text.Contains("=")) { continue }
    $vorlagenSchluessel += $text.Split("=", 2)[0].Trim()
  }
  $neu = @($vorlagenSchluessel | Where-Object { -not $werte.ContainsKey($_) })

  Write-Host ("   einstellungen.txt bleibt unveraendert ({0} eigene(r) Eintrag/Eintraege: {1})" -f `
    $gesetzt.Count, ($gesetzt -join ", ")) -ForegroundColor Yellow
  if ($neu.Count -gt 0) {
    Write-Host ("   Die Vorlage kennt zusaetzlich: {0} - bei Bedarf von Hand nachtragen." -f ($neu -join ", ")) -ForegroundColor Yellow
  }
}

function AbholungBeilegen($ziel) {
  # Die Foto-Abholung gehoert mit ins Paket: Jedes Teammitglied, das die App
  # bekommt, kann damit auch die vom Handy hochgeladenen Fotos ins
  # Projektverzeichnis holen - und zwar auch dann, wenn der Rechner des
  # Kollegen aus ist. Der Server sorgt dafuer, dass jeder Satz nur einmal
  # abgeholt wird.
  $quelle = Join-Path (Split-Path -Parent $PSScriptRoot) "abholung"
  if (-not (Test-Path $quelle)) { return }

  $ordner = Join-Path $ziel "Foto-Abholung"
  if (-not (Test-Path $ordner)) { New-Item -ItemType Directory -Path $ordner | Out-Null }

  # Skripte immer erneuern, Einstellungsdateien nur anlegen, wenn sie fehlen -
  # sonst waeren nach jedem Update die eingetragenen Pfade weg.
  foreach ($datei in @("Baufotos-Abholen.ps1", "Aufgabe-Einrichten.ps1", "Zuerst-lesen.txt")) {
    $von = Join-Path $quelle $datei
    if (Test-Path $von) { Copy-Item $von $ordner -Force }
  }
  foreach ($datei in @("einstellungen.txt", "Projekt-Ausnahmen.txt")) {
    $von = Join-Path $quelle $datei
    $nach = Join-Path $ordner $datei
    if ((Test-Path $von) -and -not (Test-Path $nach)) { Copy-Item $von $nach }
  }
}

function ZipBauen($ordner) {
  $zipPfad = "$ordner.zip"
  Schritt "ZIP zum Verteilen erstellen"
  if (Test-Path $zipPfad) { Remove-Item $zipPfad -Force }

  # WICHTIG: Den Ordner "daten" NICHT mitpacken. Er entsteht erst beim Start
  # und enthaelt echte Projekte, Maengel und Fotos - die duerfen nicht
  # versehentlich an Kollegen verteilt werden. Deshalb wird gezielt
  # aufgezaehlt statt "alles ausser".
  $mitnehmen = Get-ChildItem $ordner | Where-Object { $_.Name -ne "daten" }
  Compress-Archive -Path $mitnehmen.FullName -DestinationPath $zipPfad

  $zipGroesse = (Get-Item $zipPfad).Length / 1MB
  Write-Host ("   {0}  ({1:N0} MB)" -f $zipPfad, $zipGroesse)
  Write-Host "   (ohne den Ordner 'daten' - der entsteht beim ersten Start)"
}

# ── 1. Oberfläche statisch exportieren ───────────────────────────────────────
Schritt "Oberflaeche exportieren (statischer Build)"
# Node wird nur zum Exportieren der Oberfläche gebraucht und liegt hier
# portabel, also nicht im Suchpfad. Gesucht wird an den Stellen, an denen es
# auf diesem Rechner schon gelegen hat: Eine neue Node-Fassung landet in einem
# Ordner mit neuer Versionsnummer, und ein fest eingetragener Pfad ließ das
# Skript dann mit "npm nicht gefunden" abbrechen — mitten im Update.
$nodeOrte = @(
  "$env:LOCALAPPDATA\Programs\nodejs",
  "$env:LOCALAPPDATA\node",
  "$env:ProgramFiles\nodejs"
)
$node = $null
foreach ($ort in $nodeOrte) {
  if (-not (Test-Path $ort)) { continue }
  if (Test-Path (Join-Path $ort "npm.cmd")) { $node = $ort; break }
  # Entpackte Fassungen liegen in einem Unterordner "node-vXX...-win-x64".
  # Absteigend sortiert, damit eine neuere Fassung gewinnt.
  $unter = Get-ChildItem $ort -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName "npm.cmd") } |
    Sort-Object Name -Descending
  if ($unter) { $node = $unter[0].FullName; break }
}
if (-not $node) {
  $gefunden = Get-Command npm -ErrorAction SilentlyContinue
  if (-not $gefunden) {
    throw ("npm nicht gefunden. Gesucht wurde in:`n  " +
           ($nodeOrte -join "`n  ") +
           "`nNode.js dorthin entpacken oder in den Suchpfad legen.")
  }
  $node = Split-Path $gefunden.Source -Parent
}
Write-Host "   Node: $node"
# npm.cmd ruft intern "node" auf und braucht es deshalb im Suchpfad. Bei einer
# portablen Node-Installation ist es das nicht — hier nachtragen.
if ($env:PATH -notlike "*$node*") { $env:PATH = "$node;$env:PATH" }
Push-Location $frontend
try {
  if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Schritt "  Abhaengigkeiten des Frontends installieren (einmalig)"
    & "$node\npm.cmd" ci --no-audit --no-fund | Out-Null
  }
  $env:NEXT_EXPORT = "1"
  & "$node\npm.cmd" run build | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Der Frontend-Build ist fehlgeschlagen." }
} finally {
  Remove-Item Env:NEXT_EXPORT -ErrorAction SilentlyContinue
  Pop-Location
}
$export = Join-Path $frontend "out"
if (-not (Test-Path (Join-Path $export "index.html"))) { throw "Export unvollstaendig: index.html fehlt." }

# ── 2. Startprogramm bauen ───────────────────────────────────────────────────
Schritt "Startprogramm uebersetzen"
& (Join-Path $desktopDir "quelle\bauen.ps1") | Out-Null
$exe = Join-Path $desktopDir "HPP-Baumanagement.exe"
if (-not (Test-Path $exe)) { throw "HPP-Baumanagement.exe wurde nicht erzeugt." }

# ── 3a. Kurzweg: nur Anwendung und Oberflaeche austauschen ───────────────────
if ($NurAnwendung) {
  if (-not (Test-Path (Join-Path $Ziel "laufzeit\python\python.exe"))) {
    throw "In '$Ziel' liegt keine vollstaendige Installation. Einmal ohne -NurAnwendung bauen."
  }
  Schritt "Anwendung und Oberflaeche austauschen (Python, Pakete und Daten bleiben)"
  $backendZiel = Join-Path $Ziel "laufzeit\backend"

  foreach ($teil in @("app", "templates", "static")) {
    $pfad = Join-Path $backendZiel $teil
    if (Test-Path $pfad) { Remove-Item -Recurse -Force $pfad }
  }
  Copy-Item (Join-Path $backend "app") $backendZiel -Recurse -Exclude "__pycache__"
  Copy-Item (Join-Path $backend "templates") $backendZiel -Recurse
  Copy-Item $export (Join-Path $backendZiel "static") -Recurse
  Get-ChildItem $backendZiel -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  Copy-Item (Join-Path $paketQuelle "server_starten.py") (Join-Path $Ziel "laufzeit") -Force

  # Startprogramm nur ersetzen, wenn es nicht gerade laeuft.
  try {
    Copy-Item $exe $Ziel -Force
    Write-Host "   Startprogramm ausgetauscht"
  } catch {
    Write-Host "   Startprogramm laeuft gerade - bitte App schliessen und erneut ausfuehren." -ForegroundColor Yellow
  }
  Copy-Item (Join-Path $paketQuelle "Zuerst-lesen.txt") $Ziel -Force
  EinstellungenBeilegen $Ziel
  AbholungBeilegen $Ziel

  Verkleinern (Join-Path $Ziel "laufzeit\pakete")
  PruefeImporte (Join-Path $Ziel "laufzeit")

  Write-Host ""
  Write-Host "Aktualisiert:" -ForegroundColor Green
  Write-Host ("   {0}" -f $Ziel)
  Write-Host "   Beim naechsten Start der App ist die neue Fassung da."

  # Auch der Kurzweg kann das Verteil-ZIP neu packen - sonst bekommen die
  # Kollegen weiter die alte Fassung.
  if ($Zip) { ZipBauen $Ziel }
  return
}

# ── 3. Zielordner vorbereiten ────────────────────────────────────────────────
Schritt "Zielordner vorbereiten: $Ziel"
# WICHTIG: Den Ordner "daten" NIEMALS anfassen. Er enthaelt echte Projekte,
# Maengel und Fotos. Ein Neubau des Pakets tauscht nur das Programm aus -
# frueher loeschte diese Zeile den ganzen Zielordner, was beim Aktualisieren
# einer benutzten Installation die gesamte Arbeit vernichtet haette.
if (Test-Path $Ziel) {
  Get-ChildItem $Ziel -Force | Where-Object { $_.Name -ne "daten" } |
    Remove-Item -Recurse -Force
  if (Test-Path (Join-Path $Ziel "daten")) {
    Write-Host "   (vorhandener Ordner 'daten' bleibt unberuehrt)" -ForegroundColor Yellow
  }
}
$laufzeit = Join-Path $Ziel "laufzeit"
New-Item -ItemType Directory -Force -Path $laufzeit | Out-Null

# ── 4. Portables Python holen ────────────────────────────────────────────────
$zwischenlager = Join-Path $env:TEMP "hpp-paket-zwischenlager"
New-Item -ItemType Directory -Force -Path $zwischenlager | Out-Null
$archiv = Join-Path $zwischenlager $pythonDatei
if (-not (Test-Path $archiv)) {
  Schritt "Portables Python herunterladen ($pythonVersion)"
  Invoke-WebRequest -Uri $pythonUrl -OutFile $archiv
} else {
  Schritt "Portables Python aus dem Zwischenlager"
}
Schritt "Python entpacken"
# tar liegt seit Windows 10 im System.
& tar -xzf $archiv -C $laufzeit
if ($LASTEXITCODE -ne 0) { throw "Entpacken fehlgeschlagen." }
$python = Join-Path $laufzeit "python\python.exe"
if (-not (Test-Path $python)) { throw "python.exe nicht im erwarteten Pfad: $python" }

# ── 5. Python-Pakete danebenlegen ────────────────────────────────────────────
Schritt "Python-Pakete installieren (dauert ein paar Minuten)"
$paketZiel = Join-Path $laufzeit "pakete"
& $python -m pip install --quiet --no-warn-script-location --target $paketZiel @pakete
if ($LASTEXITCODE -ne 0) { throw "pip install fehlgeschlagen." }

Verkleinern $paketZiel

# ── 6. Anwendungscode und Oberflaeche kopieren ───────────────────────────────
Schritt "Anwendung kopieren"
$backendZiel = Join-Path $laufzeit "backend"
New-Item -ItemType Directory -Force -Path $backendZiel | Out-Null
Copy-Item (Join-Path $backend "app") $backendZiel -Recurse -Exclude "__pycache__"
Copy-Item (Join-Path $backend "templates") $backendZiel -Recurse
Copy-Item $export (Join-Path $backendZiel "static") -Recurse
Get-ChildItem $backendZiel -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $paketQuelle "server_starten.py") $laufzeit

PruefeImporte $laufzeit

# ── 7. Startprogramm und Begleitdateien ──────────────────────────────────────
Schritt "Startprogramm und Anleitung beilegen"
Copy-Item $exe $Ziel
EinstellungenBeilegen $Ziel
Copy-Item (Join-Path $paketQuelle "Zuerst-lesen.txt") $Ziel
AbholungBeilegen $Ziel

# ── 8. Fertig ────────────────────────────────────────────────────────────────
$groesse = (Get-ChildItem $Ziel -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ""
Write-Host "Paket fertig:" -ForegroundColor Green
Write-Host ("   {0}" -f $Ziel)
Write-Host ("   {0:N0} Dateien, {1:N0} MB" -f `
  (Get-ChildItem $Ziel -Recurse -File).Count, ($groesse / 1MB))

if ($Zip) { ZipBauen $Ziel }

Write-Host ""
Write-Host "Naechster Schritt: im Zielordner HPP-Baumanagement.exe doppelklicken."
