"""E-Mail-Versand des fertigen Bautagesberichts per SMTP.

Ersetzt den ursprünglichen Outlook-COM-Versand, der nur unter Windows mit
lokal installiertem Outlook funktioniert hat. Diese Fassung läuft auf jedem
Server (Linux/Docker) und braucht nur SMTP-Zugangsdaten in den
Umgebungsvariablen (siehe ``app.config.Settings``).

Solange ``BTB_SMTP_HOST`` nicht gesetzt ist, wirft ``send_bautagesbericht``
einen ``RuntimeError`` — der Aufrufer in ``pipeline.py`` verpackt das in
eine Warnung, sodass der Nutzer die Datei weiterhin herunterladen kann.
"""

from __future__ import annotations

import smtplib
import ssl
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from app.config import settings


BODY_TEMPLATE = """Guten Tag,

anbei der aufbereitete HPP-Bautagesbericht für das Projekt „{projekt}" vom {datum}.

Diese Nachricht wurde automatisch erzeugt.

Mit freundlichen Grüßen
HPP Architekten Baumanagement
"""


def _build_message(
    empfaenger_email: str,
    projekt_name: str,
    datum: date,
    anhang_pfad: Path,
    cc_email: str | None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"Bautagesbericht {projekt_name} — {datum.strftime('%d.%m.%Y')}"
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = empfaenger_email
    if cc_email:
        msg["Cc"] = cc_email
    msg.set_content(BODY_TEMPLATE.format(projekt=projekt_name, datum=datum.strftime("%d.%m.%Y")))

    data = anhang_pfad.read_bytes()
    msg.add_attachment(
        data,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=anhang_pfad.name,
    )
    return msg


def send_bautagesbericht(
    empfaenger_email: str,
    projekt_name: str,
    datum: date,
    anhang_pfad: Path,
    cc_email: str | None = None,
) -> None:
    """Sendet den fertigen Bericht als E-Mail mit Word-Anhang per SMTP.

    Wirft ``RuntimeError``, wenn SMTP nicht konfiguriert ist oder der Versand
    fehlschlägt — der Aufrufer wandelt das in eine Warnung um.
    """
    if not settings.smtp_host:
        raise RuntimeError(
            "SMTP nicht konfiguriert — bitte BTB_SMTP_HOST, BTB_SMTP_USER, "
            "BTB_SMTP_PASSWORD und BTB_SMTP_FROM setzen."
        )
    if not anhang_pfad.exists():
        raise RuntimeError(f"Anhang nicht gefunden: {anhang_pfad}")

    msg = _build_message(empfaenger_email, projekt_name, datum, anhang_pfad, cc_email)

    try:
        if settings.smtp_port == 465:
            # Impliziter TLS (SMTPS)
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=30) as server:
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
        else:
            # STARTTLS (Standard, Port 587) oder unverschlüsselt
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                server.ehlo()
                if settings.smtp_use_tls:
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
    except Exception as exc:
        raise RuntimeError(f"E-Mail-Versand fehlgeschlagen: {exc}") from exc
