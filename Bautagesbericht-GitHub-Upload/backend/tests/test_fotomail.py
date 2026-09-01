"""Rauchtest: Baufotos per E-Mail (Entwurf und SMTP)."""
import io
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import date
from email import message_from_bytes, policy
from pathlib import Path

# Eigene Ablage im Temp-Ordner — die echte storage/ bleibt unberuehrt.
STORAGE = Path(tempfile.gettempdir()) / "hpp-fotomailtest"
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

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services import fotoversand as versand  # noqa: E402

ok = 0
fehler = []


def pruefe(bedingung, text):
    global ok
    if bedingung:
        ok += 1
    else:
        fehler.append(text)


def bild(groesse=(900, 600), farbe=(120, 140, 160)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", groesse, farbe).save(puffer, format="JPEG", quality=90)
    return puffer.getvalue()


# Verschickte Nachrichten hier sammeln statt wirklich zu senden.
gesendet = []


def falscher_smtp(nachricht):
    gesendet.append(nachricht)


with TestClient(app) as c:
    pid = c.post("/api/projekte", json={
        "name": "2451 Neubau Verwaltungsgebäude Süd", "adresse": "",
    }).json()["id"]

    # ── Fähigkeiten: ohne SMTP-Host nur der Entwurfsweg ──
    faehig = c.get("/api/fotosaetze/mail/faehigkeiten")
    pruefe(faehig.status_code == 200, f"faehigkeiten: {faehig.status_code}")
    faehig = faehig.json()
    pruefe(faehig["smtp"] is False, f"smtp muesste aus sein: {faehig}")
    pruefe(faehig["max_anhang_mb"] == versand.MAX_ANHANG_MB,
           f"max_anhang_mb: {faehig}")
    pruefe(faehig["absender"] == "", f"absender muesste leer sein: {faehig}")

    satz = c.post("/api/fotosaetze", json={
        "projekt_id": pid, "kategorie": "Rohbau EG",
        "datum": "2026-08-19", "notiz": "Achse C, Schalung",
    }).json()
    sid = satz["id"]

    # ── Ohne Fotos: kein Versand ──
    leer = c.post(f"/api/fotosaetze/{sid}/mail/entwurf",
                  json={"empfaenger": ["bauherr@example.com"]})
    pruefe(leer.status_code == 400, f"ohne fotos: {leer.status_code} {leer.text[:200]}")

    c.post(f"/api/fotosaetze/{sid}/fotos", files=[
        ("dateien", ("IMG_1.jpg", bild(), "image/jpeg")),
        ("dateien", ("IMG_2.jpg", bild(farbe=(200, 90, 90)), "image/jpeg")),
    ])

    # ── Ohne Empfänger: 422 ──
    ohne = c.post(f"/api/fotosaetze/{sid}/mail/entwurf", json={"empfaenger": []})
    pruefe(ohne.status_code == 422, f"ohne empfaenger: {ohne.status_code}")

    # Leere Zeilen aus dem Formular dürfen nicht stören.
    leerzeile = c.post(f"/api/fotosaetze/{sid}/mail/entwurf",
                       json={"empfaenger": ["bauherr@example.com", "  ", ""]})
    pruefe(leerzeile.status_code == 200,
           f"leere zeilen: {leerzeile.status_code} {leerzeile.text[:200]}")

    # ── Unsinnige Adresse: 422, nicht 500 ──
    murks = c.post(f"/api/fotosaetze/{sid}/mail/entwurf",
                   json={"empfaenger": ["kein-at-zeichen"]})
    pruefe(murks.status_code == 422, f"murksadresse: {murks.status_code}")

    # ── Entwurf mit Kopie ──
    antwort = c.post(f"/api/fotosaetze/{sid}/mail/entwurf", json={
        "empfaenger": ["bauherr@example.com", "statik@example.com"],
        "kopie": ["ablage@example.com"],
    })
    pruefe(antwort.status_code == 200,
           f"entwurf: {antwort.status_code} {antwort.text[:300]}")
    pruefe(antwort.headers["content-type"].startswith("message/rfc822"),
           f"typ: {antwort.headers.get('content-type')}")
    verfuegung = antwort.headers["content-disposition"]
    pruefe(".eml" in verfuegung and "filename*=UTF-8''" in verfuegung,
           f"dateiname: {verfuegung}")
    pruefe("Verwaltungsgeb" in verfuegung, f"projektname im dateinamen: {verfuegung}")

    mail = message_from_bytes(antwort.content, policy=policy.default)
    pruefe(mail["X-Unsent"] == "1", f"X-Unsent fehlt: {dict(mail.items())}")
    pruefe(mail["From"] is None, f"From muesste offen bleiben: {mail['From']}")
    pruefe(mail["To"] == "bauherr@example.com, statik@example.com", f"To: {mail['To']}")
    pruefe(mail["Cc"] == "ablage@example.com", f"Cc: {mail['Cc']}")
    pruefe(mail["Subject"] == "Baufotos 2451 Neubau Verwaltungsgebäude Süd — "
                              "Rohbau EG, 19.08.2026", f"Betreff: {mail['Subject']}")

    text = mail.get_body(preferencelist=("plain",)).get_content()
    pruefe("Achse C, Schalung" in text, "Notiz muesste im Text stehen")
    pruefe("260819_Rohbau_EG_1.jpg" in text and "260819_Rohbau_EG_2.jpg" in text,
           f"Dateinamen fehlen im Text:\n{text}")
    pruefe("2 Foto(s)" in text, f"Anzahl fehlt:\n{text}")
    pruefe("localhost" not in text and "Direkter Download" not in text,
           "ohne public_base_url darf kein Link im Text stehen")

    anhaenge = [t for t in mail.iter_attachments()]
    pruefe(len(anhaenge) == 1, f"genau ein Anhang erwartet: {len(anhaenge)}")
    anhang = anhaenge[0]
    pruefe(anhang.get_filename() == satz["zip_dateiname"],
           f"Anhangname {anhang.get_filename()} != {satz['zip_dateiname']}")
    with zipfile.ZipFile(io.BytesIO(anhang.get_payload(decode=True))) as archiv:
        namen = sorted(archiv.namelist())
    pruefe(namen == ["260819_Rohbau_EG_1.jpg", "260819_Rohbau_EG_2.jpg"],
           f"ZIP-Inhalt: {namen}")

    # ── Der Entwurf wird am Fotosatz vermerkt ──
    stand = c.get(f"/api/fotosaetze/{sid}").json()
    pruefe(stand["mail_weg"] == "entwurf", f"mail_weg: {stand['mail_weg']}")
    pruefe(stand["mail_versendet_am"] == date.today().isoformat(),
           f"mail_versendet_am: {stand['mail_versendet_am']}")
    pruefe("bauherr@example.com" in stand["mail_empfaenger"]
           and "ablage@example.com" in stand["mail_empfaenger"],
           f"mail_empfaenger: {stand['mail_empfaenger']}")
    liste = c.get(f"/api/fotosaetze?projekt_id={pid}").json()
    pruefe(liste[0]["mail_weg"] == "entwurf", "Liste muesste den Weg mitliefern")

    # ── Eigener Betreff und Text werden übernommen ──
    eigen = c.post(f"/api/fotosaetze/{sid}/mail/entwurf", json={
        "empfaenger": ["bauherr@example.com"],
        "betreff": "Fotos Abnahme Dach",
        "nachricht": "Hallo Herr Meyer,\n\nwie besprochen.",
    })
    eigen_mail = message_from_bytes(eigen.content, policy=policy.default)
    pruefe(eigen_mail["Subject"] == "Fotos Abnahme Dach",
           f"eigener Betreff: {eigen_mail['Subject']}")
    pruefe("wie besprochen" in
           eigen_mail.get_body(preferencelist=("plain",)).get_content(),
           "eigener Text fehlt")

    # ── Link nur, wenn die App öffentlich erreichbar ist ──
    settings.public_base_url = "https://baumanagement.hpp.com"
    mit_link = message_from_bytes(
        c.post(f"/api/fotosaetze/{sid}/mail/entwurf",
               json={"empfaenger": ["bauherr@example.com"]}).content,
        policy=policy.default)
    pruefe("https://baumanagement.hpp.com/api/fotosaetze/" in
           mit_link.get_body(preferencelist=("plain",)).get_content(),
           "Link fehlt trotz public_base_url")
    settings.public_base_url = ""

    # ── Senden ohne SMTP: klare Absage, kein Fehler 500 ──
    absage = c.post(f"/api/fotosaetze/{sid}/mail/senden",
                    json={"empfaenger": ["bauherr@example.com"]})
    pruefe(absage.status_code == 503, f"senden ohne smtp: {absage.status_code}")
    pruefe("Outlook-Entwurf" in absage.text, f"Hinweis fehlt: {absage.text[:200]}")

    # ── Mit SMTP: es wird wirklich verschickt ──
    settings.smtp_host = "mail.hpp.local"
    settings.smtp_port = 25
    settings.smtp_absender = "baumanagement@hpp.com"
    echt = versand.sende_per_smtp
    versand.sende_per_smtp = falscher_smtp
    try:
        faehig2 = c.get("/api/fotosaetze/mail/faehigkeiten").json()
        pruefe(faehig2["smtp"] is True, f"smtp muesste an sein: {faehig2}")
        pruefe(faehig2["absender"] ==
               "HPP Baumanagement <baumanagement@hpp.com>",
               f"absender: {faehig2}")

        gesendet.clear()
        erfolg = c.post(f"/api/fotosaetze/{sid}/mail/senden", json={
            "empfaenger": ["bauherr@example.com"], "kopie": ["ablage@example.com"],
        })
        pruefe(erfolg.status_code == 200,
               f"senden: {erfolg.status_code} {erfolg.text[:300]}")
        daten = erfolg.json()
        pruefe(daten["versendet"] is True, f"versendet: {daten}")
        pruefe(daten["empfaenger"] == ["bauherr@example.com", "ablage@example.com"],
               f"empfaenger: {daten}")
        pruefe(len(gesendet) == 1, f"genau eine Nachricht erwartet: {len(gesendet)}")
        pruefe(gesendet[0]["From"] == "HPP Baumanagement <baumanagement@hpp.com>",
               f"From: {gesendet[0]['From']}")
        pruefe(gesendet[0]["X-Unsent"] is None,
               "eine wirklich verschickte Mail darf kein X-Unsent tragen")
        stand2 = c.get(f"/api/fotosaetze/{sid}").json()
        pruefe(stand2["mail_weg"] == "smtp", f"mail_weg nach senden: {stand2['mail_weg']}")

        # ── Fehler beim Relay: 502 mit technischer Meldung ──
        def kaputt(_nachricht):
            raise OSError("Verbindung abgelehnt")

        versand.sende_per_smtp = kaputt
        panne = c.post(f"/api/fotosaetze/{sid}/mail/senden",
                       json={"empfaenger": ["bauherr@example.com"]})
        pruefe(panne.status_code == 502, f"relay-fehler: {panne.status_code}")
        pruefe("mail.hpp.local" in panne.text and "abgelehnt" in panne.text,
               f"Meldung zu unspezifisch: {panne.text[:200]}")
    finally:
        versand.sende_per_smtp = echt
        settings.smtp_host = ""
        settings.smtp_absender = ""

    # ── Zu großer Anhang: 413 statt einer Mail, die abprallt ──
    grenze = versand.MAX_ANHANG_MB
    versand.MAX_ANHANG_MB = 0
    try:
        zu_gross = c.post(f"/api/fotosaetze/{sid}/mail/entwurf",
                          json={"empfaenger": ["bauherr@example.com"]})
        pruefe(zu_gross.status_code == 413, f"zu gross: {zu_gross.status_code}")
        pruefe("ZIP-Datei herunter" in zu_gross.text,
               f"Auswegs-Hinweis fehlt: {zu_gross.text[:250]}")
    finally:
        versand.MAX_ANHANG_MB = grenze

    # ── Unbekannter Fotosatz ──
    pruefe(c.post("/api/fotosaetze/99999/mail/entwurf",
                  json={"empfaenger": ["a@example.com"]}).status_code == 404,
           "unbekannter fotosatz muesste 404 sein")

print(f"\n{ok} Pruefungen ok, {len(fehler)} Fehler")
for f in fehler:
    print("  FEHLER:", f)
sys.exit(1 if fehler else 0)
