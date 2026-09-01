# Übersetzt HPP-Baumanagement.exe aus HppBaumanagement.cs.
#
# HINWEIS ZUR KODIERUNG: Diese Datei ist UTF-8 MIT BOM gespeichert. Windows
# PowerShell 5.1 liest .ps1-Dateien ohne BOM als ANSI — Umlaute zerbrechen dann
# die Zeichenketten. Beim Bearbeiten die Kodierung beibehalten.
#
# WARUM DER C#-COMPILER AUS WINDOWS
# =================================
# csc.exe liegt in jedem Windows (.NET Framework 4). Es braucht also kein SDK,
# kein NuGet, keine Internetverbindung — und das Ergebnis läuft auf jedem
# Bürorechner ohne Installation. Eine Python-Variante (PyInstaller) wäre
# 15 MB groß, würde häufiger vom Virenscanner angehalten und bräuchte erst
# eine Build-Umgebung.
#
# Nutzung:
#   .\bauen.ps1
# Das Ergebnis landet als ..\HPP-Baumanagement.exe

$ErrorActionPreference = "Stop"

$quelle  = Join-Path $PSScriptRoot "HppBaumanagement.cs"
$symbol  = Join-Path (Split-Path $PSScriptRoot -Parent) "hpp-app.ico"
$ziel    = Join-Path (Split-Path $PSScriptRoot -Parent) "HPP-Baumanagement.exe"

# Neueste vorhandene Fassung des Compilers nehmen (v4.0.30319 ist der Standard
# auf Windows 10 und 11).
$csc = Get-ChildItem "$env:WINDIR\Microsoft.NET\Framework64\v4*\csc.exe" |
       Sort-Object FullName -Descending | Select-Object -First 1
if (-not $csc) {
  throw "csc.exe nicht gefunden - laeuft dieses Windows ohne .NET Framework 4?"
}

Write-Host "Compiler: $($csc.FullName)"

$argumente = @(
  "/nologo",
  # winexe statt exe: kein schwarzes Konsolenfenster beim Doppelklick.
  "/target:winexe",
  "/optimize+",
  "/platform:anycpu",
  "/out:$ziel",
  "/r:System.dll",
  "/r:System.Windows.Forms.dll"
)
if (Test-Path $symbol) {
  $argumente += "/win32icon:$symbol"
} else {
  Write-Host "Hinweis: hpp-app.ico fehlt - die Datei bekommt das Standardsymbol." -ForegroundColor Yellow
}
$argumente += $quelle

& $csc.FullName $argumente
if ($LASTEXITCODE -ne 0) { throw "Uebersetzen fehlgeschlagen (Code $LASTEXITCODE)." }

$datei = Get-Item $ziel
Write-Host ""
Write-Host "Fertig:" -ForegroundColor Green
Write-Host ("   {0}  ({1:N0} Bytes)" -f $datei.FullName, $datei.Length)
Write-Host ""
Write-Host "Selbsttest:  .\HPP-Baumanagement.exe --pruefen"
