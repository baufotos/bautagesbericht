"""Eine ``.eml``-Datei zerlegen — und als Notausgang vom Modell lesen lassen.

ZWEI AUFGABEN, KLAR GETRENNT
============================
1. ``lies_eml`` zerlegt die hochgeladene Datei: Kopfdaten, Klartext (aus dem
   HTML-Teil, wenn es keinen Klartext gibt) und die Namen der Anhänge. Reine
   Stdlib, kein Netz, keine Kosten — das funktioniert immer.
2. ``analysiere`` fragt das Sprachmodell. Das ist der **Notausgang**, nicht
   der Hauptweg.

DER HAUPTWEG IST ``mcdonalds_sls``
==================================
Die SLS-Anfrage von McDonald's ist maschinenerzeugt und immer gleich
aufgebaut; sie wird nach Regeln gelesen. Das ist schneller, kostenlos,
braucht keinen Schlüssel und ist zuverlässiger, weil ein regulärer Ausdruck
auf einer festen Zeile trifft oder gar nicht trifft — ein Modell hält
dagegen auch mal etwas anderes für plausibel.

Dieses Modul kommt zum Zug, wenn die Regeln nichts finden: McDonald's ändert
das Format, oder jemand lädt eine andere Auftragsmail hoch. Dann liest — falls
ein Anthropic-Schlüssel hinterlegt ist — das Modell dieselben Felder aus dem
Freitext. Findet auch das nichts, bleiben die Felder leer und werden von Hand
gefüllt; der hochgeladene Text ist gespeichert und geht nicht verloren.

WAS DIESES MODUL NICHT TUT
==========================
Es entscheidet nichts. Alles, was hier entsteht, ist ein Vorschlag und in der
Oberfläche änderbar, bevor daraus ein Ordnername oder ein Vertragstermin wird
— dieselbe Regel wie in ``besprechung_analyse``, aus demselben Grund: Ein
falsch gelesener Termin sieht in einem Einzelabruf genauso aus wie ein
richtiger.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from email import message_from_bytes, policy
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from app.config import settings
from app.services import schnittstelle

#: Dasselbe Modell wie in ``besprechung_analyse``. Steht bewusst hier und
#: nicht in der Konfiguration: Ein Modellwechsel ist eine Entscheidung, die
#: man je Anwendungsfall prüft.
CLAUDE_MODELL = "claude-opus-5"

#: Eine Auftragsmail ist kurz — die Antwort noch kürzer.
MAX_TOKENS = 2048

#: Ab hier wird der Mailtext gekürzt. Was darüber steht, ist bei einer
#: weitergeleiteten Mail der angehängte Verlauf früherer Nachrichten.
MAX_MAILTEXT = 60_000

#: Die Phasen des Kundenprozesses, gegen die geprüft wird.
from app.models import MCDONALDS_PHASEN  # noqa: E402


class AnalyseFehler(RuntimeError):
    """Die Analyse konnte nicht durchgeführt werden."""


@dataclass
class EmlInhalt:
    """Was in der hochgeladenen Datei steht — ohne jede Deutung."""

    betreff: str = ""
    absender: str = ""
    empfaenger: str = ""
    gesendet_am: datetime | None = None
    text: str = ""
    anhaenge: list[str] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)


@dataclass
class FallAngaben:
    """Die herausgelesenen Eckdaten — Feldnamen wie am Modell."""

    #: Ort des Standorts ("Nievern") — Grundlage des Ortscodes.
    ort: str = ""
    plz: str = ""
    strasse: str = ""
    #: 1-3, die Phase des McDonald's-Prozesses (NICHT die HOAI-Leistungsphase).
    phase: int | None = None
    #: Was beim Auswerten aufgefallen ist. Steht in der Oberfläche.
    hinweise: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Die Mail lesen (ohne Netz)
# ─────────────────────────────────────────────────────────────────────────────


class _HtmlZuText(HTMLParser):
    """Notfallweg, wenn eine Mail nur HTML enthält.

    Kein vollwertiger Umbau, sondern genau das, was für eine Auftragsmail
    zählt: Text behalten, Absätze und Zeilenumbrüche als solche erhalten,
    Stil- und Skriptblöcke wegwerfen.
    """

    _UMBRUCH = {"p", "br", "div", "tr", "li", "h1", "h2", "h3", "h4"}
    _STUMM = {"style", "script", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._teile: list[str] = []
        self._ueberspringen = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._STUMM:
            self._ueberspringen += 1
        elif tag in self._UMBRUCH:
            self._teile.append("\n")

    def handle_endtag(self, tag):
        if tag in self._STUMM and self._ueberspringen:
            self._ueberspringen -= 1
        elif tag in self._UMBRUCH:
            self._teile.append("\n")

    def handle_data(self, daten):
        if not self._ueberspringen:
            self._teile.append(daten)

    def text(self) -> str:
        roh = "".join(self._teile)
        # Höchstens eine Leerzeile — HTML-Mails erzeugen sonst Dutzende.
        return re.sub(r"\n{3,}", "\n\n", roh).strip()


def html_zu_text(html: str) -> str:
    """Klartext aus einem HTML-Mailteil."""
    umbau = _HtmlZuText()
    umbau.feed(html or "")
    umbau.close()
    return umbau.text()


def _teiltext(teil) -> str:
    """Der Text eines Mailteils, egal in welcher Kodierung er steckt."""
    try:
        inhalt = teil.get_content()
    except Exception:  # noqa: BLE001 — kaputte Kodierung, siehe unten
        # Eine Mail mit falsch deklarierter Kodierung darf den Upload nicht
        # verhindern: Roh dekodieren und ersetzen, was nicht passt.
        rohdaten = teil.get_payload(decode=True) or b""
        inhalt = rohdaten.decode("utf-8", errors="replace")
    return inhalt if isinstance(inhalt, str) else ""


def lies_eml(rohdaten: bytes, dateiname: str = "") -> EmlInhalt:
    """Zerlegt eine ``.eml``-Datei in Kopfdaten, Klartext und Anhangnamen.

    Reine Stdlib (``email``). Der Klartextteil wird bevorzugt; gibt es nur
    HTML, wird daraus Text gemacht. Anhänge werden nur benannt, nicht
    übernommen — sie gehören in den Projektordner, nicht in die Datenbank.
    """
    if not rohdaten:
        raise AnalyseFehler("Die hochgeladene Datei ist leer.")

    try:
        nachricht = message_from_bytes(rohdaten, policy=policy.default)
    except Exception as fehler:  # noqa: BLE001
        raise AnalyseFehler(
            f"Die Datei {dateiname or 'ohne Namen'} ließ sich nicht als "
            "E-Mail lesen. In Outlook bitte über „Datei → Speichern unter“ "
            "als „Outlook-Nachrichtenformat“ oder „.eml“ ablegen."
        ) from fehler

    inhalt = EmlInhalt(
        betreff=str(nachricht.get("Subject", "") or "").strip(),
        absender=str(nachricht.get("From", "") or "").strip(),
        empfaenger=str(nachricht.get("To", "") or "").strip(),
    )

    datum = nachricht.get("Date")
    if datum:
        try:
            inhalt.gesendet_am = parsedate_to_datetime(str(datum))
        except (TypeError, ValueError):
            inhalt.hinweise.append("Das Sendedatum der Mail war nicht lesbar.")

    klartext: list[str] = []
    html: list[str] = []

    for teil in nachricht.walk():
        if teil.get_content_maintype() == "multipart":
            continue
        name = teil.get_filename()
        if name or teil.get_content_disposition() == "attachment":
            inhalt.anhaenge.append(str(name or "ohne Namen"))
            continue
        art = teil.get_content_type()
        if art == "text/plain":
            klartext.append(_teiltext(teil))
        elif art == "text/html":
            html.append(_teiltext(teil))

    if klartext:
        inhalt.text = "\n".join(t for t in klartext if t.strip()).strip()
    elif html:
        inhalt.text = html_zu_text("\n".join(html))
        inhalt.hinweise.append(
            "Die Mail enthielt nur eine HTML-Fassung; der Text wurde daraus "
            "gewonnen. Bitte gegenlesen."
        )

    if not inhalt.text.strip():
        inhalt.hinweise.append(
            "In der Mail war kein Text zu finden — vielleicht steckt die "
            "Beauftragung in einem Anhang. Dann bitte die Angaben von Hand "
            "eintragen."
        )

    return inhalt


def prompttext(inhalt: EmlInhalt) -> tuple[str, list[str]]:
    """Baut den Text, den das Modell zu sehen bekommt."""
    hinweise: list[str] = []
    text = (inhalt.text or "").strip()
    if len(text) > MAX_MAILTEXT:
        text = text[:MAX_MAILTEXT]
        hinweise.append(
            f"Der Mailtext war länger als {MAX_MAILTEXT // 1000}.000 Zeichen "
            "und wurde für die Analyse gekürzt."
        )

    teile = [
        f"BETREFF: {inhalt.betreff or '(kein Betreff)'}",
        f"ABSENDER: {inhalt.absender or '(unbekannt)'}",
        f"EMPFÄNGER: {inhalt.empfaenger or '(unbekannt)'}",
    ]
    if inhalt.gesendet_am:
        teile.append(f"GESENDET: {inhalt.gesendet_am:%d.%m.%Y %H:%M}")
    if inhalt.anhaenge:
        teile.append("ANHÄNGE: " + ", ".join(inhalt.anhaenge))
    teile += ["", "MAILTEXT:", text or "(kein Text)"]
    return "\n".join(teile), hinweise


# ─────────────────────────────────────────────────────────────────────────────
# Der Auftrag an das Modell
#
# Gefragt wird nach genau den Feldern, die ``mcdonalds_sls`` aus dem Betreff
# liest — Phase, Postleitzahl, Ort, Straße. Nach den Terminen wird NICHT
# gefragt: Sie stehen in einem Vertragstext, und ein geratener Termin ist
# schlimmer als ein leeres Feld, das jemand füllen muss.
# ─────────────────────────────────────────────────────────────────────────────

ANWEISUNG = """Du liest eine Auftragsmail an ein Architekturbüro und trägst \
den Standort in ein Formular ein.

Zum Zusammenhang: Der Kunde ist McDonald's Deutschland. Die Mails kündigen \
einen neuen Restaurant-Standort an und bitten um die Vorbereitung einer von \
drei Projektphasen.

Regeln:

1. NICHTS RATEN. Was nicht in der Mail steht, bleibt leer. Ein leeres Feld \
wird im Büro nachgetragen; ein erfundenes fällt niemandem auf.
2. Der ORT ist der Ortsname allein, ohne Postleitzahl und ohne Stadtteil \
("Nievern", nicht "56132 Nievern, Auf d. Lay"). Er wird für die Suche in \
einer amtlichen Ortstabelle gebraucht, in der nur Ortsnamen stehen.
3. Die POSTLEITZAHL fünfstellig, nur wenn sie dasteht.
4. Die STRASSE mit Hausnummer, falls angegeben, ohne Ort.
5. Die PHASE ist 1, 2 oder 3 und nur zu setzen, wenn die Mail sie benennt — \
"F1", "Phase 1", "F2 Vorbereitung". Achtung: Das sind die Phasen des \
Kundenprozesses, NICHT die Leistungsphasen 1-9 der HOAI. Steht in der Mail \
eine Leistungsphase nach HOAI, gehört sie nicht in dieses Feld.
6. In HINWEISE gehört, was unklar blieb — besonders Widersprüche und \
Angaben, die dastehen, aber mehrdeutig sind."""

WERKZEUG = {
    "name": "standort_erfassen",
    "description": (
        "Trägt den Standort einer Auftragsmail in das Formular des Büros ein."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ort": {
                "type": "string",
                "description": (
                    "Nur der Ortsname, ohne Postleitzahl und Stadtteil."
                ),
            },
            "plz": {
                "type": "string",
                "description": "Fünfstellige Postleitzahl, sonst leer.",
            },
            "strasse": {
                "type": "string",
                "description": "Straße mit Hausnummer, sonst leer.",
            },
            "phase": {
                "type": ["integer", "null"],
                "description": (
                    "1, 2 oder 3 (Kundenprozess, nicht HOAI), oder null."
                ),
            },
            "hinweise": {
                "type": "array",
                "description": "Was beim Lesen unklar oder widersprüchlich war.",
                "items": {"type": "string"},
            },
        },
        "required": ["ort", "plz", "strasse", "phase"],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Die Anfrage
# ─────────────────────────────────────────────────────────────────────────────


def _client():
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _werkzeug_antwort(antwort, name: str) -> dict:
    for block in antwort.content:
        if block.type == "tool_use" and block.name == name:
            return dict(block.input or {})
    return {}


async def _frage(client, text: str) -> dict:
    """Eine Anfrage, außerhalb der Ereignisschleife ausgeführt.

    Wie bei der Besprechungsanalyse läuft der Aufruf in einem eigenen Thread
    (siehe services/schnittstelle): Das Anthropic-Paket wird synchron benutzt,
    und der Webserver soll währenddessen weiter antworten.
    """

    def ruf():
        return client.messages.create(
            model=CLAUDE_MODELL,
            max_tokens=MAX_TOKENS,
            system=ANWEISUNG,
            tools=[WERKZEUG],
            tool_choice={"type": "tool", "name": WERKZEUG["name"]},
            messages=[{"role": "user", "content": text}],
        )

    antwort = await schnittstelle.mit_wiederholung(ruf)
    return _werkzeug_antwort(antwort, WERKZEUG["name"]) if antwort else {}


# ─────────────────────────────────────────────────────────────────────────────
# Ergebnis säubern
# ─────────────────────────────────────────────────────────────────────────────


def _text(wert) -> str:
    return " ".join(str(wert or "").split())


def zu_angaben(roh: dict) -> FallAngaben:
    """Macht aus der Modellantwort ein geprüftes Ergebnisobjekt.

    Jedes Feld wird einzeln geprüft. Eine Phase 7 oder eine vierstellige
    Postleitzahl wird verworfen und gemeldet, nicht durchgelassen: Was hier
    hineinkommt, steht nachher im Ordnernamen.
    """
    angaben = FallAngaben(
        ort=_text(roh.get("ort")),
        plz=_text(roh.get("plz")),
        strasse=_text(roh.get("strasse")),
    )

    if angaben.plz and not re.fullmatch(r"\d{5}", angaben.plz):
        angaben.hinweise.append(
            f"„{angaben.plz}“ ist keine deutsche Postleitzahl und wurde nicht "
            "übernommen."
        )
        angaben.plz = ""

    phase = roh.get("phase")
    if phase not in (None, ""):
        try:
            zahl = int(phase)
        except (TypeError, ValueError):
            angaben.hinweise.append(
                f"Die Phase „{phase}“ war keine Zahl und wurde nicht übernommen."
            )
        else:
            if zahl in MCDONALDS_PHASEN:
                angaben.phase = zahl
            else:
                angaben.hinweise.append(
                    f"Phase {zahl} gibt es nicht (1–3) — nicht übernommen."
                )

    for hinweis in roh.get("hinweise") or []:
        text = _text(hinweis)
        if text:
            angaben.hinweise.append(text)

    return angaben


# ─────────────────────────────────────────────────────────────────────────────
# Öffentliche Funktion
# ─────────────────────────────────────────────────────────────────────────────


def ist_verfuegbar() -> bool:
    """Steckt ein Anthropic-Schlüssel in der Konfiguration?"""
    return bool((settings.anthropic_api_key or "").strip())


async def analysiere(inhalt: EmlInhalt) -> FallAngaben:
    """Liest den Standort aus dem Inhalt einer Auftragsmail heraus.

    Nur aufrufen, wenn ``mcdonalds_sls`` nichts gefunden hat — siehe
    Modultext.
    """
    if not ist_verfuegbar():
        raise AnalyseFehler(
            "Für die Mail-Analyse fehlt der Anthropic-Schlüssel. Ohne ihn "
            "lassen sich die Angaben von Hand erfassen."
        )
    if not (inhalt.text or "").strip():
        raise AnalyseFehler(
            "Die Mail enthielt keinen Text — es gibt nichts auszuwerten."
        )

    text, hinweise = prompttext(inhalt)

    try:
        roh = await _frage(_client(), text)
    except Exception as fehler:  # Netz, Schlüssel, Kontingent
        # Klartext statt Rohmeldung: Die Schnittstelle antwortet auf Englisch
        # und mit Statuscodes. Wer im Büro eine Auftragsmail hochlädt, sucht
        # damit den Fehler in der Mail, während der Grund die Konfiguration
        # ist (siehe services/schnittstelle).
        raise AnalyseFehler(
            "Die Analyse der Mail ist fehlgeschlagen. "
            + schnittstelle.fehlertext(fehler)
        ) from fehler

    if not roh:
        raise AnalyseFehler(
            "Die Analyse kam ohne verwertbares Ergebnis zurück. Bitte erneut "
            "versuchen oder die Angaben von Hand eintragen."
        )

    angaben = zu_angaben(roh)
    angaben.hinweise = hinweise + inhalt.hinweise + angaben.hinweise
    if not angaben.ort:
        angaben.hinweise.append(
            "In der Mail war kein Ort zu finden. Ohne Ort gibt es keinen "
            "Ortscode und keinen Ordnernamen — bitte nachtragen."
        )
    return angaben
