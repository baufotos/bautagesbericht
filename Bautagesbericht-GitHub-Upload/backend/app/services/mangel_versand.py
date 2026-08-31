"""Versand und Versand-Validierung einer Mängelrüge.

**Zustellweg.** Die App benachrichtigt über Microsoft-Teams-Kanal-Webhooks,
nicht über SMTP — dieselbe Entscheidung wie beim Bautagesbericht, weil der
kostenlose Hosting-Plan keine ausgehenden SMTP-Verbindungen erlaubt (siehe
Modul-Kommentar in app.services.teams_notifier). Die E-Mail-Adresse am Gewerk
ist deshalb heute die *Voraussetzung* für den Versand und wird geprüft, aber
noch nicht selbst angeschrieben.

Sobald ein Mailweg zur Verfügung steht (eigener SMTP-Server oder ein
API-Dienst wie Postmark/Brevo), ist ``_verschicke_ueber_mail`` die einzige
Stelle, die dafür ausgefüllt werden muss — Validierung, Statuspflege und
Oberfläche bleiben unverändert.

**Kanal-Reihenfolge** für die Teams-Nachricht: eigener Kanal des Gewerks →
Kanal des Projekts → globaler ``BTB_TEAMS_WEBHOOK_URL``.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import Mangel
from app.services.mangel_logik import aktuelle_frist, gewerk_anzeige
from app.services.teams_notifier import send_mangel_notification

# Wortgleich zur Meldung in der bisherigen Bürosoftware, damit die Kollegen
# den Hinweis wiedererkennen.
MAIL_FEHLER_KEINE_ADRESSE = "Fehler! Firma/Büro hat keine Email-Adresse"
MAIL_FEHLER_KEINE_FIRMA = "Fehler! Kein zuständiges Gewerk / keine Firma gewählt"


def mail_fehler(mangel: Mangel) -> str | None:
    """Warum ein Versand an die Firma (noch) nicht möglich ist — oder ``None``.

    Wird unabhängig von ``mail_autosend`` berechnet und in der Detailansicht
    rot angezeigt: Auch bei manuellem Versand nützt die schönste Mängelrüge
    nichts, wenn am Gewerk keine Adresse hinterlegt ist.
    """
    if mangel.gewerk_id is None or mangel.gewerk is None:
        return MAIL_FEHLER_KEINE_FIRMA
    if not (mangel.gewerk.email or "").strip():
        return MAIL_FEHLER_KEINE_ADRESSE
    return None


def erzwinge_manuellen_versand(mangel: Mangel) -> str | None:
    """Blockiert Autosend, wenn die Firma nicht angeschrieben werden kann.

    Fällt in diesem Fall auf ``mail_versendemodus = "manuell"`` zurück und gibt
    den Fehlertext zurück, damit der Aufrufer ihn in die Antwort legen kann.
    Wird bei jedem Anlegen und Ändern eines Mangels aufgerufen — so kann kein
    Mangel mit aktivem Autosend und fehlender Adresse in der Datenbank
    stehen.
    """
    fehler = mail_fehler(mangel)
    if fehler is None:
        return None
    mangel.mail_autosend = False
    mangel.mail_versendemodus = "manuell"
    return fehler


def webhook_fuer(mangel: Mangel) -> str:
    """Teams-Webhook des Gewerks, sonst des Projekts, sonst leer (= global)."""
    if mangel.gewerk is not None and (mangel.gewerk.teams_webhook_url or "").strip():
        return mangel.gewerk.teams_webhook_url.strip()
    if mangel.projekt is not None and (mangel.projekt.teams_webhook_url or "").strip():
        return mangel.projekt.teams_webhook_url.strip()
    return ""


async def benachrichtige_teams(mangel: Mangel, anlass: str,
                               zusatz: str = "") -> bool:
    """Postet eine Teams-Nachricht zu diesem Mangel. Fehler werden geschluckt.

    Gibt ``True`` nur zurück, wenn tatsächlich gepostet wurde — ist kein Kanal
    hinterlegt oder scheitert der Versand, ist es ``False``. Eine
    fehlgeschlagene Benachrichtigung darf das Erfassen oder Ändern eines
    Mangels nicht scheitern lassen: Die Daten sind gespeichert, und in der
    Mängel-Übersicht sieht ohnehin jeder selbst nach.
    """
    try:
        return await send_mangel_notification(
            mangel_id=mangel.id,
            nummer=mangel.nummer,
            kurzbezeichnung=mangel.kurzbezeichnung,
            projekt_name=mangel.projekt.name if mangel.projekt else "",
            firma=gewerk_anzeige(mangel.gewerk),
            status=mangel.status,
            frist=aktuelle_frist(mangel),
            anlass=anlass,
            zusatz=zusatz,
            webhook_url=webhook_fuer(mangel),
        )
    except Exception:
        return False


async def _verschicke_ueber_mail(mangel: Mangel) -> bool:
    """Platzhalter für den echten E-Mail-Versand an die Firma.

    Bewusst noch nicht implementiert: Auf dem kostenlosen Render-Plan ist
    ausgehendes SMTP gesperrt. Kommt später ein Mailweg dazu, wird genau hier
    verschickt (Empfänger: ``mangel.gewerk.email``, Inhalt: die Mängelrüge aus
    app.services.maengelliste_generation) — der Rest der Kette bleibt
    unverändert.
    """
    return False


async def sende_mangelruege(db: Session, mangel: Mangel) -> tuple[bool, str, str]:
    """"Jetzt senden": prüft, verschickt und schreibt das Versanddatum.

    Gibt ``(versendet, kanal, nachricht)`` zurück. ``kanal`` ist "mail",
    "teams" oder "keiner".
    """
    fehler = mail_fehler(mangel)
    if fehler:
        return False, "keiner", fehler

    if await _verschicke_ueber_mail(mangel):
        mangel.zuletzt_versendet_am = date.today()
        db.commit()
        return True, "mail", f"Mängelrüge an {mangel.gewerk.email} versendet."

    zusatz = f"Mängelrüge an {mangel.gewerk.email}"
    if await benachrichtige_teams(mangel, anlass="versand", zusatz=zusatz):
        mangel.zuletzt_versendet_am = date.today()
        db.commit()
        return True, "teams", (
            "Als Teams-Nachricht mit Link zum Mangel gemeldet. Der direkte "
            "E-Mail-Versand an die Firma ist noch nicht freigeschaltet."
        )

    return False, "keiner", (
        "Kein Zustellweg verfügbar: Es ist kein Teams-Kanal hinterlegt "
        "(Gewerk, Projekt oder BTB_TEAMS_WEBHOOK_URL) und der E-Mail-Versand "
        "ist noch nicht freigeschaltet. Die Mängelliste lässt sich weiterhin "
        "als Word-Dokument exportieren."
    )
