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
    # Kennung fuer die Kartendienste (Nominatim, Photon). Nominatim sperrt
    # nichtssagende Kennungen - eine Sperre saehe in der App genauso aus wie
    # eine nicht gefundene Adresse, deshalb steht hier etwas Erkennbares.
    # Bewusst ohne persoenliche Daten: Der Dienst braucht das Buero, nicht die
    # Mailadresse eines Mitarbeiters.
    nominatim_user_agent: str = (
        "HPP-Baumanagement/1.0 (+https://bautagesbericht.onrender.com)"
    )

    # ── Wo hochgeladene Fotos liegen ──
    #
    # Warum das eine Frage ist: Auf Render liegt das Dateisystem im Container.
    # Der Dienst schläft nach 15 Minuten ohne Zugriff ein, und beim Aufwachen —
    # ebenso bei jedem Deploy — startet der Container leer. Hochgeladene Fotos
    # wären dann verschwunden, während in der Datenbank noch ihre Verweise
    # stehen. Für Baustellendokumentation ist das nicht tragbar.
    #
    #   "datei"  Dateisystem wie bisher. Standard und auf dem Bürorechner
    #            richtig, denn dort ist die Platte dauerhaft.
    #   "db"     In der Datenbank. Richtig auf Render: dauerhaft, ohne
    #            zusätzlichen Dienst und ohne Zusatzkosten. Die Fotos liegen
    #            dort nur bis zur Abholung durch das Büro, danach werden sie
    #            wieder freigegeben (app.services.fotospeicher.raeume_auf).
    #   "objekt" S3-kompatibler Objektspeicher, siehe BTB_R2_* unten.
    #
    # Leer = selbst entscheiden: Objektspeicher, wenn die vier R2-Werte
    # gesetzt sind, sonst Dateisystem.
    fotospeicher: str = ""

    # Nur für "db": Wie lange die Bilddaten eines Fotosatzes nach der Abholung
    # noch in der Datenbank bleiben. Die Schonfrist gibt es, damit die Galerie
    # in der App direkt nach dem Termin noch Vorschaubilder zeigt. Danach ist
    # der Projektordner das Archiv; der Datensatz bleibt mit Namen, Größe und
    # Zielordner erhalten.
    fotos_aufbewahren_tage: int = 2
    # Obergrenze für die Bilddaten in der Datenbank. Wird sie überschritten,
    # werden zusätzlich die ältesten bereits abgeholten Sätze geleert. Noch
    # nicht abgeholte Sätze bleiben unter allen Umständen liegen.
    fotos_max_mb: int = 300

    # ── Objektspeicher, falls die Fotomenge einmal wächst (optional) ──
    #
    # S3-kompatibel: Cloudflare R2, Backblaze B2, MinIO im eigenen Haus. Nicht
    # nötig für den Normalbetrieb — die Datenbank reicht, weil Fotos nur bis
    # zur Abholung dort liegen.
    r2_endpoint: str = ""      # z. B. https://<konto-id>.r2.cloudflarestorage.com
    r2_bucket: str = ""        # Name des Buckets, z. B. baustellenfotos
    r2_key_id: str = ""        # Access Key ID
    r2_secret: str = ""        # Secret Access Key

    # ── Passwortschutz der Weboberfläche ──
    #
    # Ohne dieses Wort ist die App im Internet für jeden erreichbar, der den
    # Render-Link kennt — auch zum Hochladen von Baufotos. Ist hier ein Wort
    # gesetzt, verlangt die Oberfläche vor dem ersten Anzeigen eine Anmeldung
    # und jeder API-Aufruf den Kopf ``X-Seiten-Passwort`` mit genau diesem
    # Wert (siehe app.security). WIRD NUR BEI RENDER GESETZT — bleibt lokal
    # und im Windows-Paket leer, dort ist die App weiterhin offen wie
    # bisher, weil dort ohnehin niemand von außen zugreifen kann.
    seiten_passwort: str = ""

    # ── Abholung durch die Bürorechner ──
    #
    # Die Abholskripte auf den Büro-PCs fragen den Server, welche Fotosätze
    # noch nicht im Netzlaufwerk liegen. Ist hier ein Wort gesetzt, muss es im
    # Kopf ``X-Abhol-Token`` mitgeschickt werden — sonst antwortet der Server
    # mit 401. Leer = offen wie der Rest der App.
    #
    # Wirkt unabhängig vom Seiten-Passwort oben: Die Abholskripte kennen keine
    # Anmeldung, deshalb sind die Abholrouten davon ausgenommen (siehe
    # app.security).
    abhol_token: str = ""

    # Wie lange ein angefangener Abholvorgang gilt. Bricht ein Büro-PC mitten
    # im Entpacken ab (Neustart, Netzlaufwerk weg), taucht der Satz danach
    # wieder in der Liste auf, damit ihn ein anderer Rechner holen kann.
    abhol_anspruch_minuten: int = 30

    # Ruhezeit nach dem letzten Foto, bevor ein Satz abgeholt werden darf.
    # Ohne sie würde das Skript einen Satz mitnehmen, während auf der
    # Baustelle noch Fotos hochgeladen werden — die späteren fehlten dann.
    abhol_wartezeit_minuten: int = 3

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
    # "https://bautagesbericht.onrender.com". Wird bei Render automatisch
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
