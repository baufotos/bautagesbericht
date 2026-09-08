"""Rauchtest: McDonald's — Mail lesen, UNLOCODE, Ordner, Angebot, Fachplaner.

Aufbau wie die anderen Suiten dieses Ordners: ein Skript, das oben seine
BTB_*-Umgebung setzt, auf Modulebene durchläuft und am Ende zählt. Kein
pytest — siehe tests/test_fotomail.py.

Die KI-Analyse wird NICHT gegen die Anthropic-Schnittstelle gefahren. Geprüft
wird stattdessen das, was ohne Netz falsch sein kann und im Betrieb weh tut:
das Zerlegen der ``.eml``, das Säubern der Modellantwort und der Weg des
Uploads ohne hinterlegten Schlüssel — genau der Fall des Bürorechners.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Eigene Ablage im Temp-Ordner — die echte storage/ bleibt unberuehrt.
STORAGE = Path(tempfile.gettempdir()) / "hpp-mcdonaldstest"
if STORAGE.exists():
    shutil.rmtree(STORAGE)
STORAGE.mkdir(parents=True)

WIN = str(STORAGE).replace("\\", "/")
os.environ["BTB_DATABASE_URL"] = f"sqlite:///{WIN}/test.db"
os.environ["BTB_UPLOAD_DIR"] = f"{WIN}/uploads"
os.environ["BTB_OUTPUT_DIR"] = f"{WIN}/output"
# Ausdruecklich leer: Der Kern dieser Suite ist, dass die fehlende
# Konfiguration einen sprechenden Zustand ergibt und keinen Absturz.
os.environ["BTB_MCDONALDS_BASIS_H"] = ""
os.environ["BTB_MCDONALDS_BASIS_SHAREPOINT"] = ""

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import UnlocodeEintrag  # noqa: E402
from app.services import mcdonalds_angebot_generation as angebot_dienst  # noqa: E402
from app.services import mcdonalds_email_analyse as analyse  # noqa: E402
from app.services import mcdonalds_ordner as ordner_dienst  # noqa: E402
from app.services import mcdonalds_unlocode as unlocode  # noqa: E402

# Die Tabellen anlegen, bevor der erste Abschnitt eine eigene Sitzung oeffnet.
# ``TestClient(app)`` tut das ueber den Lebenszyklus auch, aber erst weiter
# unten — die Dienste werden vorher schon ohne API geprueft.
init_db()

ok = 0
fehler = []


def pruefe(bedingung, text):
    global ok
    if bedingung:
        ok += 1
    else:
        fehler.append(text)


BEISPIEL_EML = Path(__file__).resolve().parent / "beispiel_beauftragung.eml"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Die .eml zerlegen (ohne Netz)
# ─────────────────────────────────────────────────────────────────────────────

print("== EML lesen ==")

rohdaten = BEISPIEL_EML.read_bytes()
inhalt = analyse.lies_eml(rohdaten, BEISPIEL_EML.name)

pruefe("Beauftragung LPH 6" in inhalt.betreff, f"Betreff: {inhalt.betreff!r}")
pruefe("firma@kunde.de" in inhalt.absender, f"Absender: {inhalt.absender!r}")
pruefe(inhalt.gesendet_am is not None and inhalt.gesendet_am.year == 2026,
       f"Sendedatum: {inhalt.gesendet_am!r}")
pruefe(inhalt.anhaenge == ["Projekthandbuch_Anlage.pdf"],
       f"Anhangnamen: {inhalt.anhaenge!r}")
pruefe("Leistungsphase 6" in inhalt.text, "Mailtext fehlt der Klartextteil")
pruefe("Europaplatz 1, 52068 Aachen" in inhalt.text,
       "Anschrift fehlt im Mailtext")
# Der Klartextteil wird bevorzugt: Die HTML-Fassung darf nicht mit hineinlaufen.
pruefe("<b>" not in inhalt.text and "margin" not in inhalt.text,
       "HTML ist in den Klartext geraten")

# Eine kaputte Datei darf nicht durchgehen.
try:
    analyse.lies_eml(b"", "leer.eml")
    pruefe(False, "leere Datei muesste AnalyseFehler werfen")
except analyse.AnalyseFehler:
    ok += 1

# Nur-HTML-Mail: Text wird gewonnen, aber mit Hinweis zum Gegenlesen.
nur_html = (
    b"From: a@b.de\r\nTo: c@d.de\r\nSubject: Test\r\n"
    b"Content-Type: text/html; charset=utf-8\r\n\r\n"
    b"<html><body><p>Beauftragung</p><p>LPH 8</p></body></html>\r\n"
)
html_inhalt = analyse.lies_eml(nur_html, "html.eml")
pruefe("Beauftragung" in html_inhalt.text and "LPH 8" in html_inhalt.text,
       f"HTML-Text nicht gewonnen: {html_inhalt.text!r}")
pruefe(any("HTML" in h for h in html_inhalt.hinweise),
       f"Hinweis auf HTML-Fassung fehlt: {html_inhalt.hinweise}")

# Mail ohne jeden Text: Hinweis statt stiller Leere.
ohne_text = b"From: a@b.de\r\nSubject: Leer\r\n\r\n"
leer_inhalt = analyse.lies_eml(ohne_text, "leer2.eml")
pruefe(any("kein Text" in h for h in leer_inhalt.hinweise),
       f"Hinweis auf fehlenden Text: {leer_inhalt.hinweise}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Die Modellantwort saeubern
# ─────────────────────────────────────────────────────────────────────────────

print("== Modellantwort saeubern ==")

angaben = analyse.zu_angaben({
    "auftraggeber": "  Muster Restaurantbetriebe GmbH ",
    "standort_name": "Aachen Europaplatz",
    "standort_adresse": "Europaplatz 1, 52068 Aachen",
    "standort_ort": "Aachen",
    "leistungsphase": 6,
    "eckdaten": [
        {"bezeichnung": "Bestellnummer", "wert": "4711-2026"},
        {"bezeichnung": "", "wert": "wird verworfen"},
        {"bezeichnung": "Baubeginn", "wert": "15.10.2026"},
    ],
    "hinweise": ["Der Baubeginn ist als 'vorgesehen' formuliert."],
})
pruefe(angaben.auftraggeber == "Muster Restaurantbetriebe GmbH",
       f"Auftraggeber nicht getrimmt: {angaben.auftraggeber!r}")
pruefe(angaben.leistungsphase == 6, f"Phase: {angaben.leistungsphase!r}")
pruefe(angaben.eckdaten == {"Bestellnummer": "4711-2026",
                            "Baubeginn": "15.10.2026"},
       f"Eckdaten: {angaben.eckdaten!r}")
pruefe(len(angaben.hinweise) == 1, f"Hinweise: {angaben.hinweise!r}")

# Eine Phase, die es nicht gibt, wird verworfen und gemeldet — nicht gesetzt.
kaputt = analyse.zu_angaben({"leistungsphase": 12, "standort_name": "X"})
pruefe(kaputt.leistungsphase is None, "Phase 12 haette nicht gelten duerfen")
pruefe(any("12" in h for h in kaputt.hinweise),
       f"Hinweis zur ungueltigen Phase fehlt: {kaputt.hinweise}")

keine_zahl = analyse.zu_angaben({"leistungsphase": "sechs"})
pruefe(keine_zahl.leistungsphase is None, "'sechs' haette nicht gelten duerfen")

# Fehlt der Ort, wird er aus der Adresse abgeleitet — mit Hinweis.
abgeleitet = analyse.zu_angaben({
    "standort_adresse": "Große Bergstraße 160, 22767 Hamburg",
    "standort_ort": "",
})
pruefe(abgeleitet.standort_ort == "Hamburg",
       f"Ort nicht abgeleitet: {abgeleitet.standort_ort!r}")
pruefe(any("abgeleitet" in h for h in abgeleitet.hinweise),
       f"Hinweis zur Ableitung fehlt: {abgeleitet.hinweise}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. UNLOCODE: Ortsnamen vergleichbar machen und nachschlagen
# ─────────────────────────────────────────────────────────────────────────────

print("== UNLOCODE ==")

pruefe(unlocode.normalisiere("München") == "muenchen",
       f"normalisiere Muenchen: {unlocode.normalisiere('München')!r}")
pruefe(unlocode.normalisiere("Frankfurt am Main") == "frankfurtammain",
       "normalisiere Frankfurt")
pruefe(unlocode.normalisiere("Baden-Baden") == "badenbaden",
       "normalisiere Baden-Baden")
pruefe(unlocode.normalisiere("  ") == "", "normalisiere Leerraum")

pruefe(unlocode.ort_aus_adresse("Europaplatz 1, 52068 Aachen") == "Aachen",
       "ort_aus_adresse mit PLZ")
pruefe(unlocode.ort_aus_adresse("Musterweg 3\n20095 Hamburg\nDeutschland")
       == "Hamburg", "ort_aus_adresse mit Land")
pruefe(unlocode.ort_aus_adresse("Musterweg 3") == "",
       "ort_aus_adresse ohne Ort muesste leer sein")
pruefe(unlocode.ort_aus_adresse("") == "", "ort_aus_adresse leer")

db = SessionLocal()
try:
    # Ohne Tabelle darf nichts gefunden werden — und nichts krachen.
    pruefe(unlocode.anzahl_eintraege(db) == 0, "Tabelle muesste leer starten")
    pruefe(unlocode.ermittle(db, "Aachen") is None,
           "ohne Tabelle darf es keinen Treffer geben")

    # Ein kleiner Bestand, gebaut wie der Upload ihn anlegt.
    db.bulk_insert_mappings(UnlocodeEintrag, [
        {"code": "AAH", "ort": "Aachen", "ort_normal": unlocode.normalisiere("Aachen"),
         "bundesland": "Nordrhein-Westfalen"},
        {"code": "AAC", "ort": "Aach", "ort_normal": unlocode.normalisiere("Aach"),
         "bundesland": "Baden-Württemberg"},
        {"code": "A2H", "ort": "Aach", "ort_normal": unlocode.normalisiere("Aach"),
         "bundesland": "Rheinland-Pfalz"},
        {"code": "HAM", "ort": "Hamburg", "ort_normal": unlocode.normalisiere("Hamburg"),
         "bundesland": "Hamburg"},
        {"code": "MUC", "ort": "München", "ort_normal": unlocode.normalisiere("München"),
         "bundesland": "Bayern"},
    ])
    db.commit()

    pruefe(unlocode.anzahl_eintraege(db) == 5,
           f"Anzahl: {unlocode.anzahl_eintraege(db)}")

    treffer = unlocode.ermittle(db, "Aachen")
    pruefe(treffer is not None and treffer.code == "AAH" and treffer.art == "exakt",
           f"exakter Treffer Aachen: {treffer!r}")

    # Umlaut-Umschrift: So schreibt man es in Mails, so steht es nicht in der
    # Tabelle — und muss trotzdem treffen.
    treffer = unlocode.ermittle(db, "Muenchen")
    pruefe(treffer is not None and treffer.code == "MUC",
           f"Muenchen -> MUC: {treffer!r}")

    # Mehrdeutiger Ortsname: Das Bundesland entscheidet.
    treffer = unlocode.ermittle(db, "Aach", "Rheinland-Pfalz")
    pruefe(treffer is not None and treffer.code == "A2H",
           f"Aach mit Bundesland: {treffer!r}")
    treffer = unlocode.ermittle(db, "Aach")
    pruefe(treffer is not None and treffer.code in ("AAC", "A2H"),
           f"Aach ohne Bundesland: {treffer!r}")

    # Stadtteil: "Hamburg-Ottensen" steht so in keiner amtlichen Liste.
    treffer = unlocode.ermittle(db, "Hamburg-Ottensen")
    pruefe(treffer is not None and treffer.code == "HAM"
           and treffer.art == "unscharf",
           f"Hamburg-Ottensen: {treffer!r}")

    # Tippfehler: unscharf, aber gefunden — und als unscharf gekennzeichnet.
    treffer = unlocode.ermittle(db, "Aachne")
    pruefe(treffer is not None and treffer.code == "AAH"
           and treffer.art == "unscharf" and treffer.guete < 1.0,
           f"Tippfehler Aachne: {treffer!r}")

    # Was gar nicht passt, wird nicht erfunden.
    pruefe(unlocode.ermittle(db, "Zzzzville") is None,
           "Zzzzville darf keinen Treffer liefern")
    pruefe(unlocode.ermittle(db, "") is None, "leerer Ort darf nichts liefern")

    pruefe(unlocode.ermittle_unlocode(db, "Aachen") == "AAH",
           "ermittle_unlocode Kurzform")
finally:
    db.close()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Ordnername und Ordneranlage ohne Konfiguration
# ─────────────────────────────────────────────────────────────────────────────

print("== Ordner ==")

pruefe(ordner_dienst.ordnername("AAH", "Aachen Europaplatz")
       == "AAH_Aachen Europaplatz", "Ordnername")
pruefe(ordner_dienst.ordnername(None, "Aachen Europaplatz")
       == "XXX_Aachen Europaplatz", "Ordnername ohne Code")
pruefe(ordner_dienst.ordnername("aah", "Aachen") == "AAH_Aachen",
       "Code wird gross geschrieben")
# Zeichen, die Windows nicht zulaesst, duerfen nicht in den Pfad geraten.
pruefe(ordner_dienst.ordnername("HAM", 'Köln Ring / Nord: "neu"')
       == "HAM_Köln Ring Nord neu", f"verbotene Zeichen: "
       f"{ordner_dienst.ordnername('HAM', 'Köln Ring / Nord: \"neu\"')!r}")
pruefe(ordner_dienst.saubere_bezeichnung("Aachen  ") == "Aachen",
       "Leerraum am Ende")
pruefe(ordner_dienst.saubere_bezeichnung("Aachen.") == "Aachen",
       "Punkt am Ende (Windows verschluckt ihn sonst)")
pruefe(ordner_dienst.UNTERORDNER == [],
       "UNTERORDNER ist noch der Platzhalter (siehe TODO McDonald's)")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Der ganze Ablauf ueber das API
# ─────────────────────────────────────────────────────────────────────────────

print("== API ==")

with TestClient(app) as c:
    # ── Faehigkeiten: nichts konfiguriert, also alles aus ──
    faehig = c.get("/api/mcdonalds/faehigkeiten")
    pruefe(faehig.status_code == 200, f"faehigkeiten: {faehig.status_code}")
    faehig = faehig.json()
    pruefe(faehig["analyse"] is False, f"analyse muesste aus sein: {faehig}")
    pruefe(faehig["ordner_h"] is False, f"ordner_h muesste aus sein: {faehig}")
    pruefe(faehig["smtp"] is False, f"smtp muesste aus sein: {faehig}")

    # ── Fachplaner-Stammdaten ──
    leer = c.get("/api/fachplaner")
    pruefe(leer.status_code == 200 and leer.json() == [],
           f"Fachplanerliste startet leer: {leer.text[:120]}")

    angelegt = c.post("/api/fachplaner", json={
        "name": "Ingenieurbüro Müller GmbH",
        "ansprechpartner": "Frau Stark",
        "email": "planung@mueller-ing.de",
        "adresse": "Musterweg 3, 20095 Hamburg",
    })
    pruefe(angelegt.status_code == 201, f"Fachplaner anlegen: {angelegt.text[:200]}")
    planer = angelegt.json()
    pruefe(planer["name"] == "Ingenieurbüro Müller GmbH", f"Name: {planer}")

    # Zweiter Eintrag, um die alphabetische Sortierung zu pruefen.
    zweiter = c.post("/api/fachplaner", json={
        "name": "Achtern & Partner", "email": "buero@achtern.de",
    }).json()
    namen = [p["name"] for p in c.get("/api/fachplaner").json()]
    pruefe(namen == sorted(namen), f"Fachplaner nicht alphabetisch: {namen}")

    # Eine unbrauchbare Adresse wird abgelehnt — sie ist der Empfaenger des
    # Entwurfs, ein Tippfehler faellt sonst erst in Outlook auf.
    pruefe(c.post("/api/fachplaner",
                  json={"name": "X", "email": "keine-adresse"}).status_code == 422,
           "kaputte Mailadresse muesste 422 sein")

    # Loeschen ohne Angebote geht.
    pruefe(c.delete(f"/api/fachplaner/{zweiter['id']}").status_code == 204,
           "Fachplaner ohne Angebote loeschen")
    pruefe(c.delete("/api/fachplaner/99999").status_code == 404,
           "unbekannter Fachplaner muesste 404 sein")

    # ── Upload der .eml ohne Anthropic-Schluessel ──
    #
    # Der Fall des Buerorechners: Die Mail muss trotzdem ankommen, ihr Text
    # gespeichert werden und ein Hinweis erscheinen.
    hochgeladen = c.post(
        "/api/mcdonalds/faelle",
        files={"datei": (BEISPIEL_EML.name, rohdaten, "message/rfc822")},
    )
    pruefe(hochgeladen.status_code == 201,
           f"EML-Upload: {hochgeladen.status_code} {hochgeladen.text[:250]}")
    fall = hochgeladen.json()
    pruefe(fall["quelle"] == "eml", f"quelle: {fall['quelle']!r}")
    pruefe(fall["eml_dateiname"] == BEISPIEL_EML.name, f"Dateiname: {fall}")
    pruefe("Leistungsphase 6" in fall["roh_text"], "roh_text nicht gespeichert")
    pruefe(fall["anhaenge"] == ["Projekthandbuch_Anlage.pdf"],
           f"Anhangnamen am Fall: {fall['anhaenge']}")
    pruefe(fall["analysiert_am"] is None,
           "ohne Schluessel darf kein Analysezeitpunkt stehen")
    pruefe(any("Anthropic" in h or "von Hand" in h for h in fall["hinweise"]),
           f"Hinweis zur fehlenden Analyse: {fall['hinweise']}")

    fall_id = fall["id"]

    # Die Hintergrundaufgabe ist beim Verlassen des Aufrufs gelaufen: Ohne
    # konfigurierten Basispfad muss der Fall auf "fehler" stehen — mit einer
    # Meldung, die sagt, was zu tun ist. Genau das ist der Punkt: kein
    # Absturz, kein ewiges "wird angelegt".
    geladen = c.get(f"/api/mcdonalds/faelle/{fall_id}").json()
    pruefe(geladen["ordner_status"] == "fehler",
           f"ordner_status ohne Konfiguration: {geladen['ordner_status']!r}")
    pruefe(geladen["ordner_pfad_h"] is None, f"pfad_h: {geladen['ordner_pfad_h']!r}")
    pruefe("Basispfad H:" in (geladen["fehlermeldung"] or ""),
           f"Meldung nennt den Basispfad nicht: {geladen['fehlermeldung']!r}")
    pruefe("mcdonalds_ordner_h" in (geladen["fehlermeldung"] or ""),
           f"Meldung sagt nicht, wo es einzutragen ist: {geladen['fehlermeldung']!r}")

    # ── Angaben von Hand nachtragen ──
    korrigiert = c.patch(f"/api/mcdonalds/faelle/{fall_id}", json={
        "standort_name": "Aachen Europaplatz",
        "standort_adresse": "Europaplatz 1, 52068 Aachen",
        "standort_ort": "Aachen",
        "auftraggeber": "Muster Restaurantbetriebe GmbH",
        "leistungsphase": 6,
        "eckdaten": {"Bestellnummer": "4711-2026"},
    })
    pruefe(korrigiert.status_code == 200, f"PATCH: {korrigiert.text[:200]}")
    korrigiert = korrigiert.json()
    pruefe(korrigiert["standort_name"] == "Aachen Europaplatz",
           f"Standort nach PATCH: {korrigiert}")
    pruefe(korrigiert["leistungsphase"] == 6, f"Phase nach PATCH: {korrigiert}")
    pruefe(c.patch(f"/api/mcdonalds/faelle/{fall_id}",
                   json={"leistungsphase": 12}).status_code == 422,
           "Phase 12 muesste 422 sein")

    # ── Jetzt mit konfiguriertem Basispfad: der Ordner entsteht wirklich ──
    zielbasis = STORAGE / "H-Laufwerk"
    zielbasis.mkdir(parents=True, exist_ok=True)
    alt = settings.mcdonalds_basis_h
    settings.mcdonalds_basis_h = str(zielbasis)
    try:
        erneut = c.post(f"/api/mcdonalds/faelle/{fall_id}/ordner")
        pruefe(erneut.status_code == 200, f"Ordner erneut: {erneut.text[:200]}")
        erneut = erneut.json()
        pruefe(erneut["ordner_status"] == "angelegt",
               f"Status mit Basispfad: {erneut['ordner_status']!r} "
               f"({erneut['fehlermeldung']!r})")
        # Kein UNLOCODE-Bestand in dieser Datenbank -> XXX, mit Hinweis.
        pruefe(erneut["ordner_name"].endswith("_Aachen Europaplatz"),
               f"Ordnername: {erneut['ordner_name']!r}")
        pruefe(Path(erneut["ordner_pfad_h"]).is_dir(),
               f"Ordner nicht auf der Platte: {erneut['ordner_pfad_h']!r}")
        # SharePoint ist nicht angebunden — das darf den Vorgang nicht kippen,
        # muss aber sichtbar bleiben.
        pruefe(erneut["ordner_pfad_sharepoint"] is None,
               f"SharePoint-Pfad: {erneut['ordner_pfad_sharepoint']!r}")
        pruefe("SharePoint" in (erneut["fehlermeldung"] or ""),
               f"Hinweis auf SharePoint fehlt: {erneut['fehlermeldung']!r}")

        # Ein zweiter Aufruf darf nicht scheitern (exist_ok).
        pruefe(c.post(f"/api/mcdonalds/faelle/{fall_id}/ordner").status_code == 200,
               "zweiter Ordner-Aufruf muesste durchgehen")
    finally:
        settings.mcdonalds_basis_h = alt

    # ── Telefonische Beauftragung ──
    telefon = c.post("/api/mcdonalds/faelle/manuell", json={
        "standort_name": "Hamburg Altona",
        "standort_adresse": "Große Bergstraße 160, 22767 Hamburg",
        "auftraggeber": "Muster Restaurantbetriebe GmbH",
        "leistungsphase": 8,
        "notiz": "Anruf Herr Weber, 04.09.2026",
    })
    pruefe(telefon.status_code == 201, f"manuell: {telefon.text[:200]}")
    telefon = telefon.json()
    pruefe(telefon["quelle"] == "telefon", f"quelle: {telefon['quelle']!r}")
    # Der Ort war nicht angegeben und wird aus der Adresse abgeleitet.
    pruefe(telefon["standort_ort"] == "Hamburg",
           f"Ort nicht abgeleitet: {telefon['standort_ort']!r}")
    pruefe(telefon["roh_text"] == "Anruf Herr Weber, 04.09.2026",
           f"Notiz nicht gespeichert: {telefon['roh_text']!r}")
    pruefe(telefon["analysiert_am"] is None,
           "Handeingabe ist keine Analyse")

    # Ohne Standort geht es nicht — der Ordner haette keinen Namen.
    pruefe(c.post("/api/mcdonalds/faelle/manuell",
                  json={"standort_name": ""}).status_code == 422,
           "leerer Standort muesste 422 sein")

    # ── UNLOCODE-Tabelle hochladen ──
    #
    # Gebaut wie die Anlage des Buerohandbuchs: Titelzeilen ueber der Tabelle,
    # Kopfzeile erst in Zeile 4. Genau das muss der Leser finden.
    def baue_xlsx(zeilen: list[list[str]]) -> bytes:
        """Eine minimale .xlsx mit Inline-Zeichenketten."""
        import io
        import zipfile
        from xml.sax.saxutils import escape

        def spalte(nummer: int) -> str:
            name = ""
            while nummer >= 0:
                name = chr(ord("A") + nummer % 26) + name
                nummer = nummer // 26 - 1
            return name

        xml_zeilen = []
        for i, zeile in enumerate(zeilen, start=1):
            zellen = "".join(
                f'<c r="{spalte(j)}{i}" t="inlineStr"><is><t>{escape(str(w))}'
                f"</t></is></c>"
                for j, w in enumerate(zeile) if str(w) != ""
            )
            xml_zeilen.append(f'<row r="{i}">{zellen}</row>')

        blatt = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main"><sheetData>'
            + "".join(xml_zeilen)
            + "</sheetData></worksheet>"
        )
        mappe = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main"><sheets>'
            '<sheet name="UNLOCODE_DE" sheetId="1" r:id="rId1" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships"/></sheets></workbook>'
        )
        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w") as archiv:
            archiv.writestr("xl/workbook.xml", mappe)
            archiv.writestr("xl/worksheets/sheet1.xml", blatt)
        return puffer.getvalue()

    tabelle = baue_xlsx([
        ["ANLAGE 5.1 - UN/LOCODE (DE)"],
        ["Quelle:", "https://service.unece.org/trade/locode/de.htm"],
        [],
        ["UNLOCODE", "Ort", "Bundesland", "Coordinates", "Remarks"],
        ["AAH", "Aachen", "Nordrhein-Westfalen", "5046N 00605E", ""],
        ["HAM", "Hamburg", "Hamburg", "5333N 00958E", ""],
        ["MUC", "München", "Bayern", "", ""],
        ["", "Zeile ohne Code", "", "", ""],
    ])

    geladen = c.post(
        "/api/mcdonalds/unlocode-tabelle",
        files={"datei": ("anlage.xlsx", tabelle,
                         "application/vnd.openxmlformats-officedocument"
                         ".spreadsheetml.sheet")},
    )
    pruefe(geladen.status_code == 200,
           f"UNLOCODE-Upload: {geladen.status_code} {geladen.text[:250]}")
    geladen = geladen.json()
    pruefe(geladen["eingelesen"] == 3, f"eingelesen: {geladen}")
    pruefe(geladen["uebersprungen"] == 1, f"uebersprungen: {geladen}")
    pruefe(geladen["blatt"] == "UNLOCODE_DE", f"blatt: {geladen}")

    nachgeschlagen = c.get("/api/mcdonalds/unlocode?ort=Aachen")
    pruefe(nachgeschlagen.status_code == 200,
           f"Nachschlagen: {nachgeschlagen.text[:200]}")
    pruefe(nachgeschlagen.json()["code"] == "AAH",
           f"Code: {nachgeschlagen.json()}")
    pruefe(c.get("/api/mcdonalds/unlocode?ort=Zzzzville").status_code == 404,
           "unbekannter Ort muesste 404 sein")

    # Keine Excel-Datei: sprechende Meldung statt Rohfehler.
    kaputt = c.post("/api/mcdonalds/unlocode-tabelle",
                    files={"datei": ("nicht.xlsx", b"kein zip", "application/octet")})
    pruefe(kaputt.status_code == 400, f"kaputte Datei: {kaputt.status_code}")
    pruefe(".xlsx" in kaputt.text, f"Meldung nennt das Format nicht: {kaputt.text[:200]}")

    # Jetzt greift der Abgleich: der Ordner bekommt einen echten Code.
    settings.mcdonalds_basis_h = str(STORAGE / "H-Laufwerk")
    try:
        mit_code = c.post(f"/api/mcdonalds/faelle/{telefon['id']}/ordner").json()
        pruefe(mit_code["unlocode"] == "HAM", f"UNLOCODE am Fall: {mit_code}")
        pruefe(mit_code["ordner_name"] == "HAM_Hamburg Altona",
               f"Ordnername mit Code: {mit_code['ordner_name']!r}")
    finally:
        settings.mcdonalds_basis_h = ""

    # ── Angebot anlegen ──
    angebot = c.post(f"/api/mcdonalds/faelle/{fall_id}/angebote", json={
        "fachplaner_id": planer["id"],
        "betreff": "Beauftragung Aachen Europaplatz",
        "angaben": {"Honorarzone": "III", "Anrechenbare Kosten": "480.000 €"},
        "mehrleistungen": [
            {"bezeichnung": "Zusätzliche Bestandsaufnahme", "betrag": 2400.0},
            {"bezeichnung": "Nachtragsprüfung", "betrag": None},
            {"bezeichnung": "   ", "betrag": 99.0},
        ],
    })
    pruefe(angebot.status_code == 201, f"Angebot anlegen: {angebot.text[:250]}")
    angebot = angebot.json()
    pruefe(angebot["fachplaner_name"] == "Ingenieurbüro Müller GmbH",
           f"Fachplanername am Angebot: {angebot}")
    # Ohne eigene Angabe uebernimmt das Angebot die Phase des Falls.
    pruefe(angebot["leistungsphase"] == 6, f"Phase geerbt: {angebot}")
    # Die leere Zeile aus dem Formular wird verworfen, nicht bemaengelt.
    pruefe(len(angebot["mehrleistungen"]) == 2,
           f"Mehrleistungen: {angebot['mehrleistungen']}")
    pruefe(angebot["mehrleistungen"][1]["betrag"] is None,
           f"Betrag darf fehlen: {angebot['mehrleistungen']}")
    pruefe(angebot["dokument_vorhanden"] is False,
           "vor dem Erzeugen darf kein Dokument gemeldet werden")

    angebot_id = angebot["id"]

    # Das Angebot haengt am Fall und kommt in der Detailansicht mit.
    detail = c.get(f"/api/mcdonalds/faelle/{fall_id}").json()
    pruefe(len(detail["angebote"]) == 1, f"Angebote am Fall: {detail['angebote']}")

    pruefe(c.post(f"/api/mcdonalds/faelle/{fall_id}/angebote",
                  json={"fachplaner_id": 99999}).status_code == 400,
           "unbekannter Fachplaner muesste 400 sein")
    pruefe(c.post("/api/mcdonalds/faelle/99999/angebote",
                  json={"fachplaner_id": planer["id"]}).status_code == 404,
           "unbekannter Fall muesste 404 sein")

    # ── Dokument erzeugen ──
    dokument = c.post(f"/api/mcdonalds/angebote/{angebot_id}/dokument")
    pruefe(dokument.status_code == 200,
           f"Dokument: {dokument.status_code} {dokument.text[:200]}")
    pruefe(dokument.content[:2] == b"PK",
           "Antwort ist keine Word-Datei (kein ZIP-Kopf)")
    pruefe("wordprocessingml" in dokument.headers.get("content-type", ""),
           f"MIME-Typ: {dokument.headers.get('content-type')}")
    pruefe(".docx" in dokument.headers.get("content-disposition", ""),
           f"Content-Disposition: {dokument.headers.get('content-disposition')}")
    pruefe(len(dokument.content) > 5000,
           f"Dokument verdaechtig klein: {len(dokument.content)} Bytes")

    nachher = c.get(f"/api/mcdonalds/angebote/{angebot_id}").json()
    pruefe(nachher["dokument_vorhanden"] is True,
           f"dokument_vorhanden nach dem Erzeugen: {nachher}")

    # Erneut holen liefert dieselbe Datei ohne neuen POST.
    erneut = c.get(f"/api/mcdonalds/angebote/{angebot_id}/dokument")
    pruefe(erneut.status_code == 200 and erneut.content[:2] == b"PK",
           f"Dokument erneut holen: {erneut.status_code}")

    # ── Outlook-Entwurf ──
    vorschlag = c.get(f"/api/mcdonalds/angebote/{angebot_id}/mail/vorschlag")
    pruefe(vorschlag.status_code == 200, f"Vorschlag: {vorschlag.text[:200]}")
    vorschlag = vorschlag.json()
    pruefe(vorschlag["empfaenger"] == ["planung@mueller-ing.de"],
           f"Empfaenger vorbelegt: {vorschlag['empfaenger']}")
    pruefe("Aachen" in vorschlag["betreff"], f"Betreff: {vorschlag['betreff']!r}")
    pruefe("Frau Stark" in vorschlag["nachricht"],
           f"Anrede aus den Stammdaten: {vorschlag['nachricht'][:120]!r}")
    pruefe("Mehrleistung" in vorschlag["nachricht"],
           "Mehrleistungen werden im Text nicht erwaehnt")

    entwurf = c.post(f"/api/mcdonalds/angebote/{angebot_id}/versenden", json={})
    pruefe(entwurf.status_code == 200,
           f"Entwurf: {entwurf.status_code} {entwurf.text[:200]}")
    pruefe(entwurf.headers.get("content-type", "").startswith("message/rfc822"),
           f"MIME-Typ des Entwurfs: {entwurf.headers.get('content-type')}")

    from email import message_from_bytes, policy  # noqa: E402

    mail = message_from_bytes(entwurf.content, policy=policy.default)
    pruefe(mail.get("X-Unsent") == "1",
           "X-Unsent fehlt — Outlook zeigte die Datei sonst als empfangene Mail")
    pruefe(mail.get("From") is None, "ein Entwurf darf keinen Absender tragen")
    pruefe(mail.get("To") == "planung@mueller-ing.de", f"To: {mail.get('To')!r}")
    anhaenge = [t.get_filename() for t in mail.iter_attachments()]
    pruefe(len(anhaenge) == 1 and str(anhaenge[0]).endswith(".docx"),
           f"Anhang des Entwurfs: {anhaenge}")

    # Der Entwurf wird als Versandweg notiert — abgeschickt hat ihn Outlook.
    nachher = c.get(f"/api/mcdonalds/angebote/{angebot_id}").json()
    pruefe(nachher["mail_weg"] == "entwurf", f"mail_weg: {nachher['mail_weg']!r}")
    pruefe(nachher["mail_versendet_am"] is not None,
           "mail_versendet_am muesste gesetzt sein")

    # Ohne Postausgangsserver ist "direkt senden" gesperrt — mit Ausweg.
    direkt = c.post(f"/api/mcdonalds/angebote/{angebot_id}/mail/senden", json={})
    pruefe(direkt.status_code == 503, f"senden ohne SMTP: {direkt.status_code}")
    pruefe("Outlook-Entwurf" in direkt.text,
           f"Auswegs-Hinweis fehlt: {direkt.text[:200]}")

    # ── Ein Fachplaner mit Angebot bleibt stehen ──
    geschuetzt = c.delete(f"/api/fachplaner/{planer['id']}")
    pruefe(geschuetzt.status_code == 409,
           f"Fachplaner mit Angebot: {geschuetzt.status_code}")
    pruefe("Angebot" in geschuetzt.text,
           f"Meldung nennt die Angebote nicht: {geschuetzt.text[:200]}")

    # ── Angebot und Fall loeschen ──
    pruefe(c.delete(f"/api/mcdonalds/angebote/{angebot_id}").status_code == 204,
           "Angebot loeschen")
    pruefe(c.delete(f"/api/fachplaner/{planer['id']}").status_code == 204,
           "Fachplaner nach dem Angebot loeschen")
    pruefe(c.delete(f"/api/mcdonalds/faelle/{fall_id}").status_code == 204,
           "Fall loeschen")
    pruefe(c.get(f"/api/mcdonalds/faelle/{fall_id}").status_code == 404,
           "geloeschter Fall muesste 404 sein")

    # Der angelegte Ordner bleibt bewusst stehen (siehe delete_fall).
    pruefe((STORAGE / "H-Laufwerk").is_dir(),
           "der Ordner im Netzlaufwerk darf nicht mitgeloescht werden")

    pruefe(c.get("/api/mcdonalds/faelle/99999").status_code == 404,
           "unbekannter Fall muesste 404 sein")
    pruefe(c.get("/api/mcdonalds/angebote/99999").status_code == 404,
           "unbekanntes Angebot muesste 404 sein")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Das Angebotsdokument selbst
# ─────────────────────────────────────────────────────────────────────────────

print("== Angebotsdokument ==")

pruefe(angebot_dienst.TEMPLATE_NAME == "",
       "TEMPLATE_NAME ist noch der Platzhalter (siehe TODO McDonald's)")
pruefe(angebot_dienst._betrag(1234.5) == "1.234,50 €",
       f"Betragsformat: {angebot_dienst._betrag(1234.5)!r}")
pruefe(angebot_dienst._betrag(None) == "—", "fehlender Betrag")

print(f"\n{ok} Pruefungen ok, {len(fehler)} Fehler")
for f in fehler:
    print("  FEHLER:", f)
sys.exit(1 if fehler else 0)
