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


# ─────────────────────────────────────────────────────────────────────────────
# Mängelmanagement
#
# Gleicher Weg wie beim Bautagesbericht, nur ein anderer Anlass: ein neu
# erfasster Mangel oder eine Änderung an Status/Frist. Die Webhook-URL sucht
# app.services.mangel_versand in dieser Reihenfolge: Gewerk -> Projekt ->
# globaler BTB_TEAMS_WEBHOOK_URL. Ist keine gesetzt, passiert nichts.
# ─────────────────────────────────────────────────────────────────────────────

# Farbe der Teams-Karte je Anlass (Kopfleiste der MessageCard).
MANGEL_FARBEN = {
    "neu": "B45309",
    "status": "1F3A5C",
    "frist": "B91C1C",
    "versand": "1F3A5C",
}


def _build_mangel_url(mangel_id: int) -> str:
    """Direktlink in die App auf genau diesen Mangel.

    Die Oberfläche liest ``?tab=maengel&mangel=<id>`` beim Laden aus und
    öffnet die Detailansicht — aus Teams heraus ist man damit einen Klick vom
    Mangel entfernt.
    """
    base = (settings.public_base_url or "").rstrip("/")
    return f"{base}/?tab=maengel&mangel={mangel_id}"


async def send_mangel_notification(
    mangel_id: int,
    nummer: str,
    kurzbezeichnung: str,
    projekt_name: str,
    firma: str = "",
    status: str = "",
    frist: date | None = None,
    anlass: str = "neu",
    zusatz: str = "",
    webhook_url: str = "",
) -> bool:
    """Postet einen Mangel in einen Teams-Kanal.

    ``anlass`` ist einer von "neu", "status", "frist", "versand" und bestimmt
    Überschrift und Farbe der Karte.

    Gibt ``True`` zurück, wenn wirklich gepostet wurde, und ``False``, wenn
    überhaupt kein Kanal hinterlegt ist. Diese Unterscheidung ist wichtig:
    "nichts zu tun" darf in der Oberfläche nicht als "versendet" erscheinen.
    Wirft eine Exception, wenn eine Webhook-URL vorhanden ist, der Versand
    aber fehlschlägt — der Aufrufer behandelt das als Warnung, statt den
    Vorgang scheitern zu lassen.
    """
    url = webhook_url or settings.teams_webhook_url
    if not url:
        return False

    ueberschriften = {
        "neu": "Neuer Mangel",
        "status": "Mangel — Status geändert",
        "frist": "Mangel — Frist geändert",
        "versand": "Mängelrüge versendet",
    }
    titel = f"{ueberschriften.get(anlass, 'Mangel')}: {nummer} {kurzbezeichnung}"

    zeilen = [f"**{projekt_name}**"]
    if firma:
        zeilen.append(f"Firma: {firma}")
    if status:
        zeilen.append(f"Status: {status}")
    if frist:
        zeilen.append(f"Frist: {frist.strftime('%d.%m.%Y')}")
    if zusatz:
        zeilen.append(zusatz)
    zeilen.append(f"[Mangel in der App öffnen]({_build_mangel_url(mangel_id)})")

    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": titel,
        "themeColor": MANGEL_FARBEN.get(anlass, "1F3A5C"),
        "title": titel,
        "text": "\n\n".join(zeilen),
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Baufotos
#
# Ein Fotosatz geht an das eigene Team, nicht an einen Nachunternehmer —
# deshalb nur der Projektkanal bzw. der globale Fallback (die Auswahl trifft
# app.services.baufotos.webhook_fuer). Die Nachricht enthält den Link auf die
# ZIP-Datei: Genau die hat man bisher per Outlook bekommen.
# ─────────────────────────────────────────────────────────────────────────────


def _build_zip_url(fotosatz_id: int) -> str:
    base = (settings.public_base_url or "").rstrip("/")
    return f"{base}/api/fotosaetze/{fotosatz_id}/zip"


async def send_fotosatz_notification(
    fotosatz_id: int,
    projekt_name: str,
    kategorie: str,
    datum: date,
    anzahl: int,
    zip_name: str,
    webhook_url: str = "",
) -> bool:
    """Postet einen fertigen Fotosatz in einen Teams-Kanal.

    Gibt ``True`` nur zurück, wenn wirklich gepostet wurde, und ``False``, wenn
    kein Kanal hinterlegt ist. Wirft eine Exception, wenn ein Kanal vorhanden
    ist, der Versand aber scheitert — der Aufrufer macht daraus eine Meldung
    für die Oberfläche, statt den Fotosatz als fehlerhaft zu behandeln.
    """
    url = webhook_url or settings.teams_webhook_url
    if not url:
        return False

    datum_str = datum.strftime("%d.%m.%Y")
    titel = f"Baufotos {projekt_name} — {kategorie} ({datum_str})"
    text = "\n\n".join([
        f"**{projekt_name}**",
        f"Kategorie: {kategorie}",
        f"{anzahl} Foto(s), umbenannt und verkleinert",
        f"[{zip_name} herunterladen]({_build_zip_url(fotosatz_id)})",
    ])

    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": titel,
        "themeColor": "2563EB",
        "title": titel,
        "text": text,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
    return True
