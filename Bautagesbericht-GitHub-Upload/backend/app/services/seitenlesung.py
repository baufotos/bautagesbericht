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
from app.services import bautext, firmennamen

#: Auflösung, mit der gerendert wird. 300 dpi statt der bisherigen 200: Bei
#: verbundener Schreibschrift entscheidet die Auflösung darüber, ob eine
#: Oberlänge als "l" oder als "e" ankommt. Mehr bringt nichts mehr, kostet
#: aber Übertragungszeit.
DPI = 300

#: Längste Kante nach dem Verkleinern.
MAX_KANTE = 2600

#: JPEG-Güte. Hoch angesetzt, weil Kompressionsartefakte genau die dünnen
#: Striche fressen, auf die es hier ankommt.
JPEG_GUETE = 88

#: Wie viele Seiten gleichzeitig gelesen werden. Zwei Durchgänge je Seite mal
#: zwölf Seiten sind 24 Anfragen; nacheinander dauert das mehrere Minuten.
#: Vier gleichzeitig ist ein Maß, das die Schnittstelle nicht überfährt.
GLEICHZEITIG = 4

#: Obergrenze, damit ein versehentlich hochgeladener Aktenordner nicht
#: unbemerkt hunderte Anfragen auslöst.
MAX_SEITEN = 40

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


def _seitenbilder(pfad: Path) -> list[bytes]:
    """PDF-Seiten als aufbereitete JPEG-Bilder."""
    from PIL import Image, ImageOps

    if pfad.suffix.lower() != ".pdf":
        return [_aufbereiten(pfad.read_bytes())]

    import pypdfium2 as pdfium

    bilder: list[bytes] = []
    doc = pdfium.PdfDocument(str(pfad))
    try:
        for i in range(min(len(doc), MAX_SEITEN)):
            bild = doc[i].render(scale=DPI / 72).to_pil()
            bild = ImageOps.exif_transpose(bild).convert("RGB")
            bild.thumbnail((MAX_KANTE, MAX_KANTE), Image.Resampling.LANCZOS)
            # Autokontrast holt blasse Bleistiftschrift vom vergilbten Papier.
            # Die 0,5 % an den Rändern schneiden Schatten und Durchschein weg.
            bild = ImageOps.autocontrast(bild, cutoff=0.5)
            puffer = io.BytesIO()
            bild.save(puffer, format="JPEG", quality=JPEG_GUETE, optimize=True)
            bilder.append(puffer.getvalue())
    finally:
        doc.close()
    return bilder


def _aufbereiten(daten: bytes) -> bytes:
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(daten)) as bild:
            bild = ImageOps.exif_transpose(bild).convert("RGB")
            bild.thumbnail((MAX_KANTE, MAX_KANTE), Image.Resampling.LANCZOS)
            bild = ImageOps.autocontrast(bild, cutoff=0.5)
            puffer = io.BytesIO()
            bild.save(puffer, format="JPEG", quality=JPEG_GUETE, optimize=True)
            return puffer.getvalue()
    except Exception:
        return daten


def _bildblock(daten: bytes) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
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
    """Eine Anfrage, außerhalb der Ereignisschleife ausgeführt.

    ``asyncio.to_thread``, weil das Anthropic-Paket hier synchron benutzt wird
    und der Webserver währenddessen sonst stillstünde — bei 24 Anfragen wären
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

    antwort = await asyncio.to_thread(ruf)
    return _werkzeug_antwort(antwort, schema["name"])


_DATUM = re.compile(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})")


def _als_datum(text: str) -> date | None:
    treffer = _DATUM.search(str(text or ""))
    if not treffer:
        return None
    tag, monat, jahr = (int(g) for g in treffer.groups())
    if jahr < 100:
        jahr += 2000
    try:
        return date(jahr, monat, tag)
    except ValueError:
        return None


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


async def _lies_seite(client, nummer: int, bild: bytes,
                      bekannte: tuple[str, ...]) -> SeitenBefund:
    """Eine Seite: abschreiben, dann prüfen."""
    hinweis = _bekannt_hinweis(bekannte)

    try:
        erste = await _frage(
            client,
            [_bildblock(bild), {"type": "text", "text": _GRUNDLAGEN + hinweis}],
            _schema(),
        )
    except Exception as fehler:
        return SeitenBefund(seite=nummer, fehler=f"Seite {nummer}: {fehler}")

    # Zweiter Durchgang. Schlägt er fehl, gilt die erste Abschrift — ein
    # ungeprüftes Ergebnis ist besser als gar keines.
    try:
        import json

        geprueft = await _frage(
            client,
            [
                _bildblock(bild),
                {"type": "text", "text": (
                    _GRUNDLAGEN + hinweis + "\n\n" + _PRUEFAUFTRAG
                    + "\n\nABSCHRIFT DES ERSTEN DURCHGANGS:\n"
                    + json.dumps(erste, ensure_ascii=False, indent=1)
                )},
            ],
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

        neuer_tag = befund.blattseite != 2 and (
            befund.datum is not None or aktuell is None
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
_zwischenspeicher: dict[tuple, list[SeitenBefund]] = {}

#: Mehr als das behalten wir nicht — die Befunde sind klein, aber unbegrenzt
#: wachsen soll der Speicher eines langlaufenden Servers trotzdem nicht.
_SPEICHER_GRENZE = 32


def _schluessel(pfad: Path) -> tuple:
    try:
        angabe = pfad.stat()
        return (str(pfad.resolve()), int(angabe.st_mtime), angabe.st_size)
    except OSError:
        return (str(pfad), 0, 0)


def vergiss(pfad: Path | None = None) -> None:
    """Zwischenspeicher leeren — für Tests und nach dem Aufräumen der Ablage."""
    if pfad is None:
        _zwischenspeicher.clear()
    else:
        _zwischenspeicher.pop(_schluessel(pfad), None)


async def lies_seiten(pfad: Path,
                      bekannte: tuple[str, ...] = ()) -> list[SeitenBefund]:
    """Liest jede Seite einzeln, zweimal, und gibt die Befunde zurück."""
    if not verfuegbar():
        return []

    merker = _schluessel(pfad)
    gemerkt = _zwischenspeicher.get(merker)
    if gemerkt is not None:
        return gemerkt

    bilder = await asyncio.to_thread(_seitenbilder, pfad)
    if not bilder:
        return []

    client = _client()
    sperre = asyncio.Semaphore(GLEICHZEITIG)

    async def eine(nummer: int, bild: bytes) -> SeitenBefund:
        async with sperre:
            return await _lies_seite(client, nummer, bild, bekannte)

    befunde = list(await asyncio.gather(
        *(eine(i + 1, bild) for i, bild in enumerate(bilder))
    ))

    if len(_zwischenspeicher) >= _SPEICHER_GRENZE:
        _zwischenspeicher.pop(next(iter(_zwischenspeicher)), None)
    _zwischenspeicher[merker] = befunde
    return befunde


async def lies_dokument(pfad: Path,
                        bekannte: tuple[str, ...] = ()) -> list[Tagesbefund]:
    """Der übliche Weg: Seiten lesen und zu Tagen zusammenfügen."""
    return zu_tagen(await lies_seiten(pfad, bekannte), bekannte)


def als_firmeneintraege(tag: Tagesbefund) -> list[dict]:
    """Einen Tagesbefund in das Format bringen, das die Pipeline erwartet."""
    eintraege = []
    for zeile in tag.firmen:
        if not zeile.firma:
            continue
        eintraege.append({
            "firma": zeile.firma,
            "ort": zeile.ort,
            "personen": zeile.personen,
            "leistung": zeile.leistung,
            "besonderes": None,
            "quelle": "ocr",
        })
    return eintraege
