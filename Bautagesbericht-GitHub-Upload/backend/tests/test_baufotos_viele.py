"""Ein Fotosatz mit 35 Bildern — der Fall, an dem am 11.09.2026 15 Fotos verschwanden.

WORUM ES GEHT
=============
Auf der Baustelle wurden 35 Fotos ausgewaehlt, im Projektordner lagen 20. Die
Ursache sass in der Oberflaeche (``FotoAuswahl`` schnitt still auf 20 ab), aber
genau deshalb muss hier festgehalten werden, dass der Server diesen Fall
klaglos kann: Wer den Fehler spaeter sucht, soll ihn nicht zweimal im Backend
suchen muessen.

Nachgestellt wird der Weg der Oberflaeche exakt: erst den Fotosatz anlegen,
dann jedes Foto EINZELN senden (so uebersteht ein Verbindungsabbruch auf der
Baustelle hoechstens ein Bild). Geprueft wird, was am Ende beim Bueromenschen
ankommt — die Zahl am Satz, die laufenden Nummern und der Inhalt des Archivs.
"""
import io
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

# Eigene Ablage im Temp-Ordner — die echte storage/ bleibt unberuehrt.
STORAGE = Path(tempfile.gettempdir()) / "hpp-baufotos-viele"
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
from app.services import baufotos as dienst  # noqa: E402

#: So viele Fotos hatte der gemeldete Bautag.
ANZAHL = 35

ok = 0
fehler = []


def pruefe(bedingung, text):
    global ok
    if bedingung:
        ok += 1
    else:
        fehler.append(text)


def bild(nr: int) -> bytes:
    """Jedes Foto anders einfaerben — sonst faellt ein vertauschtes nicht auf."""
    puffer = io.BytesIO()
    farbe = (40 + (nr * 5) % 200, 90, 200 - (nr * 3) % 150)
    Image.new("RGB", (2400, 1800), farbe).save(puffer, format="JPEG", quality=90)
    return puffer.getvalue()


with TestClient(app) as c:
    projekt = c.post("/api/projekte", json={
        "name": "226093 AJH Arne-Jacobsen-Haus", "adresse": "",
    }).json()

    satz = c.post("/api/fotosaetze", json={
        "projekt_id": projekt["id"],
        "kategorie": "Rohbau",
        "datum": "2026-09-11",
        "notiz": "Begehung mit der Bauleitung",
    }).json()
    satz_id = satz["id"]

    # ── Einzeln senden, genau wie die Oberflaeche ──
    angenommen = 0
    for nr in range(ANZAHL):
        antwort = c.post(
            f"/api/fotosaetze/{satz_id}/fotos",
            files=[("dateien", (f"IMG_{nr:04d}.jpg", bild(nr), "image/jpeg"))],
        )
        if antwort.status_code == 201:
            angenommen += 1

    pruefe(angenommen == ANZAHL,
           f"Nur {angenommen} von {ANZAHL} Einzel-Uploads angenommen")

    # ── Was der Server ueber den Satz sagt ──
    voll = c.get(f"/api/fotosaetze/{satz_id}").json()
    pruefe(voll["anzahl_fotos"] == ANZAHL,
           f"anzahl_fotos ist {voll['anzahl_fotos']}, erwartet {ANZAHL}")
    pruefe(len(voll["fotos"]) == ANZAHL,
           f"{len(voll['fotos'])} Fotos am Satz, erwartet {ANZAHL}")

    # Laufende Nummern luecken- und doppelungsfrei 1..35: Sie stehen im
    # Dateinamen und damit spaeter im Projektordner.
    nummern = sorted(f["reihenfolge"] for f in voll["fotos"])
    pruefe(nummern == list(range(1, ANZAHL + 1)),
           f"Reihenfolge ist {nummern[:5]}…{nummern[-3:]}, erwartet 1..{ANZAHL}")

    namen = {f["dateiname"] for f in voll["fotos"]}
    pruefe(len(namen) == ANZAHL, f"Nur {len(namen)} verschiedene Dateinamen")
    pruefe(f"260911_Rohbau_{ANZAHL}.jpg" in namen,
           f"260911_Rohbau_{ANZAHL}.jpg fehlt — das letzte Foto kam nicht an")

    # ── Und was wirklich im Projektordner landet: das Archiv ──
    zip_antwort = c.get(f"/api/fotosaetze/{satz_id}/zip")
    pruefe(zip_antwort.status_code == 200,
           f"ZIP-Abruf endete mit {zip_antwort.status_code}")
    with zipfile.ZipFile(io.BytesIO(zip_antwort.content)) as archiv:
        eintraege = archiv.namelist()
    pruefe("FEHLT.txt" not in eintraege,
           "Das Archiv meldet fehlende Fotos (FEHLT.txt)")
    pruefe(len(eintraege) == ANZAHL,
           f"Im ZIP liegen {len(eintraege)} Dateien, erwartet {ANZAHL}")

    # ── Die Buendelgrenze bleibt eine LAUTE Grenze ──
    # Ein Buendel oberhalb des Erlaubten muss einen Fehler geben und darf
    # niemals stillschweigend die ersten n nehmen. Genau diese Stille war der
    # gemeldete Fehler, nur eine Ebene hoeher.
    zuviel = c.post(
        f"/api/fotosaetze/{satz_id}/fotos",
        files=[("dateien", (f"X_{i}.jpg", bild(i), "image/jpeg"))
               for i in range(dienst.MAX_FOTOS_PRO_UPLOAD + 1)],
    )
    pruefe(zuviel.status_code == 400,
           f"Uebergrosses Buendel gab {zuviel.status_code} statt 400")

    danach = c.get(f"/api/fotosaetze/{satz_id}").json()
    pruefe(danach["anzahl_fotos"] == ANZAHL,
           f"Nach dem abgelehnten Buendel sind es {danach['anzahl_fotos']} "
           f"Fotos — es wurde teilweise angenommen")

shutil.rmtree(STORAGE, ignore_errors=True)

print(f"{ok} Pruefungen bestanden.")
if fehler:
    print(f"\n{len(fehler)} FEHLER:")
    for text in fehler:
        print(f"  - {text}")
    sys.exit(1)
print("Ein Fotosatz mit 35 Bildern kommt vollstaendig durch.")
