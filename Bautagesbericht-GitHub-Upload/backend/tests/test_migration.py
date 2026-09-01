"""Prüft die Mini-Migration an einer KOPIE der echten Datenbank.

Die Spalten mail_versendet_am, mail_empfaenger und mail_weg kommen nachträglich
dazu. Auf dem Rechner des Kollegen liegt eine Datenbank ohne sie — genau dieser
Fall wird hier durchgespielt, damit niemand nach dem Update vor einem Fehler
steht.
"""
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.gettempdir()) / "hpp-test"
SCRATCH.mkdir(exist_ok=True)
ECHT = (Path(__file__).resolve().parent.parent.parent
        / "desktop/HPP-Baumanagement-App/daten/hpp-baumanagement.db")
KOPIE = SCRATCH / "migrationstest.db"

if not ECHT.is_file():
    print(f"Keine echte Datenbank unter {ECHT} — Test übersprungen.")
    raise SystemExit(0)

for rest in ("", "-wal", "-shm"):
    ziel = Path(str(KOPIE) + rest)
    if ziel.exists():
        ziel.unlink()

# WICHTIG: -wal und -shm mitkopieren. SQLite hält im WAL-Modus alles Neue in
# der Nebendatei; nur die .db zu kopieren ergibt eine (fast) leere Datenbank.
shutil.copy2(ECHT, KOPIE)
for rest in ("-wal", "-shm"):
    quelle = Path(str(ECHT) + rest)
    if quelle.is_file():
        shutil.copy2(quelle, Path(str(KOPIE) + rest))

# Zustand VOR der Migration festhalten.
with sqlite3.connect(KOPIE) as conn:
    vorher = {z[1] for z in conn.execute("PRAGMA table_info(fotosaetze)")}
    anzahl_saetze = conn.execute("SELECT count(*) FROM fotosaetze").fetchone()[0]
    anzahl_fotos = conn.execute("SELECT count(*) FROM baufotos").fetchone()[0]
    anzahl_projekte = conn.execute("SELECT count(*) FROM projekte").fetchone()[0]

print(f"Kopie der echten Datenbank: {anzahl_projekte} Projekt(e), "
      f"{anzahl_saetze} Fotosatz/Fotosätze, {anzahl_fotos} Foto(s)")
print(f"Spalten vorher: {sorted(vorher)}")

neu = {"mail_versendet_am", "mail_empfaenger", "mail_weg"}
schon_da = neu & vorher
if schon_da:
    print(f"Hinweis: {sorted(schon_da)} war(en) schon vorhanden.")

os.environ["BTB_DATABASE_URL"] = f"sqlite:///{KOPIE.as_posix()}"
os.environ["BTB_UPLOAD_DIR"] = str(SCRATCH / "migrationstest_uploads")
os.environ["BTB_OUTPUT_DIR"] = str(SCRATCH / "migrationstest_output")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

ok = 0
fehler = []


def pruefe(bedingung, text):
    global ok
    if bedingung:
        ok += 1
    else:
        fehler.append(text)


with TestClient(app) as c:
    with sqlite3.connect(KOPIE) as conn:
        nachher = {z[1] for z in conn.execute("PRAGMA table_info(fotosaetze)")}
        saetze_danach = conn.execute("SELECT count(*) FROM fotosaetze").fetchone()[0]
        fotos_danach = conn.execute("SELECT count(*) FROM baufotos").fetchone()[0]
        projekte_danach = conn.execute("SELECT count(*) FROM projekte").fetchone()[0]

    pruefe(neu <= nachher, f"Spalten fehlen nach der Migration: {sorted(neu - nachher)}")
    pruefe(vorher <= nachher, "Es darf keine Spalte verloren gehen")
    pruefe(saetze_danach == anzahl_saetze, "Fotosätze müssen erhalten bleiben")
    pruefe(fotos_danach == anzahl_fotos, "Fotos müssen erhalten bleiben")
    pruefe(projekte_danach == anzahl_projekte, "Projekte müssen erhalten bleiben")

    # Und die App muss die alten Daten auch ausliefern können.
    projekte = c.get("/api/projekte")
    pruefe(projekte.status_code == 200, f"projekte: {projekte.status_code}")
    pruefe(len(projekte.json()) == anzahl_projekte,
           f"projekte gelesen: {len(projekte.json())} statt {anzahl_projekte}")

    liste = c.get("/api/fotosaetze")
    pruefe(liste.status_code == 200, f"fotosaetze: {liste.status_code} {liste.text[:200]}")
    for eintrag in liste.json():
        pruefe(eintrag["mail_versendet_am"] is None,
               f"alter Satz muesste ohne Mailvermerk sein: {eintrag['id']}")
        pruefe(eintrag["mail_weg"] == "", f"mail_weg leer erwartet: {eintrag['mail_weg']!r}")

    maengel = c.get("/api/maengel")
    pruefe(maengel.status_code == 200, f"maengel: {maengel.status_code}")

print(f"\n{ok} Pruefungen ok, {len(fehler)} Fehler")
for f in fehler:
    print("  FEHLER:", f)
sys.exit(1 if fehler else 0)
