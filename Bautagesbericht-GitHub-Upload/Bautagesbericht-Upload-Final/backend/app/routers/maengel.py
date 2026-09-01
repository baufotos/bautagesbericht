"""Mängel: erfassen, pflegen, dokumentieren, exportieren.

Reihenfolge der Routen ist bewusst: erst die feststehenden Pfade (``/export``,
``/fotos/...``, ``/dateien/...``), danach die mit ``/{mangel_id}``. FastAPI
prüft in Registrierungsreihenfolge — sonst würde "export" als Mangel-ID
gelesen.

Aufteilung der Erfassung in zwei Schritte (erst Mangel anlegen, dann Fotos
hochladen) ist eine Entscheidung für die Baustelle: Der Datensatz ist mit dem
ersten, sehr kleinen Aufruf gesichert; die Fotos gehen danach einzeln raus und
ein Abbruch der Mobilfunkverbindung kostet höchstens ein Foto, nicht die
ganze Aufnahme.
"""

from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models import (
    Gewerk,
    Mangel,
    MangelDatei,
    MangelFoto,
    MangelPlanMarkierung,
    Projekt,
    ProjektPlan,
)
from app.schemas import (
    MaengellisteJSON,
    MangelCreate,
    MangelDateiResponse,
    MangelExportEintrag,
    MangelFotoResponse,
    MangelFotoUpdate,
    MangelListItem,
    MangelPlanMarkierungCreate,
    MangelPlanMarkierungResponse,
    MangelResponse,
    MangelUpdate,
    MangelVersandErgebnis,
)
from app.services import bilder
from app.services.cleanup import delete_mangel_cascade
from app.services.maengelliste_generation import generate_maengelliste
from app.services.mangel_logik import (
    abgeschlossene_status,
    aktuelle_frist,
    duplikat_erstellen,
    gewerk_anzeige,
    ist_abgeschlossen,
    ist_ueberfaellig,
    naechste_nummer,
    status_farben,
)
from app.services.mangel_versand import (
    benachrichtige_teams,
    erzwinge_manuellen_versand,
    mail_fehler,
    sende_mangelruege,
)
from app.utils.file_storage import get_absolute_path, save_upload_in

router = APIRouter(prefix="/maengel", tags=["maengel"])

# Obergrenze pro Upload-Aufruf. Das Frontend schickt die Fotos einzeln bzw. in
# kleinen Gruppen; die Grenze schützt nur vor Ausrutschern.
MAX_FOTOS_PRO_UPLOAD = 20


# ─────────────────────────────────────────────────────────────────────────────
# Hintergrundaufgaben
#
# Wie in app.routers.einreichungen: Der Request gibt seine DB-Sitzung frei,
# sobald die Antwort raus ist. Hintergrundaufgaben holen sich deshalb eine
# eigene Sitzung und laden den Mangel neu.
# ─────────────────────────────────────────────────────────────────────────────


def _run_benachrichtigung(mangel_id: int, anlass: str) -> None:
    import asyncio

    db = SessionLocal()
    try:
        mangel = db.get(Mangel, mangel_id)
        if mangel is not None:
            asyncio.run(benachrichtige_teams(mangel, anlass))
    finally:
        db.close()


def _run_autosend(mangel_id: int) -> None:
    import asyncio

    db = SessionLocal()
    try:
        mangel = db.get(Mangel, mangel_id)
        if mangel is not None:
            asyncio.run(sende_mangelruege(db, mangel))
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Antwort-Aufbau
# ─────────────────────────────────────────────────────────────────────────────


def _foto_uebersicht(db: Session, mangel_ids: list[int]) -> dict[int, tuple[int, int]]:
    """Pro Mangel: (Anzahl Fotos, ID des Titelfotos).

    Ein Aufruf für die ganze Liste statt einer Abfrage pro Zeile.
    """
    if not mangel_ids:
        return {}
    rows = (
        db.query(MangelFoto.mangel_id, MangelFoto.id)
        .filter(MangelFoto.mangel_id.in_(mangel_ids))
        .order_by(MangelFoto.reihenfolge, MangelFoto.id)
        .all()
    )
    uebersicht: dict[int, tuple[int, int]] = {}
    for mangel_id, foto_id in rows:
        anzahl, titel = uebersicht.get(mangel_id, (0, foto_id))
        uebersicht[mangel_id] = (anzahl + 1, titel)
    return uebersicht


def _duplikat_anzahl(db: Session, mangel_ids: list[int]) -> dict[int, int]:
    if not mangel_ids:
        return {}
    rows = (
        db.query(Mangel.eltern_mangel_id, func.count(Mangel.id))
        .filter(Mangel.eltern_mangel_id.in_(mangel_ids))
        .group_by(Mangel.eltern_mangel_id)
        .all()
    )
    return {eltern_id: anzahl for eltern_id, anzahl in rows}


def _list_item(mangel: Mangel, farben: dict[str, str], abgeschlossen: set[str],
               fotos: tuple[int, int] | None, duplikate: int) -> MangelListItem:
    item = MangelListItem.model_validate(mangel)
    item.projekt_name = mangel.projekt.name if mangel.projekt else ""
    item.gewerk_anzeige = gewerk_anzeige(mangel.gewerk)
    item.firma_name = mangel.gewerk.firma_name if mangel.gewerk else ""
    item.status_farbe = farben.get(mangel.status, "")
    item.aktuelle_frist = aktuelle_frist(mangel)
    item.ist_ueberfaellig = ist_ueberfaellig(mangel, abgeschlossen)
    item.ist_abgeschlossen = ist_abgeschlossen(mangel, abgeschlossen)
    item.anzahl_fotos = fotos[0] if fotos else 0
    item.titel_foto_id = fotos[1] if fotos else None
    item.anzahl_duplikate = duplikate
    return item


def _detail(db: Session, mangel: Mangel) -> MangelResponse:
    farben = status_farben(db)
    abgeschlossen = abgeschlossene_status(db)
    fotos = list(mangel.fotos)

    antwort = MangelResponse.model_validate(mangel)
    antwort.projekt_name = mangel.projekt.name if mangel.projekt else ""
    antwort.gewerk_anzeige = gewerk_anzeige(mangel.gewerk)
    antwort.firma_name = mangel.gewerk.firma_name if mangel.gewerk else ""
    antwort.status_farbe = farben.get(mangel.status, "")
    antwort.aktuelle_frist = aktuelle_frist(mangel)
    antwort.ist_ueberfaellig = ist_ueberfaellig(mangel, abgeschlossen)
    antwort.ist_abgeschlossen = ist_abgeschlossen(mangel, abgeschlossen)
    antwort.anzahl_fotos = len(fotos)
    antwort.titel_foto_id = fotos[0].id if fotos else None
    antwort.anzahl_duplikate = len(mangel.duplikate or [])
    antwort.zustaendiger_user_name = (
        mangel.zustaendiger_user.name if mangel.zustaendiger_user else ""
    )
    if mangel.eltern_mangel is not None:
        antwort.eltern_nummer = mangel.eltern_mangel.nummer
        antwort.eltern_kurzbezeichnung = mangel.eltern_mangel.kurzbezeichnung
    antwort.mail_fehler = mail_fehler(mangel)
    antwort.fotos = [MangelFotoResponse.model_validate(f) for f in fotos]
    antwort.dateien = [MangelDateiResponse.model_validate(d) for d in mangel.dateien]

    markierung = mangel.markierungen[0] if mangel.markierungen else None
    if markierung is not None:
        antwort.markierung = MangelPlanMarkierungResponse.model_validate(markierung)
        antwort.markierung.plan_dateiname = (
            markierung.plan.dateiname if markierung.plan else ""
        )
    return antwort


def _hole_mangel(db: Session, mangel_id: int) -> Mangel:
    mangel = db.get(Mangel, mangel_id)
    if not mangel:
        raise HTTPException(404, "Mangel nicht gefunden")
    return mangel


# ─────────────────────────────────────────────────────────────────────────────
# Übersicht und Export (feststehende Pfade zuerst)
# ─────────────────────────────────────────────────────────────────────────────


def _gefiltert(
    db: Session,
    projekt_id: int | None,
    status: str | None,
    gewerk_id: int | None,
    prioritaet: str | None,
    typ: str | None,
    ueberfaellig: bool | None,
    abgeschlossen: bool | None,
    suche: str | None,
):
    """Gemeinsame Filterlogik von Übersicht und Export."""
    query = db.query(Mangel)
    if projekt_id is not None:
        query = query.filter(Mangel.projekt_id == projekt_id)
    if status:
        query = query.filter(Mangel.status == status)
    if gewerk_id is not None:
        query = query.filter(Mangel.gewerk_id == gewerk_id)
    if prioritaet:
        query = query.filter(Mangel.prioritaet == prioritaet)
    if typ:
        query = query.filter(Mangel.typ == typ)
    if suche:
        muster = f"%{suche.strip()}%"
        query = query.filter(
            Mangel.kurzbezeichnung.ilike(muster)
            | Mangel.beschreibung.ilike(muster)
            | Mangel.nummer.ilike(muster)
        )

    fertig = abgeschlossene_status(db)
    # Überfälligkeit und Abschluss hängen an mehreren Feldern; die Bedingung
    # wird direkt in SQL formuliert, damit auch bei vielen Mängeln nicht die
    # ganze Tabelle in den Speicher muss. Maßgeblich ist die Nachfrist, sonst
    # die erste Frist — dieselbe Regel wie mangel_logik.aktuelle_frist.
    frist = func.coalesce(Mangel.erste_nachfrist_bis, Mangel.erste_frist_bis)
    offen_bedingung = Mangel.erledigt_am.is_(None)
    if fertig:
        offen_bedingung = offen_bedingung & Mangel.status.notin_(fertig)

    if ueberfaellig is True:
        query = query.filter(frist.isnot(None), frist < date.today(), offen_bedingung)
    elif ueberfaellig is False:
        query = query.filter(
            (frist.is_(None)) | (frist >= date.today()) | ~offen_bedingung
        )

    if abgeschlossen is True:
        query = query.filter(~offen_bedingung)
    elif abgeschlossen is False:
        query = query.filter(offen_bedingung)

    # Nummern sind Text ("00012", "00012.1") — die Textsortierung liefert
    # dank fester Stellenzahl genau die fachlich richtige Reihenfolge.
    return query.order_by(Mangel.projekt_id, Mangel.nummer)


@router.get("", response_model=list[MangelListItem])
def list_maengel(
    projekt_id: int | None = None,
    status: str | None = None,
    gewerk_id: int | None = None,
    prioritaet: str | None = None,
    typ: str | None = None,
    ueberfaellig: bool | None = None,
    abgeschlossen: bool | None = None,
    suche: str | None = None,
    db: Session = Depends(get_db),
):
    rows = _gefiltert(db, projekt_id, status, gewerk_id, prioritaet, typ,
                      ueberfaellig, abgeschlossen, suche).all()

    ids = [m.id for m in rows]
    fotos = _foto_uebersicht(db, ids)
    duplikate = _duplikat_anzahl(db, ids)
    farben = status_farben(db)
    fertig = abgeschlossene_status(db)
    return [
        _list_item(m, farben, fertig, fotos.get(m.id), duplikate.get(m.id, 0))
        for m in rows
    ]


def _filter_beschreibung(projekt: Projekt, status: str | None,
                         gewerk: Gewerk | None, prioritaet: str | None,
                         ueberfaellig: bool | None) -> str:
    teile = []
    if status:
        teile.append(f"Status: {status}")
    if gewerk is not None:
        teile.append(f"Firma: {gewerk_anzeige(gewerk)}")
    if prioritaet:
        teile.append(f"Priorität: {prioritaet}")
    if ueberfaellig is True:
        teile.append("nur überfällige")
    return " · ".join(teile) or "alle Mängel"


@router.get("/export")
def export_maengelliste(
    projekt_id: int,
    status: str | None = None,
    gewerk_id: int | None = None,
    prioritaet: str | None = None,
    ueberfaellig: bool | None = None,
    intern: bool = False,
    db: Session = Depends(get_db),
):
    """Erzeugt die Mängelliste als Word-Dokument und liefert sie zum Download.

    ``intern=true`` erzeugt die interne Fassung *mit* internen Bemerkungen.
    Ohne diesen Schalter wird die interne Bemerkung nicht einmal in das
    Export-DTO übernommen — sie kann also nicht versehentlich in einer Fassung
    für die Firma landen.
    """
    projekt = db.get(Projekt, projekt_id)
    if not projekt:
        raise HTTPException(404, "Projekt nicht gefunden")

    rows = _gefiltert(db, projekt_id, status, gewerk_id, prioritaet, None,
                      ueberfaellig, None, None).all()
    fertig = abgeschlossene_status(db)

    eintraege = []
    for mangel in rows:
        markierung = mangel.markierungen[0] if mangel.markierungen else None
        markierung_text = ""
        if markierung is not None:
            plan_name = markierung.plan.dateiname if markierung.plan else "Plan"
            markierung_text = (
                f"{plan_name}, Seite {markierung.seite} "
                f"({markierung.x_prozent:.0f} % / {markierung.y_prozent:.0f} %)"
            )

        eintraege.append(MangelExportEintrag(
            nummer=mangel.nummer,
            kurzbezeichnung=mangel.kurzbezeichnung,
            typ=mangel.typ,
            status=mangel.status,
            prioritaet=mangel.prioritaet,
            firma=gewerk_anzeige(mangel.gewerk),
            ort=mangel.hinweis_ort or "",
            raumnummer=mangel.raumnummer or "",
            beschreibung=mangel.beschreibung or "",
            erstellt_am=mangel.erstellt_am,
            frist_bis=mangel.erste_frist_bis,
            nachfrist_bis=mangel.erste_nachfrist_bis,
            erledigt_am=mangel.erledigt_am,
            rueckmeldung_status=mangel.rueckmeldung_status or "",
            ist_ueberfaellig=ist_ueberfaellig(mangel, fertig),
            plan_markierung=markierung_text,
            foto_pfade=[
                str(get_absolute_path(f.dateipfad))
                for f in mangel.fotos
                if get_absolute_path(f.dateipfad).is_file()
            ],
            # Nur bei internem Export überhaupt gefüllt — siehe Docstring.
            interne_bemerkung=(mangel.interne_bemerkung or "") if intern else "",
        ))

    gewerk = db.get(Gewerk, gewerk_id) if gewerk_id is not None else None
    daten = MaengellisteJSON(
        projekt=projekt.name,
        stand=date.today(),
        filter_beschreibung=_filter_beschreibung(
            projekt, status, gewerk, prioritaet, ueberfaellig
        ),
        intern=intern,
        maengel=eintraege,
    )

    pfad = generate_maengelliste(daten)
    return FileResponse(
        pfad,
        filename=pfad.name,
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Fotos und Dateien (feststehende Pfade)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/fotos/{foto_id}/bild")
def foto_bild(foto_id: int, thumb: bool = False, db: Session = Depends(get_db)):
    """Liefert ein Foto aus — mit ``thumb=true`` als kleines Vorschaubild."""
    foto = db.get(MangelFoto, foto_id)
    if not foto:
        raise HTTPException(404, "Foto nicht gefunden")

    pfad = get_absolute_path(foto.dateipfad)
    if not pfad.is_file():
        raise HTTPException(404, "Bilddatei nicht gefunden")

    if thumb:
        vorschau = bilder.thumbnail(pfad)
        if vorschau is not None:
            pfad = vorschau

    return FileResponse(
        pfad,
        # Fotos werden nach dem Upload nicht mehr verändert — der Browser darf
        # sie behalten, das spart auf der Baustelle Datenvolumen.
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.patch("/fotos/{foto_id}", response_model=MangelFotoResponse)
def update_foto(foto_id: int, data: MangelFotoUpdate, db: Session = Depends(get_db)):
    foto = db.get(MangelFoto, foto_id)
    if not foto:
        raise HTTPException(404, "Foto nicht gefunden")
    for feld, wert in data.model_dump(exclude_unset=True).items():
        setattr(foto, feld, wert)
    db.commit()
    db.refresh(foto)
    return foto


@router.delete("/fotos/{foto_id}", status_code=204)
def delete_foto(foto_id: int, db: Session = Depends(get_db)):
    foto = db.get(MangelFoto, foto_id)
    if not foto:
        raise HTTPException(404, "Foto nicht gefunden")
    bilder.loesche_mit_thumbnail(get_absolute_path(foto.dateipfad))
    db.delete(foto)
    db.commit()


@router.get("/dateien/{datei_id}/download")
def download_datei(datei_id: int, db: Session = Depends(get_db)):
    datei = db.get(MangelDatei, datei_id)
    if not datei:
        raise HTTPException(404, "Datei nicht gefunden")
    pfad = get_absolute_path(datei.dateipfad)
    if not pfad.is_file():
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(pfad, filename=datei.dateiname)


@router.delete("/dateien/{datei_id}", status_code=204)
def delete_datei(datei_id: int, db: Session = Depends(get_db)):
    datei = db.get(MangelDatei, datei_id)
    if not datei:
        raise HTTPException(404, "Datei nicht gefunden")
    pfad = get_absolute_path(datei.dateipfad)
    try:
        if pfad.is_file():
            pfad.unlink()
    except OSError:
        pass
    db.delete(datei)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Mangel anlegen, lesen, ändern, löschen
# ─────────────────────────────────────────────────────────────────────────────


@router.post("", response_model=MangelResponse, status_code=201)
def create_mangel(
    data: MangelCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if not db.get(Projekt, data.projekt_id):
        raise HTTPException(400, "Projekt nicht gefunden")
    if data.gewerk_id is not None and not db.get(Gewerk, data.gewerk_id):
        raise HTTPException(400, "Gewerk nicht gefunden")

    werte = data.model_dump()
    nummer = (werte.pop("nummer") or "").strip() or naechste_nummer(db, data.projekt_id)
    werte["erstellt_am"] = werte.get("erstellt_am") or date.today()

    mangel = Mangel(nummer=nummer, **werte)
    db.add(mangel)
    db.commit()
    db.refresh(mangel)

    # Autosend nur, wenn die Firma auch erreichbar ist. Sonst greift der
    # Fallback auf manuellen Versand und die Antwort trägt den Fehlertext.
    autosend_gewollt = mangel.mail_autosend
    erzwinge_manuellen_versand(mangel)
    db.commit()
    db.refresh(mangel)

    if autosend_gewollt and mangel.mail_autosend:
        background_tasks.add_task(_run_autosend, mangel.id)
    else:
        # Teams-Nachricht "Neuer Mangel" — passiert nur, wenn irgendwo ein
        # Webhook hinterlegt ist (Gewerk, Projekt oder global).
        background_tasks.add_task(_run_benachrichtigung, mangel.id, "neu")

    return _detail(db, mangel)


@router.get("/{mangel_id}", response_model=MangelResponse)
def get_mangel(mangel_id: int, db: Session = Depends(get_db)):
    return _detail(db, _hole_mangel(db, mangel_id))


@router.patch("/{mangel_id}", response_model=MangelResponse)
def update_mangel(
    mangel_id: int,
    data: MangelUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    mangel = _hole_mangel(db, mangel_id)
    aenderungen = data.model_dump(exclude_unset=True)

    if "gewerk_id" in aenderungen and aenderungen["gewerk_id"] is not None:
        if not db.get(Gewerk, aenderungen["gewerk_id"]):
            raise HTTPException(400, "Gewerk nicht gefunden")

    alter_status = mangel.status
    alte_frist = aktuelle_frist(mangel)

    for feld, wert in aenderungen.items():
        setattr(mangel, feld, wert)

    # "1. Nachfrist gesetzt" ist das Datum, an dem die Nachfrist vergeben
    # wurde. Wer nur ein Nachfristende einträgt, meint damit "heute gesetzt".
    if mangel.erste_nachfrist_bis and not mangel.erste_nachfrist_gesetzt_am:
        mangel.erste_nachfrist_gesetzt_am = date.today()

    fehler = erzwinge_manuellen_versand(mangel)
    db.commit()
    db.refresh(mangel)

    if mangel.status != alter_status:
        background_tasks.add_task(_run_benachrichtigung, mangel.id, "status")
    elif aktuelle_frist(mangel) != alte_frist:
        background_tasks.add_task(_run_benachrichtigung, mangel.id, "frist")

    antwort = _detail(db, mangel)
    if fehler:
        antwort.mail_fehler = fehler
    return antwort


@router.delete("/{mangel_id}", status_code=204)
def delete_mangel(mangel_id: int, db: Session = Depends(get_db)):
    """Löscht einen Mangel samt Fotos, Anhängen und Plan-Markierung."""
    mangel = _hole_mangel(db, mangel_id)
    delete_mangel_cascade(db, mangel)
    db.commit()


@router.post("/{mangel_id}/duplizieren", response_model=MangelResponse,
             status_code=201)
def duplizieren(mangel_id: int, db: Session = Depends(get_db)):
    """"Duplikat NU erstellen" — Kopie für einen weiteren Nachunternehmer.

    Nummer bekommt ein fortlaufendes Punkt-Suffix, ``eltern_mangel_id`` zeigt
    auf das Original. Details siehe app.services.mangel_logik.
    """
    original = _hole_mangel(db, mangel_id)
    kopie = duplikat_erstellen(db, original)
    return _detail(db, kopie)


# ─────────────────────────────────────────────────────────────────────────────
# Fotos, Anhänge, Plan-Markierung eines Mangels
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{mangel_id}/fotos", response_model=list[MangelFotoResponse],
             status_code=201)
async def upload_fotos(
    mangel_id: int,
    dateien: list[UploadFile] = File(...),
    bildunterschrift: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    """Nimmt ein oder mehrere Fotos zu einem Mangel an.

    Jedes Foto wird serverseitig noch einmal auf Handy-taugliche Maße gebracht
    und nach EXIF gedreht (siehe app.services.bilder) — auch wenn das Frontend
    das schon vor dem Upload tut.
    """
    mangel = _hole_mangel(db, mangel_id)
    if len(dateien) > MAX_FOTOS_PRO_UPLOAD:
        raise HTTPException(400, f"Maximal {MAX_FOTOS_PRO_UPLOAD} Fotos pro Upload")

    letzte_reihenfolge = (
        db.query(func.max(MangelFoto.reihenfolge))
        .filter(MangelFoto.mangel_id == mangel_id)
        .scalar()
    ) or 0

    grenze = settings.max_file_size_mb * 1024 * 1024
    neue: list[MangelFoto] = []
    for datei in dateien:
        rohdaten = await datei.read()
        if len(rohdaten) > grenze:
            raise HTTPException(
                400,
                f"'{datei.filename}' ist größer als {settings.max_file_size_mb} MB",
            )
        inhalt, name = bilder.normalisiere_foto(rohdaten, datei.filename or "foto.jpg")
        datei.filename = name
        rel_pfad = await save_upload_in(
            f"maengel/{mangel.id}/fotos", datei, inhalt=inhalt
        )
        letzte_reihenfolge += 1
        foto = MangelFoto(
            mangel_id=mangel.id,
            dateipfad=rel_pfad,
            bildunterschrift=bildunterschrift.strip(),
            reihenfolge=letzte_reihenfolge,
        )
        db.add(foto)
        neue.append(foto)

    db.commit()
    for foto in neue:
        db.refresh(foto)
    return neue


@router.post("/{mangel_id}/dateien", response_model=list[MangelDateiResponse],
             status_code=201)
async def upload_dateien(
    mangel_id: int,
    dateien: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Sonstige Anhänge (Schriftverkehr, Prüfprotokolle, …)."""
    mangel = _hole_mangel(db, mangel_id)
    grenze = settings.max_file_size_mb * 1024 * 1024

    neue: list[MangelDatei] = []
    for datei in dateien:
        rohdaten = await datei.read()
        if len(rohdaten) > grenze:
            raise HTTPException(
                400,
                f"'{datei.filename}' ist größer als {settings.max_file_size_mb} MB",
            )
        rel_pfad = await save_upload_in(
            f"maengel/{mangel.id}/dateien", datei, inhalt=rohdaten
        )
        eintrag = MangelDatei(
            mangel_id=mangel.id,
            dateipfad=rel_pfad,
            dateiname=(datei.filename or "Anhang"),
        )
        db.add(eintrag)
        neue.append(eintrag)

    db.commit()
    for eintrag in neue:
        db.refresh(eintrag)
    return neue


@router.put("/{mangel_id}/markierung", response_model=MangelPlanMarkierungResponse)
def setze_markierung(
    mangel_id: int,
    data: MangelPlanMarkierungCreate,
    db: Session = Depends(get_db),
):
    """Setzt die Stecknadel auf einem Plan (ersetzt eine vorhandene).

    Ein Mangel hat genau eine Markierung — genau wie in der Bürosoftware
    ("Es ist keine Markierung vorhanden." bzw. eine Nadel). Das Datenmodell
    könnte mehrere tragen, die Oberfläche braucht das bisher nicht.
    """
    mangel = _hole_mangel(db, mangel_id)
    plan = db.get(ProjektPlan, data.plan_datei_id)
    if not plan:
        raise HTTPException(400, "Plan nicht gefunden")
    if plan.projekt_id != mangel.projekt_id:
        raise HTTPException(400, "Der Plan gehört zu einem anderen Projekt")
    if data.seite < 1 or data.seite > plan.seiten:
        raise HTTPException(400, f"Der Plan hat {plan.seiten} Seite(n)")

    db.query(MangelPlanMarkierung).filter(
        MangelPlanMarkierung.mangel_id == mangel_id
    ).delete(synchronize_session=False)

    markierung = MangelPlanMarkierung(
        mangel_id=mangel_id,
        plan_datei_id=data.plan_datei_id,
        x_prozent=data.x_prozent,
        y_prozent=data.y_prozent,
        seite=data.seite,
    )
    db.add(markierung)
    db.commit()
    db.refresh(markierung)

    antwort = MangelPlanMarkierungResponse.model_validate(markierung)
    antwort.plan_dateiname = plan.dateiname
    return antwort


@router.delete("/{mangel_id}/markierung", status_code=204)
def loesche_markierung(mangel_id: int, db: Session = Depends(get_db)):
    _hole_mangel(db, mangel_id)
    db.query(MangelPlanMarkierung).filter(
        MangelPlanMarkierung.mangel_id == mangel_id
    ).delete(synchronize_session=False)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Versand
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{mangel_id}/senden", response_model=MangelVersandErgebnis)
async def jetzt_senden(mangel_id: int, db: Session = Depends(get_db)):
    """"Jetzt senden": Mängelrüge an die zuständige Firma melden.

    Fehlt die E-Mail-Adresse am Gewerk, kommt der Fehlertext aus
    app.services.mangel_versand zurück (HTTP 200 mit ``versendet: false``) —
    die Oberfläche zeigt ihn rot an, so wie im Formular vorgesehen.
    """
    mangel = _hole_mangel(db, mangel_id)
    versendet, kanal, nachricht = await sende_mangelruege(db, mangel)
    db.refresh(mangel)
    return MangelVersandErgebnis(
        mangel_id=mangel.id,
        versendet=versendet,
        kanal=kanal,
        nachricht=nachricht,
        zuletzt_versendet_am=mangel.zuletzt_versendet_am,
    )
