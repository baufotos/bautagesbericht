# -*- coding: utf-8 -*-
"""Auswertung OHNE Anthropic-Schluessel — an einem echten tl;dv-Text.

Die Funktion darf nicht davon abhaengen, dass jemand einen Schluessel
eingetragen hat. Ohne ihn wertet app.services.besprechung_lokal nach Regeln
aus: Stichpunkte trennen, Fristen und Zustaendige lesen, Punkte den laufenden
Themen zuordnen. Dieser Test haelt genau das fest — inklusive der Faelle, an
denen die Regeln frueher gescheitert sind:

  * Einwort-Themen wie "Geruestaufstockung" wurden nicht wiedererkannt und
    erzeugten bei jeder Sitzung eine Dublette.
  * "Frau Stark" in den Notizen fand die Firma nicht, weil in den Stammdaten
    "Frau R. Stark" steht.
  * Der Absatz unter "Zusammenfassung" landete als eigenes Thema im Protokoll.
"""
import io
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

TMP = tempfile.mkdtemp(prefix="lokal_")
os.environ["BTB_DATABASE_URL"] = f"sqlite:///{TMP}/t.db".replace("\\", "/")
os.environ["BTB_UPLOAD_DIR"] = f"{TMP}/up"
os.environ["BTB_OUTPUT_DIR"] = f"{TMP}/out"

from fastapi.testclient import TestClient  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

settings.anthropic_api_key = ""          # <- genau Bens Situation
init_db()
c = TestClient(app)
FEHLER: list[str] = []
OK = 0


def pruefe(bedingung, text):
    global OK
    print(("  OK   " if bedingung else "  FEHLT") + f"  {text}")
    if bedingung:
        OK += 1
    else:
        FEHLER.append(text)


def j(a, ok=(200, 201)):
    if a.status_code not in ok:
        raise SystemExit(f"{a.request.url} -> {a.status_code}: {a.text[:400]}")
    return a.json() if a.content else None


# So sehen tl;dv-Notizen aus.
NOTIZEN = """\
Zusammenfassung
Baubesprechung Nr. 17 auf dem Baufeld Weidenstieg 29.

Wichtigste Punkte
- Übermittlung eines Detailterminplans durch Rolfes Bau bis KW 36'26
- Der wilde Verband wird gem. der neu erstellten Musterfläche hergestellt
- Bemusterungstermin Musterfläche Verblendmauerwerk wurde abgenommen, damit erledigt
- Frau Stark meldet: Gerüstaufstockung kann erst ab 15.09.2026 erfolgen

Aufgaben
- MOR: Prüfung Ausführung Detail im Sockelbereich bis 20.09.26
- Baustellenbesichtigung durch Studierende am 28.09.26, HPP organisiert
- Die Lieferung des Bürocontainers ist kritisch, Verzug von vier Wochen
"""

TRANSKRIPT = """\
[00:00:12] Katharina Blanck (HPP): Guten Morgen, dann fangen wir an.
[00:01:40] Andreas Eberz (ROL): Der Detailterminplan kommt bis KW 36.
[00:04:02] Ronny Melms (SBH): Von unserer Seite passt das.
[00:06:15] Thomas Reinhardt (MOR): Das Sockeldetail prüfe ich bis zum 20.09.
[00:09:44] Rita Stark: Beim Gerüst wird es der 15.09.2026.
"""

# ── Projekt mit laufenden Themen aufsetzen ──
pid = j(c.post("/api/projekte", json={"name": "W29", "adresse": "Weidenstieg 29, 20259 Hamburg"}))["id"]
j(c.post("/api/gewerke", json={"projekt_id": pid, "firma_name": "Rolfes Bau",
                               "vergabeeinheit_code": "VE300.01",
                               "vergabeeinheit_bezeichnung": "VE01 Rohbau"}))
kap = j(c.post(f"/api/besprechungsprotokolle/kapitel/aus-gewerken?projekt_id={pid}"))
for k, n, r, ap in (("SBH", "Schulbau Hamburg", "Bauherr", "Herr R. Melms"),
                    ("HPP", "HPP Architekten", "Objektüberwachung", "Frau K. Blanck"),
                    ("ROL", "Rolfes Bau", "Rohbauer", "Frau R. Stark"),
                    ("MOR", "Mo Re Architekten", "Objektplanung", "Herr T. Reinhardt")):
    j(c.post("/api/besprechungsprotokolle/beteiligte",
             json={"projekt_id": pid, "kuerzel": k, "name": n, "rolle": r,
                   "ansprechpartner": ap, "telefon": ""}))

p1 = j(c.post("/api/besprechungsprotokolle",
              json={"projekt_id": pid, "besprechungsdatum": "2026-09-01"}))
LAUFEND = [
    (kap[1]["id"], "Übermittlung eines Detailterminplans", "ROL", "KW 35'26", "b"),
    (kap[1]["id"], "Bemusterungstermin Musterfläche Verblendmauerwerk", "ROL", "25.08.26", "n"),
    (kap[1]["id"], "Die Lieferung des Bürocontainers steht aus", "ROL", "KW 41'26", "b"),
    (kap[1]["id"], "Gerüstaufstockung", "ROL", "20.08.26", "b"),
]
for kid, text, zu, fr, st in LAUFEND:
    j(c.post(f"/api/besprechungsprotokolle/{p1['id']}/themen",
             json={"kapitel_id": kid, "thema_text": text, "zustaendig": zu,
                   "bearb_bis": fr, "status": st}))
j(c.post(f"/api/besprechungsprotokolle/{p1['id']}/freigeben", json={}))

# ── Protokoll 2: auswerten OHNE Schluessel ──
p2 = j(c.post("/api/besprechungsprotokolle",
              json={"projekt_id": pid, "besprechungsdatum": "2026-09-08"}))

print("\n=== Auswertung ohne Anthropic-Schluessel ===")
bericht = c.post(f"/api/besprechungsprotokolle/{p2['id']}/tldv-import",
                 json={"transkript": TRANSKRIPT, "notizen": NOTIZEN})
pruefe(bericht.status_code == 200,
       f"Der Aufruf geht durch statt 422 (HTTP {bericht.status_code})")
if bericht.status_code != 200:
    print(bericht.text[:400]); raise SystemExit(1)
b = bericht.json()
print(f"  -> {b['fortschreibungen']} Fortschreibungen, {b['neue_themen']} neu, "
      f"{b['teilnehmer']} Teilnehmer")
for h in b["hinweise"]:
    print(f"     Hinweis: {h[:110]}")

pruefe(b["fortschreibungen"] + b["neue_themen"] >= 6,
       f"Mindestens 6 Punkte erkannt (sind {b['fortschreibungen'] + b['neue_themen']})")
pruefe(b["fortschreibungen"] >= 3,
       f"Mindestens 3 laufende Themen wiedererkannt (sind {b['fortschreibungen']})")
pruefe(b["teilnehmer"] >= 4, f"Sprecher erkannt (sind {b['teilnehmer']})")

detail = j(c.get(f"/api/besprechungsprotokolle/{p2['id']}"))
nach_text = {}
print("\n=== Die erzeugten Zeilen ===")
for u in sorted(detail["themen_updates"], key=lambda x: x["nummer"]):
    kopf = u["thema_text"].splitlines()[0]
    nach_text[kopf] = u
    print(f"  {u['nummer']:14s} [{u['status']}] {u['zustaendig'].replace(chr(10), ' '):14s} "
          f"{u['bearb_bis']:12s} {kopf[:52]}")

print("\n=== Einzelpruefungen ===")
term = next((u for u in detail["themen_updates"] if "Detailterminplan" in u["thema_text"]), None)
pruefe(term is not None, "Der Terminplan-Punkt ist da")
if term:
    pruefe(term["bb_nr"] == "02",
           f"…als Fortschreibung erkannt, BB rueckt auf 02 (ist {term['bb_nr']})")
    pruefe(term["bearb_bis"] == "KW 36'26",
           f"…neue Frist KW 36'26 uebernommen (ist {term['bearb_bis']!r})")
    pruefe("ROL" in term["zustaendig"],
           f"…Zustaendiger ROL aus 'Rolfes Bau' erkannt (ist {term['zustaendig']!r})")
    pruefe(not term["bestaetigt"], "…und ist NICHT vorbestaetigt")

bem = next((u for u in detail["themen_updates"] if "Bemusterung" in u["thema_text"]), None)
pruefe(bem is not None and bem["status"] == "e",
       f"'abgenommen, damit erledigt' -> Status e (ist {bem['status'] if bem else '-'})")

cont = next((u for u in detail["themen_updates"] if "container" in u["thema_text"].lower()), None)
pruefe(cont is not None and cont["status"] == "k",
       f"'kritisch, Verzug' -> Status k (ist {cont['status'] if cont else '-'})")

ger = next((u for u in detail["themen_updates"] if "erüst" in u["thema_text"]), None)
pruefe(ger is not None and ger["bearb_bis"] == "15.09.2026",
       f"Datum 15.09.2026 erkannt (ist {ger['bearb_bis'] if ger else '-'})")
pruefe(ger is not None and "ROL" in ger["zustaendig"],
       f"'Frau Stark' ueber den Ansprechpartner zu ROL aufgeloest "
       f"(ist {ger['zustaendig'] if ger else '-'!r})")

sockel = next((u for u in detail["themen_updates"] if "Sockelbereich" in u["thema_text"]), None)
pruefe(sockel is not None and "MOR" in sockel["zustaendig"],
       f"'MOR:' als Zustaendiger erkannt (ist {sockel['zustaendig'] if sockel else '-'!r})")
pruefe(sockel is not None and sockel["bearb_bis"] == "20.09.26",
       f"Frist 20.09.26 erkannt (ist {sockel['bearb_bis'] if sockel else '-'})")

pruefe(all(not u["bestaetigt"] for u in detail["themen_updates"] if u["herkunft"] == "ki"),
       "Kein Vorschlag ist vorbestaetigt — der Pruefschritt bleibt Pflicht")
pruefe(c.post(f"/api/besprechungsprotokolle/{p2['id']}/freigeben",
              json={}).status_code == 409,
       "Ohne Pruefung entsteht weiterhin kein Dokument")

tn = {t["name"] for t in detail["teilnehmer"]}
print(f"\n  Teilnehmer: {sorted(tn)}")
pruefe("Katharina Blanck" in tn and "Rita Stark" in tn,
       "Sprecher mit und ohne Firmenklammer erkannt")
stark = next((t for t in detail["teilnehmer"] if t["name"] == "Rita Stark"), None)
pruefe(stark is not None and stark["firma_kuerzel"] == "ROL",
       f"'Rita Stark' ohne Klammer ueber Stammdaten zu ROL (ist "
       f"{stark['firma_kuerzel'] if stark else '-'!r})")

print("\n=== Leerer Text wird sauber abgelehnt ===")
p3 = j(c.post("/api/besprechungsprotokolle",
              json={"projekt_id": pid, "besprechungsdatum": "2026-09-15"}))
leer = c.post(f"/api/besprechungsprotokolle/{p3['id']}/tldv-import",
              json={"transkript": "", "notizen": ""})
pruefe(leer.status_code == 422, f"Leere Eingabe -> 422 (ist {leer.status_code})")

nur_gerede = c.post(f"/api/besprechungsprotokolle/{p3['id']}/tldv-import",
                    json={"transkript": "[00:01] A: Guten Morgen. Wie geht es?",
                          "notizen": ""})
pruefe(nur_gerede.status_code == 200,
       "Reines Gerede fuehrt nicht zum Absturz")
if nur_gerede.status_code == 200:
    h = nur_gerede.json()["hinweise"]
    pruefe(any("keine Themen" in x or "Notizen" in x for x in h),
           "…sondern zu einem verstaendlichen Hinweis")
    print(f"     {h[0][:130]}")

print("\n" + "=" * 62)
print(f"{len(FEHLER)} fehlgeschlagen" if FEHLER else "Alle Pruefungen bestanden.")
for f in FEHLER:
    print("  -", f)
sys.exit(1 if FEHLER else 0)
