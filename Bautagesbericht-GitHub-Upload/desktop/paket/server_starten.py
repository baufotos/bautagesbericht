"""Startet die App im Windows-Paket — ein Prozess für Oberfläche und Daten.

Diese Datei läuft NICHT auf dem Server (dort startet ``start.sh`` uvicorn und
Next.js getrennt). Sie gehört zum Windows-Paket, in dem alles in einem Prozess
steckt: FastAPI liefert die statisch exportierte Oberfläche mit aus
(siehe app.main), deshalb wird auf dem Bürorechner kein Node.js gebraucht.

Aufgerufen wird sie von ``HPP-Baumanagement.exe``:

    python\\python.exe server_starten.py --port 8765

WO DIE DATEN LIEGEN
===================
Standard ist der Ordner ``daten`` neben dem Programm: eine SQLite-Datei und die
hochgeladenen Fotos. Damit läuft das Paket auf einem einzelnen Rechner
vollständig ohne Internet.

Für den gemeinsamen Betrieb im Büro trägt man in ``einstellungen.txt`` eine
zentrale Datenbank und einen Datenordner auf dem Netzlaufwerk ein — dann sehen
alle denselben Stand, obwohl das Programm auf jedem Rechner läuft. Die Datei
wird hier gelesen, nicht im Startprogramm: Es sind Servereinstellungen.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Verzeichnis dieser Datei = laufzeit-Ordner des Pakets.
LAUFZEIT = Path(__file__).resolve().parent
PAKET = LAUFZEIT.parent

# Mitgelieferte Pakete und der Anwendungscode müssen auf den Suchpfad, bevor
# irgendetwas importiert wird. Beides liegt im Paket, damit auf dem Rechner
# kein Python installiert sein muss.
sys.path.insert(0, str(LAUFZEIT / "pakete"))
sys.path.insert(0, str(LAUFZEIT / "backend"))


def einstellungen_lesen() -> dict[str, str]:
    """Liest ``einstellungen.txt`` neben dem Programm (Schlüssel=Wert)."""
    datei = PAKET / "einstellungen.txt"
    werte: dict[str, str] = {}
    if not datei.is_file():
        return werte

    for zeile in datei.read_text(encoding="utf-8-sig").splitlines():
        text = zeile.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        schluessel, _, wert = text.partition("=")
        werte[schluessel.strip().lower()] = wert.strip()
    return werte


def umgebung_vorbereiten() -> Path:
    """Setzt die BTB_*-Variablen und gibt den Datenordner zurück."""
    werte = einstellungen_lesen()

    datenordner = Path(werte.get("datenordner") or (PAKET / "daten"))
    datenordner.mkdir(parents=True, exist_ok=True)

    datenbank = werte.get("datenbank", "").strip()
    if not datenbank:
        # Vorwärtsschrägstriche: SQLite bekommt den Pfad als URL, dort sind
        # Backslashes unter Windows eine Fehlerquelle.
        pfad = (datenordner / "hpp-baumanagement.db").as_posix()
        datenbank = f"sqlite:///{pfad}"

    # Nur setzen, was nicht schon von außen kommt — so kann das Startprogramm
    # (oder ein Fachmann in der Eingabeaufforderung) alles überschreiben.
    os.environ.setdefault("BTB_DATABASE_URL", datenbank)
    os.environ.setdefault("BTB_UPLOAD_DIR", str(datenordner / "uploads"))
    os.environ.setdefault("BTB_OUTPUT_DIR", str(datenordner / "output"))
    os.environ.setdefault("BTB_STATIC_DIR", str(LAUFZEIT / "backend" / "static"))
    if werte.get("teams_webhook"):
        os.environ.setdefault("BTB_TEAMS_WEBHOOK_URL", werte["teams_webhook"])
    if werte.get("anthropic_key"):
        os.environ.setdefault("BTB_ANTHROPIC_API_KEY", werte["anthropic_key"])

    # Postausgangsserver für "Baufotos per E-Mail" (app.services.fotoversand).
    # Deutsche Schlüssel in der Datei, BTB_*-Namen nach innen — die Kollegen
    # sollen keine Umgebungsvariablen setzen müssen. Ohne Eintrag bleibt der
    # Outlook-Entwurf der Weg, und der braucht keinen Server.
    for schluessel, variable in (
        ("smtp_server", "BTB_SMTP_HOST"),
        ("smtp_port", "BTB_SMTP_PORT"),
        ("smtp_benutzer", "BTB_SMTP_USER"),
        ("smtp_kennwort", "BTB_SMTP_PASSWORT"),
        ("smtp_tls", "BTB_SMTP_TLS"),
        ("smtp_absender", "BTB_SMTP_ABSENDER"),
    ):
        if werte.get(schluessel):
            os.environ.setdefault(variable, werte[schluessel])

    return datenordner


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args, _ = parser.parse_known_args()

    datenordner = umgebung_vorbereiten()

    # Ausgaben in eine Datei umleiten: Das Programm läuft ohne Konsole, und bei
    # einer Störung ist genau dieses Protokoll die erste Anlaufstelle.
    protokoll = datenordner / "protokoll.txt"
    try:
        strom = open(protokoll, "a", encoding="utf-8", buffering=1)
        sys.stdout = strom
        sys.stderr = strom
    except OSError:
        pass

    import uvicorn

    print(f"--- Start auf {args.host}:{args.port}, Daten in {datenordner} ---")
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        log_level="warning",
        # Kein Reload, kein Mehrprozessbetrieb: Ein einzelner Arbeiter genügt
        # für ein Büro und hält den Speicherbedarf klein.
        workers=1,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
