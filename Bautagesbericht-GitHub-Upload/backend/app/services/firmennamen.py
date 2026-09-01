"""Firmennamen aus Handschrift zusammenführen.

DAS PROBLEM
===========
Auf einem handschriftlichen Bautagebuch steht dieselbe Firma auf Seite 1 als
"Riedd Bau" und auf Seite 2 als "Riedel Bau" — nicht weil der Polier sich
vertippt hat, sondern weil eine Schleife anders geraten ist und die Erkennung
zweimal anders geraten hat. Über eine Woche werden daraus fünf Schreibweisen,
und im Bericht stehen fünf Firmen, wo drei gearbeitet haben.

DIE LÖSUNG
==========
Drei Stufen, in dieser Reihenfolge:

1. **Aufräumen** (``normalisiere``). Doppelpunkte, "Fa.", doppelte Leerzeichen,
   ein versehentliches "GMBH" — Kleinkram, der nichts mit Erkennung zu tun hat.
2. **An bekannten Firmen ausrichten** (``vereinheitliche`` mit ``bekannt``).
   Die Firmen der Baustelle stehen in den Stammdaten. Ein gelesener Name, der
   einer davon nahe kommt, wird zu ihr — das ist die verlässlichste Quelle,
   weil dort jemand den Namen von Hand richtig eingetragen hat.
3. **Varianten untereinander bündeln.** Bleiben unbekannte Namen übrig, werden
   ähnliche Schreibweisen zu der zusammengefasst, die am häufigsten und am
   vollständigsten auftritt.

WO BEWUSST NICHTS ZUSAMMENGEFASST WIRD
======================================
Zwei Sicherungen, weil ein falsches Zusammenlegen schlimmer ist als zwei
Schreibweisen im Bericht:

* **Zwei bekannte Firmen werden nie vereint.** "Meier Bau" und "Meyer Bau"
  sehen sich zum Verwechseln ähnlich und sind zwei Unternehmen. Stehen beide
  in den Stammdaten, bleiben sie getrennt.
* **Bei Gleichstand wird nichts entschieden.** Passt ein gelesener Name zu
  zwei bekannten Firmen fast gleich gut, bleibt er, wie er gelesen wurde, und
  es wird eine Warnung gemeldet. Lieber eine Rückfrage als die falsche Firma
  im Bericht an den Bauherrn.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

#: Ab dieser Ähnlichkeit gelten zwei Schreibweisen als dieselbe Firma.
#: 0.78 ist an den echten Verwechslungen der Handschrift ausgerichtet
#: ("Riedd Bau"/"Riedel Bau" liegt bei 0.82) und lässt "Meier"/"Meyer" (0.87)
#: bewusst durch — dagegen schützt die Regel über bekannte Firmen, nicht die
#: Schwelle.
SCHWELLE = 0.78

#: Passt ein Name zu zwei bekannten Firmen und liegen die Werte enger als das
#: beieinander, wird nicht geraten.
GLEICHSTAND = 0.06

#: Zu kurze Namen taugen nicht für einen Ähnlichkeitsvergleich — "Ott" und
#: "Ost" wären eine Übereinstimmung.
MIN_LAENGE = 4

#: Rechtsformen. Für den Vergleich weggelassen, im Ergebnis behalten:
#: "Riedel Bau" und "Riedel Bau GmbH" sind dieselbe Firma, aber im Bericht
#: soll stehen, was auf dem Blatt stand.
_RECHTSFORMEN = (
    "gmbh & co. kg", "gmbh & co kg", "gmbh und co kg",
    "gmbh", "mbh", "ohg", "gbr", "kgaa", "kg", "ag", "se", "ug",
    "e.k.", "ek", "e.v.", "ev", "co.", "co",
)

#: Was am Anfang eines Firmennamens nichts verloren hat.
_VORSATZ = re.compile(r"^\s*(fa\.?|firma|nu|nachunternehmer)\s*[:.\-]?\s+", re.I)

#: Unsicherheitszeichen der Erkennung. Für den Vergleich weg, im Ergebnis bleibt
#: es stehen, damit man sieht, was unsicher gelesen wurde.
_UNSICHER = re.compile(r"\[\?\]")


def normalisiere(name: str) -> str:
    """Kleinkram aufräumen, ohne den Namen zu verändern.

    Ergebnis ist der Name, wie er im Bericht stehen soll — mit Rechtsform,
    mit Umlauten, mit einem etwaigen ``[?]`` an der unsicheren Stelle.
    """
    text = str(name or "").strip()
    if not text:
        return ""

    # Zeilenumbrüche und mehrfache Leerzeichen aus der Erkennung.
    text = re.sub(r"\s+", " ", text.replace("\n", " "))
    # Abschließende Doppelpunkte: Auf dem Blatt steht "Riedel Bau:" als
    # Überschrift der ausgeführten Arbeiten.
    text = text.strip(" :;,-–—")
    text = _VORSATZ.sub("", text).strip()

    # Häufige Schreibweisen der Rechtsform geraderücken.
    text = re.sub(r"\bGMBH\b", "GmbH", text)
    text = re.sub(r"\bgmbh\b", "GmbH", text)
    text = re.sub(r"\bAg\b", "AG", text)

    return text.strip()


def _falte(name: str) -> str:
    """Vergleichsform: nur Buchstaben und Ziffern, ohne Rechtsform, klein."""
    text = _UNSICHER.sub("", str(name or "")).lower()
    # Umlaute auflösen, damit "Grünanlagen" und "Gruenanlagen" gleich sind.
    text = (text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
                .replace("ß", "ss"))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(z for z in text if not unicodedata.combining(z))

    for form in _RECHTSFORMEN:
        # Nur am Wortende abschneiden: "Kagermann" darf sein "ag" behalten.
        text = re.sub(r"[\s,.\-]+" + re.escape(form) + r"\s*$", " ", text)

    return re.sub(r"[^a-z0-9]", "", text)


def aehnlichkeit(a: str, b: str) -> float:
    """0.0 bis 1.0. Vergleicht die gefalteten Formen."""
    fa, fb = _falte(a), _falte(b)
    if not fa or not fb:
        return 0.0
    if fa == fb:
        return 1.0
    if len(fa) < MIN_LAENGE or len(fb) < MIN_LAENGE:
        return 0.0
    return SequenceMatcher(None, fa, fb).ratio()


def _wortanfang_treffer(name: str, kandidaten: list[str]) -> str | None:
    """Ist der gelesene Name der Anfang genau einer bekannten Firma?

    Auf den Berichten steht die Kurzform: "Fa. Miro (2 Mann)", "Unterschrift
    RF". Gemeint sind "Miro Ventig" und "RF Fassaden GmbH". Für den
    Ähnlichkeitsvergleich sind diese Kürzel zu kurz — als Wortanfang sind sie
    dagegen eindeutig, solange nur eine bekannte Firma so beginnt.

    Die Eindeutigkeit ist die ganze Sicherung: Gibt es "Miro Ventig" und
    "Miro Bau", wird nicht geraten.
    """
    kurz = _falte(name)
    if len(kurz) < 2:
        return None
    treffer = [k for k in kandidaten if _falte(k).startswith(kurz)]
    # Der Name selbst zählt nicht als Kurzform seiner selbst.
    treffer = [k for k in treffer if _falte(k) != kurz] or treffer
    return treffer[0] if len(treffer) == 1 else None


def _bester_treffer(name: str, kandidaten: list[str]) -> tuple[str | None, str]:
    """Die am besten passende bekannte Firma. ``(treffer, warnung)``.

    ``treffer`` ist None, wenn nichts passt **oder** wenn zwei Kandidaten fast
    gleich gut passen — dann wird nicht geraten.
    """
    if not kandidaten:
        return None, ""

    # Kurzform zuerst: Sie ist eindeutig oder gar nicht, und der
    # Ähnlichkeitsvergleich würde sie nie finden.
    anfang = _wortanfang_treffer(name, kandidaten)
    if anfang is not None:
        return anfang, ""

    werte = sorted(
        ((aehnlichkeit(name, k), k) for k in kandidaten),
        key=lambda p: (-p[0], p[1]),
    )
    bester, kandidat = werte[0]
    if bester < SCHWELLE:
        return None, ""

    if len(werte) > 1 and bester - werte[1][0] < GLEICHSTAND:
        return None, (
            f"„{name}“ passt fast gleich gut zu „{kandidat}“ und "
            f"„{werte[1][1]}“ — bitte selbst zuordnen."
        )
    return kandidat, ""


def _gewicht(name: str, haeufigkeit: int) -> tuple:
    """Wie gut sich eine Schreibweise als Vertreter ihrer Gruppe eignet.

    Häufigkeit zuerst: Was fünfmal gleich gelesen wurde, ist wahrscheinlich
    richtig gelesen. Danach: keine Unsicherheitszeichen, dann der längere Name
    (Rechtsform und ausgeschriebene Wörter sind Information), zuletzt
    alphabetisch, damit das Ergebnis bei Gleichstand reproduzierbar ist.
    """
    return (haeufigkeit, 0 if _UNSICHER.search(name) else 1, len(name), name)


def vereinheitliche(
    namen: list[str], bekannt: list[str] | tuple[str, ...] = ()
) -> tuple[dict[str, str], list[str]]:
    """Ordnet jeder gelesenen Schreibweise den Namen zu, der gelten soll.

    Gibt ``(zuordnung, warnungen)`` zurück. ``zuordnung`` enthält jeden
    übergebenen Namen als Schlüssel — auch die, die unverändert bleiben, damit
    der Aufrufer stumpf nachschlagen kann.

    ``bekannt`` sind die Firmen der Baustelle aus den Stammdaten.
    """
    aufgeraeumt = {roh: normalisiere(roh) for roh in namen}
    bekannte = [normalisiere(b) for b in bekannt if normalisiere(b)]
    haeufig = Counter(v for v in aufgeraeumt.values() if v)

    zuordnung: dict[str, str] = {}
    warnungen: list[str] = []
    # Unbekannte Namen, die untereinander gebündelt werden müssen.
    offen: list[str] = []

    for roh, sauber in aufgeraeumt.items():
        if not sauber:
            zuordnung[roh] = ""
            continue
        treffer, warnung = _bester_treffer(sauber, bekannte)
        if warnung and warnung not in warnungen:
            warnungen.append(warnung)
        if treffer:
            zuordnung[roh] = treffer
        else:
            zuordnung[roh] = sauber
            if sauber not in offen:
                offen.append(sauber)

    # Übrige Namen untereinander bündeln. Der Vertreter jeder Gruppe ist die
    # Schreibweise mit dem höchsten Gewicht.
    gruppen: list[list[str]] = []
    for name in sorted(offen, key=lambda n: _gewicht(n, haeufig[n]), reverse=True):
        for gruppe in gruppen:
            if any(aehnlichkeit(name, mitglied) >= SCHWELLE for mitglied in gruppe):
                gruppe.append(name)
                break
        else:
            gruppen.append([name])

    vertreter: dict[str, str] = {}
    for gruppe in gruppen:
        chef = max(gruppe, key=lambda n: _gewicht(n, haeufig[n]))
        for name in gruppe:
            vertreter[name] = chef

    for roh, wert in list(zuordnung.items()):
        if wert in vertreter:
            zuordnung[roh] = vertreter[wert]

    return zuordnung, warnungen


def gleiche_firma(a: str, b: str) -> bool:
    """Für Nachschlagevorgänge: Sind das zwei Schreibweisen derselben Firma?

    Gebraucht beim Zusammenführen von Seite 1 (Firma + Anzahl) und Seite 2
    (Firma + ausgeführte Arbeiten) desselben Blattes.
    """
    return aehnlichkeit(a, b) >= SCHWELLE


# ─────────────────────────────────────────────────────────────────────────────
# Was dieses Projekt schon kennt
#
# Zwei Quellen, beide ohne Pflegeaufwand für den Anwender:
#   * die Firmen der Stammdaten (Gewerke) — dort steht der Name von Hand
#     eingetragen und damit richtig,
#   * die Firmen früherer Berichte desselben Projekts — die sammeln sich von
#     selbst an, sobald einmal ein Bericht erzeugt wurde.
# ─────────────────────────────────────────────────────────────────────────────


def bekannte_firmen(db, projekt_id: int) -> tuple[str, ...]:
    """Alle für dieses Projekt bekannten Firmennamen, häufigste zuerst.

    Sortierung nach Häufigkeit ist wichtig: Beim Abgleich eines unsicher
    gelesenen Namens soll die Firma gewinnen, die auf dieser Baustelle
    tatsächlich arbeitet, nicht eine, die einmal falsch erfasst wurde.
    """
    from app.models import Firmenname, Gewerk

    namen: list[str] = []
    gesehen: set[str] = set()

    def aufnehmen(roh: str) -> None:
        sauber = normalisiere(roh)
        if not sauber:
            return
        schluessel = _falte(sauber)
        if schluessel and schluessel not in gesehen:
            gesehen.add(schluessel)
            namen.append(sauber)

    for (roh,) in (
        db.query(Gewerk.firma_name)
        .filter(Gewerk.projekt_id == projekt_id)
        .all()
    ):
        aufnehmen(roh or "")

    for eintrag in (
        db.query(Firmenname)
        .filter(Firmenname.projekt_id == projekt_id)
        .order_by(Firmenname.anzahl.desc(), Firmenname.name)
        .all()
    ):
        aufnehmen(eintrag.name or "")

    return tuple(namen)


#: Namen, die nicht gemerkt werden dürfen — sie sind Platzhalter der
#: Erkennung, keine Firmen. Kämen sie in den Bestand, würde die nächste
#: Erkennung ausgerechnet auf sie hin ausgerichtet.
def _merkwuerdig(name: str) -> bool:
    sauber = (name or "").strip()
    if len(sauber) < MIN_LAENGE:
        return True
    if sauber.startswith("("):          # "(Handschrift/Scan: …)"
        return True
    if "[?]" in sauber:                 # unsicher gelesen
        return True
    if "bitte" in sauber.lower():       # "Firma bitte ergänzen"
        return True
    return False


def merke_firmen(db, projekt_id: int, namen: list[str]) -> None:
    """Hält fest, welche Firmen in einem fertigen Bericht standen.

    Wird erst nach dem Erzeugen des Dokuments aufgerufen — dann hat jemand das
    Ergebnis gesehen. Was die Erkennung nur vorgeschlagen und niemand geprüft
    hat, gehört nicht in den Bestand.
    """
    from app.models import Firmenname

    for roh in namen:
        sauber = normalisiere(roh)
        if not sauber or _merkwuerdig(sauber):
            continue

        # Schon vorhanden? Auch in einer anderen Schreibweise — dann wird der
        # Zähler der bestehenden erhöht, statt eine Variante anzulegen.
        vorhanden = (
            db.query(Firmenname)
            .filter(Firmenname.projekt_id == projekt_id)
            .all()
        )
        treffer = next(
            (e for e in vorhanden if gleiche_firma(e.name, sauber)), None
        )
        if treffer is not None:
            treffer.anzahl = (treffer.anzahl or 0) + 1
            # Die längere Schreibweise gewinnt: "Riedel Bau GmbH" sagt mehr
            # als "Riedel Bau", und beide meinen dieselbe Firma.
            if len(sauber) > len(treffer.name or ""):
                treffer.name = sauber
        else:
            db.add(Firmenname(projekt_id=projekt_id, name=sauber, anzahl=1))
    db.commit()
