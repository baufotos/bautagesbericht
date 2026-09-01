"""Prueft Fusszeile und Abstaende des erzeugten Bautagesberichts.

Die Fusszeile ist der Punkt, an dem die Blanko-Vorlage und ein erzeugtes
Dokument auseinandergehen: In der Vorlage sind "Bautagebuch" und "1 / 1"
gewoehnlicher Text am Blattende — richtig fuer ein Blatt, das von Hand
ausgefuellt wird, falsch fuer einen Bericht, der zwei Seiten lang werden kann.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ARBEIT = Path(tempfile.gettempdir()) / "hpp-test-btb-layout"
ARBEIT.mkdir(exist_ok=True)
os.environ.setdefault("BTB_OUTPUT_DIR", str(ARBEIT / "output"))
os.environ.setdefault("BTB_UPLOAD_DIR", str(ARBEIT / "uploads"))
os.environ.setdefault("BTB_DATABASE_URL", f"sqlite:///{(ARBEIT / 'x.db').as_posix()}")

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.schemas import BautagesberichtJSON, FirmaEintrag  # noqa: E402
from app.services.docx_generation import (  # noqa: E402
    BLOCK_ABSTAND,
    FELD_ABSTAND,
    ZEILENABSTAND_TEXT,
    generate_bautagesbericht,
)

ok = 0
fehler: list[str] = []


def pruefe(bedingung, text):
    global ok
    if bedingung:
        ok += 1
    else:
        fehler.append(text)


def gleich(ist, soll, text):
    pruefe(ist == soll, f"{text}: erwartet {soll!r}, war {ist!r}")


def baue(anzahl_firmen: int) -> Path:
    firmen = [
        FirmaEintrag(
            firma=f"Firma {i + 1} GmbH", ort=f"OG{i} / Achse A",
            personen=3 + i,
            leistung="Schalung, Bewehrung und Betonage der Decke, "
                     "danach Ausschalen und Nacharbeiten am Anschluss",
            besonderes="Betonpumpe stand bis 14:00 Uhr" if i == 0 else None,
        )
        for i in range(anzahl_firmen)
    ]
    daten = BautagesberichtJSON(
        projekt="Testbaustelle Nord", datum=date(2026, 8, 5),
        haupteintrag="Baubegehung mit dem Bauherrn",
        firmen=firmen, unterschrift_datum=date(2026, 8, 5),
    )
    return generate_bautagesbericht(daten)


def teile(pfad: Path) -> dict[str, str]:
    with zipfile.ZipFile(pfad) as z:
        return {n: z.read(n).decode("utf-8", "replace")
                for n in z.namelist() if n.endswith(".xml")}


print("─── Fusszeile ───")

pfad = baue(2)
inhalt = teile(pfad)

fusszeilen = [n for n in inhalt if "footer" in n]
pruefe(fusszeilen, "es gibt ueberhaupt eine Fusszeile")

fuss = "\n".join(inhalt[n] for n in fusszeilen)
pruefe("Bautagebuch - Testbaustelle Nord - 05.08.2026" in fuss,
       "Projektzeile steht in der Fusszeile")
pruefe("PAGE" in fuss, "Seitenzahl als PAGE-Feld")
pruefe("NUMPAGES" in fuss, "Gesamtzahl als NUMPAGES-Feld")
pruefe('w:fldCharType="begin"' in fuss, "als echtes Word-Feld, nicht als Text")

# Und NICHT mehr im Text: sonst stuende alles doppelt.
text = inhalt["word/document.xml"]
sichtbar = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", text))
pruefe("Bautagebuch" not in sichtbar,
       "die Vorlagenzeile ist aus dem Text verschwunden")
pruefe("1 / 1" not in sichtbar,
       "die feste Seitenangabe ist aus dem Text verschwunden")

# Der Abschnitt muss die Fusszeile auch benutzen.
pruefe("footerReference" in text, "Fusszeile ist am Abschnitt angemeldet")


print("─── Abstaende ───")

pruefe(FELD_ABSTAND >= 150,
       f"Abstand zwischen den Feldern ist grosszuegig ({FELD_ABSTAND} Twips)")
pruefe(BLOCK_ABSTAND > FELD_ABSTAND,
       "zwischen zwei Firmen ist mehr Luft als zwischen ihren Zeilen")
pruefe(ZEILENABSTAND_TEXT > 240,
       f"mehrzeilige Werte stehen weiter ({ZEILENABSTAND_TEXT} statt 240)")

pruefe(f'w:line="{ZEILENABSTAND_TEXT}"' in text,
       "der weitere Zeilenabstand steht im Dokument")
pruefe(f'w:after="{FELD_ABSTAND}"' in text,
       "der Feldabstand steht im Dokument")

# Zellen haben Innenabstand, Zeilen eine Mindesthoehe.
pruefe("<w:tcMar>" in text, "Zellen haben Innenabstand")
pruefe('w:hRule="atLeast"' in text, "Zeilen haben eine Mindesthoehe")

# Zeilen duerfen am Seitenrand nicht zerrissen werden.
pruefe("<w:cantSplit/>" in text, "Tabellenzeilen brechen nicht mitten um")


print("─── Kein leeres Blatt am Ende ───")

# Nach der letzten Tabelle darf hoechstens ein leerer Absatz stehen.
nach_tabelle = text.rsplit("</w:tbl>", 1)[-1]
absaetze = re.findall(r"<w:p[ >].*?</w:p>", nach_tabelle, re.DOTALL)
pruefe(len(absaetze) <= 1,
       f"hoechstens ein Absatz hinter der Tabelle (waren {len(absaetze)})")

print()
if fehler:
    print(f"{ok} Pruefungen ok, {len(fehler)} Fehler:")
    for f in fehler:
        print("  -", f)
    raise SystemExit(1)
print(f"{ok} Pruefungen ok, 0 Fehler")
