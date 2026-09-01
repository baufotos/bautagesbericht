"""Prüft, ob eine Paket-Laufzeit wirklich startfähig ist.

WARUM ES DIESE PRÜFUNG GIBT
===========================
``pip install --target`` legt Pakete einfach in einen Ordner. Bricht der
Vorgang ab — Netz weg, Datei gesperrt, Fenster geschlossen — bleibt ein
Ordner zurück, der auf den ersten Blick vollständig aussieht: ``fastapi`` ist
da, nur eine seiner Abhängigkeiten fehlt. Das Paket lässt sich dann bauen,
zippen und verteilen, und **erst beim Doppelklick auf dem Bürorechner** kommt
``ModuleNotFoundError``. Genau so ist es einmal passiert (``annotated_doc``
und ``anyio`` fehlten).

Deshalb wird nach dem Installieren einmal wirklich importiert — nicht die
Paketliste verglichen, sondern ``app.main`` geladen. Das ist derselbe Weg, den
uvicorn beim Start nimmt, also derselbe Fehler zur Bauzeit statt beim Kollegen.

Aufruf:
    python importe_pruefen.py <pfad-zur-laufzeit>

Rückgabe: 0 wenn alles lädt, sonst 1 mit Liste des Fehlenden.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

#: Was der Code direkt importiert. Die Abhängigkeiten dahinter deckt der
#: Import von ``app.main`` ab — der zieht die ganze Kette.
MODULE = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "pydantic",
    "pydantic_settings",
    "docx",           # python-docx
    "PIL",            # pillow
    "pillow_heif",    # HEIC vom iPhone — ohne das kommen Fotos unverarbeitet an
    "pypdfium2",
    "httpx",
    "pdfplumber",
    "psycopg",
    "anthropic",
    "multipart",      # python-multipart
    "email_validator",
]


def main() -> int:
    if len(sys.argv) < 2:
        print("Aufruf: python importe_pruefen.py <pfad-zur-laufzeit>")
        return 2

    laufzeit = Path(sys.argv[1]).resolve()
    pakete = laufzeit / "pakete"
    backend = laufzeit / "backend"
    for ordner in (pakete, backend):
        if not ordner.is_dir():
            print(f"FEHLER: {ordner} gibt es nicht.")
            return 2

    sys.path.insert(0, str(pakete))
    sys.path.insert(0, str(backend))

    fehlt: list[str] = []
    for name in MODULE:
        try:
            importlib.import_module(name)
        except Exception as fehler:                      # noqa: BLE001
            fehlt.append(f"{name} ({type(fehler).__name__}: {fehler})")

    # Der eigentliche Test: die Anwendung selbst laden. Das zieht die ganze
    # Kette der Abhängigkeiten und meldet auch Fehler im eigenen Code.
    anwendung = None
    try:
        modul = importlib.import_module("app.main")
        anwendung = modul.app
    except Exception as fehler:                           # noqa: BLE001
        fehlt.append(f"app.main ({type(fehler).__name__}: {fehler})")

    if fehlt:
        print("Die Laufzeit ist NICHT startfaehig - es fehlt:")
        for eintrag in fehlt:
            print(f"   {eintrag}")
        print("\nBehebung:")
        print(f'   "{laufzeit / "python" / "python.exe"}" -m pip install '
              f'--target "{pakete}" --upgrade <paket>')
        return 1

    print(f"   Startfaehig: {len(MODULE)} Pakete geladen, app.main mit "
          f"{len(anwendung.routes)} Routen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
