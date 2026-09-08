"""Passwortschutz der Weboberfläche — wer darf, und wer ausdrücklich nicht.

Warum das eine eigene Testreihe hat: Dieselbe App läuft an zwei Orten mit
gegensätzlichen Erwartungen. Auf dem Bürorechner hört sie nur auf localhost
und soll ohne Anmeldung erreichbar sein; im Netz ist dasselbe leere Passwort
ein offenes Tor. Beide Fälle hängen an einem einzigen ``if`` in
``app.security`` — und der ist genau die Stelle, an der ein Versehen niemandem
auffällt, weil die Seite dann ja *funktioniert*.

Anlass für Abschnitt 2 war ein echter Vorfall am 08.09.2026: Der
Blueprint-Abgleich bei Render legte einen zweiten Dienst an und ließ dabei
alle Felder mit ``sync: false`` leer. Der Dienst startete mit leerer
Ersatzdatenbank und ohne Passwort und war für jeden mit der Adresse offen —
inklusive Hochladen. Seitdem verweigert er in diesem Zustand die Arbeit.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ARBEIT = Path(tempfile.gettempdir()) / "hpp-seitenschutztest"
ARBEIT.mkdir(parents=True, exist_ok=True)
WIN = str(ARBEIT).replace("\\", "/")
os.environ["BTB_DATABASE_URL"] = f"sqlite:///{WIN}/test.db"
os.environ["BTB_UPLOAD_DIR"] = f"{WIN}/uploads"
os.environ["BTB_OUTPUT_DIR"] = f"{WIN}/output"
os.environ.pop("RENDER", None)

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app import security  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

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


init_db()

PASSWORT = "Losung-fuer-den-Test"
GESCHUETZT = "/api/projekte"


def frisch():
    """Neuer Client ohne Cookies aus dem vorigen Abschnitt."""
    return TestClient(app)


def im_netz(ja):
    if ja:
        os.environ["RENDER"] = "true"
    else:
        os.environ.pop("RENDER", None)


print("1. Buerorechner ohne Passwort: offen wie bisher")
settings.seiten_passwort = ""
im_netz(False)
c = frisch()
gleich(c.get("/api/health").status_code, 200, "Health erreichbar")
gleich(c.get(GESCHUETZT).status_code, 200, "Projekte ohne Anmeldung erreichbar")

print("2. Im Netz ohne Passwort: verweigert die Arbeit statt offen zu stehen")
settings.seiten_passwort = ""
im_netz(True)
c = frisch()
gleich(c.get("/api/health").status_code, 200,
       "Health bleibt erreichbar (Render braucht es)")
gleich(c.get("/api/health/dokumente").status_code, 200,
       "Selbstauskunft bleibt erreichbar")
antwort = c.get(GESCHUETZT)
gleich(antwort.status_code, 503, "Projekte gesperrt")
text = antwort.json().get("detail", "")
pruefe("BTB_SEITEN_PASSWORT" in text, f"nennt die Variable: {text}")
pruefe("Render" in text, f"sagt wo sie hingehoert: {text}")
gleich(c.post(GESCHUETZT, json={"name": "Einschmuggeln"}).status_code, 503,
       "Anlegen ebenfalls gesperrt")

print("3. Mit Passwort: ohne Nachweis kein Zutritt")
settings.seiten_passwort = PASSWORT
im_netz(True)
c = frisch()
gleich(c.get("/api/health").status_code, 200, "Health weiterhin offen")
gleich(c.get(GESCHUETZT).status_code, 401, "ohne Nachweis 401")
gleich(c.get(GESCHUETZT, headers={"X-Seiten-Passwort": "falsch"}).status_code,
       401, "falsches Passwort 401")

print("4. Mit Passwort: die zwei erlaubten Wege")
c = frisch()
gleich(c.get(GESCHUETZT, headers={"X-Seiten-Passwort": PASSWORT}).status_code,
       200, "Weg 1: Kopfzeile")

c = frisch()
c.cookies.set(security.COOKIE_NAME, security._fingerabdruck(PASSWORT))
gleich(c.get(GESCHUETZT).status_code, 200, "Weg 2: Cookie")

# Der Cookie-Weg ist kein Komfort, sondern Voraussetzung: Bilder und
# Downloads laedt der Browser selbst, und dabei kann JavaScript keine
# Kopfzeile setzen.
c = frisch()
c.cookies.set(security.COOKIE_NAME, security._fingerabdruck("anderes Wort"))
gleich(c.get(GESCHUETZT).status_code, 401, "Cookie vom falschen Passwort 401")

print("5. Passwortwechsel entwertet alte Cookies")
c = frisch()
c.cookies.set(security.COOKIE_NAME, security._fingerabdruck(PASSWORT))
settings.seiten_passwort = "Neues-Losungswort"
gleich(c.get(GESCHUETZT).status_code, 401, "altes Cookie gilt nicht mehr")
settings.seiten_passwort = PASSWORT

print("6. Abholweg der Buerorechner")
zip_pfad = "/api/fotosaetze/1/zip"
settings.abhol_token = "ABHOL-TEST"
c = frisch()
pruefe(c.get(zip_pfad).status_code == 401,
       "ZIP ohne alles bleibt gesperrt (Nummern sind ratbar)")
antwort = c.get(zip_pfad, headers={"X-Abhol-Token": "ABHOL-TEST"})
pruefe(antwort.status_code != 401,
       f"ZIP mit Losungswort kommt am Schutz vorbei ({antwort.status_code})")
gleich(c.get(zip_pfad, headers={"X-Abhol-Token": "falsch"}).status_code, 401,
       "falsches Losungswort 401")

# Ohne hinterlegtes Losungswort gibt es keinen Nachweis — und damit auch
# keine Ausnahme. Sonst stuende der ZIP-Download offen.
settings.abhol_token = ""
c = frisch()
gleich(c.get(zip_pfad, headers={"X-Abhol-Token": "irgendwas"}).status_code, 401,
       "ohne hinterlegtes Losungswort keine Ausnahme")

print("7. Aufraeumen: Zustand wie vorgefunden")
settings.seiten_passwort = ""
settings.abhol_token = ""
im_netz(False)
c = frisch()
gleich(c.get(GESCHUETZT).status_code, 200, "wieder offen wie auf dem PC")

print()
print(f"{ok} Pruefungen ok, {len(fehler)} Fehler")
if fehler:
    print("FEHLER:")
    for f in fehler:
        print(" -", f)
    sys.exit(1)
