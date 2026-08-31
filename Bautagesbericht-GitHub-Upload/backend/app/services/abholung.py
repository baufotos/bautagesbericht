"""Der Weg vom Server ins Netzlaufwerk.

WARUM ES DIESES MODUL GIBT
==========================
Die Fotos werden auf der Baustelle mit dem Handy hochgeladen. Liegen sollen sie
am Ende in ``L:\\Bauleitung-Hamburg\\<Projekt>\\01 FOTOS\\<JJMMTT>_<Tätigkeit>``.
Dazwischen liegt eine Grenze, die sich nicht wegprogrammieren lässt: ``L:`` ist
ein Laufwerk im Büronetz, der Server steht im Internet. Der Server kann dort
nicht hineinschreiben.

Also holt das Büro ab. Auf den Bürorechnern läuft ein kleines PowerShell-Skript
(``desktop/abholung/Baufotos-Abholen.ps1``) in der Aufgabenplanung, das hier
nachfragt: "Was liegt bereit?" — herunterlädt, entpackt und zurückmeldet.

WARUM ES NICHT REICHT, EINFACH ALLES ABZUHOLEN
==============================================
Jedes Teammitglied bekommt das Skript, damit die Fotos auch dann ankommen,
wenn ein bestimmter Rechner aus ist. Damit laufen mehrere Abholer parallel, und
ohne Absprache legten sie denselben Satz mehrfach ab. Deshalb der dreistufige
Ablauf:

1. **Beanspruchen** — der erste Rechner bekommt den Satz, alle anderen eine
   Abfuhr (409). Das ist ein einziges bedingtes UPDATE, also auch dann
   eindeutig, wenn zwei Rechner in derselben Sekunde fragen.
2. **Abholen** — ZIP laden, entpacken, ablegen.
3. **Quittieren** — mit dem tatsächlichen Zielpfad. Erst damit gilt der Satz
   als erledigt.

Bricht ein Rechner zwischen 1 und 3 ab (Neustart, Netzlaufwerk weg), verfällt
der Anspruch nach ``abhol_anspruch_minuten`` und der Satz taucht wieder auf.
Ein Satz kann dadurch im schlimmsten Fall zweimal abgelegt werden — mit
identischem Inhalt unter identischem Namen. Das ist der harmlosere Fehler:
Lieber einmal zu viel im Projektordner als ein Fotosatz, der nie ankommt.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Baufoto, Fotosatz, Projekt
from app.services import baufotos as dienst


def ordnername(fotosatz: Fotosatz) -> str:
    """``{JJMMTT}_{Tätigkeit}`` — der Ordner im Projektverzeichnis.

    Dieselbe Regel wie im bisherigen Baustellenfotos-Werkzeug des Büros: Das
    Datum vorn sortiert die Ordner chronologisch, die Tätigkeit dahinter macht
    sie lesbar ("260819_Baustellenbegehung").
    """
    return f"{dienst.datum_stempel(fotosatz.datum)}_{dienst.sanitize(fotosatz.kategorie)}"


def jetzt_laut_db(db: Session) -> datetime:
    """Die aktuelle Zeit, gemessen an der Uhr der Datenbank.

    Warum nicht ``datetime.now()``: ``hochgeladen_am`` und ``erstellt_am``
    werden von der Datenbank selbst gesetzt (``func.now()``). SQLite schreibt
    dabei UTC, während ``datetime.now()`` die lokale Zeit des Rechners liefert
    — in Hamburg im Sommer zwei Stunden Unterschied. Ein Vergleich zwischen
    beiden Uhren wäre je nach Jahreszeit um ein bis zwei Stunden daneben, und
    die Ruhezeit vor dem Abholen träfe nie zu.

    Deshalb kommt hier **eine** Uhr zum Einsatz: die der Datenbank. Auch die
    selbst geschriebenen Zeitstempel (``abgeholt_am``) stammen von ihr.
    """
    wert = db.query(func.now()).scalar()
    if isinstance(wert, str):
        # SQLite liefert Text ("2026-08-31 07:12:34").
        try:
            return datetime.fromisoformat(wert)
        except ValueError:
            return datetime.now()
    if wert is None:
        return datetime.now()
    # Postgres liefert einen Wert mit Zeitzone; die Spalten sind ohne. Ohne
    # tzinfo passt der Wert zu dem, was func.now() in die Spalte schreibt.
    return wert.replace(tzinfo=None)


def _anspruch_verfaellt_vor(jetzt: datetime) -> datetime:
    return jetzt - timedelta(minutes=max(1, settings.abhol_anspruch_minuten))


def _ruhe_seit(jetzt: datetime) -> datetime:
    return jetzt - timedelta(minutes=max(0, settings.abhol_wartezeit_minuten))


def ist_offen(fotosatz: Fotosatz, jetzt: datetime) -> bool:
    """Wartet dieser Satz noch auf das Netzlaufwerk?

    Quittiert (``abgeholt_ziel`` gefüllt) heißt endgültig erledigt. Ein
    beanspruchter, aber nicht quittierter Satz gilt wieder als offen, sobald
    der Anspruch verfallen ist.
    """
    if (fotosatz.abgeholt_ziel or "").strip():
        return False
    if fotosatz.abgeholt_am is None:
        return True
    return fotosatz.abgeholt_am < _anspruch_verfaellt_vor(jetzt)


def offene_saetze(db: Session, jetzt: datetime | None = None) -> list[Fotosatz]:
    """Alle Sätze, die abgeholt werden dürfen — älteste zuerst.

    Ausgeschlossen sind Sätze ohne Fotos und solche, in die vor weniger als
    ``abhol_wartezeit_minuten`` noch ein Foto gelegt wurde: Auf der Baustelle
    lädt jemand 20 Fotos einzeln hoch, und ein Satz, der nach dem dritten Foto
    abgeholt wird, käme unvollständig im Projektordner an.
    """
    jetzt = jetzt or jetzt_laut_db(db)
    grenze = _ruhe_seit(jetzt)
    verfall = _anspruch_verfaellt_vor(jetzt)

    letztes_foto = (
        db.query(
            Baufoto.fotosatz_id.label("satz_id"),
            func.max(Baufoto.hochgeladen_am).label("zuletzt"),
            func.count(Baufoto.id).label("anzahl"),
        )
        .group_by(Baufoto.fotosatz_id)
        .subquery()
    )

    saetze = (
        db.query(Fotosatz)
        .join(letztes_foto, letztes_foto.c.satz_id == Fotosatz.id)
        .filter(letztes_foto.c.anzahl > 0)
        # Beides zusammen heißt "offen": nie beansprucht ODER Anspruch verfallen,
        # und in beiden Fällen noch nicht quittiert.
        .filter(
            (Fotosatz.abgeholt_am.is_(None)) | (Fotosatz.abgeholt_am < verfall)
        )
        .filter((Fotosatz.abgeholt_ziel == "") | (Fotosatz.abgeholt_ziel.is_(None)))
        .order_by(Fotosatz.datum, Fotosatz.id)
        .all()
    )

    # Ruhezeit in Python statt in SQL: ``hochgeladen_am`` kann bei alten
    # Datensätzen NULL sein (die Spalte kam später dazu), und ein NULL-Vergleich
    # in SQL würde diese Sätze für immer aussperren.
    reif = []
    for satz in saetze:
        zeiten = [f.hochgeladen_am for f in satz.fotos if f.hochgeladen_am]
        if zeiten and max(zeiten) > grenze:
            continue
        reif.append(satz)
    return reif


def beanspruche(db: Session, fotosatz_id: int, rechner: str,
                jetzt: datetime | None = None) -> tuple[bool, str]:
    """Reserviert einen Satz für genau einen Bürorechner.

    Gibt ``(erfolg, nachricht)`` zurück. Das UPDATE trägt die Bedingung in
    sich, damit zwischen Prüfen und Schreiben kein zweiter Rechner
    dazwischenkommen kann — kein ``SELECT`` davor, das wäre die Lücke.
    """
    jetzt = jetzt or jetzt_laut_db(db)
    verfall = _anspruch_verfaellt_vor(jetzt)

    getroffen = (
        db.query(Fotosatz)
        .filter(Fotosatz.id == fotosatz_id)
        .filter(
            (Fotosatz.abgeholt_am.is_(None)) | (Fotosatz.abgeholt_am < verfall)
        )
        .filter((Fotosatz.abgeholt_ziel == "") | (Fotosatz.abgeholt_ziel.is_(None)))
        .update(
            {"abgeholt_am": jetzt, "abgeholt_von": (rechner or "").strip()[:120]},
            synchronize_session=False,
        )
    )
    db.commit()

    if getroffen:
        return True, "Fotosatz reserviert."

    satz = db.get(Fotosatz, fotosatz_id)
    if satz is None:
        return False, "Fotosatz nicht gefunden."
    if (satz.abgeholt_ziel or "").strip():
        return False, (
            f"Bereits abgeholt von {satz.abgeholt_von or 'einem anderen Rechner'} "
            f"nach {satz.abgeholt_ziel}."
        )
    return False, (
        f"Wird gerade von {satz.abgeholt_von or 'einem anderen Rechner'} abgeholt."
    )


def quittiere(db: Session, fotosatz: Fotosatz, rechner: str, ziel: str,
              jetzt: datetime | None = None) -> None:
    """Trägt ein, dass der Satz im Projektordner liegt."""
    fotosatz.abgeholt_am = jetzt or jetzt_laut_db(db)
    if (rechner or "").strip():
        fotosatz.abgeholt_von = rechner.strip()[:120]
    fotosatz.abgeholt_ziel = (ziel or "").strip()
    db.commit()


def gib_frei(db: Session, fotosatz: Fotosatz) -> None:
    """Nimmt einen Anspruch zurück — für den Fehlerfall im Abholskript.

    Ohne diesen Weg müsste das Skript nach einem gescheiterten Entpacken die
    Verfallszeit abwarten. So steht der Satz sofort wieder bereit.
    """
    fotosatz.abgeholt_am = None
    fotosatz.abgeholt_von = ""
    fotosatz.abgeholt_ziel = ""
    db.commit()


def zielpfad_von(projekt: Projekt | None) -> str:
    """Der in den Projektstammdaten gepflegte Ordner, ohne Schrägstrich am Ende."""
    if projekt is None:
        return ""
    return (projekt.foto_zielpfad or "").strip().rstrip("\\/")
