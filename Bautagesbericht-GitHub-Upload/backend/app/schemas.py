from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class ProjektCreate(BaseModel):
    name: str
    adresse: str = ""
    teams_webhook_url: str = ""
    #: Zielordner der Baufotos im Netzlaufwerk, z. B.
    #: "L:\\Bauleitung-Hamburg\\K30159 Kita Nord\\01 FOTOS".
    #: Leer = der abholende Rechner bildet den Pfad nach seiner Standardregel.
    foto_zielpfad: str = ""
    #: Koordinaten von Hand oder aus einem ausgewaehlten Suchtreffer. Sind sie
    #: gesetzt, wird die Adresse NICHT nachgeschlagen: Der Mensch hat schon
    #: entschieden, und ein fremder Dienst darf das nicht ueberstimmen.
    lat: float | None = None
    lon: float | None = None


class ProjektUpdate(BaseModel):
    """Nachtraegliche Aenderung. Nicht gesetzte Felder bleiben, wie sie sind."""

    name: str | None = None
    adresse: str | None = None
    teams_webhook_url: str | None = None
    foto_zielpfad: str | None = None
    #: Standort von Hand setzen, siehe ProjektCreate.
    lat: float | None = None
    lon: float | None = None
    #: Adresse erneut nachschlagen, ohne sie zu aendern - fuer den Knopf
    #: "Standort neu suchen" auf der Projektkarte. Vorher gab es dafuer keinen
    #: Weg: Wer eine richtige Adresse eingetippt hatte und "ohne Standort"
    #: sah, konnte nichts weiter tun.
    standort_neu_suchen: bool = False
    #: Standort loeschen. Braucht ein eigenes Feld, weil "lat": null in einem
    #: PATCH nicht von "lat nicht mitgeschickt" zu unterscheiden ist - und ein
    #: von Hand falsch gesetzter Punkt muss wieder wegkoennen.
    standort_entfernen: bool = False


class ProjektResponse(BaseModel):
    id: int
    name: str
    adresse: str
    lat: float | None
    lon: float | None
    teams_webhook_url: str = ""
    foto_zielpfad: str = ""
    #: "adresse" | "strasse" | "ort" | "manuell" | "" (vor der Umstellung).
    standort_guete: str = ""
    standort_label: str = ""
    erstellt_am: datetime

    model_config = {"from_attributes": True}


class StandortTreffer(BaseModel):
    """Ein Kandidat der Standortsuche, zur Auswahl durch den Menschen."""

    lat: float
    lon: float
    #: Klartext des Treffers, zum Gegenlesen.
    label: str
    #: "adresse" | "strasse" | "ort"
    guete: str
    #: "nominatim" | "photon" | "open-meteo"
    quelle: str
    #: Gesetzt, wenn der Treffer von der Eingabe abweicht.
    hinweis: str = ""


class StandortSucheAntwort(BaseModel):
    """Was die Suche zu einer Adresse gefunden hat.

    ``dienst_erreichbar=False`` heisst "konnte nicht suchen" und nicht "nicht
    gefunden". Der Oberflaeche sahen beide Faelle bisher gleich aus, obwohl
    sie den Nutzer zu zwei verschiedenen Dingen veranlassen muessen.
    """

    adresse: str
    treffer: list[StandortTreffer] = []
    dienst_erreichbar: bool = True
    #: Wie die Eingabe verstanden wurde. Zeigt sofort, wenn etwa der Ort im
    #: Feld "Strasse" gelandet ist.
    erkannt: dict[str, str] = {}
    #: Welche Suchstufen gelaufen sind, fuer den Aufklapper "Details".
    versuche: list[str] = []


class EmpfaengerCreate(BaseModel):
    label: str
    email: EmailStr
    teams_webhook_url: str = ""


class EmpfaengerResponse(BaseModel):
    id: int
    label: str
    email: str
    teams_webhook_url: str = ""
    erstellt_am: datetime

    model_config = {"from_attributes": True}


class EinreichungResponse(BaseModel):
    id: int
    projekt_id: int
    projekt_name: str = ""
    empfaenger_id: int
    empfaenger_label: str = ""
    empfaenger_email: str = ""
    datum: date
    ergaenzende_angaben: str | None
    status: str
    quelle_dateien: list[str]
    warnungen: list[dict]
    eingereicht_am: datetime
    verarbeitet_am: datetime | None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Wochenpaket: einmal hochladen, fuenf Tagesberichte heraus
# ─────────────────────────────────────────────────────────────────────────────


class WochenQuelle(BaseModel):
    """Eine hochgeladene Datei und die Seiten, die zu einem Tag gehoeren."""

    #: Nur der Dateiname innerhalb des Wochenpakets, nie ein Pfad.
    datei: str
    #: 1-basiert wie im PDF-Betrachter. Leer = die ganze Datei.
    seiten: list[int] = []


class WochenTag(BaseModel):
    """Ein Tag des Pakets, so wie er erkannt wurde."""

    datum: date | None = None
    quellen: list[WochenQuelle] = []
    anzahl_seiten: int = 0
    #: Text, der zusaetzlich in den Bericht dieses Tages soll.
    ergaenzende_angaben: str = ""


class WochenAnalyse(BaseModel):
    """Was im hochgeladenen Paket steckt — noch ohne etwas anzulegen."""

    #: Kennung der Zwischenablage; gehoert in den zweiten Aufruf.
    kennung: str
    dateien: list[str] = []
    #: Tage mit erkanntem Datum, aufsteigend.
    tage: list[WochenTag] = []
    #: Seiten, denen kein Tag zugeordnet werden konnte.
    ohne_datum: WochenTag | None = None
    #: Klartexthinweise fuer die Oberflaeche.
    hinweise: list[str] = []


class WochenEinreichung(BaseModel):
    """Der zweite Schritt: aus den bestaetigten Tagen Berichte machen."""

    kennung: str
    projekt_id: int
    empfaenger_id: int
    tage: list[WochenTag] = []


class WochenErgebnis(BaseModel):
    einreichungen: list[EinreichungResponse] = []
    hinweise: list[str] = []


class VerarbeitungsLogResponse(BaseModel):
    id: int
    einreichung_id: int
    schritt: str
    ergebnis: str
    details: str | None
    dauer_ms: int | None
    erstellt_am: datetime

    model_config = {"from_attributes": True}


class WarnungSchema(BaseModel):
    feld: str
    problem: str
    quelle_datei: str = ""
    #: Hält den Bericht auf, bis jemand bestätigt. False = nur ein Hinweis;
    #: das Dokument entsteht trotzdem (siehe services/pipeline._haelt_auf).
    blockiert: bool = True


class FirmaEintrag(BaseModel):
    firma: str
    ort: str = ""
    personen: int = 0
    leistung: str = ""
    besonderes: str | None = None


class WetterStundenwert(BaseModel):
    stunde: int
    temperatur_c: float | None = None
    niederschlag_mm: float | None = None
    wind_ms: float | None = None
    wind_grad: int | None = None
    bewoelkung_prozent: int | None = None
    icon: str | None = None


class WetterBlock(BaseModel):
    station: str = ""
    temp_max_c: float | None = None
    temp_min_c: float | None = None
    regen_mm: float | None = None
    wind_max_ms: float | None = None
    schnee_cm: float | None = None
    stundenwerte: list[WetterStundenwert] = []


class BautagesberichtJSON(BaseModel):
    projekt: str
    datum: date
    haupteintrag: str | None = None
    wetter: WetterBlock | None = None
    firmen: list[FirmaEintrag] = []
    unterschrift_datum: date | None = None
    warnungen: list[WarnungSchema] = []


# ─────────────────────────────────────────────────────────────────────────────
# Mängelmanagement
#
# Die erlaubten Werte der kleinen Auswahlfelder stehen hier als Literal —
# in der Datenbank sind es Strings, damit auf Postgres kein ALTER TYPE nötig
# ist (siehe Kommentar in app.models).
# ─────────────────────────────────────────────────────────────────────────────

Prioritaet = Literal["hoch", "mittel", "niedrig"]
Versendemodus = Literal["manuell", "automatisch"]


def _leer_zu_none(value):
    """Leere Formularfelder als "nicht gesetzt" behandeln.

    Das Frontend schickt für ein leeres Feld "" statt null; für E-Mail- und
    Datumsfelder wäre "" ein Validierungsfehler.
    """
    if isinstance(value, str) and not value.strip():
        return None
    return value


# ───────── Stammdaten: Wertelisten ─────────


class MangelTypCreate(BaseModel):
    bezeichnung: str
    sortierung: int = 0


class MangelTypResponse(BaseModel):
    id: int
    bezeichnung: str
    sortierung: int

    model_config = {"from_attributes": True}


class MangelStatusCreate(BaseModel):
    bezeichnung: str
    sortierung: int = 0
    farbe: str = "#6B7280"
    ist_abgeschlossen: bool = False


class MangelStatusResponse(BaseModel):
    id: int
    bezeichnung: str
    sortierung: int
    farbe: str
    ist_abgeschlossen: bool

    model_config = {"from_attributes": True}


class MangelRueckmeldungStatusCreate(BaseModel):
    bezeichnung: str
    sortierung: int = 0


class MangelRueckmeldungStatusResponse(BaseModel):
    id: int
    bezeichnung: str
    sortierung: int

    model_config = {"from_attributes": True}


class BearbeiterCreate(BaseModel):
    name: str
    email: EmailStr | None = None
    # Kopfzeile des Besprechungsprotokolls: "Ze: kbl  T - 22".
    kuerzel: str = ""
    durchwahl: str = ""

    _norm_email = field_validator("email", mode="before")(_leer_zu_none)


class BearbeiterUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    kuerzel: str | None = None
    durchwahl: str | None = None

    _norm_email = field_validator("email", mode="before")(_leer_zu_none)


class BearbeiterResponse(BaseModel):
    id: int
    name: str
    email: str | None
    kuerzel: str = ""
    durchwahl: str = ""

    model_config = {"from_attributes": True}


# ───────── Gewerk (zuständige Firma / Büro) ─────────


class GewerkCreate(BaseModel):
    projekt_id: int
    firma_name: str
    vergabeeinheit_code: str = ""
    vergabeeinheit_bezeichnung: str = ""
    email: EmailStr | None = None
    # Postanschrift fuer die Maengelanzeige - optional, weil sie fuer Teams
    # und Fristenverwaltung nicht gebraucht wird.
    ansprechpartner: str = ""
    strasse: str = ""
    plz: str = ""
    ort: str = ""
    teams_webhook_url: str = ""

    _norm_email = field_validator("email", mode="before")(_leer_zu_none)


class GewerkUpdate(BaseModel):
    firma_name: str | None = None
    vergabeeinheit_code: str | None = None
    vergabeeinheit_bezeichnung: str | None = None
    email: EmailStr | None = None
    ansprechpartner: str | None = None
    strasse: str | None = None
    plz: str | None = None
    ort: str | None = None
    teams_webhook_url: str | None = None

    _norm_email = field_validator("email", mode="before")(_leer_zu_none)


class GewerkResponse(BaseModel):
    id: int
    projekt_id: int
    firma_name: str
    vergabeeinheit_code: str
    vergabeeinheit_bezeichnung: str
    email: str | None
    ansprechpartner: str = ""
    strasse: str = ""
    plz: str = ""
    ort: str = ""
    teams_webhook_url: str
    erstellt_am: datetime
    # Zusammengesetzte Anzeige wie im Formular:
    # "Rolfes Bau GmbH | VE300-01 Erweiterter Rohbau"
    anzeige_name: str = ""

    model_config = {"from_attributes": True}


# ───────── Pläne und Markierungen ─────────


class ProjektPlanResponse(BaseModel):
    id: int
    projekt_id: int
    dateiname: str
    seiten: int
    hochgeladen_am: datetime

    model_config = {"from_attributes": True}


class MangelPlanMarkierungCreate(BaseModel):
    plan_datei_id: int
    x_prozent: float
    y_prozent: float
    seite: int = 1

    @field_validator("x_prozent", "y_prozent")
    @classmethod
    def _im_bild(cls, v: float) -> float:
        if not 0 <= v <= 100:
            raise ValueError("Position muss zwischen 0 und 100 Prozent liegen")
        return v


class MangelPlanMarkierungResponse(BaseModel):
    id: int
    mangel_id: int
    plan_datei_id: int
    plan_dateiname: str = ""
    x_prozent: float
    y_prozent: float
    seite: int

    model_config = {"from_attributes": True}


# ───────── Fotos und Dateien ─────────


class MangelFotoResponse(BaseModel):
    id: int
    mangel_id: int
    bildunterschrift: str
    reihenfolge: int
    aufgenommen_am: datetime | None

    model_config = {"from_attributes": True}


class MangelFotoUpdate(BaseModel):
    bildunterschrift: str | None = None
    reihenfolge: int | None = None


class MangelDateiResponse(BaseModel):
    id: int
    mangel_id: int
    dateiname: str
    hochgeladen_am: datetime | None

    model_config = {"from_attributes": True}


# ───────── Mangel ─────────


class MangelCreate(BaseModel):
    projekt_id: int
    kurzbezeichnung: str
    typ: str = "Mangel"
    status: str = "offen"
    gewerk_id: int | None = None
    raumnummer: str | None = None
    hinweis_ort: str = ""
    prioritaet: Prioritaet = "mittel"
    beschreibung: str = ""
    farbmarkierung: str = ""
    interne_bemerkung: str = ""
    erstellt_am: date | None = None
    erste_frist_bis: date | None = None
    aufgenommen_von: str = "HPP Architekten GmbH"
    zustaendiger_user_id: int | None = None
    rueckmeldung_status: str = ""
    mail_autosend: bool = False
    mail_versendemodus: Versendemodus = "manuell"
    # Nummer wird normalerweise fortlaufend vergeben; ein expliziter Wert
    # erlaubt das Übernehmen bestehender Nummernkreise.
    nummer: str | None = None

    _norm_datum = field_validator(
        "erstellt_am", "erste_frist_bis", mode="before"
    )(_leer_zu_none)


class MangelUpdate(BaseModel):
    """Teil-Aktualisierung — nur mitgesendete Felder werden geschrieben."""

    nummer: str | None = None
    typ: str | None = None
    status: str | None = None
    gewerk_id: int | None = None
    raumnummer: str | None = None
    hinweis_ort: str | None = None
    prioritaet: Prioritaet | None = None
    kurzbezeichnung: str | None = None
    beschreibung: str | None = None
    farbmarkierung: str | None = None
    interne_bemerkung: str | None = None
    erstellt_am: date | None = None
    erste_frist_bis: date | None = None
    aufgenommen_von: str | None = None
    zustaendiger_user_id: int | None = None
    erste_nachfrist_gesetzt_am: date | None = None
    erste_nachfrist_bis: date | None = None
    anmerkung_nachfrist: str | None = None
    beseitigungsanzeige_am: date | None = None
    freigemeldet_am: date | None = None
    erledigt_am: date | None = None
    zurueckweisung_am: date | None = None
    rueckmeldung_status: str | None = None
    mail_autosend: bool | None = None
    mail_versendemodus: Versendemodus | None = None

    _norm_datum = field_validator(
        "erstellt_am",
        "erste_frist_bis",
        "erste_nachfrist_gesetzt_am",
        "erste_nachfrist_bis",
        "beseitigungsanzeige_am",
        "freigemeldet_am",
        "erledigt_am",
        "zurueckweisung_am",
        mode="before",
    )(_leer_zu_none)


class MangelListItem(BaseModel):
    """Eine Zeile der Mängel-Übersicht."""

    id: int
    projekt_id: int
    projekt_name: str = ""
    nummer: str
    typ: str
    status: str
    status_farbe: str = ""
    gewerk_id: int | None
    gewerk_anzeige: str = ""
    firma_name: str = ""
    raumnummer: str | None
    hinweis_ort: str
    prioritaet: str
    kurzbezeichnung: str
    farbmarkierung: str
    erstellt_am: date
    erste_frist_bis: date | None
    # Nachfrist schlägt die erste Frist — das ist die Frist, die zählt.
    aktuelle_frist: date | None = None
    ist_ueberfaellig: bool = False
    ist_abgeschlossen: bool = False
    anzahl_fotos: int = 0
    titel_foto_id: int | None = None
    eltern_mangel_id: int | None = None
    anzahl_duplikate: int = 0

    model_config = {"from_attributes": True}


class MangelResponse(MangelListItem):
    """Detailansicht eines Mangels."""

    beschreibung: str
    interne_bemerkung: str
    aufgenommen_von: str
    zustaendiger_user_id: int | None
    zustaendiger_user_name: str = ""
    erste_nachfrist_gesetzt_am: date | None
    erste_nachfrist_bis: date | None
    anmerkung_nachfrist: str
    beseitigungsanzeige_am: date | None
    freigemeldet_am: date | None
    erledigt_am: date | None
    zurueckweisung_am: date | None
    rueckmeldung_status: str
    mail_autosend: bool
    mail_versendemodus: str
    zuletzt_versendet_am: date | None
    angelegt_am: datetime | None
    # "Ist Kopie von: 00012 Stahlbeton"
    eltern_nummer: str = ""
    eltern_kurzbezeichnung: str = ""
    # Gefüllt, wenn Autosend gewünscht ist, die Firma aber keine E-Mail hat
    # ("Fehler! Firma/Büro hat keine Email-Adresse").
    mail_fehler: str | None = None
    fotos: list[MangelFotoResponse] = []
    dateien: list[MangelDateiResponse] = []
    markierung: MangelPlanMarkierungResponse | None = None


class MangelVersandErgebnis(BaseModel):
    """Ergebnis von "Jetzt senden"."""

    mangel_id: int
    versendet: bool
    kanal: str
    nachricht: str
    zuletzt_versendet_am: date | None = None


# ───────── Export (Mängelliste als Word-Dokument) ─────────


class MangelExportEintrag(BaseModel):
    """Ein Mangel, wie er im Word-Dokument erscheint.

    Bewusst ein eigenes DTO und nicht das ORM-Objekt: Die interne Bemerkung
    ("für Firmen nicht sichtbar") ist hier nur dann überhaupt gefüllt, wenn
    der Export ausdrücklich als interner Export angefordert wurde. Damit kann
    die Dokumenterzeugung das Feld nicht versehentlich ausgeben.
    """

    nummer: str
    kurzbezeichnung: str
    typ: str = ""
    status: str = ""
    prioritaet: str = ""
    firma: str = ""
    ort: str = ""
    raumnummer: str = ""
    beschreibung: str = ""
    erstellt_am: date | None = None
    frist_bis: date | None = None
    nachfrist_bis: date | None = None
    erledigt_am: date | None = None
    rueckmeldung_status: str = ""
    ist_ueberfaellig: bool = False
    plan_markierung: str = ""
    # Absolute Pfade der einzubettenden Fotos (leer = kein Foto).
    foto_pfade: list[str] = []
    # Nur bei internem Export gefüllt, sonst immer "".
    interne_bemerkung: str = ""


class MaengellisteJSON(BaseModel):
    projekt: str
    stand: date
    filter_beschreibung: str = ""
    # True = interner Export inklusive interner Bemerkungen. False = Fassung
    # für die Firma.
    intern: bool = False
    maengel: list[MangelExportEintrag] = []


class MangelStammdaten(BaseModel):
    """Alle Wertelisten des Mängelmoduls in einer Antwort.

    Die Oberfläche braucht sie beim Öffnen des Moduls gemeinsam — ein Aufruf
    statt vier ist auf einer Baustellenverbindung ein merkbarer Unterschied.
    """

    typen: list[MangelTypResponse] = []
    status: list[MangelStatusResponse] = []
    rueckmeldung_status: list[MangelRueckmeldungStatusResponse] = []
    bearbeiter: list[BearbeiterResponse] = []
    prioritaeten: list[str] = ["hoch", "mittel", "niedrig"]
    versendemodi: list[str] = ["manuell", "automatisch"]


# ─────────────────────────────────────────────────────────────────────────────
# Baufotos
# ─────────────────────────────────────────────────────────────────────────────


class BaufotoResponse(BaseModel):
    id: int
    fotosatz_id: int
    # Der umbenannte Name — genau so heißt die Datei später im Projektordner.
    dateiname: str
    original_dateiname: str
    reihenfolge: int
    groesse_bytes: int
    hochgeladen_am: datetime | None

    model_config = {"from_attributes": True}


class FotosatzCreate(BaseModel):
    projekt_id: int
    kategorie: str
    datum: date | None = None
    notiz: str = ""

    _norm_datum = field_validator("datum", mode="before")(_leer_zu_none)


class FotosatzUpdate(BaseModel):
    kategorie: str | None = None
    datum: date | None = None
    notiz: str | None = None

    _norm_datum = field_validator("datum", mode="before")(_leer_zu_none)


class FotosatzListItem(BaseModel):
    """Eine Karte in der Fotosatz-Übersicht."""

    id: int
    projekt_id: int
    projekt_name: str = ""
    kategorie: str
    datum: date
    notiz: str
    anzahl_fotos: int = 0
    titel_foto_id: int | None = None
    # Name, unter dem das Archiv heruntergeladen wird — steht in der Oberfläche,
    # damit vor dem Klick klar ist, was im Projektordner landet.
    zip_dateiname: str = ""
    groesse_bytes: int = 0
    erstellt_am: datetime | None = None
    zuletzt_gemeldet_am: date | None = None
    mail_versendet_am: date | None = None
    mail_empfaenger: str = ""
    mail_weg: str = ""
    abgeholt_am: datetime | None = None
    abgeholt_von: str = ""
    abgeholt_ziel: str = ""

    model_config = {"from_attributes": True}


class FotosatzResponse(FotosatzListItem):
    fotos: list[BaufotoResponse] = []


class FotosatzVersand(BaseModel):
    """Ergebnis von "In Teams melden"."""

    fotosatz_id: int
    gemeldet: bool
    kanal: str
    nachricht: str


class FotosatzMailAnfrage(BaseModel):
    """Angaben aus dem Mail-Dialog eines Fotosatzes.

    Leerer ``betreff`` bzw. ``nachricht`` heißt: Der Server setzt seinen
    Vorschlag ein. So bleibt der Aufruf auch aus einem Skript brauchbar.
    """

    empfaenger: list[EmailStr] = Field(min_length=1)
    kopie: list[EmailStr] = []
    betreff: str = ""
    nachricht: str = ""

    @field_validator("empfaenger", "kopie", mode="before")
    @classmethod
    def _leere_weg(cls, wert):
        """Leere Zeilen aus dem Formular verwerfen, statt sie zu bemängeln."""
        if isinstance(wert, list):
            return [eintrag for eintrag in wert
                    if not isinstance(eintrag, str) or eintrag.strip()]
        return wert


# ─────────────────────────────────────────────────────────────────────────────
# Abholung durch einen Buerorechner
# ─────────────────────────────────────────────────────────────────────────────


class OffenerFotosatz(BaseModel):
    """Ein Fotosatz, der noch auf dem Weg ins Projektverzeichnis wartet.

    Enthaelt alles, was das Abholskript braucht, um den Zielordner zu bilden:
    Projektname (= Ordnername auf L:), Datum und Taetigkeit.
    """

    id: int
    projekt_name: str
    #: Taetigkeit, z. B. "Baustellenbegehung".
    kategorie: str
    datum: date
    notiz: str = ""
    anzahl_fotos: int = 0
    groesse_bytes: int = 0
    #: Name des Ordners, der im Projektverzeichnis angelegt werden soll:
    #: "{JJMMTT}_{Taetigkeit}" — dieselbe Regel wie im bisherigen Skript.
    ordnername: str = ""
    zip_dateiname: str = ""
    #: Zielordner aus den Projektstammdaten, z. B.
    #: "L:\\Bauleitung-Hamburg\\K30159 Kita Nord\\01 FOTOS".
    #: Leer = das Skript bildet den Pfad nach seiner eigenen Standardregel.
    zielpfad: str = ""
    erstellt_am: datetime | None = None


class AbholAnspruch(BaseModel):
    """Ein Buerorechner meldet: Ich nehme diesen Satz jetzt."""

    rechner: str = ""


class AbholStatus(BaseModel):
    """Antwort auf Anspruch, Quittung und Freigabe."""

    id: int
    #: True = der Aufrufer darf/durfte weitermachen.
    erfolg: bool = True
    nachricht: str = ""
    abgeholt_am: datetime | None = None
    abgeholt_von: str = ""
    abgeholt_ziel: str = ""


class AbholQuittung(BaseModel):
    """Rueckmeldung des Bueros: Satz liegt im Projektverzeichnis."""

    #: Rechnername, damit im Protokoll steht, wer abgeholt hat.
    rechner: str = ""
    #: Vollstaendiger Zielpfad — fuer Rueckfragen ("wo liegt der Satz?").
    ziel: str = ""


class FotosatzMailFaehigkeiten(BaseModel):
    """Was dieser Server beim Mailversand kann — steuert den Dialog."""

    #: Ist ein Postausgangsserver hinterlegt? Nur dann gibt es "Direkt senden".
    smtp: bool
    #: Adresse, unter der der Server verschickt (leer, wenn ohne SMTP).
    absender: str = ""
    #: Grenze für das ZIP in MB.
    max_anhang_mb: int


class FotosatzMailVorschlag(BaseModel):
    """Vorgeschlagener Betreff und Text — der Dialog füllt damit die Felder.

    Der Vorschlag kommt vom Server und nicht aus der Oberfläche, damit beide
    Wege (Dialog und direkter API-Aufruf) denselben Text erzeugen.
    """

    betreff: str
    nachricht: str
    zip_dateiname: str
    groesse_bytes: int
    #: Passt das Archiv durch eine Mail? Sonst steht in ``hinweis``, warum nicht.
    passt: bool = True
    hinweis: str = ""


class FotosatzMailErgebnis(BaseModel):
    """Ergebnis von "Direkt senden"."""

    fotosatz_id: int
    versendet: bool
    empfaenger: list[str] = []
    nachricht: str


# ─────────────────────────────────────────────────────────────────────────────
# Mängelanzeige (zwei Word-Dokumente, siehe services/maengelanzeige_generation)
# ─────────────────────────────────────────────────────────────────────────────


class MaengelanzeigeEmpfaenger(BaseModel):
    """Adressblock des Anschreibens."""

    firma: str
    #: Wie im Adressfeld, also im Akkusativ: „Herrn Hey“. Die Anrede formt der
    #: Erzeuger daraus („Sehr geehrter Herr Hey,“).
    ansprechpartner: str = ""
    strasse_hausnummer: str = ""
    plz_ort: str = ""
    versandart: str = "per Mail"
    email: EmailStr | None = None

    _norm_email = field_validator("email", mode="before")(_leer_zu_none)


class MaengelanzeigeSachbearbeiter(BaseModel):
    """Datumszeile und Unterschriftenblock."""

    name: str
    funktion: str = "-Baumanagement-"
    zeichen: str = ""
    auftragsnummer: str = ""
    email: EmailStr | None = None

    _norm_email = field_validator("email", mode="before")(_leer_zu_none)


class MaengelanzeigeAnfrage(BaseModel):
    """Ein Vorgang: Projekt, Firma, ausgewählte Mängel und die Termine."""

    projekt_id: int
    gewerk_id: int | None = None
    #: Die Mängel, die in die Anlage kommen — in dieser Reihenfolge.
    mangel_ids: list[int] = Field(min_length=1)
    empfaenger: MaengelanzeigeEmpfaenger
    sachbearbeiter: MaengelanzeigeSachbearbeiter
    begehungsdatum: date
    #: Ohne Angabe: heute.
    briefdatum: date | None = None
    #: Ohne Angabe: die früheste am Mangel gesetzte Frist, sonst +14 Tage.
    fristsetzungsdatum: date | None = None
    #: Stand der Anlage; ohne Angabe gilt das Begehungsdatum.
    anlagedatum: date | None = None
    #: Überschreiben, falls im Schreiben anders als in den Stammdaten.
    projektbezeichnung: str = ""
    vergabeeinheit: str = ""
    dokumentkuerzel: str = ""

    _norm_datum = field_validator(
        "briefdatum", "fristsetzungsdatum", "anlagedatum", mode="before"
    )(_leer_zu_none)


class MaengelanzeigeBereichVorschau(BaseModel):
    bereich: str
    anzahl_fotos: int
    beschreibungen: list[str] = []


class MaengelanzeigeVorschau(BaseModel):
    """Was entstehen würde — für die Kontrolle vor dem Erzeugen."""

    dateiname_anschreiben: str
    dateiname_anlage: str
    fristsetzungsdatum: date
    anzahl_fotos: int
    bereiche: list[MaengelanzeigeBereichVorschau] = []
    #: Übersprungene Mängel (kein Foto, Datei fehlt) — kein Fehler, ein Hinweis.
    hinweise: list[str] = []


class MaengelanzeigeVorbelegung(BaseModel):
    """Vorschläge für das Formular, aus den Stammdaten gezogen."""

    projektbezeichnung: str
    vergabeeinheit: str
    dokumentkuerzel: str
    begehungsdatum: date
    briefdatum: date
    fristsetzungsdatum: date
    empfaenger: MaengelanzeigeEmpfaenger
    #: Feste dritte Betreffzeile — die Oberfläche zeigt sie, ändern kann sie
    #: nur der Code (es ist eine Rechtsformulierung).
    betreff_dritte_zeile: str


# ─────────────────────────────────────────────────────────────────────────────
# Projektbericht (Monatsbericht)
# ─────────────────────────────────────────────────────────────────────────────


class BaubegehungSchema(BaseModel):
    datum: str = ""
    teilnehmer: str = ""
    firma: str = ""


class BesprechungSchema(BaseModel):
    bezeichnung: str = ""
    rhythmus: str = ""
    uhrzeit: str = ""


class SollIstZeileSchema(BaseModel):
    bezeichnung: str = ""
    soll: str = ""
    ist: str = ""
    verzug: str = ""


class ProjektberichtFotoResponse(BaseModel):
    id: int
    bericht_id: int
    bildunterschrift: str
    reihenfolge: int
    hochgeladen_am: datetime | None = None

    model_config = {"from_attributes": True}


class ProjektberichtFotoUpdate(BaseModel):
    bildunterschrift: str | None = None
    reihenfolge: int | None = None


class ProjektberichtBasis(BaseModel):
    """Felder, die Anlegen und Ändern teilen."""

    nummer: int | None = None
    berichtsdatum: date | None = None
    zeitraum_von: date | None = None
    zeitraum_bis: date | None = None
    ersteller: str = ""
    #: Kopfzeile links; leer = Projektname aus den Stammdaten.
    projektname: str = ""
    #: Kürzel für Fußzeile und Dateiname („BoB“).
    projektkuerzel: str = ""
    buero: str = "HPP"
    #: Kapitelschlüssel → Text (siehe services/projektbericht_gliederung).
    kapitel: dict[str, str] = {}
    baubegehungen: list[BaubegehungSchema] = []
    besprechungen: list[BesprechungSchema] = []
    soll_ist: list[SollIstZeileSchema] = []

    _norm_datum = field_validator(
        "berichtsdatum", "zeitraum_von", "zeitraum_bis", mode="before"
    )(_leer_zu_none)


class ProjektberichtCreate(ProjektberichtBasis):
    projekt_id: int
    #: Inhalte des zuletzt erstellten Berichts übernehmen.
    aus_letztem_bericht: bool = False


class ProjektberichtUpdate(ProjektberichtBasis):
    """Alle Felder freiwillig — die Oberfläche speichert einzeln nach."""


class ProjektberichtListItem(BaseModel):
    id: int
    projekt_id: int
    projekt_name: str = ""
    nummer: int
    berichtsdatum: date
    zeitraum_von: date | None = None
    zeitraum_bis: date | None = None
    ersteller: str
    projektname: str
    projektkuerzel: str
    anzahl_fotos: int = 0
    #: Wie viele Kapitel im Dokument erscheinen würden.
    anzahl_kapitel: int = 0
    hat_dokument: bool = False
    hat_pdf: bool = False
    erzeugt_am: datetime | None = None
    erstellt_am: datetime | None = None
    geaendert_am: datetime | None = None

    model_config = {"from_attributes": True}


class ProjektberichtResponse(ProjektberichtListItem):
    buero: str = "HPP"
    kapitel: dict[str, str] = {}
    baubegehungen: list[BaubegehungSchema] = []
    besprechungen: list[BesprechungSchema] = []
    soll_ist: list[SollIstZeileSchema] = []
    fotos: list[ProjektberichtFotoResponse] = []


class GliederungUnterkapitel(BaseModel):
    schluessel: str
    titel: str
    art: str
    immer_zeigen: bool


class GliederungHauptkapitel(BaseModel):
    schluessel: str
    titel: str
    art: str
    ohne_ueberschrift: bool
    unterkapitel: list[GliederungUnterkapitel] = []


class ProjektberichtVorschauKapitel(BaseModel):
    nummer: str
    titel: str
    ebene: int
    schluessel: str
    art: str
    hat_inhalt: bool


class ProjektberichtVorschau(BaseModel):
    """Was im Dokument erschiene — vor allem die Nummerierung."""

    dateiname_docx: str
    dateiname_pdf: str
    kapitel: list[ProjektberichtVorschauKapitel] = []
    #: Kapitel, die wegen fehlendem Inhalt entfallen.
    entfallen: list[str] = []
    anzahl_fotos: int = 0
    pdf_moeglich: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Baubesprechungsprotokolle
# ─────────────────────────────────────────────────────────────────────────────

#: Die fünf Statuswerte der Legende (Seite 3 des Protokolls).
BesprechungStatus = Literal["k", "b", "e", "n", "i"]

#: entwurf -> geprueft -> freigegeben.
ProtokollStatus = Literal["entwurf", "geprueft", "freigegeben"]


class ProjektbeteiligterBasis(BaseModel):
    kuerzel: str = ""
    name: str = ""
    rolle: str = ""
    ansprechpartner: str = ""
    telefon: str = ""
    sortierung: int = 0


class ProjektbeteiligterCreate(ProjektbeteiligterBasis):
    projekt_id: int


class ProjektbeteiligterUpdate(ProjektbeteiligterBasis):
    pass


class ProjektbeteiligterResponse(ProjektbeteiligterBasis):
    id: int
    projekt_id: int

    model_config = {"from_attributes": True}


class BesprechungsKapitelBasis(BaseModel):
    nummer: str = ""
    titel: str = ""
    sortierung: int = 0
    gewerk_id: int | None = None


class BesprechungsKapitelCreate(BesprechungsKapitelBasis):
    projekt_id: int


class BesprechungsKapitelUpdate(BesprechungsKapitelBasis):
    pass


class BesprechungsKapitelResponse(BesprechungsKapitelBasis):
    id: int
    projekt_id: int
    #: Wie viele Themen in diesem Kapitel hängen (offene und erledigte).
    anzahl_themen: int = 0

    model_config = {"from_attributes": True}


class BesprechungsThemaResponse(BaseModel):
    """Ein Sachverhalt der laufenden Themenliste — der Projektstand."""

    id: int
    projekt_id: int
    kapitel_id: int
    kapitel_nummer: str = ""
    kapitel_titel: str = ""
    inhalt_nr: str = ""
    thema: str = ""
    zustaendig: str = ""
    bearb_bis: str = ""
    status: str = "n"
    erledigt_am: date | None = None
    #: Protokollnummer, in der das Thema zuletzt behandelt wurde — die dritte
    #: Zahl der Protokollnummer.
    zuletzt_bb: int | None = None
    erstmals_bb: int | None = None
    #: "02. 08." — Kapitel und Inhalt, ohne die BB-Nummer.
    kennung: str = ""

    model_config = {"from_attributes": True}


class ThemaUpdateBasis(BaseModel):
    thema_text: str = ""
    zustaendig: str = ""
    bearb_bis: str = ""
    status: BesprechungStatus = "n"
    hervorheben: bool = False
    sortierung: int = 0
    bestaetigt: bool = False


class ThemaUpdateCreate(ThemaUpdateBasis):
    """Eine Zeile für dieses Protokoll.

    Entweder Fortschreibung eines bestehenden Themas (``thema_id`` gesetzt)
    oder ein neues Thema; dann sagt ``kapitel_id``, wohin es gehört. Genau
    einer der beiden Fälle muss zutreffen — die Prüfung steht im Router,
    damit die Fehlermeldung auf Deutsch und konkret sein kann.
    """

    thema_id: int | None = None
    kapitel_id: int | None = None


class ThemaUpdateAendern(ThemaUpdateBasis):
    """Alle Felder freiwillig — die Prüfansicht speichert einzeln nach."""

    thema_text: str | None = None
    zustaendig: str | None = None
    bearb_bis: str | None = None
    status: BesprechungStatus | None = None
    hervorheben: bool | None = None
    sortierung: int | None = None
    bestaetigt: bool | None = None
    #: Umhängen: doch ein anderes bestehendes Thema als gedacht.
    thema_id: int | None = None


class ThemaUpdateResponse(ThemaUpdateBasis):
    id: int
    protokoll_id: int
    thema_id: int
    herkunft: str = "mensch"
    #: Die vollständige Nummer, wie sie gedruckt wird: "02. 08. 16".
    nummer: str = ""
    #: Die BB-Nummer der Sitzung, aus der die Zeile stammt. Bei einem
    #: fortgeschriebenen offenen Punkt ist das eine ältere Nummer als die des
    #: Protokolls, in dem die Zeile gerade steht.
    bb_nr: str = ""
    #: Wurde die Zeile in diesem Protokoll nur unverändert mitgenommen?
    #: Die Prüfansicht darf sie dann ruhiger darstellen.
    uebernommen: bool = False
    kapitel_id: int = 0
    kapitel_nummer: str = ""
    kapitel_titel: str = ""
    inhalt_nr: str = ""
    #: Stand dieses Themas im vorherigen Protokoll — damit in der Prüfansicht
    #: sichtbar ist, was sich heute geändert hat.
    vorher_text: str = ""
    vorher_status: str = ""
    vorher_bb: int | None = None

    model_config = {"from_attributes": True}


class TeilnehmerBasis(BaseModel):
    name: str = ""
    firma_kuerzel: str = ""
    telefon: str = ""
    anwesend: bool = True
    reihenfolge: int = 0


class TeilnehmerCreate(TeilnehmerBasis):
    pass


class TeilnehmerUpdate(TeilnehmerBasis):
    name: str | None = None
    firma_kuerzel: str | None = None
    telefon: str | None = None
    anwesend: bool | None = None
    reihenfolge: int | None = None


class TeilnehmerResponse(TeilnehmerBasis):
    id: int
    protokoll_id: int
    aus_transkript: bool = False

    model_config = {"from_attributes": True}


class AnlageResponse(BaseModel):
    id: int
    protokoll_id: int
    dateiname: str = ""
    bezeichnung: str = ""
    reihenfolge: int = 0
    hochgeladen_am: datetime | None = None

    model_config = {"from_attributes": True}


class ProtokollBasis(BaseModel):
    leistung: str = "Baubesprechung"
    besprechungsort: str = ""
    besprechungsdatum: date
    ersteller_id: int | None = None
    ersteller_name: str = ""
    ersteller_kuerzel: str = ""
    ersteller_durchwahl: str = ""
    ersteller_email: str = ""


class ProtokollCreate(ProtokollBasis):
    projekt_id: int
    #: Leer lassen: Die nächste freie Nummer des Projekts wird vergeben.
    nummer: int | None = None
    #: Offene Punkte (Status b, k, n, i) aus dem letzten Protokoll als
    #: Fortschreibung übernehmen. Genau das macht die Excel-Vorlage von Hand.
    offene_punkte_uebernehmen: bool = True


class ProtokollUpdate(BaseModel):
    leistung: str | None = None
    besprechungsort: str | None = None
    besprechungsdatum: date | None = None
    ersteller_id: int | None = None
    ersteller_name: str | None = None
    ersteller_kuerzel: str | None = None
    ersteller_durchwahl: str | None = None
    ersteller_email: str | None = None
    nummer: int | None = None


class ProtokollListItem(BaseModel):
    id: int
    projekt_id: int
    projekt_name: str = ""
    nummer: int
    leistung: str = "Baubesprechung"
    besprechungsort: str = ""
    besprechungsdatum: date
    ersteller_name: str = ""
    ersteller_kuerzel: str = ""
    status: ProtokollStatus = "entwurf"
    anzahl_themen: int = 0
    anzahl_offen: int = 0
    anzahl_teilnehmer: int = 0
    anzahl_anlagen: int = 0
    #: Zeilen, die noch niemand angesehen hat — die Freigabe warnt danach.
    anzahl_ungeprueft: int = 0
    hat_transkript: bool = False
    hat_dokument: bool = False
    hat_pdf: bool = False
    analyse_am: datetime | None = None
    erzeugt_am: datetime | None = None
    erstellt_am: datetime | None = None
    geaendert_am: datetime | None = None

    model_config = {"from_attributes": True}


class ProtokollResponse(ProtokollListItem):
    ersteller_durchwahl: str = ""
    ersteller_email: str = ""
    ersteller_id: int | None = None
    tldv_transkript_roh: str = ""
    tldv_notizen_roh: str = ""
    analyse_hinweise: list[str] = []
    geprueft_am: datetime | None = None
    freigegeben_am: datetime | None = None
    themen_updates: list[ThemaUpdateResponse] = []
    teilnehmer: list[TeilnehmerResponse] = []
    anlagen: list[AnlageResponse] = []
    #: Kopfdaten des Deckblatts, aus dem Projekt — damit die Oberfläche sie
    #: anzeigen kann, ohne das Projekt einzeln zu laden.
    projekt_nummer: str = ""
    bauherr: str = ""
    projekt_adresse: str = ""


class TldvImport(BaseModel):
    """Rohtext aus tl;dv: Transkript und KI-Notizen.

    Beides ist freiwillig, aber eines von beiden muss da sein — nur aus den
    Notizen entsteht schon eine brauchbare Themenliste, nur aus dem Transkript
    auch. Zusammen wird es besser.
    """

    transkript: str = ""
    notizen: str = ""
    #: Nach dem Import gleich analysieren. Ausschalten, wenn erst noch
    #: Kapitel gepflegt werden sollen.
    analysieren: bool = True


class AnalyseErgebnis(BaseModel):
    """Was die KI-Analyse vorgeschlagen hat — nichts davon ist schon gültig."""

    neue_themen: int = 0
    fortschreibungen: int = 0
    teilnehmer: int = 0
    hinweise: list[str] = []


class ProtokollFreigabe(BaseModel):
    geprueft_von_id: int | None = None
    #: Auch freigeben, wenn noch Zeilen ungeprüft sind. Standard: nein — die
    #: ganze Funktion existiert, damit nichts Ungeprüftes hinausgeht.
    trotz_ungeprueft: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Mehrkostenanzeigen (und Behinderungsanzeigen, Nachträge, …) beantworten
#
# Der Ablauf hat drei Schritte, und die Schemas folgen ihnen:
#
#   1. auslesen   Dateien hoch  ->  GelesenesSchreibenSchema (je Datei)
#   2. vorschau   Formular hin  ->  AnzeigeAntwortVorschau
#   3. dokument   Formular hin  ->  die .docx, bzw. der Outlook-Entwurf
#
# Zwischen 1 und 2 liegt der Mensch: Was ausgelesen wurde, füllt das Formular
# vor und ist dort Feld für Feld änderbar. Nichts aus einem fremden Dokument
# geht ungesehen in ein Schreiben des Büros.
# ─────────────────────────────────────────────────────────────────────────────


class AnschriftSchema(BaseModel):
    firma: str = ""
    zusatz: str = ""
    strasse: str = ""
    plz: str = ""
    ort: str = ""
    land: str = ""


class GelesenerPunktSchema(BaseModel):
    """Ein nummerierter Abschnitt der eingegangenen Anzeige."""

    nummer: str
    titel: str
    text: str = ""


class GelesenesSchreibenSchema(BaseModel):
    """Was aus einer hochgeladenen Anzeige herauszulesen war."""

    quelle: str
    seiten: int = 0

    #: "Mehrkostenanzeige", "Behinderungsanzeige", "Nachtragsangebot", …
    art: str = ""
    nummer: str = ""
    #: Wie die Firma selbst zählt: "MKA 01", "BEH 01", "MEKO 11".
    kennung: str = ""
    datum: date | None = None
    betreff: str = ""
    #: Betreff ohne die Zählung davor — der Sachverhalt allein.
    kurzbezeichnung: str = ""

    #: Die Anschrift der anzeigenden Firma. Sie bekommt die Antwort.
    absender: AnschriftSchema = AnschriftSchema()
    absender_email: str = ""
    absender_telefon: str = ""
    ansprechpartner: str = ""
    ansprechpartner_email: str = ""

    #: Wen die Firma angeschrieben hat (meist der Bauherr) — für den Verteiler.
    empfaenger: AnschriftSchema = AnschriftSchema()

    projektnummer: str = ""
    leistungsort: str = ""
    gewerk: str = ""

    rechtsgrundlage: str = ""
    punkte: list[GelesenerPunktSchema] = []
    lv_positionen: list[str] = []
    bauzeit: str = ""
    forderung: str = ""
    unterzeichner: str = ""
    unterzeichner_funktion: str = ""

    #: Der Wortlaut der Anzeige. Er geht mit an die Oberfläche, weil das
    #: Ausformulieren der Stellungnahme ihn als Tatsachengrundlage braucht
    #: (siehe ``app.services.anzeige_formulierung``) — die hochgeladene Datei
    #: selbst ist danach gelöscht.
    volltext: str = ""

    #: Was unsicher war. Kein Fehler — eine Bitte, im Formular hinzusehen.
    hinweise: list[str] = []


class AnzeigeAuslesenErgebnis(BaseModel):
    """Antwort des Auslesens: je Datei ein Ergebnis, dazu die Fehlschläge."""

    schreiben: list[GelesenesSchreibenSchema] = []
    #: Dateien, die sich nicht lesen ließen — mit dem Grund im Klartext.
    fehlgeschlagen: list[str] = []


class AnzeigeEmpfaengerSchema(BaseModel):
    """Adressblock: die Firma, die die Anzeige geschrieben hat."""

    firma: str
    #: "Herr", "Frau" oder leer. Leer heißt "Sehr geehrte Damen und Herren" —
    #: geraten wird nichts.
    anrede: Literal["", "Herr", "Frau"] = ""
    ansprechpartner: str = ""
    strasse: str = ""
    plz: str = ""
    ort: str = ""
    email: EmailStr | None = None

    _norm_email = field_validator("email", mode="before")(_leer_zu_none)


class AnzeigeSachbearbeiterSchema(BaseModel):
    """Datumszeile und Unterschriftsblock des Briefs."""

    name: str
    funktion: str = "-Baumanagement-"
    zeichen: str = ""
    durchwahl: str = ""
    email: EmailStr | None = None

    _norm_email = field_validator("email", mode="before")(_leer_zu_none)


class AnzeigeSchema(BaseModel):
    """Die eingegangene Anzeige, soweit die Antwort sie braucht."""

    art: str = "Mehrkostenanzeige"
    nummer: str = ""
    kennung: str = ""
    datum: date | None = None
    kurzbezeichnung: str = ""
    #: Der Satz der Firma zur Bauzeit. Steht hier etwas, kann die Antwort ihn
    #: ausdrücklich zurückweisen (``bauzeit_ablehnen``).
    bauzeit: str = ""

    _norm_datum = field_validator("datum", mode="before")(_leer_zu_none)


class AnzeigeAntwortAnfrage(BaseModel):
    """Alles, was das Formular für ein Antwortschreiben liefert."""

    empfaenger: AnzeigeEmpfaengerSchema
    sachbearbeiter: AnzeigeSachbearbeiterSchema
    anzeige: AnzeigeSchema

    #: Die fette Projektzeile, z. B. "G.100-DESYUM_Neubau Besucherzentrum".
    projektzeile: str
    #: Zweite fette Zeile, z. B. "VE300.01- Erweiterter Rohbau".
    vergabeeinheit: str = ""
    #: Leer = aus Art, Nummer, Datum und Sachverhalt der Anzeige gebildet.
    betreff: str = ""
    #: Ohne Angabe: heute.
    briefdatum: date | None = None

    #: Das Info-/Prompt-Feld: die Stellungnahme des Büros. Sie kommt Wort für
    #: Wort in den Brief.
    stellungnahme: str
    #: Leer = Standardeinleitung ("wir haben Ihre … erhalten und nehmen …").
    einleitung: str = ""
    haltung: Literal[
        "ablehnung", "teilweise", "pruefung", "anerkennung", "kenntnisnahme"
    ] = "kenntnisnahme"
    #: Leer = Standardschluss zur gewählten Haltung.
    schlusssatz: str = ""
    bauzeit_ablehnen: bool = False

    anlagen: str = ""
    verteiler: str = ""
    #: Projektkürzel für den Dateinamen, z. B. "G.100-DESYUM".
    dateikuerzel: str = ""

    _norm_datum = field_validator("briefdatum", mode="before")(_leer_zu_none)


class AnzeigeAbsatzVorschau(BaseModel):
    text: str
    zitat: bool = False


class AnzeigeAntwortVorschau(BaseModel):
    """Was entstehen würde — zur Kontrolle vor dem Erzeugen."""

    dateiname: str
    #: Die drei fetten Zeilen und die Anrede, so wie sie im Brief stehen.
    projektzeile: str
    vergabeeinheit: str = ""
    betreff: str
    anrede: str
    adressblock: list[str] = []
    datumszeile: list[str] = []
    #: Der Briefkörper Absatz für Absatz; eingerückte LV-Zitate sind markiert.
    absaetze: list[AnzeigeAbsatzVorschau] = []
    verteilerseite: list[str] = []
    #: Betreff und Text der E-Mail — genau das, was Outlook bekommt.
    mail_betreff: str
    mail_text: str
    mail_an: str = ""
    hinweise: list[str] = []


class AnzeigeMailAnfrage(BaseModel):
    """Outlook-Entwurf: dieselben Daten wie fürs Dokument, plus Mailfelder."""

    antwort: AnzeigeAntwortAnfrage
    #: Ohne Angabe: die Adresse aus dem Adressblock.
    an: list[str] = []
    kopie: list[str] = []
    #: Ohne Angabe: der vorgeschlagene Betreff bzw. Text.
    betreff: str = ""
    text: str = ""
    #: Das Schreiben als Anhang mitgeben. Aus heißt: nur Empfänger, Betreff
    #: und Text — das Dokument hängt man selbst an.
    dokument_anhaengen: bool = True


class AnzeigeFormulierenAnfrage(BaseModel):
    """Stichpunkte rein, ausformulierte Stellungnahme raus.

    Das Ergebnis geht **ins Infofeld**, nicht ins Dokument: Erst liest ein
    Mensch, was das Büro schreiben würde, dann entsteht das Schreiben. Siehe
    ``app.services.anzeige_formulierung``.
    """

    #: Was in der Antwort stehen soll. Stichworte genügen.
    stichpunkte: str
    #: Die Angaben der eingegangenen Anzeige — die Tatsachengrundlage.
    anzeige: AnzeigeSchema = AnzeigeSchema()
    #: Die nummerierten Punkte der Anzeige, als "1. Titel" je Eintrag.
    punkte: list[str] = []
    lv_positionen: list[str] = []
    rechtsgrundlage: str = ""
    #: Der Volltext der Anzeige. Ohne ihn kann das Modell nur die Stichpunkte
    #: verwenden — mit ihm kann es sich auf den Wortlaut der Firma beziehen.
    anzeigetext: str = ""
    haltung: Literal[
        "ablehnung", "teilweise", "pruefung", "anerkennung", "kenntnisnahme"
    ] = "kenntnisnahme"
    projektzeile: str = ""
    vergabeeinheit: str = ""


class AnzeigeFormulierenErgebnis(BaseModel):
    #: Fertig zum Einsetzen ins Infofeld.
    stellungnahme: str
    #: Angaben, die gefehlt haben — bewusst NICHT ausformuliert.
    offene_fragen: list[str] = []
    hinweise: list[str] = []


class AnzeigeBausteinSchema(BaseModel):
    """Ein Standardsatz des Büros, fertig zum Einsetzen ins Infofeld."""

    kennung: str
    #: Kurze Beschriftung für den Knopf.
    titel: str
    #: Der Satz. „___“ markiert eine Stelle, die noch zu füllen ist.
    text: str
    #: Eingerückt einsetzen (LV-Zitat).
    zitat: bool = False


class AnzeigeBausteinGruppeSchema(BaseModel):
    kennung: str
    titel: str
    bausteine: list[AnzeigeBausteinSchema] = []


class AnzeigeBausteineErgebnis(BaseModel):
    """Der Katalog, gefiltert auf die gewählte Haltung."""

    gruppen: list[AnzeigeBausteinGruppeSchema] = []
    #: Die Zeichenfolge, die eine offene Lücke markiert.
    luecke: str


class AnzeigeGlaettenAnfrage(BaseModel):
    #: Die Stichworte aus dem Infofeld.
    text: str


class AnzeigeGlaettenErgebnis(BaseModel):
    text: str
    #: Was auffiel — offene Lücken, Stichworte, fehlende Großschreibung.
    hinweise: list[str] = []
