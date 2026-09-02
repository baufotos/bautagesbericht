from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Projekt
from app.schemas import (
    ProjektCreate,
    ProjektResponse,
    ProjektUpdate,
    StandortSucheAntwort,
)
from app.services.cleanup import (
    count_besprechungsprotokolle_for,
    count_einreichungen_for,
    count_fotosaetze_for,
    count_projektberichte_for,
    count_maengel_for,
    delete_besprechungen_for,
    delete_einreichungen_for,
    delete_fotosaetze_for,
    delete_projektberichte_for,
    delete_maengel_for,
)
from app.services.geocoding import suche_standort

router = APIRouter(prefix="/projekte", tags=["projekte"])


@router.get("", response_model=list[ProjektResponse])
def list_projekte(db: Session = Depends(get_db)):
    return db.query(Projekt).order_by(Projekt.erstellt_am.desc()).all()


# Muss vor "/{projekt_id}" stehen, sonst hielte FastAPI "standort-suche" fuer
# eine Projekt-ID.
@router.get("/standort-suche", response_model=StandortSucheAntwort)
async def standort_suche(adresse: str):
    """Sucht Koordinaten zu einer Adresse und gibt ALLE Kandidaten zurueck.

    Warum die Auswahl beim Menschen bleibt: Eine Baustellenadresse ist oft
    mehrdeutig ("Baufeld 3"), und ein Kartendienst raet dann. Wer die Baustelle
    kennt, erkennt den richtigen Treffer auf einen Blick - der Server nicht.
    Deshalb liefert dieser Endpunkt eine Liste mit Klartext-Beschriftung und
    Guete, und die Oberflaeche laesst waehlen.
    """
    ergebnis = await suche_standort(adresse, grenze=5)
    teile = ergebnis.teile
    return StandortSucheAntwort(
        adresse=adresse,
        treffer=[t.als_dict() for t in ergebnis.treffer],
        dienst_erreichbar=ergebnis.dienst_erreichbar,
        erkannt={
            k: v
            for k, v in (
                ("zusatz", teile.zusatz),
                ("strasse", teile.strasse),
                ("hausnummer", teile.hausnummer),
                ("plz", teile.plz),
                ("ort", teile.ort),
                ("land", teile.land),
            )
            if v
        },
        versuche=ergebnis.versuche,
    )


async def _standort_bestimmen(adresse: str) -> tuple[float | None, float | None, str, str]:
    """Koordinaten samt Guete und Klartext zu einer Adresse."""
    ergebnis = await suche_standort(adresse, grenze=1)
    bester = ergebnis.bester
    if not bester:
        return None, None, "", ""
    return bester.lat, bester.lon, bester.guete, bester.label


@router.post("", response_model=ProjektResponse, status_code=201)
async def create_projekt(data: ProjektCreate, db: Session = Depends(get_db)):
    if data.lat is not None and data.lon is not None:
        # Aus der Suche ausgewaehlt oder von Hand eingetippt: uebernehmen und
        # nicht nachschlagen.
        lat, lon, guete, label = data.lat, data.lon, "manuell", ""
    else:
        lat, lon, guete, label = await _standort_bestimmen(data.adresse)
    projekt = Projekt(
        name=data.name,
        adresse=data.adresse,
        lat=lat,
        lon=lon,
        standort_guete=guete,
        standort_label=label,
        teams_webhook_url=data.teams_webhook_url.strip(),
        foto_zielpfad=data.foto_zielpfad.strip(),
    )
    db.add(projekt)
    db.commit()
    db.refresh(projekt)
    return projekt


@router.patch("/{projekt_id}", response_model=ProjektResponse)
async def update_projekt(
    projekt_id: int, data: ProjektUpdate, db: Session = Depends(get_db)
):
    """Aendert Stammdaten eines Projekts.

    Vor allem fuer den Fotozielpfad gedacht: Jedes Projekt liegt woanders im
    Netzlaufwerk, und der Pfad wird selten beim Anlegen schon feststehen.
    """
    projekt = db.get(Projekt, projekt_id)
    if not projekt:
        raise HTTPException(404, "Projekt nicht gefunden")

    if data.name is not None and data.name.strip():
        projekt.name = data.name.strip()
    if data.teams_webhook_url is not None:
        projekt.teams_webhook_url = data.teams_webhook_url.strip()
    if data.foto_zielpfad is not None:
        projekt.foto_zielpfad = data.foto_zielpfad.strip()
    adresse_neu = (
        data.adresse is not None
        and data.adresse.strip() != (projekt.adresse or "")
    )
    if data.adresse is not None:
        projekt.adresse = data.adresse.strip()

    if data.standort_entfernen:
        projekt.lat, projekt.lon = None, None
        projekt.standort_guete, projekt.standort_label = "", ""
    elif data.lat is not None and data.lon is not None:
        # Von Hand gesetzt oder aus der Suche gewaehlt. Hat Vorrang vor allem
        # anderen, auch vor einer gleichzeitig geaenderten Adresse: Der Mensch
        # sieht die Baustelle, der Kartendienst nicht.
        projekt.lat, projekt.lon = data.lat, data.lon
        projekt.standort_guete, projekt.standort_label = "manuell", ""
    elif adresse_neu or data.standort_neu_suchen:
        # Adresse geaendert: Koordinaten neu bestimmen, sonst zeigt die
        # Wetterabfrage des Bautagesberichts auf den alten Ort. Und auf
        # ausdruecklichen Wunsch auch ohne Adressaenderung - eine Suche, die
        # beim Anlegen an einer Stoerung scheiterte, muss wiederholbar sein.
        lat, lon, guete, label = await _standort_bestimmen(projekt.adresse)
        if lat is not None or not projekt.lat or adresse_neu:
            # Bei einer erfolglosen Wiederholung den bisherigen Standort
            # behalten, statt einen brauchbaren gegen "leer" zu tauschen.
            projekt.lat, projekt.lon = lat, lon
            projekt.standort_guete, projekt.standort_label = guete, label

    db.commit()
    db.refresh(projekt)
    return projekt


@router.delete("/{projekt_id}", status_code=204)
def delete_projekt(projekt_id: int, force: bool = False, db: Session = Depends(get_db)):
    """Löscht ein Projekt.

    Hängen noch Einreichungen oder Mängel daran, wird ohne ``force=true`` mit
    409 abgelehnt und die Anzahl gemeldet — so kann die Oberfläche nachfragen,
    bevor Berichts- und Mängelhistorie mitgelöscht werden.
    """
    projekt = db.get(Projekt, projekt_id)
    if not projekt:
        raise HTTPException(404, "Projekt nicht gefunden")

    anzahl = count_einreichungen_for(db, projekt_id=projekt_id)
    anzahl_maengel = count_maengel_for(db, projekt_id=projekt_id)
    anzahl_fotosaetze = count_fotosaetze_for(db, projekt_id=projekt_id)
    anzahl_berichte = count_projektberichte_for(db, projekt_id=projekt_id)
    anzahl_protokolle = count_besprechungsprotokolle_for(db, projekt_id=projekt_id)
    if (anzahl or anzahl_maengel or anzahl_fotosaetze or anzahl_berichte
            or anzahl_protokolle) and not force:
        teile = []
        if anzahl:
            teile.append(f"{anzahl} Einreichung(en)")
        if anzahl_maengel:
            teile.append(f"{anzahl_maengel} Mangel/Mängel")
        if anzahl_fotosaetze:
            teile.append(f"{anzahl_fotosaetze} Fotosatz/Fotosätze")
        if anzahl_berichte:
            teile.append(f"{anzahl_berichte} Projektbericht(e)")
        if anzahl_protokolle:
            teile.append(f"{anzahl_protokolle} Besprechungsprotokoll(e)")
        raise HTTPException(
            409,
            detail={
                "grund": "abhaengige_daten_vorhanden",
                "anzahl": (anzahl + anzahl_maengel + anzahl_fotosaetze
                           + anzahl_berichte + anzahl_protokolle),
                "anzahl_einreichungen": anzahl,
                "anzahl_maengel": anzahl_maengel,
                "anzahl_fotosaetze": anzahl_fotosaetze,
                "anzahl_projektberichte": anzahl_berichte,
                "anzahl_besprechungsprotokolle": anzahl_protokolle,
                "nachricht": (
                    f"Zu diesem Projekt gehören noch {', '.join(teile)}. "
                    "Beim Löschen werden sie mit entfernt."
                ),
            },
        )

    if anzahl:
        delete_einreichungen_for(db, projekt_id=projekt_id)
    if anzahl_fotosaetze:
        delete_fotosaetze_for(db, projekt_id=projekt_id)
    if anzahl_berichte:
        delete_projektberichte_for(db, projekt_id=projekt_id)
    # Vor delete_maengel_for: Die Besprechungskapitel verweisen auf Gewerke,
    # und die raeumt der Mangel-Aufruf ab. Immer aufrufen — auch ohne
    # Protokolle kann ein Projekt Kapitel und Projektbeteiligte haben.
    delete_besprechungen_for(db, projekt_id=projekt_id)
    # Immer aufrufen: Auch ein Projekt ohne Mängel kann Gewerke und Pläne
    # haben, die per Fremdschlüssel darauf verweisen und mit weg müssen.
    delete_maengel_for(db, projekt_id=projekt_id)
    db.delete(projekt)
    db.commit()
