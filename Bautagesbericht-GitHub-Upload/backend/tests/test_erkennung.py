"""Erkennung der Unternehmensberichte — an echten Vorlagen festgehalten.

Die Textbausteine hier sind nicht erfunden: Sie stammen Wort für Wort aus dem,
was die Windows-Texterkennung auf den eingereichten Blättern gelesen hat.
Damit sind die Eigenheiten mit dabei, die im Labor nie auffallen —
"Leistungserqebnisse" statt "Leistungsergebnisse", "406." statt "4.OG.",
"Uh erschrift" statt "Unterschrift".

Geprüft werden drei Dinge, die im Bericht an den Bauherrn landen und dort
falsch aussähen:

1. Geschossangaben. "3.0G." ist keine Zahl, sondern das dritte Obergeschoss.
2. Der Firmenname. "RF" ist die Kurzform von "RF Fassaden GmbH".
3. Ob überhaupt etwas gelesen wurde — oder nur der leere Vordruck.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STORAGE = Path(tempfile.gettempdir()) / "hpp-erkennungstest"
if STORAGE.exists():
    shutil.rmtree(STORAGE)
STORAGE.mkdir(parents=True)

WIN = str(STORAGE).replace("\\", "/")
os.environ["BTB_DATABASE_URL"] = f"sqlite:///{WIN}/test.db"
os.environ["BTB_UPLOAD_DIR"] = f"{WIN}/uploads"
os.environ["BTB_OUTPUT_DIR"] = f"{WIN}/output"

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.services import bautext, firmennamen  # noqa: E402
from app.services.pdf_extraction import parse_formblatt  # noqa: E402

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
# Die echten Vorlagen
# ─────────────────────────────────────────────────────────────────────────────

#: Blatt 1 aus "K30159 … KW 14", gelesen von der Windows-Texterkennung.
#: Ein gedrucktes Formblatt der RF Fassaden — Datum und Leistung stehen
#: maschinengeschrieben darauf, nur die Unterschrift ist handschriftlich.
RF_BLATT = (
    "Ident-Nr.\nFormblatt\nBautagesbericht\nF0377_RF\nBautagesbericht- Nr\n76\n"
    "Kommission:\nK 30159\nBauvorhaben:\n"
    "Hambur Neubau Besucherzentrum DESYUM\nAbschnitt.\n406. Ost Achse 3 A-D\n"
    "Datum:\nSa. 0604.2024\nWitterunq\nSonne\nRegen\nFrost\n"
    "Temperatur: H 8' T 30\nWind\nSchnee\nSonstiges\nbewölkt\n"
    "Verantwortlicher Bauleiter: Herr Luithle\n"
    "Anzahl der Beschäftigten Arbeiter: 8\nArbeitszeit von:\n7:00\nbis:\n17 n\n"
    "Uhr\nName\nVorarb.\nMonteur\n8 Mitarbeiter\n1\n7\nLeistungserqebnisse:\n"
    "Leistungsschutz Schutzfolien\n"
    "3.0G. An den Fensterbändern fehlende Schutzfolien auf die Fensterprofile "
    "geklebt.\n"
    "4.0G. An der PR-Fassade Westseite Achse 1 A-D fehlende Schutzfolien auf die\n"
    "Fassadenprofilegeklebt.\n"
    "4.0G. Dachterrasse PR- Fassade Ost,Achse 3 A-D\n"
    "Einmessen und anzeichnen der Achsen für die Monta e der Unterkonstruktion.\n"
    "Bemerkungen:\nUh erschrift RF\nUnterschrift Bauherr/Stellvertreter\n"
    "erstellt 31.01.2020 CZ\nRev 01\nSeite 1/1"
)

#: Blatt 1 aus "2024-KW03", einem handschriftlichen Riedel-Bautagebuch. Die
#: Erkennung hat ausschließlich den gedruckten Vordruck gelesen — von der
#: Schreibschrift kein Wort. Genau daraus entstand früher ein Eintrag, dessen
#: "Leistung" die Liste der Spaltenüberschriften war.
RIEDEL_NUR_VORDRUCK = (
    "Riedel\nBau\nBautagebuch\nDatum:\nBlatt-Nr.\nSeite 1/2\nBaustelle:\n"
    "71/20874\nBau-Nr.:\nArbeitszeit:\nWetter\nTemperatur:\n12h\nmin\nmax\n"
    "Niederschlag:\nRegenschauer\nDauerregen\nSchneefall\nLuftbewegung:\n"
    "still\nmäßiger Wind\nstarker Wind / Sturm\nArbeitskräfte\nPolier\n"
    "Werkpolier\nVorarbeiter\nMaurer\nZimmerer\nBetonbauer\nAzubis\n"
    "Maschinenführer\nGeräte\nBaustoffe\nRadlader\nKräne\nKompressor\n"
    "Verdichtungsgeräte\nLKW\nBetonstahl\nBeton\nNachunternehmer\nFirma\n"
    "Anzahl\nSonstiges\nBesuche"
)

#: Dieselbe Datei, Seite 2. Hier steht zusätzlich das gedruckte Logo, was den
#: Vordruckanteil der Einzelseite drückt — deshalb entscheidet die Prüfung
#: über das ganze Dokument und nicht über die Seite.
RIEDEL_SEITE_2 = (
    "Riedel\nBau\nBautagebuch\nBlatt-Nr.\nSeite 2/2\nAusgeführte Arbeiten\n"
    "Polier\nBauleiter\nBauherr"
)


abschnitt("Geschossangaben geraderücken")
for roh, erwartet in [
    ("406. Ost Achse 3 A-D", "4.OG. Ost Achse 3 A-D"),
    ("3.0G. An den Fensterbändern", "3.OG. An den Fensterbändern"),
    ("4.0G. Dachterrasse", "4.OG. Dachterrasse"),
    ("1.U6 WC-Bereich", "1.UG WC-Bereich"),
    ("E6 Küche", "EG Küche"),
    ("Tr.R. Nord Wände", "Trh. Nord Wände"),
    ("Achse 1 - 4 / A - D", "Achse 1-4/A-D"),
    # Der Punkt fehlt: kommt auf gescannten Formblättern ständig vor.
    ("4 OG. West Achse 1 A-D", "4.OG. West Achse 1 A-D"),
    ("1 UG Keller", "1.UG Keller"),
    ("Arbeitszeit 7oo bis 18oo", "Arbeitszeit 7:00 bis 18:00"),
    ("Temperatur: H 8' T 3°", "Temperatur: H 8° T 3°"),
    # Was schon richtig ist, bleibt richtig.
    ("4.OG. bleibt 4.OG.", "4.OG. bleibt 4.OG."),
    # Und was keine Geschossangabe ist, wird keine. Die Hausnummer ist der
    # Grund, warum die Regel ohne Punkt echte Buchstaben verlangt: "4 06"
    # wäre sonst ein viertes Obergeschoss.
    ("Notkestraße 406", "Notkestraße 406"),
    ("Notkestraße 4 06", "Notkestraße 4 06"),
    ("Achse 4 Ost", "Achse 4 Ost"),
    ("12 Ordner", "12 Ordner"),
]:
    ergebnis = bautext.geraderuecken(roh)
    pruefe(ergebnis == erwartet, f"{roh!r} -> {ergebnis!r} statt {erwartet!r}")


abschnitt("Gedrucktes Formblatt: Firma, Ort, Leistung")
eintraege = parse_formblatt(RF_BLATT)
pruefe(len(eintraege) == 1, f"ein Eintrag: {len(eintraege)}")
eintrag = eintraege[0]
pruefe(eintrag["personen"] == 8, f"acht Arbeiter: {eintrag['personen']}")
pruefe(eintrag["ort"] == "4.OG. Ost Achse 3 A-D", f"Ort: {eintrag['ort']!r}")
pruefe("3.OG." in eintrag["leistung"], "Geschoss in der Leistung geradegerückt")
pruefe("3.0G." not in eintrag["leistung"], "keine Null mehr im Geschoss")
pruefe("Schutzfolien" in eintrag["leistung"], "Leistungstext übernommen")
# Ohne Stammdaten bleibt das Kürzel stehen — das ist ehrlicher als ein
# geratener Name, und die Formularnummer wird jedenfalls nicht zur Firma.
pruefe(eintrag["firma"] in ("RF", "RF Fassaden"),
       f"Firma ohne Stammdaten: {eintrag['firma']!r}")
pruefe("F0377" not in eintrag["firma"], "Formularnummer wird nicht zur Firma")

abschnitt("Mit den Firmen der Baustelle wird aus dem Kürzel der volle Name")
mit = parse_formblatt(RF_BLATT, bekannte=("RF Fassaden GmbH", "Lindner Polska"))
pruefe(mit[0]["firma"] == "RF Fassaden GmbH", f"Firma: {mit[0]['firma']!r}")
# Und es wird nicht geraten, wenn zwei Firmen gleich anfangen.
zweideutig = parse_formblatt(RF_BLATT, bekannte=("RF Fassaden GmbH", "RF Metallbau"))
pruefe(zweideutig[0]["firma"] == "RF",
       f"bei zwei Möglichkeiten nicht geraten: {zweideutig[0]['firma']!r}")

abschnitt("Nur der Vordruck gelesen — das darf kein Eintrag werden")
pruefe(bautext.vordruckanteil(RIEDEL_NUR_VORDRUCK) > 0.8,
       f"Vordruckanteil: {bautext.vordruckanteil(RIEDEL_NUR_VORDRUCK):.2f}")
pruefe(bautext.vordruckanteil(RF_BLATT) < 0.5,
       f"echtes Blatt niedrig: {bautext.vordruckanteil(RF_BLATT):.2f}")
pruefe(bautext.handschrift_unlesbar(
           [RIEDEL_NUR_VORDRUCK, RIEDEL_SEITE_2], False),
       "Riedel-Bautagebuch als unlesbar erkannt")
pruefe(not bautext.handschrift_unlesbar([RF_BLATT], True),
       "RF-Formblatt gilt als lesbar")
# Das Gegenargument schlägt alles: Wo ein Datum gelesen wurde, ist Inhalt da.
pruefe(not bautext.handschrift_unlesbar([RIEDEL_NUR_VORDRUCK], True),
       "mit gefundenem Datum wird nichts verworfen")
pruefe(bautext.handschrift_unlesbar([], False), "leeres Dokument ist unlesbar")

hinweis = bautext.unlesbar_hinweis("2024-KW03.pdf", "einstellungen.txt")
pruefe("2024-KW03.pdf" in hinweis, "Hinweis nennt die Datei")
pruefe("Schreibschrift" in hinweis, "Hinweis nennt den Grund")
pruefe("einstellungen.txt" in hinweis, "Hinweis nennt den Weg")


abschnitt("Firmennamen zusammenführen")
for a, b, gleich in [
    ("Riedd Bau", "Riedel Bau", True),      # verlesene Schleife
    ("Miro Ventig", "Miro Venlig", True),   # t/l verwechselt
    ("Riedel Bau:", "Riedel Bau", True),    # Doppelpunkt der Überschrift
    ("Riedel Bau GmbH", "Riedel Bau", True),
    ("Fa. Riedel Bau", "Riedel Bau", True),
    ("Kraft Gerüst", "Kraft Geruest", True),
    ("Ott", "Ost", False),                  # zu kurz zum Vergleichen
]:
    pruefe(firmennamen.gleiche_firma(a, b) == gleich,
           f"{a!r} / {b!r}: {firmennamen.aehnlichkeit(a, b):.2f}")

zuordnung, warnungen = firmennamen.vereinheitliche(
    ["Riedd Bau", "Riedel Bau", "Riedel Bau:", "Miro Ventig", "Miro Venlig",
     "Goni Bau"]
)
pruefe(len({v for v in zuordnung.values()}) == 3,
       f"aus sechs Schreibweisen drei Firmen: {sorted(set(zuordnung.values()))}")
pruefe(zuordnung["Riedd Bau"] == "Riedel Bau",
       f"häufigste Schreibweise gewinnt: {zuordnung['Riedd Bau']!r}")
pruefe(not warnungen, f"keine Warnung nötig: {warnungen}")

abschnitt("Zwei bekannte Firmen werden nie vereint")
zuordnung, _ = firmennamen.vereinheitliche(
    ["Meier Bau", "Meyer Bau"], ["Meier Bau", "Meyer Bau GmbH"])
pruefe(zuordnung["Meier Bau"] == "Meier Bau", f"{zuordnung['Meier Bau']!r}")
pruefe(zuordnung["Meyer Bau"] == "Meyer Bau GmbH", f"{zuordnung['Meyer Bau']!r}")
pruefe(zuordnung["Meier Bau"] != zuordnung["Meyer Bau"],
       "zwei Firmen bleiben zwei Firmen")

abschnitt("Kurzform wird zum vollen Namen, aber nur wenn eindeutig")
zuordnung, _ = firmennamen.vereinheitliche(["Miro"], ["Miro Ventig", "Goni Bau"])
pruefe(zuordnung["Miro"] == "Miro Ventig", f"{zuordnung['Miro']!r}")
zuordnung, _ = firmennamen.vereinheitliche(["Miro"], ["Miro Ventig", "Miro Bau"])
pruefe(zuordnung["Miro"] == "Miro", f"zweideutig bleibt stehen: {zuordnung['Miro']!r}")

abschnitt("Platzhalter dürfen nicht in den Bestand")
for name in ["(Handschrift/Scan: x.pdf)", "Firma bitte ergänzen", "Ried[?]", "RF"]:
    pruefe(firmennamen._merkwuerdig(name), f"{name!r} wird nicht gemerkt")
for name in ["Riedel Bau", "Miro Ventig", "RF Fassaden GmbH"]:
    pruefe(not firmennamen._merkwuerdig(name), f"{name!r} darf gemerkt werden")

abschnitt("Jedes Bildformat, das die Oberfläche annimmt, wird auch gelesen")
# Die Oberfläche lässt HEIC, AVIF und TIF zur Auswahl zu — die Auswertung
# hatte dafür eine eigene, kürzere Aufzählung. Ein mit dem iPhone
# abfotografierter Bericht kam damit an, wurde stillschweigend verworfen und
# der Bericht entstand ohne eine einzige Firma. Beide Listen müssen dieselbe
# sein, und die eine Quelle dafür ist services/bildformate.
import asyncio  # noqa: E402

from app.services import bildformate, pdf_extraction  # noqa: E402

for endung in (".heic", ".heif", ".avif", ".tif", ".tiff", ".webp", ".jpg",
               ".jpeg", ".png", ".bmp", ".gif"):
    pruefe(endung in bildformate.BILD_ENDUNGEN, f"{endung} gilt als Bild")

# Und die Auswertung nimmt sie wirklich an: Ohne Schlüssel landet ein Bild im
# Zweig "kann auf diesem Rechner nicht gelesen werden" — und ausdrücklich
# NICHT bei "gibt einfach nichts zurück", was vorher geschah.
gemerkt = pdf_extraction.settings.anthropic_api_key
pdf_extraction.settings.anthropic_api_key = ""
try:
    for endung in (".heic", ".avif", ".tif", ".webp"):
        probe = STORAGE / f"bericht{endung}"
        probe.write_bytes(b"kein echtes Bild")
        ergebnis = asyncio.run(pdf_extraction.extract_from_file(probe))
        pruefe(len(ergebnis) == 1,
               f"{endung}: ein Hinweis-Eintrag statt nichts ({len(ergebnis)})")
        pruefe(bool(ergebnis) and bool(ergebnis[0].get("leistung")),
               f"{endung}: mit einem Text, der sagt, was zu tun ist")
finally:
    pdf_extraction.settings.anthropic_api_key = gemerkt

abschnitt("Wenn nichts zu lesen war, bleibt der Bericht vorzeigbar")
# Vorher stand die ganze Erklaerung im Feld "Leistung" eines Berichts, der an
# den Bauherrn geht: "Von 2024-KW03_2024-01-16.pdf konnte nur der gedruckte
# Vordruck gelesen werden ... Anthropic-Schluessel ... einstellungen.txt ...".
# Eine Konfigurationsmeldung als Bautaetigkeit. Der Grund gehoert in die
# Warnung der Oberflaeche, wo der Anwender etwas tun kann.
from app.services.pdf_extraction import (  # noqa: E402
    PLATZHALTER_FIRMA,
    PLATZHALTER_LEISTUNG,
    platzhalter,
)
from app.services.pipeline import _namen_pruefen  # noqa: E402

eintraege = platzhalter("Von „x.pdf“ konnte nur der gedruckte Vordruck "
                        "gelesen werden. Anthropic-Schluessel fehlt.")
pruefe(len(eintraege) == 1, "genau ein Platzhalter-Eintrag")
eintrag = eintraege[0]
pruefe(eintrag["firma"] == PLATZHALTER_FIRMA,
       f"kurzer Firmen-Platzhalter: {eintrag['firma']!r}")
pruefe(eintrag["leistung"] == PLATZHALTER_LEISTUNG,
       f"kurze Leistung: {eintrag['leistung']!r}")
pruefe(len(eintrag["leistung"]) < 40,
       f"die Leistung ist eine Zeile, keine Anleitung ({len(eintrag['leistung'])} Zeichen)")
pruefe("Anthropic" not in eintrag["leistung"] and "einstellungen" not in eintrag["leistung"],
       "kein Konfigurationshinweis im Dokumentfeld")
pruefe("Anthropic" in eintrag["hinweis"], "der Grund haengt am Eintrag")

# Und die Pipeline macht daraus die Warnung.
warnungen = []
_namen_pruefen(list(eintraege), (), warnungen)
firmenwarnungen = [w for w in warnungen if w["feld"] == "firmen"]
pruefe(any("Anthropic" in w["problem"] for w in firmenwarnungen),
       f"der Grund steht in der Warnung: {[w['problem'][:50] for w in firmenwarnungen]}")

# Fuenf unlesbare Blaetter einer Woche geben nicht fuenf Mal denselben Satz.
viele = platzhalter("derselbe Grund") * 5
warnungen = []
_namen_pruefen(viele, (), warnungen)
pruefe(len([w for w in warnungen if "derselbe Grund" in w["problem"]]) == 1,
       "derselbe Grund wird nur einmal gemeldet")

# Der Platzhalter darf nicht als Firma in den Bestand wandern.
pruefe(firmennamen._merkwuerdig(PLATZHALTER_FIRMA),
       "Platzhalter wird nicht als Firma gemerkt")

abschnitt("Die Anweisung an die Bilderkennung kennt Tag und Baustelle")
# Die Grundanweisung sagt "nimm alle Firmen aller Tage auf". Fuer ein Blatt,
# das fuer EINEN Tag hochgeladen wurde, ist das falsch: Im Bericht vom Montag
# stand dann die Arbeit der ganzen Woche.
from datetime import date as _date  # noqa: E402

grund = pdf_extraction._ocr_anweisung()
pruefe(grund == pdf_extraction.OCR_ANWEISUNG,
       "ohne Zusaetze bleibt es die Grundanweisung")

mit_tag = pdf_extraction._ocr_anweisung(ziel=_date(2024, 1, 15))
pruefe("15.01.2024" in mit_tag, "der Tag steht in der Anweisung")
pruefe("NUR die Firmen dieses einen Tages" in mit_tag,
       "…und ausdruecklich, dass nur er gemeint ist")
pruefe("kein Datum zu lesen" in mit_tag,
       "…aber ohne lesbares Datum wird nichts verworfen")

mit_firmen = pdf_extraction._ocr_anweisung(("Riedel Bau", "Miro Ventig"))
pruefe("Riedel Bau" in mit_firmen and "Miro Ventig" in mit_firmen,
       "die Firmen der Baustelle sind Lesehilfe — im Bilderzweig fehlten sie")
pruefe("keine Auswahlliste" in mit_firmen,
       "…als Hilfe formuliert, damit keine neue Firma umgedeutet wird")

print()
print(f"{ok} Pruefungen ok, {len(fehler)} Fehler")
if fehler:
    print("FEHLER:")
    for f in fehler:
        print(" -", f)
    sys.exit(1)
