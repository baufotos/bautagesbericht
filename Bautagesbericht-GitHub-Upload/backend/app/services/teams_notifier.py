"""Benachrichtigung per Microsoft-Teams-Kanal-Webhook.

Alternative zum E-Mail-Versand: Viele kostenlose Hosting-Plattformen (auch
Render) sperren ausgehende SMTP-Verbindungen, siehe app.services.email_sender.
Ein Teams-Kanal-Webhook ist dagegen ein ganz normaler HTTPS-POST an eine von
Teams generierte URL — kein SMTP-Port, kein bezahlter Hosting-Plan und kein
klassischer API-Key nötig.

Ein Webhook postet immer in einen Kanal, nie in einen echten 1:1-Chat. Damit
sich das für die einzelne Person trotzdem wie ein persönlicher Kanal anfühlt,
legt man pro Empfänger einen eigenen kleinen Teams-Kanal an (nur diese Person
als Mitglied) und hinterlegt dessen Webhook-URL direkt am Empfänger (Feld
``teams_webhook_url`` in der Stammdaten-Verwaltung). Alternativ kann
BTB_TEAMS_WEBHOOK_URL als gemeinsamer Kanal für alle Empfänger ohne eigene
Webhook-URL dienen.

Einrichtung in Teams (einmalig, pro Kanal):
  1. Im gewünschten Kanal auf die drei Punkte ("...") klicken -> "Workflows".
  2. Vorlage "Send webhook alerts to a channel" auswählen, Team/Kanal
     bestätigen, speichern.
  3. "Copy webhook link" klicken und die URL kopieren.
  4. Diese URL beim jeweiligen Empfänger eintragen (oder als
     BTB_TEAMS_WEBHOOK_URL bei Render, für einen gemeinsamen Kanal).

Ist gar keine Webhook-URL vorhanden (weder am Empfänger noch als globaler
Fallback), tut ``send_teams_notification`` nichts — der Aufrufer in
pipeline.py wandelt einen Fehlschlag in eine Warnung um, der Download bleibt
in jedem Fall möglich.
"""

from __future__ import annotations

from datetime import date

import httpx

from app.config import settings


def _build_download_url(einreichung_id: int) -> str:
    base = (settings.public_base_url or "").rstrip("/")
    return f"{base}/api/einreichungen/{einreichung_id}/dokument"


async def send_teams_notification(
    einreichung_id: int,
    projekt_name: str,
    datum: date,
    webhook_url: str = "",
) -> None:
    """Postet eine Nachricht mit Download-Link in einen Teams-Kanal.

    ``webhook_url`` ist normalerweise die persönliche Kanal-Webhook-URL des
    Empfängers; ist sie leer, wird ersatzweise BTB_TEAMS_WEBHOOK_URL genutzt.
    Sind beide leer, passiert nichts.

    Wirft eine Exception, wenn eine Webhook-URL vorhanden ist, der Versand
    aber fehlschlägt (z. B. falsche/abgelaufene URL). Der Aufrufer fängt das
    ab und protokolliert eine Warnung statt den Bericht als fehlgeschlagen zu
    markieren.
    """
    url = webhook_url or settings.teams_webhook_url
    if not url:
        return

    download_url = _build_download_url(einreichung_id)
    datum_str = datum.strftime("%d.%m.%Y")
    text = (
        f"Neuer Bautagesbericht **{projekt_name}** vom {datum_str} ist fertig.\n\n"
        f"[Bericht herunterladen]({download_url})"
    )
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"Bautagesbericht {projekt_name}",
        "themeColor": "0076D7",
        "title": f"Bautagesbericht {projekt_name} — {datum_str}",
        "text": text,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
