"""Den Einzelabruf an den Subplaner verschicken.

DERSELBE WEG WIE BEI DEN BAUFOTOS
=================================
Zwei Möglichkeiten, aus demselben Grund wie in ``fotoversand``:

1. **Entwurf (.eml)** — funktioniert immer, ohne jede Serverkonfiguration.
   Outlook öffnet die Datei als fertigen Entwurf mit Senden-Knopf; der
   Kollege liest gegen und schickt selbst ab. Das ist hier der Regelweg, und
   zwar mit Absicht: Ein Einzelabruf ist ein Vertragsdokument. Er soll von
   einem Menschen gelesen werden, bevor er hinausgeht — erst recht, wenn die
   Termine darin aus einer Regel stammen.
2. **Direkt senden** — nur mit hinterlegtem Postausgangsserver
   (``BTB_SMTP_HOST``). Auf dem kostenlosen Render-Plan ohnehin gesperrt.

OHNE ANHANG
===========
Anders als beim Fotoversand hängt hier nichts dran: Der Einzelabruf *ist* der
Mailtext (siehe ``mcdonalds_beauftragung``). Ein zusätzliches Word-Dokument
mit demselben Wortlaut wäre eine zweite Fassung desselben Vertrags — und
irgendwann weichen zwei Fassungen voneinander ab.

Die ``.eml`` selbst wird zusätzlich im Vertragsordner des Subplaners abgelegt
(``mcdonalds_ordner.lege_datei_ab``). Damit liegt die Beauftragung im
Projektordner, obwohl sie über Outlook rausgeht.

Der Postweg steckt in ``app.services.mailversand`` und ist mit den Baufotos
geteilt.
"""

from __future__ import annotations

from datetime import date
from email.message import EmailMessage

from app.models import McdonaldsBeauftragung
from app.services import mailversand
# Weitergegeben, damit der Router alles über dieses Modul erreicht
# (``versand.smtp_bereit()``, ``versand.sende_per_smtp(...)``) — genau wie
# beim Fotoversand. Hier im Modul selbst werden sie nicht aufgerufen.
from app.services.mailversand import (  # noqa: F401
    absender_adresse,
    sende_per_smtp,
    smtp_bereit,
)


def baue_nachricht(
    *,
    empfaenger: list[str],
    kopie: list[str],
    betreff: str,
    text: str,
    absender: str = "",
    als_entwurf: bool = True,
) -> EmailMessage:
    """Baut den Einzelabruf als Mail.

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

    if als_entwurf:
        mailversand.als_entwurf_kennzeichnen(nachricht)
    elif absender:
        nachricht["From"] = absender

    return nachricht


def notiere_versand(
    beauftragung: McdonaldsBeauftragung, empfaenger: list[str], weg: str
) -> None:
    """Hält an der Beauftragung fest, wann, an wen und wie sie herausging.

    Der Aufrufer committet. ``weg="entwurf"`` heißt: Die App hat den Entwurf
    gebaut, abgeschickt hat ihn Outlook — dieselbe Unterscheidung wie beim
    Fotoversand, und die Oberfläche zeigt sie auch so an.
    """
    beauftragung.mail_versendet_am = date.today()
    beauftragung.empfaenger = empfaenger
    beauftragung.mail_weg = weg
