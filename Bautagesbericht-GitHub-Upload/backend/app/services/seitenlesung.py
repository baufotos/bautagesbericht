"""Handschriftliche Bautagebücher Seite für Seite lesen.

WARUM ES DIESES MODUL GIBT
==========================
Der bisherige Weg schickte bis zu zwölf Seiten in **einer** Anfrage und bat um
eine Firmenliste. Bei gedruckten Formblättern reicht das. Bei einem
handschriftlichen Bautagebuch — sechs Tage, zwölf Blätter, verbundene
Schreibschrift — bricht es zusammen: Jede Seite bekommt einen Bruchteil der
Aufmerksamkeit, Datumsangaben gehen verloren, und Firmen von Montag landen
beim Mittwoch.

Hier wird stattdessen **jede Seite einzeln** gelesen, und zwar zweimal:

1. **Abschrift.** Was steht in welchem Feld? Wörtlich, ohne Deutung.
2. **Prüfung.** Dieselbe Seite noch einmal, zusammen mit der Abschrift, mit
   einem einzigen Auftrag: Finde, was falsch abgeschrieben wurde. Zahlen und
   Firmennamen zuerst.

Der zweite Durchgang ist der teure und der wichtige. Eine Schleife, die beim
ersten Ansehen wie ein "d" aussieht, entpuppt sich beim gezielten Vergleich
als "el" — genau der Unterschied zwischen "Riedd Bau" und "Riedel Bau". Und
weil das Ergebnis in einen Bericht an den Bauherrn wandert, ist der zweite
Blick den Aufwand wert.

WAS AN DIESER STELLE NICHT GERATEN WIRD
=======================================
Unlesbares wird als ``[?]`` gekennzeichnet und nicht ersetzt. Ein erfundener
Firmenname sieht im Bericht genauso aus wie ein richtiger — dagegen hilft nur,
die Unsicherheit sichtbar zu lassen.

DER AUFBAU DES BLATTS
=====================
Das Riedel-Bautagebuch verteilt einen Tag auf zwei Seiten:

* **Seite 1/2** — Datum, Baustelle, Wetter, Arbeitskräfte, Geräte,
  Nachunternehmer mit Anzahl, Sonstiges, Besuche.
* **Seite 2/2** — "Ausgeführte Arbeiten", nach Firmen gegliedert.

Die Anzahl der Leute steht also auf der einen Seite und die Leistung auf der
anderen. Erst das Zusammenführen beider ergibt einen Firmeneintrag — deshalb
liest dieses Modul das ganze Dokument und nicht einzelne Seiten für sich.
"""

from __future__ import annotations

import asyncio
import base64
import io
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app.config import settings
from app.services import bautext, bildformate, firmennamen, schnittstelle

# HEIC/HEIF bei Pillow anmelden. Handschriftliche Berichte kommen als
# Handyfoto, und ein iPhone fotografiert in HEIC — ohne diese Zeile wirft
# ``Image.open`` und die Seite gilt als unlesbar.
bildformate.registriere()

#: Auflösung, mit der gerendert wird. 300 dpi statt der bisherigen 200: Bei
#: verbundener Schreibschrift entscheidet die Auflösung darüber, ob eine
#: Oberlänge als "l" oder als "e" ankommt.
DPI = 300

#: Längste Kante eines Bildes, das an die Schnittstelle geht.
#:
#: WARUM AUSGERECHNET DIESER WERT
#: Die Modelle rechnen ein Bild mit mehr als 1568 Pixeln auf der langen Kante
#: selbst herunter. Vorher standen hier 2600 — jedes Blatt wurde also mit
#: 2600 Pixeln übertragen und drüben wieder auf 1568 verkleinert. Die
#: zusätzliche Auflösung kam nie an, kostete aber Zeit, und das Verkleinern
#: übernahm die Gegenseite statt LANCZOS hier.
#:
#: 1540 liegt knapp darunter und bleibt damit unangetastet.
MAX_KANTE = 1540

#: Anteil der langen Blattkante, den ein Ausschnitt abdeckt.
#:
#: WOZU AUSSCHNITTE
#: Ein A4-Blatt als Ganzes hat bei 1540 Pixeln Höhe rund 134 dpi. Das reicht
#: für Druckbuchstaben und ist bei verbundener Schreibschrift genau die
#: Grenze, an der eine Schleife zur Deutungsfrage wird. Ein Ausschnitt über
#: die halbe Blatthöhe hat dagegen die BREITE als lange Kante — dieselben
#: 1540 Pixel ergeben dann rund 190 dpi. Dieselbe Handschrift, anderthalbfach
#: so groß, ohne dass die Schnittstelle etwas dazutun muss.
#:
#: 0,55 statt 0,5: Die beiden Ausschnitte überlappen sich in der Mitte um
#: 10 % der Blatthöhe. Eine Tabellenzeile, die genau auf der Schnittkante
#: liegt, ist damit auf einem der beiden ganz zu sehen.
AUSSCHNITT_ANTEIL = 0.55

#: JPEG-Güte. Hoch angesetzt, weil Kompressionsartefakte genau die dünnen
#: Striche fressen, auf die es hier ankommt.
JPEG_GUETE = 92

#: Wie viele Seiten gleichzeitig gelesen werden. Zwei Durchgänge je Seite mal
#: zwölf Seiten sind 24 Anfragen; nacheinander dauert das mehrere Minuten.
#: Vier gleichzeitig ist ein Maß, das die Schnittstelle nicht überfährt.
GLEICHZEITIG = 4

#: Obergrenze, damit ein versehentlich hochgeladener Aktenordner nicht
#: unbemerkt hunderte Anfragen auslöst.
MAX_SEITEN = 40

#: Wie oft eine Anfrage wiederholt wird, die an etwas Vorübergehendem
#: gescheitert ist — Überlastung, Zeitüberschreitung, kurzer Netzaussetzer.
#:
#: Ohne das ging eine ganze Seite verloren, weil die Schnittstelle für zwei
#: Sekunden überlastet war: In der Woche fehlte dann ein Tag, und in der
#: Oberfläche stand als Grund "gerade überlastet" — für den Anwender ein
#: Hinweis, mit dem er nichts anfangen kann, weil er die Datei ja schon
#: hochgeladen hat.
VERSUCHE = 3

#: Wartezeit vor dem zweiten Versuch, danach jeweils das Doppelte.
WARTEN_SEKUNDEN = 2.0

CLAUDE_MODELL = "claude-opus-5"


# ─────────────────────────────────────────────────────────────────────────────
# Ergebnisformen
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class FirmenZeile:
    """Eine Firma auf einem Blatt — Anzahl von Seite 1, Leistung von Seite 2."""

    firma: str = ""
    personen: int = 0
    leistung: str = ""
    ort: str = ""


@dataclass
class SeitenBefund:
    """Was auf einer Seite steht."""

    seite: int
    #: 1 = erste Seite eines Blattes (Kopf und Nachunternehmer),
    #: 2 = Fortsetzung (ausgeführte Arbeiten). 0 = unbekannt.
    blattseite: int = 0
    #: Blatt-Nummer des Bautagebuchs, wenn lesbar. Verbindet Seite 1 und 2.
    blatt_nr: str = ""
    datum: date | None = None
    baustelle: str = ""
    arbeitszeit: str = ""
    wetter: str = ""
    firmen: list[FirmenZeile] = field(default_factory=list)
    sonstiges: list[str] = field(default_factory=list)
    besuche: list[str] = field(default_factory=list)
    #: Was der zweite Durchgang korrigiert hat — fürs Protokoll.
    korrekturen: list[str] = field(default_factory=list)
    #: Klartext, wenn eine Seite nicht gelesen werden konnte.
    fehler: str = ""

    @property
    def leer(self) -> bool:
        return not (self.firmen or self.sonstiges or self.besuche or self.datum)


@dataclass
class Tagesbefund:
    """Ein Tag, aus einer oder zwei Seiten zusammengesetzt."""

    datum: date | None
    seiten: list[int]
    firmen: list[FirmenZeile]
    haupteintrag: str = ""
    baustelle: str = ""
    korrekturen: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Bilder
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Seitenbild:
    """Eine Seite in zwei Auflösungen.

    ``uebersicht`` ist das ganze Blatt: daran erkennt man den Aufbau, welche
    Spalte welche ist und ob dies eine Kopf- oder eine Fortsetzungsseite ist.

    ``ausschnitte`` sind überlappende Hälften desselben Blattes, jede für sich
    mit rund anderthalbfacher Auflösung (siehe ``AUSSCHNITT_ANTEIL``). Sie
    gehen in den zweiten Durchgang — der soll ja nicht dasselbe Bild noch
    einmal ansehen, sondern mehr sehen als der erste.
    """

    uebersicht: bytes
    ausschnitte: list[bytes] = field(default_factory=list)


def _jpeg(bild) -> bytes:
    puffer = io.BytesIO()
    bild.save(puffer, format="JPEG", quality=JPEG_GUETE, optimize=True)
    return puffer.getvalue()


def _lesbar_machen(bild):
    """Kontrast und Schärfe eines Blattes für die Erkennung.

    Handschriftliche Berichte kommen als Handyfoto: schief belichtet, grauer
    Schatten über dem Blatt, Bleistift auf vergilbtem Papier.

    * **Autokontrast** mit 0,5 % Beschnitt an beiden Enden hebt blasse
      Bleistiftschrift vom Papier ab und schneidet Schatten und Durchschein
      weg.
    * **Unscharfmaskieren** danach: Beim Verkleinern von 300 dpi auf die
      Zielgröße verwischt LANCZOS genau die dünnen Striche, auf die es
      ankommt. Ein leichtes Nachschärfen holt die Kanten zurück, ohne das
      Papierkorn hochzuziehen.
    """
    from PIL import ImageFilter, ImageOps

    bild = ImageOps.autocontrast(bild, cutoff=0.5)
    return bild.filter(ImageFilter.UnsharpMask(radius=1.2, percent=80,
                                               threshold=3))


def _verkleinert(bild):
    from PIL import Image

    kopie = bild.copy()
    kopie.thumbnail((MAX_KANTE, MAX_KANTE), Image.Resampling.LANCZOS)
    return kopie


def _ausschnitte(bild) -> list:
    """Zwei überlappende Hälften, geteilt entlang der langen Blattkante.

    Geteilt wird immer quer zur langen Kante: Bei einem hochkanten A4-Blatt
    entstehen so zwei breite Streifen, und eine Tabellenzeile bleibt in einem
    Stück. Bei einem querformatigen Foto ist es umgekehrt.

    Ein Blatt, das schon fast quadratisch ist, gewinnt durch das Teilen
    nichts — dann bleibt die Liste leer und der zweite Durchgang arbeitet mit
    der Übersicht.
    """
    breite, hoehe = bild.size
    if max(breite, hoehe) < 1.15 * min(breite, hoehe):
        return []

    if hoehe >= breite:
        fenster = int(hoehe * AUSSCHNITT_ANTEIL)
        rahmen = [(0, 0, breite, fenster), (0, hoehe - fenster, breite, hoehe)]
    else:
        fenster = int(breite * AUSSCHNITT_ANTEIL)
        rahmen = [(0, 0, fenster, hoehe), (breite - fenster, 0, breite, hoehe)]
    return [bild.crop(r) for r in rahmen]


def _als_seitenbild(bild) -> Seitenbild:
    """Aus einem geöffneten Bild die zwei Auflösungen machen.

    Reihenfolge mit Bedacht: Zuerst wird aus dem GROSSEN Original
    ausgeschnitten und erst der Ausschnitt verkleinert. Umgekehrt — erst
    verkleinern, dann schneiden — wäre der Ausschnitt nur ein
    Bildschirmausschnitt und hätte keinen einzigen Bildpunkt mehr als die
    Übersicht. Genau darin liegt der Gewinn.
    """
    from PIL import ImageOps

    bild = ImageOps.exif_transpose(bild)
    if bild.mode != "RGB":
        bild = bild.convert("RGB")

    uebersicht = _jpeg(_lesbar_machen(_verkleinert(bild)))
    teile = [_jpeg(_lesbar_machen(_verkleinert(teil)))
             for teil in _ausschnitte(bild)]
    return Seitenbild(uebersicht=uebersicht, ausschnitte=teile)


def _seitenbilder(pfad: Path) -> list[Seitenbild]:
    """PDF-Seiten oder ein Foto als aufbereitete Bilder."""
    if pfad.suffix.lower() != ".pdf":
        einzeln = _aufbereiten(pfad)
        return [einzeln] if einzeln else []

    import pypdfium2 as pdfium

    bilder: list[Seitenbild] = []
    doc = pdfium.PdfDocument(str(pfad))
    try:
        for i in range(min(len(doc), MAX_SEITEN)):
            bilder.append(_als_seitenbild(doc[i].render(scale=DPI / 72).to_pil()))
    finally:
        doc.close()
    return bilder


def _aufbereiten(pfad: Path) -> Seitenbild | None:
    """Ein einzelnes Foto oder Bild aufbereiten. ``None``, wenn unlesbar."""
    from PIL import Image

    try:
        with Image.open(pfad) as bild:
            return _als_seitenbild(bild)
    except Exception:
        # Unlesbares Bild: als Rohdaten weiterreichen. Vielleicht kommt die
        # Schnittstelle damit zurecht, wo Pillow es nicht tut.
        try:
            return Seitenbild(uebersicht=pfad.read_bytes())
        except OSError:
            return None


def _bildblock(daten: bytes, medientyp: str = "image/jpeg") -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": medientyp,
            "data": base64.standard_b64encode(daten).decode(),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Was gefragt wird
# ─────────────────────────────────────────────────────────────────────────────


def _schema() -> dict:
    return {
        "name": "seite_abschreiben",
        "description": "Gibt zurück, was auf dieser Seite steht.",
        "input_schema": {
            "type": "object",
            "properties": {
                "blattseite": {
                    "type": "integer",
                    "description": "1 = Kopfseite mit Datum und Nachunternehmern, "
                                   "2 = Fortsetzung mit ausgeführten Arbeiten, "
                                   "0 = weder noch",
                },
                "blatt_nr": {"type": "string"},
                "datum": {
                    "type": "string",
                    "description": "TT.MM.JJJJ, oder leer wenn kein Datum dasteht",
                },
                "baustelle": {"type": "string"},
                "arbeitszeit": {"type": "string"},
                "wetter": {"type": "string"},
                "firmen": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "firma": {"type": "string"},
                            "personen": {"type": "integer"},
                            "leistung": {"type": "string"},
                            "ort": {"type": "string"},
                        },
                        "required": ["firma", "personen", "leistung", "ort"],
                    },
                },
                "sonstiges": {"type": "array", "items": {"type": "string"}},
                "besuche": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["blattseite", "datum", "firmen"],
        },
    }


def _pruef_schema() -> dict:
    schema = _schema()
    schema["name"] = "seite_pruefen"
    schema["description"] = "Gibt die berichtigte Fassung zurück."
    schema["input_schema"]["properties"]["korrekturen"] = {
        "type": "array",
        "items": {"type": "string"},
        "description": "Je Berichtigung ein Satz: was stand da, was ist richtig.",
    }
    return schema


_GRUNDLAGEN = (
    "Du liest ein Bautagebuch von einer Baustelle. Es ist mit der Hand "
    "ausgefüllt, oft in verbundener deutscher Schreibschrift, meist mit "
    "Kugelschreiber.\n\n"
    "SO IST DAS BLATT AUFGEBAUT\n"
    "Viele Vordrucke verteilen einen Tag auf zwei Seiten:\n"
    "  Seite 1 — Datum, Baustelle, Bau-Nr., Arbeitszeit, Wetter, "
    "Arbeitskräfte, Geräte, dann eine Tabelle 'Nachunternehmer' mit Firma "
    "und Anzahl, darunter 'Sonstiges' und 'Besuche'.\n"
    "  Seite 2 — 'Ausgeführte Arbeiten', nach Firmen gegliedert: links der "
    "Firmenname mit Doppelpunkt, rechts daneben die Tätigkeiten.\n\n"
    "WAS IN WELCHES FELD GEHÖRT\n"
    "  blattseite  1 oder 2, siehe oben. 0, wenn das Blatt anders aussieht.\n"
    "  datum       Nur das Datum aus dem Kopf, als TT.MM.JJJJ. Steht dort ein "
    "Wochentag davor ('Mo. 15.01.2024'), gehört er nicht ins Feld. Auf einer "
    "Fortsetzungsseite steht meist kein Datum — dann leer lassen.\n"
    "  firmen      Auf Seite 1 aus der Nachunternehmer-Tabelle: firma und "
    "personen (die Zahl in der Spalte 'Anzahl'), leistung bleibt leer. Auf "
    "Seite 2 aus 'Ausgeführte Arbeiten': firma und leistung, personen 0.\n"
    "              Die Nachunternehmer-Tabelle hat MEHRERE Spaltenpaare "
    "'Firma | Anzahl' nebeneinander — üblicherweise vier. Die Anzahl steht "
    "IMMER in der Spalte direkt rechts neben dem Namen, nicht in einer "
    "weiter rechts liegenden. Sind die rechten Paare leer, gibt es dort auch "
    "keine Firma. Steht hinter der Anzahl noch eine Uhrzeit "
    "('3  10⁰⁰-13⁰⁰'), gehört sie in leistung und nicht in personen.\n"
    "  ort         Bauteil, Geschoss, Achse — soweit in der Zeile genannt "
    "('4.OG. Trh. Nord'). Sonst leer.\n"
    "  sonstiges   Die Zeilen aus dem Feld 'Sonstiges', je Zeile ein Eintrag.\n"
    "  besuche     Die Zeilen aus dem Feld 'Besuche'.\n\n"
    "REGELN\n"
    "- Schreibe ab, was dasteht. Deute nichts hinein und ergänze nichts.\n"
    "- Unleserlich: den erkennbaren Teil schreiben und [?] anhängen. Lieber "
    "'Ried[?]' als ein geratener Name.\n"
    "- Ein leeres Feld bleibt leer. Erfinde keine Werte.\n"
    "- Durchgestrichenes ist zurückgenommen und gehört nicht ins Ergebnis.\n"
    "- Spaltenüberschriften des Vordrucks ('Firma', 'Anzahl', 'Polier', "
    "'Maurer', 'Radlader') sind keine Inhalte.\n"
    "- Die Zahl bei 'personen' ist die Anzahl Personen, nicht eine Uhrzeit "
    "und keine Stundenzahl.\n"
    "- Geschosse in der üblichen Schreibweise: 4.OG, 1.UG, EG."
)

_PRUEFAUFTRAG = (
    "Das ist dieselbe Seite noch einmal, zusammen mit der Abschrift des "
    "ersten Durchgangs.\n\n"
    "Deine Aufgabe ist nicht, neu abzuschreiben, sondern **Fehler zu "
    "finden**. Geh die Abschrift Feld für Feld gegen das Bild durch. Achte "
    "besonders auf:\n"
    "- **Zahlen.** Anzahl der Personen, Datum, Uhrzeiten. Eine 1 und eine 7 "
    "sehen in deutscher Handschrift ähnlich aus, ebenso 4 und 9.\n"
    "- **Firmennamen.** Vergleiche Buchstabe für Buchstabe. Kommt derselbe "
    "Name auf dem Blatt mehrfach vor, muss er überall gleich geschrieben "
    "sein.\n"
    "- **Ausgelassenes.** Eine Zeile, eine Firma, ein Eintrag unter "
    "'Sonstiges', der in der Abschrift fehlt.\n\n"
    "Gib die berichtigte Fassung vollständig zurück — auch die Felder, an "
    "denen nichts zu ändern war. Trage unter 'korrekturen' jede Änderung mit "
    "einem Satz ein ('personen bei Riedel Bau: 5 gelesen, richtig ist 3'). "
    "War nichts zu ändern, bleibt 'korrekturen' leer."
)

#: Erklärt die vergrößerten Ausschnitte des zweiten Durchgangs. Ohne diesen
#: Satz werden sie für weitere Blätter gehalten und ihre Firmen ein zweites
#: Mal aufgeführt — aus drei Nachunternehmern wurden sechs.
_AUSSCHNITT_HINWEIS = (
    "\n\nZU DEN BILDERN\n"
    "Das erste Bild ist das ganze Blatt. Die Bilder danach sind vergrößerte "
    "Ausschnitte DESSELBEN Blattes — obere und untere Hälfte, mit einer "
    "Überlappung in der Mitte. Sie zeigen dieselbe Handschrift größer und "
    "sind dafür da, dass du Buchstaben und Zahlen genau vergleichen kannst.\n"
    "Es sind KEINE weiteren Blätter und keine weiteren Tage. Was auf zwei "
    "Ausschnitten zu sehen ist, gehört einmal ins Ergebnis, nicht zweimal."
)


def _bekannt_hinweis(bekannte: tuple[str, ...]) -> str:
    """Die Firmen der Baustelle als Hilfe mitgeben.

    Das ist der wirksamste einzelne Hebel für die Erkennung: Wer weiß, dass
    auf dieser Baustelle "Riedel Bau", "Miro Ventig" und "Goni Bau"
    arbeiten, liest eine krakelige Schleife richtig.

    Bewusst als Hilfe formuliert und nicht als Auswahlliste — sonst wird eine
    neue Firma in eine bekannte umgedeutet.
    """
    if not bekannte:
        return ""
    liste = ", ".join(bekannte[:15])
    return (
        "\n\nAUF DIESER BAUSTELLE BEKANNT\n"
        f"Diese Firmen kommen auf diesem Projekt vor: {liste}.\n"
        "Das ist eine Lesehilfe, keine Auswahlliste: Passt ein Name "
        "erkennbar zu einem davon, nimm die bekannte Schreibweise. Steht "
        "dort eine andere Firma, schreib sie so ab, wie sie dasteht."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Die Anfragen
# ─────────────────────────────────────────────────────────────────────────────


def _client():
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _werkzeug_antwort(antwort, name: str) -> dict:
    for block in antwort.content:
        if block.type == "tool_use" and block.name == name:
            return dict(block.input or {})
    return {}


async def _frage(client, inhalt: list[dict], schema: dict) -> dict:
    """Eine Anfrage an die Schnittstelle.

    Der Aufruf läuft in einem eigenen Thread und wird bei vorübergehenden
    Störungen wiederholt — beides steckt in ``services/schnittstelle``, weil
    die Formblatt-Erkennung und die Besprechungsanalyse dasselbe brauchen.

    Warum der eigene Thread: Das Anthropic-Paket wird hier synchron benutzt,
    und der Webserver stünde währenddessen sonst still — bei 24 Anfragen wären
    das mehrere Minuten, in denen die App nicht antwortet.
    """

    def ruf():
        return client.messages.create(
            model=CLAUDE_MODELL,
            max_tokens=8192,
            tools=[schema],
            tool_choice={"type": "tool", "name": schema["name"]},
            messages=[{"role": "user", "content": inhalt}],
        )

    antwort = await schnittstelle.mit_wiederholung(
        ruf, versuche=VERSUCHE, warten=WARTEN_SEKUNDEN)
    return _werkzeug_antwort(antwort, schema["name"]) if antwort else {}


#: Beides steht in services/schnittstelle, weil auch die Formblatt-Erkennung
#: und die Besprechungsanalyse es brauchen. Die Namen bleiben hier stehen: Sie
#: sind die, unter denen pdf_extraction und die Prüfungen sie kennen.
_vorruebergehend = schnittstelle.vorruebergehend


def _als_datum(text: str) -> date | None:
    """Das Datum aus einer abgeschriebenen Datumsangabe.

    Nutzt die Datumsmuster der Wochenaufteilung, damit hier nicht eine
    zweite, engere Fassung dessen steht, was dort schon an echten
    Firmenberichten ausgemessen wurde: "5.1.24", "15-01-2024", "Mo.
    15.01.2024", aber auch die Formen, in denen die Texterkennung Punkte
    verliert ("15 01 2024", "15012024").
    """
    from app.services.wochenaufteilung import daten_in_text

    gefunden = daten_in_text(str(text or ""))
    return gefunden[0] if gefunden else None


def _zu_befund(seite: int, roh: dict) -> SeitenBefund:
    firmen = []
    for eintrag in (roh.get("firmen") or []):
        name = firmennamen.normalisiere(str(eintrag.get("firma", "")))
        if not name:
            continue
        try:
            personen = int(eintrag.get("personen") or 0)
        except (TypeError, ValueError):
            personen = 0
        firmen.append(FirmenZeile(
            firma=name,
            personen=max(0, personen),
            leistung=bautext.geraderuecken(str(eintrag.get("leistung", "")).strip()),
            ort=bautext.geraderuecken(str(eintrag.get("ort", "")).strip()),
        ))

    return SeitenBefund(
        seite=seite,
        blattseite=int(roh.get("blattseite") or 0),
        blatt_nr=str(roh.get("blatt_nr", "")).strip(),
        datum=_als_datum(roh.get("datum", "")),
        baustelle=str(roh.get("baustelle", "")).strip(),
        arbeitszeit=str(roh.get("arbeitszeit", "")).strip(),
        wetter=str(roh.get("wetter", "")).strip(),
        firmen=firmen,
        sonstiges=[bautext.geraderuecken(str(z).strip())
                   for z in (roh.get("sonstiges") or []) if str(z).strip()],
        besuche=[bautext.geraderuecken(str(z).strip())
                 for z in (roh.get("besuche") or []) if str(z).strip()],
        korrekturen=[str(k).strip() for k in (roh.get("korrekturen") or [])
                     if str(k).strip()],
    )


#: Die Fehlerdeutung steht in services/schnittstelle — die Formblatt-
#: Erkennung und die Besprechungsanalyse brauchen dieselbe. Hier bleiben die
#: Namen, unter denen pdf_extraction und die Prüfungen sie kennen.
fehlertext = schnittstelle.fehlertext
_endgueltig = schnittstelle.endgueltig


async def _lies_seite(client, nummer: int, bild: Seitenbild,
                      bekannte: tuple[str, ...]) -> SeitenBefund:
    """Eine Seite: abschreiben, dann mit mehr Auflösung nachprüfen.

    Der Unterschied zum ersten Entwurf steckt im zweiten Durchgang: Er sieht
    nicht dasselbe Bild noch einmal, sondern zusätzlich die vergrößerten
    Ausschnitte (siehe ``Seitenbild``). Ein zweiter Blick auf dieselben
    Bildpunkte findet vor allem das, was schon beim ersten Mal zu sehen war;
    ein zweiter Blick mit anderthalbfacher Auflösung findet die Schleife, die
    beim ersten Mal ein "d" war und in Wahrheit "el" heißt.
    """
    hinweis = _bekannt_hinweis(bekannte)

    try:
        erste = await _frage(
            client,
            [_bildblock(bild.uebersicht),
             {"type": "text", "text": _GRUNDLAGEN + hinweis}],
            _schema(),
        )
    except Exception as fehler:
        return SeitenBefund(seite=nummer, fehler=fehlertext(fehler))

    # Zweiter Durchgang. Schlägt er fehl, gilt die erste Abschrift — ein
    # ungeprüftes Ergebnis ist besser als gar keines.
    try:
        import json

        bilder = [_bildblock(bild.uebersicht)]
        bilder += [_bildblock(teil) for teil in bild.ausschnitte]
        auftrag = _GRUNDLAGEN + hinweis
        if bild.ausschnitte:
            auftrag += _AUSSCHNITT_HINWEIS
        auftrag += (
            "\n\n" + _PRUEFAUFTRAG
            + "\n\nABSCHRIFT DES ERSTEN DURCHGANGS:\n"
            + json.dumps(erste, ensure_ascii=False, indent=1)
        )

        geprueft = await _frage(
            client,
            bilder + [{"type": "text", "text": auftrag}],
            _pruef_schema(),
        )
        if geprueft:
            return _zu_befund(nummer, geprueft)
    except Exception:
        pass

    return _zu_befund(nummer, erste)


# ─────────────────────────────────────────────────────────────────────────────
# Seiten zu Tagen zusammenfügen
# ─────────────────────────────────────────────────────────────────────────────


def _passt_zu_blatt(kopf: SeitenBefund, folge: SeitenBefund) -> bool:
    """Gehört die Fortsetzungsseite zu diesem Kopfblatt?

    Erstes Kriterium ist die Blatt-Nummer. Sie wird allerdings selbst
    handschriftlich eingetragen und auf der Fortsetzung gern zusammen mit der
    Seitenzahl geschrieben ("243|2") — deshalb genügt es, wenn die eine
    Nummer in der anderen steckt. Fehlt sie, entscheidet die Nachbarschaft:
    Seite 2 folgt auf Seite 1.
    """
    a = re.sub(r"[^0-9]", "", kopf.blatt_nr or "")
    b = re.sub(r"[^0-9]", "", folge.blatt_nr or "")
    if a and b:
        return a in b or b in a
    return folge.seite == kopf.seite + 1


def zu_tagen(befunde: list[SeitenBefund],
             bekannte: tuple[str, ...] = ()) -> list[Tagesbefund]:
    """Aus den Seitenbefunden Tage machen.

    Ein Tag ist ein Kopfblatt plus die unmittelbar folgenden
    Fortsetzungsseiten. Die Anzahl der Leute steht auf dem Kopfblatt, die
    Leistung auf der Fortsetzung — zusammengeführt wird über den Firmennamen,
    und zwar tolerant, weil derselbe Name auf zwei Seiten unterschiedlich
    gelesen werden kann.
    """
    tage: list[Tagesbefund] = []
    aktuell: Tagesbefund | None = None
    kopf: SeitenBefund | None = None

    for befund in befunde:
        if befund.fehler or befund.leer:
            continue

        # Ein Kopfblatt beginnt einen neuen Tag — auch dann, wenn sein Datum
        # nicht zu lesen war. Vorher hing das allein am Datum: Ein Blatt,
        # dessen Kopfzeile verschmiert oder abgeschnitten war, wurde als
        # Fortsetzung des Vortags behandelt, und die Arbeitskräfte von
        # Dienstag standen im Bericht von Montag. Ein Tag ohne Datum lässt
        # sich in der Oberfläche zuordnen; ein Tag, den es gar nicht mehr
        # gibt, nicht.
        neuer_tag = befund.blattseite == 1 or (
            befund.blattseite != 2
            and (befund.datum is not None or aktuell is None)
        )
        if neuer_tag or aktuell is None or kopf is None or not _passt_zu_blatt(kopf, befund):
            aktuell = Tagesbefund(
                datum=befund.datum, seiten=[befund.seite],
                firmen=list(befund.firmen),
                haupteintrag="", baustelle=befund.baustelle,
                korrekturen=list(befund.korrekturen),
            )
            aktuell.haupteintrag = _haupteintrag(befund)
            tage.append(aktuell)
            kopf = befund
            continue

        # Fortsetzungsseite: Leistungen an die Firmen des Kopfblatts hängen.
        aktuell.seiten.append(befund.seite)
        aktuell.korrekturen.extend(befund.korrekturen)
        if aktuell.datum is None and befund.datum is not None:
            aktuell.datum = befund.datum
        for zeile in befund.firmen:
            treffer = next(
                (f for f in aktuell.firmen
                 if firmennamen.gleiche_firma(f.firma, zeile.firma)),
                None,
            )
            if treffer is None:
                aktuell.firmen.append(zeile)
                continue
            if zeile.leistung:
                treffer.leistung = (
                    f"{treffer.leistung} · {zeile.leistung}"
                    if treffer.leistung else zeile.leistung
                )
            if zeile.ort and not treffer.ort:
                treffer.ort = zeile.ort
            if zeile.personen and not treffer.personen:
                treffer.personen = zeile.personen
        zusatz = _haupteintrag(befund)
        if zusatz:
            aktuell.haupteintrag = (
                f"{aktuell.haupteintrag}\n{zusatz}"
                if aktuell.haupteintrag else zusatz
            )

    # Schreibweisen über das ganze Dokument angleichen.
    alle = [f.firma for tag in tage for f in tag.firmen]
    zuordnung, _ = firmennamen.vereinheitliche(alle, list(bekannte))
    for tag in tage:
        for zeile in tag.firmen:
            zeile.firma = zuordnung.get(zeile.firma, zeile.firma)

    return tage


def _haupteintrag(befund: SeitenBefund) -> str:
    """"Sonstiges" und "Besuche" werden zum Haupteintrag des Tages.

    Im HPP-Bericht gibt es dafür das Notizfeld über den Firmenblöcken. Dort
    gehört hin, was den ganzen Tag betrifft und keiner Firma zuzuordnen ist:
    Frost, Baustellenräumung, angelieferte Geräte.
    """
    zeilen: list[str] = list(befund.sonstiges)
    if befund.besuche:
        zeilen.append("Besuche: " + "; ".join(befund.besuche))
    return "\n".join(zeilen)


# ─────────────────────────────────────────────────────────────────────────────
# Einstieg
# ─────────────────────────────────────────────────────────────────────────────


def _grundsaetzlich(meldung: str) -> bool:
    """Ist dieser Fehlschlag für alle Seiten derselbe?

    Geprüft wird der bereits übersetzte Klartext, nicht die Ausnahme: An
    dieser Stelle ist die Ausnahme schon zu einem Satz geworden.
    """
    return any(wort in meldung for wort in
               ("Schlüssel", "Guthaben", "Modell nicht benutzen"))


def verfuegbar() -> bool:
    """Kann seitenweise gelesen werden? Braucht einen Anthropic-Schlüssel."""
    schluessel = (settings.anthropic_api_key or "").strip()
    return bool(schluessel) and not schluessel.lower().startswith("dein-")


#: Gelesene Dokumente, damit dieselbe Datei nicht zweimal an die
#: Schnittstelle geht. Das passiert sonst zwangsläufig: Die Wochenanalyse
#: braucht die Datumsangaben, und kurz darauf braucht die Berichtserzeugung
#: die Firmen — beides steht in denselben Seiten. Bei zwölf Seiten sind das
#: 24 vermeidbare Anfragen.
#:
#: Schlüssel ist Pfad samt Änderungszeit und Größe: Wird dieselbe Datei
#: verändert erneut hochgeladen, wird sie neu gelesen.
#:
#: Die Firmen der Baustelle gehören mit in den Schlüssel. Sie sind die
#: stärkste Lesehilfe, und die Wochenanalyse kennt sie noch nicht immer: Wer
#: das Paket vor der Projektwahl hochlädt, ließ die Seiten ohne Lesehilfe
#: lesen — und die Berichtserzeugung bekam danach aus dem Zwischenspeicher
#: genau dieses schlechtere Ergebnis zurück, obwohl sie die Firmen inzwischen
#: kannte.
_zwischenspeicher: dict[tuple, list[SeitenBefund]] = {}

#: Mehr als das behalten wir nicht — die Befunde sind klein, aber unbegrenzt
#: wachsen soll der Speicher eines langlaufenden Servers trotzdem nicht.
_SPEICHER_GRENZE = 32


def _schluessel(pfad: Path, bekannte: tuple[str, ...] = ()) -> tuple:
    hilfe = tuple(sorted(firmennamen.normalisiere(b) for b in bekannte))
    try:
        angabe = pfad.stat()
        return (str(pfad.resolve()), int(angabe.st_mtime), angabe.st_size, hilfe)
    except OSError:
        return (str(pfad), 0, 0, hilfe)


def vergiss(pfad: Path | None = None) -> None:
    """Zwischenspeicher leeren — für Tests und nach dem Aufräumen der Ablage."""
    if pfad is None:
        _zwischenspeicher.clear()
        return
    # Dieselbe Datei kann unter mehreren Lesehilfen im Speicher stehen; beim
    # Vergessen sind alle gemeint.
    stamm = _schluessel(pfad)[:3]
    for merker in [k for k in _zwischenspeicher if k[:3] == stamm]:
        _zwischenspeicher.pop(merker, None)


async def lies_seiten(pfad: Path,
                      bekannte: tuple[str, ...] = ()) -> list[SeitenBefund]:
    """Liest jede Seite einzeln, zweimal, und gibt die Befunde zurück."""
    if not verfuegbar():
        return []

    merker = _schluessel(pfad, bekannte)
    gemerkt = _zwischenspeicher.get(merker)
    if gemerkt is not None:
        return gemerkt

    bilder = await asyncio.to_thread(_seitenbilder, pfad)
    if not bilder:
        return []

    client = _client()

    # Die erste Seite allein, bevor die übrigen losgeschickt werden. Scheitert
    # sie an etwas Grundsätzlichem — falscher Schlüssel, kein Guthaben —,
    # brauchen die anderen elf gar nicht erst zu fahren. Vorher lief eine
    # ganze Woche Bautagebuch in 24 aussichtslose Anfragen, und am Ende stand
    # bloß "0 Tage erkannt", ohne dass jemand den Grund erfuhr.
    erste = await _lies_seite(client, 1, bilder[0], bekannte)
    if erste.fehler and _grundsaetzlich(erste.fehler):
        return [SeitenBefund(seite=i + 1, fehler=erste.fehler)
                for i in range(len(bilder))]

    sperre = asyncio.Semaphore(GLEICHZEITIG)

    async def eine(nummer: int, bild: bytes) -> SeitenBefund:
        async with sperre:
            return await _lies_seite(client, nummer, bild, bekannte)

    befunde = [erste] + list(await asyncio.gather(
        *(eine(i + 2, bild) for i, bild in enumerate(bilder[1:]))
    ))

    if len(_zwischenspeicher) >= _SPEICHER_GRENZE:
        _zwischenspeicher.pop(next(iter(_zwischenspeicher)), None)
    _zwischenspeicher[merker] = befunde
    return befunde


async def lies_dokument(pfad: Path,
                        bekannte: tuple[str, ...] = ()) -> list[Tagesbefund]:
    """Der übliche Weg: Seiten lesen und zu Tagen zusammenfügen."""
    return zu_tagen(await lies_seiten(pfad, bekannte), bekannte)


def fehlermeldungen(befunde: list[SeitenBefund]) -> list[str]:
    """Die Fehlschläge, jeder Grund nur einmal.

    Bei zwölf Seiten mit demselben Problem soll nicht zwölfmal dieselbe Zeile
    in der Oberfläche stehen.
    """
    gesehen: list[str] = []
    for befund in befunde:
        if befund.fehler and befund.fehler not in gesehen:
            gesehen.append(befund.fehler)
    return gesehen


def als_firmeneintraege(tag: Tagesbefund) -> list[dict]:
    """Einen Tagesbefund in das Format bringen, das die Pipeline erwartet.

    ``tagesnotiz`` trägt "Sonstiges" und "Besuche" des Blattes mit — Frost,
    abgehängte Wände, angelieferte Bauheizungen. Das steht auf dem Blatt,
    wurde hier gelesen und zweimal geprüft, hatte aber bis dahin keinen Weg
    in den Bericht: Die Pipeline kennt nur Firmeneinträge, und der
    Haupteintrag kam allein aus dem Textfeld der Oberfläche. Der Inhalt
    verschwand also lautlos.

    Der Umweg über die Firmeneinträge ist bewusst gewählt: Er lässt die
    Schnittstelle von ``extract_from_file`` unverändert (eine Liste von
    Angaben je Firma), und die Pipeline sammelt die Notiz daraus ein — siehe
    ``pipeline._tagesnotizen``.
    """
    eintraege = []
    for zeile in tag.firmen:
        if not zeile.firma:
            continue
        eintrag = {
            "firma": zeile.firma,
            "ort": zeile.ort,
            "personen": zeile.personen,
            "leistung": zeile.leistung,
            "besonderes": None,
            "quelle": "ocr",
        }
        if tag.haupteintrag:
            eintrag["tagesnotiz"] = tag.haupteintrag
        eintraege.append(eintrag)
    return eintraege
