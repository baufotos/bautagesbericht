# Bringt den aktuellen Quellcode auf die Website.
#
# HINWEIS ZUR KODIERUNG: Diese Datei kommt ohne Umlaute aus. Damit ist es egal,
# ob Windows PowerShell sie als UTF-8 oder als ANSI liest.
#
# WAS DAS SKRIPT MACHT
# ====================
#   1. Kopiert den Quellcode in die Git-Arbeitskopie.
#   2. Committet und schiebt zu GitHub.
#   3. Render merkt die Aenderung selbst und baut neu (5 bis 10 Minuten).
#
# WARUM DER UMWEG UEBER EINE ZWEITE ARBEITSKOPIE
# ==============================================
# Im GitHub-Repo liegt alles in einem Unterordner "Bautagesbericht-GitHub-Upload"
# - so ist es damals per Drag & Drop hochgeladen worden, und der Render-Dienst
# ist auf genau diesen Pfad eingestellt. Wuerde man die Dateien in die
# Repo-Wurzel schieben, faende Render das Dockerfile nicht mehr und der Dienst
# waere tot. Deshalb bleibt die Schachtelung, und dieses Skript legt den
# Quellcode an die Stelle, die Render erwartet.
#
# WAS NICHT MITGEHT
# =================
# node_modules, Build-Zwischenstaende, __pycache__, das fertige Windows-Paket
# und backend/storage (dort liegen echte Fotos und Dokumente). Die Website baut
# sich das Frontend im Container selbst.
#
# Nutzung:
#   .\Website-aktualisieren.ps1
#   .\Website-aktualisieren.ps1 -Nachricht "Kurz was sich geaendert hat"
#   .\Website-aktualisieren.ps1 -NurZeigen     nichts senden, nur auflisten

[CmdletBinding()]
param(
  [string]$Nachricht = "",
  [switch]$NurZeigen
)

$ErrorActionPreference = "Stop"

$quelle = Split-Path -Parent $PSScriptRoot
$repo   = Join-Path (Split-Path -Parent $quelle) "bautagesbericht-git"
$ziel   = Join-Path $repo "Bautagesbericht-GitHub-Upload"

function Schritt($text) { Write-Host "==> $text" -ForegroundColor Cyan }

if (-not (Test-Path (Join-Path $repo ".git"))) {
  throw "Keine Arbeitskopie in '$repo'. Einmal anlegen mit:`n" +
        "  git clone https://github.com/baufotos/bautagesbericht.git `"$repo`""
}

# ---------------------------------------------------------------------------
# 1. Quellcode in die Arbeitskopie spiegeln
# ---------------------------------------------------------------------------
# robocopy /MIR spiegelt, loescht also im Ziel auch das, was in der Quelle weg
# ist. Genau das ist gewollt: Sonst schleppt das Repo geloeschte Dateien ewig
# mit. Der Ordner .git liegt eine Ebene hoeher und wird davon nicht beruehrt.
Schritt "Quellcode spiegeln"

$ausschluss = @(
  "node_modules", ".next", "out", "__pycache__", ".venv", "storage", "static",
  "HPP-Baumanagement-App",
  # Im Quellordner liegt eine aeltere, verschachtelte Kopie des Projekts
  # gleichen Namens. Ohne diesen Ausschluss wandert sie als 112 ueberfluessige
  # Dateien ins Repo und verwirrt jeden, der dort nachsieht.
  "Bautagesbericht-Upload-Final"
)
$dateiAusschluss = @("*.pyc", "*.tsbuildinfo", "*.zip", "*.db", "*.db-shm", "*.db-wal")

$roboArgs = @(
  $quelle, $ziel, "/MIR", "/NDL", "/NJH", "/NJS", "/NP",
  "/XD"
) + $ausschluss + @(".git") + @("/XF") + $dateiAusschluss

if ($NurZeigen) {
  # /L listet nur auf, statt zu kopieren. Weil dann auch nichts in der
  # Arbeitskopie ankommt, kann git hinterher nichts mehr zeigen - die Liste
  # von robocopy IST hier die Antwort.
  $roboArgs += "/L"
  $bericht = & robocopy @roboArgs
  if ($LASTEXITCODE -ge 8) { throw "Probelauf fehlgeschlagen (robocopy $LASTEXITCODE)." }
  $zeilen = $bericht | Where-Object { $_.Trim() -ne "" }
  if ($zeilen.Count -eq 0) {
    Write-Host "Nichts zu tun - die Website ist schon auf diesem Stand." -ForegroundColor Green
  } else {
    Schritt ("Wuerde uebertragen ({0} Eintraege)" -f $zeilen.Count)
    $zeilen | Select-Object -First 50 | ForEach-Object { Write-Host "   $($_.Trim())" }
    if ($zeilen.Count -gt 50) { Write-Host ("   ... und {0} weitere" -f ($zeilen.Count - 50)) }
    Write-Host ""
    Write-Host "Nur gezeigt - nichts gesendet (-NurZeigen)." -ForegroundColor Yellow
  }
  # robocopy meldet "1" fuer "es gaebe etwas zu kopieren". Das ist hier ein
  # Erfolg und darf nicht als Fehler der Sitzung stehen bleiben.
  $global:LASTEXITCODE = 0
  return
}

& robocopy @roboArgs | Out-Null
# robocopy meldet Erfolg mit Codes 0-7; ab 8 ist wirklich etwas schiefgegangen.
if ($LASTEXITCODE -ge 8) { throw "Kopieren fehlgeschlagen (robocopy $LASTEXITCODE)." }

# Die .exe und das Startprogramm gehoeren nicht auf die Website.
foreach ($weg in @("desktop\HPP-Baumanagement.exe", "desktop\hpp-app.ico")) {
  $p = Join-Path $ziel $weg
  if (Test-Path $p) { Remove-Item $p -Force }
}

# ---------------------------------------------------------------------------
# 2. Was hat sich geaendert?
# ---------------------------------------------------------------------------
Push-Location $repo
try {
  $geaendert = & git status --porcelain
  if (-not $geaendert) {
    Write-Host "Nichts zu tun - die Website ist schon auf diesem Stand." -ForegroundColor Green
    return
  }

  Schritt "Aenderungen"
  $geaendert | Select-Object -First 40 | ForEach-Object { Write-Host "   $_" }
  if ($geaendert.Count -gt 40) { Write-Host ("   ... und {0} weitere" -f ($geaendert.Count - 40)) }

  # -------------------------------------------------------------------------
  # 3. Senden
  # -------------------------------------------------------------------------
  if ($Nachricht -eq "") {
    $Nachricht = "Stand vom " + (Get-Date -Format "dd.MM.yyyy HH:mm")
  }

  Schritt "Committen und senden"

  # ACHTUNG, PowerShell-Falle: git schreibt auch harmlose Hinweise nach stderr
  # ("LF will be replaced by CRLF"). Bei ErrorActionPreference = "Stop" macht
  # PowerShell daraus einen Abbruch, und der Push bliebe liegen, obwohl gar
  # nichts kaputt ist. Deshalb hier auf "Continue" schalten und den Erfolg am
  # Rueckgabewert ablesen - der luegt nicht.
  $vorher = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & git add -A
    if ($LASTEXITCODE -ne 0) { throw "git add fehlgeschlagen." }
    & git commit -m $Nachricht | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "git commit fehlgeschlagen." }
    & git push origin main
    if ($LASTEXITCODE -ne 0) { throw "git push fehlgeschlagen - Zugang pruefen." }
  } finally {
    $ErrorActionPreference = $vorher
  }

  Write-Host ""
  Write-Host "Gesendet." -ForegroundColor Green
  Write-Host "   Render baut jetzt neu. Dauer 5 bis 10 Minuten."
  Write-Host "   Fortschritt: https://dashboard.render.com"
  Write-Host "   Danach:      https://bautagesbericht-jwga.onrender.com  (einmal Strg+F5)"
} finally {
  Pop-Location
}
