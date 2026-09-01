"""Baubesprechungsprotokolle: anlegen, auswerten, prüfen, freigeben, erzeugen.

DER PUNKT, AN DEM DIESES MODUL STEHT ODER FÄLLT
===============================================
Ein Protokoll ist **kein** Behälter für die Themen einer Sitzung. Es ist ein
Schnappschuss der fortlaufenden Themenliste des Projekts. Wer das andersherum
baut — eine frische Liste je Besprechung — bekommt eine App, die schön
aussieht und die durchgehende Nachverfolgung zerstört, für die es die Liste
überhaupt gibt.

Daraus folgen drei Regeln, die dieses Modul durchsetzt:

1. **Anlegen** (``POST /``) beginnt nie leer. Jede noch nicht erledigte Zeile
   des letzten Protokolls wird unverändert übernommen — Text, Zuständige,
   Frist, Status und vor allem die alte BB-Nummer. Siehe
   ``_uebernimm_offene_punkte``.

2. **Auswerten** (``/analysieren``) ordnet zu, statt neu zu erfinden. Die
   offenen Themen gehen in den Prompt; erkennt die Analyse einen Punkt als
   Fortschreibung, wird die vorhandene Zeile aktualisiert und bekommt die
   BB-Nummer dieser Sitzung. Nur wirklich Neues legt ein neues Thema an.

3. **Freigeben** (``/freigeben``) schreibt die Zeilen in die Themenliste
   fort und setzt ``erledigt_am`` ausschließlich dort, wo ein Mensch den
   Status auf "e" gesetzt hat. Nicht besprochen heißt nicht erledigt — ein
   Thema verschwindet nur, wenn jemand es ausdrücklich abhakt.

Erst nach der Freigabe entsteht das Word-Dokument. Vorher gibt es keinen
Endpunkt, der eine Datei ausliefert.

Feste Pfade stehen vor Pfaden mit ``/{protokoll_id}`` — FastAPI prüft in
Registrierungsreihenfolge.
"""

from __future__ import annotations

from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import (
    Bearbeiter,
    BesprechungsAnlage,
    BesprechungsKapitel,
    BesprechungsTeilnehmer,
    BesprechungsThema,
    BesprechungsThemaUpdate,
    Besprechungsprotokoll,
    Gewerk,
    Projekt,
    Projektbeteiligter,
)
from app.schemas import (
    AnalyseErgebnis,
    AnlageResponse,
    BesprechungsKapitelCreate,
    BesprechungsKapitelResponse,
    BesprechungsKapitelUpdate,
    BesprechungsThemaResponse,
    ProjektbeteiligterCreate,
    ProjektbeteiligterResponse,
    ProjektbeteiligterUpdate,
    ProtokollCreate,
    ProtokollFreigabe,
    ProtokollListItem,
    ProtokollResponse,
    ProtokollUpdate,
    TeilnehmerCreate,
    TeilnehmerResponse,
    TeilnehmerUpdate,
    ThemaUpdateAendern,
    ThemaUpdateCreate,
    ThemaUpdateResponse,
    TldvImport,
)
from app.services import besprechung_analyse as analyse
from app.services import besprechung_lokal as lokal
from app.services import besprechungsprotokoll_generation as erzeugung
from app.services import word_pdf
from app.utils.file_storage import get_absolute_path, save_upload_in

router = APIRouter(prefix="/besprechungsprotokolle", tags=["besprechungsprotokolle"])

#: Status, in dem ein Thema als abgeschlossen gilt. Nur diese Zeilen werden
#: beim nächsten Protokoll nicht mehr mitgenommen.
ERLEDIGT = "e"

#: Kapitel 1 heißt in jedem HPP-Protokoll gleich und gehört zu keinem Gewerk.
ALLGEMEIN_NUMMER = "01."
ALLGEMEIN_TITEL = "Allgemein/ Projektorganisation"


# ─────────────────────────────────────────────────────────────────────────────
# Kleine Helfer
# ─────────────────────────────────────────────────────────────────────────────


def _hole(db: Session, protokoll_id: int) -> Besprechungsprotokoll:
    protokoll = db.get(Besprechungsprotokoll, protokoll_id)
    if protokoll is None:
        raise HTTPException(404, "Besprechungsprotokoll nicht gefunden")
    return protokoll


def _hole_projekt(db: Session, projekt_id: int) -> Projekt:
    projekt = db.get(Projekt, projekt_id)
    if projekt is None:
        raise HTTPException(404, "Projekt nicht gefunden")
    return projekt


def _pruefe_offen(protokoll: Besprechungsprotokoll) -> None:
    """Ein freigegebenes Protokoll ist ein Dokument, kein Entwurf mehr."""
    if protokoll.status == "freigegeben":
        raise HTTPException(
            409,
            "Dieses Protokoll ist freigegeben und kann nicht mehr geändert "
            "werden. Für Korrekturen bitte ein neues Protokoll anlegen — die "
            "offenen Punkte werden dabei übernommen.",
        )


def _naechste_nummer(db: Session, projekt_id: int) -> int:
    hoechste = (
        db.query(func.max(Besprechungsprotokoll.nummer))
        .filter(Besprechungsprotokoll.projekt_id == projekt_id)
        .scalar()
    )
    return int(hoechste or 0) + 1


def _vorheriges(
    db: Session, projekt_id: int, nummer: int
) -> Besprechungsprotokoll | None:
    """Das Protokoll mit der nächstkleineren Nummer desselben Projekts."""
    return (
        db.query(Besprechungsprotokoll)
        .filter(
            Besprechungsprotokoll.projekt_id == projekt_id,
            Besprechungsprotokoll.nummer < nummer,
        )
        .order_by(Besprechungsprotokoll.nummer.desc())
        .first()
    )


def _naechste_inhalt_nr(db: Session, kapitel_id: int) -> str:
    """Nächste freie laufende Nummer innerhalb eines Kapitels.

    Zweistellig wie im Original ("08"), aber ohne Begrenzung nach oben.
    """
    vorhandene = [
        t.inhalt_nr
        for t in db.query(BesprechungsThema)
        .filter(BesprechungsThema.kapitel_id == kapitel_id)
        .all()
    ]
    zahlen = []
    for wert in vorhandene:
        ziffern = "".join(c for c in str(wert) if c.isdigit())
        if ziffern:
            zahlen.append(int(ziffern))
    return f"{(max(zahlen) + 1) if zahlen else 1:02d}"


def _zweistellig(wert: str) -> str:
    """"2." -> "02.", "01." -> "01." — die Schreibweise der Themenzeilen.

    Im Kapitelbalken steht die Nummer so, wie sie gepflegt wurde ("2."); in
    der Zeile darunter immer zweistellig ("02. 08. 16"). Das ist im Original
    genauso und soll in der Oberfläche nicht anders aussehen als im Dokument.
    """
    ziffern = "".join(c for c in str(wert or "") if c.isdigit())
    return f"{int(ziffern):02d}." if ziffern else str(wert or "")


def _kennung(thema: BesprechungsThema) -> str:
    kapitel = _zweistellig(thema.kapitel.nummer) if thema.kapitel else ""
    return f"{kapitel} {_zweistellig(thema.inhalt_nr)}"


def _adresszeilen(projekt: Projekt) -> list[str]:
    """Die Adresse des Projekts als Zeilen für den Kopfblock.

    ``Projekt.adresse`` ist ein Freitextfeld; im Büro steht dort meist
    "Weidenstieg 29, 20259 Hamburg". Kommas und Zeilenumbrüche trennen.
    """
    roh = (projekt.adresse or "").replace(";", ",")
    zeilen: list[str] = []
    for stueck in roh.splitlines():
        zeilen.extend(teil.strip() for teil in stueck.split(","))
    return [z for z in zeilen if z]


# ─────────────────────────────────────────────────────────────────────────────
# Umwandlung Datenbank -> Antwort
# ─────────────────────────────────────────────────────────────────────────────


def _sortierschluessel(update: BesprechungsThemaUpdate) -> tuple:
    """Reihenfolge im Protokoll: Kapitel, dann Thema-Nummer, dann BB.

    Genau die Ordnung des Ausdrucks — "02. 08. 10" steht vor "02. 08. 15",
    und beide vor "02. 09. 02".
    """
    thema = update.thema
    kapitel = thema.kapitel if thema else None

    def zahl(wert: str) -> int:
        ziffern = "".join(c for c in str(wert or "") if c.isdigit())
        return int(ziffern) if ziffern else 0

    return (
        kapitel.sortierung if kapitel else 0,
        zahl(kapitel.nummer) if kapitel else 0,
        zahl(thema.inhalt_nr) if thema else 0,
        zahl(update.bb_nr),
        update.sortierung,
        update.id,
    )


def _zu_update_antwort(
    update: BesprechungsThemaUpdate,
    vorher: BesprechungsThemaUpdate | None = None,
) -> ThemaUpdateResponse:
    antwort = ThemaUpdateResponse.model_validate(update)
    thema = update.thema
    kapitel = thema.kapitel if thema else None
    antwort.bb_nr = update.bb_nr
    antwort.inhalt_nr = thema.inhalt_nr if thema else ""
    antwort.kapitel_id = kapitel.id if kapitel else 0
    antwort.kapitel_nummer = kapitel.nummer if kapitel else ""
    antwort.kapitel_titel = kapitel.titel if kapitel else ""
    antwort.nummer = f"{_kennung(thema)} {update.bb_nr}" if thema else update.bb_nr
    antwort.uebernommen = update.herkunft == "fortschreibung"
    if vorher is not None:
        antwort.vorher_text = vorher.thema_text
        antwort.vorher_status = vorher.status
        antwort.vorher_bb = int(vorher.bb_nr) if vorher.bb_nr.isdigit() else None
    return antwort


def _vorherige_staende(
    db: Session, protokoll: Besprechungsprotokoll
) -> dict[int, BesprechungsThemaUpdate]:
    """Der Stand jedes Themas im vorherigen Protokoll — für die Prüfansicht."""
    vorher = _vorheriges(db, protokoll.projekt_id, protokoll.nummer)
    if vorher is None:
        return {}
    return {u.thema_id: u for u in vorher.themen_updates}


def _zu_listitem(protokoll: Besprechungsprotokoll) -> ProtokollListItem:
    eintrag = ProtokollListItem.model_validate(protokoll)
    eintrag.projekt_name = protokoll.projekt.name if protokoll.projekt else ""
    eintrag.anzahl_themen = len(protokoll.themen_updates)
    eintrag.anzahl_offen = sum(
        1 for u in protokoll.themen_updates if u.status != ERLEDIGT
    )
    eintrag.anzahl_teilnehmer = len(protokoll.teilnehmer)
    eintrag.anzahl_anlagen = len(protokoll.anlagen)
    eintrag.anzahl_ungeprueft = sum(
        1 for u in protokoll.themen_updates if not u.bestaetigt
    )
    eintrag.hat_transkript = bool(
        protokoll.tldv_transkript_roh or protokoll.tldv_notizen_roh
    )
    eintrag.hat_dokument = bool(protokoll.dokument_pfad)
    eintrag.hat_pdf = bool(protokoll.pdf_pfad)
    return eintrag


def _zu_detail(db: Session, protokoll: Besprechungsprotokoll) -> ProtokollResponse:
    antwort = ProtokollResponse.model_validate(protokoll)
    basis = _zu_listitem(protokoll)
    for feld, wert in basis.model_dump().items():
        setattr(antwort, feld, wert)

    projekt = protokoll.projekt
    antwort.projekt_nummer = projekt.projekt_nummer if projekt else ""
    antwort.bauherr = projekt.bauherr if projekt else ""
    antwort.projekt_adresse = projekt.adresse if projekt else ""
    antwort.analyse_hinweise = list(protokoll.analyse_hinweise or [])

    vorher = _vorherige_staende(db, protokoll)
    antwort.themen_updates = [
        _zu_update_antwort(u, vorher.get(u.thema_id))
        for u in sorted(protokoll.themen_updates, key=_sortierschluessel)
    ]
    antwort.teilnehmer = [
        TeilnehmerResponse.model_validate(t) for t in protokoll.teilnehmer
    ]
    antwort.anlagen = [AnlageResponse.model_validate(a) for a in protokoll.anlagen]
    return antwort


# ─────────────────────────────────────────────────────────────────────────────
# Kapitel (Stammdaten je Projekt)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/kapitel", response_model=list[BesprechungsKapitelResponse])
def kapitel_liste(projekt_id: int = Query(...), db: Session = Depends(get_db)):
    kapitel = (
        db.query(BesprechungsKapitel)
        .filter(BesprechungsKapitel.projekt_id == projekt_id)
        .order_by(BesprechungsKapitel.sortierung, BesprechungsKapitel.id)
        .all()
    )
    antworten = []
    for eintrag in kapitel:
        antwort = BesprechungsKapitelResponse.model_validate(eintrag)
        antwort.anzahl_themen = len(eintrag.themen)
        antworten.append(antwort)
    return antworten


@router.post("/kapitel", response_model=BesprechungsKapitelResponse, status_code=201)
def kapitel_anlegen(daten: BesprechungsKapitelCreate, db: Session = Depends(get_db)):
    _hole_projekt(db, daten.projekt_id)
    kapitel = BesprechungsKapitel(**daten.model_dump())
    if not kapitel.sortierung:
        hoechste = (
            db.query(func.max(BesprechungsKapitel.sortierung))
            .filter(BesprechungsKapitel.projekt_id == daten.projekt_id)
            .scalar()
        )
        kapitel.sortierung = int(hoechste or 0) + 1
    db.add(kapitel)
    db.commit()
    db.refresh(kapitel)
    return BesprechungsKapitelResponse.model_validate(kapitel)


@router.post("/kapitel/aus-gewerken", response_model=list[BesprechungsKapitelResponse])
def kapitel_aus_gewerken(projekt_id: int = Query(...), db: Session = Depends(get_db)):
    """Legt die Kapitelliste aus den Vergabeeinheiten des Projekts an.

    Kapitel 1 ist immer "Allgemein/ Projektorganisation" und hängt an keinem
    Gewerk; danach kommt je Vergabeeinheit ein Kapitel, benannt wie im
    Protokoll: "VE01 Erweiterte Rohbauarbeiten - Rolfes Bau (VE300.01)".

    Ruft man das ein zweites Mal auf, kommen nur die Gewerke dazu, für die
    noch kein Kapitel existiert — bereits umbenannte Kapitel bleiben, wie sie
    sind.
    """
    _hole_projekt(db, projekt_id)
    vorhanden = (
        db.query(BesprechungsKapitel)
        .filter(BesprechungsKapitel.projekt_id == projekt_id)
        .all()
    )
    belegte_gewerke = {k.gewerk_id for k in vorhanden if k.gewerk_id}
    sortierung = max([k.sortierung for k in vorhanden], default=0)

    if not any(k.gewerk_id is None for k in vorhanden):
        sortierung += 1
        db.add(BesprechungsKapitel(
            projekt_id=projekt_id,
            nummer=ALLGEMEIN_NUMMER,
            titel=ALLGEMEIN_TITEL,
            sortierung=sortierung,
        ))

    gewerke = (
        db.query(Gewerk)
        .filter(Gewerk.projekt_id == projekt_id)
        .order_by(Gewerk.vergabeeinheit_code, Gewerk.id)
        .all()
    )
    for gewerk in gewerke:
        if gewerk.id in belegte_gewerke:
            continue
        sortierung += 1
        teile = [
            t for t in (gewerk.vergabeeinheit_bezeichnung, gewerk.firma_name) if t
        ]
        titel = " - ".join(teile) or gewerk.firma_name
        if gewerk.vergabeeinheit_code:
            titel = f"{titel} ({gewerk.vergabeeinheit_code})"
        db.add(BesprechungsKapitel(
            projekt_id=projekt_id,
            nummer=f"{sortierung}.",
            titel=titel,
            sortierung=sortierung,
            gewerk_id=gewerk.id,
        ))

    db.commit()
    return kapitel_liste(projekt_id=projekt_id, db=db)


@router.patch("/kapitel/{kapitel_id}", response_model=BesprechungsKapitelResponse)
def kapitel_aendern(
    kapitel_id: int, daten: BesprechungsKapitelUpdate, db: Session = Depends(get_db)
):
    kapitel = db.get(BesprechungsKapitel, kapitel_id)
    if kapitel is None:
        raise HTTPException(404, "Kapitel nicht gefunden")
    for feld, wert in daten.model_dump(exclude_unset=True).items():
        setattr(kapitel, feld, wert)
    db.commit()
    db.refresh(kapitel)
    antwort = BesprechungsKapitelResponse.model_validate(kapitel)
    antwort.anzahl_themen = len(kapitel.themen)
    return antwort


@router.delete("/kapitel/{kapitel_id}", status_code=204)
def kapitel_loeschen(kapitel_id: int, db: Session = Depends(get_db)):
    kapitel = db.get(BesprechungsKapitel, kapitel_id)
    if kapitel is None:
        raise HTTPException(404, "Kapitel nicht gefunden")
    if kapitel.themen:
        raise HTTPException(
            409,
            f"An diesem Kapitel hängen {len(kapitel.themen)} Themen. Sie würden "
            f"ihre Nummer verlieren. Bitte die Themen erst in ein anderes "
            f"Kapitel umhängen.",
        )
    db.delete(kapitel)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Projektbeteiligte (Seite 3 des Protokolls)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/beteiligte", response_model=list[ProjektbeteiligterResponse])
def beteiligte_liste(projekt_id: int = Query(...), db: Session = Depends(get_db)):
    return [
        ProjektbeteiligterResponse.model_validate(b)
        for b in db.query(Projektbeteiligter)
        .filter(Projektbeteiligter.projekt_id == projekt_id)
        .order_by(Projektbeteiligter.sortierung, Projektbeteiligter.id)
        .all()
    ]


@router.post("/beteiligte", response_model=ProjektbeteiligterResponse, status_code=201)
def beteiligter_anlegen(
    daten: ProjektbeteiligterCreate, db: Session = Depends(get_db)
):
    _hole_projekt(db, daten.projekt_id)
    beteiligter = Projektbeteiligter(**daten.model_dump())
    if not beteiligter.sortierung:
        hoechste = (
            db.query(func.max(Projektbeteiligter.sortierung))
            .filter(Projektbeteiligter.projekt_id == daten.projekt_id)
            .scalar()
        )
        beteiligter.sortierung = int(hoechste or 0) + 1
    db.add(beteiligter)
    db.commit()
    db.refresh(beteiligter)
    return ProjektbeteiligterResponse.model_validate(beteiligter)


@router.patch("/beteiligte/{beteiligter_id}", response_model=ProjektbeteiligterResponse)
def beteiligter_aendern(
    beteiligter_id: int,
    daten: ProjektbeteiligterUpdate,
    db: Session = Depends(get_db),
):
    beteiligter = db.get(Projektbeteiligter, beteiligter_id)
    if beteiligter is None:
        raise HTTPException(404, "Projektbeteiligter nicht gefunden")
    for feld, wert in daten.model_dump(exclude_unset=True).items():
        setattr(beteiligter, feld, wert)
    db.commit()
    db.refresh(beteiligter)
    return ProjektbeteiligterResponse.model_validate(beteiligter)


@router.delete("/beteiligte/{beteiligter_id}", status_code=204)
def beteiligter_loeschen(beteiligter_id: int, db: Session = Depends(get_db)):
    beteiligter = db.get(Projektbeteiligter, beteiligter_id)
    if beteiligter is None:
        raise HTTPException(404, "Projektbeteiligter nicht gefunden")
    db.delete(beteiligter)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Die laufende Themenliste
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/themen", response_model=list[BesprechungsThemaResponse])
def themen_liste(
    projekt_id: int = Query(...),
    nur_offen: bool = Query(True),
    db: Session = Depends(get_db),
):
    """Die Themenliste des Projekts — unabhängig von einem Protokoll.

    Das ist die Liste, die über alle Besprechungen hinweg lebt.
    """
    abfrage = db.query(BesprechungsThema).filter(
        BesprechungsThema.projekt_id == projekt_id
    )
    if nur_offen:
        abfrage = abfrage.filter(BesprechungsThema.status != ERLEDIGT)
    themen = abfrage.all()

    antworten = []
    for thema in themen:
        antwort = BesprechungsThemaResponse.model_validate(thema)
        antwort.kapitel_nummer = thema.kapitel.nummer if thema.kapitel else ""
        antwort.kapitel_titel = thema.kapitel.titel if thema.kapitel else ""
        antwort.kennung = _kennung(thema)
        for feld, quelle in (
            ("zuletzt_bb", thema.zuletzt_protokoll_id),
            ("erstmals_bb", thema.erstmals_protokoll_id),
        ):
            protokoll = db.get(Besprechungsprotokoll, quelle) if quelle else None
            setattr(antwort, feld, protokoll.nummer if protokoll else None)
        antworten.append(antwort)

    antworten.sort(key=lambda a: (a.kapitel_nummer, a.inhalt_nr))
    return antworten


# ─────────────────────────────────────────────────────────────────────────────
# Protokolle
# ─────────────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[ProtokollListItem])
def liste(
    projekt_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    abfrage = db.query(Besprechungsprotokoll)
    if projekt_id is not None:
        abfrage = abfrage.filter(Besprechungsprotokoll.projekt_id == projekt_id)
    protokolle = abfrage.order_by(
        Besprechungsprotokoll.projekt_id, Besprechungsprotokoll.nummer.desc()
    ).all()
    return [_zu_listitem(p) for p in protokolle]


def _uebernimm_offene_punkte(
    db: Session,
    protokoll: Besprechungsprotokoll,
    vorheriges: Besprechungsprotokoll,
) -> int:
    """Alle noch offenen Zeilen des Vorgängers unverändert mitnehmen.

    Das Wort "unverändert" ist hier wörtlich gemeint — auch die BB-Nummer
    bleibt. Ein Punkt aus Sitzung 10, über den seither nicht gesprochen wurde,
    steht in Sitzung 16 immer noch als "02. 19. 10" da und nicht als
    "02. 19. 16". Erst wenn wirklich wieder etwas dazu gesagt wird, rückt die
    Nummer nach (siehe ``_verarbeite_vorschlaege``).

    Übernommene Zeilen gelten als geprüft: Sie standen schon einmal in einem
    freigegebenen Protokoll und haben sich nicht geändert.
    """
    anzahl = 0
    for alt in vorheriges.themen_updates:
        if alt.status == ERLEDIGT:
            continue
        db.add(BesprechungsThemaUpdate(
            protokoll_id=protokoll.id,
            ursprung_protokoll_id=alt.ursprung_protokoll_id or vorheriges.id,
            thema_id=alt.thema_id,
            thema_text=alt.thema_text,
            zustaendig=alt.zustaendig,
            bearb_bis=alt.bearb_bis,
            status=alt.status,
            hervorheben=alt.hervorheben,
            sortierung=alt.sortierung,
            herkunft="fortschreibung",
            bestaetigt=True,
        ))
        anzahl += 1
    return anzahl


@router.post("", response_model=ProtokollResponse, status_code=201)
def anlegen(daten: ProtokollCreate, db: Session = Depends(get_db)):
    """Legt einen Protokoll-Entwurf an — nie leer, wenn es Vorgänger gibt."""
    projekt = _hole_projekt(db, daten.projekt_id)

    werte = daten.model_dump(exclude={"nummer", "offene_punkte_uebernehmen"})
    protokoll = Besprechungsprotokoll(**werte)
    protokoll.nummer = daten.nummer or _naechste_nummer(db, daten.projekt_id)

    # Ersteller aus den Stammdaten vorbelegen, sofern nichts mitgegeben wurde.
    if daten.ersteller_id and not daten.ersteller_kuerzel:
        bearbeiter = db.get(Bearbeiter, daten.ersteller_id)
        if bearbeiter is not None:
            protokoll.ersteller_name = protokoll.ersteller_name or bearbeiter.name
            protokoll.ersteller_kuerzel = bearbeiter.kuerzel
            protokoll.ersteller_durchwahl = bearbeiter.durchwahl
            protokoll.ersteller_email = protokoll.ersteller_email or (
                bearbeiter.email or ""
            )

    db.add(protokoll)
    db.commit()
    db.refresh(protokoll)

    if daten.offene_punkte_uebernehmen:
        vorheriges = _vorheriges(db, projekt.id, protokoll.nummer)
        if vorheriges is not None:
            _uebernimm_offene_punkte(db, protokoll, vorheriges)
            db.commit()
            db.refresh(protokoll)

    return _zu_detail(db, protokoll)


@router.get("/{protokoll_id}", response_model=ProtokollResponse)
def detail(protokoll_id: int, db: Session = Depends(get_db)):
    return _zu_detail(db, _hole(db, protokoll_id))


@router.patch("/{protokoll_id}", response_model=ProtokollResponse)
def aendern(
    protokoll_id: int, daten: ProtokollUpdate, db: Session = Depends(get_db)
):
    protokoll = _hole(db, protokoll_id)
    _pruefe_offen(protokoll)
    for feld, wert in daten.model_dump(exclude_unset=True).items():
        setattr(protokoll, feld, wert)
    db.commit()
    db.refresh(protokoll)
    return _zu_detail(db, protokoll)


@router.delete("/{protokoll_id}", status_code=204)
def loeschen(protokoll_id: int, db: Session = Depends(get_db)):
    protokoll = _hole(db, protokoll_id)
    if protokoll.status == "freigegeben":
        raise HTTPException(
            409,
            "Ein freigegebenes Protokoll wird nicht gelöscht — es ist Teil der "
            "Projektakte.",
        )
    db.delete(protokoll)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# tl;dv-Import und Analyse
# ─────────────────────────────────────────────────────────────────────────────


def _analyse_kontext(db: Session, protokoll: Besprechungsprotokoll):
    """Was die Analyse über das Projekt wissen muss."""
    kapitel = (
        db.query(BesprechungsKapitel)
        .filter(BesprechungsKapitel.projekt_id == protokoll.projekt_id)
        .order_by(BesprechungsKapitel.sortierung, BesprechungsKapitel.id)
        .all()
    )
    beteiligte = (
        db.query(Projektbeteiligter)
        .filter(Projektbeteiligter.projekt_id == protokoll.projekt_id)
        .order_by(Projektbeteiligter.sortierung)
        .all()
    )
    # Die offenen Themen des Projekts — der Kern des Prompts. Der aktuelle
    # Stand kommt, wo vorhanden, aus der Zeile dieses Protokolls: Was hier
    # schon steht, ist die Fassung, die die Analyse fortschreiben soll.
    hier = {u.thema_id: u for u in protokoll.themen_updates}
    offene = []
    for thema in (
        db.query(BesprechungsThema)
        .filter(
            BesprechungsThema.projekt_id == protokoll.projekt_id,
            BesprechungsThema.status != ERLEDIGT,
        )
        .all()
    ):
        stand = hier.get(thema.id)
        offene.append(analyse.OffenesThema(
            id=thema.id,
            kennung=_kennung(thema),
            kapitel=thema.kapitel.titel if thema.kapitel else "",
            text=stand.thema_text if stand else thema.thema,
            zustaendig=stand.zustaendig if stand else thema.zustaendig,
            bearb_bis=stand.bearb_bis if stand else thema.bearb_bis,
            status=stand.status if stand else thema.status,
        ))
    offene.sort(key=lambda t: t.kennung)

    return (
        offene,
        [analyse.KapitelInfo(id=k.id, nummer=k.nummer, titel=k.titel) for k in kapitel],
        [
            analyse.BeteiligterInfo(
                kuerzel=b.kuerzel, name=b.name, rolle=b.rolle,
                ansprechpartner=b.ansprechpartner,
            )
            for b in beteiligte
        ],
    )


def _verarbeite_vorschlaege(
    db: Session,
    protokoll: Besprechungsprotokoll,
    ergebnis: analyse.AnalyseErgebnis,
) -> tuple[int, int]:
    """Vorschläge als Entwurfszeilen speichern. Gibt (neu, fortgeschrieben)."""
    vorhandene = {u.thema_id: u for u in protokoll.themen_updates}
    neu = fortgeschrieben = 0

    for vorschlag in ergebnis.themen:
        if vorschlag.thema_id is not None:
            thema = db.get(BesprechungsThema, vorschlag.thema_id)
            if thema is None:
                continue
            zeile = vorhandene.get(thema.id)
            if zeile is None:
                # Das Thema war nicht im Protokoll (z. B. weil es aus einer
                # älteren Sitzung stammt) — es kommt jetzt dazu.
                zeile = BesprechungsThemaUpdate(
                    protokoll_id=protokoll.id, thema_id=thema.id
                )
                db.add(zeile)
                vorhandene[thema.id] = zeile
            # Zu diesem Punkt wurde heute etwas gesagt: Die BB-Nummer rückt
            # auf die laufende Sitzung.
            zeile.ursprung_protokoll_id = protokoll.id
            fortgeschrieben += 1
        else:
            thema = BesprechungsThema(
                projekt_id=protokoll.projekt_id,
                kapitel_id=vorschlag.kapitel_id,
                inhalt_nr=_naechste_inhalt_nr(db, vorschlag.kapitel_id),
                thema=vorschlag.text,
                erstmals_protokoll_id=protokoll.id,
            )
            db.add(thema)
            db.flush()
            zeile = BesprechungsThemaUpdate(
                protokoll_id=protokoll.id,
                ursprung_protokoll_id=protokoll.id,
                thema_id=thema.id,
            )
            db.add(zeile)
            vorhandene[thema.id] = zeile
            neu += 1

        zeile.thema_text = vorschlag.text
        zeile.zustaendig = vorschlag.zustaendig
        zeile.bearb_bis = vorschlag.bearb_bis
        zeile.status = vorschlag.status
        zeile.herkunft = "ki"
        # Der ganze Sinn des Prüfschritts: Ein KI-Vorschlag ist nie bestätigt.
        zeile.bestaetigt = False

    bekannte = {t.name.strip().lower() for t in protokoll.teilnehmer}
    reihenfolge = len(protokoll.teilnehmer)
    for person in ergebnis.teilnehmer:
        if person.name.strip().lower() in bekannte:
            continue
        # Firma und Telefon aus den Stammdaten vorschlagen — tl;dv liefert
        # beides nicht, und geraten wird hier nichts: Wer nicht eindeutig
        # zugeordnet werden kann, bekommt leere Felder und muss beim Prüfen
        # ergänzt werden.
        telefon = ""
        if person.firma_kuerzel:
            stamm = (
                db.query(Projektbeteiligter)
                .filter(
                    Projektbeteiligter.projekt_id == protokoll.projekt_id,
                    func.upper(Projektbeteiligter.kuerzel) == person.firma_kuerzel,
                )
                .first()
            )
            if stamm is not None:
                telefon = stamm.telefon
        reihenfolge += 1
        db.add(BesprechungsTeilnehmer(
            protokoll_id=protokoll.id,
            name=person.name,
            firma_kuerzel=person.firma_kuerzel,
            telefon=telefon,
            reihenfolge=reihenfolge,
            aus_transkript=True,
        ))
        bekannte.add(person.name.strip().lower())

    return neu, fortgeschrieben


async def _fuehre_analyse(
    db: Session, protokoll: Besprechungsprotokoll
) -> AnalyseErgebnis:
    offene, kapitel, beteiligte = _analyse_kontext(db, protokoll)
    if not kapitel:
        raise HTTPException(
            409,
            "Für dieses Projekt sind noch keine Kapitel angelegt. Neue Themen "
            "hätten keine Nummer. Unter „Kapitel“ die Liste aus den Gewerken "
            "erzeugen oder von Hand anlegen.",
        )

    argumente = dict(
        transkript=protokoll.tldv_transkript_roh,
        notizen=protokoll.tldv_notizen_roh,
        offene_themen=offene,
        kapitel=kapitel,
        beteiligte=beteiligte,
        projektname=protokoll.projekt.name if protokoll.projekt else "",
        besprechungsdatum=protokoll.besprechungsdatum.strftime("%d.%m.%Y"),
    )

    # ── Welcher Weg? ──
    #
    # Die Auswertung funktioniert IMMER. Ein Anthropic-Schlüssel macht sie
    # besser, ist aber keine Voraussetzung: Ohne ihn übernimmt die
    # regelbasierte Auswertung (app.services.besprechung_lokal), die
    # dieselben Vorschläge in derselben Form liefert — nur mechanisch statt
    # mit Sprachverständnis. Früher stand hier ein 422 und die Funktion war
    # für jeden ohne Schlüssel tot.
    if not analyse.ist_verfuegbar():
        return _als_bericht(
            protokoll, lokal.analysiere(**argumente), db
        )

    try:
        ergebnis = await analyse.analysiere(**argumente)
    except analyse.AnalyseFehler as fehler:
        # Netz weg, Kontingent leer, Schlüssel abgelaufen: Statt den Anwender
        # vor einer toten Schaltfläche stehen zu lassen, wird ohne KI
        # ausgewertet — und im Hinweis steht, warum.
        ergebnis = lokal.analysiere(**argumente)
        ergebnis.hinweise.insert(
            0, f"Die KI-Auswertung war nicht möglich ({fehler}). Es wurde "
               f"ohne KI ausgewertet."
        )
        return _als_bericht(protokoll, ergebnis, db)

    return _als_bericht(protokoll, ergebnis, db)


def _als_bericht(
    protokoll: Besprechungsprotokoll,
    ergebnis: analyse.AnalyseErgebnis,
    db: Session,
) -> AnalyseErgebnis:
    """Vorschläge speichern und zusammenfassen — für beide Auswertungswege."""

    neu, fortgeschrieben = _verarbeite_vorschlaege(db, protokoll, ergebnis)
    protokoll.analyse_am = datetime.now()
    protokoll.analyse_hinweise = ergebnis.hinweise
    db.commit()
    db.refresh(protokoll)

    return AnalyseErgebnis(
        neue_themen=neu,
        fortschreibungen=fortgeschrieben,
        teilnehmer=len(ergebnis.teilnehmer),
        hinweise=ergebnis.hinweise,
    )


@router.post("/{protokoll_id}/tldv-import", response_model=AnalyseErgebnis)
async def tldv_import(
    protokoll_id: int, daten: TldvImport, db: Session = Depends(get_db)
):
    """Nimmt den Rohtext aus tl;dv entgegen und stößt die Analyse an."""
    protokoll = _hole(db, protokoll_id)
    _pruefe_offen(protokoll)

    if not (daten.transkript.strip() or daten.notizen.strip()):
        raise HTTPException(
            422,
            "Es wurde weder ein Transkript noch Notizen eingefügt. In tl;dv "
            "den Text kopieren und hier einsetzen.",
        )

    protokoll.tldv_transkript_roh = daten.transkript
    protokoll.tldv_notizen_roh = daten.notizen
    db.commit()

    if not daten.analysieren:
        return AnalyseErgebnis(hinweise=["Text gespeichert, noch nicht ausgewertet."])
    return await _fuehre_analyse(db, protokoll)


@router.post("/{protokoll_id}/analysieren", response_model=AnalyseErgebnis)
async def analysieren(protokoll_id: int, db: Session = Depends(get_db)):
    """Wertet den gespeicherten Rohtext (erneut) aus."""
    protokoll = _hole(db, protokoll_id)
    _pruefe_offen(protokoll)
    if not (protokoll.tldv_transkript_roh or protokoll.tldv_notizen_roh):
        raise HTTPException(422, "Zu diesem Protokoll ist kein tl;dv-Text hinterlegt.")
    return await _fuehre_analyse(db, protokoll)


# ─────────────────────────────────────────────────────────────────────────────
# Themenzeilen von Hand
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{protokoll_id}/themen", response_model=ThemaUpdateResponse,
             status_code=201)
def thema_hinzufuegen(
    protokoll_id: int, daten: ThemaUpdateCreate, db: Session = Depends(get_db)
):
    """Eine Zeile von Hand ergänzen — neues Thema oder bestehendes aufgreifen."""
    protokoll = _hole(db, protokoll_id)
    _pruefe_offen(protokoll)

    if daten.thema_id is None and daten.kapitel_id is None:
        raise HTTPException(
            422,
            "Bitte angeben, ob die Zeile ein bestehendes Thema fortschreibt "
            "(thema_id) oder ein neues Thema ist (kapitel_id).",
        )

    if daten.thema_id is not None:
        thema = db.get(BesprechungsThema, daten.thema_id)
        if thema is None or thema.projekt_id != protokoll.projekt_id:
            raise HTTPException(404, "Thema nicht gefunden")
        vorhanden = next(
            (u for u in protokoll.themen_updates if u.thema_id == thema.id), None
        )
        if vorhanden is not None:
            raise HTTPException(
                409,
                f"Das Thema {_kennung(thema)} steht in diesem Protokoll bereits. "
                f"Bitte die vorhandene Zeile bearbeiten.",
            )
    else:
        kapitel = db.get(BesprechungsKapitel, daten.kapitel_id)
        if kapitel is None or kapitel.projekt_id != protokoll.projekt_id:
            raise HTTPException(404, "Kapitel nicht gefunden")
        thema = BesprechungsThema(
            projekt_id=protokoll.projekt_id,
            kapitel_id=kapitel.id,
            inhalt_nr=_naechste_inhalt_nr(db, kapitel.id),
            thema=daten.thema_text,
            erstmals_protokoll_id=protokoll.id,
        )
        db.add(thema)
        db.flush()

    zeile = BesprechungsThemaUpdate(
        protokoll_id=protokoll.id,
        ursprung_protokoll_id=protokoll.id,
        thema_id=thema.id,
        thema_text=daten.thema_text,
        zustaendig=daten.zustaendig,
        bearb_bis=daten.bearb_bis,
        status=daten.status,
        hervorheben=daten.hervorheben,
        sortierung=daten.sortierung,
        herkunft="mensch",
        bestaetigt=True,
    )
    db.add(zeile)
    db.commit()
    db.refresh(zeile)
    return _zu_update_antwort(
        zeile, _vorherige_staende(db, protokoll).get(zeile.thema_id)
    )


@router.patch("/{protokoll_id}/themen/{update_id}", response_model=ThemaUpdateResponse)
def thema_aendern(
    protokoll_id: int,
    update_id: int,
    daten: ThemaUpdateAendern,
    db: Session = Depends(get_db),
):
    protokoll = _hole(db, protokoll_id)
    _pruefe_offen(protokoll)
    zeile = db.get(BesprechungsThemaUpdate, update_id)
    if zeile is None or zeile.protokoll_id != protokoll.id:
        raise HTTPException(404, "Zeile nicht gefunden")

    werte = daten.model_dump(exclude_unset=True)

    neues_thema = werte.pop("thema_id", None)
    if neues_thema is not None and neues_thema != zeile.thema_id:
        ziel = db.get(BesprechungsThema, neues_thema)
        if ziel is None or ziel.projekt_id != protokoll.projekt_id:
            raise HTTPException(404, "Thema nicht gefunden")
        if any(u.thema_id == neues_thema and u.id != zeile.id
               for u in protokoll.themen_updates):
            raise HTTPException(
                409,
                f"Das Thema {_kennung(ziel)} steht in diesem Protokoll bereits.",
            )
        zeile.thema_id = neues_thema

    inhaltlich = {"thema_text", "zustaendig", "bearb_bis", "status"}
    geaendert = any(
        feld in werte and werte[feld] != getattr(zeile, feld) for feld in inhaltlich
    )
    for feld, wert in werte.items():
        setattr(zeile, feld, wert)

    # Wer eine übernommene Zeile inhaltlich anfasst, hat sie heute besprochen —
    # dann rückt auch die BB-Nummer auf diese Sitzung.
    if geaendert and zeile.herkunft == "fortschreibung":
        zeile.herkunft = "mensch"
        zeile.ursprung_protokoll_id = protokoll.id
    if "bestaetigt" not in werte and geaendert:
        zeile.bestaetigt = True

    db.commit()
    db.refresh(zeile)
    return _zu_update_antwort(
        zeile, _vorherige_staende(db, protokoll).get(zeile.thema_id)
    )


@router.delete("/{protokoll_id}/themen/{update_id}", status_code=204)
def thema_entfernen(
    protokoll_id: int, update_id: int, db: Session = Depends(get_db)
):
    """Nimmt eine Zeile aus diesem Protokoll — das Thema selbst bleibt."""
    protokoll = _hole(db, protokoll_id)
    _pruefe_offen(protokoll)
    zeile = db.get(BesprechungsThemaUpdate, update_id)
    if zeile is None or zeile.protokoll_id != protokoll.id:
        raise HTTPException(404, "Zeile nicht gefunden")
    db.delete(zeile)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Teilnehmer
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{protokoll_id}/teilnehmer", response_model=TeilnehmerResponse,
             status_code=201)
def teilnehmer_hinzufuegen(
    protokoll_id: int, daten: TeilnehmerCreate, db: Session = Depends(get_db)
):
    protokoll = _hole(db, protokoll_id)
    _pruefe_offen(protokoll)
    person = BesprechungsTeilnehmer(protokoll_id=protokoll.id, **daten.model_dump())
    if not person.reihenfolge:
        person.reihenfolge = len(protokoll.teilnehmer) + 1
    db.add(person)
    db.commit()
    db.refresh(person)
    return TeilnehmerResponse.model_validate(person)


@router.patch("/{protokoll_id}/teilnehmer/{teilnehmer_id}",
              response_model=TeilnehmerResponse)
def teilnehmer_aendern(
    protokoll_id: int,
    teilnehmer_id: int,
    daten: TeilnehmerUpdate,
    db: Session = Depends(get_db),
):
    protokoll = _hole(db, protokoll_id)
    _pruefe_offen(protokoll)
    person = db.get(BesprechungsTeilnehmer, teilnehmer_id)
    if person is None or person.protokoll_id != protokoll.id:
        raise HTTPException(404, "Teilnehmer nicht gefunden")
    for feld, wert in daten.model_dump(exclude_unset=True).items():
        setattr(person, feld, wert)
    # Von Hand angefasst heißt: nicht mehr nur ein Vorschlag aus dem Transkript.
    person.aus_transkript = False
    db.commit()
    db.refresh(person)
    return TeilnehmerResponse.model_validate(person)


@router.delete("/{protokoll_id}/teilnehmer/{teilnehmer_id}", status_code=204)
def teilnehmer_loeschen(
    protokoll_id: int, teilnehmer_id: int, db: Session = Depends(get_db)
):
    protokoll = _hole(db, protokoll_id)
    _pruefe_offen(protokoll)
    person = db.get(BesprechungsTeilnehmer, teilnehmer_id)
    if person is None or person.protokoll_id != protokoll.id:
        raise HTTPException(404, "Teilnehmer nicht gefunden")
    db.delete(person)
    db.commit()


@router.post("/{protokoll_id}/teilnehmer/aus-beteiligten",
             response_model=list[TeilnehmerResponse])
def teilnehmer_aus_beteiligten(
    protokoll_id: int, db: Session = Depends(get_db)
):
    """Übernimmt die hinterlegten Ansprechpartner als Teilnehmervorschlag.

    Für den häufigen Fall "es waren die üblichen Verdächtigen": einmal
    klicken, dann die streichen, die gefehlt haben.
    """
    protokoll = _hole(db, protokoll_id)
    _pruefe_offen(protokoll)
    bekannte = {t.name.strip().lower() for t in protokoll.teilnehmer}
    reihenfolge = len(protokoll.teilnehmer)
    for beteiligter in (
        db.query(Projektbeteiligter)
        .filter(Projektbeteiligter.projekt_id == protokoll.projekt_id)
        .order_by(Projektbeteiligter.sortierung)
        .all()
    ):
        name = (beteiligter.ansprechpartner or "").strip()
        if not name or name.lower() in bekannte:
            continue
        reihenfolge += 1
        db.add(BesprechungsTeilnehmer(
            protokoll_id=protokoll.id,
            name=name,
            firma_kuerzel=beteiligter.kuerzel,
            telefon=beteiligter.telefon,
            reihenfolge=reihenfolge,
        ))
        bekannte.add(name.lower())
    db.commit()
    db.refresh(protokoll)
    return [TeilnehmerResponse.model_validate(t) for t in protokoll.teilnehmer]


# ─────────────────────────────────────────────────────────────────────────────
# Anlagen
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{protokoll_id}/anlagen", response_model=AnlageResponse, status_code=201)
async def anlage_hochladen(
    protokoll_id: int,
    datei: UploadFile = File(...),
    bezeichnung: str = Form(""),
    db: Session = Depends(get_db),
):
    """Hängt eine Datei hinten an das Protokoll.

    Gedacht für die unterschriebene Teilnehmerliste: vor dem Termin drucken,
    vor Ort gegenzeichnen lassen, einscannen, hier hochladen. PDF und Bilder
    werden beim Erzeugen als ganzseitige Abbildungen angefügt.
    """
    protokoll = _hole(db, protokoll_id)
    _pruefe_offen(protokoll)

    pfad = await save_upload_in(
        f"besprechungsprotokolle/{protokoll.id}/anlagen", datei
    )
    anlage = BesprechungsAnlage(
        protokoll_id=protokoll.id,
        dateipfad=pfad,
        dateiname=datei.filename or "Anlage",
        bezeichnung=bezeichnung.strip(),
        reihenfolge=len(protokoll.anlagen) + 1,
    )
    db.add(anlage)
    db.commit()
    db.refresh(anlage)
    return AnlageResponse.model_validate(anlage)


@router.delete("/{protokoll_id}/anlagen/{anlage_id}", status_code=204)
def anlage_loeschen(
    protokoll_id: int, anlage_id: int, db: Session = Depends(get_db)
):
    protokoll = _hole(db, protokoll_id)
    _pruefe_offen(protokoll)
    anlage = db.get(BesprechungsAnlage, anlage_id)
    if anlage is None or anlage.protokoll_id != protokoll.id:
        raise HTTPException(404, "Anlage nicht gefunden")
    db.delete(anlage)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Freigabe und Dokument
# ─────────────────────────────────────────────────────────────────────────────


def _baue_daten(db: Session, protokoll: Besprechungsprotokoll):
    """Aus dem Datensatz die Eingabe für die Word-Erzeugung bauen."""
    projekt = protokoll.projekt

    bloecke: list[erzeugung.KapitelBlock] = []
    nach_kapitel: dict[int, erzeugung.KapitelBlock] = {}
    for zeile in sorted(protokoll.themen_updates, key=_sortierschluessel):
        thema = zeile.thema
        kapitel = thema.kapitel if thema else None
        if kapitel is None:
            continue
        block = nach_kapitel.get(kapitel.id)
        if block is None:
            block = erzeugung.KapitelBlock(nummer=kapitel.nummer, titel=kapitel.titel)
            nach_kapitel[kapitel.id] = block
            bloecke.append(block)
        block.zeilen.append(erzeugung.ThemaZeile(
            kapitel_nr=_zweistellig(kapitel.nummer),
            inhalt_nr=_zweistellig(thema.inhalt_nr),
            bb_nr=zeile.bb_nr,
            thema=zeile.thema_text,
            zustaendig=zeile.zustaendig,
            bearb_bis=zeile.bearb_bis,
            status=zeile.status,
            hervorheben=zeile.hervorheben,
        ))

    beteiligte = [
        erzeugung.BeteiligterZeile(kuerzel=b.kuerzel, name=b.name, rolle=b.rolle)
        for b in db.query(Projektbeteiligter)
        .filter(Projektbeteiligter.projekt_id == protokoll.projekt_id)
        .order_by(Projektbeteiligter.sortierung, Projektbeteiligter.id)
        .all()
    ]

    anlagen = []
    for anlage in protokoll.anlagen:
        pfad = get_absolute_path(anlage.dateipfad)
        if pfad.is_file():
            anlagen.append(erzeugung.AnlagenSeite(
                pfad=pfad, bezeichnung=anlage.bezeichnung
            ))

    return erzeugung.ProtokollDaten(
        nummer=protokoll.nummer,
        projektname=projekt.name if projekt else "",
        projekt_adresse_zeilen=_adresszeilen(projekt) if projekt else [],
        projekt_nummer=projekt.projekt_nummer if projekt else "",
        leistung=protokoll.leistung,
        bauherr=projekt.bauherr if projekt else "",
        besprechungsort=protokoll.besprechungsort,
        besprechungsdatum=protokoll.besprechungsdatum,
        erstellt_datum=date.today(),
        ersteller_name=protokoll.ersteller_name,
        ersteller_kuerzel=protokoll.ersteller_kuerzel,
        ersteller_durchwahl=protokoll.ersteller_durchwahl,
        ersteller_email=protokoll.ersteller_email,
        kapitel=bloecke,
        teilnehmer=[
            erzeugung.TeilnehmerZeile(
                name=t.name, firma=t.firma_kuerzel, telefon=t.telefon
            )
            for t in protokoll.teilnehmer
            if t.anwesend
        ],
        beteiligte=beteiligte,
        anlagen=anlagen,
    )


def _schreibe_themenliste_fort(
    db: Session, protokoll: Besprechungsprotokoll
) -> None:
    """Überträgt die Zeilen dieses Protokolls in die laufende Themenliste.

    Der aktuelle Stand eines Themas ist die Zeile mit der höchsten BB-Nummer —
    wenn ein Thema in diesem Protokoll mehrfach vorkommt (Vorgeschichte plus
    heutiger Stand), zählt die jüngste.

    ``erledigt_am`` wird ausschließlich gesetzt, wenn ein Mensch den Status
    auf "e" gestellt hat. Ein Thema, über das heute niemand gesprochen hat,
    bleibt offen — Schweigen ist keine Erledigung.
    """
    je_thema: dict[int, BesprechungsThemaUpdate] = {}
    for zeile in sorted(protokoll.themen_updates, key=_sortierschluessel):
        je_thema[zeile.thema_id] = zeile

    for thema_id, zeile in je_thema.items():
        thema = db.get(BesprechungsThema, thema_id)
        if thema is None:
            continue
        thema.thema = zeile.thema_text
        thema.zustaendig = zeile.zustaendig
        thema.bearb_bis = zeile.bearb_bis
        thema.status = zeile.status
        thema.zuletzt_protokoll_id = zeile.ursprung_protokoll_id or protokoll.id
        if thema.erstmals_protokoll_id is None:
            thema.erstmals_protokoll_id = protokoll.id
        if zeile.status == ERLEDIGT:
            if thema.erledigt_am is None:
                thema.erledigt_am = protokoll.besprechungsdatum
        else:
            # Ein wieder aufgenommenes Thema gilt nicht mehr als erledigt.
            thema.erledigt_am = None


def _erzeuge_dokument(db: Session, protokoll: Besprechungsprotokoll) -> list[str]:
    daten = _baue_daten(db, protokoll)
    try:
        pfad, probleme = erzeugung.generate_besprechungsprotokoll(daten)
    except erzeugung.ProtokollFehler as fehler:
        raise HTTPException(422, str(fehler)) from fehler

    protokoll.dokument_pfad = str(pfad)
    protokoll.erzeugt_am = datetime.now()

    # PDF nur, wenn Word erreichbar ist (Bürorechner ja, Server nein).
    protokoll.pdf_pfad = None
    try:
        pdf = word_pdf.nach_pdf(pfad.read_bytes())
        if pdf:
            pdf_pfad = pfad.with_suffix(".pdf")
            pdf_pfad.write_bytes(pdf)
            protokoll.pdf_pfad = str(pdf_pfad)
    except Exception:
        # Kein Grund, die Freigabe scheitern zu lassen — das Word-Dokument
        # ist die verbindliche Ausgabe.
        pass

    db.commit()
    return probleme


@router.post("/{protokoll_id}/freigeben", response_model=ProtokollResponse)
def freigeben(
    protokoll_id: int,
    daten: ProtokollFreigabe | None = None,
    db: Session = Depends(get_db),
):
    """Prüfung abschließen, Themenliste fortschreiben, Dokument erzeugen.

    Die Reihenfolge ist wichtig und nicht beliebig: erst prüfen, dann
    fortschreiben, dann erzeugen. Ein Dokument entsteht nie aus ungeprüften
    Zeilen.
    """
    protokoll = _hole(db, protokoll_id)
    daten = daten or ProtokollFreigabe()

    if protokoll.status == "freigegeben":
        raise HTTPException(409, "Dieses Protokoll ist bereits freigegeben.")
    if not protokoll.themen_updates:
        raise HTTPException(
            422,
            "Das Protokoll enthält keine einzige Themenzeile. Bitte zuerst "
            "einen tl;dv-Text auswerten oder Themen von Hand erfassen.",
        )

    ungeprueft = [u for u in protokoll.themen_updates if not u.bestaetigt]
    if ungeprueft and not daten.trotz_ungeprueft:
        raise HTTPException(
            409,
            f"{len(ungeprueft)} Zeile(n) wurden noch nicht geprüft. Genau dafür "
            f"gibt es den Prüfschritt: Bitte jede Zeile ansehen und "
            f"bestätigen — oder die Freigabe ausdrücklich trotzdem anfordern.",
        )

    protokoll.geprueft_von_id = daten.geprueft_von_id
    protokoll.geprueft_am = datetime.now()
    protokoll.freigegeben_am = datetime.now()
    protokoll.status = "freigegeben"

    _schreibe_themenliste_fort(db, protokoll)
    db.commit()

    probleme = _erzeuge_dokument(db, protokoll)
    db.refresh(protokoll)

    antwort = _zu_detail(db, protokoll)
    if probleme:
        antwort.analyse_hinweise = list(antwort.analyse_hinweise) + [
            f"Diese Anlage konnte nicht eingebunden werden: {name}"
            for name in probleme
        ]
    return antwort


@router.post("/{protokoll_id}/generieren", response_model=ProtokollResponse)
def generieren(protokoll_id: int, db: Session = Depends(get_db)):
    """Erzeugt das Dokument eines freigegebenen Protokolls neu.

    Für den Fall, dass die Datei verloren ging oder eine Anlage nachgereicht
    wurde. An den Inhalten ändert das nichts — die stehen fest.
    """
    protokoll = _hole(db, protokoll_id)
    if protokoll.status != "freigegeben":
        raise HTTPException(
            409,
            "Ein Dokument entsteht erst mit der Freigabe. Bitte die Zeilen "
            "prüfen und dann freigeben.",
        )
    _erzeuge_dokument(db, protokoll)
    db.refresh(protokoll)
    return _zu_detail(db, protokoll)


@router.get("/{protokoll_id}/dokument")
def dokument(
    protokoll_id: int,
    als_pdf: bool = Query(False),
    db: Session = Depends(get_db),
):
    protokoll = _hole(db, protokoll_id)
    pfad_text = protokoll.pdf_pfad if als_pdf else protokoll.dokument_pfad
    if not pfad_text:
        raise HTTPException(
            404,
            "Für dieses Protokoll gibt es noch kein PDF." if als_pdf
            else "Für dieses Protokoll wurde noch kein Dokument erzeugt.",
        )

    from pathlib import Path

    pfad = Path(pfad_text)
    if not pfad.is_file():
        raise HTTPException(
            404,
            "Die Datei liegt nicht mehr im Ausgabeordner. Über „Neu erzeugen“ "
            "lässt sie sich wiederherstellen.",
        )

    name = pfad.name
    typ = (
        "application/pdf" if als_pdf
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(
        path=str(pfad),
        media_type=typ,
        filename=name,
        headers={
            "Content-Disposition":
                f"attachment; filename*=UTF-8''{quote(name)}"
        },
    )
