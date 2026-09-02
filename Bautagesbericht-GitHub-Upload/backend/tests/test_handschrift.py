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

#: Die echte Bildaufbereitung, bevor der Prüfstand sie ersetzt. Sie braucht
#: keinen Schlüssel und wird weiter unten für sich geprüft.
ECHTE_SEITENBILDER = seitenlesung._seitenbilder

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
        #: Je Anfrage die Bilder, die mitgeschickt wurden. Der zweite
        #: Durchgang soll mehr sehen als der erste — das ist hier prüfbar.
        self.bilder = []
        self.messages = self

    def create(self, *, model, max_tokens, tools, tool_choice, messages):
        werkzeug = tools[0]["name"]
        # An welcher Seite sind wir? Die Reihenfolge der Bilder ist die
        # Reihenfolge der Aufrufe — der Prüfstand zählt die Abschriften.
        text = next(t["text"] for t in messages[0]["content"] if t["type"] == "text")
        self.anfragen.append((werkzeug, text))
        self.bilder.append((werkzeug, [
            t["source"]["data"] for t in messages[0]["content"]
            if t["type"] == "image"
        ]))

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
    # Vier Seiten "rendern", ohne eine echte Datei zu brauchen. Je Seite eine
    # Übersicht und zwei vergrößerte Ausschnitte — genau die Form, die
    # ``_seitenbilder`` aus einem echten Blatt macht.
    seitenlesung._seitenbilder = lambda pfad: [
        seitenlesung.Seitenbild(uebersicht=marke,
                                ausschnitte=[marke + b"-oben", marke + b"-unten"])
        for marke in (b"x", b"y", b"z", b"w")
    ]
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

abschnitt("Der zweite Durchgang sieht mehr als der erste")
# Das ist der Kern der Verbesserung: Ein zweiter Blick auf dieselben
# Bildpunkte findet vor allem das, was schon beim ersten Mal zu sehen war.
# Der zweite Durchgang bekommt deshalb zusätzlich vergrößerte Ausschnitte.
erste_bilder = next(b for w, b in client.bilder if w == "seite_abschreiben")
zweite_bilder = next(b for w, b in client.bilder if w == "seite_pruefen")
pruefe(len(erste_bilder) == 1,
       f"Abschrift bekommt das ganze Blatt: {len(erste_bilder)} Bild(er)")
pruefe(len(zweite_bilder) == 3,
       f"Prüfung bekommt Blatt und zwei Ausschnitte: {len(zweite_bilder)}")
pruefe(erste_bilder[0] == zweite_bilder[0],
       "beide sehen dasselbe Blatt")
pruefe("ZU DEN BILDERN" in prueftext,
       "die Ausschnitte werden erklärt — sonst gelten sie als weitere Blätter")
pruefe("nicht zweimal" in prueftext,
       "…und ausdrücklich nicht als weitere Tage gezählt")

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

abschnitt("Sonstiges und Besuche finden den Weg in den Bericht")
# Sie wurden gelesen und zweimal geprüft — und dann verworfen, weil die
# Pipeline nur Firmeneinträge kennt und der Haupteintrag allein aus dem
# Textfeld der Oberfläche kam. Ein zweimal geprüfter Satz über den Frost am
# Morgen landete im Papierkorb.
from app.services.pipeline import _tagesnotizen  # noqa: E402

pruefe(all("tagesnotiz" in e for e in eintraege),
       "die Tagesnotiz hängt an den Einträgen des Blattes")
notizen = _tagesnotizen(eintraege)
pruefe(len(notizen) == 1,
       f"bei drei Firmen desselben Blattes bleibt EINE Notiz: {len(notizen)}")
pruefe("Bauheizungen" in notizen[0], f"Inhalt übernommen: {notizen[0][:60]}")
pruefe("Besuche:" in notizen[0], "Besuche gekennzeichnet")

# Ein Blatt ohne Sonstiges und Besuche trägt keine Notiz mit.
ohne_notiz = seitenlesung.als_firmeneintraege(
    seitenlesung.Tagesbefund(datum=None, seiten=[1], firmen=[
        seitenlesung.FirmenZeile(firma="Riedel Bau", personen=2)]))
pruefe(all("tagesnotiz" not in e for e in ohne_notiz),
       "ohne Notiz wird kein leeres Feld angehängt")
pruefe(_tagesnotizen(ohne_notiz) == [], "und es kommt keine Zeile heraus")

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

abschnitt("Ein Kopfblatt ohne lesbares Datum beginnt trotzdem einen Tag")
# Vorher hing das allein am Datum: Ein Blatt, dessen Kopfzeile verschmiert
# oder abgeschnitten war, wurde als Fortsetzung des Vortags behandelt — und
# die Arbeitskräfte von Dienstag standen im Bericht von Montag.
montag = seitenlesung.SeitenBefund(
    seite=1, blattseite=1, blatt_nr="243", datum=date(2024, 1, 15),
    firmen=[seitenlesung.FirmenZeile(firma="Riedel Bau", personen=3)],
)
dienstag_ohne_datum = seitenlesung.SeitenBefund(
    seite=2, blattseite=1, blatt_nr="", datum=None,
    firmen=[seitenlesung.FirmenZeile(firma="Goni Bau", personen=5)],
)
getrennt = seitenlesung.zu_tagen([montag, dienstag_ohne_datum], BEKANNT)
pruefe(len(getrennt) == 2,
       f"zwei Tage, obwohl das zweite Datum fehlt: {len(getrennt)}")
pruefe(getrennt[0].datum == date(2024, 1, 15) and getrennt[1].datum is None,
       f"der zweite Tag bleibt ohne Datum: {[t.datum for t in getrennt]}")
pruefe(len(getrennt[0].firmen) == 1,
       f"Montag behält seine eine Firma: {[f.firma for f in getrennt[0].firmen]}")

# Eine echte Fortsetzungsseite (blattseite=2) gehört weiterhin dazu.
fortsetzung = seitenlesung.SeitenBefund(
    seite=2, blattseite=2, blatt_nr="243|2", datum=None,
    firmen=[seitenlesung.FirmenZeile(firma="Riedel Bau", leistung="Schalung")],
)
zusammen = seitenlesung.zu_tagen([montag, fortsetzung], BEKANNT)
pruefe(len(zusammen) == 1, f"Fortsetzung bleibt beim Tag: {len(zusammen)}")

abschnitt("Der Zwischenspeicher unterscheidet nach Lesehilfe")
# Wer das Wochenpaket vor der Projektwahl hochlädt, ließ die Seiten ohne
# Lesehilfe lesen. Die Berichtserzeugung bekam danach genau dieses
# schlechtere Ergebnis zurück, obwohl sie die Firmen inzwischen kannte.
client = stelle_pruefstand_bereit()
datei = STORAGE / "tagebuch.pdf"
datei.write_bytes(b"kein echtes PDF")
asyncio.run(seitenlesung.lies_seiten(datei))
ohne_hilfe = len([w for w, _ in client.anfragen if w == "seite_abschreiben"])
asyncio.run(seitenlesung.lies_seiten(datei, BEKANNT))
mit_hilfe = len([w for w, _ in client.anfragen if w == "seite_abschreiben"])
pruefe(mit_hilfe > ohne_hilfe,
       f"mit Lesehilfe wird neu gelesen ({ohne_hilfe} -> {mit_hilfe})")
vorher = mit_hilfe
asyncio.run(seitenlesung.lies_seiten(datei, BEKANNT))
nachher = len([w for w, _ in client.anfragen if w == "seite_abschreiben"])
pruefe(nachher == vorher,
       f"derselbe Aufruf fragt kein zweites Mal ({vorher} -> {nachher})")
seitenlesung.vergiss(datei)
asyncio.run(seitenlesung.lies_seiten(datei, BEKANNT))
pruefe(len([w for w, _ in client.anfragen if w == "seite_abschreiben"]) > nachher,
       "nach dem Vergessen wird wieder gelesen")

abschnitt("Nur die Tage des Berichts")
# Ein handschriftliches Bautagebuch enthält meist die ganze Woche. Bisher
# wurde das Zieldatum hier nicht beachtet: Im Bericht vom Montag stand die
# Arbeit der ganzen Woche, mit doppelten Firmen und aufaddierten Personen.
from app.services.pdf_extraction import _tage_fuer  # noqa: E402

woche = seitenlesung.zu_tagen(befunde, BEKANNT)
gewaehlt = _tage_fuer(woche, date(2024, 1, 16))
pruefe(len(gewaehlt) == 1 and gewaehlt[0].datum == date(2024, 1, 16),
       f"nur der Dienstag: {[t.datum for t in gewaehlt]}")
pruefe(len(_tage_fuer(woche, None)) == len(woche),
       "ohne Zieldatum bleiben alle Tage")
pruefe(len(_tage_fuer(woche, date(2024, 3, 1))) == len(woche),
       "passt kein Tag, wird nicht gefiltert — ein leerer Bericht wäre "
       "schlimmer als einer mit Hinweis")

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
                       ("32.01.2024", None),
                       # Aus echtem Erkennungstext: ein Punkt ist verloren.
                       ("Di. 02 04.2024", date(2024, 4, 2)),
                       ("Mi. 03042024", date(2024, 4, 3))]:
    pruefe(seitenlesung._als_datum(text) == erwartet,
           f"{text!r} -> {seitenlesung._als_datum(text)} statt {erwartet}")

abschnitt("Vorübergehende Störungen werden wiederholt")


class Stoerung(Exception):
    pass


def wackliger_client(fehlschlaege: int):
    """Ein Client, der die ersten Anfragen mit Überlastung abweist."""

    class Wacklig(PruefstandClient):
        def __init__(self):
            super().__init__()
            self.abgewiesen = 0

        def create(self, **kwargs):
            if self.abgewiesen < fehlschlaege:
                self.abgewiesen += 1
                raise Stoerung("Error code: 529 - overloaded_error")
            return super().create(**kwargs)

    return Wacklig()


seitenlesung.WARTEN_SEKUNDEN = 0.01     # der Test soll nicht warten
wacklig = wackliger_client(2)
seitenlesung.verfuegbar = lambda: True
seitenlesung._client = lambda: wacklig
seitenlesung.vergiss()
befunde_wacklig = asyncio.run(
    seitenlesung.lies_seiten(Path("nicht-vorhanden.pdf"), BEKANNT))
pruefe(befunde_wacklig and not befunde_wacklig[0].fehler,
       f"nach zwei Abweisungen kommt die Seite durch: "
       f"{befunde_wacklig[0].fehler if befunde_wacklig else 'nichts'}")
pruefe(wacklig.abgewiesen == 2, f"zweimal abgewiesen: {wacklig.abgewiesen}")

# Ein falscher Schlüssel wird nicht wiederholt — der ist beim dritten Versuch
# genauso falsch wie beim ersten.
pruefe(not seitenlesung._vorruebergehend(
           Stoerung("Error code: 401 - authentication_error")),
       "falscher Schlüssel gilt nicht als vorübergehend")
pruefe(seitenlesung._vorruebergehend(Stoerung("Read timed out")),
       "Zeitüberschreitung gilt als vorübergehend")
pruefe(not seitenlesung._vorruebergehend(Stoerung("credit balance too low")),
       "leeres Guthaben gilt nicht als vorübergehend")

# Der Umgang mit der Schnittstelle steht an einer Stelle — auch die
# Besprechungsanalyse und die Formblatt-Erkennung benutzen ihn.
from app.services import schnittstelle  # noqa: E402

pruefe(seitenlesung.fehlertext is schnittstelle.fehlertext,
       "die Fehlerdeutung ist dieselbe für alle Wege")
for meldung, erwartet in [
    ("Error code: 401 - authentication_error", "Schlüssel"),
    ("Error code: 403 - permission_error", "Modell"),
    ("credit balance is too low", "Guthaben"),
    ("Error code: 529 - overloaded_error", "überlastet"),
    ("Connection error: getaddrinfo failed", "Verbindung"),
]:
    text = schnittstelle.fehlertext(Stoerung(meldung))
    pruefe(erwartet in text, f"{meldung[:28]!r} -> {text[:50]!r}")

# Nach der letzten Wiederholung wird der Fehler durchgelassen, statt still
# ein leeres Ergebnis zu liefern.
zaehler = {"n": 0}


def immer_ueberlastet():
    zaehler["n"] += 1
    raise Stoerung("Error code: 529 - overloaded_error")


try:
    asyncio.run(schnittstelle.mit_wiederholung(
        immer_ueberlastet, versuche=3, warten=0.01))
    fehler.append("dauerhafte Überlastung müsste am Ende durchschlagen")
except Stoerung:
    pruefe(zaehler["n"] == 3, f"genau drei Versuche: {zaehler['n']}")

abschnitt("Die Ausschnitte zeigen die Handschrift wirklich größer")
# Das ist der Kern der Auflösungsänderung, und er lässt sich ohne Schlüssel
# nachrechnen: Die Modelle rechnen Bilder über 1568 Pixel selbst herunter.
# Ein ganzes A4-Blatt hat auf der langen Kante also höchstens 1540 Pixel und
# damit rund 134 dpi. Ein Ausschnitt über die halbe Blatthöhe hat dagegen die
# BREITE als lange Kante — dieselben 1540 Pixel ergeben dort rund 190 dpi.
import io as _io  # noqa: E402

from PIL import Image as _Image  # noqa: E402


def _groesse(daten: bytes) -> tuple[int, int]:
    with _Image.open(_io.BytesIO(daten)) as bild:
        return bild.size


BLATT = STORAGE / "blatt.png"
_Image.new("RGB", (2480, 3508), "white").save(BLATT)      # A4 hochkant, 300 dpi

seite = ECHTE_SEITENBILDER(BLATT)[0]
breite_uebersicht = _groesse(seite.uebersicht)[0]
pruefe(max(_groesse(seite.uebersicht)) <= seitenlesung.MAX_KANTE,
       f"die Übersicht bleibt unter der Grenze: {_groesse(seite.uebersicht)}")
pruefe(len(seite.ausschnitte) == 2,
       f"zwei überlappende Ausschnitte: {len(seite.ausschnitte)}")
breite_ausschnitt = _groesse(seite.ausschnitte[0])[0]
pruefe(breite_ausschnitt > breite_uebersicht * 1.3,
       f"der Ausschnitt zeigt dieselbe Blattbreite mit mehr Bildpunkten "
       f"({breite_uebersicht} -> {breite_ausschnitt})")
pruefe(all(max(_groesse(a)) <= seitenlesung.MAX_KANTE
           for a in seite.ausschnitte),
       "auch die Ausschnitte bleiben unter der Grenze — sonst würden sie "
       "drüben wieder verkleinert")

# Ein querformatiges Foto wird andersherum geteilt, damit derselbe Gewinn
# entsteht.
QUER = STORAGE / "quer.png"
_Image.new("RGB", (3508, 2480), "white").save(QUER)
quer = ECHTE_SEITENBILDER(QUER)[0]
pruefe(len(quer.ausschnitte) == 2, "querformatiges Blatt wird auch geteilt")
pruefe(_groesse(quer.ausschnitte[0])[1] > _groesse(quer.uebersicht)[1] * 1.3,
       "beim Querformat gewinnt die Höhe")

# Ein fast quadratisches Bild gewinnt durch das Teilen nichts.
QUADRAT = STORAGE / "quadrat.png"
_Image.new("RGB", (2000, 1900), "white").save(QUADRAT)
pruefe(ECHTE_SEITENBILDER(QUADRAT)[0].ausschnitte == [],
       "fast quadratisch: keine Ausschnitte, das brächte nichts")

# Eine kaputte Datei darf die Seite nicht verschlucken.
KAPUTT = STORAGE / "kaputt.png"
KAPUTT.write_bytes(b"kein Bild")
notfall = ECHTE_SEITENBILDER(KAPUTT)
pruefe(len(notfall) == 1 and notfall[0].uebersicht == b"kein Bild",
       "unlesbares Bild wird unverändert weitergereicht statt verworfen")

print()
print(f"{ok} Pruefungen ok, {len(fehler)} Fehler")
if fehler:
    print("FEHLER:")
    for f in fehler:
        print(" -", f)
    sys.exit(1)
