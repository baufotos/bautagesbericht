"""Konfiguration.

Alle Werte lassen sich per Umgebungsvariable mit Präfix ``BTB_`` überschreiben,
z. B. ``BTB_DATABASE_URL=postgresql+psycopg://...``. In der lokalen Entwicklung
werden die Werte weiterhin aus einer ``.env``-Datei geladen; auf einem
Hosting-Server (Render, Fly.io, ...) werden sie über das Dashboard gesetzt.
"""

import os
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

    # Benachrichtigung per Microsoft-Teams-Kanal-Webhook (siehe
    # app.services.teams_notifier) — der einzige automatische Zustellweg.
    # Zusätzlich gibt es die Übersichtsseite in der App, in der jeder selbst
    # nachschauen kann, ohne dass überhaupt benachrichtigt werden muss.
    # BTB_TEAMS_WEBHOOK_URL kommt aus Teams: Kanal -> "..." -> Workflows ->
    # Vorlage "Send webhook alerts to a channel" (globaler Fallback-Kanal,
    # normalerweise reicht die pro Empfänger hinterlegte Webhook-URL).
    teams_webhook_url: str = ""

    # Öffentlich erreichbare Basis-URL der App, um im Teams-Post einen
    # funktionierenden Download-Link zu erzeugen, z. B.
    # "https://bautagesbericht-jwga.onrender.com". Wird bei Render automatisch
    # aus RENDER_EXTERNAL_URL übernommen, falls nicht explizit gesetzt.
    public_base_url: str = ""

    model_config = {"env_prefix": "BTB_", "env_file": ".env", "extra": "ignore"}


settings = Settings()

if not settings.public_base_url:
    settings.public_base_url = os.environ.get("RENDER_EXTERNAL_URL", "")
