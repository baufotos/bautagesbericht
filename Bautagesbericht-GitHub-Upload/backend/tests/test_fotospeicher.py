"""Fotos in der Datenbank — die Rückwand, die auf Render gilt.

Warum das eine eigene Testreihe hat: Auf Render ist das Dateisystem flüchtig,
und ein Fotosatz, der zwischen Upload und Abholung verschwindet, ist genau der
Fehler, den niemand bemerkt, bis jemand im Projektordner nachsieht. Geprüft
wird deshalb der ganze Weg — hochladen, ansehen, zippen, abholen, aufräumen —
mit ``BTB_FOTOSPEICHER=db``.
"""
import io
import os
import random
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STORAGE = Path(tempfile.gettempdir()) / "hpp-fotospeichertest"
if STORAGE.exists():
    shutil.rmtree(STORAGE)
STORAGE.mkdir(parents=True)

WIN = str(STORAGE).replace("\\", "/")
os.environ["BTB_DATABASE_URL"] = f"sqlite:///{WIN}/test.db"
os.environ["BTB_UPLOAD_DIR"] = f"{WIN}/uploads"
os.environ["BTB_OUTPUT_DIR"] = f"{WIN}/output"
os.environ["BTB_FOTOSPEICHER"] = "db"
os.environ["BTB_ABHOL_WARTEZEIT_MINUTEN"] = "0"

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Baufoto, Fotoblob, Fotosatz  # noqa: E402
from app.services import abholung, fotospeicher  # noqa: E402

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


def bild(farbe=(150, 110, 70), groesse=(1800, 1350)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", groesse, farbe).save(puffer, format="JPEG", quality=92)
    return puffer.getvalue()


def rausch_bild(saat: int, groesse=(1600, 1600)) -> bytes:
    """Ein Bild, das sich nicht wegkomprimieren lässt (rund 1 MB).

    Für die Platzgrenze gebraucht: Ein einfarbiges Bild schrumpft auf wenige
    Kilobyte, damit ließe sich kein Volllaufen nachstellen. Echte
    Baustellenfotos liegen größenmäßig in dieser Gegend.
    """
    zufall = random.Random(saat)
    rohdaten = bytes(zufall.getrandbits(8) for _ in range(groesse[0] * groesse[1] * 3))
    puffer = io.BytesIO()
    Image.frombytes("RGB", groesse, rohdaten).save(
        puffer, format="JPEG", quality=95)
    return puffer.getvalue()


ZIEL = r"L:\Bauleitung-Hamburg\K30159 Kita Nord\01 FOTOS"

with TestClient(app) as c:
    abschnitt("Rückwand erkannt")
    pruefe(fotospeicher.art() == "db", f"Rückwand: {fotospeicher.art()}")
    pruefe("Datenbank" in fotospeicher.beschreibung(),
           f"Beschreibung: {fotospeicher.beschreibung()}")

    projekt = c.post("/api/projekte", json={
        "name": "K30159 Kita Nord", "adresse": "", "foto_zielpfad": ZIEL,
    }).json()
    satz = c.post("/api/fotosaetze", json={
        "projekt_id": projekt["id"], "kategorie": "Baustellenbegehung",
        "datum": "2026-08-19",
    }).json()
    sid = satz["id"]

    abschnitt("Hochladen landet in der Datenbank, nicht auf der Platte")
    hoch = c.post(f"/api/fotosaetze/{sid}/fotos", files=[
        ("dateien", ("IMG_1.jpg", bild(), "image/jpeg")),
        ("dateien", ("IMG_2.heic", bild((80, 130, 90)), "image/heic")),
        ("dateien", ("IMG_3.png", bild((60, 80, 170)), "image/png")),
    ])
    pruefe(hoch.status_code == 201, f"Upload: {hoch.status_code} {hoch.text[:200]}")
    fotos = hoch.json()
    pruefe(len(fotos) == 3, f"drei Fotos: {len(fotos)}")
    # Egal womit fotografiert wurde — im Projektordner liegt immer JPEG.
    pruefe(all(f["dateiname"].endswith(".jpg") for f in fotos),
           f"alles JPEG: {[f['dateiname'] for f in fotos]}")

    with SessionLocal() as db:
        eintraege = db.query(Baufoto).filter(Baufoto.fotosatz_id == sid).all()
        pruefe(all(v.dateipfad.startswith("db:") for v in eintraege),
               f"Verweise: {[v.dateipfad for v in eintraege]}")
        blobs = db.query(Fotoblob).all()
        pruefe(len(blobs) == 3, f"drei Blobs: {len(blobs)}")
        pruefe(all(b.groesse_bytes > 0 for b in blobs), "Größen gefüllt")
        pruefe(all(bytes(b.daten)[:2] == b"\xff\xd8" for b in blobs),
               "Blobs sind JPEG-Daten")
        # Der Schlüssel sieht aus wie der Pfad, den die Dateiablage benutzt
        # hätte — dadurch bleiben Verweise in beiden Fällen gleich lesbar.
        pruefe(all(b.schluessel.startswith(f"baufotos/{sid}/") for b in blobs),
               f"Schlüssel: {[b.schluessel for b in blobs]}")

    # Auf der Platte darf nichts liegen.
    hochgeladen = list((STORAGE / "uploads").rglob("*.jpg")) if (STORAGE / "uploads").exists() else []
    pruefe(not hochgeladen, f"keine Dateien auf der Platte: {hochgeladen}")

    abschnitt("Anzeigen")
    voll = c.get(f"/api/fotosaetze/fotos/{fotos[0]['id']}/bild")
    pruefe(voll.status_code == 200, f"Vollbild: {voll.status_code}")
    pruefe(voll.content[:2] == b"\xff\xd8", "Vollbild ist JPEG")
    pruefe(voll.headers.get("content-type") == "image/jpeg",
           f"Content-Type: {voll.headers.get('content-type')}")

    klein = c.get(f"/api/fotosaetze/fotos/{fotos[0]['id']}/bild?thumb=true")
    pruefe(klein.status_code == 200, f"Vorschau: {klein.status_code}")
    pruefe(len(klein.content) < len(voll.content),
           f"Vorschau kleiner: {len(klein.content)} vs {len(voll.content)}")

    abschnitt("ZIP wird aus der Datenbank gebaut")
    archiv = c.get(f"/api/fotosaetze/{sid}/zip")
    pruefe(archiv.status_code == 200, f"ZIP: {archiv.status_code}")
    with zipfile.ZipFile(io.BytesIO(archiv.content)) as z:
        namen = z.namelist()
        pruefe(len(namen) == 3, f"drei Dateien im ZIP: {namen}")
        pruefe("FEHLT.txt" not in namen, "nichts fehlt")
        pruefe(z.read(namen[0])[:2] == b"\xff\xd8", "Inhalt ist JPEG")

    abschnitt("Einzelnes Foto löschen räumt auch die Daten weg")
    weg = c.delete(f"/api/fotosaetze/fotos/{fotos[2]['id']}")
    pruefe(weg.status_code == 204, f"Löschen: {weg.status_code}")
    with SessionLocal() as db:
        pruefe(db.query(Fotoblob).count() == 2,
               f"Blob mitgelöscht: {db.query(Fotoblob).count()}")

    abschnitt("Abholen")
    offen = c.get("/api/fotosaetze/abholung/offen").json()
    pruefe(any(e["id"] == sid for e in offen), "Satz steht bereit")
    c.post(f"/api/fotosaetze/{sid}/abholung/beanspruchen", json={"rechner": "PC-BEN"})
    quittung = c.post(f"/api/fotosaetze/{sid}/abholung/quittieren", json={
        "rechner": "PC-BEN", "ziel": ZIEL + r"\260819_Baustellenbegehung",
    })
    pruefe(quittung.status_code == 200, f"Quittung: {quittung.status_code}")

    abschnitt("Schonfrist: direkt nach der Abholung bleiben die Bilder")
    with SessionLocal() as db:
        anzahl, bytes_frei = fotospeicher.raeume_auf(db)
        pruefe(anzahl == 0, f"nichts geleert: {anzahl}")
        pruefe(db.query(Fotoblob).count() == 2, "Bilder noch da")
    noch_da = c.get(f"/api/fotosaetze/fotos/{fotos[0]['id']}/bild")
    pruefe(noch_da.status_code == 200, "Galerie zeigt weiter Bilder")

    abschnitt("Nach der Schonfrist wird der Platz freigegeben")
    with SessionLocal() as db:
        s = db.get(Fotosatz, sid)
        s.abgeholt_am = abholung.jetzt_laut_db(db) - timedelta(
            days=settings.fotos_aufbewahren_tage + 1)
        db.commit()
        anzahl, bytes_frei = fotospeicher.raeume_auf(db)
        pruefe(anzahl == 2, f"zwei Blobs geleert: {anzahl}")
        pruefe(bytes_frei > 0, f"Bytes gemeldet: {bytes_frei}")
        pruefe(db.query(Fotoblob).count() == 0, "Datenbank ist leer")
        # Der Datensatz bleibt: Name, Größe und Zielordner sollen weiter
        # ablesbar sein, auch wenn die Bilder fort sind.
        pruefe(db.query(Baufoto).filter(Baufoto.fotosatz_id == sid).count() == 2,
               "Fotodatensätze bleiben")

    verschwunden = c.get(f"/api/fotosaetze/fotos/{fotos[0]['id']}/bild")
    pruefe(verschwunden.status_code == 404, f"Bild fort: {verschwunden.status_code}")
    pruefe("Projektordner" in verschwunden.text,
           f"Meldung nennt den Grund: {verschwunden.text[:200]}")

    detail = c.get(f"/api/fotosaetze/{sid}").json()
    pruefe(detail["anzahl_fotos"] == 2, "Satz zeigt weiter zwei Fotos")
    pruefe(detail["abgeholt_ziel"].endswith("260819_Baustellenbegehung"),
           "Zielordner weiter ablesbar")

    abschnitt("Ein nicht abgeholter Satz wird niemals geleert")
    satz2 = c.post("/api/fotosaetze", json={
        "projekt_id": projekt["id"], "kategorie": "Rohbau", "datum": "2026-08-20",
    }).json()
    c.post(f"/api/fotosaetze/{satz2['id']}/fotos", files=[
        ("dateien", ("A1.jpg", rausch_bild(1), "image/jpeg")),
        ("dateien", ("A2.jpg", rausch_bild(2), "image/jpeg")),
    ])
    with SessionLocal() as db:
        belegt = fotospeicher.belegung_bytes(db)
        pruefe(belegt > 1024 * 1024, f"Belegung über 1 MB: {belegt}")
        # Satz künstlich altern lassen UND die Platzgrenze unter die Belegung
        # drücken — selbst dann darf nichts verschwinden, was nicht quittiert
        # ist. Das ist die eiserne Regel des Aufräumens.
        s = db.get(Fotosatz, satz2["id"])
        s.erstellt_am = abholung.jetzt_laut_db(db) - timedelta(days=90)
        db.commit()
        settings.fotos_max_mb = 1
        anzahl, _ = fotospeicher.raeume_auf(db)
        settings.fotos_max_mb = 300
        pruefe(anzahl == 0, f"nichts geleert: {anzahl}")
        pruefe(db.query(Fotoblob).count() == 2, "Bilder des offenen Satzes liegen noch")
    foto_id = c.get(f"/api/fotosaetze/{satz2['id']}").json()["fotos"][0]["id"]
    bereit = c.get(f"/api/fotosaetze/fotos/{foto_id}/bild")
    pruefe(bereit.status_code == 200, f"Bild abrufbar: {bereit.status_code}")

    abschnitt("Platzgrenze greift nur bei abgeholten Sätzen")
    satz3 = c.post("/api/fotosaetze", json={
        "projekt_id": projekt["id"], "kategorie": "Fenster EG", "datum": "2026-08-21",
    }).json()
    c.post(f"/api/fotosaetze/{satz3['id']}/fotos", files=[
        ("dateien", ("B1.jpg", rausch_bild(3), "image/jpeg")),
        ("dateien", ("B2.jpg", rausch_bild(4), "image/jpeg")),
    ])
    c.post(f"/api/fotosaetze/{satz3['id']}/abholung/beanspruchen",
           json={"rechner": "PC-BEN"})
    c.post(f"/api/fotosaetze/{satz3['id']}/abholung/quittieren",
           json={"rechner": "PC-BEN", "ziel": ZIEL + r"\260821_Fenster_EG"})

    with SessionLocal() as db:
        vorher = fotospeicher.belegung_bytes(db)
        pruefe(vorher > 2 * 1024 * 1024, f"Belegung gemessen: {vorher}")
        settings.fotos_max_mb = 1          # Grenze unter die Belegung drücken
        anzahl, bytes_frei = fotospeicher.raeume_auf(db)
        settings.fotos_max_mb = 300
        pruefe(anzahl == 2, f"abgeholter Satz geleert: {anzahl}")
        pruefe(bytes_frei > 0, f"Bytes gemeldet: {bytes_frei}")
        # Der offene Satz aus dem Abschnitt davor muss unberührt bleiben —
        # auch wenn danach noch immer zu wenig Platz ist.
        offene_blobs = db.query(Fotoblob).count()
        pruefe(offene_blobs == 2,
               f"nur der offene Satz ist übrig: {offene_blobs}")

    abschnitt("Löschen eines Satzes nimmt die Bilddaten mit")
    c.delete(f"/api/fotosaetze/{satz2['id']}")
    with SessionLocal() as db:
        pruefe(db.query(Fotoblob).count() == 0,
               f"keine Reste: {db.query(Fotoblob).count()}")

    abschnitt("Dateiablage bleibt unangetastet nutzbar")
    settings.fotospeicher = "datei"
    fotospeicher._client = None
    pruefe(fotospeicher.art() == "datei", f"Umschalten: {fotospeicher.art()}")
    satz4 = c.post("/api/fotosaetze", json={
        "projekt_id": projekt["id"], "kategorie": "Dach", "datum": "2026-08-22",
    }).json()
    auf_platte = c.post(f"/api/fotosaetze/{satz4['id']}/fotos", files=[
        ("dateien", ("C.jpg", bild((110, 110, 40)), "image/jpeg")),
    ])
    pruefe(auf_platte.status_code == 201, f"Upload: {auf_platte.status_code}")
    with SessionLocal() as db:
        v = db.query(Baufoto).filter(Baufoto.fotosatz_id == satz4["id"]).first()
        pruefe(not v.dateipfad.startswith("db:"), f"Pfad: {v.dateipfad}")
        pruefe(fotospeicher.ist_datei(v.dateipfad), "als Datei erkannt")
        pruefe(db.query(Fotoblob).count() == 0, "kein Blob angelegt")
    platte_bild = c.get(f"/api/fotosaetze/fotos/{auf_platte.json()[0]['id']}/bild")
    pruefe(platte_bild.status_code == 200, f"Datei-Bild: {platte_bild.status_code}")
    # Aufräumen tut in der Dateiablage nichts — dort ist die Platte dauerhaft.
    with SessionLocal() as db:
        pruefe(fotospeicher.raeume_auf(db) == (0, 0), "Aufräumen greift nicht")
        pruefe(fotospeicher.belegung_bytes(db) == 0, "keine Belegung gemeldet")
    settings.fotospeicher = "db"

print()
print(f"{ok} Pruefungen ok, {len(fehler)} Fehler")
if fehler:
    print("FEHLER:")
    for f in fehler:
        print(" -", f)
    sys.exit(1)
