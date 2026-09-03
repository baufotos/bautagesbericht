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

from app.schemas import (  # noqa: E402
    BautagesberichtJSON,
    FirmaEintrag,
    WetterBlock,
    WetterStundenwert,
)
from app.services.docx_generation import (  # noqa: E402
    BLOCK_ABSTAND,
    FELD_ABSTAND,
    ZEILENABSTAND_TEXT,
    _diagramm_bereich,
    anzeigename,
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

print("─── Steuerzeichen halten das Dokument nicht auf ───")

# Ein Seitenvorschub aus einem kopierten PDF oder ein vertikaler Tabulator
# aus der Texterkennung liess das Erzeugen mit "PCDATA invalid Char value 12"
# platzen. Der Bericht stand dann auf "fehlgeschlagen", ohne dass irgendwo
# gestanden haette, woran es lag.
stoerfall = BautagesberichtJSON(
    projekt="Testbaustelle\x0bNord", datum=date(2026, 8, 5),
    haupteintrag="Frost am Morgen\x0cBaustelle geraeumt",
    firmen=[FirmaEintrag(
        firma="Riedel Bau", personen=3,
        leistung="Zeile eins\nZeile zwei\x0bZeile drei",
        besonderes="Behinderung\x01A",
    )],
)
try:
    pfad_stoer = generate_bautagesbericht(stoerfall)
    pruefe(True, "Dokument mit Steuerzeichen entsteht")
except Exception as exc:      # pragma: no cover - genau das darf nicht sein
    fehler.append(f"Steuerzeichen lassen das Dokument platzen: {exc}")
    pfad_stoer = None

if pfad_stoer is not None:
    stoer = teile(pfad_stoer)["word/document.xml"]
    laeufe = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", stoer)
    pruefe("Zeile eins" in laeufe and "Zeile drei" in laeufe,
           f"alle drei Leistungszeilen stehen drin: {laeufe[-6:]}")
    # Mehrzeilige Werte brauchen echte Umbrueche. Ein "\n" mitten in <w:t>
    # ist fuer Word bloss Leerraum — aus drei Zeilen wurde eine lange.
    pruefe("<w:br/>" in stoer, "mehrzeilige Werte werden mit <w:br/> gesetzt")
    pruefe("BehinderungA" in laeufe,
           f"Steuerzeichen ist weg, der Text bleibt: {[l for l in laeufe if 'Behinder' in l]}")
    gleich([l for l in laeufe if l.startswith("Testbaustelle")],
           ["Testbaustelle Nord"], "Projektname bleibt einzeilig")

    # Die Fusszeile ist eine Zeile. Ein Umbruchzeichen im Projektnamen machte
    # sie zweizeilig — auf jeder Seite, und der Seitenspiegel rutschte hoch.
    stoer_fuss = "\n".join(v for k, v in teile(pfad_stoer).items() if "footer" in k)
    pruefe("Bautagebuch - Testbaustelle Nord - 05.08.2026" in stoer_fuss,
           "Fusszeile bleibt eine Zeile, auch mit Steuerzeichen im Namen")
    pruefe("<w:br/>" not in stoer_fuss, "kein Umbruch in der Fusszeile")


print("─── Temperaturdiagramm an einem Frosttag ───")

# Der Nullpunkt war fest: An einem Tag zwischen -5 und -1 Grad war kein
# einziger Balken zu sehen, das Diagramm verschwand im Winter stillschweigend.
gleich(_diagramm_bereich([-5.0, -4.0, -1.0]), (-5.0, -1.0),
       "bei Frost sinkt der Boden mit")
gleich(_diagramm_bereich([12.0, 20.0]), (0.0, 20.0),
       "ueber null bleibt der Boden bei 0 Grad — Tage bleiben vergleichbar")
gleich(_diagramm_bereich([3.0, 3.0]), (0.0, 3.0),
       "gleichbleibende Temperatur teilt nicht durch null")
gleich(_diagramm_bereich([]), (0.0, 1.0), "ohne Messwerte kein Absturz")

frosttag = BautagesberichtJSON(
    projekt="Winterbaustelle", datum=date(2026, 1, 15),
    wetter=WetterBlock(
        station="DWD Test", temp_max_c=-1.0, temp_min_c=-5.0,
        stundenwerte=[
            WetterStundenwert(stunde=stunde, temperatur_c=temp, icon="snow")
            for stunde, temp in zip(
                range(1, 24, 2),
                [-5.0, -5.0, -4.0, -4.0, -3.0, -2.0, -1.0, -2.0, -3.0, -4.0,
                 -4.0, -5.0])
        ],
    ),
    firmen=[FirmaEintrag(firma="Riedel Bau", personen=2)],
)
winter = teile(generate_bautagesbericht(frosttag))["word/document.xml"]
gleich(winter.count('w:fill="FFA500"'), 12,
       "zwoelf Balken, auch wenn der ganze Tag unter null lag")


print("─── Zwei Berichte fuer denselben Tag ───")

# Ohne Kennung im Dateinamen schrieb der zweite Bericht den ersten still
# ueber, und der Download des aelteren lieferte danach den Inhalt des neueren.
daten = BautagesberichtJSON(
    projekt="Testbaustelle Nord", datum=date(2026, 8, 5),
    firmen=[FirmaEintrag(firma="Riedel Bau", personen=1)],
)
erster = generate_bautagesbericht(daten, kennung="17")
zweiter = generate_bautagesbericht(daten, kennung="18")
pruefe(erster != zweiter,
       f"zwei Einreichungen, zwei Dateien: {erster.name} / {zweiter.name}")
pruefe(erster.is_file() and zweiter.is_file(), "beide Dateien liegen da")
gleich(anzeigename("Testbaustelle Nord", date(2026, 8, 5)),
       "Bautagesbericht 2026-08-05 Testbaustelle Nord.docx",
       "beim Herunterladen steht ein lesbarer Name")


print()
if fehler:
    print(f"{ok} Pruefungen ok, {len(fehler)} Fehler:")
    for f in fehler:
        print("  -", f)
    raise SystemExit(1)
print(f"{ok} Pruefungen ok, 0 Fehler")
