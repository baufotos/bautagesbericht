"""Gliederung des Projektberichts und die Nummerierung leerer Kapitel.

WARUM DAS EIN EIGENES MODUL IST
===============================
Das ist die Stelle, an der die Word-Vorlage des Büros bisher scheitert. Im
Referenzbericht (``BoB- Projektbericht Nr.3``) steht im Inhaltsverzeichnis
„2.2 Fortschritt“, im Text folgt auf 2.1 aber direkt „2.2 Verzögerungen“ —
das leere Kapitel wurde von Hand gelöscht, die folgenden nachnummeriert, das
Verzeichnis aber nicht. Dasselbe am Ende: Das Verzeichnis sagt „7 Fotos“ und
„8 Anlagen“, der Text „6 Fotos“ und „7 Anlagen“.

Deshalb wird hier **einmal** entschieden, welche Kapitel erscheinen und welche
Nummer sie tragen. Text und Verzeichnis lesen anschließend dieselbe Liste —
sie können gar nicht mehr auseinanderlaufen. Ohne Word, ohne XML, ohne
Datenbank: eine reine Funktion, die sich prüfen lässt.

NEUE KAPITEL ERGÄNZEN
=====================
Einen Eintrag in ``GLIEDERUNG`` hinzufügen — mehr nicht. Das Formular baut
sich daraus auf, der Erzeuger ebenso, und die Nummerierung stimmt von selbst.
Der ``schluessel`` ist der bleibende Name (er steht so in der Datenbank);
Titel und Reihenfolge dürfen sich ändern, ohne dass alte Berichte kaputtgehen.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: Was ein Kapitel aufnimmt. Steuert Formular und Erzeuger.
#:
#:   text            Fließtext (Standardfall)
#:   baubegehungen   Liste: Datum, Teilnehmer, Firma
#:   besprechungen   Liste: Bezeichnung, Rhythmus, Uhrzeit
#:   sollist         Tabelle: Bezeichnung, SOLL, IST, Verzug
#:   fotos           Fotos mit Bildunterschrift
ART_TEXT = "text"
ART_BAUBEGEHUNGEN = "baubegehungen"
ART_BESPRECHUNGEN = "besprechungen"
ART_SOLLIST = "sollist"
ART_FOTOS = "fotos"


@dataclass(frozen=True)
class Unterkapitel:
    schluessel: str
    titel: str
    art: str = ART_TEXT
    #: Erscheint auch ohne Inhalt.
    #:
    #: Nur für die vier Punkte der zusammenfassenden Bewertung (1.1–1.4): Sie
    #: sind im Original auch dann abgedruckt, wenn nichts darunter steht — die
    #: Leerstelle ist dort die Aussage („zu Resumée gibt es diesen Monat
    #: nichts“). Alle anderen Kapitel verschwinden, wenn sie leer bleiben.
    immer_zeigen: bool = False


@dataclass(frozen=True)
class Hauptkapitel:
    schluessel: str
    titel: str
    unterkapitel: tuple[Unterkapitel, ...] = ()
    #: Kapitel 1 trägt keine eigene Überschrift — dort steht die Titelzeile
    #: „Zusammenfassende Bewertung / Monatsbericht Nr: n“.
    ohne_ueberschrift: bool = False
    #: Nimmt selbst Inhalt auf (Kapitel ohne Unterkapitel, z. B. „Sonstiges“).
    art: str = ART_TEXT


GLIEDERUNG: tuple[Hauptkapitel, ...] = (
    Hauptkapitel(
        "bewertung", "Zusammenfassende Bewertung", ohne_ueberschrift=True,
        unterkapitel=(
            Unterkapitel("resumee", "Resumée", immer_zeigen=True),
            Unterkapitel("baubegehungen", "Baubegehungen",
                         art=ART_BAUBEGEHUNGEN, immer_zeigen=True),
            Unterkapitel("besprechungen", "Besprechungen",
                         art=ART_BESPRECHUNGEN, immer_zeigen=True),
            Unterkapitel("sonst_erwaehnenswert", "Sonst erwähnenswert",
                         immer_zeigen=True),
        ),
    ),
    Hauptkapitel(
        "ablauf", "Ablauf",
        unterkapitel=(
            Unterkapitel("meilensteine", "Meilensteine"),
            Unterkapitel("soll_ist", "SOLL-IST-Vergleich", art=ART_SOLLIST),
            Unterkapitel("fortschritt", "Fortschritt"),
            Unterkapitel("verzoegerungen", "Verzögerungen"),
            Unterkapitel("vorkommnisse", "Vorkommnisse"),
            Unterkapitel("naechste_schritte", "Nächste Schritte"),
        ),
    ),
    Hauptkapitel(
        "planung", "Planung",
        unterkapitel=(
            Unterkapitel("planung_architektur", "Architektur"),
            Unterkapitel("planung_haustechnik", "Haustechnik"),
            Unterkapitel("planung_nutzertechnik", "Nutzertechnik"),
            Unterkapitel("planung_einrichtung", "Einrichtung"),
            Unterkapitel("planung_aussenanlagen", "Außenanlagen und Erschließung"),
            Unterkapitel("planung_entscheidungen",
                         "Entscheidungen, Bemusterungen, Änderungen"),
        ),
    ),
    Hauptkapitel(
        "ausfuehrung", "Ausführung",
        unterkapitel=(
            Unterkapitel("aus_baulogistik", "Baulogistik"),
            Unterkapitel("aus_abbruch", "Abbruch"),
            Unterkapitel("aus_rohbau", "Rohbau"),
            Unterkapitel("aus_aussenhuelle", "Außenhülle"),
            Unterkapitel("aus_haustechnik", "Haustechnik / Brandschutz"),
            Unterkapitel("aus_ausbau", "Ausbau"),
            Unterkapitel("aus_nutzertechnik", "Nutzertechnik"),
            Unterkapitel("aus_einrichtung", "Einrichtung"),
            Unterkapitel("aus_aussenanlagen", "Außenanlagen"),
            Unterkapitel("aus_maengel", "Mängel"),
            Unterkapitel("aus_zustandsfeststellungen",
                         "Zustandsfeststellungen und Übergaben"),
        ),
    ),
    Hauptkapitel(
        "aenderungen", "Änderungen",
        unterkapitel=(
            Unterkapitel("aend_quantitaeten", "Änderung Quantitäten"),
            Unterkapitel("aend_qualitaeten", "Änderungen Qualitäten"),
            Unterkapitel("aend_termine", "Änderungen Termine"),
        ),
    ),
    Hauptkapitel("sonstiges", "Sonstiges"),
    Hauptkapitel("fotos", "Fotos", art=ART_FOTOS),
    Hauptkapitel("anlagen", "Anlagen"),
)

#: Alle Schlüssel in Reihenfolge — praktisch für Formular und Prüfungen.
ALLE_SCHLUESSEL: tuple[str, ...] = tuple(
    s
    for haupt in GLIEDERUNG
    for s in ((haupt.schluessel,) if not haupt.unterkapitel else ())
    + tuple(u.schluessel for u in haupt.unterkapitel)
)


@dataclass
class GerendertesKapitel:
    """Ein Kapitel, wie es im Dokument erscheint."""

    nummer: str          # "2" oder "2.3"
    titel: str
    ebene: int           # 1 oder 2
    schluessel: str
    art: str
    inhalt: Any          # Text oder Liste, je nach art
    #: Nur Überschrift, kein eigener Inhalt (Hauptkapitel mit Unterkapiteln).
    nur_ueberschrift: bool = False


def ist_leer(wert: Any) -> bool:
    """Gilt ein Kapitelinhalt als leer?

    Leerzeichen und Zeilenumbrüche zählen nicht als Inhalt — sonst würde ein
    versehentlich gedrücktes Enter ein Kapitel im Bericht auftauchen lassen.
    """
    if wert is None:
        return True
    if isinstance(wert, str):
        return not wert.strip()
    if isinstance(wert, (list, tuple, dict, set)):
        return len(wert) == 0
    return False


def nummeriere(inhalte: Mapping[str, Any]) -> list[GerendertesKapitel]:
    """Bestimmt Reihenfolge und Nummern der Kapitel, die erscheinen.

    Regeln, in dieser Reihenfolge:

    1. Ein **Unterkapitel** erscheint, wenn es Inhalt hat — oder wenn es als
       ``immer_zeigen`` gekennzeichnet ist (1.1–1.4).
    2. Ein **Hauptkapitel** erscheint, wenn es eigenen Inhalt hat oder
       mindestens ein Unterkapitel erscheint. Sonst fällt es ganz weg.
    3. Nummeriert wird **nach** dem Weglassen, fortlaufend ab 1 — genau das,
       was im Original von Hand passiert und schiefgeht.

    Kapitel 1 („Zusammenfassende Bewertung“) bekommt keine eigene Überschrift,
    zählt aber als Nummer 1 mit; seine Unterpunkte heißen deshalb 1.1 bis 1.4.
    """
    ergebnis: list[GerendertesKapitel] = []
    haupt_nummer = 0

    for haupt in GLIEDERUNG:
        sichtbare_unter = [
            u for u in haupt.unterkapitel
            if u.immer_zeigen or not ist_leer(inhalte.get(u.schluessel))
        ]
        eigener_inhalt = inhalte.get(haupt.schluessel)
        hat_eigenen = not haupt.unterkapitel and not ist_leer(eigener_inhalt)

        if not sichtbare_unter and not hat_eigenen:
            continue

        haupt_nummer += 1
        if not haupt.ohne_ueberschrift:
            ergebnis.append(GerendertesKapitel(
                nummer=str(haupt_nummer),
                titel=haupt.titel,
                ebene=1,
                schluessel=haupt.schluessel,
                art=haupt.art,
                inhalt=eigener_inhalt if hat_eigenen else None,
                nur_ueberschrift=bool(haupt.unterkapitel),
            ))

        for lauf, unter in enumerate(sichtbare_unter, start=1):
            ergebnis.append(GerendertesKapitel(
                nummer=f"{haupt_nummer}.{lauf}",
                titel=unter.titel,
                ebene=2,
                schluessel=unter.schluessel,
                art=unter.art,
                inhalt=inhalte.get(unter.schluessel),
            ))

    return ergebnis


def inhaltsverzeichnis(kapitel: list[GerendertesKapitel]) -> list[GerendertesKapitel]:
    """Die Einträge fürs Verzeichnis — alles ab Kapitel 2.

    Kapitel 1 steht im Original nicht im Verzeichnis: Es ist der Inhalt der
    ersten Seite, und darunter beginnt „Weiterer Inhalt:“. Genau diese Liste
    wird abgedruckt — dieselbe Quelle wie der Text, deshalb stimmen die
    Nummern zusammen.

    Verglichen wird der Nummernstamm und nicht der Anfang der Zeichenkette:
    Sonst fiele bei genügend Kapiteln auch „10.1“ heraus.
    """
    return [k for k in kapitel if k.nummer.split(".")[0] != "1"]
