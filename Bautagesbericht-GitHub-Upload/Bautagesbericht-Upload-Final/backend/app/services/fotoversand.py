"""Baufotos per E-Mail verschicken — als Anhang, nicht als Link.

WARUM ANHANG UND NICHT LINK
===========================
Der Teams-Weg (``melde_fotosatz``) verschickt einen Download-Link. Der ist
kurz, setzt aber voraus, dass der Empfänger die App erreicht. Genau das gilt
für Bauherrn, Prüfstatiker oder Sachverständige nicht — die haben bisher eine
Outlook-Mail mit dem ZIP im Anhang bekommen, und genau das kann dieses Modul.

ZWEI WEGE, WEIL DAS BÜRO GEMISCHT ARBEITET
==========================================
1. **Direkt senden** — nur wenn ein Postausgangsserver hinterlegt ist
   (``BTB_SMTP_HOST``). Dann geht die Mail wirklich vom Server los, mit ZIP im
   Anhang. Auf dem kostenlosen Render-Plan ist ausgehendes SMTP gesperrt
   (siehe ``app.services.teams_notifier``); im Windows-Paket im Büronetz
   funktioniert es dagegen mit dem hausinternen Relay.
2. **Entwurf (.eml)** — funktioniert *immer*, ohne jede Serverkonfiguration.
   Die Datei enthält Empfänger, Betreff, Text und den ZIP-Anhang; der Kopf
   ``X-Unsent: 1`` sorgt dafür, dass Outlook sie nicht als empfangene Mail
   anzeigt, sondern als **fertigen Entwurf mit Senden-Knopf**. Absender bleibt
   leer, damit Outlook das Konto des Kollegen nimmt.

   Das gilt für das klassische Outlook. Wer das neue Outlook oder die
   Browserfassung nutzt, lädt die ZIP-Datei herunter und hängt sie selbst an —
   die Oberfläche sagt das dort auch.

GRÖSSE
======
Base64 macht aus einem Anhang rund ein Drittel mehr Bytes. Deshalb liegt die
Grenze beim ZIP und nicht bei der Mail: 15 MB ZIP werden zu etwa 20 MB Mail,
und 20 MB ist die Grenze, die die meisten Postfächer noch annehmen. Wer mehr
Fotos verschicken will, teilt den Fotosatz — das ist ehrlicher, als eine Mail
losschicken zu lassen, die beim Empfänger abprallt.
"""

from __future__ import annotations

import smtplib
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings
from app.models import Fotosatz
from app.services.baufotos import zip_dateiname

#: Grenze für das ZIP selbst. Base64 macht daraus etwa 20 MB Mail — die Grenze,
#: die Exchange und die meisten Provider noch durchlassen.
MAX_ANHANG_MB = 15

#: So viele Dateinamen kommen in den Mailtext. Darüber wird gezählt statt
#: aufgelistet — eine Mail mit 200 Zeilen Dateinamen liest niemand.
MAX_NAMEN_IM_TEXT = 40


def zu_gross(groesse_bytes: int) -> str | None:
    """Meldung, wenn das Archiv zu groß für eine Mail ist — sonst ``None``."""
    grenze = MAX_ANHANG_MB * 1024 * 1024
    if groesse_bytes <= grenze:
        return None
    return (
        f"Das Archiv ist {groesse_bytes / 1024 / 1024:.1f} MB groß. Per E-Mail "
        f"gehen höchstens {MAX_ANHANG_MB} MB (daraus werden beim Versand rund "
        f"{MAX_ANHANG_MB * 4 // 3} MB). Lade die ZIP-Datei herunter und lege sie "
        f"im Projektordner ab — oder teile die Fotos auf zwei Fotosätze auf."
    )


def betreff_fuer(fotosatz: Fotosatz) -> str:
    """Betreffzeile, wie sie im Büro üblich ist: Projekt, Kategorie, Datum."""
    projekt = fotosatz.projekt.name if fotosatz.projekt else "Projekt"
    return f"Baufotos {projekt} — {fotosatz.kategorie}, {fotosatz.datum:%d.%m.%Y}"


def standardtext(fotosatz: Fotosatz) -> str:
    """Vorgeschlagener Mailtext. Der Absender kann ihn im Dialog überschreiben."""
    projekt = fotosatz.projekt.name if fotosatz.projekt else "Projekt"
    fotos = sorted(fotosatz.fotos, key=lambda f: (f.reihenfolge, f.id))

    zeilen = [
        "Guten Tag,",
        "",
        f"im Anhang die Baufotos vom {fotosatz.datum:%d.%m.%Y}.",
        "",
        f"Projekt:    {projekt}",
        f"Kategorie:  {fotosatz.kategorie}",
        f"Aufnahmen:  {len(fotos)} Foto(s)",
    ]
    if (fotosatz.notiz or "").strip():
        zeilen += ["", f"Notiz: {fotosatz.notiz.strip()}"]

    if fotos:
        zeilen += ["", "Enthaltene Dateien:"]
        for foto in fotos[:MAX_NAMEN_IM_TEXT]:
            zeilen.append(f"  {foto.dateiname}")
        rest = len(fotos) - MAX_NAMEN_IM_TEXT
        if rest > 0:
            zeilen.append(f"  … und {rest} weitere")

    zeilen += ["", "Mit freundlichen Grüßen"]
    return "\n".join(zeilen)


def _zip_link(fotosatz_id: int) -> str:
    """Download-Link auf das Archiv — nur wenn die App öffentlich erreichbar ist.

    Im Windows-Paket läuft die App auf ``localhost``; ein solcher Link wäre für
    den Empfänger wertlos und bleibt deshalb weg.
    """
    basis = (settings.public_base_url or "").rstrip("/")
    if not basis:
        return ""
    return f"{basis}/api/fotosaetze/{fotosatz_id}/zip"


def baue_nachricht(
    fotosatz: Fotosatz,
    *,
    empfaenger: list[str],
    kopie: list[str],
    betreff: str,
    text: str,
    zip_bytes: bytes,
    zip_name: str,
    absender: str = "",
    als_entwurf: bool = False,
) -> EmailMessage:
    """Baut die vollständige Mail samt ZIP-Anhang.

    ``als_entwurf`` setzt ``X-Unsent: 1`` und lässt Datum und Absender weg —
    damit öffnet Outlook die Datei als bearbeitbaren Entwurf statt als
    empfangene Nachricht.
    """
    nachricht = EmailMessage()
    nachricht["To"] = ", ".join(empfaenger)
    if kopie:
        nachricht["Cc"] = ", ".join(kopie)
    nachricht["Subject"] = betreff

    inhalt = text.rstrip()
    link = _zip_link(fotosatz.id)
    if link:
        inhalt += f"\n\nDirekter Download (nur intern): {link}"
    nachricht.set_content(inhalt + "\n")

    nachricht.add_attachment(
        zip_bytes,
        maintype="application",
        subtype="zip",
        filename=zip_name,
    )

    if als_entwurf:
        # Der Kopf, an dem Outlook eine noch nicht gesendete Nachricht erkennt.
        nachricht["X-Unsent"] = "1"
    elif absender:
        nachricht["From"] = absender

    return nachricht


def smtp_bereit() -> bool:
    """Ist ein Postausgangsserver hinterlegt?"""
    return bool((settings.smtp_host or "").strip())


def absender_adresse() -> str:
    """Adresse, unter der der Server verschickt (leer, wenn nichts hinterlegt)."""
    adresse = (settings.smtp_absender or settings.smtp_user or "").strip()
    if not adresse:
        return ""
    name = (settings.smtp_absender_name or "").strip()
    return formataddr((name, adresse)) if name else adresse


def sende_per_smtp(nachricht: EmailMessage) -> None:
    """Verschickt die Nachricht. Wirft bei Fehlern — der Aufrufer meldet sie.

    Bewusst synchron: Der Vorgang dauert Sekunden, und der Kollege soll im
    Dialog erfahren, ob die Mail wirklich raus ist. Ein Versand im Hintergrund
    würde Erfolg melden, wo keiner ist.
    """
    host = settings.smtp_host.strip()
    port = settings.smtp_port
    absender = (settings.smtp_absender or settings.smtp_user or "").strip()

    empfaenger = []
    for feld in ("To", "Cc"):
        wert = nachricht.get(feld, "")
        empfaenger += [teil.strip() for teil in wert.split(",") if teil.strip()]

    if port == 465:
        verbindung = smtplib.SMTP_SSL(host, port, timeout=60)
    else:
        verbindung = smtplib.SMTP(host, port, timeout=60)

    with verbindung as server:
        if port != 465 and settings.smtp_tls:
            server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_passwort)
        server.send_message(nachricht, from_addr=absender or None,
                            to_addrs=empfaenger)


def notiere_versand(fotosatz: Fotosatz, empfaenger: list[str], weg: str) -> None:
    """Hält am Fotosatz fest, an wen und wie er verschickt wurde.

    Der Aufrufer committet. Für den Entwurf wird ``weg="entwurf"`` gesetzt —
    dann steht auf der Karte "Entwurf erstellt" und nicht "versendet", denn
    abgeschickt hat ihn dann Outlook, nicht die App.
    """
    fotosatz.mail_versendet_am = date.today()
    fotosatz.mail_empfaenger = ", ".join(empfaenger)
    fotosatz.mail_weg = weg
