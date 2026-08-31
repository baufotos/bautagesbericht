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


# ─────────────────────────────────────────────────────────────────────────────
# Mängelmanagement
#
# Ein Mangel hängt an Fotos, Anhängen und einer Plan-Markierung; ein Projekt
# zusätzlich an Gewerken und hochgeladenen Plänen. Auch hier gilt: Die
# Datenbank verbietet verwaiste Verweise, also wird der ganze Rattenschwanz
# entfernt — inklusive der Dateien auf der Festplatte.
# ─────────────────────────────────────────────────────────────────────────────


def delete_mangel_cascade(db: Session, mangel) -> None:
    """Entfernt einen Mangel samt Fotos, Anhängen und Plan-Markierung.

    Duplikate ("Ist Kopie von") bleiben erhalten und verlieren nur den Verweis
    auf ihr Original — sie sind eigene Vorgänge mit eigenem Fristenlauf.
    """
    from app.models import Mangel, MangelDatei, MangelFoto, MangelPlanMarkierung
    from app.services.bilder import loesche_mit_thumbnail

    db.query(Mangel).filter(Mangel.eltern_mangel_id == mangel.id).update(
        {"eltern_mangel_id": None}, synchronize_session=False
    )

    for foto in db.query(MangelFoto).filter(MangelFoto.mangel_id == mangel.id).all():
        loesche_mit_thumbnail(settings.upload_dir.parent / foto.dateipfad)
    db.query(MangelFoto).filter(MangelFoto.mangel_id == mangel.id).delete(
        synchronize_session=False
    )

    for datei in db.query(MangelDatei).filter(MangelDatei.mangel_id == mangel.id).all():
        _remove_file(datei.dateipfad)
    db.query(MangelDatei).filter(MangelDatei.mangel_id == mangel.id).delete(
        synchronize_session=False
    )

    db.query(MangelPlanMarkierung).filter(
        MangelPlanMarkierung.mangel_id == mangel.id
    ).delete(synchronize_session=False)

    ordner = settings.upload_dir / "maengel" / str(mangel.id)
    try:
        if ordner.is_dir():
            shutil.rmtree(ordner, ignore_errors=True)
    except OSError:
        pass

    db.delete(mangel)


def count_maengel_for(db: Session, *, projekt_id: int) -> int:
    from app.models import Mangel

    return db.query(Mangel).filter(Mangel.projekt_id == projekt_id).count()


def delete_maengel_for(db: Session, *, projekt_id: int) -> int:
    """Löscht alle Mängel eines Projekts samt Gewerken und Plänen."""
    from app.models import Gewerk, Mangel, MangelPlanMarkierung, ProjektPlan

    maengel = db.query(Mangel).filter(Mangel.projekt_id == projekt_id).all()
    for mangel in maengel:
        delete_mangel_cascade(db, mangel)
    db.flush()

    for plan in db.query(ProjektPlan).filter(
        ProjektPlan.projekt_id == projekt_id
    ).all():
        db.query(MangelPlanMarkierung).filter(
            MangelPlanMarkierung.plan_datei_id == plan.id
        ).delete(synchronize_session=False)
        _remove_file(plan.dateipfad)
        db.delete(plan)

    plan_ordner = settings.upload_dir / "plaene" / str(projekt_id)
    try:
        if plan_ordner.is_dir():
            shutil.rmtree(plan_ordner, ignore_errors=True)
    except OSError:
        pass

    db.query(Gewerk).filter(Gewerk.projekt_id == projekt_id).delete(
        synchronize_session=False
    )
    return len(maengel)


# ─────────────────────────────────────────────────────────────────────────────
# Baufotos
# ─────────────────────────────────────────────────────────────────────────────


def delete_fotosatz_cascade(db: Session, fotosatz) -> None:
    """Entfernt einen Fotosatz samt Fotos, Vorschaubildern und Ordner."""
    from app.models import Baufoto
    from app.services.bilder import loesche_mit_thumbnail

    for foto in db.query(Baufoto).filter(Baufoto.fotosatz_id == fotosatz.id).all():
        loesche_mit_thumbnail(settings.upload_dir.parent / foto.dateipfad)
    db.query(Baufoto).filter(Baufoto.fotosatz_id == fotosatz.id).delete(
        synchronize_session=False
    )

    ordner = settings.upload_dir / "baufotos" / str(fotosatz.id)
    try:
        if ordner.is_dir():
            shutil.rmtree(ordner, ignore_errors=True)
    except OSError:
        pass

    db.delete(fotosatz)


def count_fotosaetze_for(db: Session, *, projekt_id: int) -> int:
    from app.models import Fotosatz

    return db.query(Fotosatz).filter(Fotosatz.projekt_id == projekt_id).count()


def delete_fotosaetze_for(db: Session, *, projekt_id: int) -> int:
    """Löscht alle Fotosätze eines Projekts. Gibt die Anzahl zurück."""
    from app.models import Fotosatz

    saetze = db.query(Fotosatz).filter(Fotosatz.projekt_id == projekt_id).all()
    for fotosatz in saetze:
        delete_fotosatz_cascade(db, fotosatz)
    return len(saetze)


def delete_projektbericht_cascade(db: Session, bericht) -> None:
    """Löscht einen Projektbericht mit Fotos und erzeugten Dateien.

    Die Fotos liegen unter ``uploads/projektberichte/<id>``, die erzeugten
    Dokumente unter ``output/projektberichte/<id>`` — beides verschwindet mit,
    sonst wachsen die Ordner mit Leichen.
    """
    # Einzeln löschen und nicht zusätzlich als Sammelabfrage: Sonst versucht
    # SQLAlchemy dieselben Zeilen zweimal zu entfernen und warnt zu Recht.
    for foto in list(bericht.fotos):
        _remove_file(foto.dateipfad)
        db.delete(foto)

    ordner = settings.upload_dir / "projektberichte" / str(bericht.id)
    if ordner.is_dir():
        shutil.rmtree(ordner, ignore_errors=True)
    erzeugt = settings.output_dir / "projektberichte" / str(bericht.id)
    if erzeugt.is_dir():
        shutil.rmtree(erzeugt, ignore_errors=True)

    db.delete(bericht)


def count_projektberichte_for(db: Session, *, projekt_id: int) -> int:
    from app.models import Projektbericht

    return (
        db.query(Projektbericht)
        .filter(Projektbericht.projekt_id == projekt_id)
        .count()
    )


def delete_projektberichte_for(db: Session, *, projekt_id: int) -> int:
    """Alle Berichte eines Projekts — für das Löschen mit ``force``."""
    from app.models import Projektbericht

    berichte = (
        db.query(Projektbericht)
        .filter(Projektbericht.projekt_id == projekt_id)
        .all()
    )
    for bericht in berichte:
        delete_projektbericht_cascade(db, bericht)
    return len(berichte)
