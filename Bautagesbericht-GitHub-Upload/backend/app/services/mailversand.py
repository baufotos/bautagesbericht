"""Der Postweg selbst, unabhängig davon, was verschickt wird.

WOZU DIESES MODUL
=================
Zwei Module verschicken inzwischen Mails mit Anhang: die Baufotos als ZIP
(``fotoversand``) und das McDonald's-Angebot als Word-Dokument
(``mcdonalds_versand``). Was sie unterscheidet, ist der Inhalt — Betreff, Text
und Anhang. Was sie teilen, ist der Weg dorthin, und das sind genau die drei
Fragen, die nichts mit Fotos oder Angeboten zu tun haben:

1. **Gibt es überhaupt einen Postausgangsserver?** (``smtp_bereit``)
   Auf dem kostenlosen Render-Plan ist ausgehendes SMTP gesperrt, im Büronetz
   gibt es das hausinterne Relay. Beide Fälle kommen vor, und die Oberfläche
   muss vorher wissen, welche Knöpfe sie anbieten darf.
2. **Unter welcher Adresse verschickt der Server?** (``absender_adresse``)
3. **Verschicken.** (``sende_per_smtp``)

Dazu der Kopf, an dem Outlook einen Entwurf erkennt (``ENTWURF_KOPF``). Der
Entwurfsweg ist der, der *immer* funktioniert: Die ``.eml``-Datei enthält
Empfänger, Betreff, Text und Anhang, und ``X-Unsent: 1`` sorgt dafür, dass
Outlook sie nicht als empfangene Mail anzeigt, sondern als fertigen Entwurf
mit Senden-Knopf. Absender bleibt dabei leer, damit Outlook das Konto des
Kollegen nimmt.

``fotoversand`` gibt diese Funktionen weiterhin unter seinem eigenen Namen
heraus — Aufrufer und Tests, die dort danach greifen, funktionieren
unverändert weiter.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings

#: Der Kopf, an dem Outlook eine noch nicht gesendete Nachricht erkennt.
ENTWURF_KOPF = "X-Unsent"


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


def als_entwurf_kennzeichnen(nachricht: EmailMessage) -> None:
    """Macht aus der Nachricht einen Outlook-Entwurf.

    Kein Datum und kein Absender: Beides würde Outlook dazu bringen, die Datei
    als empfangene Nachricht anzuzeigen — dann fehlt der Senden-Knopf, und der
    Kollege müsste alles noch einmal von Hand zusammenstellen.
    """
    nachricht[ENTWURF_KOPF] = "1"


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
