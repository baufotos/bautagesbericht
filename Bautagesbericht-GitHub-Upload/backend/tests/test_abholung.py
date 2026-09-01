"""Abholung der Fotosätze durch die Bürorechner.

Geprüft wird vor allem der Fall, der im Alltag wehtut: Zwei Kollegen haben das
Abholskript in der Aufgabenplanung, beide Rechner laufen, beide fragen im
selben Moment. Genau einer darf den Satz bekommen.
"""
import io
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

STORAGE = Path(tempfile.gettempdir()) / "hpp-abholtest"
if STORAGE.exists():
    shutil.rmtree(STORAGE)
STORAGE.mkdir(parents=True)

WIN = str(STORAGE).replace("\\", "/")
os.environ["BTB_DATABASE_URL"] = f"sqlite:///{WIN}/test.db"
os.environ["BTB_UPLOAD_DIR"] = f"{WIN}/uploads"
os.environ["BTB_OUTPUT_DIR"] = f"{WIN}/output"
# Ruhezeit aus: Der Test lädt hoch und holt sofort ab.
os.environ["BTB_ABHOL_WARTEZEIT_MINUTEN"] = "0"

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Fotosatz  # noqa: E402
from app.services import abholung  # noqa: E402

ok = 0
fehler = []


def pruefe(bedingung, text):
    global ok
    if bedingung:
        ok += 1
    else:
        fehler.append(text)


def bild(farbe=(140, 160, 190)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", (1200, 900), farbe).save(puffer, format="JPEG", quality=90)
    return puffer.getvalue()


ZIEL = r"L:\Bauleitung-Hamburg\K30159 Kita Nord\01 FOTOS"

with TestClient(app) as c:
    # ── Projekt mit gepflegtem Zielordner ──
    projekt = c.post("/api/projekte", json={
        "name": "K30159 Kita Nord",
        "adresse": "",
        "foto_zielpfad": ZIEL,
    })
    pruefe(projekt.status_code == 201, f"Projekt anlegen: {projekt.status_code}")
    projekt = projekt.json()
    pid = projekt["id"]
    pruefe(projekt["foto_zielpfad"] == ZIEL, f"Zielpfad gespeichert: {projekt}")

    # Zweites Projekt ohne Pfad — soll leer bleiben, nicht raten.
    ohne = c.post("/api/projekte", json={"name": "K30160 Schule Ost"}).json()
    pruefe(ohne["foto_zielpfad"] == "", f"ohne Pfad leer: {ohne['foto_zielpfad']}")

    # ── Pfad nachtraeglich pflegen (der Normalfall) ──
    ZIEL2 = r"L:\Bauleitung-Hamburg\K30160 Schule Ost\01 FOTOS"
    geaendert = c.patch(f"/api/projekte/{ohne['id']}",
                        json={"foto_zielpfad": ZIEL2})
    pruefe(geaendert.status_code == 200, f"PATCH: {geaendert.status_code}")
    pruefe(geaendert.json()["foto_zielpfad"] == ZIEL2,
           f"PATCH Pfad: {geaendert.json()['foto_zielpfad']}")
    # Nicht gesetzte Felder bleiben unveraendert.
    pruefe(geaendert.json()["name"] == "K30160 Schule Ost",
           "PATCH laesst den Namen stehen")

    # ── Fotosatz mit Fotos ──
    satz = c.post("/api/fotosaetze", json={
        "projekt_id": pid, "kategorie": "Baustellenbegehung",
        "datum": "2026-08-19", "notiz": "Achse C",
    }).json()
    sid = satz["id"]
    hoch = c.post(f"/api/fotosaetze/{sid}/fotos", files=[
        ("dateien", ("IMG_1.jpg", bild(), "image/jpeg")),
        ("dateien", ("IMG_2.jpg", bild((90, 140, 90)), "image/jpeg")),
    ])
    pruefe(hoch.status_code == 201, f"Upload: {hoch.status_code} {hoch.text[:200]}")

    # ── Offene Liste ──
    offen = c.get("/api/fotosaetze/abholung/offen")
    pruefe(offen.status_code == 200, f"offen: {offen.status_code} {offen.text[:200]}")
    offen = offen.json()
    pruefe(len(offen) == 1, f"genau ein offener Satz: {len(offen)}")
    eintrag = offen[0]
    pruefe(eintrag["id"] == sid, "richtiger Satz")
    pruefe(eintrag["ordnername"] == "260819_Baustellenbegehung",
           f"Ordnername: {eintrag['ordnername']}")
    pruefe(eintrag["zielpfad"] == ZIEL, f"Zielpfad geliefert: {eintrag['zielpfad']}")
    pruefe(eintrag["projekt_name"] == "K30159 Kita Nord", "Projektname dabei")
    pruefe(eintrag["anzahl_fotos"] == 2, f"Fotoanzahl: {eintrag['anzahl_fotos']}")
    pruefe(eintrag["groesse_bytes"] > 0, "Groesse gefuellt")
    pruefe(eintrag["zip_dateiname"] ==
           "260819_K30159_Kita_Nord_Baustellenbegehung.zip",
           f"ZIP-Name: {eintrag['zip_dateiname']}")

    # Ein Satz ohne Fotos darf nicht in der Liste stehen — sonst legte das
    # Skript leere Ordner im Projektverzeichnis an.
    leer = c.post("/api/fotosaetze", json={
        "projekt_id": pid, "kategorie": "Noch nichts", "datum": "2026-08-20",
    }).json()
    offen2 = c.get("/api/fotosaetze/abholung/offen").json()
    pruefe(all(e["id"] != leer["id"] for e in offen2),
           "leerer Satz erscheint nicht")

    # ── Wettlauf zweier Buerorechner ──
    erster = c.post(f"/api/fotosaetze/{sid}/abholung/beanspruchen",
                    json={"rechner": "PC-BEN"})
    pruefe(erster.status_code == 200, f"erster Anspruch: {erster.status_code}")
    pruefe(erster.json()["abgeholt_von"] == "PC-BEN",
           f"Rechner vermerkt: {erster.json()}")

    zweiter = c.post(f"/api/fotosaetze/{sid}/abholung/beanspruchen",
                     json={"rechner": "PC-KOLLEGE"})
    pruefe(zweiter.status_code == 409, f"zweiter Anspruch abgewiesen: {zweiter.status_code}")
    pruefe("PC-BEN" in zweiter.text, f"Abfuhr nennt den Rechner: {zweiter.text[:200]}")

    # Beansprucht = nicht mehr in der offenen Liste.
    offen3 = c.get("/api/fotosaetze/abholung/offen").json()
    pruefe(all(e["id"] != sid for e in offen3), "beanspruchter Satz ist weg")

    # ── ZIP holen (die bestehende Route, das Skript braucht keine neue) ──
    zipdatei = c.get(f"/api/fotosaetze/{sid}/zip")
    pruefe(zipdatei.status_code == 200, f"ZIP: {zipdatei.status_code}")
    pruefe(zipdatei.content[:2] == b"PK", "ZIP-Kennung")

    # ── Quittieren ──
    voll = ZIEL + "\\260819_Baustellenbegehung"
    quittung = c.post(f"/api/fotosaetze/{sid}/abholung/quittieren",
                      json={"rechner": "PC-BEN", "ziel": voll})
    pruefe(quittung.status_code == 200, f"Quittung: {quittung.status_code}")
    pruefe(quittung.json()["abgeholt_ziel"] == voll,
           f"Ziel gespeichert: {quittung.json()['abgeholt_ziel']}")

    # Quittung ohne Ziel waere wertlos — dann weiss niemand, wo der Satz liegt.
    ohne_ziel = c.post(f"/api/fotosaetze/{sid}/abholung/quittieren",
                       json={"rechner": "PC-BEN", "ziel": "  "})
    pruefe(ohne_ziel.status_code == 400, f"Quittung ohne Ziel: {ohne_ziel.status_code}")

    # ── Nach der Quittung ist Schluss ──
    offen4 = c.get("/api/fotosaetze/abholung/offen").json()
    pruefe(all(e["id"] != sid for e in offen4), "quittierter Satz bleibt weg")

    nochmal = c.post(f"/api/fotosaetze/{sid}/abholung/beanspruchen",
                     json={"rechner": "PC-KOLLEGE"})
    pruefe(nochmal.status_code == 409, f"kein zweiter Anspruch: {nochmal.status_code}")
    pruefe("bereits abgeholt" in nochmal.text.lower() or "Bereits" in nochmal.text,
           f"Begruendung: {nochmal.text[:200]}")

    freigabe = c.post(f"/api/fotosaetze/{sid}/abholung/freigeben")
    pruefe(freigabe.status_code == 409,
           f"quittierter Satz nicht freigebbar: {freigabe.status_code}")

    # Der Fotosatz zeigt die Abholung auch in der normalen Ansicht.
    detail = c.get(f"/api/fotosaetze/{sid}").json()
    pruefe(detail["abgeholt_ziel"] == voll, "Detailansicht zeigt das Ziel")
    pruefe(detail["abgeholt_von"] == "PC-BEN", "Detailansicht zeigt den Rechner")
    liste = c.get("/api/fotosaetze").json()
    treffer = [e for e in liste if e["id"] == sid]
    pruefe(treffer and treffer[0]["abgeholt_ziel"] == voll,
           "Uebersichtsliste zeigt das Ziel")

    # ── Abgebrochene Abholung: Anspruch verfaellt ──
    satz2 = c.post("/api/fotosaetze", json={
        "projekt_id": pid, "kategorie": "Rohbau", "datum": "2026-08-21",
    }).json()
    c.post(f"/api/fotosaetze/{satz2['id']}/fotos", files=[
        ("dateien", ("A.jpg", bild((200, 120, 60)), "image/jpeg")),
    ])
    beansprucht = c.post(f"/api/fotosaetze/{satz2['id']}/abholung/beanspruchen",
                         json={"rechner": "PC-ABGESTUERZT"})
    pruefe(beansprucht.status_code == 200, "zweiter Satz beansprucht")

    # Anspruch kuenstlich altern lassen — als waere der Rechner abgestuerzt.
    with SessionLocal() as db:
        s = db.get(Fotosatz, satz2["id"])
        # Nach der Uhr der Datenbank altern lassen, nicht nach der des
        # Rechners — sonst laege der Wert je nach Zeitzone in der Zukunft.
        s.abgeholt_am = abholung.jetzt_laut_db(db) - timedelta(
            minutes=settings.abhol_anspruch_minuten + 5)
        db.commit()

    wieder = c.get("/api/fotosaetze/abholung/offen").json()
    pruefe(any(e["id"] == satz2["id"] for e in wieder),
           "verfallener Anspruch gibt den Satz frei")
    uebernahme = c.post(f"/api/fotosaetze/{satz2['id']}/abholung/beanspruchen",
                        json={"rechner": "PC-KOLLEGE"})
    pruefe(uebernahme.status_code == 200,
           f"anderer Rechner uebernimmt: {uebernahme.status_code}")
    pruefe(uebernahme.json()["abgeholt_von"] == "PC-KOLLEGE",
           "neuer Rechner eingetragen")

    # ── Freigabe nach Fehlschlag ──
    frei = c.post(f"/api/fotosaetze/{satz2['id']}/abholung/freigeben")
    pruefe(frei.status_code == 200, f"Freigabe: {frei.status_code}")
    danach = c.get("/api/fotosaetze/abholung/offen").json()
    pruefe(any(e["id"] == satz2["id"] for e in danach),
           "freigegebener Satz steht sofort wieder bereit")

    # ── Ruhezeit: frisch hochgeladen = noch nicht abholen ──
    settings.abhol_wartezeit_minuten = 10
    satz3 = c.post("/api/fotosaetze", json={
        "projekt_id": pid, "kategorie": "Fenster EG", "datum": "2026-08-22",
    }).json()
    c.post(f"/api/fotosaetze/{satz3['id']}/fotos", files=[
        ("dateien", ("B.jpg", bild((60, 60, 200)), "image/jpeg")),
    ])
    waehrend = c.get("/api/fotosaetze/abholung/offen").json()
    pruefe(all(e["id"] != satz3["id"] for e in waehrend),
           "frischer Upload wartet die Ruhezeit ab")
    settings.abhol_wartezeit_minuten = 0
    fertig = c.get("/api/fotosaetze/abholung/offen").json()
    pruefe(any(e["id"] == satz3["id"] for e in fertig),
           "nach der Ruhezeit abholbar")

    # ── Ordnernamen-Regel ──
    with SessionLocal() as db:
        s = db.get(Fotosatz, satz3["id"])
        pruefe(abholung.ordnername(s) == "260822_Fenster_EG",
               f"Ordnername mit Leerzeichen: {abholung.ordnername(s)}")
        s.kategorie = "Abnahme Dach/Attika"
        pruefe(abholung.ordnername(s) == "260822_Abnahme_DachAttika",
               f"Sonderzeichen entfernt: {abholung.ordnername(s)}")
        s.kategorie = "Grünanlage Süd"
        pruefe(abholung.ordnername(s) == "260822_Grünanlage_Süd",
               f"Umlaute bleiben: {abholung.ordnername(s)}")

    # ── Token-Schutz ──
    settings.abhol_token = "geheim"
    gesperrt = c.get("/api/fotosaetze/abholung/offen")
    pruefe(gesperrt.status_code == 401, f"ohne Token gesperrt: {gesperrt.status_code}")
    falsch = c.get("/api/fotosaetze/abholung/offen",
                   headers={"X-Abhol-Token": "falsch"})
    pruefe(falsch.status_code == 401, f"falscher Token: {falsch.status_code}")
    richtig = c.get("/api/fotosaetze/abholung/offen",
                    headers={"X-Abhol-Token": "geheim"})
    pruefe(richtig.status_code == 200, f"richtiger Token: {richtig.status_code}")
    # Die uebrige App bleibt unberuehrt.
    normal = c.get("/api/fotosaetze")
    pruefe(normal.status_code == 200, "Token sperrt nur die Abholrouten")
    settings.abhol_token = ""

print(f"{ok} Pruefungen ok")
if fehler:
    print("FEHLER:")
    for f in fehler:
        print(" -", f)
    sys.exit(1)
