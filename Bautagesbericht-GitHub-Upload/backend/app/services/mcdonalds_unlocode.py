"""Den 3-stelligen UN/LOCODE zu einem Ort finden.

WOZU
====
Der Projektordner eines McDonald's-Standorts heißt ``<UNLOCODE>_<Standortname>``
— zum Beispiel ``AAH_Aachen Europaplatz``. Der Code ist keine Erfindung des
Büros, sondern die amtliche Ortskennung der UNECE; die deutsche Liste liegt als
Anlage 5.1 des Projekthandbuchs vor (``260224_PHB_Anlage 5.1_UNLOCODE (DE).xlsx``,
rund 10.000 Orte, Spalten UNLOCODE / Ort / Bundesland / Coordinates / Remarks).

Die Datei wird in der App hochgeladen und landet in der Tabelle
``mcdonalds_unlocode``. Das ist Absicht: Auf dem Bürorechner läge sie sonst auf
einem Netzlaufwerk, das der Server im Internet nicht erreicht, und eine neue
Fassung der Anlage wäre ein Software-Update statt eines Uploads.

WARUM DIE EXCEL-DATEI OHNE ZUSATZPAKET GELESEN WIRD
===================================================
Eine ``.xlsx``-Datei ist ein ZIP mit XML darin, und für eine flache
Nachschlagetabelle braucht das keine Bibliothek: ``zipfile`` und
``xml.etree`` genügen und stehen überall zur Verfügung. Ein Zusatzpaket
(openpyxl) hätte bedeutet, das Windows-Paket der Kollegen um ein Paket zu
vergrößern, das genau eine Datei im Jahr liest.

Grenze dieses Wegs: Nur ``.xlsx``. Eine alte ``.xls``-Datei muss vorher in
Excel einmal neu gespeichert werden — die Oberfläche sagt das auch.

DAS EIGENTLICHE PROBLEM IST NICHT DAS LESEN, SONDERN DAS TREFFEN
================================================================
Aus einer Mail kommt "Große Bergstraße 160, 22767 Hamburg" oder "Frankfurt am
Main" oder "Muenchen". In der Tabelle stehen "Hamburg", "Frankfurt am Main" und
"München". Deshalb wird jeder Ortsname vereinfacht (klein, ohne Umlaute, ohne
Sonderzeichen) und in dieser Form abgelegt. Erst wenn das nichts findet, kommt
ein unscharfer Vergleich zum Zug — und der meldet mit, wie sicher er ist, damit
in der Oberfläche ein Mensch entscheiden kann.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import UnlocodeEintrag

#: Namensraum der Tabellendateien in einer .xlsx.
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

#: Überschriften, an denen die Kopfzeile der Tabelle erkannt wird. Die Anlage
#: hat einen Titel über der Tabelle (Zeile 1–2) — die Kopfzeile steht erst in
#: Zeile 4, und in einer künftigen Fassung vielleicht in Zeile 5. Deshalb wird
#: sie gesucht und nicht gezählt.
_KOPF_CODE = ("unlocode", "un/locode", "code", "locode")
_KOPF_ORT = ("ort", "name", "location", "stadt")
_KOPF_BUNDESLAND = ("bundesland", "subdivision", "region", "land")

#: Ab dieser Ähnlichkeit gilt ein unscharfer Treffer als brauchbar. 0.82 ist
#: streng genug, dass "Ahrensburg" nicht als "Ahrensbök" durchgeht, und mild
#: genug für "Muenchen" → "München" und für einen fehlenden Bindestrich.
AEHNLICHKEIT_GRENZE = 0.82

#: So viele Kandidaten holt der unscharfe Vergleich, bevor der beste gewählt
#: wird. Mehr als drei sind für eine Entscheidung ohne Menschen wertlos.
FUZZY_KANDIDATEN = 3


class UnlocodeFehler(RuntimeError):
    """Die Referenztabelle ließ sich nicht lesen."""


@dataclass
class LadeErgebnis:
    """Was der Upload der Referenztabelle bewirkt hat."""

    eingelesen: int
    #: Zeilen, die übersprungen wurden (leerer Code oder Ort).
    uebersprungen: int
    #: Name des Tabellenblatts, das benutzt wurde.
    blatt: str
    hinweise: list[str]


@dataclass
class Treffer:
    """Ein gefundener Code samt Begründung — die Oberfläche zeigt beides."""

    code: str
    ort: str
    bundesland: str
    #: "exakt" | "unscharf". Ein unscharfer Treffer gehört gegengelesen.
    art: str
    #: 1.0 bei exaktem Treffer, sonst die Ähnlichkeit des Vergleichs.
    guete: float


# ─────────────────────────────────────────────────────────────────────────────
# Ortsnamen vergleichbar machen
# ─────────────────────────────────────────────────────────────────────────────


#: Umlaute so, wie sie im Deutschen ersetzt werden — nicht so, wie Unicode sie
#: zerlegt. Ohne diese Tabelle würde aus "München" das "Munchen" der
#: Zerlegung; "Muenchen", wie es in Mails wirklich steht, träfe dann nicht.
_UMSCHRIFT = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe", "Ü": "ue", "ß": "ss"}
)


def normalisiere(ort: str) -> str:
    """Vereinfachte Form eines Ortsnamens für den Abgleich.

    "Müllheim" → "muellheim", "Frankfurt am Main" → "frankfurtammain",
    "Bad Oldesloe " → "badoldesloe". Leerzeichen und Bindestriche fallen weg,
    weil sie in Mails beliebig gesetzt werden ("Baden Baden", "Baden-Baden").
    """
    text = (ort or "").strip().translate(_UMSCHRIFT)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(z for z in text if not unicodedata.combining(z))
    return re.sub(r"[^a-z0-9]", "", text.lower())


#: Zusätze, die vor dem Ortsnamen stehen und nicht zur Tabelle gehören.
_ADRESS_RAUSCHEN = re.compile(
    r"\b(deutschland|germany|de)\b[\s,]*$", flags=re.IGNORECASE
)


def ort_aus_adresse(adresse: str) -> str:
    """Den Ortsnamen aus einer Anschrift herausziehen.

    "Große Bergstraße 160, 22767 Hamburg" → "Hamburg".
    "Europaplatz 1\\n52068 Aachen\\nDeutschland" → "Aachen".

    Regel: Die deutsche Postleitzahl ist der zuverlässigste Anker, den eine
    Anschrift bietet — was hinter ihr steht, ist der Ort. Fehlt sie, wird das
    letzte Stück nach dem letzten Komma genommen. Der Rückgabewert ist ein
    Vorschlag und keine Wahrheit; die Oberfläche zeigt ihn zum Gegenlesen.
    """
    text = (adresse or "").replace("\n", ", ").strip()
    if not text:
        return ""
    text = _ADRESS_RAUSCHEN.sub("", text).strip(" ,")

    # Hinter der Postleitzahl steht der Ort — bis zum nächsten Komma.
    nach_plz = re.search(r"\b\d{5}\b[\s,]*([^,]+)", text)
    if nach_plz:
        kandidat = nach_plz.group(1).strip(" ,.")
        if kandidat:
            return _ohne_stadtteil(kandidat)

    letztes = text.split(",")[-1].strip(" ,.")
    # Eine Zeile, die nur aus Hausnummer und Straße besteht, ist kein Ort.
    if not letztes or re.search(r"(stra(ss|ß)e|str\.|weg|platz|allee)", letztes, re.I):
        return ""
    return _ohne_stadtteil(letztes)


def _ohne_stadtteil(ort: str) -> str:
    """"Hamburg-Ottensen" → "Hamburg", falls der Ort so nicht in der Liste steht.

    Wird von ``ermittle`` benutzt, nicht hier entschieden: Es gibt Orte, die
    wirklich einen Bindestrich tragen ("Baden-Baden", "Castrop-Rauxel"), und
    die dürfen nicht halbiert werden. Diese Funktion liefert deshalb nur den
    vollständigen Namen zurück; das Kürzen passiert beim Suchen.
    """
    return ort.strip()


def _ohne_zusatz(ort: str) -> str:
    """Der Teil vor dem ersten Bindestrich — der zweite Versuch beim Suchen."""
    return ort.split("-")[0].strip()


# ─────────────────────────────────────────────────────────────────────────────
# Die Excel-Datei lesen
# ─────────────────────────────────────────────────────────────────────────────


def _spaltenname(zellbezug: str) -> str:
    """"C17" → "C"."""
    treffer = re.match(r"([A-Z]+)", zellbezug or "")
    return treffer.group(1) if treffer else ""


def _zeichenketten(archiv: zipfile.ZipFile) -> list[str]:
    """Die gemeinsame Zeichenkettentabelle der Arbeitsmappe.

    Excel legt jeden Text einmal dort ab und verweist in den Zellen nur mit
    einer Nummer darauf. Ohne diese Liste enthielte jede Zelle nur "38181".
    """
    if "xl/sharedStrings.xml" not in archiv.namelist():
        return []
    wurzel = ET.fromstring(archiv.read("xl/sharedStrings.xml"))
    return [
        "".join(t.text or "" for t in eintrag.iter(_NS + "t"))
        for eintrag in wurzel
    ]


def _blattpfade(archiv: zipfile.ZipFile) -> list[tuple[str, str]]:
    """(Blattname, Pfad im Archiv) in der Reihenfolge der Arbeitsmappe."""
    namen = [
        blatt.get("name", "")
        for blatt in ET.fromstring(archiv.read("xl/workbook.xml")).iter(_NS + "sheet")
    ]
    pfade = sorted(
        (n for n in archiv.namelist() if n.startswith("xl/worksheets/sheet")),
        key=lambda n: int(re.search(r"(\d+)", n).group(1)),
    )
    return list(zip(namen, pfade))


def _zeilen(archiv: zipfile.ZipFile, pfad: str, texte: list[str]):
    """Die Zellen eines Blatts als {Spaltenbuchstabe: Text} je Zeile."""
    wurzel = ET.fromstring(archiv.read(pfad))
    for zeile in wurzel.iter(_NS + "row"):
        werte: dict[str, str] = {}
        for zelle in zeile:
            spalte = _spaltenname(zelle.get("r", ""))
            if not spalte:
                continue
            if zelle.get("t") == "inlineStr":
                werte[spalte] = "".join(
                    t.text or "" for t in zelle.iter(_NS + "t")
                ).strip()
                continue
            wert = zelle.find(_NS + "v")
            if wert is None or wert.text is None:
                continue
            if zelle.get("t") == "s":
                nummer = int(wert.text)
                werte[spalte] = texte[nummer].strip() if nummer < len(texte) else ""
            else:
                werte[spalte] = wert.text.strip()
        if werte:
            yield werte


def _finde_kopfzeile(zeilen: list[dict[str, str]]) -> dict[str, str] | None:
    """Sucht die Zeile mit den Spaltenüberschriften und ordnet sie zu.

    Ergebnis: {"code": "A", "ort": "B", "bundesland": "C"} — welche Spalte
    was enthält. ``None``, wenn in diesem Blatt keine passende Kopfzeile
    steht (die Anlage hat drei Blätter, zwei davon sind Titel und Legende).
    """
    for zeile in zeilen[:30]:
        gefunden: dict[str, str] = {}
        for spalte, text in zeile.items():
            klein = (text or "").strip().lower()
            if not klein:
                continue
            if "code" not in gefunden and klein in _KOPF_CODE:
                gefunden["code"] = spalte
            elif "ort" not in gefunden and klein in _KOPF_ORT:
                gefunden["ort"] = spalte
            elif "bundesland" not in gefunden and klein in _KOPF_BUNDESLAND:
                gefunden["bundesland"] = spalte
        if "code" in gefunden and "ort" in gefunden:
            return gefunden
    return None


def lies_unlocode_tabelle(excel_pfad: str | Path) -> tuple[list[dict], LadeErgebnis]:
    """Liest die Referenztabelle und gibt die Zeilen samt Bericht zurück.

    Getrennt von ``lade_unlocode_tabelle``, damit sich das Lesen ohne
    Datenbank prüfen lässt — die Datei ist der Teil, der überrascht.
    """
    pfad = Path(excel_pfad)
    if not pfad.is_file():
        raise UnlocodeFehler(f"Die Datei {pfad.name} ist nicht (mehr) da.")

    try:
        archiv = zipfile.ZipFile(pfad)
    except zipfile.BadZipFile as fehler:
        raise UnlocodeFehler(
            "Die Datei ist keine Excel-Arbeitsmappe im Format .xlsx. Bitte in "
            "Excel öffnen und über „Speichern unter“ als .xlsx ablegen."
        ) from fehler

    with archiv:
        texte = _zeichenketten(archiv)
        for blattname, blattpfad in _blattpfade(archiv):
            zeilen = list(_zeilen(archiv, blattpfad, texte))
            kopf = _finde_kopfzeile(zeilen)
            if not kopf:
                continue
            return _zeilen_zu_eintraegen(zeilen, kopf, blattname)

    raise UnlocodeFehler(
        "In der Arbeitsmappe war keine Tabelle mit den Spalten „UNLOCODE“ und "
        "„Ort“ zu finden. Bitte prüfen, ob die richtige Datei hochgeladen "
        "wurde (Anlage 5.1 des Projekthandbuchs)."
    )


def _zeilen_zu_eintraegen(
    zeilen: list[dict[str, str]], kopf: dict[str, str], blattname: str
) -> tuple[list[dict], LadeErgebnis]:
    """Baut aus den Rohzeilen die Einträge — ab der Zeile nach der Kopfzeile."""
    eintraege: list[dict] = []
    uebersprungen = 0
    kopf_gesehen = False

    for zeile in zeilen:
        code = (zeile.get(kopf["code"]) or "").strip()
        ort = (zeile.get(kopf["ort"]) or "").strip()

        if not kopf_gesehen:
            # Die Kopfzeile selbst überspringen; alles darüber (Titel, Quelle)
            # hat keinen Code und fällt unten sowieso heraus.
            if code.lower() in _KOPF_CODE and ort.lower() in _KOPF_ORT:
                kopf_gesehen = True
            continue

        if not code or not ort:
            uebersprungen += 1
            continue

        eintraege.append({
            "code": code.upper(),
            "ort": ort,
            "ort_normal": normalisiere(ort),
            "bundesland": (zeile.get(kopf.get("bundesland", "")) or "").strip(),
        })

    hinweise: list[str] = []
    if uebersprungen:
        hinweise.append(
            f"{uebersprungen} Zeile(n) ohne Code oder Ort wurden übersprungen."
        )
    if not eintraege:
        raise UnlocodeFehler(
            f"Im Blatt „{blattname}“ standen unter der Kopfzeile keine "
            "verwertbaren Zeilen."
        )

    return eintraege, LadeErgebnis(
        eingelesen=len(eintraege),
        uebersprungen=uebersprungen,
        blatt=blattname,
        hinweise=hinweise,
    )


def lade_unlocode_tabelle(excel_pfad: str | Path, db: Session) -> LadeErgebnis:
    """Liest die Excel-Referenzliste und ersetzt damit den Bestand.

    Ersetzen und nicht zusammenführen: Die Anlage ist eine amtliche Liste, die
    als Ganzes fortgeschrieben wird. Würde man nur ergänzen, blieben gestrichene
    Orte für immer stehen — und niemand käme darauf, dass ein falscher Code aus
    einer Fassung von vorletztem Jahr stammt.
    """
    eintraege, ergebnis = lies_unlocode_tabelle(excel_pfad)

    db.query(UnlocodeEintrag).delete()
    db.bulk_insert_mappings(UnlocodeEintrag, eintraege)
    db.commit()
    return ergebnis


def anzahl_eintraege(db: Session) -> int:
    """Wie viele Orte in der Nachschlagetabelle stehen."""
    return db.query(UnlocodeEintrag).count()


# ─────────────────────────────────────────────────────────────────────────────
# Nachschlagen
# ─────────────────────────────────────────────────────────────────────────────


def ermittle(db: Session, ort: str, bundesland: str = "") -> Treffer | None:
    """Sucht den Code zu einem Ort — exakt, sonst unscharf.

    ``bundesland`` ist nur ein Wunsch und keine Bedingung: Mehrdeutige
    Ortsnamen gibt es reichlich ("Aach" in Baden-Württemberg und in
    Rheinland-Pfalz), und wenn das Bundesland bekannt ist, entscheidet es.
    Ist es unbekannt, wird der erste Treffer genommen — mit ``art="unscharf"``
    gekennzeichnet, damit die Oberfläche zum Gegenlesen auffordern kann.
    """
    gesucht = normalisiere(ort)
    if not gesucht:
        return None

    treffer = _exakt(db, gesucht, bundesland)
    if treffer:
        return treffer

    # "Hamburg-Ottensen" ist kein Ort der Liste, "Hamburg" schon.
    kurz = normalisiere(_ohne_zusatz(ort))
    if kurz and kurz != gesucht:
        treffer = _exakt(db, kurz, bundesland)
        if treffer:
            return Treffer(treffer.code, treffer.ort, treffer.bundesland,
                           "unscharf", 0.95)

    return _unscharf(db, gesucht, bundesland)


def _exakt(db: Session, normal: str, bundesland: str) -> Treffer | None:
    kandidaten = (
        db.query(UnlocodeEintrag)
        .filter(UnlocodeEintrag.ort_normal == normal)
        .all()
    )
    if not kandidaten:
        return None
    gewaehlt = _mit_bundesland(kandidaten, bundesland)
    return Treffer(gewaehlt.code, gewaehlt.ort, gewaehlt.bundesland, "exakt", 1.0)


def _unscharf(db: Session, normal: str, bundesland: str) -> Treffer | None:
    """Unscharfer Vergleich über alle Ortsnamen.

    ``difflib`` bekommt die vereinfachten Namen, nicht die Anzeigenamen: Sonst
    würde jede Groß-/Kleinschreibung und jeder Umlaut die Ähnlichkeit senken.
    Bei 10.000 Orten dauert das Bruchteile einer Sekunde und läuft ohnehin nur
    dann, wenn der exakte Weg nichts fand.
    """
    alle = db.query(UnlocodeEintrag).all()
    if not alle:
        return None

    namen = {eintrag.ort_normal for eintrag in alle}
    nahe = difflib.get_close_matches(
        normal, namen, n=FUZZY_KANDIDATEN, cutoff=AEHNLICHKEIT_GRENZE
    )
    if not nahe:
        return None

    beste = nahe[0]
    guete = difflib.SequenceMatcher(None, normal, beste).ratio()
    passende = [e for e in alle if e.ort_normal == beste]
    gewaehlt = _mit_bundesland(passende, bundesland)
    return Treffer(
        gewaehlt.code, gewaehlt.ort, gewaehlt.bundesland, "unscharf", round(guete, 3)
    )


def _mit_bundesland(
    kandidaten: list[UnlocodeEintrag], bundesland: str
) -> UnlocodeEintrag:
    """Aus mehreren gleichnamigen Orten den im gesuchten Bundesland."""
    if bundesland:
        gesucht = normalisiere(bundesland)
        for eintrag in kandidaten:
            if normalisiere(eintrag.bundesland) == gesucht:
                return eintrag
    return kandidaten[0]


def ermittle_unlocode(db: Session, ort: str, bundesland: str = "") -> str | None:
    """Nur der Code — für Aufrufer, die die Begründung nicht brauchen."""
    treffer = ermittle(db, ort, bundesland)
    return treffer.code if treffer else None
