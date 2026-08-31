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


class ProjektUpdate(BaseModel):
    """Nachtraegliche Aenderung. Nicht gesetzte Felder bleiben, wie sie sind."""

    name: str | None = None
    adresse: str | None = None
    teams_webhook_url: str | None = None
    foto_zielpfad: str | None = None


class ProjektResponse(BaseModel):
    id: int
    name: str
    adresse: str
    lat: float | None
    lon: float | None
    teams_webhook_url: str = ""
    foto_zielpfad: str = ""
    erstellt_am: datetime

    model_config = {"from_attributes": True}


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

    _norm_email = field_validator("email", mode="before")(_leer_zu_none)


class BearbeiterResponse(BaseModel):
    id: int
    name: str
    email: str | None

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
