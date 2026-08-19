"""Konfiguration.

Alle Werte lassen sich per Umgebungsvariable mit Präfix ``BTB_`` überschreiben,
z. B. ``BTB_DATABASE_URL=postgresql+psycopg://...``. In der lokalen Entwicklung
werden die Werte weiterhin aus einer ``.env``-Datei geladen; auf einem
Hosting-Server (Render, Fly.io, ...) werden sie über das Dashboard gesetzt.
"""

from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Datenbank: SQLite lokal, Postgres (Neon/Supabase/Render) in Produktion.
    # In Produktion setze BTB_DATABASE_URL auf die von Neon gelieferte URL,
    # z. B. "postgresql+psycopg://user:pw@host/db?sslmode=require".
    database_url: str = f"sqlite:///{BASE_DIR / 'storage' / 'bautagesberichte.db'}"

    upload_dir: Path = BASE_DIR / "storage" / "uploads"
    output_dir: Path = BASE_DIR / "storage" / "output"
    template_dir: Path = BASE_DIR / "templates"

    # Wer darf das API im Browser aufrufen? Standard: lokaler Next-Dev-Server.
    # In Produktion die deployte Frontend-URL eintragen, z. B.
    # BTB_CORS_ORIGINS='["https://bautagesbericht.vercel.app"]'
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    max_file_size_mb: int = 50
    max_files_per_submission: int = 20

    anthropic_api_key: str = ""
    nominatim_user_agent: str = "bautagesbericht-hpp/1.0"

    # SMTP-Versand — Zugangsdaten kommen ausschließlich aus Umgebungsvariablen.
    # BTB_SMTP_HOST, BTB_SMTP_PORT, BTB_SMTP_USER, BTB_SMTP_PASSWORD,
    # BTB_SMTP_FROM (Absender-Adresse, z. B. bautagesbericht@hpp.com),
    # BTB_SMTP_USE_TLS (True/False, Standard True = STARTTLS auf Port 587).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

    model_config = {"env_prefix": "BTB_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
