"""SQLAlchemy-Setup.

Funktioniert sowohl mit SQLite (lokal) als auch mit Postgres (Produktion).
Der Treiber wird an der URL erkannt.
"""

from datetime import date

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


if _is_sqlite(settings.database_url):
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    # Postgres: pool_pre_ping fängt geschlossene Verbindungen ab, die bei
    # kostenlosen Free-Tier-Datenbanken (Neon o. ä.) nach Idle-Timeouts auftreten.
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        echo=False,
    )


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401
    _raeume_alte_mcdonalds_tabellen_auf()
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    _seed_mangel_stammdaten()
    _seed_mcdonalds_subplaner()


# Tabellen der ersten McDonald's-Fassung. Sie hießen anders und hatten ein
# anderes Feldschema (``leistungsphase`` 1-9 statt ``phase`` 1-3, ein Angebot
# als Word-Dokument statt eines Einzelabrufs). Beim Umbau am 10.09.2026 sind
# sie ersatzlos entfallen.
ALTE_MCDONALDS_TABELLEN = ("mcdonalds_angebote", "mcdonalds_faelle",
                           "mcdonalds_fachplaner")


def _raeume_alte_mcdonalds_tabellen_auf() -> None:
    """Entfernt die alten McDonald's-Tabellen — aber nur, wenn sie leer sind.

    WARUM UEBERHAUPT LOESCHEN
    =========================
    ``create_all`` legt die neuen Tabellen daneben an und ruehrt die alten
    nicht an. Die blieben dann fuer immer stehen: drei Tabellen, die niemand
    liest, mit Spalten, die es im Modell nicht mehr gibt. Wer spaeter in die
    Datenbank schaut, sieht zwei Feature-Generationen und weiss nicht, welche
    gilt.

    WARUM NUR WENN LEER
    ===================
    Weil ein Loeschen mit Daten Datenverlust waere. Die Bedingung ist die
    Sicherung: Das Feature ist am 04.09.2026 entstanden und wurde am
    10.09.2026 umgebaut, es kann also hoechstens Probierdatensaetze geben.
    Steht irgendwo eine Zeile, bleibt alles liegen und diese Funktion tut
    nichts — dann entscheidet ein Mensch, was damit passiert.

    Die Reihenfolge ist wichtig: ``mcdonalds_angebote`` zeigt per
    Fremdschluessel auf die beiden anderen und muss zuerst weg.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    vorhanden = [t for t in ALTE_MCDONALDS_TABELLEN
                 if t in set(inspector.get_table_names())]
    if not vorhanden:
        return

    with engine.begin() as conn:
        for tabelle in vorhanden:
            anzahl = conn.execute(
                text(f"SELECT COUNT(*) FROM {tabelle}")  # noqa: S608
            ).scalar_one()
            if anzahl:
                return          # Daten drin: nichts anfassen.

        for tabelle in vorhanden:
            conn.execute(text(f"DROP TABLE {tabelle}"))


# Nachträglich ins Modell aufgenommene Spalten, Tabelle -> Spaltenname -> DDL.
#
# Das Projekt nutzt bewusst kein Alembic: ``create_all`` legt fehlende
# *Tabellen* an (neue Tabellen wie ``maengel`` kommen also von selbst), ändert
# aber bestehende Tabellen nicht. Wer eine Spalte zu einer schon deployten
# Tabelle ergänzt, trägt sie hier ein — sonst fehlt sie auf der laufenden
# Neon-Datenbank und der nächste Zugriff schlägt fehl.
#
# Regeln für die DDL: nur ``ADD COLUMN``, immer NULL-erlaubt oder mit
# DEFAULT, und die Formulierung muss für SQLite und Postgres gleich gültig
# sein (also z. B. VARCHAR statt TEXT-spezifischer Typen).
NACHTRAEGLICHE_SPALTEN: dict[str, dict[str, str]] = {
    "empfaenger": {
        "teams_webhook_url": "VARCHAR NOT NULL DEFAULT ''",
    },
    "projekte": {
        # Mängelmanagement: Teams-Kanal des Projekts als Fallback, wenn am
        # Gewerk kein eigener Kanal hinterlegt ist.
        "teams_webhook_url": "VARCHAR NOT NULL DEFAULT ''",
        # Zielordner der Baufotos im Netzlaufwerk (siehe Kommentar am Modell).
        "foto_zielpfad": "VARCHAR NOT NULL DEFAULT ''",
        # Kopfdaten des Besprechungsprotokoll-Deckblatts.
        "projekt_nummer": "VARCHAR NOT NULL DEFAULT ''",
        "bauherr": "VARCHAR NOT NULL DEFAULT ''",
        # Wie genau der hinterlegte Standort ist und was gefunden wurde
        # (siehe Kommentar am Modell). Leer bei Projekten, die vor der
        # Umstellung angelegt wurden — die Karte zeigt dann nur die
        # Koordinaten, wie bisher.
        "standort_guete": "VARCHAR NOT NULL DEFAULT ''",
        "standort_label": "VARCHAR NOT NULL DEFAULT ''",
    },
    "bearbeiter": {
        # Kopfzeile des Besprechungsprotokolls: "Ze: kbl  T - 22".
        "kuerzel": "VARCHAR NOT NULL DEFAULT ''",
        "durchwahl": "VARCHAR NOT NULL DEFAULT ''",
    },
    "gewerke": {
        # Postanschrift der Firma fuer den Adressblock der Maengelanzeige.
        "ansprechpartner": "VARCHAR NOT NULL DEFAULT ''",
        "strasse": "VARCHAR NOT NULL DEFAULT ''",
        "plz": "VARCHAR NOT NULL DEFAULT ''",
        "ort": "VARCHAR NOT NULL DEFAULT ''",
    },
    "fotosaetze": {
        # Baufotos per E-Mail (app.services.fotoversand): Nachweis, wann ein
        # Satz an wen herausging. Nachträglich ergänzt, damit bestehende
        # Installationen ihre Fotos behalten.
        "mail_versendet_am": "DATE",
        "mail_empfaenger": "TEXT NOT NULL DEFAULT ''",
        "mail_weg": "VARCHAR NOT NULL DEFAULT ''",
        # Abholung durch einen Buerorechner (siehe models.Fotosatz).
        "abgeholt_am": "TIMESTAMP",
        "abgeholt_von": "VARCHAR NOT NULL DEFAULT ''",
        "abgeholt_ziel": "TEXT NOT NULL DEFAULT ''",
    },
}


def _ensure_columns() -> None:
    """Leichte Ad-hoc-Migration für neu hinzugekommene Spalten.

    Arbeitet die Tabelle ``NACHTRAEGLICHE_SPALTEN`` ab und ergänzt jede dort
    genannte Spalte, die in der Datenbank noch fehlt. Fehlt die Tabelle
    komplett, ist nichts zu tun — ``create_all`` hat sie dann gerade mit allen
    Spalten neu angelegt.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    vorhandene_tabellen = set(inspector.get_table_names())

    for tabelle, spalten in NACHTRAEGLICHE_SPALTEN.items():
        if tabelle not in vorhandene_tabellen:
            continue
        vorhanden = {col["name"] for col in inspector.get_columns(tabelle)}
        for spalte, ddl in spalten.items():
            if spalte in vorhanden:
                continue
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {ddl}"))


# Startwerte der konfigurierbaren Wertelisten des Mängelmanagements. Sie
# werden nur angelegt, solange die jeweilige Tabelle noch leer ist — wer die
# Listen in der App anpasst oder Einträge löscht, bekommt sie beim nächsten
# Start also nicht zurück.
MANGEL_TYPEN_START = ["Mangel", "Hinweis", "Gefahr", "Frage", "Sonstiges"]

# (Bezeichnung, Farbe, gilt als abgeschlossen)
MANGEL_STATUS_START = [
    ("offen", "#B45309", False),
    ("in Bearbeitung", "#1D4ED8", False),
    ("Nachfrist", "#B91C1C", False),
    ("freigemeldet", "#7C3AED", False),
    ("erledigt", "#15803D", True),
    ("zurückgewiesen", "#991B1B", False),
]

MANGEL_RUECKMELDUNG_START = [
    "keine Rückmeldung",
    "erledigt gemeldet",
    "abgelehnt",
    "in Prüfung",
]


def _seed_mangel_stammdaten() -> None:
    """Legt die Standard-Wertelisten an, falls noch keine vorhanden sind."""
    from app.models import MangelRueckmeldungStatus, MangelStatus, MangelTyp

    db = SessionLocal()
    try:
        if db.query(MangelTyp).count() == 0:
            for i, bezeichnung in enumerate(MANGEL_TYPEN_START, start=1):
                db.add(MangelTyp(bezeichnung=bezeichnung, sortierung=i))

        if db.query(MangelStatus).count() == 0:
            for i, (bezeichnung, farbe, abgeschlossen) in enumerate(
                MANGEL_STATUS_START, start=1
            ):
                db.add(MangelStatus(
                    bezeichnung=bezeichnung,
                    sortierung=i,
                    farbe=farbe,
                    ist_abgeschlossen=abgeschlossen,
                ))

        if db.query(MangelRueckmeldungStatus).count() == 0:
            for i, bezeichnung in enumerate(MANGEL_RUECKMELDUNG_START, start=1):
                db.add(MangelRueckmeldungStatus(bezeichnung=bezeichnung, sortierung=i))

        db.commit()
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Startwerte der McDonald's-Stammdaten
#
# In Phase 1 werden immer dieselben zwei Subplaner beauftragt. Die Angaben
# stammen aus den Musterschreiben des Büros (Stand 10.09.2026) und sind hier
# hinterlegt, damit der Ablauf nach dem Aktualisieren sofort funktioniert,
# ohne dass jemand zwei Firmen von Hand einträgt.
#
# NUR DIE E-MAIL-ADRESSEN FEHLEN
# ==============================
# Sie standen in den Musterschreiben nicht drin und werden deshalb NICHT
# geraten — eine falsche Adresse in einem Einzelabruf fällt erst auf, wenn
# der Subplaner nicht liefert. Die Oberfläche zeigt die beiden Firmen mit dem
# Hinweis "Adresse fehlt" und lässt keinen Entwurf zu, solange keine
# hinterlegt ist (siehe app.routers.mcdonalds).
#
# Angelegt wird nur, solange die Tabelle noch leer ist — wer die Stammdaten
# anpasst oder eine Firma löscht, bekommt sie beim nächsten Start nicht
# zurück. Dieselbe Regel wie bei den Mängel-Wertelisten oben.
# ─────────────────────────────────────────────────────────────────────────────

MCDONALDS_SUBPLANER_START = [
    {
        "phase": 1,
        "kuerzel": "KOCKS",
        "name": "Kocks Consult",
        "ordner": "090_VAA_Kocks",
        "ansprechpartner": "Herr Hömmerich",
        "anrede": "Sehr geehrter Herr Hömmerich,",
        "angebot_datum": date(2026, 2, 27),
        "textvariante": "kocks",
        "sortierung": 1,
    },
    {
        "phase": 1,
        "kuerzel": "RKA",
        "name": "RKA Architekten Ammon & Kanthak PartGmbB",
        "ordner": "010_OPG_ARC_RKA",
        "ansprechpartner": "Frau Ammon",
        "anrede": "Sehr geehrte Frau Ammon,",
        "angebot_datum": date(2026, 3, 12),
        "textvariante": "rka",
        "sortierung": 2,
    },
]


def _seed_mcdonalds_subplaner() -> None:
    """Legt die Subplaner der Phase 1 an, falls noch keine vorhanden sind."""
    from app.models import McdonaldsSubplaner

    db = SessionLocal()
    try:
        if db.query(McdonaldsSubplaner).count() == 0:
            for angaben in MCDONALDS_SUBPLANER_START:
                db.add(McdonaldsSubplaner(emails=[], **angaben))
            db.commit()
    finally:
        db.close()
