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
#   .\Website-aktualisieren.ps1 -NurPruefen    nur der Geheimwert-Riegel
#
# ACHTUNG: Das Repo ist OEFFENTLICH. Vor dem Senden laeuft deshalb ein Riegel
# gegen Geheimwerte (Abschnitt 1b) - er bricht ab, statt zu senden.

[CmdletBinding()]
param(
  [string]$Nachricht = "",
  [switch]$NurZeigen,
  # Spiegelt und prueft auf Geheimwerte, sendet aber nicht. Fuer den Fall,
  # dass man nur wissen will, ob der Riegel haelt.
  [switch]$NurPruefen
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
  # Zwischenspeicher der Testlaeufe. Entsteht, sobald jemand pytest benutzt,
  # und hatte im Repo nichts zu suchen.
  ".pytest_cache",
  # Im Quellordner liegt eine aeltere, verschachtelte Kopie des Projekts
  # gleichen Namens. Ohne diesen Ausschluss wandert sie als 112 ueberfluessige
  # Dateien ins Repo und verwirrt jeden, der dort nachsieht.
  "Bautagesbericht-Upload-Final"
)
# *.exe: Das Startprogramm wird bei jedem Paketbau neu uebersetzt (siehe
# desktop/paket/erstellen.ps1). Ein mitgeschobenes Windows-Programm im
# oeffentlichen Repo waere ein Bauergebnis am falschen Ort - und Render
# braucht es nicht, dort laeuft nur Backend und Oberflaeche.
$dateiAusschluss = @("*.pyc", "*.tsbuildinfo", "*.zip", "*.exe",
                     "*.db", "*.db-shm", "*.db-wal")

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

# Was im Ziel nichts zu suchen hat, aber von /MIR nicht erwischt wird.
#
# Wichtig zu wissen: Ein mit /XD ausgeschlossener Ordner wird von robocopy
# weder kopiert NOCH geloescht - /MIR fasst ihn gar nicht an. Was einmal im
# Ziel liegt, bliebe also ewig. Deshalb hier von Hand weg.
foreach ($weg in @(
  "desktop\HPP-Baumanagement.exe",
  "desktop\hpp-app.ico",
  "Bautagesbericht-Upload-Final"
)) {
  $p = Join-Path $ziel $weg
  if (Test-Path $p) { Remove-Item $p -Recurse -Force }
}

# ---------------------------------------------------------------------------
# 1b. Riegel: keine Geheimwerte ins Repo
#
# WARUM ES DIESEN RIEGEL GIBT
# ===========================
# Das Repo github.com/baufotos/bautagesbericht ist OEFFENTLICH. Am 10.09.2026
# ist mit desktop\abholung-mcdonalds\einstellungen.txt das echte
# BTB_ABHOL_TOKEN mitgegangen - im Klartext, fuer jeden lesbar. Mit diesem
# Wort kommt man an die Baufotos-ZIPs vorbei am Seiten-Passwort (siehe
# backend\app\security.py). Aus der laufenden Fassung ist es entfernt, in der
# Historie steht es weiter; das Wort musste neu vergeben werden.
#
# Ein Kommentar in der Datei allein reicht offensichtlich nicht. Deshalb
# prueft dieses Skript jetzt selbst und BRICHT AB, statt zu senden. Ein Push
# ist nicht zurueckzunehmen - eine abgebrochene Uebertragung schon.
#
# Geprueft wird der gespiegelte Baum, also genau das, was gesendet wuerde.
# ---------------------------------------------------------------------------
function Pruefe-Geheimwerte {
  param([string]$Wurzel)

  # Was in Anleitungen und Vorlagen als BEISPIEL steht und kein Geheimnis ist.
  # Ohne diese Liste schlaegt der Riegel bei jedem Aufruf an - und ein Riegel,
  # der immer anschlaegt, wird nach dem zweiten Mal weggeklickt. Genau das
  # macht ihn wertlos, deshalb ist die Genauigkeit hier wichtiger als
  # Grosszuegigkeit.
  $platzhalter = @(
    'user:pw', 'benutzer:kennwort', 'USER:PASSWORD', 'benutzer:passwort',
    'dein-passwort', 'xxx', 'ep-cool-name', 'ep-xyz', '...', '…',
    '<', 'DEIN', 'dein_'
  )

  # Je Regel: wo gesucht wird, wonach, und was danach zu tun ist. Die Muster
  # suchen WERTE, nicht Namen - "BTB_ABHOL_TOKEN" darf in render.yaml und in
  # jeder Anleitung stehen, nur eben ohne Wort dahinter.
  #
  # [ \t] statt \s ist kein Schoenheitsfehler: Mit \s frisst der Ausdruck den
  # Zeilenumbruch mit und findet dann das '#' der naechsten Kommentarzeile als
  # angeblichen Wert. Genau so hat der Riegel im ersten Versuch bei der
  # leeren, voellig korrekten Foto-Abholung angeschlagen.
  $regeln = @(
    @{ NurDatei = 'einstellungen.txt';
       Muster = '(?m)^[ \t]*token[ \t]*=[ \t]*\S.*$';
       Grund  = 'In einer einstellungen.txt steht ein Losungswort. Das Feld muss leer bleiben - der echte Wert gehoert nur in die Arbeitskopie auf dem Buerorechner (C:\HPP-Baufotos, C:\HPP-Mcdonalds-Abholung).' },
    @{ Muster = 'postgres(ql)?(\+\w+)?://[^\s:/]+:[^\s@/]+@';
       Grund  = 'Eine Datenbank-Adresse mit Passwort. Die gehoert ausschliesslich in die Render-Umgebung (BTB_DATABASE_URL).' },
    @{ Muster = 'sk-ant-[A-Za-z0-9_\-]{10,}';
       Grund  = 'Ein Anthropic-Schluessel. Der gehoert ausschliesslich in die Render-Umgebung (BTB_ANTHROPIC_API_KEY).' },
    @{ Muster = '(?m)^[ \t]*(BTB_SEITEN_PASSWORT|BTB_ABHOL_TOKEN|BTB_SMTP_PASSWORT)[ \t]*=[ \t]*\S.*$';
       Grund  = 'Ein Geheimwert steht mit Wert in einer Datei. Solche Werte werden bei Render eingetragen, nie im Repo.' },
    @{ Muster = 'https://[a-z0-9.\-]*(webhook|logic\.azure)[a-z0-9.\-/]*\?[^\s]{20,}';
       Grund  = 'Eine Webhook-Adresse mit Zugangsteil. Die gehoert in BTB_TEAMS_WEBHOOK_URL bei Render.' }
  )

  $treffer = @()
  # Nur Textdateien. Die Suche laeuft ueber den ganzen gespiegelten Baum -
  # node_modules und Co. sind darin ohnehin nicht enthalten.
  $dateien = Get-ChildItem -LiteralPath $Wurzel -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @('.txt', '.ps1', '.py', '.ts', '.tsx', '.md',
                                      '.yaml', '.yml', '.json', '.env', '.cfg', '.sh', '.bat') }

  foreach ($datei in $dateien) {
    $inhalt = Get-Content -LiteralPath $datei.FullName -Raw -ErrorAction SilentlyContinue
    if (-not $inhalt) { continue }
    foreach ($regel in $regeln) {
      if ($regel.NurDatei -and $datei.Name -ne $regel.NurDatei) { continue }
      foreach ($m in [regex]::Matches($inhalt, $regel.Muster)) {
        $stelle = ($m.Value -replace '\s+', ' ').Trim()
        $istBeispiel = $false
        foreach ($p in $platzhalter) {
          if ($stelle.ToLower().Contains($p.ToLower())) { $istBeispiel = $true; break }
        }
        if ($istBeispiel) { continue }
        $relativ = $datei.FullName.Substring($Wurzel.TrimEnd('\').Length).TrimStart('\')
        $treffer += [pscustomobject]@{
          Datei = $relativ
          Stelle = $stelle
          Grund = $regel.Grund
        }
      }
    }
  }
  return $treffer
}

Schritt "Auf Geheimwerte pruefen"
$gefunden = @(Pruefe-Geheimwerte -Wurzel $ziel)
if ($gefunden.Count -gt 0) {
  Write-Host ""
  Write-Host "ABBRUCH - es wird NICHTS gesendet." -ForegroundColor Red
  Write-Host "Im zu sendenden Stand stehen Werte, die nicht in ein oeffentliches Repo gehoeren:" -ForegroundColor Red
  foreach ($t in $gefunden) {
    Write-Host ""
    Write-Host ("   Datei:  " + $t.Datei) -ForegroundColor Yellow
    Write-Host ("   Fund:   " + $t.Stelle)
    Write-Host ("   Grund:  " + $t.Grund)
  }
  Write-Host ""
  Write-Host "Bitte im QUELLCODE beheben (nicht in der Arbeitskopie) und erneut aufrufen." -ForegroundColor Red
  throw "Geheimwerte im zu sendenden Stand - Abbruch."
}
Write-Host "   nichts gefunden."

if ($NurPruefen) {
  Write-Host ""
  Write-Host "Nur geprueft - nichts gesendet (-NurPruefen)." -ForegroundColor Yellow
  return
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
  Write-Host "   Danach:      https://bautagesbericht.onrender.com  (einmal Strg+F5)"
} finally {
  Pop-Location
}
