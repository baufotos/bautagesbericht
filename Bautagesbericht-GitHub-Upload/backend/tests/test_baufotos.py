"""Rauchtest der Baufotos-API gegen eine frische SQLite-Datenbank."""
import io
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

# Eigene Ablage im Temp-Ordner — die echte storage/ bleibt unberuehrt.
STORAGE = Path(tempfile.gettempdir()) / "hpp-baufotostest"
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

ok = 0
fehler = []


def pruefe(bedingung, text):
    global ok
    if bedingung:
        ok += 1
    else:
        fehler.append(text)


def bild(groesse=(2400, 1800), farbe=(180, 120, 90)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", groesse, farbe).save(puffer, format="JPEG", quality=95)
    return puffer.getvalue()


with TestClient(app) as c:
    projekt = c.post("/api/projekte", json={
        "name": "2451 Neubau Verwaltungsgebäude Süd", "adresse": "",
    }).json()
    pid = projekt["id"]

    # ── Fotosatz anlegen ──
    satz = c.post("/api/fotosaetze", json={
        "projekt_id": pid, "kategorie": "Rohbau EG",
        "datum": "2026-08-19", "notiz": "Achse C",
    })
    pruefe(satz.status_code == 201, f"anlegen: {satz.status_code} {satz.text[:300]}")
    satz = satz.json()
    pruefe(satz["zip_dateiname"] ==
           "260819_2451_Neubau_Verwaltungsgebäude_Süd_Rohbau_EG.zip",
           f"ZIP-Name: {satz['zip_dateiname']}")
    pruefe(satz["anzahl_fotos"] == 0, f"leer: {satz['anzahl_fotos']}")

    # Leere Kategorie muss abgelehnt werden
    leer = c.post("/api/fotosaetze", json={"projekt_id": pid, "kategorie": "  "})
    pruefe(leer.status_code == 400, f"leere Kategorie: {leer.status_code}")

    # ── Fotos hochladen (eines im Hochformat) ──
    up = c.post(f"/api/fotosaetze/{satz['id']}/fotos", files=[
        ("dateien", ("IMG_9001.JPG", bild(), "image/jpeg")),
        ("dateien", ("IMG_9002.JPG", bild((1800, 2400), (90, 120, 180)), "image/jpeg")),
    ])
    pruefe(up.status_code == 201, f"upload: {up.status_code} {up.text[:300]}")
    fotos = up.json()
    pruefe([f["dateiname"] for f in fotos] ==
           ["260819_Rohbau_EG_1.jpg", "260819_Rohbau_EG_2.jpg"],
           f"Namen: {[f['dateiname'] for f in fotos]}")
    pruefe(fotos[0]["original_dateiname"] == "IMG_9001.JPG", "Originalname fehlt")
    pruefe(all(0 < f["groesse_bytes"] < 900_000 for f in fotos),
           f"Groessen: {[f['groesse_bytes'] for f in fotos]}")

    # Zweiter Upload zaehlt weiter
    up2 = c.post(f"/api/fotosaetze/{satz['id']}/fotos", files=[
        ("dateien", ("IMG_9003.JPG", bild((1200, 900), (120, 160, 110)), "image/jpeg")),
    ])
    pruefe(up2.json()[0]["dateiname"] == "260819_Rohbau_EG_3.jpg",
           f"Fortzaehlung: {up2.json()[0]['dateiname']}")

    # Keine Bilddatei
    kein_bild = c.post(f"/api/fotosaetze/{satz['id']}/fotos", files=[
        ("dateien", ("notiz.txt", b"kein bild", "text/plain")),
    ])
    pruefe(kein_bild.status_code == 400, f"Nicht-Bild: {kein_bild.status_code}")

    # ── Verkleinerung wirklich passiert? ──
    bild_ant = c.get(f"/api/fotosaetze/fotos/{fotos[0]['id']}/bild")
    pruefe(bild_ant.status_code == 200, f"bild: {bild_ant.status_code}")
    with Image.open(io.BytesIO(bild_ant.content)) as im:
        pruefe(max(im.size) == 1600, f"max Kante: {im.size}")
    thumb = c.get(f"/api/fotosaetze/fotos/{fotos[0]['id']}/bild?thumb=true")
    pruefe(0 < len(thumb.content) < len(bild_ant.content),
           f"thumb {len(thumb.content)} vs {len(bild_ant.content)}")

    # ── Hochformat blieb hochformat (EXIF/Seitenverhaeltnis) ──
    hoch = c.get(f"/api/fotosaetze/fotos/{fotos[1]['id']}/bild")
    with Image.open(io.BytesIO(hoch.content)) as im:
        pruefe(im.size[1] > im.size[0], f"Hochformat: {im.size}")

    # ── ZIP ──
    zip_ant = c.get(f"/api/fotosaetze/{satz['id']}/zip")
    pruefe(zip_ant.status_code == 200, f"zip: {zip_ant.status_code} {zip_ant.text[:200]}")
    pruefe(zip_ant.headers["content-type"] == "application/zip",
           zip_ant.headers.get("content-type", ""))
    cd = zip_ant.headers.get("content-disposition", "")
    pruefe("filename*=UTF-8''" in cd and "260819" in cd, f"Content-Disposition: {cd}")
    with zipfile.ZipFile(io.BytesIO(zip_ant.content)) as z:
        namen = z.namelist()
    pruefe(namen == ["260819_Rohbau_EG_1.jpg", "260819_Rohbau_EG_2.jpg",
                     "260819_Rohbau_EG_3.jpg"], f"ZIP-Inhalt: {namen}")

    # ── Kategorien-Endpunkt (feststehender Pfad vor /{id}) ──
    kat = c.get(f"/api/fotosaetze/kategorien?projekt_id={pid}")
    pruefe(kat.status_code == 200 and kat.json() == ["Rohbau EG"],
           f"kategorien: {kat.status_code} {kat.text[:200]}")

    # ── Liste ──
    liste = c.get(f"/api/fotosaetze?projekt_id={pid}").json()
    pruefe(len(liste) == 1 and liste[0]["anzahl_fotos"] == 3,
           f"liste: {liste}")
    pruefe(liste[0]["titel_foto_id"] == fotos[0]["id"],
           f"Titelfoto: {liste[0]['titel_foto_id']} vs {fotos[0]['id']}")
    pruefe(liste[0]["groesse_bytes"] > 0, "Groesse fehlt")
    suche = c.get(f"/api/fotosaetze?projekt_id={pid}&suche=achse").json()
    pruefe(len(suche) == 1, f"suche: {len(suche)}")
    andere = c.get(f"/api/fotosaetze?projekt_id={pid}&kategorie=Dach").json()
    pruefe(andere == [], f"kategorie-filter: {andere}")

    # ── Aendern benennt NICHT um (bewusst) ──
    geaendert = c.patch(f"/api/fotosaetze/{satz['id']}",
                        json={"notiz": "Achse C und D"}).json()
    pruefe(geaendert["notiz"] == "Achse C und D", f"notiz: {geaendert['notiz']}")
    pruefe(geaendert["fotos"][0]["dateiname"] == "260819_Rohbau_EG_1.jpg",
           "Fotos duerfen beim Aendern nicht umbenannt werden")

    # ── Melden ohne Webhook ──
    melden = c.post(f"/api/fotosaetze/{satz['id']}/melden").json()
    pruefe(melden["gemeldet"] is False and melden["kanal"] == "keiner",
           f"melden: {melden}")

    # ── Foto loeschen: Nummern der anderen bleiben ──
    pruefe(c.delete(f"/api/fotosaetze/fotos/{fotos[0]['id']}").status_code == 204,
           "foto loeschen")
    nach = c.get(f"/api/fotosaetze/{satz['id']}").json()
    pruefe([f["dateiname"] for f in nach["fotos"]] ==
           ["260819_Rohbau_EG_2.jpg", "260819_Rohbau_EG_3.jpg"],
           f"nach Loeschen: {[f['dateiname'] for f in nach['fotos']]}")
    weiter = c.post(f"/api/fotosaetze/{satz['id']}/fotos", files=[
        ("dateien", ("IMG_9004.JPG", bild((800, 600)), "image/jpeg")),
    ]).json()
    pruefe(weiter[0]["dateiname"] == "260819_Rohbau_EG_4.jpg",
           f"keine doppelte Nummer: {weiter[0]['dateiname']}")

    # ── Dateien liegen wirklich auf der Platte ──
    ordner = STORAGE / "uploads" / "baufotos" / str(satz["id"])
    pruefe(ordner.is_dir() and len(list(ordner.glob("*.jpg"))) >= 3,
           f"Ordner: {list(ordner.glob('*')) if ordner.exists() else 'fehlt'}")

    # ── Zweiter Fotosatz, andere Kategorie ──
    satz2 = c.post("/api/fotosaetze", json={
        "projekt_id": pid, "kategorie": "Dach", "datum": "2026-08-20",
    }).json()
    c.post(f"/api/fotosaetze/{satz2['id']}/fotos", files=[
        ("dateien", ("a.jpg", bild((600, 400)), "image/jpeg")),
    ])
    kat2 = c.get(f"/api/fotosaetze/kategorien?projekt_id={pid}").json()
    pruefe(kat2 == ["Dach", "Rohbau EG"], f"kategorien2: {kat2}")
    liste2 = c.get(f"/api/fotosaetze?projekt_id={pid}").json()
    pruefe([s["kategorie"] for s in liste2] == ["Dach", "Rohbau EG"],
           f"Sortierung neueste zuerst: {[s['kategorie'] for s in liste2]}")

    # ── Fotosatz loeschen raeumt Dateien auf ──
    pruefe(c.delete(f"/api/fotosaetze/{satz2['id']}").status_code == 204,
           "fotosatz loeschen")
    pruefe(not (STORAGE / "uploads" / "baufotos" / str(satz2["id"])).exists(),
           "Ordner des geloeschten Satzes muesste weg sein")

    # ── Projekt loeschen: 409, dann force ──
    konflikt = c.delete(f"/api/projekte/{pid}")
    pruefe(konflikt.status_code == 409, f"projekt konflikt: {konflikt.status_code}")
    pruefe(konflikt.json()["detail"]["anzahl_fotosaetze"] == 1,
           konflikt.text[:300])
    pruefe(c.delete(f"/api/projekte/{pid}?force=true").status_code == 204,
           "projekt force loeschen")
    pruefe(c.get(f"/api/fotosaetze?projekt_id={pid}").json() == [],
           "Fotosaetze noch da")
    pruefe(not (STORAGE / "uploads" / "baufotos" / str(satz["id"])).exists(),
           "Ordner nach Projektloeschung muesste weg sein")

print(f"\n{ok} Pruefungen ok, {len(fehler)} Fehler")
for f in fehler:
    print("  FEHLER:", f)
sys.exit(1 if fehler else 0)
