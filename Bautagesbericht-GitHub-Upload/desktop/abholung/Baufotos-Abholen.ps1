# Baufotos-Abholen.ps1
# ============================================================================
# Holt die auf der Baustelle hochgeladenen Fotosaetze vom Server und legt sie
# im Projektverzeichnis auf L: ab.
#
# WOZU
# ----
# Auf der Baustelle: Handy -> Website -> Ort/Projekt/Taetigkeit eingeben ->
# Fotos hochladen. Fertig. Alles Weitere macht dieses Skript, das in der
# Windows-Aufgabenplanung alle paar Minuten laeuft.
#
# Der Server kann nicht selbst auf L: schreiben - er steht im Internet, L: ist
# ein Laufwerk im Bueronetz. Deshalb holt das Buero ab.
#
# JEDER IM TEAM DARF DAS SKRIPT HABEN
# -----------------------------------
# Damit die Fotos auch ankommen, wenn ein einzelner Rechner aus ist, laeuft es
# auf mehreren PCs. Der Server sorgt dafuer, dass jeder Satz nur einmal geholt
# wird: Erst "beanspruchen" (genau einer bekommt den Zuschlag), dann ablegen,
# dann "quittieren".
#
# EINRICHTEN
# ----------
# 1. Diesen Ordner nach C:\HPP-Baufotos kopieren.
# 2. einstellungen.txt anpassen (Server-Adresse, Basisordner).
# 3. Aufgabe-Einrichten.ps1 einmal ausfuehren - legt die geplante Aufgabe an.
#
# Aufrufparameter (ueberschreiben die einstellungen.txt):
#   -Server      https://bautagesbericht.onrender.com
#   -Basis       "L:\Bauleitung-Hamburg"
#   -Testlauf    zeigt nur an, was passieren wuerde
# ============================================================================

[CmdletBinding()]
param(
    [string]$Server,
    [string]$Basis,
    [string]$Token,
    [switch]$Testlauf
)

$ErrorActionPreference = "Stop"
$OrdnerDesSkripts = Split-Path -Parent $MyInvocation.MyCommand.Path

# ---------------------------------------------------------------------------
# Einstellungen
# ---------------------------------------------------------------------------

function Lies-Einstellung {
    param([string]$Datei, [string]$Schluessel, [string]$Standard = "")
    if (-not (Test-Path $Datei)) { return $Standard }
    foreach ($zeile in (Get-Content $Datei -Encoding UTF8)) {
        $text = $zeile.Trim()
        if ($text -eq "" -or $text.StartsWith("#")) { continue }
        $teile = $text.Split("=", 2)
        if ($teile.Count -eq 2 -and $teile[0].Trim() -ieq $Schluessel) {
            return $teile[1].Trim()
        }
    }
    return $Standard
}

$EinstellungenDatei = Join-Path $OrdnerDesSkripts "einstellungen.txt"

if (-not $Server) {
    $Server = Lies-Einstellung $EinstellungenDatei "server" "https://bautagesbericht.onrender.com"
}
if (-not $Basis) {
    $Basis = Lies-Einstellung $EinstellungenDatei "basisordner" "L:\Bauleitung-Hamburg"
}
if (-not $Token) {
    $Token = Lies-Einstellung $EinstellungenDatei "token" ""
}
$UnterordnerFotos = Lies-Einstellung $EinstellungenDatei "unterordner" "01 FOTOS"
$ProtokollDatei   = Lies-Einstellung $EinstellungenDatei "protokoll" (Join-Path $OrdnerDesSkripts "abholung.log")
$AusnahmenDatei   = Join-Path $OrdnerDesSkripts "Projekt-Ausnahmen.txt"

$Server = $Server.TrimEnd("/")
$Rechner = $env:COMPUTERNAME

# ---------------------------------------------------------------------------
# Protokoll
#
# Laeuft im Hintergrund, also ist die Logdatei die einzige Spur. Sie wird bei
# 2 MB umbenannt, damit sie nicht unbemerkt das Laufwerk fuellt.
# ---------------------------------------------------------------------------

function Schreib-Log {
    param([string]$Text, [string]$Art = "INFO")
    $zeile = "{0}  {1,-5}  {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Art, $Text
    Write-Host $zeile
    try {
        if ((Test-Path $ProtokollDatei) -and ((Get-Item $ProtokollDatei).Length -gt 2MB)) {
            Move-Item $ProtokollDatei "$ProtokollDatei.alt" -Force
        }
        Add-Content -Path $ProtokollDatei -Value $zeile -Encoding UTF8
    } catch {
        # Ein nicht schreibbares Protokoll darf die Abholung nicht stoppen.
    }
}

# ---------------------------------------------------------------------------
# Projekt -> Zielordner
#
# Drei Quellen, in dieser Reihenfolge:
#   1. Projekt-Ausnahmen.txt auf diesem Rechner  (hoechste Prioritaet)
#   2. der in der App am Projekt gepflegte Pfad  (der Normalfall)
#   3. die Standardregel <Basis>\<Projekt>\<Unterordner>
#
# Grund fuer die Reihenfolge: Der Pfad in der App gilt fuer alle. Wer auf
# seinem Rechner ein Laufwerk anders eingebunden hat (M: statt L:), kann das
# lokal ueberschreiben, ohne den Wert fuer die Kollegen zu veraendern.
# ---------------------------------------------------------------------------

function Lies-Ausnahmen {
    $tabelle = @{}
    if (-not (Test-Path $AusnahmenDatei)) { return $tabelle }
    foreach ($zeile in (Get-Content $AusnahmenDatei -Encoding UTF8)) {
        $text = $zeile.Trim()
        if ($text -eq "" -or $text.StartsWith("#")) { continue }
        $teile = $text.Split("=", 2)
        if ($teile.Count -eq 2) {
            $tabelle[$teile[0].Trim().ToLower()] = $teile[1].Trim().TrimEnd("\")
        }
    }
    return $tabelle
}

function Bestimme-Zielordner {
    param($Satz, $Ausnahmen)

    $schluessel = $Satz.projekt_name.Trim().ToLower()
    if ($Ausnahmen.ContainsKey($schluessel)) {
        return $Ausnahmen[$schluessel]
    }
    if ($Satz.zielpfad -and $Satz.zielpfad.Trim() -ne "") {
        return $Satz.zielpfad.Trim().TrimEnd("\")
    }
    return (Join-Path (Join-Path $Basis $Satz.projekt_name) $UnterordnerFotos)
}

# ---------------------------------------------------------------------------
# Server-Aufrufe
# ---------------------------------------------------------------------------

$Kopfzeilen = @{}
if ($Token -ne "") { $Kopfzeilen["X-Abhol-Token"] = $Token }

function Ruf-Server {
    param([string]$Pfad, [string]$Methode = "Get", $Rumpf = $null)
    $adresse = "$Server/api$Pfad"
    if ($Rumpf -ne $null) {
        return Invoke-RestMethod -Uri $adresse -Method $Methode -Headers $Kopfzeilen `
            -Body ($Rumpf | ConvertTo-Json -Compress) -ContentType "application/json" `
            -TimeoutSec 120
    }
    return Invoke-RestMethod -Uri $adresse -Method $Methode -Headers $Kopfzeilen -TimeoutSec 120
}

# ---------------------------------------------------------------------------
# Ein Fotosatz
# ---------------------------------------------------------------------------

function Hole-Fotosatz {
    param($Satz, $Ausnahmen)

    $zielordner = Bestimme-Zielordner $Satz $Ausnahmen
    $vollstaendig = Join-Path $zielordner $Satz.ordnername

    Schreib-Log ("Satz {0}: {1} / {2} ({3} Fotos) -> {4}" -f `
        $Satz.id, $Satz.projekt_name, $Satz.kategorie, $Satz.anzahl_fotos, $vollstaendig)

    if ($Testlauf) {
        Schreib-Log "  Testlauf - es wird nichts geschrieben." "TEST"
        return
    }

    # Erreichbarkeit VOR dem Beanspruchen pruefen: Ist das Netzlaufwerk weg,
    # soll der Satz gar nicht erst reserviert werden.
    $wurzel = [System.IO.Path]::GetPathRoot($zielordner)
    if ($wurzel -and -not (Test-Path $wurzel)) {
        Schreib-Log "  Laufwerk $wurzel nicht erreichbar - uebersprungen." "WARN"
        return
    }

    # 1. Beanspruchen. 409 = ein anderer Rechner ist dran, kein Fehler.
    try {
        Ruf-Server "/fotosaetze/$($Satz.id)/abholung/beanspruchen" "Post" @{ rechner = $Rechner } | Out-Null
    } catch {
        $code = $null
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        if ($code -eq 409) {
            Schreib-Log "  Uebernimmt gerade ein anderer Rechner - uebersprungen."
        } else {
            Schreib-Log "  Beanspruchen fehlgeschlagen: $($_.Exception.Message)" "FEHL"
        }
        return
    }

    $zipdatei = Join-Path $env:TEMP ("baufotos-{0}-{1}.zip" -f $Satz.id, $PID)
    $entpackt = $false

    try {
        # 2. ZIP laden.
        Invoke-WebRequest -Uri "$Server/api/fotosaetze/$($Satz.id)/zip" -Headers $Kopfzeilen `
            -OutFile $zipdatei -TimeoutSec 600 | Out-Null

        if (-not (Test-Path $zipdatei) -or (Get-Item $zipdatei).Length -lt 100) {
            throw "Heruntergeladene ZIP-Datei ist leer."
        }

        # 3. Entpacken. Erst in einen Zwischenordner, dann verschieben - sonst
        #    liegt bei einem Abbruch ein halber Satz im Projektverzeichnis.
        $zwischen = Join-Path $env:TEMP ("baufotos-{0}-{1}" -f $Satz.id, $PID)
        if (Test-Path $zwischen) { Remove-Item $zwischen -Recurse -Force }
        New-Item -ItemType Directory -Path $zwischen -Force | Out-Null
        Expand-Archive -Path $zipdatei -DestinationPath $zwischen -Force

        $dateien = @(Get-ChildItem $zwischen -File)
        if ($dateien.Count -eq 0) { throw "ZIP-Datei enthielt keine Fotos." }

        $fehlt = $dateien | Where-Object { $_.Name -eq "FEHLT.txt" }
        if ($fehlt) {
            Schreib-Log "  Achtung: Der Server meldet fehlende Einzelfotos (FEHLT.txt liegt bei)." "WARN"
        }

        # 4. In den Projektordner legen.
        if (-not (Test-Path $vollstaendig)) {
            New-Item -ItemType Directory -Path $vollstaendig -Force | Out-Null
        }
        foreach ($datei in $dateien) {
            Copy-Item $datei.FullName (Join-Path $vollstaendig $datei.Name) -Force
        }
        $entpackt = $true

        $angekommen = @(Get-ChildItem $vollstaendig -File).Count
        Schreib-Log "  $($dateien.Count) Datei(en) abgelegt, im Ordner liegen jetzt $angekommen."

        # 5. Quittieren. Erst jetzt gilt der Satz als erledigt.
        Ruf-Server "/fotosaetze/$($Satz.id)/abholung/quittieren" "Post" `
            @{ rechner = $Rechner; ziel = $vollstaendig } | Out-Null
        Schreib-Log "  Fertig und quittiert."

    } catch {
        Schreib-Log "  Fehlgeschlagen: $($_.Exception.Message)" "FEHL"
        if (-not $entpackt) {
            # Nichts abgelegt: Satz sofort wieder freigeben, damit ihn ein
            # anderer Rechner holen kann, statt die Verfallszeit abzuwarten.
            try {
                Ruf-Server "/fotosaetze/$($Satz.id)/abholung/freigeben" "Post" | Out-Null
                Schreib-Log "  Wieder freigegeben."
            } catch {
                Schreib-Log "  Freigabe fehlgeschlagen: $($_.Exception.Message)" "WARN"
            }
        } else {
            # Fotos liegen bereits im Projektordner, nur die Quittung fehlt.
            # Nicht freigeben - sonst legt der naechste Rechner sie erneut ab.
            Schreib-Log "  Fotos liegen im Projektordner, nur die Quittung fehlt." "WARN"
        }
    } finally {
        foreach ($rest in @($zipdatei, (Join-Path $env:TEMP ("baufotos-{0}-{1}" -f $Satz.id, $PID)))) {
            if (Test-Path $rest) { Remove-Item $rest -Recurse -Force -ErrorAction SilentlyContinue }
        }
    }
}

# ---------------------------------------------------------------------------
# Hauptlauf
# ---------------------------------------------------------------------------

Schreib-Log "--- Abholung gestartet ($Rechner) ---"

function Als-Liste {
    # Invoke-RestMethod gibt ein JSON-Array in PowerShell 5.1 als ein einziges
    # verschachteltes Objekt zurueck. Die Pipeline loest genau eine Ebene auf.
    # Der Aufrufer muss das Ergebnis noch einmal in @() fassen: Ein Array mit
    # nur einem Eintrag wird beim Verlassen der Funktion wieder ausgepackt.
    param($Antwort)
    return @($Antwort | ForEach-Object { $_ })
}

try {
    $offen = @(Als-Liste (Ruf-Server "/fotosaetze/abholung/offen"))
} catch {
    # Der Server auf Render schlaeft nach 15 Minuten ein und braucht dann bis
    # zu einer Minute zum Aufwachen. Der erste Versuch laeuft dabei in einen
    # Zeitfehler - deshalb ein zweiter, bevor es als Stoerung gilt.
    Schreib-Log "Server antwortet nicht, zweiter Versuch in 45 Sekunden ..." "WARN"
    Start-Sleep -Seconds 45
    try {
        $offen = @(Als-Liste (Ruf-Server "/fotosaetze/abholung/offen"))
    } catch {
        Schreib-Log "Server nicht erreichbar: $($_.Exception.Message)" "FEHL"
        exit 1
    }
}

if ($offen.Count -eq 0) {
    Schreib-Log "Nichts abzuholen."
    exit 0
}

Schreib-Log "$($offen.Count) Fotosatz/Fotosaetze warten."
$ausnahmen = Lies-Ausnahmen

foreach ($satz in $offen) {
    try {
        Hole-Fotosatz $satz $ausnahmen
    } catch {
        # Ein kaputter Satz darf die uebrigen nicht aufhalten.
        Schreib-Log "Satz $($satz.id) uebersprungen: $($_.Exception.Message)" "FEHL"
    }
}

Schreib-Log "--- Abholung beendet ---"
