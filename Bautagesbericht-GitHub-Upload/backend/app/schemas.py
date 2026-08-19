from datetime import date, datetime
from pydantic import BaseModel, EmailStr


class ProjektCreate(BaseModel):
    name: str
    adresse: str = ""


class ProjektResponse(BaseModel):
    id: int
    name: str
    adresse: str
    lat: float | None
    lon: float | None
    erstellt_am: datetime

    model_config = {"from_attributes": True}


class EmpfaengerCreate(BaseModel):
    label: str
    email: EmailStr


class EmpfaengerResponse(BaseModel):
    id: int
    label: str
    email: str
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
