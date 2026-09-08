"""Das fertige Angebot an den Fachplaner schicken.

DERSELBE WEG WIE BEI DEN BAUFOTOS
=================================
Zwei Möglichkeiten, aus demselben Grund wie in ``fotoversand``:

1. **Entwurf (.eml)** — funktioniert immer, ohne jede Serverkonfiguration.
   Outlook öffnet die Datei als fertigen Entwurf mit Senden-Knopf; der
   Kollege liest gegen und schickt selbst ab. Das ist hier der Regelweg:
   Ein Angebot ist ein Schreiben nach außen, und es soll gelesen werden,
   bevor es hinausgeht.
2. **Direkt senden** — nur mit hinterlegtem Postausgangsserver
   (``BTB_SMTP_HOST``).

Der Postweg selbst steckt in ``app.services.mailversand`` und ist mit den
Baufotos geteilt. Was dieses Modul beisteuert, ist der Inhalt: Empfänger aus
den Fachplaner-Stammdaten, Betreff, Text und das Word-Dokument als Anhang.
"""

from __future__ import annotations

from datetime import date
from email.message import EmailMessage

from app.models import McdonaldsAngebot
from app.services import mailversand
# Weitergegeben, damit der Router alles über dieses Modul erreicht
# (``versand.smtp_bereit()``, ``versand.sende_per_smtp(...)``) — genau wie
# beim Fotoversand. Hier im Modul selbst werden sie nicht aufgerufen.
from app.services.mailversand import (  # noqa: F401
    absender_adresse,
    sende_per_smtp,
    smtp_bereit,
)

#: MIME-Typ eines .docx — sonst kommt es als "application/octet-stream" an
#: und manche Postfächer zeigen es als unbekannte Datei.
DOCX_TYP = (
    "application",
    "vnd.openxmlformats-officedocument.wordprocessingml.document",
)


def _standort(angebot: McdonaldsAngebot) -> str:
    fall = angebot.fall
    if not fall:
        return "Standort"
    return fall.standort_name or fall.ordner_name or fall.standort_ort or "Standort"


def _phase(angebot: McdonaldsAngebot) -> str:
    return f"LPH {angebot.leistungsphase}" if angebot.leistungsphase else ""


# ─────────────────────────────────────────────────────────────────────────────
# Betreff und Text
#
# TODO McDonald's: Die Textbausteine des Büros werden nachgereicht — je
# Leistungsphase unterschiedlich (siehe Konzeptblatt: "Versandt Beauftragung
# Fachplaner (unterschiedlich je nach Phase)"). Die beiden Funktionen hier
# sind der Platz dafür: Wer sie ersetzt, muss die Versandlogik nicht anfassen.
# Für phasenabhängige Texte genügt eine Zuordnung {Phase: Textbaustein} und
# ein Zugriff darauf in ``standardtext_fuer`` — Vorbild ist
# ``app.services.anzeige_bausteine``.
# ─────────────────────────────────────────────────────────────────────────────


def betreff_fuer(angebot: McdonaldsAngebot) -> str:
    """Betreffzeile des Entwurfs. Im Dialog überschreibbar."""
    if (angebot.betreff or "").strip():
        return angebot.betreff.strip()
    phase = _phase(angebot)
    return f"Beauftragung {_standort(angebot)}" + (f" — {phase}" if phase else "")


def standardtext_fuer(angebot: McdonaldsAngebot) -> str:
    """Vorgeschlagener Mailtext. Der Absender kann ihn im Dialog überschreiben."""
    fall = angebot.fall
    planer = angebot.fachplaner
    anrede = "Guten Tag"
    if planer and (planer.ansprechpartner or "").strip():
        anrede = f"Guten Tag {planer.ansprechpartner.strip()}"

    zeilen = [
        f"{anrede},",
        "",
        "im Anhang das Angebot zur Beauftragung.",
        "",
        f"Standort:        {_standort(angebot)}",
    ]
    if fall and (fall.standort_adresse or "").strip():
        zeilen.append(f"Anschrift:       {fall.standort_adresse.strip()}")
    if _phase(angebot):
        zeilen.append(f"Leistungsphase:  {_phase(angebot)}")
    if fall and (fall.auftraggeber or "").strip():
        zeilen.append(f"Auftraggeber:    {fall.auftraggeber.strip()}")

    anzahl = len([
        e for e in (angebot.mehrleistungen or [])
        if isinstance(e, dict) and str(e.get("bezeichnung") or "").strip()
    ])
    if anzahl:
        zeilen += ["", f"Enthalten sind {anzahl} Mehrleistung(en) — siehe Angebot."]

    zeilen += ["", "Mit freundlichen Grüßen"]
    return "\n".join(zeilen)


# ─────────────────────────────────────────────────────────────────────────────
# Die Nachricht
# ─────────────────────────────────────────────────────────────────────────────


def baue_nachricht(
    angebot: McdonaldsAngebot,
    *,
    empfaenger: list[str],
    kopie: list[str],
    betreff: str,
    text: str,
    dokument: bytes,
    dokument_name: str,
    absender: str = "",
    als_entwurf: bool = False,
) -> EmailMessage:
    """Baut die vollständige Mail samt Angebot als Anhang.

    ``als_entwurf`` lässt Datum und Absender weg und setzt ``X-Unsent: 1``
    (siehe ``mailversand``) — damit öffnet Outlook die Datei als bearbeitbaren
    Entwurf statt als empfangene Nachricht.
    """
    nachricht = EmailMessage()
    nachricht["To"] = ", ".join(empfaenger)
    if kopie:
        nachricht["Cc"] = ", ".join(kopie)
    nachricht["Subject"] = betreff
    nachricht.set_content(text.rstrip() + "\n")

    nachricht.add_attachment(
        dokument,
        maintype=DOCX_TYP[0],
        subtype=DOCX_TYP[1],
        filename=dokument_name,
    )

    if als_entwurf:
        mailversand.als_entwurf_kennzeichnen(nachricht)
    elif absender:
        nachricht["From"] = absender

    return nachricht


def notiere_versand(angebot: McdonaldsAngebot, weg: str) -> None:
    """Hält am Angebot fest, wann und wie es herausging.

    Der Aufrufer committet. ``weg="entwurf"`` heißt: Die App hat den Entwurf
    gebaut, abgeschickt hat ihn Outlook — dieselbe Unterscheidung wie beim
    Fotoversand, und die Oberfläche zeigt sie auch so an.
    """
    angebot.mail_versendet_am = date.today()
    angebot.mail_weg = weg
