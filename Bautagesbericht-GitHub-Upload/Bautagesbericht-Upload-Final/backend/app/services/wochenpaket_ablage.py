"""Zwischenablage für ein hochgeladenes Wochenpaket.

WARUM ES DIE GIBT
=================
Der Ablauf hat zwei Schritte: erst sehen, welche Tage im Paket stecken, dann
die Berichte erzeugen. Dazwischen darf man die Dateien nicht ein zweites Mal
hochladen — auf der Baustelle hängt das am Mobilfunknetz, und ein Wochenpaket
sind schnell 20 MB.

Also liegen die Dateien nach dem ersten Schritt unter
``uploads/wochen/<kennung>`` und werden im zweiten Schritt von dort geholt.
Kein Datenbankeintrag: Das Paket lebt nur bis zum Erzeugen der Berichte,
danach hängen die Teil-PDFs an den Einreichungen und sind dort dauerhaft.

AUFRÄUMEN
=========
Wer den zweiten Schritt nie macht (Fenster geschlossen, Rechner zugeklappt),
hinterlässt einen Ordner. Deshalb räumt jeder neue Upload die Pakete weg, die
älter als einen Tag sind — ohne Zeitgeber und ohne Hintergrunddienst.
"""

from __future__ import annotations

import re
import secrets
import shutil
import time
from pathlib import Path

from app.config import settings

#: Nach so vielen Sekunden gilt ein liegengebliebenes Paket als vergessen.
HALTBARKEIT_SEKUNDEN = 24 * 60 * 60

#: Eine Kennung besteht ausschließlich hieraus — alles andere wird abgewiesen,
#: damit über sie kein Pfad zusammengebaut werden kann.
_KENNUNG = re.compile(r"^[0-9a-f]{16}$")


def wurzel() -> Path:
    return settings.upload_dir / "wochen"


def neue_kennung() -> str:
    return secrets.token_hex(8)


def ordner(kennung: str) -> Path:
    """Der Ordner eines Pakets. Wirft bei einer erfundenen Kennung.

    Die Kennung kommt aus der Antwort des ersten Aufrufs zurück, also über den
    Browser — sie wird wie jede Eingabe von außen behandelt.
    """
    if not _KENNUNG.match(kennung or ""):
        raise ValueError("Ungültige Paketkennung")
    return wurzel() / kennung


def datei_im_paket(kennung: str, dateiname: str) -> Path:
    """Pfad einer Paketdatei — nur der Basisname zählt.

    ``Path(name).name`` schneidet jeden Pfadanteil ab; anschließend wird
    geprüft, dass das Ergebnis wirklich im Paketordner liegt. Ohne das könnte
    ein manipulierter Name auf beliebige Dateien des Rechners zeigen.
    """
    basis = ordner(kennung)
    ziel = basis / Path(dateiname or "").name
    if ziel.parent.resolve() != basis.resolve():
        raise ValueError("Ungültiger Dateiname")
    return ziel


def dateien(kennung: str) -> list[Path]:
    basis = ordner(kennung)
    if not basis.is_dir():
        return []
    return sorted((p for p in basis.iterdir() if p.is_file()),
                  key=lambda p: p.name.lower())


def aufraeumen(jetzt: float | None = None) -> int:
    """Entfernt vergessene Pakete. Gibt zurück, wie viele es waren."""
    basis = wurzel()
    if not basis.is_dir():
        return 0
    grenze = (jetzt if jetzt is not None else time.time()) - HALTBARKEIT_SEKUNDEN
    entfernt = 0
    for eintrag in basis.iterdir():
        if not eintrag.is_dir():
            continue
        try:
            if eintrag.stat().st_mtime < grenze:
                shutil.rmtree(eintrag, ignore_errors=True)
                entfernt += 1
        except OSError:
            # Ein gesperrter Ordner darf den Upload nicht aufhalten.
            continue
    return entfernt


def verwerfen(kennung: str) -> None:
    """Löscht ein Paket — nach dem Erzeugen der Berichte oder auf Abbruch."""
    try:
        shutil.rmtree(ordner(kennung), ignore_errors=True)
    except ValueError:
        pass
