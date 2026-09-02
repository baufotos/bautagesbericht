"""Adresse → Koordinaten. Mehrstufig, weil eine Baustellenadresse selten sauber ist.

Warum das mehr ist als ein HTTP-Aufruf
--------------------------------------
Auf dem Bau heißt eine Adresse nicht „Kaistraße 5, 40221 Düsseldorf", sondern
„DESYUM, Notkestraße 85, 22607 Hamburg" oder „Baufeld 3, Überseeallee 10,
20457 Hamburg". Nominatims Freitextsuche gibt bei solchen Zusätzen keine
ungenaue Antwort, sondern eine **leere Liste** — und genau das stand hinter der
Meldung „ohne Standort" bei einer völlig richtigen Adresse. Gemessen am
02.09.2026 gegen den öffentlichen Dienst:

    "Kaistraße 5, 40221 Düsseldorf"                -> Treffer
    "Weidenstieg 29, 20259 Hamburg"                -> Treffer
    "DESYUM, Notkestraße 85, 22607 Hamburg"        -> leer
    "Baufeld 3, Überseeallee 10, 20457 Hamburg"    -> leer
    "Grundstück neben Hausnummer 14, Musterweg, …" -> leer

Deshalb wird die Eingabe hier erst **zerlegt** (Zusatz, Straße, Hausnummer,
PLZ, Ort) und dann in **absteigender Genauigkeit** gesucht — erst die genaue
Hausnummer, am Ende nur noch der Ort. Für den Zweck der Koordinaten, den
Wetterabruf des Bautagesberichts, ist der Ort immer noch brauchbar: die
DWD-Station liegt ohnehin Kilometer entfernt. Ein grober Treffer ist also
besser als keiner — er wird nur als grob **gekennzeichnet**, damit die
Oberfläche das sagen kann statt es zu verschweigen.

Zwei Dienste, weil sie sich ergänzen
------------------------------------
* **Nominatim** ist streng: strukturierte Felder treffen genau, Freitext mit
  Zusatz fällt durch.
* **Photon** (ebenfalls OSM, ebenfalls ohne Schlüssel) ist tolerant und findet
  „DESYUM, Notkestraße 85" und Abkürzungen wie „Hauptstr." — dafür rät es
  gelegentlich daneben. Für „Hauptstr. 12, 45127 Essen" liefert es
  „Alte Hauptstraße 12, 45289 Essen", also eine andere Straße in einem anderen
  Stadtteil.

Deswegen wird **jeder** Treffer gegen die Eingabe geprüft (`_bewerte`): Wenn
die gefundene PLZ der eingegebenen widerspricht **und** der Ort ein anderer
ist, wird er verworfen. Widerspricht nur die PLZ, kommt er als „ungenau"
durch — das ist der Fall oben, und im selben Ort ist das fürs Wetter richtig.

Open-Meteo steht als letzte Ebene bereit, aber **nur für Ortsnamen**: mit einer
PLZ befragt liefert es Unsinn („20259" → Baliarrain, Baskenland).
"""

from __future__ import annotations

import asyncio
import math
import re
import time
import unicodedata
from dataclasses import dataclass, field, replace

import httpx

from app.config import settings

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_URL = "https://photon.komoot.io/api"
OPEN_METEO_URL = "https://geocoding-api.open-meteo.com/v1/search"

#: Nominatims Nutzungsbedingungen erlauben eine Abfrage pro Sekunde. Die
#: Leiter unten stellt bis zu fünf Abfragen — ohne diese Bremse antwortet der
#: Dienst irgendwann mit 403 und die App hätte wieder „ohne Standort", nur aus
#: einem anderen Grund.
NOMINATIM_ABSTAND = 1.1

#: Ländervorwahl der Suche. Ohne sie findet „Essen" auch Orte in den
#: Niederlanden, und „Celle" eine Gemeinde in Italien.
LAENDER = "de,at,ch"

#: Frist einer einzelnen Abfrage.
ZEITLIMIT = 8.0

#: Versuche je Abfrage. Zwei, weil ein einzelner Aussetzer haeufig ist und
#: eine Wiederholung fast immer traegt.
VERSUCHE = 2

#: Frist fuer die ganze Leiter. Ohne sie koennte ein zaeher Dienst das Anlegen
#: eines Projekts minutenlang blockieren: sechs Stufen, je zwei Versuche, je
#: acht Sekunden. Wird sie erreicht, gilt das Beste, was bis dahin zusammenkam
#: - und dass abgebrochen wurde, steht in "versuche".
GESAMTFRIST = 30.0


# ─────────────────────────────────────────────────────────────────────────────
# Eingabe aufräumen
# ─────────────────────────────────────────────────────────────────────────────

#: Was auf Bauplänen und in Mails abgekürzt steht. Nominatim kennt die
#: Langform, Photon beide — ausgeschrieben trifft es also in jedem Fall.
#: Reihenfolge zählt: „-str." muss vor „str." greifen, sonst entsteht
#: „Willy-Brandt-Str aße".
ABKUERZUNGEN: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<=\w)str\.(?=\s|,|$)", re.I), "straße"),
    (re.compile(r"\bStr\.(?=\s|,|$)"), "Straße"),
    (re.compile(r"\bstr\.(?=\s|,|$)"), "straße"),
    (re.compile(r"(?<=\w)pl\.(?=\s|,|$)", re.I), "platz"),
    (re.compile(r"\bPl\.(?=\s|,|$)"), "Platz"),
    (re.compile(r"(?<=\w)g\.(?=\s|,|$)", re.I), "gasse"),
    (re.compile(r"(?<=\w)w\.(?=\s|,|$)", re.I), "weg"),
    (re.compile(r"\bSt\.(?=\s)"), "Sankt"),
    (re.compile(r"\ba\.\s*d\.(?=\s)", re.I), "an der"),
    (re.compile(r"\ba\.\s*m\.(?=\s)", re.I), "am"),
    (re.compile(r"\bb\.(?=\s)", re.I), "bei"),
    (re.compile(r"\bggü\.(?=\s|,|$)", re.I), "gegenüber"),
)

#: Angaben, die auf einer Baustelle vor der Straße stehen und keinen
#: Kartenbezug haben. Sie werden für die strukturierte Suche entfernt, für die
#: tolerante Freitextsuche aber behalten — „DESYUM" ist bei Photon sogar der
#: Treffer.
FUELLWOERTER = re.compile(
    r"^(baufeld|bauabschnitt|ba|bauteil|los|gebäude|geb\.|haus|"
    r"grundstück|flurstück|flst\.?|gemarkung|ecke|zufahrt|"
    r"gegenüber|neben|hinter|an|auf|c/o)\b",
    re.I,
)

LAENDERNAMEN = {
    "deutschland": "Deutschland",
    "germany": "Deutschland",
    "de": "Deutschland",
    "österreich": "Österreich",
    "oesterreich": "Österreich",
    "austria": "Österreich",
    "at": "Österreich",
    "schweiz": "Schweiz",
    "switzerland": "Schweiz",
    "ch": "Schweiz",
}

PLZ_DE = re.compile(r"(?<!\d)(\d{5})(?!\d)")

#: Vierstellige PLZ (Oesterreich, Schweiz). Nur am Ende und nur mit einem
#: Ortsnamen dahinter: Sonst haelt "Baufeld 2024" die Jahreszahl fuer eine
#: Postleitzahl. Fuenfstellig hat immer Vorrang.
PLZ_KURZ = re.compile(
    r"(?<!\d)(\d{4})\s+([A-Za-zÀ-ɏ][\wÀ-ɏ.\-]*"
    r"(?:[ \-][A-Za-zÀ-ɏ][\wÀ-ɏ.\-]*)*)\s*$"
)

#: Hausnummer am Ende eines Straßenteils: „29", „29a", „29-31", „29/31",
#: „85 a". Nicht gierig genug, um eine PLZ zu erwischen — die ist vorher
#: schon herausgeschnitten.
HAUSNUMMER = re.compile(
    r"[\s,]+(\d{1,4}\s*[a-zA-Z]?(?:\s*[-–/]\s*\d{1,4}\s*[a-zA-Z]?)?)\s*$"
)


def _vereinfache(text: str) -> str:
    """Für Vergleiche: ohne Umlaute, ohne Satzzeichen, klein.

    „Düsseldorf" und „Duesseldorf" müssen als derselbe Ort gelten, sonst
    verwirft die Plausibilitätsprüfung einen richtigen Treffer.
    """
    text = text.lower()
    text = (
        text.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    text = unicodedata.normalize("NFKD", text)
    text = "".join(z for z in text if not unicodedata.combining(z))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _abkuerzungen_aufloesen(text: str) -> str:
    for muster, ersatz in ABKUERZUNGEN:
        text = muster.sub(ersatz, text)
    return text


@dataclass
class Adressteile:
    """Was aus der Eingabe herauszulesen war. Leere Felder heißt: stand nicht drin."""

    strasse: str = ""
    hausnummer: str = ""
    plz: str = ""
    ort: str = ""
    land: str = ""
    #: „DESYUM", „Baufeld 3" — vor der Straße, ohne Kartenbezug.
    zusatz: str = ""
    #: Die aufgeräumte Eingabe (Abkürzungen aufgelöst), für Freitextsuchen.
    freitext: str = ""

    @property
    def hausnummer_einzeln(self) -> str:
        """„29-31" → „29". Für Nummernbereiche kennt OSM nur den Anfang."""
        if not self.hausnummer:
            return ""
        return re.split(r"\s*[-–/]\s*", self.hausnummer)[0].strip()

    @property
    def strasse_mit_nummer(self) -> str:
        nummer = self.hausnummer_einzeln
        return f"{self.strasse} {nummer}".strip() if self.strasse else ""

    @property
    def ortsteil(self) -> str:
        """„20259 Hamburg" bzw. nur „Hamburg", wenn keine PLZ dastand."""
        return f"{self.plz} {self.ort}".strip()


def zerlege(adresse: str) -> Adressteile:
    """Zerlegt eine frei getippte Adresse in ihre Bestandteile.

    Bewusst regelbasiert und ohne Dienst: Das Zerlegen muss auch dann
    funktionieren, wenn gar kein Netz da ist, und es ist die Grundlage dafür,
    überhaupt gezielt suchen zu können.
    """
    roh = re.sub(r"\s+", " ", (adresse or "").strip().strip(",")).strip()
    teile = Adressteile()
    if not roh:
        return teile

    roh = _abkuerzungen_aufloesen(roh)
    teile.freitext = roh

    # Land hinten abschneiden, sonst hält es der Ortsvergleich für den Ort.
    stuecke = [s.strip() for s in roh.split(",")]
    if stuecke and _vereinfache(stuecke[-1]) in {
        _vereinfache(k) for k in LAENDERNAMEN
    }:
        teile.land = LAENDERNAMEN[_vereinfache(stuecke[-1]).replace(" ", "")]
        stuecke = stuecke[:-1]
    ohne_land = ", ".join(s for s in stuecke if s)

    # PLZ suchen und die Adresse daran auftrennen. Fünfstellig ist Deutschland;
    # vier Stellen kommen nur in Betracht, wenn ein Land dafür genannt wurde
    # oder gar keine fünfstellige Zahl dasteht — sonst wäre „Baufeld 3" mit
    # seiner „3" ein Kandidat.
    treffer = PLZ_DE.search(ohne_land)
    # "8001 Zürich" ohne Landangabe muss ebenso gehen wie mit — die Suche ist
    # ohnehin auf de/at/ch eingestellt. Fünfstellig hat Vorrang.
    kurz = None if treffer else PLZ_KURZ.search(ohne_land)

    if treffer:
        teile.plz = treffer.group(1)
        vor = ohne_land[: treffer.start()].strip().strip(",").strip()
        nach = ohne_land[treffer.end() :].strip().strip(",").strip()
        # Nach der PLZ steht der Ort; ein weiteres Komma trennt Zusätze ab.
        teile.ort = nach.split(",")[0].strip()
    elif kurz:
        # Das kurze Muster fasst PLZ *und* Ort, damit "2024" in "Baufeld 2024"
        # nicht als Postleitzahl durchgeht. Der Ort steht deshalb schon in der
        # zweiten Gruppe und nicht im Rest hinter dem Treffer.
        teile.plz, teile.ort = kurz.group(1), kurz.group(2).strip()
        vor = ohne_land[: kurz.start()].strip().strip(",").strip()
    else:
        vor, teile.ort = ohne_land, ""

    vorteile = [s.strip() for s in vor.split(",") if s.strip()]

    if not (treffer or kurz) and len(vorteile) >= 2:
        # Keine PLZ, aber mehrere Teile: der letzte ist der Ort.
        teile.ort = vorteile[-1]
        vorteile = vorteile[:-1]

    if vorteile:
        strassenteil = vorteile[-1]
        teile.zusatz = ", ".join(vorteile[:-1])
        # Ein reines Füllwort ist keine Straße („Baufeld 3, 20457 Hamburg").
        if FUELLWOERTER.match(strassenteil) and not re.search(
            r"(stra|str|weg|allee|platz|gasse|ring|damm|chaussee|ufer|steig|"
            r"pfad|kamp|deich|wall|markt|hof|brücke)", strassenteil, re.I
        ):
            teile.zusatz = ", ".join(filter(None, [teile.zusatz, strassenteil]))
            strassenteil = ""

        if strassenteil:
            nummer = HAUSNUMMER.search(strassenteil)
            if nummer:
                teile.hausnummer = re.sub(r"\s+", "", nummer.group(1))
                strassenteil = strassenteil[: nummer.start()].strip()
            teile.strasse = strassenteil.strip(" ,")

    # Nur ein Wort ohne Zahl und ohne PLZ: das ist ein Ortsname, keine Straße.
    if not teile.plz and not teile.ort and teile.strasse and not teile.hausnummer:
        if " " not in teile.strasse.strip():
            teile.ort, teile.strasse = teile.strasse, ""

    return teile


# ─────────────────────────────────────────────────────────────────────────────
# Ergebnis
# ─────────────────────────────────────────────────────────────────────────────

#: Wie genau ein Treffer ist — von der Hausnummer bis zum bloßen Ort.
GUETE_RANG = {"adresse": 3, "strasse": 2, "ort": 1, "unbekannt": 0}


@dataclass
class Standort:
    lat: float
    lon: float
    #: Was der Dienst gefunden hat, zum Gegenlesen durch den Menschen.
    label: str
    #: „adresse" | „strasse" | „ort"
    guete: str
    #: „nominatim" | „photon" | „open-meteo"
    quelle: str
    #: Gesetzt, wenn der Treffer von der Eingabe abweicht („PLZ 45289 statt
    #: 45127"). Die Oberfläche zeigt das an, statt es zu verschweigen.
    hinweis: str = ""

    def als_dict(self) -> dict:
        return {
            "lat": self.lat,
            "lon": self.lon,
            "label": self.label,
            "guete": self.guete,
            "quelle": self.quelle,
            "hinweis": self.hinweis,
        }


#: Naeher als das beieinander sind zwei Treffer fuer eine Baustelle dasselbe.
#: Nominatim liefert zu "Notkestrasse 85" fuenf Objekte - Gebaeude, Eingang,
#: Grundstueck -, die alle gleich beschriftet sind. In der Auswahlliste waeren
#: das fuenf ununterscheidbare Zeilen, zwischen denen niemand waehlen kann.
NAH_METER = 150.0


def _abstand_meter(a: "Standort", b: "Standort") -> float:
    """Entfernung zweier Punkte, flach gerechnet.

    Auf 150 m ist die Erdkruemmung ohne Belang; die Naeherung spart die
    Trigonometrie einer echten Grosskreisformel.
    """
    mittel = math.radians((a.lat + b.lat) / 2)
    dx = (a.lon - b.lon) * 111_320 * math.cos(mittel)
    dy = (a.lat - b.lat) * 110_574
    return math.hypot(dx, dy)


@dataclass
class Suchergebnis:
    """Was die Suche gefunden hat — und was sie unterwegs versucht hat."""

    teile: Adressteile
    treffer: list[Standort] = field(default_factory=list)
    #: Für die Fehlersuche und für den Text in der Oberfläche.
    versuche: list[str] = field(default_factory=list)
    #: Netz weg, Dienst aus, Zeitüberschreitung. Unterscheidet „nicht
    #: gefunden" von „konnte nicht suchen" — zwei sehr verschiedene Dinge.
    dienst_erreichbar: bool = True

    @property
    def bester(self) -> Standort | None:
        return self.treffer[0] if self.treffer else None


# ─────────────────────────────────────────────────────────────────────────────
# Die Dienste
# ─────────────────────────────────────────────────────────────────────────────

_nominatim_sperre = asyncio.Lock()
_nominatim_zuletzt = 0.0
#: So viele Treffer werden immer geholt und gemerkt, unabhängig davon, wie
#: viele der Aufrufer sehen will.
#:
#: Warum nicht einfach die gewünschte Zahl: Das Anlegen eines Projekts fragt
#: nur nach dem besten Treffer, der Knopf „Standort suchen" nach fünf. Wäre
#: das Gemerkte an der Zahl des ersten Aufrufs hängen geblieben, hätte die
#: Auswahlliste danach genau einen Eintrag gezeigt — und das ist der Weg, den
#: jeder geht: anlegen, Ergebnis ansehen, nachbessern wollen.
TREFFER_MAX = 5

#: Adresse (vereinfacht) → Ergebnis. Ein Projekt wird beim Anlegen, beim
#: Ändern und beim Prüfen befragt; dreimal dasselbe zu fragen wäre gegenüber
#: einem kostenlosen Dienst unhöflich.
_zwischenspeicher: dict[str, Suchergebnis] = {}

#: Obergrenze des Zwischenspeichers. Er lebt so lange wie der Serverprozess;
#: ohne Deckel wüchse er mit jeder je gesuchten Adresse weiter.
ZWISCHENSPEICHER_MAX = 500


def _kopfzeilen() -> dict[str, str]:
    return {"User-Agent": settings.nominatim_user_agent, "Accept-Language": "de"}


async def _hole(
    client: httpx.AsyncClient, url: str, params: dict, *, bremsen: bool
) -> tuple[object | None, bool]:
    """Eine Abfrage, mit Nominatim-Bremse und einem Wiederholungsversuch.

    429/503 heißt „gerade zu viel" und nicht „gibt es nicht" — einmal
    nachfassen lohnt. Alles andere wird still übergangen, damit das Anlegen
    eines Projekts nie an einem fremden Dienst scheitert.

    Zurück kommt zusätzlich, ob der Dienst überhaupt **geantwortet** hat. Der
    Unterschied ist für den Menschen davor der ganze Punkt: „Adresse nicht
    gefunden" heißt „nochmal nachsehen", „Dienst nicht erreichbar" heißt
    „liegt nicht an dir" — im Büronetz hinter einem Proxy sieht sonst jede
    richtige Adresse aus wie ein Tippfehler.
    """
    global _nominatim_zuletzt
    for versuch in range(VERSUCHE):
        if bremsen:
            async with _nominatim_sperre:
                pause = NOMINATIM_ABSTAND - (time.monotonic() - _nominatim_zuletzt)
                if pause > 0:
                    await asyncio.sleep(pause)
                _nominatim_zuletzt = time.monotonic()
        try:
            antwort = await client.get(url, params=params, headers=_kopfzeilen())
        except Exception:
            # Zeitueberschreitung, abgebrochene Verbindung, DNS-Zucken. Genau
            # hier ging in der Praxis eine einzelne Stufe verloren, obwohl der
            # Dienst eine Sekunde spaeter wieder antwortete - und das sah in
            # der App aus wie "Adresse nicht gefunden".
            if versuch + 1 < VERSUCHE:
                await asyncio.sleep(0.8)
                continue
            return None, False
        if antwort.status_code in (429, 503) and versuch + 1 < VERSUCHE:
            await asyncio.sleep(1.5)
            continue
        if antwort.status_code != 200:
            # 403 (gesperrter User-Agent) oder 5xx: der Dienst ist da, aber
            # nicht nutzbar. Auch das ist nicht „nicht gefunden".
            return None, False
        try:
            return antwort.json(), True
        except Exception:
            return None, True
    return None, False


def _gleiche_strasse(getippt: str, gefunden: str) -> bool:
    """„Hauptstraße" und „Alte Hauptstraße" sind dieselbe Straße, „Musterweg"
    und „Paul-Nevermann-Platz" nicht. Enthält der eine Name den anderen, gilt
    es als Treffer — Zusätze wie „Alte", „Große" oder „Am" sind üblich."""
    a, b = _vereinfache(getippt), _vereinfache(gefunden)
    return bool(a and b and (a in b or b in a))


def _bewerte(
    teile: Adressteile,
    *,
    gefunden_plz: str,
    gefunden_ort: str,
    gefunden_strasse: str,
    hat_hausnummer: bool,
) -> tuple[str, str] | None:
    """Güte und Hinweis eines Treffers — oder ``None``, wenn er verworfen wird.

    Verworfen wird nur, was der Eingabe **doppelt** widerspricht: andere PLZ
    *und* anderer Ort. Das trifft die Ausreißer der toleranten Suche (eine
    „20259" wird sonst zu einem Dorf im Baskenland) und lässt den harmlosen
    Fall durch, dass ein Nachbar-Stadtteil eine andere PLZ hat.

    Die Güte kann nie feiner sein als die Eingabe: Wer keine Straße getippt
    hat, bekommt höchstens „ort", auch wenn der Dienst zufällig ein Haus in
    der PLZ zurückgibt. Sonst stünde in der Oberfläche „hausnummergenau" über
    einem Punkt, den niemand so angegeben hat.
    """
    plz_widerspruch = bool(
        teile.plz and gefunden_plz and teile.plz != gefunden_plz
    )
    ort_bekannt = bool(teile.ort and gefunden_ort)
    ort_widerspruch = bool(
        ort_bekannt
        and _vereinfache(teile.ort) not in _vereinfache(gefunden_ort)
        and _vereinfache(gefunden_ort) not in _vereinfache(teile.ort)
    )

    if plz_widerspruch and (ort_widerspruch or not ort_bekannt):
        return None
    if ort_widerspruch and not teile.plz:
        return None

    hinweise = []
    strasse_verfehlt = bool(
        teile.strasse
        and gefunden_strasse
        and not _gleiche_strasse(teile.strasse, gefunden_strasse)
    )

    if not teile.strasse:
        guete = "ort"
    elif strasse_verfehlt:
        guete = "ort"
        hinweise.append(f"„{teile.strasse}“ nicht gefunden")
    elif hat_hausnummer and teile.hausnummer:
        guete = "adresse"
    elif gefunden_strasse:
        guete = "strasse"
    else:
        guete = "ort"

    if plz_widerspruch:
        hinweise.append(f"gefundene PLZ {gefunden_plz} statt {teile.plz}")
    if ort_widerspruch:
        hinweise.append(f"gefundener Ort „{gefunden_ort}“")
    return guete, "; ".join(hinweise)


async def _nominatim(
    client: httpx.AsyncClient, teile: Adressteile, params: dict, grenze: int
) -> tuple[list[Standort], bool]:
    voll = {
        **params,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": grenze,
        "countrycodes": LAENDER,
    }
    daten, erreichbar = await _hole(client, NOMINATIM_URL, voll, bremsen=True)
    if not isinstance(daten, list):
        return [], erreichbar

    ergebnis: list[Standort] = []
    for eintrag in daten:
        adresse = eintrag.get("address") or {}
        ort = (
            adresse.get("city")
            or adresse.get("town")
            or adresse.get("village")
            or adresse.get("municipality")
            or adresse.get("suburb")
            or ""
        )
        bewertung = _bewerte(
            teile,
            gefunden_plz=str(adresse.get("postcode") or "").strip(),
            gefunden_ort=str(ort),
            gefunden_strasse=str(adresse.get("road") or "").strip(),
            hat_hausnummer=bool(adresse.get("house_number")),
        )
        if bewertung is None:
            continue
        guete, hinweis = bewertung
        try:
            ergebnis.append(
                Standort(
                    lat=float(eintrag["lat"]),
                    lon=float(eintrag["lon"]),
                    label=str(eintrag.get("display_name") or "").strip(),
                    guete=guete,
                    quelle="nominatim",
                    hinweis=hinweis,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return ergebnis, erreichbar


async def _photon(
    client: httpx.AsyncClient, teile: Adressteile, frage: str, grenze: int
) -> tuple[list[Standort], bool]:
    daten, erreichbar = await _hole(
        client,
        PHOTON_URL,
        {"q": frage, "limit": grenze, "lang": "de"},
        bremsen=False,
    )
    if not isinstance(daten, dict):
        return [], erreichbar

    ergebnis: list[Standort] = []
    for merkmal in daten.get("features") or []:
        koordinaten = (merkmal.get("geometry") or {}).get("coordinates") or []
        eigenschaften = merkmal.get("properties") or {}
        if len(koordinaten) < 2:
            continue
        if eigenschaften.get("countrycode", "DE").lower() not in ("de", "at", "ch"):
            continue
        bewertung = _bewerte(
            teile,
            gefunden_plz=str(eigenschaften.get("postcode") or "").strip(),
            gefunden_ort=str(
                eigenschaften.get("city")
                or eigenschaften.get("town")
                or eigenschaften.get("village")
                or eigenschaften.get("district")
                or ""
            ),
            gefunden_strasse=str(eigenschaften.get("street") or "").strip(),
            hat_hausnummer=bool(eigenschaften.get("housenumber")),
        )
        if bewertung is None:
            continue
        guete, hinweis = bewertung
        beschriftung = ", ".join(
            str(t)
            for t in (
                " ".join(
                    filter(
                        None,
                        [
                            eigenschaften.get("street") or eigenschaften.get("name"),
                            eigenschaften.get("housenumber"),
                        ],
                    )
                ),
                " ".join(
                    filter(
                        None,
                        [eigenschaften.get("postcode"), eigenschaften.get("city")],
                    )
                ),
                eigenschaften.get("state"),
            )
            if t
        )
        try:
            ergebnis.append(
                Standort(
                    lat=float(koordinaten[1]),
                    lon=float(koordinaten[0]),
                    label=beschriftung,
                    guete=guete,
                    quelle="photon",
                    hinweis=hinweis,
                )
            )
        except (TypeError, ValueError):
            continue
    return ergebnis, erreichbar


async def _open_meteo(
    client: httpx.AsyncClient, teile: Adressteile, grenze: int
) -> tuple[list[Standort], bool]:
    """Letzte Ebene: reiner Ortsname.

    **Nur** mit einem Ortsnamen aufrufen. Mit einer PLZ befragt liefert der
    Dienst Orte in aller Welt („20259" → Baliarrain, Baskenland).
    """
    if not teile.ort or any(z.isdigit() for z in teile.ort):
        return [], True
    daten, erreichbar = await _hole(
        client,
        OPEN_METEO_URL,
        {"name": teile.ort, "count": grenze, "language": "de"},
        bremsen=False,
    )
    if not isinstance(daten, dict):
        return [], erreichbar

    ergebnis: list[Standort] = []
    for eintrag in daten.get("results") or []:
        if str(eintrag.get("country_code") or "").lower() not in ("de", "at", "ch"):
            continue
        beschriftung = ", ".join(
            str(t)
            for t in (eintrag.get("name"), eintrag.get("admin1"), eintrag.get("country"))
            if t
        )
        try:
            ergebnis.append(
                Standort(
                    lat=float(eintrag["latitude"]),
                    lon=float(eintrag["longitude"]),
                    label=beschriftung,
                    guete="ort",
                    quelle="open-meteo",
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return ergebnis, erreichbar


# ─────────────────────────────────────────────────────────────────────────────
# Die Leiter
# ─────────────────────────────────────────────────────────────────────────────


def _ziel_guete(teile: Adressteile) -> str:
    """Wie genau ein Treffer für **diese** Eingabe überhaupt werden kann.

    Wer nur „20259 Hamburg" eingibt, kann keinen hausnummergenauen Treffer
    bekommen — und dann darf die Suche auch nicht weiter die Leiter
    hinabsteigen, sobald der Ort gefunden ist. Ohne dieses Ziel liefe für eine
    reine PLZ die ganze Kette durch, mit sieben Abfragen bei fremden Diensten
    für ein Ergebnis, das nach der ersten feststand.
    """
    if teile.strasse and teile.hausnummer:
        return "adresse"
    if teile.strasse:
        return "strasse"
    return "ort"


def _stufen(teile: Adressteile) -> list[tuple[str, object]]:
    """Die Suchleiter für diese Adresse — von genau nach grob.

    Ohne Straße in der Eingabe fallen alle Straßenstufen weg. Das ist nicht
    nur schneller: Photon liefert auf „20259 Hamburg" irgendein Haus in dieser
    PLZ, und das sähe in der Oberfläche nach einem Treffer aus, den niemand
    gesucht hat.
    """
    land = teile.land or "Deutschland"
    stufen: list[tuple[str, object]] = []

    if teile.strasse:
        if teile.hausnummer:
            stufen.append(
                (
                    f"Nominatim strukturiert: {teile.strasse_mit_nummer}, "
                    f"{teile.ortsteil}",
                    {
                        "street": teile.strasse_mit_nummer,
                        "postalcode": teile.plz,
                        "city": teile.ort,
                        "country": land,
                    },
                )
            )
        stufen.append(
            (
                f"Nominatim strukturiert ohne Hausnummer: {teile.strasse}, "
                f"{teile.ortsteil}",
                {
                    "street": teile.strasse,
                    "postalcode": teile.plz,
                    "city": teile.ort,
                    "country": land,
                },
            )
        )
        # Photon: die tolerante Ebene. Bekommt den vollen Text mitsamt Zusatz,
        # weil „DESYUM" dort ein Treffer und kein Störfeuer ist.
        stufen.append((f"Photon: {teile.freitext}", ("photon", teile.freitext)))
        gekuerzt = ", ".join(
            t for t in (teile.strasse_mit_nummer, teile.ortsteil) if t
        )
        if _vereinfache(gekuerzt) != _vereinfache(teile.freitext):
            stufen.append((f"Photon ohne Zusatz: {gekuerzt}", ("photon", gekuerzt)))
            stufen.append((f"Nominatim Freitext: {gekuerzt}", {"q": gekuerzt}))

    if teile.plz or teile.ort:
        stufen.append(
            (
                f"Nominatim nur Ort: {teile.ortsteil}",
                {"postalcode": teile.plz, "city": teile.ort, "country": land},
            )
        )
    if teile.ort:
        stufen.append((f"Photon nur Ort: {teile.ortsteil}", ("photon", teile.ortsteil)))
        stufen.append((f"Open-Meteo nur Ortsname: {teile.ort}", ("open-meteo", "")))
    elif teile.plz:
        # Nur eine PLZ und sonst nichts: Open-Meteo scheidet aus, das kennt
        # keine Postleitzahlen und liefert Orte in aller Welt.
        stufen.append((f"Photon nur PLZ: {teile.plz}", ("photon", teile.plz)))
    return stufen


def _gekuerzt(ergebnis: Suchergebnis, grenze: int) -> Suchergebnis:
    """Eine Sicht mit höchstens ``grenze`` Treffern.

    Als Kopie, damit ein Aufrufer nicht den gemerkten Stand beschneidet.
    """
    if len(ergebnis.treffer) <= grenze:
        return ergebnis
    return replace(ergebnis, treffer=ergebnis.treffer[:grenze])


async def suche_standort(adresse: str, *, grenze: int = TREFFER_MAX) -> Suchergebnis:
    """Sucht Koordinaten zu einer Adresse — von genau nach grob.

    Bricht ab, sobald eine Stufe die für diese Eingabe bestmögliche Güte ohne
    Abweichung liefert. Sonst wird weitergesucht und am Ende das Beste
    genommen, was zusammenkam.
    """
    teile = zerlege(adresse)
    if not teile.freitext:
        return Suchergebnis(teile=teile)

    schluessel = _vereinfache(teile.freitext)
    gemerkt = _zwischenspeicher.get(schluessel)
    if gemerkt is not None:
        return _gekuerzt(gemerkt, grenze)

    ergebnis = Suchergebnis(teile=teile)
    ziel = GUETE_RANG[_ziel_guete(teile)]
    erreichbar = False
    schluss = time.monotonic() + GESAMTFRIST

    async with httpx.AsyncClient(timeout=ZEITLIMIT, follow_redirects=True) as client:
        for beschreibung, auftrag in _stufen(teile):

            if time.monotonic() > schluss:
                ergebnis.versuche.append(
                    "Abbruch nach "
                    f"{GESAMTFRIST:.0f} s - die restlichen Stufen entfielen"
                )
                break
            if isinstance(auftrag, tuple) and auftrag[0] == "photon":
                gefunden, geantwortet = await _photon(
                    client, teile, str(auftrag[1]), TREFFER_MAX
                )
            elif isinstance(auftrag, tuple) and auftrag[0] == "open-meteo":
                gefunden, geantwortet = await _open_meteo(
                    client, teile, TREFFER_MAX
                )
            else:
                # Leere Felder weglassen — Nominatim liefert sonst nichts.
                sauber = {
                    k: v for k, v in dict(auftrag).items() if str(v or "").strip()
                }
                gefunden, geantwortet = (
                    await _nominatim(client, teile, sauber, TREFFER_MAX)
                    if sauber
                    else ([], True)
                )

            erreichbar = erreichbar or geantwortet
            ergebnis.versuche.append(
                f"{beschreibung} → "
                + (f"{len(gefunden)} Treffer" if geantwortet else "keine Antwort")
            )
            for standort in gefunden:
                # Dubletten weglassen: gleicher Text oder praktisch gleicher
                # Punkt. Sonst steht dieselbe Adresse fuenfmal zur Wahl.
                doppelt = any(
                    _vereinfache(v.label) == _vereinfache(standort.label)
                    or _abstand_meter(v, standort) < NAH_METER
                    for v in ergebnis.treffer
                )
                if not doppelt:
                    ergebnis.treffer.append(standort)

            if any(
                GUETE_RANG.get(s.guete, 0) >= ziel and not s.hinweis for s in gefunden
            ):
                break

    ergebnis.dienst_erreichbar = erreichbar or bool(ergebnis.treffer)
    # Das Genaueste zuerst; bei gleicher Güte die Treffer ohne Abweichung.
    ergebnis.treffer.sort(
        key=lambda s: (-GUETE_RANG.get(s.guete, 0), bool(s.hinweis))
    )
    del ergebnis.treffer[TREFFER_MAX:]
    # Eine Störung nicht merken: Sonst bliebe der Standort für die ganze
    # Laufzeit des Servers leer, obwohl das Netz längst wieder da ist.
    if ergebnis.dienst_erreichbar:
        if len(_zwischenspeicher) >= ZWISCHENSPEICHER_MAX:
            # Der älteste Eintrag geht; Python behält die Einfügereihenfolge.
            del _zwischenspeicher[next(iter(_zwischenspeicher))]
        _zwischenspeicher[schluessel] = ergebnis
    return _gekuerzt(ergebnis, grenze)


def leere_zwischenspeicher() -> None:
    """Nur für Tests — sonst hängt ein Ergebnis über die Testgrenze hinaus."""
    _zwischenspeicher.clear()
