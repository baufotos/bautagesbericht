"""Rauchtest: Projektbericht — Nummerierung, Erzeuger, Endpunkte, Historie."""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Eigene Ablage im Temp-Ordner: Der Test legt Datenbank, Uploads und erzeugte
# Dokumente an — die echte storage/ bleibt unberuehrt.
STORAGE = Path(tempfile.gettempdir()) / "hpp-test-projektbericht"
if STORAGE.exists():
    shutil.rmtree(STORAGE)
STORAGE.mkdir(parents=True)

WIN = str(STORAGE).replace("\\", "/")
os.environ["BTB_DATABASE_URL"] = f"sqlite:///{WIN}/test.db"
os.environ["BTB_UPLOAD_DIR"] = f"{WIN}/uploads"
os.environ["BTB_OUTPUT_DIR"] = f"{WIN}/output"

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.main import app  # noqa: E402
from app.services import projektbericht_generation as pb  # noqa: E402
from app.services import projektbericht_gliederung as gl  # noqa: E402

ok = 0
fehler: list[str] = []


def pruefe(bedingung, text):
    global ok
    if bedingung:
        ok += 1
    else:
        fehler.append(text)


def foto(farbe=(140, 150, 160), groesse=(1200, 1600)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", groesse, farbe).save(puffer, format="JPEG", quality=85)
    return puffer.getvalue()


def teile(inhalt: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(inhalt)) as z:
        return {n: z.read(n).decode("utf-8", "replace")
                for n in z.namelist() if n.endswith(".xml")}


print("─── (a) Nummerierung: leere Kapitel entfallen ───")

# Nur zwei Kapitel aus „Ablauf“ befuellt — genau der Fall des Originals:
# „Fortschritt“ bleibt leer, „Verzögerungen“ muss dadurch zu 2.2 werden.
kapitel = gl.nummeriere({
    "meilensteine": "Rahmenterminplan",
    "verzoegerungen": "Entrauchung verzögert",
    "aus_rohbau": "Start erfolgt",
})
nach_schluessel = {k.schluessel: k.nummer for k in kapitel}
pruefe(nach_schluessel.get("meilensteine") == "2.1",
       f"Meilensteine sollte 2.1 sein: {nach_schluessel.get('meilensteine')}")
pruefe(nach_schluessel.get("verzoegerungen") == "2.2",
       f"Verzögerungen sollte 2.2 sein (Fortschritt ist leer): "
       f"{nach_schluessel.get('verzoegerungen')}")
pruefe("fortschritt" not in nach_schluessel, "leeres Kapitel darf nicht erscheinen")
pruefe("vorkommnisse" not in nach_schluessel, "leeres Kapitel darf nicht erscheinen")
pruefe(nach_schluessel.get("ausfuehrung") == "3",
       f"Ausführung sollte 3 sein (Planung ist ganz leer): "
       f"{nach_schluessel.get('ausfuehrung')}")
pruefe(nach_schluessel.get("aus_rohbau") == "3.1",
       f"Rohbau sollte 3.1 sein: {nach_schluessel.get('aus_rohbau')}")
pruefe("planung" not in nach_schluessel,
       "Hauptkapitel ohne befüllte Unterkapitel muss ganz entfallen")

# 1.1 bis 1.4 erscheinen auch ohne Inhalt (wie im Original).
erste = [k.nummer for k in kapitel if k.nummer.startswith("1.")]
pruefe(erste == ["1.1", "1.2", "1.3", "1.4"],
       f"Kapitel 1.1–1.4 müssen immer erscheinen: {erste}")

# Verzeichnis und Text stammen aus derselben Liste — das ist der Kern.
verzeichnis = gl.inhaltsverzeichnis(kapitel)
pruefe(all(k.nummer.split(".")[0] != "1" for k in verzeichnis),
       "Kapitel 1 gehört nicht ins Verzeichnis")
pruefe([k.nummer for k in verzeichnis] == [k.nummer for k in kapitel if k not in
        [x for x in kapitel if x.nummer.split('.')[0] == '1']],
       "Verzeichnis muss dieselbe Reihenfolge wie der Text haben")

# Leerzeichen sind kein Inhalt.
nur_leer = gl.nummeriere({"fortschritt": "   \n  "})
pruefe(all(k.schluessel != "fortschritt" for k in nur_leer),
       "Ein Kapitel mit nur Leerzeichen muss als leer gelten")

# Alles leer: nur die vier Punkte der Bewertung bleiben.
leer = gl.nummeriere({})
pruefe([k.nummer for k in leer] == ["1.1", "1.2", "1.3", "1.4"],
       f"Bei leerem Bericht bleiben nur 1.1–1.4: {[k.nummer for k in leer]}")

# Listen zaehlen als Inhalt.
mit_liste = gl.nummeriere({"soll_ist": [pb.SollIstZeile("A", "1", "2", "3")]})
pruefe(any(k.schluessel == "soll_ist" for k in mit_liste),
       "eine gefüllte SOLL-IST-Liste muss das Kapitel zeigen")

print("─── (b) Kopf, Fuß, Dateiname, Seitenzahlen ───")

bericht = pb.Projektbericht(
    projektname="BOB Boulevard Berlin",
    projektkuerzel="BoB",
    nummer=3,
    berichtsdatum=date(2026, 7, 31),
    ersteller="S. Buchholz",
    kapitel={"meilensteine": "Rahmenterminplan",
             "verzoegerungen": "! Voraussichtlich im Oktober 2026",
             "anlagen": "Keine"},
    besprechungen=[pb.Besprechung("Baubesprechung", "Jour Fixe wöchentlich",
                                  "13.00 Uhr – 14.30 Uhr")],
    soll_ist=[pb.SollIstZeile("Start Entrauchung", "22.04.26", "kein Start",
                              "3 Monate")],
    fotos=[pb.Berichtsfoto(foto(), "BE mit Bauaufzug")],
)

pruefe(pb.dateiname(bericht) == "BoB-Projektbericht_Nr.3_20260731.docx",
       f"Dateiname: {pb.dateiname(bericht)}")
pruefe(pb.dateiname(bericht, "pdf").endswith(".pdf"), "PDF-Endung fehlt")

inhalt = pb.erzeuge_bericht(bericht)
xml = teile(inhalt)
dokument = xml["word/document.xml"]

kopf_teile = [v for k, v in xml.items() if k.startswith("word/header")]
fuss_teile = [v for k, v in xml.items() if k.startswith("word/footer")]
pruefe(len(kopf_teile) >= 2, f"erste Seite und Folgeseiten brauchen je eine Kopfzeile: {len(kopf_teile)}")
pruefe(any("BOB Boulevard Berlin" in t and "HPP" in t for t in kopf_teile),
       "Kopfzeile ohne Projektname und Bürokürzel")
pruefe(sum("BOB Boulevard Berlin" in t for t in kopf_teile) == 1,
       "der Projektname gehört nur auf die erste Seite")
pruefe(all("w:pBdr" in t for t in kopf_teile), "Kopfzeile ohne Trennlinie")
pruefe(any("BoB-Projektbericht_Nr.3_20260731.doc" in t for t in fuss_teile),
       "Fußzeile ohne Dateinamen")
pruefe(all("PAGE" in t and "NUMPAGES" in t for t in fuss_teile),
       "Fußzeile ohne Seitenzahlfelder")
pruefe(any("Impact" in t for t in fuss_teile),
       "Seitenzahl steht im Original in Impact")
pruefe("PAGEREF" in dokument, "Verzeichnis ohne Seitenverweise")
pruefe("bookmarkStart" in dokument, "Überschriften ohne Textmarken")
pruefe("updateFields" in xml["word/settings.xml"],
       "Word soll die Felder beim Öffnen aktualisieren")
pruefe("Zusammenfassende Bewertung / Monatsbericht Nr:3" in dokument,
       "Titelzeile fehlt oder trägt die falsche Nummer")
pruefe("Weiterer Inhalt:" in dokument, "Überschrift des Verzeichnisses fehlt")
pruefe('w:val="C00000"' in dokument or "C00000" in dokument,
       "die mit ! markierte Zeile muss rot sein")
pruefe("Voraussichtlich im Oktober 2026" in dokument
       and "! Voraussichtlich" not in dokument,
       "das Ausrufezeichen der Rotmarkierung darf nicht im Text stehen")
pruefe(dokument.count("<w:tbl>") == 1, "SOLL-IST-Tabelle fehlt oder ist doppelt")
with zipfile.ZipFile(io.BytesIO(inhalt)) as z:
    bilder = [n for n in z.namelist() if n.startswith("word/media/")]
pruefe(len(bilder) == 1, f"genau ein Foto erwartet: {bilder}")

print("─── (c) Abgleich mit der Referenz ───")

# Seiteneinrichtung, wie sie aus der Original-.doc gelesen wurde.
abschnitt_xml = dokument[dokument.index("<w:sectPr"):]
for name, wert, beschreibung in [
    ("w:left", 1417, "linker Rand 2.50 cm"),
    ("w:right", 1134, "rechter Rand 2.00 cm"),
    ("w:top", 1417, "oberer Rand 2.50 cm"),
    ("w:bottom", 1843, "unterer Rand 3.25 cm"),
]:
    pruefe(f'{name}="{wert}"' in abschnitt_xml,
           f"{beschreibung} stimmt nicht ({name})")
pruefe('w:header="720"' in abschnitt_xml, "Kopfabstand 1.27 cm fehlt")
pruefe('w:footer="539"' in abschnitt_xml, "Fußabstand 0.95 cm fehlt")
pruefe("titlePg" in abschnitt_xml, "„Erste Seite anders“ fehlt")
pruefe('w:ascii="Arial"' in xml["word/styles.xml"], "Grundschrift ist nicht Arial")

print("─── Endpunkte ───")

with TestClient(app) as c:
    pid = c.post("/api/projekte", json={
        "name": "BOB Boulevard Berlin", "adresse": "",
    }).json()["id"]

    gliederung = c.get("/api/projektberichte/gliederung")
    pruefe(gliederung.status_code == 200, f"gliederung: {gliederung.status_code}")
    gliederung = gliederung.json()
    pruefe(len(gliederung) == len(gl.GLIEDERUNG), "Gliederung unvollständig")
    pruefe(gliederung[0]["ohne_ueberschrift"] is True,
           "Kapitel 1 trägt keine eigene Überschrift")

    vorlage = c.get(f"/api/projektberichte/vorlage?projekt_id={pid}").json()
    pruefe(vorlage["nummer"] == 1, f"erster Bericht bekommt Nr. 1: {vorlage['nummer']}")
    pruefe(vorlage["projektkuerzel"] == "BOB", f"Kürzel: {vorlage['projektkuerzel']}")

    angelegt = c.post("/api/projektberichte", json={
        "projekt_id": pid, "nummer": 1, "berichtsdatum": "2026-06-30",
        "projektkuerzel": "BoB", "ersteller": "S. Buchholz",
        "kapitel": {"meilensteine": "Erster Monat", "aus_rohbau": "Beginn"},
        "besprechungen": [{"bezeichnung": "Baubesprechung",
                           "rhythmus": "wöchentlich", "uhrzeit": "13.00 Uhr"}],
    })
    pruefe(angelegt.status_code == 201,
           f"anlegen: {angelegt.status_code} {angelegt.text[:200]}")
    erster = angelegt.json()
    pruefe(erster["anzahl_kapitel"] > 0, "Kapitelzahl wird mitgeliefert")

    # Gleiche Nummer zweimal -> 409 mit klarer Meldung
    doppelt = c.post("/api/projektberichte", json={
        "projekt_id": pid, "nummer": 1, "berichtsdatum": "2026-07-31",
    })
    pruefe(doppelt.status_code == 409, f"doppelte Nummer: {doppelt.status_code}")
    pruefe("Nr. 1" in doppelt.text, f"Meldung nennt die Nummer nicht: {doppelt.text[:150]}")

    # Zweiter Bericht uebernimmt die Inhalte des ersten
    zweiter = c.post("/api/projektberichte", json={
        "projekt_id": pid, "nummer": 2, "berichtsdatum": "2026-07-31",
        "projektkuerzel": "BoB", "aus_letztem_bericht": True,
    })
    pruefe(zweiter.status_code == 201, f"zweiter Bericht: {zweiter.status_code}")
    zweiter = zweiter.json()
    pruefe(zweiter["kapitel"].get("meilensteine") == "Erster Monat",
           f"Vorbefüllung aus dem letzten Bericht fehlt: {zweiter['kapitel']}")
    pruefe(len(zweiter["besprechungen"]) == 1, "Besprechungen nicht übernommen")

    vorlage2 = c.get(f"/api/projektberichte/vorlage?projekt_id={pid}").json()
    pruefe(vorlage2["nummer"] == 3, f"nächste Nummer nach 2: {vorlage2['nummer']}")

    bid = zweiter["id"]

    # Aendern
    geaendert = c.patch(f"/api/projektberichte/{bid}", json={
        "kapitel": {"meilensteine": "Rahmenterminplan",
                    "verzoegerungen": "! Entrauchung verzögert",
                    "anlagen": "Keine"},
        "soll_ist": [{"bezeichnung": "Start Entrauchung", "soll": "22.04.26",
                      "ist": "kein Start", "verzug": "3 Monate"}],
    })
    pruefe(geaendert.status_code == 200, f"aendern: {geaendert.status_code}")
    pruefe(geaendert.json()["kapitel"]["verzoegerungen"].startswith("!"),
           "Rotmarkierung muss gespeichert bleiben")

    # Foto hochladen, beschriften, sortieren
    hoch = c.post(f"/api/projektberichte/{bid}/fotos",
                  files=[("dateien", ("IMG_1.jpg", foto(), "image/jpeg")),
                         ("dateien", ("IMG_2.jpg", foto((90, 110, 130)), "image/jpeg"))])
    pruefe(hoch.status_code == 201, f"fotos: {hoch.status_code} {hoch.text[:200]}")
    fotos = hoch.json()
    pruefe([f["reihenfolge"] for f in fotos] == [0, 1], "Reihenfolge beim Upload")
    beschriftet = c.patch(f"/api/projektberichte/fotos/{fotos[0]['id']}",
                          json={"bildunterschrift": "BE mit Bauaufzug",
                                "reihenfolge": 5})
    pruefe(beschriftet.status_code == 200, "Bildunterschrift speichern")
    pruefe(beschriftet.json()["reihenfolge"] == 5, "Reihenfolge speichern")
    pruefe(c.get(f"/api/projektberichte/fotos/{fotos[0]['id']}/bild").status_code == 200,
           "Foto muss abrufbar sein")

    # Vorschau: Nummerierung und Entfallenes
    schau = c.get(f"/api/projektberichte/{bid}/vorschau")
    pruefe(schau.status_code == 200, f"vorschau: {schau.status_code} {schau.text[:200]}")
    schau = schau.json()
    nummern = {k["schluessel"]: k["nummer"] for k in schau["kapitel"]}
    pruefe(nummern.get("verzoegerungen") == "2.3",
           f"Verzögerungen nach Meilensteinen und SOLL-IST: {nummern.get('verzoegerungen')}")
    pruefe(nummern.get("fotos") is not None, "Fotokapitel fehlt trotz Fotos")
    pruefe(any("Fortschritt" in e for e in schau["entfallen"]),
           "entfallene Kapitel werden nicht gemeldet")
    pruefe(schau["dateiname_docx"] == "BoB-Projektbericht_Nr.2_20260731.docx",
           f"Dateiname in der Vorschau: {schau['dateiname_docx']}")
    pruefe(schau["anzahl_fotos"] == 2, "Fotoanzahl in der Vorschau")

    # Dokument erzeugen und ablegen
    erzeugt = c.post(f"/api/projektberichte/{bid}/dokument?format=docx")
    pruefe(erzeugt.status_code == 200,
           f"dokument: {erzeugt.status_code} {erzeugt.text[:200]}")
    pruefe("wordprocessingml" in erzeugt.headers.get("content-type", ""),
           "falscher Inhaltstyp")
    pruefe("BoB-Projektbericht_Nr.2_20260731.docx" in
           erzeugt.headers.get("content-disposition", ""),
           f"Dateiname im Kopf: {erzeugt.headers.get('content-disposition')}")

    nachher = c.get(f"/api/projektberichte/{bid}").json()
    pruefe(nachher["hat_dokument"] is True, "Ablage am Bericht nicht vermerkt")
    pruefe(nachher["erzeugt_am"], "Erzeugungszeitpunkt fehlt")
    abgelegt = STORAGE / "output" / "projektberichte" / str(bid)
    pruefe(abgelegt.is_dir() and any(abgelegt.iterdir()),
           f"erzeugtes Dokument nicht abgelegt: {abgelegt}")

    # Historie: erneut abrufen, ohne neu zu bauen
    wieder = c.get(f"/api/projektberichte/{bid}/dokument")
    pruefe(wieder.status_code == 200, f"Historie: {wieder.status_code}")
    pruefe(len(wieder.content) > 5000, "abgelegtes Dokument ist zu klein")
    pruefe(c.get(f"/api/projektberichte/{bid}/dokument?format=pdf").status_code == 404,
           "ohne erzeugtes PDF muss der Abruf 404 sein")

    # Liste
    liste = c.get(f"/api/projektberichte?projekt_id={pid}").json()
    pruefe([b["nummer"] for b in liste] == [2, 1],
           f"neueste zuerst: {[b['nummer'] for b in liste]}")

    # Projekt loeschen: Konflikt nennt die Berichte
    konflikt = c.delete(f"/api/projekte/{pid}")
    pruefe(konflikt.status_code == 409, f"Projektlöschung: {konflikt.status_code}")
    pruefe(konflikt.json()["detail"].get("anzahl_projektberichte") == 2,
           f"Berichte im Konflikt: {konflikt.json()['detail']}")
    pruefe(c.delete(f"/api/projekte/{pid}?force=true").status_code == 204,
           "Projekt mit force löschen")
    pruefe(c.get(f"/api/projektberichte/{bid}").status_code == 404,
           "Bericht muss mit dem Projekt verschwinden")
    pruefe(not (STORAGE / "uploads" / "projektberichte" / str(bid)).exists(),
           "Fotoordner des gelöschten Berichts muss weg sein")

print(f"\n{ok} Pruefungen ok, {len(fehler)} Fehler")
for f in fehler:
    print("  FEHLER:", f)
sys.exit(1 if fehler else 0)
