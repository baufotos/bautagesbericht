"""Prueft das Auslesen gedruckter Firmen-Formblaetter aus einem Scan.

Der Text hier ist echte Ausgabe der Windows-Texterkennung an einem
Bautagesbericht der Firma RF Fassaden — samt ihrer Fehler: "4.OG" wurde zu
"406", "Leistungsergebnisse" zu "Leistungserqebnisse", und auf vier von fuenf
Seiten fehlt die Ueberschrift ganz. Genau daran muss der Parser sich bewaehren.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.services.pdf_extraction import parse_formblatt  # noqa: E402

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


# Mit Ueberschrift — der gute Fall.
MIT_UEBERSCHRIFT = """Ident-Nr.
Formblatt
Bautagesbericht
F0377_RF
Bautagesbericht- Nr
76
Kommission:
K 30159
Bauvorhaben:
Hambur Neubau Besucherzentrum DESYUM
Abschnitt.
406. Ost Achse 3 A-D
Datum:
Sa. 0604.2024
Witterunq
Sonne
Regen
Temperatur: H 8' T 30
bewölkt
Verantwortlicher Bauleiter: Herr Luithle
Anzahl der Beschäftigten Arbeiter: 8
Arbeitszeit von:
7:00
bis:
Uhr
Name
Vorarb.
Monteur
8 Mitarbeiter
1
7
Leistungserqebnisse:
Leistungsschutz Schutzfolien
3.0G. An den Fensterbändern fehlende Schutzfolien auf die Fensterprofile geklebt.
4.0G. Dachterrasse PR- Fassade Ost,Achse 3 A-D
Bemerkungen:
Uh erschrift RF
Unterschrift Bauherr/Stellvertreter
erstellt 31.01.2020 CZ
Seite 1/1"""

# Ohne Ueberschrift — so kommt es meistens aus der Texterkennung.
OHNE_UEBERSCHRIFT = MIT_UEBERSCHRIFT.replace("Leistungserqebnisse:\n", "")


print("─── Formblatt mit Ueberschrift ───")

eintraege = parse_formblatt(MIT_UEBERSCHRIFT)
gleich(len(eintraege), 1, "ein Eintrag je Formblatt")
e = eintraege[0]
gleich(e["personen"], 8, "Arbeiterzahl aus der Kopfzeile")
gleich(e["firma"], "RF", "Firma aus der Unterschriftszeile")
pruefe("Ost Achse 3 A-D" in e["ort"], f"Ort uebernommen (war {e['ort']!r})")
pruefe("Schutzfolien" in e["leistung"], "Leistungstext uebernommen")
pruefe("Dachterrasse" in e["leistung"], "auch die zweite Zeile")
gleich(e["quelle"], "ocr", "als maschinell gelesen markiert")

# Der Kopf gehoert NICHT in den Leistungstext.
for fremd in ("Kommission", "Bauvorhaben", "Besucherzentrum", "Witterunq",
              "Mitarbeiter", "Bauleiter", "Seite 1/1", "erstellt"):
    pruefe(fremd not in e["leistung"],
           f"'{fremd}' steht nicht im Leistungstext")


print("─── Formblatt ohne Ueberschrift ───")

eintraege = parse_formblatt(OHNE_UEBERSCHRIFT)
gleich(len(eintraege), 1, "auch ohne Ueberschrift ein Eintrag")
e = eintraege[0]
gleich(e["personen"], 8, "Arbeiterzahl weiterhin")
pruefe("Schutzfolien" in e["leistung"],
       f"Leistungstext ueber den Rahmen erkannt (war {e['leistung'][:60]!r})")
for fremd in ("Kommission", "Besucherzentrum", "Bauleiter"):
    pruefe(fremd not in e["leistung"], f"'{fremd}' bleibt draussen")


print("─── Personenzahl in anderen Schreibweisen ───")

for text, soll in [
    ("Anzahl der Beschäftigten Arbeiter: 12\nArbeiten am Dach ausgefuehrt heute", 12),
    ("Arbeiter: 5\nMontage der Fassade an der Westseite erledigt", 5),
    ("Fa. Test (7 Mann)\nArbeiten an der Fassade heute ausgefuehrt", 7),
    ("3 Mitarbeiter\nBewehrung der Decke ueber UG eingebaut heute", 3),
]:
    eintraege = parse_formblatt(text)
    pruefe(eintraege and eintraege[0]["personen"] == soll,
           f"{soll} Personen erkannt (war {eintraege[0]['personen'] if eintraege else '-'})")


print("─── Wann NICHTS zurueckgegeben wird ───")

gleich(parse_formblatt(""), [], "leerer Text")
gleich(parse_formblatt("Rechnung Nr. 4711\nBetrag 1.200,00 EUR"), [],
       "kein Bautagesbericht -> kein Eintrag")


print("─── Firmenname ───")

mit_rechtsform = MIT_UEBERSCHRIFT.replace(
    "Uh erschrift RF", "Meyer Bau GmbH & Co. KG")
gleich(parse_formblatt(mit_rechtsform)[0]["firma"], "Meyer Bau GmbH & Co. KG",
       "Rechtsform schlaegt Unterschriftszeile")

# Die Unterschriftszeile ohne Kürzel — genau so kam ein Blatt aus einem
# echten Stapel an, während die vier anderen desselben Tages "RF" trugen.
# Dann bleibt die Formularkennung: Die Nummer gehört dem Vordruck, der
# Buchstabenteil dahinter der Firma, die ihn herausgibt.
ohne_unterschrift = MIT_UEBERSCHRIFT.replace("Uh erschrift RF", "Unterschrift")
gleich(parse_formblatt(ohne_unterschrift)[0]["firma"], "RF",
       "Firma aus der Formularkennung, wenn die Unterschriftszeile schweigt")

# Fehlt auch die, wird nicht geraten.
ohne_hinweis = ohne_unterschrift.replace("F0377_RF", "Bautagesbericht")
gleich(parse_formblatt(ohne_hinweis)[0]["firma"], "Firma bitte ergänzen",
       "ohne jeden Anhaltspunkt wird nicht geraten")

pruefe("Bauherr" not in parse_formblatt(MIT_UEBERSCHRIFT)[0]["firma"],
       "'Unterschrift Bauherr' wird nicht als Firma gelesen")

print("─── Was den Bericht aufhaelt und was nicht ───")

from app.services.pipeline import _haelt_auf  # noqa: E402

ocr_hinweis = {"feld": "firmen", "problem": "Aus einem Scan gelesen",
               "quelle_datei": "", "blockiert": False}
echte_warnung = {"feld": "dateien", "problem": "Datei nicht gefunden",
                 "quelle_datei": "x.pdf"}

pruefe(not _haelt_auf([]), "ohne Meldung laeuft es durch")
pruefe(not _haelt_auf([ocr_hinweis]),
       "der Scan-Hinweis allein haelt den Bericht NICHT auf")
pruefe(not _haelt_auf([ocr_hinweis, dict(ocr_hinweis)]),
       "auch mehrere Hinweise nicht")
pruefe(_haelt_auf([echte_warnung]), "eine fehlende Datei schon")
pruefe(_haelt_auf([ocr_hinweis, echte_warnung]),
       "Hinweis plus echte Warnung: haelt auf")
# Ohne das Feld gilt die alte, vorsichtige Regel.
pruefe(_haelt_auf([{"feld": "x", "problem": "y"}]),
       "Meldung ohne Kennzeichnung haelt vorsichtshalber auf")

print()
if fehler:
    print(f"{ok} Pruefungen ok, {len(fehler)} Fehler:")
    for f in fehler:
        print("  -", f)
    raise SystemExit(1)
print(f"{ok} Pruefungen ok, 0 Fehler")
