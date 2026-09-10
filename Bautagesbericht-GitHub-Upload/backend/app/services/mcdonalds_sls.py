"""Die SLS-Anfrage von McDonald's nach Regeln auslesen — ohne KI.

WARUM NACH REGELN UND NICHT MIT DEM MODELL
==========================================
Diese Mail schreibt kein Mensch. Sie kommt aus dem SLS-System von McDonald's
(``no-reply@ext.mcdonalds.com``) und sieht jedes Mal gleich aus:

    Betreff:  SLS - Anfrage zur F1 Vorbereitung 56132 Nievern, Auf d. Lay
    Text:     Es wurde ein neuer Standort in SLS angelegt und Sie sind diesem
              Objekt zugeordnet. …
              Wir bitten um Zusendung der vorgenannten Unterlagen bis zum : 04.09.2026
              url:comtradenet:activity_id=2535628

Alles, was das Büro daraus braucht, steht an einer festen Stelle: Phase (F1),
Postleitzahl, Ort, Straße, Abgabetermin und die SLS-Vorgangsnummer. Das mit
einem Sprachmodell zu lesen wäre langsamer, kostet Geld, braucht einen
Schlüssel — und wäre *unzuverlässiger*, weil ein Modell auch mal etwas anderes
für plausibel hält. Ein regulärer Ausdruck auf einer maschinenerzeugten Zeile
trifft immer oder gar nicht, und "gar nicht" ist als Zustand ehrlich.

Damit funktioniert der ganze Ablauf auf dem Bürorechner ohne
Anthropic-Schlüssel (siehe einstellungen.txt) — und das ist der Normalfall.
Dasselbe Muster wie ``besprechung_lokal`` neben ``besprechung_analyse``.

WAS DAS MODELL TROTZDEM TUT
===========================
Nichts, solange die Regeln greifen. Findet der Leser den Betreff nicht (weil
McDonald's das Format ändert oder weil jemand eine ganz andere Mail hochlädt),
springt ``mcdonalds_email_analyse`` ein, falls ein Schlüssel hinterlegt ist.
Die Regeln sind der Hauptweg, die KI der Notausgang — nicht umgekehrt.

DER WEITERGELEITETE VERLAUF IST DIE ZWEITE QUELLE
=================================================
Ricardo leitet die Mail an das Büro weiter. Im Text steht dadurch der
Outlook-Kopf der Originalnachricht:

    From: no-reply@ext.mcdonalds.com
    Sent: Friday, 21 August 2026 14:03:41

Dieses Datum ist der **Leistungsbeginn** der Beauftragung (im Beispiel Nievern
genau die 21.08.2026 aus dem Schreiben an Kocks und RKA) — und nicht das Datum
der Weiterleitung. Wer nur den ``Date``-Kopf der hochgeladenen Datei nimmt,
bekommt den Tag, an dem Ricardo weitergeleitet hat, und schreibt damit einen
falschen Leistungsbeginn in zwei Verträge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from app.services.mcdonalds_email_analyse import EmlInhalt

# ─────────────────────────────────────────────────────────────────────────────
# Die Muster
# ─────────────────────────────────────────────────────────────────────────────

#: Der Betreff der SLS-Anfrage. Er trägt vier der sechs Angaben:
#: "SLS - Anfrage zur F1 Vorbereitung 56132 Nievern, Auf d. Lay"
#:
#: Bewusst großzügig: "Fw:"/"AW:" davor, ein Bindestrich als Gedankenstrich,
#: mehrere Leerzeichen — all das kommt vor und darf nicht am Muster scheitern.
#: Der harte Kern ist "F<Zahl>" und danach die fünfstellige Postleitzahl.
SLS_BETREFF = re.compile(
    r"F\s*(?P<phase>[1-9])\b"          # F1 / F 2 …
    r".*?"                              # "Vorbereitung", "Planung", …
    r"(?P<plz>\d{5})\s+"                # 56132
    r"(?P<ort>[^,]+?)\s*"               # Nievern
    r"(?:,\s*(?P<strasse>.+))?$",       # , Auf d. Lay   (darf fehlen)
    re.IGNORECASE | re.DOTALL,
)

#: Fallback, wenn im Betreff keine Postleitzahl steht: nur die Phase.
SLS_PHASE = re.compile(r"\bF\s*([1-9])\b", re.IGNORECASE)

#: "Wir bitten um Zusendung der vorgenannten Unterlagen bis zum : 04.09.2026"
#: Der Doppelpunkt steht in der Vorlage mit Leerzeichen davor — beides optional.
ABGABE = re.compile(
    r"bis\s+zum\s*:?\s*(?P<datum>\d{1,2}\.\s?\d{1,2}\.\s?\d{2,4})",
    re.IGNORECASE,
)

#: "url:comtradenet:activity_id=2535628" — die Vorgangsnummer im SLS.
#: Für das Büro der Rückweg in das System des Kunden, deshalb aufgehoben.
VORGANG = re.compile(r"activity_id\s*=\s*(\d+)", re.IGNORECASE)

#: Die "Sent:"-Zeile des weitergeleiteten Outlook-Kopfes. Outlook schreibt sie
#: in der Sprache der Oberfläche — englisch bei Ricardo, deutsch bei anderen.
GESENDET = re.compile(
    r"^\s*(?:Sent|Gesendet)\s*:\s*(?P<wert>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

#: Die "From:"-Zeile des weitergeleiteten Kopfes — daran wird erkannt, dass es
#: wirklich eine SLS-Mail ist und nicht irgendein Verlauf.
SLS_ABSENDER = re.compile(r"@ext\.mcdonalds\.com|@de\.mcd\.com", re.IGNORECASE)

#: Monatsnamen beider Sprachen für die "Sent:"-Zeile.
_MONATE = {
    "januar": 1, "january": 1, "jan": 1,
    "februar": 2, "february": 2, "feb": 2,
    "märz": 3, "maerz": 3, "march": 3, "mar": 3, "mrz": 3,
    "april": 4, "apr": 4,
    "mai": 5, "may": 5,
    "juni": 6, "june": 6, "jun": 6,
    "juli": 7, "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "october": 10, "okt": 10, "oct": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "december": 12, "dez": 12, "dec": 12,
}

#: "21 August 2026" / "21. August 2026"
_TEXTDATUM = re.compile(r"(\d{1,2})\.?\s+([A-Za-zÄÖÜäöüß]+)\.?\s+(\d{4})")
#: "04.09.2026" / "4.9.26"
_ZIFFERNDATUM = re.compile(r"(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{2,4})")


@dataclass
class SlsAngaben:
    """Was in der SLS-Anfrage stand. Leere Felder sind ehrlich leer."""

    #: 1–3 (im Musterordner heißen sie PHASE 1 … PHASE 3). ``None`` = nicht
    #: erkannt; dann wählt der Bauleiter die Phase selbst.
    phase: int | None = None
    plz: str = ""
    ort: str = ""
    strasse: str = ""
    #: Wann die Unterlagen beim Kunden sein müssen — im Schreiben an die
    #: Subplaner die Zeile "Abgabe Phase 1".
    abgabetermin: date | None = None
    #: Datum der Original-SLS-Mail = Leistungsbeginn (siehe Modultext).
    leistungsbeginn: date | None = None
    #: SLS-Vorgangsnummer (activity_id).
    sls_vorgang: str = ""
    #: Hat der Leser die Mail als SLS-Anfrage erkannt? Nur dann sind die
    #: Angaben belastbar.
    erkannt: bool = False
    hinweise: list[str] = field(default_factory=list)

    @property
    def adresse(self) -> str:
        """Die Anschrift in einer Zeile: "Auf d. Lay, 56132 Nievern"."""
        teile = []
        if self.strasse:
            teile.append(self.strasse)
        if self.plz or self.ort:
            teile.append(f"{self.plz} {self.ort}".strip())
        return ", ".join(teile)


# ─────────────────────────────────────────────────────────────────────────────
# Datumshilfen
# ─────────────────────────────────────────────────────────────────────────────


def _jahr(rohwert: str) -> int:
    """Zweistellige Jahreszahlen als 20xx lesen."""
    zahl = int(rohwert)
    return zahl + 2000 if zahl < 100 else zahl


def lies_datum(text: str) -> date | None:
    """Erstes Datum in ``text`` — Ziffern- oder Textschreibweise, DE und EN.

    Reihenfolge mit Absicht: Zuerst die Ziffernschreibweise, weil sie im
    deutschen Mailtext die übliche ist ("bis zum : 04.09.2026"). Ein
    Textdatum steht nur im weitergeleiteten Outlook-Kopf.
    """
    treffer = _ZIFFERNDATUM.search(text or "")
    if treffer:
        tag, monat, jahr = treffer.groups()
        try:
            return date(_jahr(jahr), int(monat), int(tag))
        except ValueError:
            pass  # 31.02. — weiter zum Textdatum

    treffer = _TEXTDATUM.search(text or "")
    if treffer:
        tag, monatsname, jahr = treffer.groups()
        monat = _MONATE.get(monatsname.strip(".").lower())
        if monat:
            try:
                return date(int(jahr), monat, int(tag))
            except ValueError:
                return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Der Leser
# ─────────────────────────────────────────────────────────────────────────────


def _ohne_praefix(betreff: str) -> str:
    """"Fw: AW: SLS - Anfrage …" → "SLS - Anfrage …"."""
    return re.sub(
        r"^(?:\s*(?:Fw|Fwd|WG|AW|RE|Antwort)\s*:\s*)+", "", betreff or "",
        flags=re.IGNORECASE,
    )


def _betreffzeilen(inhalt: EmlInhalt) -> list[str]:
    """Alle Zeilen, die ein SLS-Betreff sein könnten.

    Zwei Quellen: der Betreff der hochgeladenen Datei und jede
    ``Subject:``-Zeile im weitergeleiteten Verlauf. Bei einer mehrfach
    weitergeleiteten Mail ist der äußere Betreff manchmal überschrieben
    ("Bitte übernehmen"), während der innere noch stimmt.
    """
    zeilen = [_ohne_praefix(inhalt.betreff)]
    for treffer in re.finditer(
        r"^\s*(?:Subject|Betreff)\s*:\s*(?P<wert>.+?)\s*$",
        inhalt.text or "", re.IGNORECASE | re.MULTILINE,
    ):
        zeilen.append(_ohne_praefix(treffer.group("wert")))
    return [z for z in zeilen if z.strip()]


def _leistungsbeginn(inhalt: EmlInhalt, angaben: SlsAngaben) -> None:
    """Datum der Original-SLS-Mail, nicht der Weiterleitung (siehe Modultext)."""
    for treffer in GESENDET.finditer(inhalt.text or ""):
        gelesen = lies_datum(treffer.group("wert"))
        if gelesen:
            angaben.leistungsbeginn = gelesen
            return

    # Kein weitergeleiteter Kopf: Dann ist die hochgeladene Datei die
    # Originalmail und ihr eigenes Sendedatum das Richtige.
    if inhalt.gesendet_am:
        angaben.leistungsbeginn = inhalt.gesendet_am.date()
        if SLS_ABSENDER.search(inhalt.absender or ""):
            return
        angaben.hinweise.append(
            "Im Mailtext war kein weitergeleiteter „Gesendet:“-Kopf zu finden. "
            "Als Leistungsbeginn steht deshalb das Sendedatum der "
            "hochgeladenen Datei — bitte prüfen, ob das der Tag der "
            "SLS-Anfrage ist."
        )


def lies_sls(inhalt: EmlInhalt) -> SlsAngaben:
    """Liest die Eckdaten aus einer SLS-Anfrage. Ohne Netz, ohne Schlüssel."""
    angaben = SlsAngaben()
    text = inhalt.text or ""

    # ── Betreff: Phase, PLZ, Ort, Straße ──
    for zeile in _betreffzeilen(inhalt):
        treffer = SLS_BETREFF.search(zeile)
        if treffer:
            angaben.phase = int(treffer.group("phase"))
            angaben.plz = treffer.group("plz")
            angaben.ort = " ".join(treffer.group("ort").split())
            angaben.strasse = " ".join((treffer.group("strasse") or "").split())
            angaben.erkannt = True
            break
    else:
        # Kein vollständiger Betreff — wenigstens die Phase retten.
        for zeile in _betreffzeilen(inhalt):
            nur_phase = SLS_PHASE.search(zeile)
            if nur_phase:
                angaben.phase = int(nur_phase.group(1))
                angaben.hinweise.append(
                    f"Im Betreff „{zeile}“ stand die Phase (F{angaben.phase}), "
                    "aber keine Postleitzahl mit Ort. Standort bitte von Hand "
                    "eintragen."
                )
                break

    # ── Text: Abgabetermin und Vorgangsnummer ──
    abgabe = ABGABE.search(text)
    if abgabe:
        angaben.abgabetermin = lies_datum(abgabe.group("datum"))
    if not angaben.abgabetermin and angaben.erkannt:
        angaben.hinweise.append(
            "Im Mailtext war kein Abgabetermin („bis zum …“) zu finden. Er "
            "steht in den Schreiben an die Subplaner als „Abgabe Phase“ und "
            "ist deshalb nachzutragen."
        )

    vorgang = VORGANG.search(text)
    if vorgang:
        angaben.sls_vorgang = vorgang.group(1)

    _leistungsbeginn(inhalt, angaben)

    if not angaben.erkannt:
        angaben.hinweise.append(
            "Die Datei sieht nicht wie eine SLS-Anfrage aus (erwartet wird ein "
            "Betreff wie „SLS - Anfrage zur F1 Vorbereitung 56132 Nievern, "
            "Auf d. Lay“). Die Angaben bitte von Hand eintragen oder prüfen."
        )

    return angaben
