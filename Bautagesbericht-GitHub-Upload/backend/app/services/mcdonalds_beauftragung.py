"""Die Einzelabrufe an die Subplaner — Betreff, Text und Ablageort.

WAS HIER ENTSTEHT
=================
Für jeden Subplaner einer Phase ein fertiges Schreiben, so wie das Büro es
schickt. Beispiel Nievern, Phase 1, Kocks:

    Betreff: 260825_NSO_NIV_Beauftragung Phase 1 KOCKS

    Sehr geehrter Herr Hömmerich,

    hiermit erteilen wir an Kocks Consult einen Einzelauftrag für die Phase 1
    gemäß ihrem Angebot vom 27.02.2026 zum genannten Projekt …

In Phase 1 sind das zwei Schreiben (Kocks und RKA), also zwei
Outlook-Entwürfe aus einem Knopfdruck.

ZWEI TEXTFASSUNGEN, WEIL DAS BÜRO ZWEI SCHREIBT
===============================================
Kocks und RKA bekommen fast denselben Brief — aber eben nur fast:

  * **Kocks** hat die Zeile „Erstellung der Projektplanung", und die Klärung
    heißt bei ihm „Klären der Aufgabenstellung/Bauordnungsrecht **durch RKA**"
    (Kocks erfährt damit, wer das liefert).
  * **RKA** hat keine Projektplanungszeile, und die Klärung heißt nur
    „Klären der Aufgabenstellung/Bauordnungsrecht" — RKA macht sie selbst.
  * Bei RKA steht der Satz „Die Ausführung … beginnt unmittelbar" direkt unter
    dem Leistungsbeginn, bei Kocks erst unter den Terminen.

Die Unterschiede sind klein, aber es sind Vertragstexte. Deshalb stehen unten
zwei **vollständige** Vorlagen und kein Baukasten, der die eine aus der
anderen zusammensetzt: Man muss sehen können, was der Subplaner liest, ohne
den Code im Kopf auszuführen. Eine dritte Fassung ist eine dritte Konstante.

WOHER DIE WERTE KOMMEN
======================
    Projekt                         Ort aus der SLS-Anfrage („Nievern")
    Leistungsbeginn                 Datum der SLS-Anfrage (21.08.2026)
    Abgabe Phase 1                  „bis zum" aus der SLS-Anfrage (04.09.2026)
    Erstellung der Projektplanung   = Abgabetermin
    Klären der Aufgabenstellung     Beauftragungsdatum + KLAERUNG_TAGE
    Angebot vom                     Stammdaten des Subplaners
    Anrede, Firmenname              Stammdaten des Subplaners

Jeder dieser Werte ist im Formular überschreibbar. Die Regeln sind Vorschlag,
nicht Gesetz — es sind Termine in einem Vertrag, und die letzte Prüfung macht
ein Mensch.

ABLAGE
======
    <STANDORTE>\\<CODE>_<Ort>\\18-GP\\12_Verträge\\02_Subplaner\\<Firmenordner>\\02_Vertrag

Der Pfad ist für alle Standorte gleich; es wechseln nur der Standortordner und
der Firmenordner (``Subplaner.ordner``, z. B. ``090_VAA_Kocks``). Dort landet
die ``.eml`` mit dem Namen des Betreffs — damit die Beauftragung im
Projektordner liegt, auch wenn sie über Outlook rausgeht.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# Feste Angaben des Büros
#
# Sie stehen in jedem Einzelabruf gleich. Als Konstanten und nicht in der
# Konfiguration: Ein Bürowechsel ist keine Einstellung, die man versehentlich
# umlegt — und wenn sich die Anschrift ändert, ändert sich der Vertragstext.
# ─────────────────────────────────────────────────────────────────────────────

AUFTRAGGEBER = "HPP Generalplanung GmbH\nZollhof 26, 40221 Düsseldorf"

#: Wer im Büro den Einzelabruf verantwortet — steht als Ansprechpartner drin.
ANSPRECHPARTNER_HPP = "Herr Ricardo da Costa"

#: Kürzel des Projekts im Betreff: 260825_**NSO**_NIV_Beauftragung …
#: ("New Store Opening", das McDonald's-Rahmenprojekt des Büros.)
PROJEKT_KUERZEL = "NSO"

#: Muster der HPP-Adresse, die bei jedem Einzelabruf in Kopie steht:
#: ``mcd-niv@hpp.com`` für Nievern. Sie wechselt mit dem Standort, nicht mit
#: der Firma — deshalb wird sie hier gebildet und nicht in den Stammdaten
#: gepflegt. Kleingeschrieben, weil Postfachnamen so vergeben werden.
HPP_KOPIE_MUSTER = "mcd-{code}@hpp.com"


def hpp_kopie(unlocode: str) -> str:
    """``mcd-niv@hpp.com`` — leer, solange kein Ortscode feststeht.

    Ohne Code keine Adresse: ``mcd-xxx@hpp.com`` wäre ein Postfach, das es
    nicht gibt, und eine Mail an eine erfundene Adresse fällt erst auf, wenn
    jemand die Unzustellbarkeit liest.
    """
    code = (unlocode or "").strip().lower()
    return HPP_KOPIE_MUSTER.format(code=code) if len(code) == 3 else ""


#: Frist für „Klären der Aufgabenstellung/Bauordnungsrecht", gerechnet ab dem
#: Beauftragungsdatum.
#:
#: ACHTUNG, BITTE PRÜFEN: Die Regel ist so hinterlegt, wie sie angegeben wurde
#: („+ 3 Tage ab Beauftragung"). Im Musterschreiben für Nievern steht als
#: Beauftragungsdatum der 25.08.2026 (Betreff „260825_…") und als Klärungstermin
#: der 31.08.2026 — das sind sechs Kalendertage, nicht drei. Möglich ist
#: also auch „+3 Werktage ab Versand" oder eine andere Bezugsgröße. Der Wert
#: ist im Formular überschreibbar, damit niemand auf diese Konstante angewiesen
#: ist, solange sie nicht bestätigt ist.
KLAERUNG_TAGE = 3

#: Die Trennzeile vor der Grußformel — steht so in den Vorlagen des Büros.
TRENNER = "………..\n"

SCHLUSS = (
    "Bitte bestätigen Sie uns den Erhalt und die Annahme dieses Einzelabrufs "
    "per E-Mail.\n"
    "\n"
    "Mit freundlichen Grüßen"
)


def _kopf(anrede: str, firma: str, phase: int, angebot_datum: str,
          projekt: str) -> str:
    """Der Teil, der in beiden Fassungen wortgleich ist."""
    return (
        f"{anrede}\n"
        f"\n"
        f"hiermit erteilen wir an {firma} einen Einzelauftrag für die "
        f"Phase {phase}\n"
        f"gemäß ihrem Angebot vom {angebot_datum} zum genannten Projekt am "
        f"angegebenen Standort.\n"
        f"\n"
        f"Auftraggeber:\n"
        f"{AUFTRAGGEBER}\n"
        f"\n"
        f"Ansprechpartner:\n"
        f"{ANSPRECHPARTNER_HPP}\n"
        f"\n"
        f"Projekt: {projekt}\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Die beiden Fassungen
#
# TEXTVARIANTEN ist die Zuordnung Kennung → Aufbaufunktion. Eine neue Fassung
# (Phase 2, weiterer Subplaner) heißt: Funktion daneben schreiben, hier
# eintragen, in den Stammdaten am Subplaner auswählen. Sonst ändert sich
# nichts — Versand, Ablage und Oberfläche kennen nur die Kennung.
# ─────────────────────────────────────────────────────────────────────────────


def _text_kocks(w: Werte) -> str:
    """Fassung Kocks: mit Projektplanung, Klärung „durch RKA"."""
    return (
        _kopf(w.anrede, w.firma, w.phase, w.angebot_datum, w.projekt)
        + f"\n"
          f"Leistungsbeginn: {w.leistungsbeginn}\n"
          f"\n"
          f"Erstellung der Projektplanung: {w.projektplanung}\n"
          f"Klären der Aufgabenstellung/Bauordnungsrecht durch RKA: "
          f"{w.klaerung}\n"
          f"\n"
          f"Die Ausführung der beauftragten Leistungen beginnt unmittelbar "
          f"mit Eingang dieser Beauftragung.\n"
          f"Abgabe Phase {w.phase}: {w.abgabe}\n"
        + TRENNER
        + "\n"
        + SCHLUSS
    )


def _text_rka(w: Werte) -> str:
    """Fassung RKA: ohne Projektplanung, Klärung ohne „durch RKA"."""
    return (
        _kopf(w.anrede, w.firma, w.phase, w.angebot_datum, w.projekt)
        + f"\n"
          f"Leistungsbeginn: {w.leistungsbeginn}\n"
          f"Die Ausführung der beauftragten Leistungen beginnt unmittelbar "
          f"mit Eingang dieser Beauftragung.\n"
          f"\n"
          f"Klären der Aufgabenstellung/Bauordnungsrecht: {w.klaerung}\n"
          f"\n"
          f"Abgabe Phase {w.phase}: {w.abgabe}\n"
        + TRENNER
        + SCHLUSS
    )


#: Kennung → Aufbaufunktion. Die Kennung steht am Subplaner in den Stammdaten.
TEXTVARIANTEN = {
    "kocks": _text_kocks,
    "rka": _text_rka,
}

#: Was in der Oberfläche zur Auswahl steht (Kennung, Beschriftung).
TEXTVARIANTEN_AUSWAHL = (
    ("kocks", "Kocks — mit „Erstellung der Projektplanung“ und „durch RKA“"),
    ("rka", "RKA — ohne Projektplanung, Klärung in eigener Verantwortung"),
)

#: Genommen, wenn am Subplaner keine gültige Fassung hinterlegt ist. Die
#: RKA-Fassung ist die schlichtere und enthält keine Aussage über Dritte.
STANDARD_VARIANTE = "rka"


@dataclass
class Werte:
    """Die eingesetzten Werte — alles schon als Text, wie es im Brief steht.

    Bewusst Text und nicht ``date``: Was hier ankommt, ist geprüft und wird
    unverändert eingesetzt. Formatiert wird eine Ebene höher (``aus_daten``),
    damit im Vorschautext und im Entwurf garantiert dasselbe steht.
    """

    anrede: str
    firma: str
    phase: int
    angebot_datum: str
    projekt: str
    leistungsbeginn: str
    projektplanung: str
    klaerung: str
    abgabe: str


def fmt(wert: date | None) -> str:
    """Datum deutsch, leer als Platzhalter.

    Der Platzhalter ist Absicht: Ein fehlender Termin soll im Entwurf
    auffallen, damit ihn jemand einträgt, statt dass die Zeile ganz
    verschwindet und niemand sie vermisst.
    """
    return f"{wert:%d.%m.%Y}" if wert else "___"


def klaerungstermin(beauftragung: date, tage: int = KLAERUNG_TAGE) -> date:
    """Beauftragungsdatum + ``tage`` — siehe Hinweis bei KLAERUNG_TAGE."""
    return beauftragung + timedelta(days=tage)


def betreff(
    *,
    beauftragung: date,
    unlocode: str,
    phase: int,
    kuerzel: str,
    projekt_kuerzel: str = PROJEKT_KUERZEL,
) -> str:
    """``260825_NSO_NIV_Beauftragung Phase 1 KOCKS``.

    Reihenfolge und Schreibweise wie im Büro: Datum sechsstellig ohne Punkte,
    dann Projekt- und Ortskürzel, dann der Klartext. Ein fehlender Ortscode
    wird zu ``XXX`` — sichtbar falsch ist besser als stillschweigend weggelassen,
    denn am Betreff hängt die Ablage beim Empfänger.
    """
    code = (unlocode or "XXX").strip().upper() or "XXX"
    return (
        f"{beauftragung:%y%m%d}_{projekt_kuerzel}_{code}_"
        f"Beauftragung Phase {phase} {kuerzel.strip().upper()}"
    )


def text(variante: str, werte: Werte) -> str:
    """Das Schreiben in der gewählten Fassung."""
    aufbau = TEXTVARIANTEN.get(
        (variante or "").strip().lower(), TEXTVARIANTEN[STANDARD_VARIANTE]
    )
    return aufbau(werte)


def aus_daten(
    *,
    variante: str,
    anrede: str,
    firma: str,
    phase: int,
    angebot_datum: date | None,
    projekt: str,
    leistungsbeginn: date | None,
    projektplanung: date | None,
    klaerung: date | None,
    abgabe: date | None,
) -> str:
    """Bequemer Weg von Datumswerten zum fertigen Text."""
    return text(variante, Werte(
        anrede=anrede.strip() or "Sehr geehrte Damen und Herren,",
        firma=firma.strip() or "___",
        phase=phase,
        angebot_datum=fmt(angebot_datum),
        projekt=projekt.strip() or "___",
        leistungsbeginn=fmt(leistungsbeginn),
        projektplanung=fmt(projektplanung),
        klaerung=fmt(klaerung),
        abgabe=fmt(abgabe),
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Ablage im Projektordner
# ─────────────────────────────────────────────────────────────────────────────

#: Der feste Teil des Ablagepfads unter dem Standortordner. Nur der
#: Firmenordner wird eingesetzt — alles andere ist für jeden Standort gleich
#: (siehe Modultext).
VERTRAGSPFAD = "18-GP/12_Verträge/02_Subplaner/{ordner}/02_Vertrag"

#: Zeichen, die Windows in Dateinamen nicht zulässt.
_VERBOTEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def ablagepfad(ordner: str) -> str:
    """Der Vertragsordner eines Subplaners, relativ zum Standortordner."""
    return VERTRAGSPFAD.format(ordner=(ordner or "").strip("/\\ "))


def dateiname(betreffzeile: str) -> str:
    """``.eml``-Name aus dem Betreff — so heißt die Datei wie das Schreiben."""
    sauber = " ".join(_VERBOTEN.sub(" ", betreffzeile or "").split())
    return f"{sauber or 'Beauftragung'}.eml"
