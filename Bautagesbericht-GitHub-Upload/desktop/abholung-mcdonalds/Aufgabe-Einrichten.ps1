# Aufgabe-Einrichten.ps1
# ============================================================================
# Traegt die Mcdonalds-Ordner-Abholung in die Windows-Aufgabenplanung ein.
# Einmal ausfuehren, danach laeuft sie von allein - genau wie bei der
# Foto-Abholung (siehe desktop/abholung/Aufgabe-Einrichten.ps1).
#
# Aufruf (Rechtsklick -> "Mit PowerShell ausfuehren" genuegt):
#   .\Aufgabe-Einrichten.ps1
#   .\Aufgabe-Einrichten.ps1 -AlleMinuten 10
#   .\Aufgabe-Einrichten.ps1 -Entfernen
#
# Die Aufgabe laeuft unter dem angemeldeten Benutzer und nur, wenn jemand
# angemeldet ist. Das ist Absicht: Das Standorte-Laufwerk ist ein
# Netzlaufwerk und existiert im SYSTEM-Kontext gar nicht.
# ============================================================================

[CmdletBinding()]
param(
    [int]$AlleMinuten = 15,
    [switch]$Entfernen
)

$ErrorActionPreference = "Stop"
$Name = "HPP Mcdonalds-Ordner abholen"
$Skript = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "Mcdonalds-Ordner-Abholen.ps1"

if ($Entfernen) {
    try {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
        Write-Host "Aufgabe '$Name' entfernt."
    } catch {
        Write-Host "Aufgabe '$Name' war nicht eingetragen."
    }
    return
}

if (-not (Test-Path $Skript)) {
    throw "Mcdonalds-Ordner-Abholen.ps1 nicht gefunden - beide Dateien muessen im selben Ordner liegen."
}

$aktion = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $Skript)

# Zwei Ausloeser: beim Anmelden (dann sind ueber Nacht angelegte Standorte
# gleich morgens da) und danach im festen Takt.
$beiAnmeldung = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$imTakt = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes $AlleMinuten)

$einstellungen = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

$anmeldung = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

try { Unregister-ScheduledTask -TaskName $Name -Confirm:$false } catch { }

Register-ScheduledTask -TaskName $Name -Action $aktion `
    -Trigger @($beiAnmeldung, $imTakt) -Settings $einstellungen -Principal $anmeldung `
    -Description "Legt die ueber die Website angelegten McDonald's-Standortordner im Projektlaufwerk an." | Out-Null

Write-Host ""
Write-Host "Aufgabe '$Name' eingerichtet - laeuft alle $AlleMinuten Minuten."
Write-Host "Protokoll: $(Join-Path (Split-Path -Parent $Skript) 'abholung.log')"
Write-Host ""
Write-Host "Zum Ausprobieren ohne Schreiben:"
Write-Host "  .\Mcdonalds-Ordner-Abholen.ps1 -Testlauf"
