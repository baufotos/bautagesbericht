# -*- coding: utf-8 -*-
"""Adresse -> Koordinaten, ohne Netz geprueft.

Der Anlass: In den Stammdaten stand bei einer voellig richtig eingetippten
Adresse "ohne Standort". Ursache war nicht die Eingabe, sondern die
Freitextsuche von Nominatim — sie liefert bei einem Zusatz vor der Strasse
keine ungenaue Antwort, sondern eine leere Liste:

    "Kaistrasse 5, 40221 Duesseldorf"               -> Treffer
    "DESYUM, Notkestrasse 85, 22607 Hamburg"        -> leer
    "Baufeld 3, Ueberseeallee 10, 20457 Hamburg"    -> leer
    "Hauptstr. 12, 45127 Essen"                     -> leer

Auf einer Baustelle sieht eine Adresse aber genau so aus. Dieser Test haelt
fest, was seitdem gilt:

  * Die Eingabe wird zerlegt, bevor gesucht wird — Zusatz raus, Abkuerzung
    aufgeloest.
  * Gesucht wird in absteigender Genauigkeit bei zwei Diensten.
  * Jeder Treffer wird gegen die Eingabe geprueft. Ein Treffer in einer
    anderen PLZ UND einem anderen Ort fliegt raus, sonst haette eine "20259"
    schon zu einem Dorf im Baskenland gefuehrt.
  * Ein Treffer sieht nie genauer aus, als die Eingabe war.
  * "nicht gefunden" und "Dienst nicht erreichbar" bleiben unterscheidbar.

Es faellt kein echter Netzaufruf an: ``_hole`` wird durch eine Attrappe
ersetzt, die feste Antworten liefert.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

TMP = tempfile.mkdtemp(prefix="geo_")
os.environ["BTB_DATABASE_URL"] = f"sqlite:///{TMP}/t.db".replace("\\", "/")
os.environ["BTB_UPLOAD_DIR"] = f"{TMP}/up"
os.environ["BTB_OUTPUT_DIR"] = f"{TMP}/out"

from fastapi.testclient import TestClient  # noqa: E402
from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import geocoding as geo  # noqa: E402

FEHLER: list[str] = []
OK = 0


def pruefe(bedingung, text):
    global OK
    if bedingung:
        OK += 1
        print(f"  OK     {text}")
    else:
        FEHLER.append(text)
        print(f"  FEHLT  {text}")


# ─────────────────────────────────────────────────────────────────────────────
# Attrappe fuer die Dienste
# ─────────────────────────────────────────────────────────────────────────────

#: Was die Attrappe auf welche Anfrage antwortet. Der Schluessel ist der
#: Dienst plus die entscheidenden Parameter.
ANTWORTEN: dict[str, object] = {}
#: Dienste, die "nicht erreichbar" spielen.
TOT: set[str] = set()
#: Mitschrift aller Anfragen, um die Reihenfolge der Leiter zu pruefen.
ANFRAGEN: list[tuple[str, dict]] = []


def _dienst(url: str) -> str:
    if "nominatim" in url:
        return "nominatim"
    if "photon" in url:
        return "photon"
    return "open-meteo"


async def _attrappe(client, url, params, *, bremsen):
    dienst = _dienst(url)
    ANFRAGEN.append((dienst, dict(params)))
    if dienst in TOT:
        return None, False
    schluessel = dienst + "|" + "|".join(
        f"{k}={params[k]}"
        for k in ("q", "street", "postalcode", "city", "name")
        if params.get(k)
    )
    return ANTWORTEN.get(schluessel, [] if dienst == "nominatim" else {}), True


#: Die echte Fassung festhalten - Abschnitt 8 prueft sie unverfaelscht.
_hole_echt = geo._hole
geo._hole = _attrappe
geo.NOMINATIM_ABSTAND = 0.0


def nominatim_treffer(lat, lon, name, *, hnr="", strasse="", plz="", ort=""):
    return [
        {
            "lat": str(lat),
            "lon": str(lon),
            "display_name": name,
            "address": {
                k: v
                for k, v in (
                    ("house_number", hnr),
                    ("road", strasse),
                    ("postcode", plz),
                    ("city", ort),
                )
                if v
            },
        }
    ]


def photon_treffer(lat, lon, *, hnr="", strasse="", plz="", ort="", land="DE"):
    return {
        "features": [
            {
                "geometry": {"coordinates": [lon, lat]},
                "properties": {
                    k: v
                    for k, v in (
                        ("housenumber", hnr),
                        ("street", strasse),
                        ("postcode", plz),
                        ("city", ort),
                        ("countrycode", land),
                    )
                    if v
                },
            }
        ]
    }


def frisch():
    """Vor jedem Fall: Zwischenspeicher und Mitschrift leeren."""
    geo.leere_zwischenspeicher()
    ANTWORTEN.clear()
    TOT.clear()
    ANFRAGEN.clear()


# ─────────────────────────────────────────────────────────────────────────────
print("=== 1. Die Eingabe zerlegen (braucht kein Netz) ===")
# ─────────────────────────────────────────────────────────────────────────────

ZERLEGUNGEN = [
    # Eingabe, Zusatz, Strasse, Hausnummer, PLZ, Ort
    ("Kaistraße 5, 40221 Düsseldorf", "", "Kaistraße", "5", "40221", "Düsseldorf"),
    ("DESYUM, Notkestraße 85, 22607 Hamburg",
     "DESYUM", "Notkestraße", "85", "22607", "Hamburg"),
    ("Baufeld 3, Überseeallee 10, 20457 Hamburg",
     "Baufeld 3", "Überseeallee", "10", "20457", "Hamburg"),
    ("Los 2, Bauteil A, Königsallee 60, 40212 Düsseldorf",
     "Los 2, Bauteil A", "Königsallee", "60", "40212", "Düsseldorf"),
    # Abkuerzungen: so steht es in jeder zweiten Mail.
    ("Hauptstr. 12, 45127 Essen", "", "Hauptstraße", "12", "45127", "Essen"),
    ("Willy-Brandt-Str. 1, 20457 Hamburg",
     "", "Willy-Brandt-Straße", "1", "20457", "Hamburg"),
    # Hausnummernbereich und fehlende Kommas.
    ("Weidenstieg 29-31, 20259 Hamburg", "", "Weidenstieg", "29-31", "20259", "Hamburg"),
    ("Weidenstieg 29 20259 Hamburg", "", "Weidenstieg", "29", "20259", "Hamburg"),
    # Land hinten dran darf nicht als Ort gelesen werden.
    ("Notkestr. 85, 22607 Hamburg, Deutschland",
     "", "Notkestraße", "85", "22607", "Hamburg"),
    # Nur PLZ+Ort, nur Ort.
    ("20259 Hamburg", "", "", "", "20259", "Hamburg"),
    ("Celle", "", "", "", "", "Celle"),
    ("Am Hauptbahnhof, Düsseldorf", "", "Am Hauptbahnhof", "", "", "Düsseldorf"),
    ("", "", "", "", "", ""),
    # Vierstellige PLZ (AT/CH) - auch OHNE Landangabe, denn die Suche ist auf
    # de/at/ch eingestellt und "8001 Zürich" ist eine vollstaendige Angabe.
    ("Bahnhofstrasse 1, 8001 Zürich", "", "Bahnhofstrasse", "1", "8001", "Zürich"),
    ("Bahnhofstrasse 1, 8001 Zürich, Schweiz",
     "", "Bahnhofstrasse", "1", "8001", "Zürich"),
    ("Ringstraße 2, 1010 Wien", "", "Ringstraße", "2", "1010", "Wien"),
    ("8001 Zürich", "", "", "", "8001", "Zürich"),
    # ... aber eine Zahl im Zusatz ist keine Postleitzahl. Deshalb greift das
    # kurze Muster nur mit einem Ortsnamen dahinter und nur am Ende.
    ("Baufeld 2024, Musterweg 5, 45127 Essen",
     "Baufeld 2024", "Musterweg", "5", "45127", "Essen"),
    ("Halle 2024", "", "Halle", "2024", "", ""),
]
for eingabe, zusatz, strasse, hnr, plz, ort in ZERLEGUNGEN:
    t = geo.zerlege(eingabe)
    ist = (t.zusatz, t.strasse, t.hausnummer, t.plz, t.ort)
    pruefe(ist == (zusatz, strasse, hnr, plz, ort),
           f"{eingabe!r} -> {ist}" + ("" if ist == (zusatz, strasse, hnr, plz, ort)
                                      else f"  erwartet {(zusatz, strasse, hnr, plz, ort)}"))

pruefe(geo.zerlege("Weidenstieg 29-31, 20259 Hamburg").hausnummer_einzeln == "29",
       "Nummernbereich '29-31' wird fuer die Suche zu '29' — OSM kennt nur den Anfang")

# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 2. Der Fall, der frueher 'ohne Standort' ergab ===")
# ─────────────────────────────────────────────────────────────────────────────
frisch()
# Nominatim strukturiert findet es, weil "DESYUM" vorher entfernt wurde.
ANTWORTEN["nominatim|street=Notkestraße 85|postalcode=22607|city=Hamburg"] = (
    nominatim_treffer(53.5731, 9.8817, "85, Notkestraße, Bahrenfeld, Hamburg, 22607",
                      hnr="85", strasse="Notkestraße", plz="22607", ort="Hamburg")
)
e = asyncio.run(geo.suche_standort("DESYUM, Notkestraße 85, 22607 Hamburg"))
pruefe(e.bester is not None and abs(e.bester.lat - 53.5731) < 1e-6,
       "'DESYUM, Notkestraße 85, 22607 Hamburg' wird gefunden")
pruefe(e.bester is not None and e.bester.guete == "adresse",
       f"…und zwar hausnummergenau (ist {e.bester.guete if e.bester else '-'})")
pruefe(len(ANFRAGEN) == 1,
       f"…mit einer einzigen Anfrage, weil die erste Stufe traf (waren {len(ANFRAGEN)})")

# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 3. Photon faengt auf, was Nominatim nicht kennt ===")
# ─────────────────────────────────────────────────────────────────────────────
frisch()
ANTWORTEN["photon|q=Hauptstraße 12, 45127 Essen"] = photon_treffer(
    51.4170, 7.1205, hnr="12", strasse="Hauptstraße", plz="45127", ort="Essen")
e = asyncio.run(geo.suche_standort("Hauptstr. 12, 45127 Essen"))
pruefe(e.bester is not None and e.bester.quelle == "photon",
       "Nominatim leer -> Photon uebernimmt")
pruefe(e.bester is not None and abs(e.bester.lat - 51.4170) < 1e-6,
       "…und liefert die richtige Stelle")
pruefe([d for d, _ in ANFRAGEN][:2] == ["nominatim", "nominatim"],
       f"Reihenfolge: strukturiert zuerst, dann tolerant (war {[d for d, _ in ANFRAGEN]})")

# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 4. Ausreisser werden verworfen ===")
# ─────────────────────────────────────────────────────────────────────────────
frisch()
# Der reale Ausrutscher: eine deutsche PLZ als Ortsname gedeutet.
ANTWORTEN["photon|q=Musterweg 1, 20259 Hamburg"] = photon_treffer(
    43.0693, -2.1278, strasse="Kale Nagusia", plz="20259", ort="Baliarrain", land="ES")
e = asyncio.run(geo.suche_standort("Musterweg 1, 20259 Hamburg"))
pruefe(e.bester is None,
       f"Treffer im Ausland wird verworfen (ist {e.bester.label if e.bester else 'keiner'})")

frisch()
# Andere PLZ, aber derselbe Ort: brauchbar, muss aber gekennzeichnet sein.
ANTWORTEN["photon|q=Hauptstraße 12, 45127 Essen"] = photon_treffer(
    51.3625, 6.9448, hnr="12", strasse="Hauptstraße", plz="45219", ort="Essen")
e = asyncio.run(geo.suche_standort("Hauptstr. 12, 45127 Essen"))
pruefe(e.bester is not None and "45219" in e.bester.hinweis,
       f"Abweichende PLZ im selben Ort: kommt durch, aber mit Hinweis "
       f"({e.bester.hinweis if e.bester else '-'!r})")

frisch()
# Die Strasse gibt es nicht — der Dienst bietet eine andere an.
ANTWORTEN["photon|q=Musterweg, 22765 Hamburg"] = photon_treffer(
    53.5522, 9.9346, strasse="Paul-Nevermann-Platz", plz="22765", ort="Hamburg")
e = asyncio.run(geo.suche_standort("Musterweg, 22765 Hamburg"))
pruefe(e.bester is not None and e.bester.guete == "ort",
       f"Fremde Strasse zaehlt nur noch als Ortstreffer "
       f"(ist {e.bester.guete if e.bester else '-'})")
pruefe(e.bester is not None and "Musterweg" in e.bester.hinweis,
       f"…und sagt, was nicht gefunden wurde ({e.bester.hinweis if e.bester else '-'!r})")

# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 5. Nie genauer aussehen als die Eingabe ===")
# ─────────────────────────────────────────────────────────────────────────────
frisch()
ANTWORTEN["nominatim|postalcode=20259|city=Hamburg"] = nominatim_treffer(
    53.5733, 9.9665, "Hamburg, Deutschland", ort="Hamburg")
e = asyncio.run(geo.suche_standort("20259 Hamburg"))
pruefe(e.bester is not None and e.bester.guete == "ort",
       f"Ohne Strasse hoechstens ortsgenau (ist {e.bester.guete if e.bester else '-'})")
pruefe(len(ANFRAGEN) == 1,
       f"…und die Leiter haelt sofort an (waren {len(ANFRAGEN)} Anfragen)")
pruefe(all(d != "photon" for d, _ in ANFRAGEN),
       "…Photon wird gar nicht erst gefragt, es haette ein x-beliebiges Haus geliefert")

frisch()
# Open-Meteo darf nie eine PLZ sehen: "20259" ist dort ein Ort in Spanien.
ANTWORTEN["nominatim|postalcode=20259"] = []
asyncio.run(geo.suche_standort("20259"))
pruefe(all(d != "open-meteo" for d, _ in ANFRAGEN),
       f"Reine PLZ geht nicht an Open-Meteo (Anfragen: {[d for d, _ in ANFRAGEN]})")

# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 6. Stoerung ist nicht dasselbe wie 'nicht gefunden' ===")
# ─────────────────────────────────────────────────────────────────────────────
frisch()
TOT.update({"nominatim", "photon", "open-meteo"})
e = asyncio.run(geo.suche_standort("Kaistraße 5, 40221 Düsseldorf"))
pruefe(e.bester is None and e.dienst_erreichbar is False,
       f"Kein Dienst erreichbar -> als Stoerung gemeldet (ist {e.dienst_erreichbar})")
pruefe(e.teile.strasse == "Kaistraße",
       "Zerlegen funktioniert auch ohne Netz")
pruefe(len(geo._zwischenspeicher) == 0,
       "Eine Stoerung wird NICHT gemerkt — sonst bliebe der Standort dauerhaft leer")

TOT.clear()
ANTWORTEN["nominatim|street=Kaistraße 5|postalcode=40221|city=Düsseldorf"] = (
    nominatim_treffer(51.2143, 6.7526, "5, Kaistraße, Düsseldorf, 40221",
                      hnr="5", strasse="Kaistraße", plz="40221", ort="Düsseldorf")
)
e = asyncio.run(geo.suche_standort("Kaistraße 5, 40221 Düsseldorf"))
pruefe(e.bester is not None, "Nach der Stoerung liefert derselbe Aufruf wieder")

frisch()
ANTWORTEN["nominatim|street=Quatschweg 9|postalcode=99999|city=Nirgendwo"] = []
e = asyncio.run(geo.suche_standort("Quatschweg 9, 99999 Nirgendwo"))
pruefe(e.bester is None and e.dienst_erreichbar is True,
       "Unauffindbar, aber Dienst erreichbar — der Nutzer muss die Adresse pruefen, "
       "nicht spaeter wiederkommen")

# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 7. Ueber die API: anlegen, waehlen, von Hand, entfernen ===")
# ─────────────────────────────────────────────────────────────────────────────
init_db()
c = TestClient(app)
frisch()
ANTWORTEN["nominatim|street=Notkestraße 85|postalcode=22607|city=Hamburg"] = (
    nominatim_treffer(53.5731, 9.8817, "85, Notkestraße, Bahrenfeld, Hamburg, 22607",
                      hnr="85", strasse="Notkestraße", plz="22607", ort="Hamburg")
)

antwort = c.get("/api/projekte/standort-suche",
                params={"adresse": "DESYUM, Notkestraße 85, 22607 Hamburg"})
pruefe(antwort.status_code == 200, f"Suchendpunkt antwortet (HTTP {antwort.status_code})")
suche = antwort.json()
pruefe(suche["erkannt"].get("zusatz") == "DESYUM",
       f"Die Oberflaeche erfaehrt, wie gelesen wurde: {suche['erkannt']}")
pruefe(len(suche["treffer"]) == 1, f"Treffer zur Auswahl ({len(suche['treffer'])})")

projekt = c.post("/api/projekte", json={
    "name": "Besucherzentrum",
    "adresse": "DESYUM, Notkestraße 85, 22607 Hamburg"}).json()
pruefe(projekt["lat"] is not None and projekt["standort_guete"] == "adresse",
       f"Anlegen setzt den Standort samt Guete ({projekt['standort_guete']!r})")
pruefe("Notkestraße" in projekt["standort_label"],
       "…und merkt sich den Klartext zum Gegenlesen")

von_hand = c.patch(f"/api/projekte/{projekt['id']}",
                   json={"lat": 53.4, "lon": 10.1}).json()
pruefe(von_hand["lat"] == 53.4 and von_hand["standort_guete"] == "manuell",
       f"Handeingabe gewinnt gegen den Dienst ({von_hand['standort_guete']!r})")

geleert = c.patch(f"/api/projekte/{projekt['id']}",
                  json={"standort_entfernen": True}).json()
pruefe(geleert["lat"] is None and geleert["standort_guete"] == "",
       "Standort laesst sich wieder entfernen")

nachgeholt = c.patch(f"/api/projekte/{projekt['id']}",
                     json={"standort_neu_suchen": True}).json()
pruefe(nachgeholt["lat"] is not None,
       "'Standort neu suchen' holt ihn ohne Adressaenderung nach — vorher gab es "
       "dafuer keinen Weg")

frisch()
TOT.update({"nominatim", "photon", "open-meteo"})
behalten = c.patch(f"/api/projekte/{projekt['id']}",
                   json={"standort_neu_suchen": True}).json()
pruefe(behalten["lat"] is not None,
       "Eine erfolglose Wiederholung loescht den guten Standort nicht")

# ---------------------------------------------------------------------------
print("\n=== 8. Ein einzelner Aussetzer darf keine Stufe kosten ===")
# ---------------------------------------------------------------------------
# Beobachtet in der laufenden App: Die erste Nominatim-Stufe meldete "keine
# Antwort", die naechste - eine Sekunde spaeter, derselbe Dienst - antwortete
# normal. Ohne Wiederholung geht dabei die genaueste Stufe verloren, und in der
# Oberflaeche sieht das aus wie "Adresse nicht gefunden".


class Antwort:
    status_code = 200

    def __init__(self, inhalt):
        self._inhalt = inhalt

    def json(self):
        return self._inhalt


class EinmalFehler:
    """Wirft beim ersten Aufruf, antwortet beim zweiten."""

    def __init__(self, inhalt):
        self.aufrufe = 0
        self.inhalt = inhalt

    async def get(self, url, params=None, headers=None):
        self.aufrufe += 1
        if self.aufrufe == 1:
            raise OSError("Verbindung abgebrochen")
        return Antwort(self.inhalt)


class ImmerFehler:
    def __init__(self):
        self.aufrufe = 0

    async def get(self, url, params=None, headers=None):
        self.aufrufe += 1
        raise OSError("dauerhaft gestoert")


class Ueberlastet:
    """Antwortet erst mit 429, dann normal - so bremst Nominatim."""

    def __init__(self, inhalt):
        self.aufrufe = 0
        self.inhalt = inhalt

    async def get(self, url, params=None, headers=None):
        self.aufrufe += 1
        if self.aufrufe == 1:
            class Zuviel:
                status_code = 429

                def json(self):
                    return {}

            return Zuviel()
        return Antwort(self.inhalt)


TESTTREFFER = nominatim_treffer(
    53.5, 10.0, "Teststrasse 1, 20095 Hamburg",
    hnr="1", strasse="Teststrasse", plz="20095", ort="Hamburg")

klient = EinmalFehler(TESTTREFFER)
daten, erreichbar = asyncio.run(
    _hole_echt(klient, geo.NOMINATIM_URL, {"q": "x"}, bremsen=False))
pruefe(klient.aufrufe == 2,
       f"Nach einer Netzausnahme wird wiederholt (Aufrufe: {klient.aufrufe})")
pruefe(erreichbar is True and daten is not None,
       "...und der zweite Versuch zaehlt als Antwort")

dauerhaft = ImmerFehler()
daten, erreichbar = asyncio.run(
    _hole_echt(dauerhaft, geo.NOMINATIM_URL, {"q": "x"}, bremsen=False))
pruefe(dauerhaft.aufrufe == geo.VERSUCHE,
       f"Bei dauerhafter Stoerung genau {geo.VERSUCHE} Versuche, dann Schluss "
       f"(waren {dauerhaft.aufrufe})")
pruefe(erreichbar is False and daten is None,
       "...und das Ergebnis heisst 'nicht erreichbar', nicht 'nichts gefunden'")

gebremst = Ueberlastet(TESTTREFFER)
daten, erreichbar = asyncio.run(
    _hole_echt(gebremst, geo.NOMINATIM_URL, {"q": "x"}, bremsen=False))
pruefe(gebremst.aufrufe == 2 and daten is not None,
       f"429 heisst 'gerade zu viel', nicht 'gibt es nicht' - wird wiederholt "
       f"(Aufrufe: {gebremst.aufrufe})")

print("\n" + "=" * 62)
print(f"{OK} Pruefungen bestanden"
      + (f", {len(FEHLER)} FEHLGESCHLAGEN" if FEHLER else "."))
for f in FEHLER:
    print("  -", f)
sys.exit(1 if FEHLER else 0)
