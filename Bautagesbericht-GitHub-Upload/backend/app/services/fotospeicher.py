"""Wo Fotos liegen, bis das Büro sie abgeholt hat.

DAS PROBLEM
===========
Auf dem Bürorechner ist die Festplatte dauerhaft: Was dort liegt, liegt
morgen noch da. Auf Render ist sie es nicht. Der Dienst schläft nach 15
Minuten ohne Zugriff ein; beim Aufwachen — und bei jedem Deploy — startet der
Container **leer**. In der Datenbank stünden dann Verweise auf Fotos, die es
nicht mehr gibt.

Für die Baustelle heißt das: Am Vormittag hochgeladene Fotos wären am Abend
verschwunden, wenn niemand sie zwischendurch abgeholt hat.

DIE LÖSUNG — OHNE ZUSÄTZLICHE KOSTEN
====================================
Die Fotos wandern in **dieselbe Datenbank**, in der ohnehin Projekte, Berichte
und Mängel liegen. Die ist dauerhaft, kostet nichts extra und muss nirgends
angemeldet werden. Kein zusätzlicher Dienst, keine Kreditkarte, kein zweites
Passwort — der übliche Weg (ein Objektspeicher wie Cloudflare R2) verlangt
beides, und dafür ist die Menge hier zu klein.

Denn die Datenbank ist hier **kein Archiv, sondern ein Durchgang**: Ein Foto
liegt dort von Baustelle bis Bürorechner, im Regelfall eine Viertelstunde.
Was im Projektverzeichnis angekommen ist, wird nach einer Schonfrist wieder
freigegeben (siehe ``raeume_auf``). Das dauerhafte Archiv ist ``L:``.

DREI RÜCKWÄNDE
==============
``BTB_FOTOSPEICHER`` bestimmt, welche gilt:

``datei``
    Wie bisher im Dateisystem. Richtig auf dem Bürorechner, wo die Platte
    selbst dauerhaft ist. Das ist der Standard.
``db``
    In der Datenbank. Richtig auf Render und überall, wo der Container
    flüchtig ist.
``objekt``
    S3-kompatibler Objektspeicher (Cloudflare R2, Backblaze B2, MinIO im
    eigenen Haus). Bleibt für den Fall, dass die Fotomenge einmal wächst.

Ohne Angabe entscheidet die Konfiguration: Sind die vier ``BTB_R2_*``-Werte
gesetzt, gilt ``objekt``, sonst ``datei``.

ABWÄRTSKOMPATIBEL
=================
Ein Verweis ist ``db:<schlüssel>``, ``objekt:<schlüssel>`` oder — wie bisher —
ein relativer Pfad. Bestehende Einträge funktionieren unverändert weiter, auch
nach einem Wechsel der Rückwand. Es gibt keine Migration; alte Fotos bleiben
einfach dort, wo sie sind.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings

#: Präfixe, an denen die Rückwand eines Verweises zu erkennen ist.
DB_PRAEFIX = "db:"
OBJEKT_PRAEFIX = "objekt:"

#: Einmal aufgebauter S3-Client. ``False`` heißt "geprüft, nicht verfügbar".
_client: object | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Welche Rückwand gilt?
# ─────────────────────────────────────────────────────────────────────────────


def _r2_konfiguriert() -> bool:
    return bool(settings.r2_endpoint and settings.r2_bucket
                and settings.r2_key_id and settings.r2_secret)


def art() -> str:
    """"datei", "db" oder "objekt" — die aktuell gültige Rückwand."""
    gewaehlt = (settings.fotospeicher or "").strip().lower()
    if gewaehlt in ("datei", "db", "objekt"):
        return gewaehlt
    return "objekt" if _r2_konfiguriert() else "datei"


def objektspeicher_aktiv() -> bool:
    return art() == "objekt" and _hole_client() is not None


def _hole_client():
    """Baut den S3-Client einmalig auf. None, wenn nicht konfiguriert."""
    global _client
    if _client is False:
        return None
    if _client is not None:
        return _client

    if not _r2_konfiguriert():
        _client = False
        return None

    try:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint,
            aws_access_key_id=settings.r2_key_id,
            aws_secret_access_key=settings.r2_secret,
            # R2 kennt keine Regionen; "auto" ist der von Cloudflare
            # vorgesehene Wert. Signaturversion 4 ist Pflicht.
            region_name="auto",
            config=Config(signature_version="s3v4",
                          retries={"max_attempts": 3, "mode": "standard"}),
        )
    except Exception:
        # Kein boto3 im Paket oder falsche Zugangsdaten: Die App läuft
        # weiter mit dem Dateisystem, statt beim Start zu scheitern.
        _client = False
        return None
    return _client


# ─────────────────────────────────────────────────────────────────────────────
# Verweise lesen
# ─────────────────────────────────────────────────────────────────────────────


def ist_objekt(verweis: str) -> bool:
    return (verweis or "").startswith(OBJEKT_PRAEFIX)


def ist_db(verweis: str) -> bool:
    return (verweis or "").startswith(DB_PRAEFIX)


def ist_datei(verweis: str) -> bool:
    """Zeigt der Verweis auf eine Datei auf der Platte?

    Der Router liefert solche Fotos als Datei aus (schneller, unterstützt
    Teilabrufe); alles andere kommt als Bytes.
    """
    return bool(verweis) and not ist_objekt(verweis) and not ist_db(verweis)


def _schluessel(verweis: str) -> str:
    if ist_db(verweis):
        return verweis[len(DB_PRAEFIX):]
    return verweis[len(OBJEKT_PRAEFIX):]


def _dateipfad(verweis: str) -> Path:
    return settings.upload_dir.parent / verweis


def _sitzung(db: Session | None):
    """Vorhandene Sitzung benutzen, sonst eine eigene aufmachen.

    Gibt ``(sitzung, selbst_geoeffnet)`` zurück — der Aufrufer schließt nur,
    was er selbst geöffnet hat.
    """
    if db is not None:
        return db, False
    from app.database import SessionLocal

    return SessionLocal(), True


# ─────────────────────────────────────────────────────────────────────────────
# Ablegen, holen, löschen
# ─────────────────────────────────────────────────────────────────────────────


async def schreibe(unterordner: str, dateiname: str, daten: bytes,
                   db: Session | None = None) -> str:
    """Legt ein Foto ab und gibt den Verweis zurück, der in die Datenbank kommt.

    ``unterordner`` ist die fachliche Ablage (z. B. ``baufotos/12``),
    ``dateiname`` der bereits nach Büroregel umbenannte Name.
    """
    rueckwand = art()

    if rueckwand == "db":
        from app.models import Fotoblob

        sitzung, selbst = _sitzung(db)
        try:
            schluessel = f"{unterordner}/{dateiname}"
            # Gleicher Name schon vergeben: durchnummerieren, damit kein Foto
            # ein anderes überschreibt (dieselbe Regel wie im Dateisystem).
            stamm, endung = Path(dateiname).stem, Path(dateiname).suffix
            zaehler = 1
            while sitzung.query(Fotoblob.id).filter(
                Fotoblob.schluessel == schluessel
            ).first():
                schluessel = f"{unterordner}/{stamm}_{zaehler}{endung}"
                zaehler += 1

            sitzung.add(Fotoblob(schluessel=schluessel, daten=daten,
                                 groesse_bytes=len(daten)))
            sitzung.commit()
            return f"{DB_PRAEFIX}{schluessel}"
        finally:
            if selbst:
                sitzung.close()

    if rueckwand == "objekt":
        client = _hole_client()
        if client is not None:
            schluessel = f"{unterordner}/{dateiname}"
            client.put_object(
                Bucket=settings.r2_bucket,
                Key=schluessel,
                Body=daten,
                ContentType="image/jpeg",
            )
            return f"{OBJEKT_PRAEFIX}{schluessel}"
        # Kein Client zustande gekommen: lieber auf der Platte ablegen als
        # das Foto der Baustelle zurückweisen.

    ziel_ordner = settings.upload_dir / unterordner
    ziel_ordner.mkdir(parents=True, exist_ok=True)
    ziel = ziel_ordner / dateiname
    zaehler = 1
    while ziel.exists():
        ziel = ziel_ordner / f"{Path(dateiname).stem}_{zaehler}{Path(dateiname).suffix}"
        zaehler += 1
    ziel.write_bytes(daten)
    return str(ziel.relative_to(settings.upload_dir.parent))


def lies(verweis: str, db: Session | None = None) -> bytes | None:
    """Holt ein Foto zurück. None, wenn es nicht (mehr) da ist."""
    if not verweis:
        return None

    if ist_db(verweis):
        from app.models import Fotoblob

        sitzung, selbst = _sitzung(db)
        try:
            treffer = (
                sitzung.query(Fotoblob.daten)
                .filter(Fotoblob.schluessel == _schluessel(verweis))
                .first()
            )
            return bytes(treffer[0]) if treffer else None
        finally:
            if selbst:
                sitzung.close()

    if ist_objekt(verweis):
        client = _hole_client()
        if client is None:
            return None
        try:
            antwort = client.get_object(Bucket=settings.r2_bucket,
                                        Key=_schluessel(verweis))
            return antwort["Body"].read()
        except Exception:
            return None

    pfad = _dateipfad(verweis)
    try:
        return pfad.read_bytes() if pfad.is_file() else None
    except OSError:
        return None


def existiert(verweis: str, db: Session | None = None) -> bool:
    if not verweis:
        return False

    if ist_db(verweis):
        from app.models import Fotoblob

        sitzung, selbst = _sitzung(db)
        try:
            return bool(
                sitzung.query(Fotoblob.id)
                .filter(Fotoblob.schluessel == _schluessel(verweis))
                .first()
            )
        finally:
            if selbst:
                sitzung.close()

    if ist_objekt(verweis):
        client = _hole_client()
        if client is None:
            return False
        try:
            client.head_object(Bucket=settings.r2_bucket,
                               Key=_schluessel(verweis))
            return True
        except Exception:
            return False

    return _dateipfad(verweis).is_file()


def loesche(verweis: str, db: Session | None = None) -> None:
    """Entfernt ein Foto. Fehler werden geschluckt — ein nicht löschbares
    Foto darf das Löschen des Datensatzes nicht verhindern."""
    if not verweis:
        return

    if ist_db(verweis):
        from app.models import Fotoblob

        sitzung, selbst = _sitzung(db)
        try:
            sitzung.query(Fotoblob).filter(
                Fotoblob.schluessel == _schluessel(verweis)
            ).delete(synchronize_session=False)
            sitzung.commit()
        except Exception:
            sitzung.rollback()
        finally:
            if selbst:
                sitzung.close()
        return

    if ist_objekt(verweis):
        client = _hole_client()
        if client is None:
            return
        try:
            client.delete_object(Bucket=settings.r2_bucket,
                                 Key=_schluessel(verweis))
        except Exception:
            pass
        return

    from app.services.bilder import loesche_mit_thumbnail

    loesche_mit_thumbnail(_dateipfad(verweis))


# ─────────────────────────────────────────────────────────────────────────────
# Aufräumen
#
# Nur nötig, wenn die Fotos in der Datenbank liegen: Dort ist der Platz
# begrenzt (das kostenlose Neon-Kontingent umfasst 0,5 GB), und ein Foto, das
# im Projektverzeichnis angekommen ist, wird hier nicht mehr gebraucht.
#
# EISERNE REGEL: Es wird ausschließlich gelöscht, was ein Bürorechner
# quittiert hat — was noch aussteht, bleibt liegen, egal wie voll es wird.
# Lieber eine volle Datenbank als ein verlorener Fotosatz.
# ─────────────────────────────────────────────────────────────────────────────


def belegung_bytes(db: Session) -> int:
    """Wie viel Platz die Fotos in der Datenbank belegen."""
    if art() != "db":
        return 0
    from app.models import Fotoblob

    return int(db.query(func.coalesce(func.sum(Fotoblob.groesse_bytes), 0)).scalar() or 0)


def raeume_auf(db: Session, jetzt: datetime | None = None) -> tuple[int, int]:
    """Gibt Platz frei, den abgeholte Fotosätze nicht mehr brauchen.

    Zwei Anlässe, beide betreffen nur quittierte Sätze:

    1. **Schonfrist abgelaufen.** Nach ``BTB_FOTOS_AUFBEWAHREN_TAGE`` sind die
       Fotos im Projektordner angekommen und dort auch gesichert. Die
       Schonfrist gibt es, damit die Galerie in der App direkt nach dem Termin
       noch Vorschaubilder zeigt.
    2. **Platz wird knapp.** Über ``BTB_FOTOS_MAX_MB`` werden zusätzlich die
       ältesten abgeholten Sätze geleert, bis wieder Luft ist.

    Der Datensatz bleibt in beiden Fällen erhalten — Name, Größe und der
    Zielordner stehen weiter in der App, nur die Bilddaten sind fort.

    Gibt ``(geleerte Fotos, freigegebene Bytes)`` zurück.
    """
    if art() != "db":
        return 0, 0

    from app.models import Baufoto, Fotoblob, Fotosatz

    jetzt = jetzt or datetime.now()
    grenze = jetzt - timedelta(days=max(0, settings.fotos_aufbewahren_tage))

    # Alle abgeholten Sätze, die ältesten zuerst — in dieser Reihenfolge wird
    # auch geleert, wenn der Platz knapp wird.
    abgeholt = (
        db.query(Fotosatz)
        .filter(Fotosatz.abgeholt_ziel != "")
        .filter(Fotosatz.abgeholt_am.isnot(None))
        .order_by(Fotosatz.abgeholt_am)
        .all()
    )
    if not abgeholt:
        return 0, 0

    frei_ab = max(0, settings.fotos_max_mb) * 1024 * 1024
    belegt = belegung_bytes(db)

    anzahl = 0
    bytes_frei = 0
    for satz in abgeholt:
        ueberfaellig = satz.abgeholt_am is not None and satz.abgeholt_am < grenze
        zu_voll = frei_ab and (belegt - bytes_frei) > frei_ab
        if not ueberfaellig and not zu_voll:
            continue

        verweise = [
            f.dateipfad
            for f in db.query(Baufoto).filter(Baufoto.fotosatz_id == satz.id).all()
            if ist_db(f.dateipfad)
        ]
        if not verweise:
            continue

        schluessel = [_schluessel(v) for v in verweise]
        summe = int(
            db.query(func.coalesce(func.sum(Fotoblob.groesse_bytes), 0))
            .filter(Fotoblob.schluessel.in_(schluessel))
            .scalar() or 0
        )
        geloescht = (
            db.query(Fotoblob)
            .filter(Fotoblob.schluessel.in_(schluessel))
            .delete(synchronize_session=False)
        )
        db.commit()
        anzahl += geloescht
        bytes_frei += summe

    return anzahl, bytes_frei


def beschreibung() -> str:
    """Klartext für die Oberfläche und die Protokolle."""
    rueckwand = art()
    if rueckwand == "db":
        return ("Fotos liegen in der Datenbank und überstehen einen Neustart "
                "des Servers. Abgeholte Sätze werden nach "
                f"{settings.fotos_aufbewahren_tage} Tag(en) dort wieder "
                "freigegeben — das Archiv ist der Projektordner.")
    if rueckwand == "objekt":
        return (f"Objektspeicher aktiv (Bucket {settings.r2_bucket}) — "
                "Fotos überstehen einen Neustart des Servers.")
    return ("Fotos liegen im Dateisystem. Auf einem Server mit flüchtigem "
            "Speicher gehen sie beim Neustart verloren — dort bitte "
            "BTB_FOTOSPEICHER=db setzen.")
