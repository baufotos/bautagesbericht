"""Konfiguration.

Alle Werte lassen sich per Umgebungsvariable mit Präfix ``BTB_`` überschreiben,
z. B. ``BTB_DATABASE_URL=postgresql+psycopg://...``. In der lokalen Entwicklung
werden die Werte weiterhin aus einer ``.env``-Datei geladen; auf einem
Hosting-Server (Render, Fly.io, ...) werden sie über das Dashboard gesetzt.
"""

import os
from pathlib import Path
from pydantic import AliasChoices, Field
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

    # Verzeichnis mit der statisch exportierten Oberfläche. Nur im Windows-Paket
    # belegt — dort liefert dieser Prozess auch die Seite aus, damit auf dem
    # Bürorechner kein Node.js nötig ist (siehe app.main). Auf Render bleibt es
    # leer, weil Next.js die Oberfläche selbst ausliefert.
    # Ohne ausdrückliche Angabe wird ``backend/static`` genommen, falls
    # vorhanden — genau dorthin legt das Paket die Dateien.
    static_dir: Path | None = None

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

    # Postausgangsserver für "Baufotos per E-Mail" (app.services.fotoversand).
    # Bleibt BTB_SMTP_HOST leer, bietet die App nur den Outlook-Entwurf an —
    # der braucht keinen Server und funktioniert deshalb überall. Im Büronetz
    # genügt meist das hausinterne Relay ohne Anmeldung:
    #   BTB_SMTP_HOST=mail.hpp.local
    #   BTB_SMTP_PORT=25
    #   BTB_SMTP_TLS=false
    #   BTB_SMTP_ABSENDER=baumanagement@hpp.com
    # Bei einem Anbieter mit Anmeldung zusätzlich BTB_SMTP_USER und
    # BTB_SMTP_PASSWORT. Port 465 schaltet automatisch auf SMTP über SSL um,
    # bei allen anderen Ports greift STARTTLS, solange BTB_SMTP_TLS gilt.
    # Die beiden englischen Namen (BTB_SMTP_PASSWORD, BTB_SMTP_FROM) stehen so
    # in ANLEITUNG-ONLINE-STELLEN.md und sind bei Render vielleicht schon
    # eingetragen — sie gelten deshalb weiter. Ein stillschweigend ignorierter
    # Wert wäre die schlimmere Variante: Der Versand scheitert dann an einer
    # Anmeldung, deren Kennwort scheinbar gesetzt ist.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_passwort: str = Field(
        default="",
        validation_alias=AliasChoices("BTB_SMTP_PASSWORT", "BTB_SMTP_PASSWORD"),
    )
    smtp_tls: bool = True
    smtp_absender: str = Field(
        default="",
        validation_alias=AliasChoices("BTB_SMTP_ABSENDER", "BTB_SMTP_FROM"),
    )
    smtp_absender_name: str = "HPP Baumanagement"

    # Öffentlich erreichbare Basis-URL der App, um im Teams-Post einen
    # funktionierenden Download-Link zu erzeugen, z. B.
    # "https://bautagesbericht-jwga.onrender.com". Wird bei Render automatisch
    # aus RENDER_EXTERNAL_URL übernommen, falls nicht explizit gesetzt.
    public_base_url: str = ""

    model_config = {"env_prefix": "BTB_", "env_file": ".env", "extra": "ignore"}


settings = Settings()

if not settings.public_base_url:
    settings.public_base_url = os.environ.get("RENDER_EXTERNAL_URL", "")

if settings.static_dir is None:
    # Vorhandenes backend/static bedeutet: Wir laufen als Windows-Paket und
    # liefern die Oberfläche selbst aus. Fehlt der Ordner, bleibt es bei None
    # und app.main bindet nichts ein.
    _mitgeliefert = BASE_DIR / "static"
    settings.static_dir = _mitgeliefert if _mitgeliefert.is_dir() else None
