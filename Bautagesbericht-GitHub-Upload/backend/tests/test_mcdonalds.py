"""Rauchtest: McDonald's — SLS lesen, UNLOCODE, Musterstruktur, Einzelabrufe.

Aufbau wie die anderen Suiten dieses Ordners: ein Skript, das oben seine
BTB_*-Umgebung setzt, auf Modulebene durchläuft und am Ende zählt. Kein
pytest — siehe tests/test_fotomail.py.

Die KI wird nicht gefahren. Sie ist in diesem Modul der Notausgang, nicht der
Weg: Die SLS-Anfrage wird nach Regeln gelesen, und genau das ist hier geprüft
— am Fixture ``beispiel_sls_nievern.eml``, das der echten Mail zum Standort
Nievern nachgebaut ist.
"""
import io
import os
import shutil
import stat
import sys
import tempfile
import zipfile
from datetime import date
from email import message_from_bytes, policy
from pathlib import Path

# Eigene Ablage im Temp-Ordner — die echte storage/ bleibt unberuehrt.
STORAGE = Path(tempfile.gettempdir()) / "hpp-mcdonaldstest"


def _weg_damit(funktion, pfad, _fehler):
    """Schreibgeschuetztes wegraeumen — der Musterordner ist es (Attribut R).

    Ohne diesen Umweg scheitert der zweite Lauf der Suite beim Aufraeumen. Der
    Dienst kopiert inzwischen ohne Attribute (siehe mcdonalds_ordner), aber
    eine Ablage aus einer aelteren Fassung koennte noch schreibgeschuetzt sein.
    """
    os.chmod(pfad, stat.S_IWRITE)
    funktion(pfad)


if STORAGE.exists():
    shutil.rmtree(STORAGE, onexc=_weg_damit)
STORAGE.mkdir(parents=True)
(STORAGE / "STANDORTE").mkdir()

WIN = str(STORAGE).replace("\\", "/")
os.environ["BTB_DATABASE_URL"] = f"sqlite:///{WIN}/test.db"
os.environ["BTB_UPLOAD_DIR"] = f"{WIN}/uploads"
os.environ["BTB_OUTPUT_DIR"] = f"{WIN}/output"
# Ausdruecklich leer: Der erste Teil prueft, dass die fehlende Konfiguration
# den Zustand "vorbereitet" ergibt und keinen Fehler.
os.environ["BTB_MCDONALDS_BASIS_STANDORTE"] = ""
os.environ["BTB_MCDONALDS_MUSTERORDNER"] = ""
os.environ["BTB_MCDONALDS_BASIS_SHAREPOINT"] = ""

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import UnlocodeEintrag  # noqa: E402
from app.services import mcdonalds_beauftragung as brief  # noqa: E402
from app.services import mcdonalds_email_analyse as analyse  # noqa: E402
from app.services import mcdonalds_ordner as ordner_dienst  # noqa: E402
from app.services import mcdonalds_sls as sls  # noqa: E402
from app.services import mcdonalds_unlocode as unlocode  # noqa: E402
from app.services.mcdonalds_musterstruktur import (  # noqa: E402
    MUSTERDATEIEN,
    MUSTERORDNER_NAME,
    UNTERORDNER,
)

# Die Tabellen anlegen, bevor der erste Abschnitt eine eigene Sitzung oeffnet.
init_db()

ok = 0
fehler = []


def pruefe(bedingung, text):
    global ok
    if bedingung:
        ok += 1
    else:
        fehler.append(text)


FIXTURE = Path(__file__).resolve().parent / "beispiel_sls_nievern.eml"
ROHDATEN = FIXTURE.read_bytes()

#: Der echte Musterordner, falls er auf diesem Rechner liegt. Nur dann laeuft
#: der Abgleich in Abschnitt 3 — auf einem Server gibt es ihn nicht.
ECHTER_MUSTER = Path.home() / "Desktop" / MUSTERORDNER_NAME


# ─────────────────────────────────────────────────────────────────────────────
# 1. Die SLS-Anfrage nach Regeln lesen
# ─────────────────────────────────────────────────────────────────────────────

print("== SLS lesen ==")

inhalt = analyse.lies_eml(ROHDATEN, FIXTURE.name)
angaben = sls.lies_sls(inhalt)

pruefe(angaben.erkannt, "die Anfrage haette erkannt werden muessen")
pruefe(angaben.phase == 1, f"Phase: {angaben.phase!r}")
pruefe(angaben.plz == "56132", f"PLZ: {angaben.plz!r}")
pruefe(angaben.ort == "Nievern", f"Ort: {angaben.ort!r}")
pruefe(angaben.strasse == "Auf d. Lay", f"Strasse: {angaben.strasse!r}")
pruefe(angaben.abgabetermin == date(2026, 9, 4),
       f"Abgabetermin: {angaben.abgabetermin!r}")
pruefe(angaben.sls_vorgang == "2535628", f"Vorgang: {angaben.sls_vorgang!r}")
pruefe(angaben.adresse == "Auf d. Lay, 56132 Nievern",
       f"Adresse: {angaben.adresse!r}")
pruefe(not angaben.hinweise, f"unerwartete Hinweise: {angaben.hinweise}")

# Der Kern: Leistungsbeginn ist das Datum der ORIGINALmail (21.08.), nicht das
# der Weiterleitung (04.09.). Sonst steht in zwei Vertraegen ein falsches Datum.
pruefe(angaben.leistungsbeginn == date(2026, 8, 21),
       f"Leistungsbeginn muesste der 21.08.2026 sein: {angaben.leistungsbeginn!r}")
pruefe(inhalt.gesendet_am.date() == date(2026, 9, 4),
       "das Fixture sollte am 04.09. weitergeleitet worden sein")

# Ohne weitergeleiteten Kopf: eigenes Sendedatum, aber mit Hinweis.
ohne_kopf = (
    b"From: no-reply@ext.mcdonalds.com\r\n"
    b"Subject: SLS - Anfrage zur F2 Vorbereitung 20095 Hamburg, Ballindamm 1\r\n"
    b"Date: Mon, 3 Aug 2026 08:00:00 +0000\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
    b"Wir bitten um Zusendung der vorgenannten Unterlagen bis zum : 31.08.2026\r\n"
)
direkt = sls.lies_sls(analyse.lies_eml(ohne_kopf, "direkt.eml"))
pruefe(direkt.erkannt and direkt.phase == 2, f"F2 direkt: {direkt!r}")
pruefe(direkt.ort == "Hamburg" and direkt.strasse == "Ballindamm 1",
       f"Hamburg/Ballindamm: {direkt.ort!r} / {direkt.strasse!r}")
pruefe(direkt.leistungsbeginn == date(2026, 8, 3),
       f"Beginn aus dem Date-Kopf: {direkt.leistungsbeginn!r}")

# Eine ganz andere Mail: nicht erkannt, mit sprechendem Hinweis.
fremd = sls.lies_sls(analyse.lies_eml(
    b"From: a@b.de\r\nSubject: Rechnung 4711\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n\r\nAnbei die Rechnung.\r\n",
    "fremd.eml",
))
pruefe(not fremd.erkannt, "eine Rechnung ist keine SLS-Anfrage")
pruefe(any("SLS" in h for h in fremd.hinweise),
       f"Hinweis auf das erwartete Format fehlt: {fremd.hinweise}")

# Betreff ohne PLZ: die Phase wird gerettet, der Rest gemeldet.
halb = sls.lies_sls(analyse.lies_eml(
    b"From: a@b.de\r\nSubject: SLS - Anfrage zur F3 Vorbereitung\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n\r\nText.\r\n",
    "halb.eml",
))
pruefe(halb.phase == 3 and not halb.erkannt, f"nur Phase: {halb!r}")
pruefe(any("Postleitzahl" in h for h in halb.hinweise),
       f"Hinweis zur fehlenden PLZ: {halb.hinweise}")

# Datumsschreibweisen
pruefe(sls.lies_datum("04.09.2026") == date(2026, 9, 4), "Ziffern DE")
pruefe(sls.lies_datum("4.9.26") == date(2026, 9, 4), "zweistelliges Jahr")
pruefe(sls.lies_datum("21 August 2026") == date(2026, 8, 21), "Text EN")
pruefe(sls.lies_datum("21. August 2026") == date(2026, 8, 21), "Text DE")
pruefe(sls.lies_datum("Freitag, 21. Dezember 2026") == date(2026, 12, 21),
       "Text DE mit Wochentag")
pruefe(sls.lies_datum("31.02.2026") is None, "31. Februar gibt es nicht")
pruefe(sls.lies_datum("") is None, "leer")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Die beiden Textfassungen
# ─────────────────────────────────────────────────────────────────────────────

print("== Einzelabruf-Texte ==")

pruefe(
    brief.betreff(beauftragung=date(2026, 8, 25), unlocode="NIV", phase=1,
                  kuerzel="KOCKS")
    == "260825_NSO_NIV_Beauftragung Phase 1 KOCKS",
    "Betreff KOCKS",
)
pruefe(
    brief.betreff(beauftragung=date(2026, 8, 25), unlocode="niv", phase=1,
                  kuerzel="rka")
    == "260825_NSO_NIV_Beauftragung Phase 1 RKA",
    "Betreff kleingeschrieben wird gross",
)
pruefe(
    "_XXX_" in brief.betreff(beauftragung=date(2026, 8, 25), unlocode="",
                             phase=1, kuerzel="RKA"),
    "fehlender Code muesste als XXX sichtbar sein",
)

termine = dict(phase=1, projekt="Nievern",
               leistungsbeginn=date(2026, 8, 21),
               projektplanung=date(2026, 9, 4),
               klaerung=date(2026, 8, 31),
               abgabe=date(2026, 9, 4))
kocks = brief.aus_daten(variante="kocks", anrede="Sehr geehrter Herr Hömmerich,",
                        firma="Kocks Consult",
                        angebot_datum=date(2026, 2, 27), **termine)
rka = brief.aus_daten(variante="rka", anrede="Sehr geehrte Frau Ammon,",
                      firma="RKA Architekten Ammon & Kanthak PartGmbB",
                      angebot_datum=date(2026, 3, 12), **termine)

# Was in beiden gleich stehen muss
for name, text in (("KOCKS", kocks), ("RKA", rka)):
    pruefe("HPP Generalplanung GmbH" in text, f"{name}: Auftraggeber fehlt")
    pruefe("Zollhof 26, 40221 Düsseldorf" in text, f"{name}: Anschrift fehlt")
    pruefe("Herr Ricardo da Costa" in text, f"{name}: Ansprechpartner fehlt")
    pruefe("Projekt: Nievern" in text, f"{name}: Projektzeile fehlt")
    pruefe("Leistungsbeginn: 21.08.2026" in text, f"{name}: Leistungsbeginn")
    pruefe("Abgabe Phase 1: 04.09.2026" in text, f"{name}: Abgabe")
    pruefe("einen Einzelauftrag für die Phase 1" in text, f"{name}: Phasensatz")
    pruefe("Bitte bestätigen Sie uns den Erhalt" in text, f"{name}: Schluss")
    pruefe("Mit freundlichen Grüßen" in text, f"{name}: Grussformel")
    pruefe("(" not in text.replace("(Phase", ""), f"{name}: Klammern im Text")

# Die Unterschiede — das ist der eigentliche Zweck der zwei Fassungen
pruefe("Kocks Consult" in kocks, "KOCKS: Firmenname")
pruefe("gemäß ihrem Angebot vom 27.02.2026" in kocks, "KOCKS: Angebotsdatum")
pruefe("Erstellung der Projektplanung: 04.09.2026" in kocks,
       "KOCKS: Projektplanungszeile fehlt")
pruefe("Bauordnungsrecht durch RKA: 31.08.2026" in kocks,
       "KOCKS: Klaerung muesste 'durch RKA' nennen")

pruefe("RKA Architekten Ammon & Kanthak PartGmbB" in rka, "RKA: Firmenname")
pruefe("gemäß ihrem Angebot vom 12.03.2026" in rka, "RKA: Angebotsdatum")
pruefe("Erstellung der Projektplanung" not in rka,
       "RKA: darf KEINE Projektplanungszeile haben")
pruefe("Bauordnungsrecht: 31.08.2026" in rka
       and "durch RKA" not in rka,
       "RKA: Klaerung ohne 'durch RKA'")

# Fehlende Termine werden sichtbar, nicht weggelassen
lueckenhaft = brief.aus_daten(
    variante="kocks", anrede="Sehr geehrte Damen und Herren,", firma="X",
    phase=1, angebot_datum=None, projekt="Y", leistungsbeginn=None,
    projektplanung=None, klaerung=None, abgabe=None,
)
pruefe(lueckenhaft.count("___") >= 4,
       "fehlende Termine muessten als ___ auffallen")

# Unbekannte Fassung faellt auf die schlichtere zurueck, statt zu krachen
pruefe("Erstellung der Projektplanung" not in brief.text(
    "gibtsnicht", brief.Werte(
        anrede="A", firma="B", phase=1, angebot_datum="1", projekt="C",
        leistungsbeginn="2", projektplanung="3", klaerung="4", abgabe="5")),
    "unbekannte Fassung muesste die RKA-Fassung nehmen")

pruefe(brief.klaerungstermin(date(2026, 8, 25)) == date(2026, 8, 28),
       f"Klaerung +3: {brief.klaerungstermin(date(2026, 8, 25))}")
pruefe(brief.ablagepfad("090_VAA_Kocks")
       == "18-GP/12_Verträge/02_Subplaner/090_VAA_Kocks/02_Vertrag",
       "Ablagepfad KOCKS")
pruefe(brief.dateiname("260825_NSO_NIV_Beauftragung Phase 1 KOCKS")
       == "260825_NSO_NIV_Beauftragung Phase 1 KOCKS.eml", "Dateiname")
pruefe("/" not in brief.dateiname("A/B:C"), "verbotene Zeichen im Dateinamen")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Die Musterstruktur
# ─────────────────────────────────────────────────────────────────────────────

print("== Musterstruktur ==")

pruefe(len(UNTERORDNER) == 163, f"Anzahl Unterordner: {len(UNTERORDNER)}")
pruefe(len(set(UNTERORDNER)) == len(UNTERORDNER), "Dubletten in der Liste")
pruefe(len(MUSTERDATEIEN) == 5, f"Anzahl Vorlagendateien: {len(MUSTERDATEIEN)}")

# Die Ordner, an denen der ganze Ablauf haengt
for pflicht in (
    "18-GP/12_Verträge/02_Subplaner/090_VAA_Kocks/02_Vertrag",
    "18-GP/12_Verträge/02_Subplaner/010_OPG_ARC_RKA/02_Vertrag",
    "18-GP/12_Verträge/01_Generalplaner/02_Vertrag",
    "PHASE 0", "PHASE 1", "PHASE 2", "PHASE 3", "PHASE 4 & 5",
    "PHASE 1/02_Checkliste, Behörde/Kampfmittelfreiheit",
    "PHASE 3/02_Behörden/01_Bauantrag/JJMMTT_Nachforderung/JJMMTT_Eingang",
):
    pruefe(pflicht in UNTERORDNER, f"fehlt in der Liste: {pflicht}")

# Jeder Pfad muss einen Elternteil haben — sonst ist die Liste lueckenhaft
for eintrag in UNTERORDNER:
    if "/" in eintrag:
        eltern = eintrag.rsplit("/", 1)[0]
        pruefe(eltern in UNTERORDNER, f"Elternordner fehlt zu: {eintrag}")

# Abgleich mit dem echten Ordner, wenn er hier liegt (siehe Modultext des
# Dienstes: der Ordner ist die Wahrheit, die Liste nur die Notfassung).
if ECHTER_MUSTER.is_dir():
    echt = {p.relative_to(ECHTER_MUSTER).as_posix()
            for p in ECHTER_MUSTER.rglob("*") if p.is_dir()}
    liste = set(UNTERORDNER)
    pruefe(echt == liste,
           f"Liste weicht vom Musterordner ab: nur im Ordner "
           f"{sorted(echt - liste)[:3]}, nur in der Liste "
           f"{sorted(liste - echt)[:3]}")
    echte_dateien = {p.relative_to(ECHTER_MUSTER).as_posix()
                     for p in ECHTER_MUSTER.rglob("*") if p.is_file()}
    pruefe(echte_dateien == set(MUSTERDATEIEN),
           f"Dateiliste weicht ab: {sorted(echte_dateien ^ set(MUSTERDATEIEN))}")
    print(f"   (gegen den echten Musterordner geprueft: {len(echt)} Ordner)")
else:
    print("   (Musterordner nicht auf diesem Rechner — Abgleich uebersprungen)")

pruefe(ordner_dienst.ordnername("NIV", "Nievern") == "a_NIV_Nievern", "Ordnername")
pruefe(ordner_dienst.ordnername(None, "Nievern") == "a_XXX_Nievern",
       "Ordnername ohne Code")
pruefe(ordner_dienst.ordnername("niv", "Nievern") == "a_NIV_Nievern",
       "Code wird gross geschrieben")
pruefe(ordner_dienst.ordnername("HAM", 'Köln Ring / Nord: "neu"')
       == "a_HAM_Köln Ring Nord neu", "verbotene Zeichen")
pruefe(ordner_dienst.saubere_bezeichnung("Nievern.") == "Nievern",
       "Punkt am Ende (Windows verschluckt ihn sonst)")
pruefe(ordner_dienst.ORDNER_PRAEFIX == "a_", "Praefix a_")
pruefe(ordner_dienst.ordnername("NIV", "").startswith("a_"),
       "auch ohne Namen mit Praefix")

# Die HPP-Adresse in Kopie wird aus dem Ortscode gebildet.
pruefe(brief.hpp_kopie("NIV") == "mcd-niv@hpp.com",
       f"hpp_kopie: {brief.hpp_kopie('NIV')!r}")
pruefe(brief.hpp_kopie("niv") == "mcd-niv@hpp.com", "kleingeschrieben")
pruefe(brief.hpp_kopie("") == "", "ohne Code keine erfundene Adresse")
pruefe(brief.hpp_kopie("XX") == "", "zweistellig ist kein Code")


# ─────────────────────────────────────────────────────────────────────────────
# 4. UNLOCODE
# ─────────────────────────────────────────────────────────────────────────────

print("== UNLOCODE ==")

pruefe(unlocode.normalisiere("München") == "muenchen", "Umlaut-Umschrift")
pruefe(unlocode.normalisiere("Baden-Baden") == "badenbaden", "Bindestrich")
pruefe(unlocode.ort_aus_adresse("Auf d. Lay, 56132 Nievern") == "Nievern",
       "ort_aus_adresse")

db = SessionLocal()
try:
    # Die Anlage 5.1 liegt im Programm und wird von init_db eingelesen —
    # niemand muss sie hochladen. Das ist der Kern: Ohne Liste hiesse jeder
    # Ordner "XXX_Nievern".
    mitgeliefert = db.query(UnlocodeEintrag).count()
    pruefe(mitgeliefert > 9000,
           f"mitgelieferte Liste nicht eingelesen: {mitgeliefert} Orte")
    aus_liste = unlocode.ermittle(db, "Nievern")
    pruefe(aus_liste is not None and aus_liste.code == "NIV",
           f"Nievern aus der mitgelieferten Liste: {aus_liste!r}")
    # Auch der Weg, den die Oberflaeche geht: aus der Adresse den Ort ziehen.
    aus_adresse = unlocode.ermittle(
        db, unlocode.ort_aus_adresse("Auf d. Lay, 56132 Nievern"))
    pruefe(aus_adresse is not None and aus_adresse.code == "NIV",
           f"NIV aus der Adresse: {aus_adresse!r}")

    db.query(UnlocodeEintrag).delete()
    db.commit()
    pruefe(unlocode.ermittle(db, "Nievern") is None,
           "ohne Tabelle darf es keinen Treffer geben")

    db.bulk_insert_mappings(UnlocodeEintrag, [
        {"code": "NIV", "ort": "Nievern",
         "ort_normal": unlocode.normalisiere("Nievern"),
         "bundesland": "Rheinland-Pfalz"},
        {"code": "HAM", "ort": "Hamburg",
         "ort_normal": unlocode.normalisiere("Hamburg"), "bundesland": "Hamburg"},
        {"code": "MUC", "ort": "München",
         "ort_normal": unlocode.normalisiere("München"), "bundesland": "Bayern"},
        {"code": "AAC", "ort": "Aach",
         "ort_normal": unlocode.normalisiere("Aach"),
         "bundesland": "Baden-Württemberg"},
        {"code": "A2H", "ort": "Aach",
         "ort_normal": unlocode.normalisiere("Aach"),
         "bundesland": "Rheinland-Pfalz"},
    ])
    db.commit()

    treffer = unlocode.ermittle(db, "Nievern")
    pruefe(treffer is not None and treffer.code == "NIV"
           and treffer.art == "exakt", f"Nievern -> NIV: {treffer!r}")
    pruefe(unlocode.ermittle(db, "Muenchen").code == "MUC", "Muenchen -> MUC")
    pruefe(unlocode.ermittle(db, "Aach", "Rheinland-Pfalz").code == "A2H",
           "Bundesland entscheidet bei Gleichnamigen")
    unscharf = unlocode.ermittle(db, "Nievren")
    pruefe(unscharf is not None and unscharf.code == "NIV"
           and unscharf.art == "unscharf", f"Tippfehler: {unscharf!r}")
    pruefe(unlocode.ermittle(db, "Zzzzville") is None, "Zzzzville")
finally:
    db.close()


# ─────────────────────────────────────────────────────────────────────────────
# 5. Der ganze Ablauf ueber das API
# ─────────────────────────────────────────────────────────────────────────────

print("== API ==")

with TestClient(app) as c:
    # ── Faehigkeiten ohne Laufwerk ──
    faehig = c.get("/api/mcdonalds/faehigkeiten").json()
    pruefe(faehig["ordner_laufwerk"] is False,
           f"ordner_laufwerk muesste aus sein: {faehig}")
    pruefe(faehig["unterordner"] == 163, f"unterordner: {faehig}")
    pruefe(len(faehig["textvarianten"]) == 2, f"textvarianten: {faehig}")

    # ── Startwerte: Kocks und RKA da, aber ohne Adresse ──
    planer = c.get("/api/subplaner").json()
    pruefe(len(planer) == 2, f"zwei Subplaner erwartet: {len(planer)}")
    nach_kuerzel = {p["kuerzel"]: p for p in planer}
    pruefe(set(nach_kuerzel) == {"KOCKS", "RKA"}, f"Kuerzel: {list(nach_kuerzel)}")
    pruefe(all(p["phase"] == 1 for p in planer), "beide in Phase 1")
    pruefe(nach_kuerzel["KOCKS"]["ordner"] == "090_VAA_Kocks",
           f"KOCKS-Ordner: {nach_kuerzel['KOCKS']['ordner']!r}")
    pruefe(nach_kuerzel["RKA"]["ordner"] == "010_OPG_ARC_RKA",
           f"RKA-Ordner: {nach_kuerzel['RKA']['ordner']!r}")
    pruefe(nach_kuerzel["KOCKS"]["kopie_emails"] == ["mcd@kocks-ing.de"],
           f"KOCKS-Kopie: {nach_kuerzel['KOCKS']['kopie_emails']!r}")
    pruefe(nach_kuerzel["RKA"]["kopie_emails"] == [],
           f"RKA hat kein eigenes Sammelpostfach: {nach_kuerzel['RKA']['kopie_emails']!r}")
    pruefe(nach_kuerzel["KOCKS"]["angebot_datum"] == "2026-02-27",
           f"KOCKS-Angebot: {nach_kuerzel['KOCKS']['angebot_datum']!r}")
    pruefe(nach_kuerzel["RKA"]["angebot_datum"] == "2026-03-12",
           f"RKA-Angebot: {nach_kuerzel['RKA']['angebot_datum']!r}")
    pruefe("Hömmerich" in nach_kuerzel["KOCKS"]["anrede"],
           f"KOCKS-Anrede: {nach_kuerzel['KOCKS']['anrede']!r}")
    pruefe(all(p["emails"] == [] for p in planer),
           "die Adressen duerfen NICHT geraten sein")
    pruefe([p["phase"] for p in c.get("/api/subplaner?phase=1").json()] == [1, 1],
           "Filter nach Phase")
    pruefe(c.get("/api/subplaner?phase=2").json() == [], "Phase 2 ist leer")

    # ── SLS-Anfrage hochladen ──
    st = c.post("/api/mcdonalds/standorte",
                files={"datei": (FIXTURE.name, ROHDATEN, "message/rfc822")})
    pruefe(st.status_code == 201, f"Upload: {st.status_code} {st.text[:200]}")
    st = st.json()
    sid = st["id"]
    pruefe(st["sls_erkannt"] is True, f"sls_erkannt: {st}")
    pruefe(st["analysiert_am"] is None,
           "ohne KI-Notausgang darf kein Analysezeitpunkt stehen")
    pruefe(st["phase"] == 1 and st["ort"] == "Nievern", f"Angaben: {st}")
    pruefe(st["abgabetermin"] == "2026-09-04", f"Abgabe: {st}")
    pruefe(st["leistungsbeginn"] == "2026-08-21", f"Beginn: {st}")
    pruefe(st["sls_vorgang"] == "2535628", f"Vorgang: {st}")
    pruefe("bis zum" in st["roh_text"], "roh_text nicht gespeichert")

    # Ohne Laufwerk: "vorbereitet", KEIN Fehler.
    geladen = c.get(f"/api/mcdonalds/standorte/{sid}").json()
    pruefe(geladen["ordner_status"] == "vorbereitet",
           f"Status ohne Laufwerk: {geladen['ordner_status']!r}")
    pruefe(geladen["ordner_name"] == "a_NIV_Nievern",
           f"Ordnername: {geladen['ordner_name']!r}")
    pruefe(geladen["unlocode"] == "NIV", f"Code: {geladen['unlocode']!r}")
    pruefe(geladen["ordner_pfad"] is None, "kein Pfad ohne Laufwerk")
    pruefe("Büronetz" in (geladen["fehlermeldung"] or ""),
           f"Meldung erklaert das nicht: {geladen['fehlermeldung']!r}")

    # ── Beauftragung ohne Adresse: abgelehnt, mit Grund ──
    vor = c.post(f"/api/mcdonalds/standorte/{sid}/beauftragungen/vorschau",
                 json={"phase": 1, "beauftragung_am": "2026-08-25"})
    pruefe(vor.status_code == 200, f"Vorschau: {vor.text[:200]}")
    vor = vor.json()
    pruefe(len(vor) == 2, f"zwei Vorschauen erwartet: {len(vor)}")
    pruefe(all(not v["bereit"] for v in vor), "ohne Adresse nicht bereit")
    pruefe(all("E-Mail-Adresse" in v["hindernis"] for v in vor),
           f"Hindernis benennt die Adresse nicht: {[v['hindernis'] for v in vor]}")

    verweigert = c.post(f"/api/mcdonalds/standorte/{sid}/beauftragungen",
                        json={"phase": 1})
    pruefe(verweigert.status_code == 400,
           f"Erzeugen ohne Adresse: {verweigert.status_code}")
    pruefe(c.get(f"/api/mcdonalds/standorte/{sid}").json()["beauftragungen"] == [],
           "es darf NICHTS halb erzeugt worden sein")

    # ── Adressen nachtragen ──
    for kuerzel, adressen in (
        ("KOCKS", ["hoemmerich@kocks-consult.de", "buero@kocks-consult.de"]),
        ("RKA", ["ammon@rka-architekten.de"]),
    ):
        r = c.patch(f"/api/subplaner/{nach_kuerzel[kuerzel]['id']}",
                    json={"emails": adressen})
        pruefe(r.status_code == 200, f"PATCH {kuerzel}: {r.text[:150]}")
        pruefe(r.json()["emails"] == adressen, f"{kuerzel}-Adressen: {r.json()}")

    pruefe(c.patch(f"/api/subplaner/{nach_kuerzel['RKA']['id']}",
                   json={"emails": ["keine-adresse"]}).status_code == 422,
           "kaputte Adresse muesste 422 sein")

    # ── Vorschau jetzt bereit, Texte stimmen ──
    vor = c.post(f"/api/mcdonalds/standorte/{sid}/beauftragungen/vorschau",
                 json={"phase": 1, "beauftragung_am": "2026-08-25"}).json()
    pruefe(all(v["bereit"] for v in vor), f"jetzt bereit: {vor}")
    nach_name = {v["subplaner_kuerzel"]: v for v in vor}
    pruefe(nach_name["KOCKS"]["betreff"]
           == "260825_NSO_NIV_Beauftragung Phase 1 KOCKS",
           f"Betreff KOCKS: {nach_name['KOCKS']['betreff']!r}")
    pruefe(nach_name["RKA"]["betreff"]
           == "260825_NSO_NIV_Beauftragung Phase 1 RKA",
           f"Betreff RKA: {nach_name['RKA']['betreff']!r}")
    # Kopie: Sammelpostfach der Firma plus HPP-Adresse des Standorts.
    pruefe(nach_name["KOCKS"]["kopie"]
           == ["mcd@kocks-ing.de", "mcd-niv@hpp.com"],
           f"KOCKS-Kopie: {nach_name['KOCKS']['kopie']!r}")
    pruefe(nach_name["RKA"]["kopie"] == ["mcd-niv@hpp.com"],
           f"RKA-Kopie: {nach_name['RKA']['kopie']!r}")
    pruefe(nach_name["KOCKS"]["ablage"].endswith("090_VAA_Kocks/02_Vertrag"),
           f"Ablage KOCKS: {nach_name['KOCKS']['ablage']!r}")
    pruefe(nach_name["RKA"]["ablage"].endswith("010_OPG_ARC_RKA/02_Vertrag"),
           f"Ablage RKA: {nach_name['RKA']['ablage']!r}")
    pruefe("Erstellung der Projektplanung" in nach_name["KOCKS"]["text"],
           "KOCKS-Fassung nicht benutzt")
    pruefe("Erstellung der Projektplanung" not in nach_name["RKA"]["text"],
           "RKA bekommt die falsche Fassung")
    pruefe("Leistungsbeginn: 21.08.2026" in nach_name["KOCKS"]["text"],
           "Leistungsbeginn aus der Mail nicht eingesetzt")
    pruefe("Abgabe Phase 1: 04.09.2026" in nach_name["KOCKS"]["text"],
           "Abgabetermin aus der Mail nicht eingesetzt")
    # Klaerung ohne eigene Angabe = Beauftragung + 3
    pruefe("Bauordnungsrecht durch RKA: 28.08.2026" in nach_name["KOCKS"]["text"],
           "Klaerungsregel nicht angewandt")
    # Eigene Angabe gewinnt
    eigen = c.post(f"/api/mcdonalds/standorte/{sid}/beauftragungen/vorschau",
                   json={"phase": 1, "beauftragung_am": "2026-08-25",
                         "klaerung": "2026-08-31"}).json()
    pruefe(all("31.08.2026" in v["text"] for v in eigen),
           "eigener Klaerungstermin wurde nicht uebernommen")

    # ── Erzeugen: zwei Entwuerfe als ZIP ──
    r = c.post(f"/api/mcdonalds/standorte/{sid}/beauftragungen",
               json={"phase": 1, "beauftragung_am": "2026-08-25"})
    pruefe(r.status_code == 200, f"Erzeugen: {r.status_code} {r.text[:200]}")
    pruefe(r.headers["content-type"].startswith("application/zip"),
           f"MIME: {r.headers['content-type']}")
    with zipfile.ZipFile(io.BytesIO(r.content)) as archiv:
        namen = sorted(archiv.namelist())
        pruefe(namen == ["260825_NSO_NIV_Beauftragung Phase 1 KOCKS.eml",
                         "260825_NSO_NIV_Beauftragung Phase 1 RKA.eml"],
               f"ZIP-Inhalt: {namen}")
        archiv_rohdaten = archiv.read(namen[0])
        mail = message_from_bytes(archiv_rohdaten, policy=policy.default)
    pruefe(mail.get("X-Unsent") == "1",
           "X-Unsent fehlt — Outlook zeigte die Datei sonst als empfangene Mail")
    pruefe(mail.get("From") is None, "ein Entwurf darf keinen Absender tragen")
    pruefe(mail.get("To") == "hoemmerich@kocks-consult.de, buero@kocks-consult.de",
           f"To: {mail.get('To')!r}")
    pruefe(mail.get("Cc") == "mcd@kocks-ing.de, mcd-niv@hpp.com",
           f"Cc: {mail.get('Cc')!r}")

    # Der Wortlaut darf NICHT durch weiche Umbrueche zerrissen sein: Genau
    # diese vier Stellen zeigten "angegeb=nen", "Einga=g", "=er E-Mail",
    # "Einzel=uftrag", weil quoted-printable bei 76 Zeichen umbricht.
    inhalt_mail = mail.get_content()
    pruefe(mail.get("Content-Transfer-Encoding") == "8bit",
           f"Kodierung: {mail.get('Content-Transfer-Encoding')!r}")
    for satz in ("am angegebenen Standort.",
                 "mit Eingang dieser Beauftragung.",
                 "dieses Einzelabrufs per E-Mail.",
                 "einen Einzelauftrag für die Phase 1"):
        pruefe(satz in inhalt_mail, f"zerrissener Satz: {satz!r}")
    # Und im ROHEN Dateiinhalt darf kein weicher Umbruch stehen.
    weicher_umbruch = bytes([61, 13, 10])   # '=' CR LF
    pruefe(weicher_umbruch not in archiv_rohdaten
           and bytes([61, 10]) not in archiv_rohdaten,
           "weiche quoted-printable-Umbrueche in der .eml")
    pruefe(not list(mail.iter_attachments()),
           "der Einzelabruf ist der Mailtext und braucht keinen Anhang")
    pruefe("Sehr geehrter Herr Hömmerich," in mail.get_content(),
           "Anrede aus den Stammdaten fehlt")

    # Am Standort haengen jetzt zwei Beauftragungen, ohne Ablage (kein Laufwerk)
    detail = c.get(f"/api/mcdonalds/standorte/{sid}").json()
    pruefe(len(detail["beauftragungen"]) == 2,
           f"Beauftragungen am Standort: {len(detail['beauftragungen'])}")
    pruefe(all(b["eml_pfad"] is None for b in detail["beauftragungen"]),
           "ohne Laufwerk kann nichts abgelegt sein")
    pruefe(all("mcd-niv@hpp.com" in b["kopie"] for b in detail["beauftragungen"]),
           f"Kopie gemerkt: {[b['kopie'] for b in detail['beauftragungen']]}")
    pruefe(all(b["mail_weg"] == "entwurf" for b in detail["beauftragungen"]),
           "mail_weg muesste 'entwurf' sein")
    pruefe(all(b["beauftragung_am"] == "2026-08-25"
               for b in detail["beauftragungen"]), "Beauftragungsdatum gemerkt")

    # Entwurf erneut holen — aus dem gespeicherten Wortlaut
    erneut = c.get(
        f"/api/mcdonalds/beauftragungen/{detail['beauftragungen'][0]['id']}/entwurf"
    )
    pruefe(erneut.status_code == 200, f"Entwurf erneut: {erneut.status_code}")
    pruefe(b"X-Unsent" in erneut.content, "X-Unsent fehlt beim erneuten Abruf")

    # ── Subplaner mit Beauftragung bleibt stehen ──
    geschuetzt = c.delete(f"/api/subplaner/{nach_kuerzel['KOCKS']['id']}")
    pruefe(geschuetzt.status_code == 409,
           f"Subplaner mit Einzelabruf: {geschuetzt.status_code}")
    pruefe("Einzelabruf" in geschuetzt.text,
           f"Meldung nennt die Einzelabrufe nicht: {geschuetzt.text[:200]}")

    # ── Jetzt MIT Laufwerk und echter Struktur ──
    settings.mcdonalds_basis_standorte = str(STORAGE / "STANDORTE")
    if ECHTER_MUSTER.is_dir():
        settings.mcdonalds_musterordner = str(ECHTER_MUSTER)
    try:
        neu = c.post(f"/api/mcdonalds/standorte/{sid}/ordner").json()
        pruefe(neu["ordner_status"] == "angelegt",
               f"Status mit Laufwerk: {neu['ordner_status']!r} "
               f"({neu['fehlermeldung']!r})")
        wurzel = Path(neu["ordner_pfad"])
        pruefe(wurzel.is_dir() and wurzel.name == "a_NIV_Nievern",
               f"Ordner: {neu['ordner_pfad']!r}")
        pruefe(neu["ordner_anzahl"] == 163,
               f"Unterordner angelegt: {neu['ordner_anzahl']}")
        for pflicht in (
            "18-GP/12_Verträge/02_Subplaner/090_VAA_Kocks/02_Vertrag",
            "18-GP/12_Verträge/02_Subplaner/010_OPG_ARC_RKA/02_Vertrag",
            "PHASE 3/02_Behörden/01_Bauantrag/JJMMTT_Nachforderung/JJMMTT_Eingang",
            "PHASE 4 & 5/09_Gewährleistung",
        ):
            pruefe((wurzel / pflicht).is_dir(), f"Ordner fehlt: {pflicht}")

        # Zweiter Aufruf darf nicht scheitern (Struktur ergaenzen)
        pruefe(c.post(f"/api/mcdonalds/standorte/{sid}/ordner").status_code == 200,
               "zweiter Ordner-Aufruf muesste durchgehen")

        # Beauftragungen erneut: jetzt landen sie im Vertragsordner
        c.post(f"/api/mcdonalds/standorte/{sid}/beauftragungen",
               json={"phase": 1, "beauftragung_am": "2026-08-25"})
        abgelegt = sorted(p.relative_to(wurzel).as_posix()
                          for p in wurzel.rglob("*.eml"))
        pruefe(len(abgelegt) == 2, f"abgelegte Entwuerfe: {abgelegt}")
        pruefe(any("090_VAA_Kocks/02_Vertrag" in a for a in abgelegt),
               f"KOCKS nicht im Vertragsordner: {abgelegt}")
        pruefe(any("010_OPG_ARC_RKA/02_Vertrag" in a for a in abgelegt),
               f"RKA nicht im Vertragsordner: {abgelegt}")
    finally:
        settings.mcdonalds_basis_standorte = ""
        settings.mcdonalds_musterordner = ""

    # ── Korrigieren ──
    korrigiert = c.patch(f"/api/mcdonalds/standorte/{sid}",
                         json={"standort_name": "Nievern Auf d. Lay",
                               "phase": 2})
    pruefe(korrigiert.status_code == 200, f"PATCH: {korrigiert.text[:200]}")
    pruefe(korrigiert.json()["standort_name"] == "Nievern Auf d. Lay",
           f"Name nach PATCH: {korrigiert.json()['standort_name']!r}")
    pruefe(c.patch(f"/api/mcdonalds/standorte/{sid}",
                   json={"phase": 7}).status_code == 422,
           "Phase 7 muesste 422 sein")

    # ── Von Hand erfassen ──
    hand = c.post("/api/mcdonalds/standorte/manuell", json={
        "ort": "Hamburg", "plz": "20095", "strasse": "Ballindamm 1",
        "phase": 1, "notiz": "Anruf Herr Weber, 10.09.2026",
    })
    pruefe(hand.status_code == 201, f"manuell: {hand.text[:200]}")
    hand = hand.json()
    pruefe(hand["quelle"] == "manuell" and hand["sls_erkannt"] is False,
           f"Quelle: {hand}")
    pruefe(hand["standort_name"] == "Hamburg", "Name aus dem Ort vorbelegt")
    pruefe(c.post("/api/mcdonalds/standorte/manuell",
                  json={"ort": ""}).status_code == 422,
           "leerer Ort muesste 422 sein")

    # ── Phase ohne Subplaner ──
    leer = c.post(f"/api/mcdonalds/standorte/{hand['id']}/beauftragungen",
                  json={"phase": 3})
    pruefe(leer.status_code == 400, f"Phase 3 ohne Subplaner: {leer.status_code}")
    pruefe("Stammdaten" in leer.text or "Subplaner" in leer.text,
           f"Meldung nennt die Stammdaten nicht: {leer.text[:200]}")

    # ── Einen Subplaner in Phase 2 anlegen ──
    neuer = c.post("/api/subplaner", json={
        "phase": 2, "name": "Imagine Structure GmbH", "kuerzel": "TWP",
        "ordner": "030_TWP_Imagine Structure",
        "ansprechpartner": "Herr Meyer",
        "anrede": "Sehr geehrter Herr Meyer,",
        "emails": ["meyer@imagine-structure.de"],
        "angebot_datum": "2026-05-04", "textvariante": "rka", "sortierung": 1,
    })
    pruefe(neuer.status_code == 201, f"Phase-2-Subplaner: {neuer.text[:200]}")
    pruefe(len(c.get("/api/subplaner?phase=2").json()) == 1, "jetzt einer in Phase 2")
    pruefe(c.delete(f"/api/subplaner/{neuer.json()['id']}").status_code == 204,
           "Subplaner ohne Einzelabruf loeschen")
    pruefe(c.delete("/api/subplaner/99999").status_code == 404,
           "unbekannter Subplaner muesste 404 sein")

    # ── UNLOCODE-Upload ueber das API ──
    def baue_xlsx(zeilen):
        """Eine minimale .xlsx mit Inline-Zeichenketten."""
        from xml.sax.saxutils import escape

        def spalte(nummer):
            name = ""
            while nummer >= 0:
                name = chr(ord("A") + nummer % 26) + name
                nummer = nummer // 26 - 1
            return name

        xml = []
        for i, zeile in enumerate(zeilen, start=1):
            zellen = "".join(
                f'<c r="{spalte(j)}{i}" t="inlineStr"><is><t>{escape(str(w))}'
                f"</t></is></c>"
                for j, w in enumerate(zeile) if str(w) != ""
            )
            xml.append(f'<row r="{i}">{zellen}</row>')
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        blatt = (f'<?xml version="1.0"?><worksheet xmlns="{ns}"><sheetData>'
                 + "".join(xml) + "</sheetData></worksheet>")
        mappe = (f'<?xml version="1.0"?><workbook xmlns="{ns}"><sheets>'
                 '<sheet name="UNLOCODE_DE" sheetId="1" r:id="rId1" '
                 'xmlns:r="http://schemas.openxmlformats.org/'
                 'officeDocument/2006/relationships"/></sheets></workbook>')
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
        ["NIV", "Nievern", "Rheinland-Pfalz", "5023N 00745E", ""],
        ["HAM", "Hamburg", "Hamburg", "5333N 00958E", ""],
        ["", "Zeile ohne Code", "", "", ""],
    ])
    geladen = c.post("/api/mcdonalds/unlocode-tabelle",
                     files={"datei": ("anlage.xlsx", tabelle,
                                      "application/vnd.ms-excel")})
    pruefe(geladen.status_code == 200, f"Upload: {geladen.text[:200]}")
    pruefe(geladen.json()["eingelesen"] == 2, f"eingelesen: {geladen.json()}")
    pruefe(geladen.json()["uebersprungen"] == 1, f"uebersprungen: {geladen.json()}")
    pruefe(c.get("/api/mcdonalds/unlocode?ort=Nievern").json()["code"] == "NIV",
           "Nachschlagen ueber das API")
    pruefe(c.get("/api/mcdonalds/unlocode?ort=Zzzz").status_code == 404,
           "unbekannter Ort muesste 404 sein")
    kaputt = c.post("/api/mcdonalds/unlocode-tabelle",
                    files={"datei": ("x.xlsx", b"kein zip", "application/octet")})
    pruefe(kaputt.status_code == 400 and ".xlsx" in kaputt.text,
           f"kaputte Datei: {kaputt.status_code} {kaputt.text[:150]}")

    # ── Loeschen ──
    pruefe(c.delete(f"/api/mcdonalds/standorte/{hand['id']}").status_code == 204,
           "Standort loeschen")
    pruefe(c.get(f"/api/mcdonalds/standorte/{hand['id']}").status_code == 404,
           "geloeschter Standort muesste 404 sein")
    pruefe(c.get("/api/mcdonalds/standorte/99999").status_code == 404,
           "unbekannter Standort muesste 404 sein")
    pruefe((STORAGE / "STANDORTE" / "a_NIV_Nievern").is_dir(),
           "der Ordner im Projektlaufwerk darf nicht mitgeloescht werden")

    # ── Zu grosse Datei ──
    zu_gross = c.post("/api/mcdonalds/standorte", files={
        "datei": ("gross.eml", b"x" * (26 * 1024 * 1024), "message/rfc822")})
    pruefe(zu_gross.status_code == 413, f"zu gross: {zu_gross.status_code}")

print(f"\n{ok} Pruefungen ok, {len(fehler)} Fehler")
for f in fehler:
    print("  FEHLER:", f)
sys.exit(1 if fehler else 0)
