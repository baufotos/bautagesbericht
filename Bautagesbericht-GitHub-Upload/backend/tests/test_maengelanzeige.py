"""Rauchtest: Mängelanzeige — Erzeuger, Prüfung und die drei Endpunkte."""
from __future__ import annotations

import io
import os
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Eigene Ablage im Temp-Ordner — die echte storage/ bleibt unberuehrt.
STORAGE = Path(tempfile.gettempdir()) / "hpp-matest"
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
from app.services import maengelanzeige_generation as ma  # noqa: E402

ok = 0
fehler: list[str] = []


def pruefe(bedingung, text):
    global ok
    if bedingung:
        ok += 1
    else:
        fehler.append(text)


def foto(groesse=(1200, 900), farbe=(150, 160, 170), drehen=False) -> bytes:
    bild = Image.new("RGB", groesse, farbe)
    puffer = io.BytesIO()
    if drehen:
        exif = Image.Exif()
        exif[274] = 6          # Orientation: 90 Grad im Uhrzeigersinn
        bild.save(puffer, format="JPEG", quality=88, exif=exif)
    else:
        bild.save(puffer, format="JPEG", quality=88)
    return puffer.getvalue()


def daten(**abweichungen) -> ma.Maengelanzeige:
    standard = dict(
        projektbezeichnung="G.100-DESYUM-Neubau Besucherzentrum DESY",
        vergabeeinheit="VE300.04- Putz-, Stuckarbeiten, WDVS",
        begehungsdatum=date(2025, 7, 30),
        dokumentkuerzel="G-100-DESYUM_VE300.04-WDVS_Mängelanzeige",
        empfaenger=ma.Empfaenger(
            firma="projectliving gmbh", ansprechpartner="Herrn Hey",
            strasse_hausnummer="Hedwig-Wachenheim-Karree 100",
            plz_ort="51107 Köln", email="info@projectliving.de",
        ),
        sachbearbeiter=ma.Sachbearbeiter(
            name="Steffen Buchholz", zeichen="Ze: sb", auftragsnummer="T - 10",
            email="steffen.buchholz@hpp.com",
        ),
        briefdatum=date(2025, 8, 11),
        fristsetzungsdatum=date(2025, 8, 20),
        bereiche=[
            ma.MangelBereich("Ostfassade", [
                ma.MangelFoto(foto(farbe=(200, 80, 80)), "Loch im WDVS fachgerecht schließen"),
                ma.MangelFoto(foto(farbe=(80, 200, 120)), "Kabel mit Silikon schließen"),
            ]),
            ma.MangelBereich("Südfassade Eingang", [
                ma.MangelFoto(foto(farbe=(90, 110, 210)), "Löcher fachgerecht schließen"),
            ]),
        ],
    )
    standard.update(abweichungen)
    return ma.Maengelanzeige(**standard)


def teile(inhalt: bytes) -> dict[str, str]:
    """Alle XML-Teile einer .docx als Text."""
    with zipfile.ZipFile(io.BytesIO(inhalt)) as z:
        return {
            n: z.read(n).decode("utf-8", "replace")
            for n in z.namelist() if n.endswith(".xml")
        }


def medien(inhalt: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(inhalt)) as z:
        return [n for n in z.namelist() if n.startswith("word/media/")]


print("─── Erzeuger ───")

# ── Zwei getrennte Dateien, beide gültig ──
paar = ma.erzeuge_beide(daten())
pruefe(len(paar) == 2, f"genau zwei Dateien erwartet: {list(paar)}")
namen = sorted(paar)
pruefe(all(n.endswith(".docx") for n in namen), f"beide .docx: {namen}")
pruefe(len({paar[n] for n in namen}) == 2, "die zwei Dateien duerfen nicht gleich sein")
for name, inhalt in paar.items():
    with zipfile.ZipFile(io.BytesIO(inhalt)) as z:
        pruefe("word/document.xml" in z.namelist(), f"{name}: kein document.xml")
        pruefe(z.testzip() is None, f"{name}: Archiv beschaedigt")

# ── Dateinamen nach Muster ──
d = daten(anlagedatum=date(2025, 8, 4))
pruefe(ma.dateiname_anschreiben(d)
       == "250811_G-100-DESYUM_VE300.04-WDVS_Mängelanzeige.docx",
       f"Briefname: {ma.dateiname_anschreiben(d)}")
pruefe(ma.dateiname_anlage(d)
       == "250804_Anlage_G-100-DESYUM_VE300.04-WDVS_Mängelanzeige.docx",
       f"Anlagenname: {ma.dateiname_anlage(d)}")
pruefe(ma.dateiname_anlage(daten()).startswith("250730_Anlage_"),
       "ohne anlagedatum gilt das Begehungsdatum")

# ── Feste Textbausteine stehen im Brief ──
brief = ma.erzeuge_anschreiben(daten())
brief_xml = teile(brief)["word/document.xml"]
for baustein in ("§ 4 Abs. 7 VOB/B", "Drittunternehmen", "Abnahme der Arbeiten",
                 "Mit freundlichen Grüßen", "20.08.2025."):
    pruefe(baustein in brief_xml, f"Textbaustein fehlt im Brief: {baustein}")
pruefe("Sehr geehrter Herr Hey," in brief_xml, "Anrede falsch gebildet")
pruefe("Herrn Hey" in brief_xml, "Adressfeld ohne Ansprechpartner")

# ── Kopf- und Fusszeile sind echte Word-Bereiche ──
brief_teile = teile(brief)
pruefe(any(n.startswith("word/header") for n in brief_teile),
       "Brief ohne Kopfzeilenteil")
fusszeilen = [n for n in brief_teile if n.startswith("word/footer")]
pruefe(len(fusszeilen) >= 1, "Brief ohne Fusszeilenteil")
fuss_xml = brief_teile[fusszeilen[0]]
pruefe("PAGE" in fuss_xml and "NUMPAGES" in fuss_xml,
       "Fusszeile ohne Seitenzahlfelder")
pruefe("fldChar" in fuss_xml, "Seitenzahl nicht als Feld")
pruefe("250811 G-100-DESYUM" in fuss_xml, "Fusszeile ohne Dokumentkuerzel")

# ── Briefkopf: freigestellte Grafik, hinter dem Text ──
kopf_xml = next(v for k, v in brief_teile.items() if k.startswith("word/header"))
pruefe("wp:anchor" in kopf_xml, "Briefkopf nicht freigestellt (kein wp:anchor)")
pruefe('behindDoc="1"' in kopf_xml, "Briefkopf nicht hinter dem Text")
pruefe(len(medien(brief)) >= 2,
       f"Briefkopf und Falzmarke erwartet, gefunden: {medien(brief)}")

# ── Silbentrennung an der richtigen Stelle ──
einst = brief_teile["word/settings.xml"]
pruefe("autoHyphenation" in einst, "Silbentrennung fehlt")
pruefe(einst.index("autoHyphenation") > einst.index("defaultTabStop"),
       "autoHyphenation muss hinter defaultTabStop stehen")
pruefe(einst.index("autoHyphenation") < einst.index("characterSpacingControl"),
       "autoHyphenation steht zu weit hinten (Word ignoriert es dann)")
pruefe('w:val="de-DE"' in brief_teile["word/styles.xml"],
       "Sprache nicht auf Deutsch gesetzt — Word trennt dann nicht")

# ── Anlage: Raster, Ueberschriften, Fotos ──
anlage = ma.erzeuge_anlage(daten())
anlage_teile = teile(anlage)
anlage_xml = anlage_teile["word/document.xml"]
pruefe(anlage_xml.count("<w:tbl>") == 2,
       f"zwei Fototabellen erwartet (2 Fotos + 1 Foto): {anlage_xml.count('<w:tbl>')}")
pruefe("Ostfassade" in anlage_xml and "Südfassade Eingang" in anlage_xml,
       "Bereichsueberschriften fehlen")
pruefe("Anlage" in anlage_xml, "Ueberschrift „Anlage“ fehlt")
pruefe('<w:u w:val="single"/>' in anlage_xml, "„Anlage“ nicht unterstrichen")
pruefe(len(medien(anlage)) == 4,
       f"drei Fotos plus Logo erwartet: {medien(anlage)}")
anlage_kopf = next(v for k, v in anlage_teile.items() if k.startswith("word/header"))
pruefe("Mängelanzeige / Begehung am 30.07.2025" in anlage_kopf,
       "Kopfzeile der Anlage ohne Begehungsdatum")
pruefe("wp:anchor" in anlage_kopf, "Logo der Anlage nicht freigestellt")

# ── Hochformat: EXIF-Drehung wird angewendet ──
hoch = daten(bereiche=[ma.MangelBereich("Nordseite", [
    ma.MangelFoto(foto(groesse=(1200, 900), drehen=True), "gedrehtes Handyfoto"),
])])
with zipfile.ZipFile(io.BytesIO(ma.erzeuge_anlage(hoch))) as z:
    bilder = [n for n in z.namelist() if n.startswith("word/media/")]
    gross = max(bilder, key=lambda n: z.getinfo(n).file_size)
    with Image.open(io.BytesIO(z.read(gross))) as bild:
        pruefe(bild.height > bild.width,
               f"EXIF-Drehung nicht angewendet: {bild.size}")

print("─── Pruefung der Eingaben ───")

def fehlt(text_teil, **abweichungen):
    try:
        ma.erzeuge_beide(daten(**abweichungen))
    except ma.MaengelanzeigeFehler as f:
        pruefe(text_teil.lower() in str(f).lower(),
               f"Meldung nennt „{text_teil}“ nicht: {f}")
        return
    fehler.append(f"kein Fehler bei: {text_teil}")

fehlt("Projektbezeichnung", projektbezeichnung="  ")
fehlt("Vergabeeinheit", vergabeeinheit="")
fehlt("Dokumentkürzel", dokumentkuerzel="")
fehlt("Firma", empfaenger=ma.Empfaenger(firma=""))
fehlt("Sachbearbeiter", sachbearbeiter=ma.Sachbearbeiter(name=""))
fehlt("Frist", fristsetzungsdatum=date(2025, 8, 1))
fehlt("Begehungsdatum", begehungsdatum=date(2025, 12, 1))
fehlt("mindestens einen Bereich", bereiche=[])
fehlt("Überschrift", bereiche=[ma.MangelBereich("  ", [ma.MangelFoto(foto(), "x")])])
fehlt("kein Foto", bereiche=[ma.MangelBereich("Ostfassade", [])])
fehlt("Bildunterschrift",
      bereiche=[ma.MangelBereich("Ostfassade", [ma.MangelFoto(foto(), " ")])])
fehlt("nicht lesen",
      bereiche=[ma.MangelBereich("Ostfassade", [ma.MangelFoto(b"kein Bild", "x")])])

# Das Anschreiben braucht keine Bereiche — es steht auch ohne Anlage.
try:
    ma.erzeuge_anschreiben(daten(bereiche=[]))
    ok += 1
except ma.MaengelanzeigeFehler as f:
    fehler.append(f"Anschreiben ohne Bereiche muesste gehen: {f}")

print("─── Endpunkte ───")

with TestClient(app) as c:
    pid = c.post("/api/projekte", json={
        "name": "G.100-DESYUM-Neubau Besucherzentrum DESY", "adresse": "",
    }).json()["id"]
    gewerk = c.post("/api/gewerke", json={
        "projekt_id": pid, "firma_name": "projectliving gmbh",
        "vergabeeinheit_code": "VE300.04",
        "vergabeeinheit_bezeichnung": "Putz-, Stuckarbeiten, WDVS",
        "email": "info@projectliving.de",
        "ansprechpartner": "Herrn Hey",
        "strasse": "Hedwig-Wachenheim-Karree 100",
        "plz": "51107", "ort": "Köln",
    })
    pruefe(gewerk.status_code == 201, f"gewerk anlegen: {gewerk.status_code} {gewerk.text[:200]}")
    gid = gewerk.json()["id"]

    # ── Vorbelegung zieht die Anschrift aus den Stammdaten ──
    vor = c.get(f"/api/maengelanzeige/vorbelegung?projekt_id={pid}&gewerk_id={gid}")
    pruefe(vor.status_code == 200, f"vorbelegung: {vor.status_code} {vor.text[:200]}")
    vor = vor.json()
    pruefe(vor["vergabeeinheit"] == "VE300.04- Putz-, Stuckarbeiten, WDVS",
           f"Vergabeeinheit: {vor['vergabeeinheit']}")
    pruefe(vor["empfaenger"]["plz_ort"] == "51107 Köln", f"PLZ/Ort: {vor['empfaenger']}")
    pruefe(vor["empfaenger"]["ansprechpartner"] == "Herrn Hey", "Ansprechpartner fehlt")
    pruefe(vor["dokumentkuerzel"].endswith("_Mängelanzeige"),
           f"Kuerzel: {vor['dokumentkuerzel']}")
    pruefe(vor["dokumentkuerzel"] == "G-100-DESYUM_VE300.04-WDVS_Mängelanzeige",
           f"Kuerzel sollte kurz sein: {vor['dokumentkuerzel']}")
    pruefe(vor["betreff_dritte_zeile"] == ma.BETREFF_DRITTE_ZEILE, "Betreffzeile falsch")

    # ── Mängel mit Fotos anlegen ──
    heute = date.today()
    ids = []
    for kurz, ort in [("Loch im WDVS fachgerecht schließen", "Ostfassade"),
                      ("Kabel mit Silikon schließen", "Ostfassade"),
                      ("Anstrich ergänzen", "Nordseite Lüftungsgitter")]:
        m = c.post("/api/maengel", json={
            "projekt_id": pid, "gewerk_id": gid, "kurzbezeichnung": kurz,
            "hinweis_ort": ort, "erste_frist_bis": (heute + timedelta(days=10)).isoformat(),
        }).json()
        c.post(f"/api/maengel/{m['id']}/fotos",
               files=[("dateien", (f"IMG_{m['id']}.jpg", foto(), "image/jpeg"))])
        ids.append(m["id"])
    ohne_foto = c.post("/api/maengel", json={
        "projekt_id": pid, "gewerk_id": gid,
        "kurzbezeichnung": "Sockel prüfen", "hinweis_ort": "Westfassade",
    }).json()
    ids.append(ohne_foto["id"])

    anfrage = {
        "projekt_id": pid, "gewerk_id": gid, "mangel_ids": ids,
        "empfaenger": vor["empfaenger"],
        "sachbearbeiter": {"name": "Steffen Buchholz", "zeichen": "Ze: sb",
                           "auftragsnummer": "T - 10",
                           "email": "steffen.buchholz@hpp.com"},
        "begehungsdatum": heute.isoformat(),
        "briefdatum": heute.isoformat(),
    }

    # ── Vorschau: Gruppierung und Hinweise ──
    schau = c.post("/api/maengelanzeige/vorschau", json=anfrage)
    pruefe(schau.status_code == 200, f"vorschau: {schau.status_code} {schau.text[:300]}")
    schau = schau.json()
    pruefe([b["bereich"] for b in schau["bereiche"]]
           == ["Ostfassade", "Nordseite Lüftungsgitter"],
           f"Bereiche/Reihenfolge: {[b['bereich'] for b in schau['bereiche']]}")
    pruefe(schau["bereiche"][0]["anzahl_fotos"] == 2, "Ostfassade muesste 2 Fotos haben")
    pruefe(schau["anzahl_fotos"] == 3, f"Fotos gesamt: {schau['anzahl_fotos']}")
    pruefe(any("Sockel prüfen" in h for h in schau["hinweise"]),
           f"Hinweis zum Mangel ohne Foto fehlt: {schau['hinweise']}")
    pruefe(schau["fristsetzungsdatum"] == (heute + timedelta(days=10)).isoformat(),
           f"Fristvorschlag: {schau['fristsetzungsdatum']}")
    pruefe(schau["dateiname_anschreiben"].startswith(heute.strftime("%y%m%d")),
           f"Briefname: {schau['dateiname_anschreiben']}")

    # ── Dokumente als ZIP: genau zwei .docx plus Hinweiszettel ──
    zip_antwort = c.post("/api/maengelanzeige/dokumente", json=anfrage)
    pruefe(zip_antwort.status_code == 200,
           f"dokumente: {zip_antwort.status_code} {zip_antwort.text[:300]}")
    pruefe(zip_antwort.headers["content-type"] == "application/zip",
           f"typ: {zip_antwort.headers.get('content-type')}")
    with zipfile.ZipFile(io.BytesIO(zip_antwort.content)) as z:
        drin = z.namelist()
        docs = [n for n in drin if n.endswith(".docx")]
        pruefe(len(docs) == 2, f"genau zwei Dokumente im ZIP: {drin}")
        pruefe(any(n.startswith(heute.strftime("%y%m%d") + "_Anlage_") for n in docs),
               f"Anlage fehlt: {docs}")
        pruefe("HINWEISE.txt" in drin, f"Hinweiszettel fehlt: {drin}")
        pruefe("Sockel" in z.read("HINWEISE.txt").decode("utf-8"),
               "Hinweiszettel ohne den uebersprungenen Mangel")

    # ── Einzeln abrufen ──
    for nur, muster in (("anschreiben", "_Mngelanzeige.docx"), ("anlage", "_Anlage_")):
        einzeln = c.post(f"/api/maengelanzeige/dokumente?nur={nur}", json=anfrage)
        pruefe(einzeln.status_code == 200, f"{nur}: {einzeln.status_code}")
        pruefe("wordprocessingml" in einzeln.headers.get("content-type", ""),
               f"{nur}: falscher Typ {einzeln.headers.get('content-type')}")
        pruefe(muster in einzeln.headers.get("content-disposition", ""),
               f"{nur}: Dateiname {einzeln.headers.get('content-disposition')}")
    pruefe(c.post("/api/maengelanzeige/dokumente?nur=quatsch",
                  json=anfrage).status_code == 400, "unbekanntes nur= muesste 400 sein")

    # ── Fehlerfaelle ──
    pruefe(c.post("/api/maengelanzeige/vorschau",
                  json={**anfrage, "mangel_ids": []}).status_code == 422,
           "leere Mangelauswahl muesste 422 sein")
    pruefe(c.post("/api/maengelanzeige/vorschau",
                  json={**anfrage, "mangel_ids": [99999]}).status_code == 404,
           "unbekannter Mangel muesste 404 sein")
    nur_ohne_foto = c.post("/api/maengelanzeige/vorschau",
                           json={**anfrage, "mangel_ids": [ohne_foto["id"]]})
    pruefe(nur_ohne_foto.status_code == 422,
           f"nur Maengel ohne Foto muesste 422 sein: {nur_ohne_foto.status_code}")
    pruefe("Bereich" in nur_ohne_foto.text or "Foto" in nur_ohne_foto.text,
           f"Meldung unklar: {nur_ohne_foto.text[:200]}")

    # Fremdes Projekt
    pid2 = c.post("/api/projekte", json={"name": "Anderes Projekt", "adresse": ""}).json()["id"]
    pruefe(c.post("/api/maengelanzeige/vorschau",
                  json={**anfrage, "projekt_id": pid2}).status_code == 400,
           "Maengel eines anderen Projekts muessten 400 sein")

print(f"\n{ok} Pruefungen ok, {len(fehler)} Fehler")
for f in fehler:
    print("  FEHLER:", f)
sys.exit(1 if fehler else 0)
