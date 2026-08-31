"""Wo Fotos liegen — auf der Platte oder in einem Objektspeicher.

DAS PROBLEM
===========
Auf dem Bürorechner ist die Festplatte dauerhaft: Was dort liegt, liegt
morgen noch da. Auf Render ist sie es nicht. Der Dienst schläft nach 15
Minuten ohne Zugriff ein; beim Aufwachen — und bei jedem Deploy — startet der
Container **leer**. In der Datenbank stünden dann Verweise auf Fotos, die es
nicht mehr gibt.

Für die Baustelle heißt das: Am Vormittag hochgeladene Fotos wären am Abend
verschwunden, wenn niemand sie zwischendurch abgeholt hat. Das ist der Grund
für dieses Modul.

DIE LÖSUNG
==========
Eine dünne Schicht mit zwei Rückwänden:

* **Objektspeicher** (Cloudflare R2 oder jeder andere S3-kompatible Dienst),
  sobald die vier Zugangswerte in der Konfiguration stehen. Fotos überstehen
  dort jeden Neustart.
* **Dateisystem** wie bisher, wenn nichts konfiguriert ist. Genau richtig auf
  dem Bürorechner.

ABWÄRTSKOMPATIBEL
=================
Ein Verweis ist entweder ``objekt:<schlüssel>`` (Objektspeicher) oder ein
relativer Pfad wie bisher. Bestehende Einträge funktionieren unverändert
weiter, auch nachdem R2 eingeschaltet wurde — es gibt keine Migration, alte
Fotos bleiben einfach dort, wo sie sind.
"""

from __future__ import annotations

from pathlib import Path

from app.config import settings

#: Präfix, an dem ein Verweis auf den Objektspeicher zu erkennen ist.
OBJEKT_PRAEFIX = "objekt:"

#: Einmal aufgebauter Client. ``False`` heißt "geprüft, nicht verfügbar".
_client: object | None = None


def objektspeicher_aktiv() -> bool:
    """Ist ein Objektspeicher konfiguriert und erreichbar?"""
    return _hole_client() is not None


def _hole_client():
    """Baut den S3-Client einmalig auf. None, wenn nicht konfiguriert."""
    global _client
    if _client is False:
        return None
    if _client is not None:
        return _client

    if not (settings.r2_endpoint and settings.r2_bucket
            and settings.r2_key_id and settings.r2_secret):
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


def ist_objekt(verweis: str) -> bool:
    return (verweis or "").startswith(OBJEKT_PRAEFIX)


def _schluessel(verweis: str) -> str:
    return verweis[len(OBJEKT_PRAEFIX):]


def _dateipfad(verweis: str) -> Path:
    return settings.upload_dir.parent / verweis


async def schreibe(unterordner: str, dateiname: str, daten: bytes) -> str:
    """Legt ein Foto ab und gibt den Verweis zurück, der in die Datenbank kommt.

    ``unterordner`` ist die fachliche Ablage (z. B. ``baufotos/12``),
    ``dateiname`` der bereits nach Büroregel umbenannte Name.
    """
    client = _hole_client()
    if client is None:
        # Dateisystem — derselbe Weg wie bisher.
        ziel_ordner = settings.upload_dir / unterordner
        ziel_ordner.mkdir(parents=True, exist_ok=True)
        ziel = ziel_ordner / dateiname
        zaehler = 1
        while ziel.exists():
            ziel = ziel_ordner / f"{Path(dateiname).stem}_{zaehler}{Path(dateiname).suffix}"
            zaehler += 1
        ziel.write_bytes(daten)
        return str(ziel.relative_to(settings.upload_dir.parent))

    schluessel = f"{unterordner}/{dateiname}"
    client.put_object(
        Bucket=settings.r2_bucket,
        Key=schluessel,
        Body=daten,
        ContentType="image/jpeg",
    )
    return f"{OBJEKT_PRAEFIX}{schluessel}"


def lies(verweis: str) -> bytes | None:
    """Holt ein Foto zurück. None, wenn es nicht (mehr) da ist."""
    if not verweis:
        return None

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


def existiert(verweis: str) -> bool:
    if not verweis:
        return False
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


def loesche(verweis: str) -> None:
    """Entfernt ein Foto. Fehler werden geschluckt — ein nicht löschbares
    Foto darf das Löschen des Datensatzes nicht verhindern."""
    if not verweis:
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


def beschreibung() -> str:
    """Klartext für die Oberfläche und die Protokolle."""
    if objektspeicher_aktiv():
        return (f"Objektspeicher aktiv (Bucket {settings.r2_bucket}) — "
                "Fotos überstehen einen Neustart des Servers.")
    return ("Fotos liegen im Dateisystem. Auf einem Server mit flüchtigem "
            "Speicher gehen sie beim Neustart verloren — dort bitte die vier "
            "R2-Werte setzen (BTB_R2_ENDPOINT, BTB_R2_BUCKET, BTB_R2_KEY_ID, "
            "BTB_R2_SECRET).")
