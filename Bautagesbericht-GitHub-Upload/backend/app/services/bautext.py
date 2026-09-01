"""Gelesenen Text von Baustellendokumenten geraderücken.

WOZU
====
Jede Texterkennung verwechselt dieselben Zeichen: ``O`` und ``0``, ``l`` und
``1``, ``G`` und ``6``. Auf einer Rechnung fällt das kaum auf. Auf einem
Bautagesbericht steht dann ``3.0G.`` statt ``3.OG.`` und ``406. Ost`` statt
``4.OG. Ost`` — und weil Geschossangaben in fast jeder Leistungszeile
vorkommen, zieht sich der Fehler durch den ganzen Bericht, der an den
Bauherrn geht.

Das lässt sich nicht durch bessere Erkennung lösen, sondern nur durch Wissen
über die Sprache der Baustelle: Nach einer Ziffer und einem Punkt kommt ein
Geschoss, kein Nullsechs.

WAS HIER NICHT PASSIERT
=======================
Es wird nichts geraten. Jede Regel greift nur in einer Umgebung, in der die
richtige Lesart eindeutig ist — ``4.0G`` ist zweifelsfrei ``4.OG``, ``40G``
allein wäre es nicht und bleibt deshalb unangetastet.
"""

from __future__ import annotations

import re

# ─────────────────────────────────────────────────────────────────────────────
# Geschosse
#
# Die häufigste Verwechslung überhaupt. Geschrieben steht "4.OG", gelesen wird
# "4.0G", "4.O6", "406" oder "4 OG".
# ─────────────────────────────────────────────────────────────────────────────

#: "4.0G." / "4.O6." / "4,0g" → "4.OG."   (Ziffer, Trenner, zwei Zeichen)
_OG = re.compile(r"\b(\d)\s*[.,]\s*[O0o]\s*[G6g]\b")
#: "4.U6." / "1.Ug" → "1.UG."
_UG = re.compile(r"\b(\d)\s*[.,]\s*[U u]\s*[G6g]\b")
#: "406." mitten im Text, wo ein Geschoss stehen muss: Ziffer + "06" + Punkt,
#: gefolgt von einem Wort. Eine echte Zahl 406 stünde nicht vor "Ost".
_OG_KOMPAKT = re.compile(r"\b(\d)0[6G]\.\s+(?=[A-ZÄÖÜ])")
#: "EG" verwechselt sich mit "E6".
_EG = re.compile(r"\b[E e][6]\b")
#: Kellergeschoss: "UG" als "U6".
_UG_KURZ = re.compile(r"\b[U u][6]\b")

# ─────────────────────────────────────────────────────────────────────────────
# Weitere Kürzel der Baustelle
# ─────────────────────────────────────────────────────────────────────────────

#: Treppenhaus wird als "Trh.", "TrH.", "Tr.H." geschrieben und gern als
#: "TrR.", "Trk." gelesen.
_TREPPENHAUS = re.compile(r"\bTr\s*[.,]?\s*[hHkKRr]\s*[.,]", re.I)

#: Achsangaben "1-4/A-D" werden mit Leerzeichen zerrissen.
_ACHSE = re.compile(r"\b(\d+)\s*-\s*(\d+)\s*/\s*([A-Z])\s*-\s*([A-Z])\b")

#: Uhrzeiten in der Schreibweise der Baustelle: "7oo" / "7°°" = 7:00.
_UHR_HOCH = re.compile(r"\b(\d{1,2})\s*[°ºo]{2}\b")

#: Temperaturen: "H 8' T 3°" — das Minutenzeichen ist ein Gradzeichen.
_GRAD = re.compile(r"(?<=\d)\s*['´`′]")


def geschosse(text: str) -> str:
    """Geschossangaben geraderücken. Der häufigste Erkennungsfehler."""
    text = _OG.sub(lambda m: f"{m.group(1)}.OG", text)
    text = _UG.sub(lambda m: f"{m.group(1)}.UG", text)
    text = _OG_KOMPAKT.sub(lambda m: f"{m.group(1)}.OG. ", text)
    text = _EG.sub("EG", text)
    text = _UG_KURZ.sub("UG", text)
    return text


def kuerzel(text: str) -> str:
    """Übrige Kürzel der Baustelle geraderücken."""
    text = _TREPPENHAUS.sub("Trh.", text)
    text = _ACHSE.sub(lambda m: f"{m.group(1)}-{m.group(2)}/{m.group(3)}-{m.group(4)}", text)
    text = _UHR_HOCH.sub(lambda m: f"{m.group(1)}:00", text)
    text = _GRAD.sub("°", text)
    return text


def geraderuecken(text: str) -> str:
    """Alles zusammen — der Aufruf, den die Erkennungswege benutzen."""
    if not text:
        return ""
    text = geschosse(text)
    text = kuerzel(text)
    # Leerzeichen vor Satzzeichen und doppelte Leerzeichen: entsteht beim
    # Zusammensetzen erkannter Wortkästchen.
    text = re.sub(r" +([,.;:!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Vordruck oder Inhalt?
#
# Bei einem handschriftlich ausgefüllten Formular liest die Windows-Erkennung
# den **gedruckten** Vordruck sauber und von der Handschrift nichts. Das
# Ergebnis sieht dann aus wie ein Erkennungserfolg — es ist aber die leere
# Vorlage. Genau das ist bei einem eingescannten Bautagebuch in Schreibschrift
# passiert: Im Bericht stand als "Leistung" die Liste "Polier · Werkpolier ·
# Vorarbeiter · Maurer …".
#
# Ein stiller Fehlgriff dieser Art ist schlimmer als eine offene Fehlmeldung:
# Niemand prüft ein Feld nach, das gefüllt aussieht.
# ─────────────────────────────────────────────────────────────────────────────

#: Wörter, die auf jedem leeren Bautagebuch-Vordruck stehen. Sie sagen nichts
#: darüber, was an diesem Tag gearbeitet wurde.
VORDRUCK_WOERTER = frozenset({
    # Riedel-Bautagebuch
    "bautagebuch", "blatt-nr", "baustelle", "bau-nr", "arbeitszeit",
    "wetter", "temperatur", "niederschlag", "regenschauer", "dauerregen",
    "schneefall", "luftbewegung", "mäßiger", "sturm",
    "arbeitskräfte", "polier", "werkpolier", "vorarbeiter", "maurer",
    "zimmerer", "betonbauer", "helfer", "maschinenführer", "azubis",
    "geräte", "baustoffe", "radlader", "bagger", "kräne", "kompressor",
    "verdichtungsgeräte", "lkw", "betonstahl", "beton",
    "nachunternehmer", "anzahl", "sonstiges", "besuche",
    "ausgeführte", "arbeiten", "bauleiter", "bauherr",
    # allgemeine Formblatt-Möblierung
    "formblatt", "bautagesbericht", "ident-nr", "kommission", "bauvorhaben",
    "abschnitt", "datum", "witterung", "sonne", "regen", "frost", "wind",
    "schnee", "bewölkt", "unterschrift", "bemerkungen", "seite", "firma",
    "gewerk", "uhrzeit", "personen", "name", "monteur",
})

#: Zeichen, die für Inhalt sprechen: eine Jahreszahl, eine Geschossangabe,
#: eine Uhrzeit — Dinge, die auf einem leeren Vordruck nicht stehen.
_INHALTSSPUR = re.compile(
    r"\b(20\d{2}|\d{1,2}\.\d{1,2}\.\d{2,4}|\d\.[OU]G|\d{1,2}:\d{2})\b"
)


def _woerter(text: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-zÄÖÜäöüß][\w\-äöüßÄÖÜ]{2,}", text or "")]


def vordruckanteil(text: str) -> float:
    """Wie viel des gelesenen Textes ist bloße Formularbeschriftung? 0.0–1.0.

    Ein voll ausgefülltes Formblatt landet bei etwa 0,4 bis 0,6 — der Vordruck
    ist ja mitgedruckt. Eine Seite, von der nur der Vordruck gelesen wurde,
    liegt über 0,9.
    """
    woerter = _woerter(text)
    if not woerter:
        return 1.0
    vordruck = sum(1 for w in woerter if w.lower().strip(":.") in VORDRUCK_WOERTER)
    return vordruck / len(woerter)


def nur_vordruck(text: str, schwelle: float = 0.82) -> bool:
    """Wurde von diesem Blatt **nur** die leere Vorlage gelesen?

    Zwei Bedingungen müssen zusammenkommen, damit hier nicht versehentlich ein
    kurzer, aber echter Text verworfen wird:

    * Fast alles Gelesene ist Formularbeschriftung, **und**
    * es findet sich keine einzige Inhaltsspur (Datum, Geschoss, Uhrzeit).
    """
    if not (text or "").strip():
        return True
    if _INHALTSSPUR.search(text):
        return False
    return vordruckanteil(text) >= schwelle


#: Ab diesem mittleren Vordruckanteil über alle Seiten gilt ein Dokument als
#: "nur Vorlage gelesen". Deutlich niedriger angesetzt als bei der Einzelseite,
#: weil hier zusätzlich verlangt wird, dass auf KEINER Seite ein Datum stand.
DOKUMENT_SCHWELLE = 0.65


def handschrift_unlesbar(seiten: list[str], datum_gefunden: bool) -> bool:
    """Ist von diesem Dokument nur der gedruckte Vordruck angekommen?

    Warum die Entscheidung auf das ganze Dokument gehört und nicht auf die
    einzelne Seite: Auf jedem Blatt steht der Firmenname des Vordrucks — beim
    Riedel-Bautagebuch das Logo "Riedel Bau". Seitenweise gerechnet drückt das
    den Vordruckanteil unter jede brauchbare Schwelle, obwohl von der
    Handschrift nichts gelesen wurde. Über zwölf Seiten hinweg ist das Bild
    dagegen eindeutig.

    ``datum_gefunden`` ist das entscheidende Gegenargument: Wo ein Datum
    gelesen wurde, ist Handschrift oder Maschinenschrift angekommen — dann
    wird nichts verworfen, egal wie viel Vordruck danebensteht.
    """
    if datum_gefunden:
        return False
    gefuellt = [s for s in seiten if (s or "").strip()]
    if not gefuellt:
        return True
    mittel = sum(vordruckanteil(s) for s in gefuellt) / len(gefuellt)
    return mittel >= DOKUMENT_SCHWELLE


#: Klartext für die Oberfläche, wenn nur der Vordruck gelesen wurde. Steht
#: hier und nicht verstreut im Code, weil dieselbe Erklärung an drei Stellen
#: gebraucht wird: Wochenanalyse, Einzeldatei und Protokoll.
def unlesbar_hinweis(dateiname: str, wo_der_schluessel: str) -> str:
    return (
        f"Von „{dateiname}“ konnte nur der gedruckte Vordruck gelesen werden — "
        "die ausgefüllten Felder nicht. Das ist der Normalfall bei "
        "Schreibschrift: Die Windows-Texterkennung liest Druckbuchstaben, "
        "verbundene Handschrift kann sie nicht. Dafür wird ein "
        "Anthropic-Schlüssel gebraucht (" + wo_der_schluessel + "). "
        "Ohne ihn bitte die Angaben von Hand eintragen."
    )
