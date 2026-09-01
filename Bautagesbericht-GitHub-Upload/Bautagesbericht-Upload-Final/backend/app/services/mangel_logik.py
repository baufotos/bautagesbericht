"""Fachregeln des Mängelmanagements: Nummernkreis, Duplikate, Fristen.

Alles, was nicht einfach "Feld speichern" ist, steht hier — die Router bleiben
damit auf HTTP-Ebene und die Regeln sind an einer Stelle nachlesbar.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Mangel, MangelFoto, MangelPlanMarkierung, MangelStatus

# Breite der Hauptnummer, z. B. "00012".
NUMMER_STELLEN = 5


# ───────── Anzeige ─────────


def gewerk_anzeige(gewerk) -> str:
    """Firma und Vergabeeinheit in einer Zeile.

    Beispiel: "Rolfes Bau GmbH | VE300-01 Erweiterter Rohbau" — genau die
    Schreibweise, die im Auswahlfeld "zuständige Firma / Büro" steht.
    """
    if gewerk is None:
        return ""
    vergabeeinheit = " ".join(
        teil
        for teil in (gewerk.vergabeeinheit_code, gewerk.vergabeeinheit_bezeichnung)
        if teil
    )
    return " | ".join(teil for teil in (gewerk.firma_name, vergabeeinheit) if teil)


# ───────── Nummernkreis ─────────


def hauptnummer(nummer: str) -> str:
    """"00012.1" -> "00012" — der Teil vor dem Punkt-Suffix."""
    return (nummer or "").split(".", 1)[0]


def _als_zahl(text: str) -> int | None:
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def naechste_nummer(db: Session, projekt_id: int) -> str:
    """Nächste freie Hauptnummer eines Projekts, fünfstellig mit Nullen.

    Der Nummernkreis läuft pro Projekt — jedes Bauvorhaben beginnt bei 00001.
    Nicht-numerische Nummern (übernommene Altbestände) werden dabei
    übersprungen, statt die Zählung zu blockieren.
    """
    nummern = db.query(Mangel.nummer).filter(Mangel.projekt_id == projekt_id).all()
    hoechste = 0
    for (nummer,) in nummern:
        wert = _als_zahl(hauptnummer(nummer))
        if wert is not None:
            hoechste = max(hoechste, wert)
    return str(hoechste + 1).zfill(NUMMER_STELLEN)


def naechste_duplikat_nummer(db: Session, projekt_id: int, basis: str) -> str:
    """Nächstes freies Punkt-Suffix zu einer Hauptnummer, z. B. "00012.2".

    Auch das Duplikat eines Duplikats hängt sich an dieselbe Hauptnummer, damit
    alle Ableitungen eines Mangels zusammen bleiben.
    """
    haupt = hauptnummer(basis)
    nummern = db.query(Mangel.nummer).filter(Mangel.projekt_id == projekt_id).all()
    hoechstes_suffix = 0
    for (nummer,) in nummern:
        if not nummer or not nummer.startswith(f"{haupt}."):
            continue
        wert = _als_zahl(nummer.split(".", 1)[1])
        if wert is not None:
            hoechstes_suffix = max(hoechstes_suffix, wert)
    return f"{haupt}.{hoechstes_suffix + 1}"


# ───────── Duplikat ("Duplikat NU erstellen") ─────────

# Inhaltliche Felder, die ein Duplikat vom Original übernimmt. Der Mangel ist
# derselbe — nur die zuständige Firma und damit der ganze Fristenlauf sind neu.
DUPLIKAT_UEBERNAHME = (
    "typ",
    "gewerk_id",
    "raumnummer",
    "hinweis_ort",
    "prioritaet",
    "kurzbezeichnung",
    "beschreibung",
    "farbmarkierung",
    "interne_bemerkung",
    "aufgenommen_von",
    "zustaendiger_user_id",
    "erste_frist_bis",
)


def _erster_status(db: Session) -> str:
    status = (
        db.query(MangelStatus)
        .order_by(MangelStatus.sortierung, MangelStatus.id)
        .first()
    )
    return status.bezeichnung if status else "offen"


def duplikat_erstellen(db: Session, original: Mangel) -> Mangel:
    """Legt eine Kopie des Mangels für einen weiteren Nachunternehmer an.

    Übernommen wird die Beschreibung des Mangels samt Fotos und
    Plan-Markierung — es geht um denselben Sachverhalt an derselben Stelle.
    Zurückgesetzt wird alles, was zum Ablauf gehört: Status, Nachfristen,
    Rückmeldung, Erledigungsdaten und der Mailversand. Insbesondere wird
    ``mail_autosend`` bewusst **nicht** übernommen, damit ein Duplikat nicht
    ungeprüft bei einer Firma landet.

    Sonstige Anhänge (``MangelDatei``) werden nicht kopiert: Schriftverkehr
    gehört zum ursprünglichen Vorgang, nicht zum neuen Nachunternehmer.
    """
    kopie = Mangel(
        projekt_id=original.projekt_id,
        eltern_mangel_id=original.id,
        nummer=naechste_duplikat_nummer(db, original.projekt_id, original.nummer),
        status=_erster_status(db),
        erstellt_am=date.today(),
        mail_autosend=False,
        mail_versendemodus="manuell",
    )
    for feld in DUPLIKAT_UEBERNAHME:
        setattr(kopie, feld, getattr(original, feld))

    db.add(kopie)
    db.commit()
    db.refresh(kopie)

    _kopiere_fotos(db, original, kopie)
    _kopiere_markierung(db, original, kopie)
    db.commit()
    db.refresh(kopie)
    return kopie


def _kopiere_fotos(db: Session, original: Mangel, kopie: Mangel) -> None:
    """Legt die Fotodateien für das Duplikat neu an.

    Bewusst echte Kopien und keine gemeinsam genutzten Pfade: Wird das
    Original später gelöscht, sollen die Fotos des Duplikats nicht mit
    verschwinden.
    """
    ziel_ordner = settings.upload_dir / "maengel" / str(kopie.id) / "fotos"
    ziel_ordner.mkdir(parents=True, exist_ok=True)

    for foto in original.fotos:
        quelle = settings.upload_dir.parent / foto.dateipfad
        if not quelle.is_file():
            continue
        ziel = ziel_ordner / quelle.name
        zaehler = 1
        while ziel.exists():
            ziel = ziel_ordner / f"{quelle.stem}_{zaehler}{quelle.suffix}"
            zaehler += 1
        try:
            shutil.copyfile(quelle, ziel)
        except OSError:
            continue
        db.add(MangelFoto(
            mangel_id=kopie.id,
            dateipfad=str(Path(ziel).relative_to(settings.upload_dir.parent)),
            bildunterschrift=foto.bildunterschrift,
            reihenfolge=foto.reihenfolge,
        ))


def _kopiere_markierung(db: Session, original: Mangel, kopie: Mangel) -> None:
    markierung = original.markierungen[0] if original.markierungen else None
    if markierung is None:
        return
    db.add(MangelPlanMarkierung(
        mangel_id=kopie.id,
        plan_datei_id=markierung.plan_datei_id,
        x_prozent=markierung.x_prozent,
        y_prozent=markierung.y_prozent,
        seite=markierung.seite,
    ))


# ───────── Fristen und Überfälligkeit ─────────


def abgeschlossene_status(db: Session) -> set[str]:
    """Bezeichnungen der Status, die als abgeschlossen gelten."""
    rows = (
        db.query(MangelStatus.bezeichnung)
        .filter(MangelStatus.ist_abgeschlossen.is_(True))
        .all()
    )
    return {bezeichnung for (bezeichnung,) in rows}


def status_farben(db: Session) -> dict[str, str]:
    rows = db.query(MangelStatus.bezeichnung, MangelStatus.farbe).all()
    return {bezeichnung: farbe for bezeichnung, farbe in rows}


def aktuelle_frist(mangel: Mangel) -> date | None:
    """Die Frist, die zählt: eine gesetzte Nachfrist verdrängt die erste Frist."""
    return mangel.erste_nachfrist_bis or mangel.erste_frist_bis


def ist_abgeschlossen(mangel: Mangel, abgeschlossen: set[str]) -> bool:
    return bool(mangel.erledigt_am) or mangel.status in abgeschlossen


def ist_ueberfaellig(mangel: Mangel, abgeschlossen: set[str],
                     stichtag: date | None = None) -> bool:
    """Frist verstrichen, ohne dass der Mangel abgeschlossen ist.

    Eine Beseitigungsanzeige der Firma (oder eine Freimeldung) zählt noch
    nicht als abgeschlossen — die Prüfung durch das Büro steht dann ja noch
    aus —, wohl aber ein Erledigungsdatum oder ein Status, der in den
    Stammdaten als abgeschlossen markiert ist.
    """
    frist = aktuelle_frist(mangel)
    if frist is None or ist_abgeschlossen(mangel, abgeschlossen):
        return False
    return frist < (stichtag or date.today())
