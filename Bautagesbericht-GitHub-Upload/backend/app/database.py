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
