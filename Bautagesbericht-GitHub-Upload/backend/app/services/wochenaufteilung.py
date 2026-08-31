"""Ein Wochenpaket in Tagesberichte zerlegen.

WOZU
====
Bisher gehörte eine Einreichung zu genau einem Tag: Man lud die Berichte der
Firmen für Montag hoch, bekam Montag, und begann für Dienstag von vorn — fünf
Mal pro Woche dasselbe. Die Firmen liefern ihre Berichte aber ohnehin
wochenweise, oft als ein PDF mit einer Seite je Tag.

Dieses Modul beantwortet die eine Frage, an der das bisher scheiterte:
**Welcher Tag steht auf welcher Seite?** Alles Weitere (Wetter, Extraktion,
Word-Erzeugung) kann danach unverändert je Tag laufen — es bekommt ein
Teil-PDF, das nur die Seiten dieses Tages enthält.

WARUM EIN EIGENES MODUL
=======================
Die Zerlegung ist reine Textarbeit an Datumsangaben und hat weder mit Word,
noch mit der Datenbank, noch mit FastAPI zu tun. Sie lässt sich damit
vollständig prüfen, ohne irgendetwas hochzuladen — und genau das ist nötig,
denn ein falsch erkanntes Datum schreibt die Arbeit eines Tages in den Bericht
eines anderen. Das fällt beim Durchsehen kaum auf.

WAS ES NICHT TUT
================
Es rät nicht. Findet es auf einer Seite kein Datum, sagt es das
(``datum is None``) und überlässt die Zuordnung dem Menschen. Ein
Scan ohne Textlayer und ein Handyfoto haben keinen lesbaren Kopf — dort ist
Raten schlimmer als Nachfragen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

#: Dateiendungen, in denen überhaupt nach Text gesucht werden kann.
TEXT_ENDUNGEN = {".pdf"}

#: Endungen, die als Bild gelten — dort gibt es keinen Textlayer.
BILD_ENDUNGEN = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".heic"}

#: Ab hier gilt ein Jahr als Tippfehler und nicht als Datum.
JAHR_VON, JAHR_BIS = 2000, 2100

# TT.MM.JJJJ und TT.MM.JJ — die Schreibweise auf praktisch jedem deutschen
# Bautagesbericht. Als Trennzeichen sind auch Bindestrich, Schrägstrich, Komma
# und Leerzeichen erlaubt: Vorlagen setzen das unterschiedlich, und die
# Texterkennung liest einen Punkt gern als Komma oder verliert ihn ganz
# ("Di. 02 04.2024" ist echter OCR-Text aus einem Firmenbericht).
_TRENNER = r"[.,\-/ ]"
_DEUTSCH = re.compile(
    rf"\b(?P<tag>\d{{1,2}}){_TRENNER}(?P<monat>\d{{1,2}}){_TRENNER}(?P<jahr>\d{{2}}|\d{{4}})\b"
)

# TTMMJJJJ ohne jedes Trennzeichen — so kommt es aus der Texterkennung, wenn
# alle Punkte verlorengegangen sind ("Mi. 03042024"). Nur mit vierstelligem
# Jahr, sonst wäre jede achtstellige Auftragsnummer ein Datum.
_KOMPAKT = re.compile(r"\b(?P<tag>\d{2})(?P<monat>\d{2})(?P<jahr>\d{4})\b")

# Nur EIN Punkt ist verlorengegangen — der häufigste Fall bei gescannten
# Formblättern ("Sa. 0604.2024", "erstellt 31.012020").
_HALB_VORNE = re.compile(
    rf"\b(?P<tag>\d{{2}})(?P<monat>\d{{2}}){_TRENNER}(?P<jahr>\d{{4}})\b"
)
_HALB_HINTEN = re.compile(
    rf"\b(?P<tag>\d{{1,2}}){_TRENNER}(?P<monat>\d{{2}})(?P<jahr>\d{{4}})\b"
)

# Tag und Monat ohne brauchbares Jahr. Wird NUR mit vorgegebenem Zeitraum
# ausgewertet — siehe _aus_tag_monat.
_TAG_MONAT = re.compile(rf"\b(?P<tag>\d{{1,2}}){_TRENNER}(?P<monat>\d{{1,2}})\b")

# JJJJ-MM-TT — kommt aus Systemen, die Berichte automatisch benennen.
_ISO = re.compile(r"\b(?P<jahr>\d{4})-(?P<monat>\d{1,2})-(?P<tag>\d{1,2})\b")

#: Wörter, die eine Zeile als Datumszeile ausweisen. Steht auf einer Seite
#: mehr als ein Datum (Berichtsdatum, Vertragsfristen, Wetterbezug), gewinnt
#: die Zeile mit einem dieser Wörter.
_DATUMSWORTE = re.compile(
    r"\b(datum|bautag|berichtstag|berichtsdatum|tagesbericht|tag\b|vom\b|"
    r"montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonnabend|sonntag|"
    # Abgekürzte Wochentage stehen auf vielen Formblättern direkt vor dem
    # Datum ("Sa. 06.04.2024"). Der Punkt hält die Abkürzung von Wörtern wie
    # "Modell" oder "Sockel" fern.
    r"(mo|di|mi|do|fr|sa|so)\.)",
    re.IGNORECASE,
)

WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag",
              "Freitag", "Samstag", "Sonntag")


def wochentag(tag: date) -> str:
    """"Montag" … "Sonntag" — für Anzeige und Dateinamen."""
    return WOCHENTAGE[tag.weekday()]


def woche_um(tag: date, tage: int = 5) -> list[date]:
    """Die Arbeitswoche, in der ``tag`` liegt — standardmäßig Montag bis Freitag."""
    montag = tag - timedelta(days=tag.weekday())
    return [montag + timedelta(days=i) for i in range(tage)]


def _als_datum(tag: str, monat: str, jahr: str) -> date | None:
    """Baut ein Datum, oder None, wenn die Zahlen keines ergeben."""
    try:
        j = int(jahr)
        if len(jahr) == 2:
            # Zweistellig: 26 -> 2026. Bauberichte sind nie aus dem letzten
            # Jahrhundert, deshalb ohne Rückblick-Fenster.
            j += 2000
        if not (JAHR_VON <= j <= JAHR_BIS):
            return None
        return date(j, int(monat), int(tag))
    except ValueError:
        return None


def daten_in_text(text: str) -> list[date]:
    """Alle plausiblen Datumsangaben eines Textes, in Lesereihenfolge.

    Doppelte werden zusammengefasst; die Reihenfolge bleibt erhalten, weil
    weiter oben stehende Angaben eher das Berichtsdatum sind.
    """
    gefunden: list[date] = []
    for muster in (_DEUTSCH, _KOMPAKT, _HALB_VORNE, _HALB_HINTEN):
        for treffer in muster.finditer(text):
            d = _als_datum(treffer.group("tag"), treffer.group("monat"),
                           treffer.group("jahr"))
            if d and d not in gefunden:
                gefunden.append(d)
    for treffer in _ISO.finditer(text):
        d = _als_datum(treffer.group("tag"), treffer.group("monat"),
                       treffer.group("jahr"))
        if d and d not in gefunden:
            gefunden.append(d)
    return gefunden


def datum_der_seite(text: str, erlaubt: set[date] | None = None) -> date | None:
    """Das Berichtsdatum einer einzelnen Seite — oder None.

    Reihenfolge der Regeln:

    1. Eine Zeile mit einem Datumswort ("Datum:", "Freitag, …", "Bautag") und
       genau einem Datum darin gewinnt. Das ist der Kopf des Formulars.
    2. Sonst das erste Datum der Seite.
    3. Ist ein Zeitraum vorgegeben (``erlaubt``), zählen nur Daten daraus.
       Das schließt Vertragsfristen und Wettertabellen zuverlässig aus, die
       sonst gern als Berichtsdatum durchgehen.
    """
    zeilen = text.splitlines()

    def zulaessig(kandidaten: list[date]) -> list[date]:
        if erlaubt is None:
            return kandidaten
        return [d for d in kandidaten if d in erlaubt]

    # 1. Datumszeilen zuerst, von oben nach unten.
    for zeile in zeilen:
        if not _DATUMSWORTE.search(zeile):
            continue
        passende = zulaessig(daten_in_text(zeile))
        if len(passende) == 1:
            return passende[0]
        if passende:
            # Mehrere in einer Zeile ("vom 03.08. bis 07.08.") — das ist ein
            # Zeitraum, kein Tag. Nicht raten.
            continue

    # 2. Erstes zulässiges Datum irgendwo auf der Seite.
    passende = zulaessig(daten_in_text(text))
    if passende:
        return passende[0]

    # 3. Letzte Stufe: Tag und Monat ohne brauchbares Jahr. Nur mit Zeitraum.
    return _aus_tag_monat(text, erlaubt)


def _aus_tag_monat(text: str, erlaubt: set[date] | None) -> date | None:
    """Rettet ein Datum, dessen Jahreszahl die Texterkennung verlesen hat.

    Auf einem gescannten Formblatt stand "Do. 04.04 9024" — Tag und Monat
    richtig, das Jahr zu Unsinn geworden. Solange ein Zeitraum vorgegeben ist,
    lässt sich daraus genau ein Tag ableiten, und das ist keine Rateleistung,
    sondern eine Schlussfolgerung: Im Zeitraum gibt es den 4. April nur einmal.

    Ohne Zeitraum passiert hier nichts — dann wäre es tatsächlich geraten.
    Ebenso, wenn die Zeile kein Datumswort trägt oder mehrere Tage in Frage
    kämen.
    """
    if not erlaubt:
        return None

    for zeile in text.splitlines():
        if not _DATUMSWORTE.search(zeile):
            continue
        kandidaten: list[date] = []
        for treffer in _TAG_MONAT.finditer(zeile):
            tag, monat = int(treffer.group("tag")), int(treffer.group("monat"))
            passend = [d for d in erlaubt if d.day == tag and d.month == monat]
            if len(passend) == 1 and passend[0] not in kandidaten:
                kandidaten.append(passend[0])
        if len(kandidaten) == 1:
            return kandidaten[0]
    return None


def tagesabschnitte(text: str,
                    erlaubt: set[date] | None = None) -> list[tuple[date, str]]:
    """Teilt eine Seite, auf der MEHRERE Tage stehen, in Abschnitte je Tag.

    Manche Firmen schicken die ganze Woche als fortlaufenden Text: mehrere
    Tagesberichte untereinander auf einem Blatt. Seitenweise zuzuordnen reicht
    dann nicht — hier wird innerhalb der Seite geschnitten.

    Geschnitten wird an Zeilen, die den Tag ansagen. Was als Ansage zählt, ist
    bewusst eng gefasst, sonst beginnt bei jedem „Nachtrag vom 12.01." ein
    neuer Abschnitt:

    * Ist ein Zeitraum vorgegeben, muss das Datum darin liegen.
    * Sonst muss die Zeile ein Datumswort tragen ("Datum", "Bautag",
      ein Wochentag).

    Rückgabe: leere Liste, wenn die Seite nur einen Tag enthält — dann ist die
    seitenweise Zuordnung richtig und es gibt nichts zu schneiden.
    """
    zeilen = text.splitlines()
    marken: list[tuple[int, date]] = []

    for nummer, zeile in enumerate(zeilen):
        kandidaten = daten_in_text(zeile)
        if erlaubt is not None:
            kandidaten = [d for d in kandidaten if d in erlaubt]
        elif not _DATUMSWORTE.search(zeile):
            continue
        if len(kandidaten) == 1:
            marken.append((nummer, kandidaten[0]))

    # Aufeinanderfolgende Marken mit demselben Tag sind eine Wiederholung
    # (Kopf- und Fußzeile derselben Tagesseite), kein neuer Abschnitt.
    entprellt: list[tuple[int, date]] = []
    for nummer, tag in marken:
        if entprellt and entprellt[-1][1] == tag:
            continue
        entprellt.append((nummer, tag))

    if len({tag for _, tag in entprellt}) < 2:
        return []

    abschnitte: list[tuple[date, str]] = []
    for i, (start, tag) in enumerate(entprellt):
        ende = entprellt[i + 1][0] if i + 1 < len(entprellt) else len(zeilen)
        abschnitt = "\n".join(zeilen[start:ende]).strip()
        if abschnitt:
            abschnitte.append((tag, abschnitt))

    # Derselbe Tag kann mehrfach vorkommen (Unterbrechung durch einen anderen
    # Tag und zurück) — zusammenfassen, Reihenfolge behalten.
    zusammen: dict[date, list[str]] = {}
    for tag, abschnitt in abschnitte:
        zusammen.setdefault(tag, []).append(abschnitt)
    return [(tag, "\n\n".join(teile)) for tag, teile in zusammen.items()]


@dataclass
class Seitenfund:
    """Eine Seite einer hochgeladenen Datei und der Tag, der darauf steht."""

    #: Pfad der Quelldatei, relativ oder absolut — wird nur durchgereicht.
    datei: str
    #: 1-basiert, wie in einem PDF-Betrachter.
    seite: int
    datum: date | None
    #: Warum dieses Datum: "kopf" (auf der Seite gefunden),
    #: "fortsetzung" (von der Seite davor übernommen),
    #: "abschnitt" (mehrere Tage auf einer Seite, hier ausgeschnitten),
    #: "" (nichts gefunden).
    herkunft: str = ""
    #: Nur bei "abschnitt": der Text dieses Tages. Aus ihm wird beim Erzeugen
    #: eine eigene Textdatei, weil sich ein halbes Blatt nicht schneiden lässt.
    abschnitt: str | None = None


@dataclass
class Tagesblock:
    """Alle Seiten eines Tages, über alle hochgeladenen Dateien hinweg."""

    datum: date | None
    #: Datei -> Seitenzahlen (1-basiert, aufsteigend)
    seiten_je_datei: dict[str, list[int]] = field(default_factory=dict)

    @property
    def anzahl_seiten(self) -> int:
        return sum(len(s) for s in self.seiten_je_datei.values())

    @property
    def dateien(self) -> list[str]:
        return list(self.seiten_je_datei)


#: Auflösung für das Nachlesen gescannter Seiten. 200 dpi ist der Punkt, ab
#: dem die Windows-Texterkennung Formblätter zuverlässig liest.
OCR_DPI = 200

#: Mehr Seiten als das per Texterkennung nachzulesen dauert zu lange für einen
#: Web-Aufruf. Ein Wochenpaket hat fünf bis zehn Seiten.
OCR_MAX_SEITEN = 30


def _seiten_per_ocr(pdf_pfad: Path, nummern: list[int]) -> dict[int, str]:
    """Liest die genannten Seiten (0-basiert) mit der Windows-Texterkennung.

    Das ist der Weg für gescannte Berichte: Ein PDF, in dem jede Seite ein
    Bild ist, hat keinen Text — und ohne Text kein Datum. Gerendert wird nur,
    was wirklich leer war; Seiten mit Textebene bleiben unangetastet.
    """
    from app.services import windows_ocr

    if not nummern or not windows_ocr.verfuegbar():
        return {}

    import tempfile

    try:
        import pypdfium2 as pdfium
    except ImportError:
        return {}

    ausgewaehlt = nummern[:OCR_MAX_SEITEN]
    try:
        dokument = pdfium.PdfDocument(str(pdf_pfad))
    except Exception:
        return {}

    with tempfile.TemporaryDirectory(prefix="hpp-ocr-seiten-") as ordner:
        basis = Path(ordner)
        bilder: list[Path] = []
        try:
            for nummer in ausgewaehlt:
                bild = basis / f"s{nummer}.png"
                dokument[nummer].render(scale=OCR_DPI / 72).to_pil().save(bild)
                bilder.append(bild)
        except Exception:
            return {}
        finally:
            dokument.close()

        texte = windows_ocr.text_aus_bildern(bilder)

    return {nummer: text for nummer, text in zip(ausgewaehlt, texte)}


def seiten_lesen(pdf_pfad: Path) -> list[str]:
    """Der Text jeder Seite eines PDFs. Leere Liste, wenn es nicht lesbar ist.

    Seiten ohne Textebene werden per Windows-Texterkennung nachgelesen — sonst
    wäre ein gescanntes Wochenpaket für die App stumm und jeder Tag müsste von
    Hand zugeordnet werden.

    Kein harter Fehler: Eine kaputte oder verschlüsselte Datei soll das ganze
    Wochenpaket nicht aufhalten — sie landet dann eben unter "Tag unbekannt".
    """
    import pdfplumber

    try:
        with pdfplumber.open(pdf_pfad) as pdf:
            seiten = [(seite.extract_text() or "") for seite in pdf.pages]
    except Exception:
        return []

    leer = [i for i, text in enumerate(seiten) if not text.strip()]
    if leer:
        for nummer, erkannt in _seiten_per_ocr(pdf_pfad, leer).items():
            if erkannt.strip():
                seiten[nummer] = erkannt

    return seiten


def finde_seitendaten(dateien: list[Path],
                      erlaubt: set[date] | None = None) -> list[Seitenfund]:
    """Bestimmt für jede Seite jeder Datei den Tag.

    Fortsetzungsseiten: Hat eine Seite kein eigenes Datum, die vorige Seite
    derselben Datei aber schon, gilt der Tag der vorigen Seite. So bleiben
    zweiseitige Tagesberichte zusammen. Vor der ersten datierten Seite wird
    nichts übernommen — dort ist wirklich unbekannt, welcher Tag gemeint ist.
    """
    funde: list[Seitenfund] = []

    for pfad in dateien:
        endung = pfad.suffix.lower()
        name = str(pfad)

        if endung not in TEXT_ENDUNGEN:
            # Bild oder unbekanntes Format: eine "Seite", kein lesbares Datum.
            funde.append(Seitenfund(datei=name, seite=1, datum=None))
            continue

        seiten = seiten_lesen(pfad)
        if not seiten:
            funde.append(Seitenfund(datei=name, seite=1, datum=None))
            continue

        letztes: date | None = None
        for nummer, text in enumerate(seiten, start=1):
            # Zuerst die Frage, ob auf DIESER Seite mehrere Tage stehen.
            # Firmen, die die ganze Woche als fortlaufenden Text schicken,
            # wären sonst auf einen einzigen Tag zusammengefallen.
            geteilt = tagesabschnitte(text, erlaubt)
            if geteilt:
                for tag, abschnitt in sorted(geteilt, key=lambda x: x[0]):
                    funde.append(
                        Seitenfund(name, nummer, tag, "abschnitt", abschnitt)
                    )
                letztes = max(tag for tag, _ in geteilt)
                continue

            gefunden = datum_der_seite(text, erlaubt)
            if gefunden is not None:
                letztes = gefunden
                funde.append(Seitenfund(name, nummer, gefunden, "kopf"))
            elif letztes is not None:
                funde.append(Seitenfund(name, nummer, letztes, "fortsetzung"))
            else:
                funde.append(Seitenfund(name, nummer, None, ""))

    return funde


def gruppiere_nach_tag(funde: list[Seitenfund]) -> list[Tagesblock]:
    """Fasst die Seitenfunde zu Tagesblöcken zusammen, aufsteigend nach Datum.

    Seiten ohne erkanntes Datum kommen als ein Block mit ``datum=None`` ans
    Ende — sie sind die Arbeit, die der Mensch noch zuordnen muss.
    """
    nach_tag: dict[date | None, Tagesblock] = {}

    for fund in funde:
        block = nach_tag.get(fund.datum)
        if block is None:
            block = Tagesblock(datum=fund.datum)
            nach_tag[fund.datum] = block
        block.seiten_je_datei.setdefault(fund.datei, []).append(fund.seite)

    mit_datum = sorted(
        (b for b in nach_tag.values() if b.datum is not None),
        key=lambda b: b.datum,
    )
    ohne_datum = [b for b in nach_tag.values() if b.datum is None]
    return mit_datum + ohne_datum


def teile_wochenpaket(dateien: list[Path],
                      erlaubt: set[date] | None = None) -> list[Tagesblock]:
    """Der übliche Weg: Dateien hinein, Tagesblöcke heraus."""
    return gruppiere_nach_tag(finde_seitendaten(dateien, erlaubt))


def schreibe_teil_pdf(quelle: Path, seiten: list[int], ziel: Path) -> Path:
    """Schreibt die genannten Seiten (1-basiert) als eigenes PDF.

    Damit muss die vorhandene Extraktion nichts von Wochenpaketen wissen: Sie
    bekommt eine Datei, die nur den einen Tag enthält, und arbeitet wie immer.
    Umfasst die Auswahl bereits das ganze Dokument, wird nur kopiert — das
    spart das Neuschreiben und erhält die Datei unverändert.
    """
    import shutil

    import pypdfium2 as pdfium

    ziel.parent.mkdir(parents=True, exist_ok=True)

    quell_dokument = pdfium.PdfDocument(str(quelle))
    try:
        gesamt = len(quell_dokument)
        gewaehlt = sorted({s for s in seiten if 1 <= s <= gesamt})
        if not gewaehlt or len(gewaehlt) == gesamt:
            shutil.copy2(quelle, ziel)
            return ziel

        neu = pdfium.PdfDocument.new()
        neu.import_pages(quell_dokument, [s - 1 for s in gewaehlt])
        neu.save(str(ziel))
        return ziel
    finally:
        quell_dokument.close()
