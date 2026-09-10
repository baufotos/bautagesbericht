# Mcdonalds-Ordner-Abholen.ps1
# ============================================================================
# Legt die Standortordner der ueber die Website angelegten McDonald's-
# Standorte im Projektlaufwerk an (M:\HAM-226010\STANDORTE).
#
# WOZU
# ----
# In der App: SLS-Mail hochladen oder Standort von Hand erfassen. Die App
# ermittelt Ortscode und Ordnername sofort - den Ordner selbst kann sie aber
# nicht anlegen, denn sie laeuft bei Render im Internet, STANDORTE ist ein
# Laufwerk im Bueronetz. Deshalb holt das Buero ab, genau wie bei den
# Baufotos (siehe desktop/abholung/Baufotos-Abholen.ps1).
#
# Ein Standort, dessen Ordner noch nicht angelegt ist, zeigt in der App den
# Status "vorbereitet" (kein Fehler). Nach diesem Skript steht er auf
# "angelegt" mit dem tatsaechlichen Pfad.
#
# WOHER DIE STRUKTUR KOMMT
# -------------------------
# Zwei Quellen, in dieser Reihenfolge - dieselbe Regel wie im Server:
#   1. Der echte Musterordner "x_CODE_NAME (Muster) [leer]" in STANDORTE,
#      wenn erreichbar. Aendert das Buero ihn, gilt das ab dem naechsten
#      Lauf automatisch.
#   2. Sonst die Unterordner-Liste vom Server (/api/mcdonalds/abholung/musterstruktur)
#      - dieselbe Liste wie in app/services/mcdonalds_musterstruktur.py.
#
# EINRICHTEN
# ----------
# 1. Diesen Ordner nach C:\HPP-Mcdonalds-Abholung kopieren.
# 2. einstellungen.txt oeffnen und pruefen (Server-Adresse, Basisordner,
#    Token).
# 3. Rechtsklick auf Aufgabe-Einrichten.ps1 -> "Mit PowerShell ausfuehren".
#
# Aufrufparameter (ueberschreiben die einstellungen.txt):
#   -Server      https://hpp-baumanagement-buero.onrender.com
#   -Basis       "M:\HAM-226010\STANDORTE"
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
    if (-not (Test-Path -LiteralPath $Datei)) { return $Standard }
    foreach ($zeile in (Get-Content -LiteralPath $Datei -Encoding UTF8)) {
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
    $Server = Lies-Einstellung $EinstellungenDatei "server" "https://hpp-baumanagement-buero.onrender.com"
}
if (-not $Basis) {
    $Basis = Lies-Einstellung $EinstellungenDatei "basisordner" "M:\HAM-226010\STANDORTE"
}
if (-not $Token) {
    $Token = Lies-Einstellung $EinstellungenDatei "token" ""
}
$ProtokollDatei = Lies-Einstellung $EinstellungenDatei "protokoll" (Join-Path $OrdnerDesSkripts "abholung.log")

$Server = $Server.TrimEnd("/")
# "unbekannt" statt leer/$null: Der Server erwartet fuer "rechner" immer
# Text, kein JSON-null - ein $null hier wuerde jede Meldung mit 422
# scheitern lassen, noch bevor die Ordner ueberhaupt gepflegt sind.
$Rechner = $env:COMPUTERNAME
if (-not $Rechner) { $Rechner = "unbekannt" }

# ---------------------------------------------------------------------------
# Protokoll
# ---------------------------------------------------------------------------

function Schreib-Log {
    param([string]$Text, [string]$Art = "INFO")
    $zeile = "{0}  {1,-5}  {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Art, $Text
    Write-Host $zeile
    try {
        if ((Test-Path -LiteralPath $ProtokollDatei) -and ((Get-Item -LiteralPath $ProtokollDatei).Length -gt 2MB)) {
            Move-Item -LiteralPath $ProtokollDatei "$ProtokollDatei.alt" -Force
        }
        Add-Content -LiteralPath $ProtokollDatei -Value $zeile -Encoding UTF8
    } catch {
        # Ein nicht schreibbares Protokoll darf die Abholung nicht stoppen.
    }
}

# ---------------------------------------------------------------------------
# Server-Aufrufe
#
# Dieselbe UTF8-Vorsicht wie bei den Baufotos: Windows PowerShell 5.1 liest
# eine Antwort ohne charset im Content-Type als ISO-8859-1, und FastAPI
# schickt nur "application/json". Aus "Koeln Ring" mit Umlaut wuerde sonst
# Buchstabensalat - und daraus ein falscher Ordnername. Deshalb Rohdaten
# holen und selbst als UTF-8 lesen.
# ---------------------------------------------------------------------------

$Kopfzeilen = @{}
if ($Token -ne "") { $Kopfzeilen["X-Abhol-Token"] = $Token }

function Ruf-Server {
    param([string]$Pfad, [string]$Methode = "Get", $Rumpf = $null)
    $adresse = "$Server/api$Pfad"

    if ($null -ne $Rumpf) {
        $inhalt = [System.Text.Encoding]::UTF8.GetBytes(($Rumpf | ConvertTo-Json -Compress))
        $antwort = Invoke-WebRequest -Uri $adresse -Method $Methode -Headers $Kopfzeilen `
            -Body $inhalt -ContentType "application/json; charset=utf-8" `
            -TimeoutSec 120 -UseBasicParsing
    } else {
        $antwort = Invoke-WebRequest -Uri $adresse -Method $Methode -Headers $Kopfzeilen `
            -TimeoutSec 120 -UseBasicParsing
    }

    $roh = $antwort.RawContentStream.ToArray()
    if ($roh.Length -eq 0) { return $null }
    $text = [System.Text.Encoding]::UTF8.GetString($roh)
    if ($text.Trim() -eq "") { return $null }
    return ConvertFrom-Json $text
}

function Als-Liste {
    # Siehe Baufotos-Abholen.ps1: die Pipeline loest genau eine Verschachtelungs-
    # ebene auf, der Aufrufer fasst das Ergebnis danach wieder in @().
    #
    # Der explizite $null-Fall ist kein Sonderfall zur Sicherheit, sondern
    # notwendig: Kommt vom Server ein leeres JSON-Array "[]" zurueck, macht
    # ConvertFrom-Json daraus $null (nicht ein leeres Array) - und dieses
    # $null, aus einer Funktion zurueckgegeben und dann durch die Pipeline
    # geschickt, ergibt hier ein Array mit EINEM $null-Element statt keinem.
    # Ohne diese Pruefung wuerde "nichts abzuholen" fälschlich als ein
    # Standort ohne jede Angabe behandelt.
    param($Antwort)
    if ($null -eq $Antwort) { return @() }
    return @($Antwort | ForEach-Object { $_ })
}

# ---------------------------------------------------------------------------
# Die Struktur anlegen
#
# Zwei Wege, ein Ergebnis: hinterher stehen alle Unterordner. Beide Wege
# uebertragen bewusst KEINE Datei- oder Ordnerattribute (kein Copy-Item
# -Recurse auf den ganzen Baum): Der echte Musterordner ist schreibgeschuetzt
# (Attribut "R"), damit niemand versehentlich in der Vorlage arbeitet. Wuerde
# dieses Attribut mitkopiert, waere jeder neue Standortordner ebenfalls
# schreibgeschuetzt - Dateien liessen sich zwar noch hineinlegen, aber nicht
# mehr umbenennen oder loeschen. Deshalb New-Item fuer Ordner (normale Rechte
# des angemeldeten Benutzers) und Copy-Item nur je Datei.
#
# -LiteralPath ueberall: Der Musterordner heisst
# "x_CODE_NAME (Muster) [leer]" - die eckigen Klammern waeren sonst ein
# Wildcard-Muster statt ein Ordnername.
# ---------------------------------------------------------------------------

function Kopiere-Musterordner {
    param([string]$Quelle, [string]$Ziel)

    if (-not (Test-Path -LiteralPath $Ziel)) {
        New-Item -ItemType Directory -Path $Ziel -Force | Out-Null
    }

    $anzahl = 0
    $vorsatzLaenge = $Quelle.TrimEnd("\").Length
    Get-ChildItem -LiteralPath $Quelle -Recurse | Sort-Object FullName | ForEach-Object {
        $relativ = $_.FullName.Substring($vorsatzLaenge).TrimStart("\")
        $neu = Join-Path $Ziel $relativ
        if ($_.PSIsContainer) {
            if (-not (Test-Path -LiteralPath $neu)) {
                New-Item -ItemType Directory -Path $neu -Force | Out-Null
            }
            $anzahl++
        } else {
            if (-not (Test-Path -LiteralPath $neu)) {
                $elternordner = Split-Path $neu -Parent
                if (-not (Test-Path -LiteralPath $elternordner)) {
                    New-Item -ItemType Directory -Path $elternordner -Force | Out-Null
                }
                Copy-Item -LiteralPath $_.FullName -Destination $neu
            }
        }
    }
    return $anzahl
}

function Erzeuge-Aus-Liste {
    param([string]$Ziel, [string[]]$Unterordner)

    foreach ($teil in $Unterordner) {
        $pfad = Join-Path $Ziel $teil
        if (-not (Test-Path -LiteralPath $pfad)) {
            New-Item -ItemType Directory -Path $pfad -Force | Out-Null
        }
    }
    if (-not (Test-Path -LiteralPath $Ziel)) {
        New-Item -ItemType Directory -Path $Ziel -Force | Out-Null
    }
    return @(Get-ChildItem -LiteralPath $Ziel -Recurse -Directory).Count
}

# ---------------------------------------------------------------------------
# Ein Standort
# ---------------------------------------------------------------------------

function Lege-Standortordner-An {
    param($Standort, $Musterstruktur)

    # Ohne Id oder Ordnername lässt sich kein sicherer Zielpfad bilden - vor
    # allem $Standort.ordner_name leer hieße sonst $Ziel = $Basis, und die
    # Struktur würde direkt in den STANDORTE-Wurzelordner geschrieben statt
    # in einen eigenen Unterordner. Lieber überspringen und im nächsten Lauf
    # erneut versuchen (die App füllt ordner_name im Hintergrund kurz nach
    # dem Anlegen; "ausstehend" heißt: dieser Schritt lief hier noch nicht).
    if (-not $Standort.id -or -not (($Standort.ordner_name -as [string]).Trim())) {
        $text = "Standort {0} ohne Ordnername (Status: {1}) - uebersprungen, naechster Lauf versucht es erneut." -f `
            $Standort.id, $Standort.ordner_status
        Schreib-Log $text "WARN"
        return
    }

    $ziel = Join-Path $Basis $Standort.ordner_name
    Schreib-Log ("Standort {0}: {1} ({2}) -> {3}" -f `
        $Standort.id, $Standort.standort_name, $Standort.ordner_name, $ziel)

    if ($Testlauf) {
        Schreib-Log "  Testlauf - es wird nichts geschrieben." "TEST"
        return
    }

    $wurzel = [System.IO.Path]::GetPathRoot($Basis)
    if ($wurzel -and -not (Test-Path -LiteralPath $wurzel)) {
        Schreib-Log "  Laufwerk $wurzel nicht erreichbar - uebersprungen." "WARN"
        return
    }
    if (-not (Test-Path -LiteralPath $Basis)) {
        Schreib-Log "  Ordner $Basis nicht erreichbar - uebersprungen." "WARN"
        return
    }

    try {
        $musterordnerPfad = Join-Path $Basis $Musterstruktur.musterordner_name
        if (Test-Path -LiteralPath $musterordnerPfad) {
            $anzahl = Kopiere-Musterordner -Quelle $musterordnerPfad -Ziel $ziel
            Schreib-Log "  Aus dem echten Musterordner kopiert: $anzahl Unterordner."
        } else {
            $anzahl = Erzeuge-Aus-Liste -Ziel $ziel -Unterordner $Musterstruktur.unterordner
            Schreib-Log "  Musterordner nicht erreichbar - aus der Liste angelegt: $anzahl Unterordner."
        }

        Ruf-Server "/mcdonalds/standorte/$($Standort.id)/abholung/melden" "Post" `
            @{ rechner = $Rechner; status = "angelegt"; pfad = $ziel; anzahl = $anzahl } | Out-Null
        Schreib-Log "  Fertig und gemeldet."

    } catch {
        $fehlertext = $_.Exception.Message
        Schreib-Log "  Fehlgeschlagen: $fehlertext" "FEHL"
        try {
            Ruf-Server "/mcdonalds/standorte/$($Standort.id)/abholung/melden" "Post" `
                @{ rechner = $Rechner; status = "fehler"; meldung = $fehlertext } | Out-Null
        } catch {
            Schreib-Log "  Fehlermeldung liess sich nicht an den Server senden: $($_.Exception.Message)" "WARN"
        }
    }
}

# ---------------------------------------------------------------------------
# Hauptlauf
# ---------------------------------------------------------------------------

Schreib-Log "--- Mcdonalds-Ordner-Abholung gestartet ($Rechner) ---"

function Hole-Mit-Wiederholung {
    param([string]$Pfad, [string]$Beschreibung)
    try {
        return (Ruf-Server $Pfad)
    } catch {
        # Render schlaeft nach 15 Minuten ein und braucht bis zu einer Minute
        # zum Aufwachen - der erste Versuch laeuft dabei in einen Zeitfehler.
        Schreib-Log "$Beschreibung nicht erreicht, zweiter Versuch in 45 Sekunden ..." "WARN"
        Start-Sleep -Seconds 45
        return (Ruf-Server $Pfad)
    }
}

try {
    $musterstruktur = Hole-Mit-Wiederholung "/mcdonalds/abholung/musterstruktur" "Musterstruktur"
} catch {
    Schreib-Log "Server nicht erreichbar: $($_.Exception.Message)" "FEHL"
    exit 1
}

try {
    $offen = @(Als-Liste (Hole-Mit-Wiederholung "/mcdonalds/standorte/abholung/offen" "Offene Standorte"))
} catch {
    Schreib-Log "Server nicht erreichbar: $($_.Exception.Message)" "FEHL"
    exit 1
}

if ($offen.Count -eq 0) {
    Schreib-Log "Nichts abzuholen."
    exit 0
}

Schreib-Log "$($offen.Count) Standort(e) warten."

foreach ($standort in $offen) {
    try {
        Lege-Standortordner-An $standort $musterstruktur
    } catch {
        # Ein kaputter Standort darf die uebrigen nicht aufhalten.
        Schreib-Log "Standort $($standort.id) uebersprungen: $($_.Exception.Message)" "FEHL"
    }
}

Schreib-Log "--- Abholung beendet ---"
