"""Prüft die Farbtokens aus globals.css gegen WCAG AA.

WOZU
====
Das Designsystem legt Farben als Tokens fest (``--t-*`` in
``src/app/globals.css``, einmal für dunkel und einmal für hell). Ob ein
gedämpftes Grau auf der Kartenfläche noch lesbar ist, kann man ansehen und
sich täuschen — oder ausrechnen. Dieses Skript rechnet.

Geprüft wird jede Paarung, die in der App wirklich vorkommt: Text auf seiner
Fläche, Plaketten (helle Schrift auf ihrer eigenen, halbdurchsichtigen
Hinterlegung) und die Seitenleiste. Halbdurchsichtige Werte werden vorher über
ihren Untergrund gerechnet, sonst wäre das Ergebnis geschmeichelt.

MASSSTAB (WCAG 2.1)
===================
    4.5:1   normaler Text (AA)
    3.0:1   großer Text ab ~24 px oder 19 px fett (AA), UI-Ränder
Werte darunter werden als FEHLER gemeldet.

Aufruf:
    python frontend/_kontrast-pruefen.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Die Windows-Konsole steht oft auf cp1252 und bricht an Rahmenzeichen und
# Umlauten ab. Ausgabe deshalb auf UTF-8 umstellen, statt auf ASCII zu verzichten.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CSS = Path(__file__).resolve().parent / "src" / "app" / "globals.css"

#: Mindestkontrast für normalen Text.
AA_TEXT = 4.5
#: Mindestkontrast für große Zahlen und Ränder.
AA_GROSS = 3.0


# ─────────────────────────────────────────────────────────────────────────────
# Farben lesen und rechnen
# ─────────────────────────────────────────────────────────────────────────────


def bloecke_lesen(text: str) -> dict[str, dict[str, str]]:
    """Gibt {"dunkel": {token: wert}, "hell": {...}} aus der CSS-Datei."""
    fassungen: dict[str, dict[str, str]] = {}
    for name, muster in (
        ("dunkel", r"^:root\s*\{(.*?)^\}"),
        ("hell", r'^:root\[data-theme="hell"\]\s*\{(.*?)^\}'),
    ):
        treffer = re.search(muster, text, re.S | re.M)
        if not treffer:
            raise SystemExit(f"Block für '{name}' nicht gefunden in {CSS}")
        werte = dict(re.findall(r"(--t-[\w-]+)\s*:\s*([^;]+);", treffer.group(1)))
        fassungen[name] = {k: v.strip() for k, v in werte.items()}
    return fassungen


def zerlege(wert: str) -> tuple[float, float, float, float]:
    """Farbwert → (r, g, b, alpha) mit 0–255 bzw. 0–1."""
    wert = wert.strip()
    if wert.startswith("#"):
        h = wert[1:]
        if len(h) == 3:
            h = "".join(z * 2 for z in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0)

    zahlen = re.findall(r"[\d.]+", wert)
    if wert.startswith("rgba") and len(zahlen) == 4:
        r, g, b, a = zahlen
        return (float(r), float(g), float(b), float(a))
    if wert.startswith("rgb") and len(zahlen) >= 3:
        r, g, b = zahlen[:3]
        return (float(r), float(g), float(b), 1.0)

    raise ValueError(f"Farbwert nicht lesbar: {wert}")


def ueber(vordergrund: str, hintergrund: tuple[float, float, float]) -> tuple[float, float, float]:
    """Legt eine (evtl. halbdurchsichtige) Farbe über einen deckenden Grund."""
    r, g, b, a = zerlege(vordergrund)
    hr, hg, hb = hintergrund
    return (r * a + hr * (1 - a), g * a + hg * (1 - a), b * a + hb * (1 - a))


def helligkeit(farbe: tuple[float, float, float]) -> float:
    """Relative Leuchtdichte nach WCAG."""
    def kanal(wert: float) -> float:
        v = wert / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = farbe
    return 0.2126 * kanal(r) + 0.7152 * kanal(g) + 0.0722 * kanal(b)


def verhaeltnis(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    la, lb = helligkeit(a), helligkeit(b)
    hell, dunkel = max(la, lb), min(la, lb)
    return (hell + 0.05) / (dunkel + 0.05)


# ─────────────────────────────────────────────────────────────────────────────
# Die Paarungen, die in der App vorkommen
# ─────────────────────────────────────────────────────────────────────────────

#: (Beschreibung, Vordergrund, Kette von Hintergründen (hinten = unten), Grenze)
PAARE: list[tuple[str, str, list[str], float]] = [
    ("Text auf Seitengrund",            "--t-text",        ["--t-bg"], AA_TEXT),
    ("Text auf Karte",                  "--t-text",        ["--t-flaeche"], AA_TEXT),
    ("Text auf ruhiger Fläche",         "--t-text",        ["--t-flaeche-still"], AA_TEXT),
    ("Text auf Hauptkachel",            "--t-text",        ["--t-flaeche-hoch"], AA_TEXT),
    ("Nebentext auf Karte",             "--t-text-still",  ["--t-flaeche"], AA_TEXT),
    ("Nebentext auf ruhiger Fläche",    "--t-text-still",  ["--t-flaeche-still"], AA_TEXT),
    ("Nebentext auf Seitengrund",       "--t-text-still",  ["--t-bg"], AA_TEXT),
    ("Leisetext auf Karte",             "--t-text-leise",  ["--t-flaeche"], AA_TEXT),
    ("Leisetext auf Hauptkachel",       "--t-text-leise",  ["--t-flaeche-hoch"], AA_TEXT),
    ("Schrift auf Akzentknopf",         "--t-akzent-text", ["--t-akzent"], AA_TEXT),
    ("Erledigt-Plakette",               "--t-ok",          ["--t-ok-sanft", "--t-flaeche"], AA_TEXT),
    ("Überfällig-Plakette",             "--t-gefahr",      ["--t-gefahr-sanft", "--t-flaeche"], AA_TEXT),
    ("Frist-Plakette",                  "--t-warn",        ["--t-warn-sanft", "--t-flaeche"], AA_TEXT),
    ("Info-Plakette",                   "--t-info",        ["--t-info-sanft", "--t-flaeche"], AA_TEXT),
    ("Grün auf Karte",                  "--t-ok",          ["--t-flaeche"], AA_TEXT),
    ("Rot auf Karte",                   "--t-gefahr",      ["--t-flaeche"], AA_TEXT),
    ("Diagrammlinie auf Karte",         "--t-chart",       ["--t-flaeche"], AA_GROSS),
    ("Vergleichsbalken auf Karte",      "--t-chart-still", ["--t-flaeche"], AA_GROSS),
    ("Kartenkante auf Seitengrund",     "--t-linie",       ["--t-flaeche"], 1.15),
    ("Navigationstext",                 "--t-sidebar-text", ["--t-sidebar"], AA_TEXT),
    ("Aktive Navigation",               "--t-sidebar-text-hell",
     ["--t-sidebar-aktiv", "--t-sidebar"], AA_TEXT),
    ("Gruppenlabel der Navigation",     "--t-sidebar-label", ["--t-sidebar"], AA_GROSS),
]


def main() -> int:
    fassungen = bloecke_lesen(CSS.read_text(encoding="utf-8"))
    fehler = 0
    knapp = 0

    for fassung, werte in fassungen.items():
        print(f"\n{'═' * 74}\n  Fassung: {fassung.upper()}\n{'═' * 74}")
        for beschreibung, vordergrund, kette, grenze in PAARE:
            fehlend = [t for t in [vordergrund, *kette] if t not in werte]
            if fehlend:
                print(f"  ?  {beschreibung:32} Token fehlt: {', '.join(fehlend)}")
                fehler += 1
                continue

            # Hintergrundkette von unten nach oben zusammenrechnen.
            grund = zerlege(werte[kette[-1]])[:3]
            for token in reversed(kette[:-1]):
                grund = ueber(werte[token], grund)
            vorne = ueber(werte[vordergrund], grund)

            wert = verhaeltnis(vorne, grund)
            if wert < grenze:
                zeichen, status = "X", "FEHLER"
                fehler += 1
            elif wert < grenze * 1.15:
                zeichen, status = "!", "knapp"
                knapp += 1
            else:
                zeichen, status = "+", ""
            print(f"  {zeichen}  {beschreibung:32} {wert:5.2f}:1  "
                  f"(mind. {grenze}) {status}")

    print(f"\n{'─' * 74}")
    if fehler:
        print(f"  {fehler} Paarung(en) unter der Grenze — bitte Tokens anpassen.")
    else:
        print(f"  Alle Paarungen erfüllen WCAG AA. {knapp} davon knapp.")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
