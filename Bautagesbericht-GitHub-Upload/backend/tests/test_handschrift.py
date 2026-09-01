"""Handschriftliche Bautagebücher: Seiten lesen, prüfen, zu Tagen fügen.

Die Anfragen an die Schnittstelle werden hier durch einen Prüfstand ersetzt,
der genau das zurückgibt, was auf den echten Blättern von 2024-KW03 steht
(Riedel Bau, Woche vom 15.01.2024). Geprüft wird damit das, was ohne Schlüssel
sonst niemand prüfen kann: ob aus zwölf Einzelseiten sechs richtige Tage
werden.

Warum das eine eigene Reihe verdient: Auf Seite 1 steht die Anzahl der Leute,
auf Seite 2 steht, was sie getan haben, und der Firmenname wird auf beiden
Seiten unterschiedlich gelesen. Geht das Zusammenführen schief, steht im
Bericht eine Firma mit Leuten und ohne Leistung — und daneben dieselbe Firma
mit Leistung und ohne Leute.
"""
import asyncio
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STORAGE = Path(tempfile.gettempdir()) / "hpp-handschrifttest"
if STORAGE.exists():
    shutil.rmtree(STORAGE)
STORAGE.mkdir(parents=True)

WIN = str(STORAGE).replace("\\", "/")
os.environ["BTB_DATABASE_URL"] = f"sqlite:///{WIN}/test.db"
os.environ["BTB_UPLOAD_DIR"] = f"{WIN}/uploads"
os.environ["BTB_OUTPUT_DIR"] = f"{WIN}/output"

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.services import bautext, firmennamen, seitenlesung  # noqa: E402

ok = 0
fehler = []


def pruefe(bedingung, text):
    global ok
    if bedingung:
        ok += 1
    else:
        fehler.append(text)


def abschnitt(text):
    print(f"─── {text} ───")


# ─────────────────────────────────────────────────────────────────────────────
# Prüfstand: gibt zurück, was auf den echten Blättern steht
# ─────────────────────────────────────────────────────────────────────────────

#: Was der erste Durchgang je Seite liefert. Die Firmennamen sind bewusst so
#: verschrieben, wie eine Erkennung sie auf diesen Blättern verliest:
#: "Riedd Bau" auf Seite 1, "Riedel Bau" auf Seite 2.
SEITEN = [
    # ── Montag, 15.01.2024, Blatt 243 ──
    {
        "blattseite": 1, "blatt_nr": "243", "datum": "15.01.2024",
        "baustelle": "Desyum HH", "arbeitszeit": "7:00 - 18:00",
        "wetter": "Schneefall, still, 7h -1°, 12h +2°, 16h -1°",
        "firmen": [
            {"firma": "Riedd Bau", "personen": 3, "leistung": "", "ort": ""},
            {"firma": "Miro Ventig", "personen": 12, "leistung": "", "ort": ""},
            {"firma": "Goni Bau", "personen": 4, "leistung": "", "ort": ""},
        ],
        "sonstiges": [
            "4.OG. Trh. Wände mit Folie abgehängt und 2 Bauheizungen in "
            "Betrieb genommen, Jumbo 65 ab 12:00",
            "Mehr Aufwand Arbeitsplätze vom Schnee wegräumen",
        ],
        "besuche": ["2 Stück Bauheizungen Jumbo 65", "1 Stück Pumpe + Schlauch"],
    },
    {
        "blattseite": 2, "blatt_nr": "243|2", "datum": "",
        "firmen": [
            {"firma": "Riedel Bau", "personen": 0,
             "leistung": "Bau Management · Material Dispo", "ort": ""},
            {"firma": "Miro Ventig", "personen": 0,
             "leistung": "2.OG. Bei Brespa Decken OK. Decke Löcher mit Mörtel "
                         "verschlossen · 4.OG. Trh. Nord Wände zugestellt und "
                         "betoniert · 4.OG. Trh. Süd Wandschalung gestellt · "
                         "4.OG. Unterzüge gestellt · Lagerplatz aufgeräumt · "
                         "UG. Wasser gepumpt",
             "ort": "2.OG / 4.OG"},
            {"firma": "Goni Bau", "personen": 0,
             "leistung": "4.OG. Trh. Süd Wände bewehrt", "ort": "4.OG"},
        ],
        "sonstiges": [], "besuche": [],
    },
    # ── Dienstag, 16.01.2024, Blatt 244 ──
    {
        "blattseite": 1, "blatt_nr": "244", "datum": "16.01.2024",
        "baustelle": "Desyum HH", "arbeitszeit": "7:00 - 18:00",
        "wetter": "Schneefall, 7h -2°, 12h -0,5°, 16h +0°",
        "firmen": [
            {"firma": "Riedel Bau", "personen": 3, "leistung": "", "ort": ""},
            {"firma": "Miro Ventig", "personen": 12, "leistung": "", "ort": ""},
            {"firma": "Goni Bau", "personen": 3, "leistung": "", "ort": ""},
            {"firma": "Kraft Gerüst", "personen": 3, "leistung": "", "ort": ""},
        ],
        "sonstiges": [
            "4.OG. Trh. Nord 2 Stück Bauheizungen in Betrieb",
            "Wegen Nachtfrost Wände mit Folie abgehängt",
            "Arbeiten unter erschwerten Bedingungen: Eis, Schnee",
        ],
        "besuche": [],
    },
    {
        "blattseite": 2, "blatt_nr": "244|2", "datum": "",
        "firmen": [
            {"firma": "Miro Ventig", "personen": 0,
             "leistung": "4.OG. Trh. Nord Wände ausgeschalt", "ort": "4.OG"},
        ],
        "sonstiges": [], "besuche": [],
    },
]

#: Was der Prüfdurchgang ändert. Bei der zweiten Seite des ersten Blattes wird
#: eine falsch gelesene Zahl berichtigt — genau der Fall, für den es den
#: zweiten Durchgang gibt.
KORREKTUREN = {
    0: ["personen bei Goni Bau: 9 gelesen, richtig ist 4"],
}


class PruefstandAntwort:
    def __init__(self, nutzlast, werkzeug):
        self.content = [type("Block", (), {
            "type": "tool_use", "name": werkzeug, "input": nutzlast,
        })()]


class PruefstandClient:
    """Ersetzt den Anthropic-Client. Zählt mit, was gefragt wurde."""

    def __init__(self):
        self.anfragen = []
        self.messages = self

    def create(self, *, model, max_tokens, tools, tool_choice, messages):
        werkzeug = tools[0]["name"]
        # An welcher Seite sind wir? Die Reihenfolge der Bilder ist die
        # Reihenfolge der Aufrufe — der Prüfstand zählt die Abschriften.
        text = next(t["text"] for t in messages[0]["content"] if t["type"] == "text")
        self.anfragen.append((werkzeug, text))

        if werkzeug == "seite_abschreiben":
            index = sum(1 for w, _ in self.anfragen if w == "seite_abschreiben") - 1
        else:
            index = sum(1 for w, _ in self.anfragen if w == "seite_pruefen") - 1

        nutzlast = dict(SEITEN[index % len(SEITEN)])
        if werkzeug == "seite_pruefen":
            nutzlast["korrekturen"] = KORREKTUREN.get(index, [])
        return PruefstandAntwort(nutzlast, werkzeug)


def stelle_pruefstand_bereit():
    client = PruefstandClient()
    seitenlesung.verfuegbar = lambda: True
    seitenlesung._client = lambda: client
    # Vier Seiten "rendern", ohne eine echte Datei zu brauchen.
    seitenlesung._seitenbilder = lambda pfad: [b"x", b"y", b"z", b"w"]
    seitenlesung.vergiss()
    return client


BEKANNT = ("Riedel Bau", "Miro Ventig", "Goni Bau")


abschnitt("Seiten werden einzeln und zweimal gelesen")
client = stelle_pruefstand_bereit()
befunde = asyncio.run(seitenlesung.lies_seiten(Path("nicht-vorhanden.pdf"), BEKANNT))

pruefe(len(befunde) == 4, f"vier Seiten: {len(befunde)}")
abschriften = [w for w, _ in client.anfragen if w == "seite_abschreiben"]
pruefungen = [w for w, _ in client.anfragen if w == "seite_pruefen"]
pruefe(len(abschriften) == 4, f"vier Abschriften: {len(abschriften)}")
pruefe(len(pruefungen) == 4, f"vier Prüfungen: {len(pruefungen)}")
# Der Prüfauftrag muss die Abschrift enthalten — sonst prüft er ins Blaue.
prueftext = next(t for w, t in client.anfragen if w == "seite_pruefen")
pruefe("ABSCHRIFT DES ERSTEN DURCHGANGS" in prueftext, "Prüfung kennt die Abschrift")
pruefe("Riedd Bau" in prueftext, "Prüfung bekommt die gelesenen Namen vorgelegt")
pruefe("Zahlen" in prueftext, "Prüfung wird auf Zahlen gestoßen")

abschnitt("Bekannte Firmen werden als Lesehilfe mitgegeben")
erster = next(t for w, t in client.anfragen if w == "seite_abschreiben")
pruefe("Miro Ventig" in erster, "bekannte Firmen im Auftrag")
pruefe("keine Auswahlliste" in erster, "als Hilfe, nicht als Zwang")

abschnitt("Einzelbefunde")
pruefe(befunde[0].datum == date(2024, 1, 15), f"Datum Seite 1: {befunde[0].datum}")
pruefe(befunde[0].blattseite == 1, f"Blattseite: {befunde[0].blattseite}")
pruefe(befunde[1].datum is None, "Fortsetzungsseite hat kein eigenes Datum")
pruefe(len(befunde[0].firmen) == 3, f"drei Firmen auf Seite 1: {len(befunde[0].firmen)}")
pruefe(befunde[0].korrekturen == KORREKTUREN[0],
       f"Korrektur übernommen: {befunde[0].korrekturen}")

abschnitt("Aus vier Seiten werden zwei Tage")
tage = seitenlesung.zu_tagen(befunde, BEKANNT)
pruefe(len(tage) == 2, f"zwei Tage: {len(tage)} ({[t.datum for t in tage]})")
pruefe(tage[0].datum == date(2024, 1, 15), f"Tag 1: {tage[0].datum}")
pruefe(tage[1].datum == date(2024, 1, 16), f"Tag 2: {tage[1].datum}")
pruefe(tage[0].seiten == [1, 2], f"Tag 1 aus Seiten {tage[0].seiten}")
pruefe(tage[1].seiten == [3, 4], f"Tag 2 aus Seiten {tage[1].seiten}")

abschnitt("Anzahl von Seite 1 und Leistung von Seite 2 gehören zusammen")
tag1 = {f.firma: f for f in tage[0].firmen}
pruefe(len(tag1) == 3, f"drei Firmen, nicht sechs: {sorted(tag1)}")
# Das ist der Kern: "Riedd Bau" (Seite 1) und "Riedel Bau" (Seite 2) sind
# dieselbe Firma. Ohne Zusammenführen stünden beide im Bericht.
pruefe("Riedel Bau" in tag1, f"Schreibweisen vereint: {sorted(tag1)}")
pruefe("Riedd Bau" not in tag1, "die verlesene Schreibweise ist weg")
riedel = tag1.get("Riedel Bau")
pruefe(riedel is not None and riedel.personen == 3,
       f"Personen von Seite 1: {riedel.personen if riedel else '-'}")
pruefe(riedel is not None and "Bau Management" in riedel.leistung,
       f"Leistung von Seite 2: {riedel.leistung if riedel else '-'}")

miro = tag1.get("Miro Ventig")
pruefe(miro is not None and miro.personen == 12, f"Miro Personen: {miro.personen}")
pruefe(miro is not None and "Unterzüge gestellt" in miro.leistung,
       "Miro Leistung vollständig")
pruefe(miro is not None and "2.OG" in miro.ort, f"Miro Ort: {miro.ort}")

goni = tag1.get("Goni Bau")
pruefe(goni is not None and goni.personen == 4, f"Goni Personen: {goni.personen}")
pruefe(goni is not None and "bewehrt" in goni.leistung, "Goni Leistung")

abschnitt("Eine Firma ohne Leistung auf Seite 2 bleibt trotzdem stehen")
tag2 = {f.firma: f for f in tage[1].firmen}
pruefe("Kraft Gerüst" in tag2, f"vierte Firma erhalten: {sorted(tag2)}")
pruefe(tag2["Kraft Gerüst"].personen == 3, "mit ihrer Anzahl")
pruefe(tag2["Kraft Gerüst"].leistung == "", "ohne erfundene Leistung")

abschnitt("Sonstiges und Besuche werden zum Haupteintrag")
pruefe("Bauheizungen" in tage[0].haupteintrag,
       f"Sonstiges übernommen: {tage[0].haupteintrag[:60]}")
pruefe("Besuche:" in tage[0].haupteintrag, "Besuche gekennzeichnet")
pruefe("Jumbo 65" in tage[0].haupteintrag, "Besuchsinhalt übernommen")

abschnitt("Umwandlung in Firmeneinträge")
eintraege = seitenlesung.als_firmeneintraege(tage[0])
pruefe(len(eintraege) == 3, f"drei Einträge: {len(eintraege)}")
pruefe(all(e["quelle"] == "ocr" for e in eintraege),
       "als maschinell gelesen gekennzeichnet")
pruefe(all(isinstance(e["personen"], int) for e in eintraege), "Personen sind Zahlen")

abschnitt("Blattzuordnung über die Blatt-Nummer")
# Auf der Fortsetzung steht die Nummer mit angehängter Seitenzahl ("243|2").
kopf = seitenlesung.SeitenBefund(seite=1, blattseite=1, blatt_nr="243")
folge = seitenlesung.SeitenBefund(seite=2, blattseite=2, blatt_nr="243|2")
fremd = seitenlesung.SeitenBefund(seite=2, blattseite=2, blatt_nr="251")
pruefe(seitenlesung._passt_zu_blatt(kopf, folge), "243|2 gehört zu 243")
pruefe(not seitenlesung._passt_zu_blatt(kopf, fremd), "251 gehört nicht zu 243")
# Ohne lesbare Nummer entscheidet die Nachbarschaft.
ohne = seitenlesung.SeitenBefund(seite=2, blattseite=2, blatt_nr="")
pruefe(seitenlesung._passt_zu_blatt(kopf, ohne), "ohne Nummer zählt die Reihenfolge")

abschnitt("Ohne Schlüssel wird nichts gelesen")
seitenlesung.verfuegbar = lambda: False
leer = asyncio.run(seitenlesung.lies_seiten(Path("egal.pdf")))
pruefe(leer == [], f"nichts gelesen: {leer}")

abschnitt("Datumsformen")
for text, erwartet in [("15.01.2024", date(2024, 1, 15)),
                       ("5.1.24", date(2024, 1, 5)),
                       ("Mo. 15.01.2024", date(2024, 1, 15)),
                       ("15-01-2024", date(2024, 1, 15)),
                       ("kein Datum", None),
                       ("32.01.2024", None)]:
    pruefe(seitenlesung._als_datum(text) == erwartet,
           f"{text!r} -> {seitenlesung._als_datum(text)} statt {erwartet}")

print()
print(f"{ok} Pruefungen ok, {len(fehler)} Fehler")
if fehler:
    print("FEHLER:")
    for f in fehler:
        print(" -", f)
    sys.exit(1)
