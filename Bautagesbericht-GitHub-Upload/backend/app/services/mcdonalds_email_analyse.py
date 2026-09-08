"""Eine als ``.eml`` exportierte Auftragsmail auswerten.

WAS DIESES MODUL TUT — UND WAS AUSDRÜCKLICH NICHT
=================================================
Es **schlägt vor**. Dieselbe Regel wie bei der Besprechungsanalyse
(``besprechung_analyse``) und aus demselben Grund: Ein falsch gelesener
Standort sieht in der Ablage genauso aus wie ein richtiger. Alles, was hier
entsteht, landet im Fall als Entwurf und ist in der Oberfläche änderbar,
bevor daraus ein Ordnername oder ein Angebot wird.

ZWEI SCHRITTE, DIE GETRENNT BLEIBEN MÜSSEN
==========================================
1. **Die Mail lesen** (``lies_eml``) — reine Stdlib, kein Netz, keine Kosten.
   Sie liefert Betreff, Absender, Datum, Klartext und die Namen der Anhänge.
2. **Die Angaben herauslesen** (``analysiere``) — dafür wird die
   Anthropic-Schnittstelle gefragt.

Der erste Schritt funktioniert immer, der zweite nur mit hinterlegtem
Schlüssel. Auf dem Bürorechner ist er oft nicht hinterlegt (siehe
einstellungen.txt). Deshalb ist die Trennung keine Formsache: Ohne Schlüssel
wird die Mail trotzdem hochgeladen und ihr Text gespeichert, und der Bauleiter
trägt die vier Eckdaten von Hand ein — statt einer Fehlermeldung, nach der er
von vorn anfängt.

WAS NICHT GERATEN WIRD
======================
* Die Leistungsphase nur, wenn sie in der Mail steht. "wahrscheinlich LPH 8"
  ist keine Beauftragung.
* Der Standortname nur, wenn er benennbar ist — nicht aus der Adresse
  zusammengebaut.
* Kein Auftraggeber aus der Absenderdomäne. Wer die Mail geschrieben hat, ist
  nicht zwangsläufig der Auftraggeber.
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

#: Leistungsphasen nach HOAI. Im McDonald's-Ablauf sind vor allem 6–9
#: relevant (Vergabe, Objektüberwachung, Objektbetreuung).
LEISTUNGSPHASEN = tuple(range(1, 10))


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
    """Die herausgelesenen Eckdaten einer Beauftragung."""

    auftraggeber: str = ""
    standort_name: str = ""
    standort_adresse: str = ""
    standort_ort: str = ""
    leistungsphase: int | None = None
    #: Sonstige Eckdaten als {Bezeichnung: Wert} — siehe models.McdonaldsFall.
    eckdaten: dict[str, str] = field(default_factory=dict)
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
# TODO McDonald's: Anweisung und Feldkatalog werden vom Büro nachgereicht.
# Was hier steht, ist ein tragfähiger Anfang mit den vier Angaben, die
# feststehen (Standortname, Adresse, Auftraggeber, Leistungsphase) plus einem
# offenen Fach für alles Weitere. Beide Konstanten sind bewusst reine Daten:
# Sie lassen sich austauschen, ohne den Ablauf darunter anzufassen.
# ─────────────────────────────────────────────────────────────────────────────

ANWEISUNG = """Du liest die Auftragsmail eines Kunden an ein Architekturbüro \
und trägst die Eckdaten in ein Formular ein.

Regeln:

1. NICHTS RATEN. Was nicht in der Mail steht, bleibt leer. Ein leeres Feld \
wird im Büro nachgetragen; ein erfundenes fällt niemandem auf.
2. Der STANDORTNAME ist die Bezeichnung, unter der das Büro den Standort \
kennt — meist Ort plus Lage ("Aachen Europaplatz", "Hamburg Altona"). Steht \
in der Mail nur eine Anschrift, bleibt das Feld leer; die Adresse gehört \
in ihr eigenes Feld.
3. Die ADRESSE vollständig, wie sie in der Mail steht (Straße, Hausnummer, \
Postleitzahl, Ort) — in einer Zeile, Teile durch Komma getrennt.
4. Der ORT ist nur der Ortsname aus dieser Adresse, ohne Postleitzahl und \
ohne Stadtteil ("Hamburg", nicht "22767 Hamburg-Altona"). Er wird für die \
Suche in einer amtlichen Ortstabelle gebraucht, in der nur Ortsnamen stehen.
5. Der AUFTRAGGEBER ist das beauftragende Unternehmen, nicht die Person, die \
die Mail geschrieben hat, und nicht aus der Mailadresse abgeleitet.
6. Die LEISTUNGSPHASE ist eine Zahl von 1 bis 9 nach HOAI und nur zu setzen, \
wenn sie in der Mail benannt ist ("LPH 6", "Leistungsphase 8", "Phase 3"). \
Sonst null.
7. In ECKDATEN gehört, was für die Beauftragung sonst zählt und klar in der \
Mail steht: Termine, Fristen, Ansprechpartner mit Rolle, Projekt- oder \
Bestellnummern des Kunden, Budget. Jeweils als kurze Bezeichnung und Wert. \
Keine Zusammenfassung des Mailtexts.
8. In HINWEISE gehört, was beim Lesen unklar blieb — insbesondere \
Widersprüche und Angaben, die zwar dastehen, aber mehrdeutig sind."""

WERKZEUG = {
    "name": "beauftragung_erfassen",
    "description": (
        "Trägt die Eckdaten einer Auftragsmail in das Formular des Büros ein."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "auftraggeber": {
                "type": "string",
                "description": (
                    "Beauftragendes Unternehmen, wie in der Mail benannt. "
                    "Leer, wenn nicht genannt."
                ),
            },
            "standort_name": {
                "type": "string",
                "description": (
                    "Bezeichnung des Standorts, z. B. 'Aachen Europaplatz'. "
                    "Leer, wenn die Mail nur eine Anschrift enthält."
                ),
            },
            "standort_adresse": {
                "type": "string",
                "description": (
                    "Vollständige Anschrift in einer Zeile, Teile durch Komma "
                    "getrennt."
                ),
            },
            "standort_ort": {
                "type": "string",
                "description": (
                    "Nur der Ortsname aus der Anschrift, ohne Postleitzahl "
                    "und ohne Stadtteil."
                ),
            },
            "leistungsphase": {
                "type": ["integer", "null"],
                "description": (
                    "1 bis 9 nach HOAI, oder null, wenn in der Mail keine "
                    "Phase benannt ist."
                ),
            },
            "eckdaten": {
                "type": "array",
                "description": "Weitere klar benannte Angaben zur Beauftragung.",
                "items": {
                    "type": "object",
                    "properties": {
                        "bezeichnung": {"type": "string"},
                        "wert": {"type": "string"},
                    },
                    "required": ["bezeichnung", "wert"],
                },
            },
            "hinweise": {
                "type": "array",
                "description": "Was beim Lesen unklar oder widersprüchlich war.",
                "items": {"type": "string"},
            },
        },
        "required": [
            "auftraggeber",
            "standort_name",
            "standort_adresse",
            "standort_ort",
            "leistungsphase",
        ],
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

    Jedes Feld wird einzeln geprüft. Eine Phase 12 oder ein Eckdatum ohne
    Bezeichnung wird verworfen und gemeldet, nicht durchgelassen: Was hier
    hineinkommt, steht nachher im Ordnernamen und im Angebot.
    """
    angaben = FallAngaben(
        auftraggeber=_text(roh.get("auftraggeber")),
        standort_name=_text(roh.get("standort_name")),
        standort_adresse=_text(roh.get("standort_adresse")),
        standort_ort=_text(roh.get("standort_ort")),
    )

    phase = roh.get("leistungsphase")
    if phase not in (None, ""):
        try:
            zahl = int(phase)
        except (TypeError, ValueError):
            angaben.hinweise.append(
                f"Die Leistungsphase „{phase}“ war keine Zahl und wurde nicht "
                "übernommen."
            )
        else:
            if zahl in LEISTUNGSPHASEN:
                angaben.leistungsphase = zahl
            else:
                angaben.hinweise.append(
                    f"Leistungsphase {zahl} gibt es nicht (1–9) — nicht "
                    "übernommen."
                )

    for eintrag in roh.get("eckdaten") or []:
        if not isinstance(eintrag, dict):
            continue
        bezeichnung = _text(eintrag.get("bezeichnung"))
        wert = _text(eintrag.get("wert"))
        if bezeichnung and wert:
            angaben.eckdaten[bezeichnung] = wert

    for hinweis in roh.get("hinweise") or []:
        text = _text(hinweis)
        if text:
            angaben.hinweise.append(text)

    if not angaben.standort_ort and angaben.standort_adresse:
        # Der Ort ist die Grundlage des UNLOCODE-Abgleichs. Fehlt er, wird er
        # aus der Adresse abgeleitet — mit Hinweis, denn das ist eine Regel
        # und keine gelesene Angabe.
        from app.services.mcdonalds_unlocode import ort_aus_adresse

        abgeleitet = ort_aus_adresse(angaben.standort_adresse)
        if abgeleitet:
            angaben.standort_ort = abgeleitet
            angaben.hinweise.append(
                f"Der Ort „{abgeleitet}“ wurde aus der Adresse abgeleitet, "
                "nicht der Mail entnommen. Bitte prüfen."
            )

    return angaben


# ─────────────────────────────────────────────────────────────────────────────
# Öffentliche Funktion
# ─────────────────────────────────────────────────────────────────────────────


def ist_verfuegbar() -> bool:
    """Steckt ein Anthropic-Schlüssel in der Konfiguration?"""
    return bool((settings.anthropic_api_key or "").strip())


async def analysiere(inhalt: EmlInhalt) -> FallAngaben:
    """Liest die Eckdaten aus dem Inhalt einer Auftragsmail heraus."""
    if not ist_verfuegbar():
        raise AnalyseFehler(
            "Für die Mail-Analyse fehlt der Anthropic-Schlüssel. In "
            "einstellungen.txt bei „anthropic_key=“ eintragen — er beginnt "
            "mit „sk-ant-“. Ohne ihn lassen sich die Angaben von Hand "
            "erfassen."
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
    if not (angaben.standort_name or angaben.standort_adresse):
        angaben.hinweise.append(
            "In der Mail war kein Standort zu finden. Ohne Standort lässt "
            "sich kein Projektordner benennen — bitte nachtragen."
        )
    return angaben
