"""Aufräumen abhängiger Daten beim Löschen von Stammdaten.

Ein Projekt bzw. ein Empfänger kann nicht einfach entfernt werden, solange noch
Einreichungen darauf verweisen (die Datenbank verbietet verwaiste Verweise).
Hier wird der komplette Rattenschwanz entfernt: Verarbeitungs-Logs, die
hochgeladenen Quelldateien und das erzeugte Word-Dokument.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Einreichung, VerarbeitungsLog


def _remove_file(rel_path: str | None) -> None:
    if not rel_path:
        return
    path = settings.upload_dir.parent / rel_path
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        # Dateisystemfehler dürfen das Löschen des Datensatzes nicht verhindern.
        pass


def delete_einreichung_cascade(db: Session, einreichung: Einreichung) -> None:
    """Entfernt eine Einreichung samt Logs, Uploads und Ergebnisdokument."""
    db.query(VerarbeitungsLog).filter(
        VerarbeitungsLog.einreichung_id == einreichung.id
    ).delete(synchronize_session=False)

    for rel in (einreichung.quelle_dateien or []):
        _remove_file(rel)

    # Upload-Ordner der Einreichung (falls leer/übrig) mit entfernen.
    upload_dir = settings.upload_dir / str(einreichung.id)
    try:
        if upload_dir.is_dir():
            shutil.rmtree(upload_dir, ignore_errors=True)
    except OSError:
        pass

    _remove_file(einreichung.ergebnis_dokument_pfad)

    db.delete(einreichung)


def delete_einreichungen_for(db: Session, *, projekt_id: int | None = None,
                             empfaenger_id: int | None = None) -> int:
    """Löscht alle Einreichungen eines Projekts bzw. Empfängers. Gibt die Anzahl zurück."""
    query = db.query(Einreichung)
    if projekt_id is not None:
        query = query.filter(Einreichung.projekt_id == projekt_id)
    if empfaenger_id is not None:
        query = query.filter(Einreichung.empfaenger_id == empfaenger_id)

    rows = query.all()
    for einreichung in rows:
        delete_einreichung_cascade(db, einreichung)
    return len(rows)


def count_einreichungen_for(db: Session, *, projekt_id: int | None = None,
                           empfaenger_id: int | None = None) -> int:
    query = db.query(Einreichung)
    if projekt_id is not None:
        query = query.filter(Einreichung.projekt_id == projekt_id)
    if empfaenger_id is not None:
        query = query.filter(Einreichung.empfaenger_id == empfaenger_id)
    return query.count()
