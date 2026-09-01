"""SQLAlchemy-Setup.

Funktioniert sowohl mit SQLite (lokal) als auch mit Postgres (Produktion).
Der Treiber wird an der URL erkannt.
"""

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
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    _seed_mangel_stammdaten()


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
