"""Baufotos: Fotosätze anlegen, Fotos hochladen, ZIP abrufen.

Fachliche Regeln (Benennung, Verkleinerung, ZIP) stehen in
``app.services.baufotos`` — hier ist nur die HTTP-Schicht.

Reihenfolge der Routen ist bewusst: erst die feststehenden Pfade
(``/kategorien``, ``/fotos/...``), danach die mit ``/{fotosatz_id}``. FastAPI
prüft in Registrierungsreihenfolge, sonst würde "kategorien" als ID gelesen.

Zwei Schritte beim Erfassen (erst Fotosatz anlegen, dann Fotos einzeln
hochladen) — dieselbe Entscheidung wie im Mängelmodul: Auf der Baustelle bricht
die Verbindung mitten im Upload ab, und dann soll höchstens ein Foto verloren
sein, nicht der ganze Vorgang.
"""

from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Baufoto, Fotosatz, Projekt
from app.schemas import (
    AbholAnspruch,
    AbholQuittung,
    AbholStatus,
    BaufotoResponse,
    FotosatzCreate,
    FotosatzListItem,
    FotosatzMailAnfrage,
    FotosatzMailErgebnis,
    FotosatzMailFaehigkeiten,
    FotosatzMailVorschlag,
    FotosatzResponse,
    FotosatzUpdate,
    FotosatzVersand,
    OffenerFotosatz,
)
from app.services import abholung
from app.services import baufotos as dienst
from app.services import bilder
from app.services import fotospeicher
from app.services import fotoversand as versand
from app.utils.file_storage import get_absolute_path, save_upload_in

router = APIRouter(prefix="/fotosaetze", tags=["baufotos"])


# ─────────────────────────────────────────────────────────────────────────────
# Antwort-Aufbau
# ─────────────────────────────────────────────────────────────────────────────


def _kennzahlen(db: Session, fotosatz_ids: list[int]) -> dict[int, tuple[int, int, int]]:
    """Pro Fotosatz: (Anzahl Fotos, Summe Bytes, ID des Titelfotos).

    Eine Abfrage für die ganze Liste statt einer je Karte — die Übersicht zeigt
    schnell mehrere Dutzend Sätze.
    """
    if not fotosatz_ids:
        return {}

    summen = dict(
        (fid, (anzahl, bytes_summe or 0))
        for fid, anzahl, bytes_summe in db.query(
            Baufoto.fotosatz_id,
            func.count(Baufoto.id),
            func.sum(Baufoto.groesse_bytes),
        )
        .filter(Baufoto.fotosatz_id.in_(fotosatz_ids))
        .group_by(Baufoto.fotosatz_id)
        .all()
    )

    titel: dict[int, int] = {}
    for fid, foto_id in (
        db.query(Baufoto.fotosatz_id, Baufoto.id)
        .filter(Baufoto.fotosatz_id.in_(fotosatz_ids))
        .order_by(Baufoto.reihenfolge, Baufoto.id)
        .all()
    ):
        titel.setdefault(fid, foto_id)

    return {
        fid: (summen.get(fid, (0, 0))[0], summen.get(fid, (0, 0))[1], titel.get(fid, 0))
        for fid in fotosatz_ids
    }


def _zu_listitem(fotosatz: Fotosatz, anzahl: int, bytes_summe: int,
                 titel_foto_id: int) -> FotosatzListItem:
    projekt_name = fotosatz.projekt.name if fotosatz.projekt else ""
    eintrag = FotosatzListItem.model_validate(fotosatz)
    eintrag.projekt_name = projekt_name
    eintrag.anzahl_fotos = anzahl
    eintrag.groesse_bytes = bytes_summe
    eintrag.titel_foto_id = titel_foto_id or None
    eintrag.zip_dateiname = dienst.zip_dateiname(
        fotosatz.datum, projekt_name or "Projekt", fotosatz.kategorie
    )
    return eintrag


def _zu_detail(db: Session, fotosatz: Fotosatz) -> FotosatzResponse:
    fotos = list(fotosatz.fotos)
    antwort = FotosatzResponse.model_validate(fotosatz)
    antwort.projekt_name = fotosatz.projekt.name if fotosatz.projekt else ""
    antwort.anzahl_fotos = len(fotos)
    antwort.groesse_bytes = sum(f.groesse_bytes or 0 for f in fotos)
    antwort.titel_foto_id = fotos[0].id if fotos else None
    antwort.zip_dateiname = dienst.zip_dateiname(
        fotosatz.datum, antwort.projekt_name or "Projekt", fotosatz.kategorie
    )
    antwort.fotos = [BaufotoResponse.model_validate(f) for f in fotos]
    return antwort


def _hole(db: Session, fotosatz_id: int) -> Fotosatz:
    fotosatz = db.get(Fotosatz, fotosatz_id)
    if not fotosatz:
        raise HTTPException(404, "Fotosatz nicht gefunden")
    return fotosatz


# ─────────────────────────────────────────────────────────────────────────────
# Übersicht und feststehende Pfade
# ─────────────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[FotosatzListItem])
def list_fotosaetze(
    projekt_id: int | None = None,
    kategorie: str | None = None,
    suche: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Fotosatz)
    if projekt_id is not None:
        query = query.filter(Fotosatz.projekt_id == projekt_id)
    if kategorie:
        query = query.filter(Fotosatz.kategorie == kategorie)
    if suche:
        muster = f"%{suche.strip()}%"
        query = query.filter(
            Fotosatz.kategorie.ilike(muster) | Fotosatz.notiz.ilike(muster)
        )

    # Neueste zuerst: Auf der Baustelle interessiert der Satz von heute.
    rows = query.order_by(Fotosatz.datum.desc(), Fotosatz.id.desc()).all()
    zahlen = _kennzahlen(db, [f.id for f in rows])
    return [
        _zu_listitem(f, *zahlen.get(f.id, (0, 0, 0)))
        for f in rows
    ]


@router.get("/kategorien", response_model=list[str])
def list_kategorien(projekt_id: int | None = None, db: Session = Depends(get_db)):
    """Bisher benutzte Kategorien — Vorschläge, keine Vorschrift.

    Die Kategorien wachsen mit dem Bau ("Rohbau", "Fenster EG", "Abnahme
    Dach"). Eine feste Liste wäre nach zwei Wochen falsch, deshalb werden hier
    die vorhandenen Werte zurückgegeben und im Formular als Vorschlag angeboten.
    """
    query = db.query(Fotosatz.kategorie).distinct()
    if projekt_id is not None:
        query = query.filter(Fotosatz.projekt_id == projekt_id)
    return sorted({k for (k,) in query.all() if k})


@router.get("/mail/faehigkeiten", response_model=FotosatzMailFaehigkeiten)
def mail_faehigkeiten():
    """Kann dieser Server selbst verschicken? Steuert die Knöpfe im Dialog.

    Ohne diese Auskunft müsste die Oberfläche "Direkt senden" immer anbieten
    und der Kollege würde die Absage erst nach dem Klick sehen.
    """
    return FotosatzMailFaehigkeiten(
        smtp=versand.smtp_bereit(),
        absender=versand.absender_adresse(),
        max_anhang_mb=versand.MAX_ANHANG_MB,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Abholung durch die Bürorechner
#
# Diese drei Routen bedienen kein Menschen-Frontend, sondern das Skript
# ``desktop/abholung/Baufotos-Abholen.ps1`` in der Windows-Aufgabenplanung.
# Der Ablauf und die Gründe dafür stehen in ``app.services.abholung``.
# ─────────────────────────────────────────────────────────────────────────────


def pruefe_abholrecht(x_abhol_token: str = Header("")) -> None:
    """Schützt die Abholrouten, wenn BTB_ABHOL_TOKEN gesetzt ist.

    Ohne gesetzten Token bleibt alles offen — dann verhält sich die Abholung
    wie der Rest der App. Mit Token braucht jeder Bürorechner denselben Wert
    in seiner Konfiguration.
    """
    erwartet = (settings.abhol_token or "").strip()
    if erwartet and (x_abhol_token or "").strip() != erwartet:
        raise HTTPException(401, "Abhol-Token fehlt oder stimmt nicht")


@router.get("/abholung/offen", response_model=list[OffenerFotosatz],
            dependencies=[Depends(pruefe_abholrecht)])
def abholung_offen(db: Session = Depends(get_db)):
    """Was wartet noch darauf, ins Netzlaufwerk gelegt zu werden?

    Enthält alles, was das Skript für den Zielordner braucht — es muss keine
    weitere Route aufrufen, um Projektname oder Pfad nachzuschlagen.
    """
    offen: list[OffenerFotosatz] = []
    for satz in abholung.offene_saetze(db):
        projekt_name = satz.projekt.name if satz.projekt else ""
        fotos = list(satz.fotos)
        offen.append(
            OffenerFotosatz(
                id=satz.id,
                projekt_name=projekt_name,
                kategorie=satz.kategorie,
                datum=satz.datum,
                notiz=satz.notiz or "",
                anzahl_fotos=len(fotos),
                groesse_bytes=sum(f.groesse_bytes or 0 for f in fotos),
                ordnername=abholung.ordnername(satz),
                zip_dateiname=_zip_name(satz),
                zielpfad=abholung.zielpfad_von(satz.projekt),
                erstellt_am=satz.erstellt_am,
            )
        )
    return offen


@router.post("/{fotosatz_id}/abholung/beanspruchen", response_model=AbholStatus,
             dependencies=[Depends(pruefe_abholrecht)])
def abholung_beanspruchen(fotosatz_id: int, anspruch: AbholAnspruch,
                          db: Session = Depends(get_db)):
    """Reserviert den Satz für diesen Rechner. 409, wenn ein anderer schneller war."""
    erfolg, nachricht = abholung.beanspruche(db, fotosatz_id, anspruch.rechner)
    satz = db.get(Fotosatz, fotosatz_id)
    if satz is None:
        raise HTTPException(404, "Fotosatz nicht gefunden")
    if not erfolg:
        # 409 und nicht 403: Der Aufrufer darf grundsätzlich, nur eben jetzt
        # nicht. Das Skript wertet genau das als "überspringen, kein Fehler".
        raise HTTPException(409, nachricht)
    return AbholStatus(
        id=satz.id,
        erfolg=True,
        nachricht=nachricht,
        abgeholt_am=satz.abgeholt_am,
        abgeholt_von=satz.abgeholt_von or "",
        abgeholt_ziel=satz.abgeholt_ziel or "",
    )


@router.post("/{fotosatz_id}/abholung/quittieren", response_model=AbholStatus,
             dependencies=[Depends(pruefe_abholrecht)])
def abholung_quittieren(fotosatz_id: int, quittung: AbholQuittung,
                        db: Session = Depends(get_db)):
    """Meldet: Der Satz liegt im Projektordner. Erst damit gilt er als erledigt."""
    satz = _hole(db, fotosatz_id)
    if not (quittung.ziel or "").strip():
        raise HTTPException(400, "Ohne Zielpfad keine Quittung")
    abholung.quittiere(db, satz, quittung.rechner, quittung.ziel)
    return AbholStatus(
        id=satz.id,
        erfolg=True,
        nachricht="Abholung eingetragen.",
        abgeholt_am=satz.abgeholt_am,
        abgeholt_von=satz.abgeholt_von or "",
        abgeholt_ziel=satz.abgeholt_ziel or "",
    )


@router.post("/{fotosatz_id}/abholung/freigeben", response_model=AbholStatus,
             dependencies=[Depends(pruefe_abholrecht)])
def abholung_freigeben(fotosatz_id: int, db: Session = Depends(get_db)):
    """Gibt einen Satz nach einem Fehlschlag sofort wieder frei."""
    satz = _hole(db, fotosatz_id)
    if (satz.abgeholt_ziel or "").strip():
        raise HTTPException(409, "Dieser Satz ist bereits abgeholt und quittiert")
    abholung.gib_frei(db, satz)
    return AbholStatus(id=satz.id, erfolg=True,
                       nachricht="Wieder zur Abholung freigegeben.")


@router.get("/fotos/{foto_id}/bild")
def foto_bild(foto_id: int, thumb: bool = False, db: Session = Depends(get_db)):
    foto = db.get(Baufoto, foto_id)
    if not foto:
        raise HTTPException(404, "Foto nicht gefunden")

    # Liegt das Foto im Objektspeicher, gibt es keinen Pfad auf der Platte —
    # dann werden die Bytes direkt ausgeliefert.
    if fotospeicher.ist_objekt(foto.dateipfad):
        daten = fotospeicher.lies(foto.dateipfad)
        if daten is None:
            raise HTTPException(404, "Bilddatei nicht gefunden")
        if thumb:
            daten = bilder.thumbnail_bytes(daten) or daten
        return Response(
            content=daten,
            media_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=86400"},
        )

    pfad = get_absolute_path(foto.dateipfad)
    if not pfad.is_file():
        raise HTTPException(404, "Bilddatei nicht gefunden")

    if thumb:
        vorschau = bilder.thumbnail(pfad)
        if vorschau is not None:
            pfad = vorschau

    return FileResponse(
        pfad,
        # Fotos werden nach dem Hochladen nicht mehr verändert — der Browser
        # darf sie behalten, das spart auf der Baustelle Datenvolumen.
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.delete("/fotos/{foto_id}", status_code=204)
def delete_foto(foto_id: int, db: Session = Depends(get_db)):
    """Löscht ein einzelnes Foto.

    Die Nummern der übrigen Fotos bleiben, wie sie sind: Ein Umnummerieren
    würde Dateinamen ändern, die vielleicht schon in einem Projektordner
    liegen — dann stimmten Archiv und Ordner nicht mehr zusammen.
    """
    foto = db.get(Baufoto, foto_id)
    if not foto:
        raise HTTPException(404, "Foto nicht gefunden")
    fotospeicher.loesche(foto.dateipfad)
    db.delete(foto)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Fotosatz
# ─────────────────────────────────────────────────────────────────────────────


@router.post("", response_model=FotosatzResponse, status_code=201)
def create_fotosatz(data: FotosatzCreate, db: Session = Depends(get_db)):
    if not db.get(Projekt, data.projekt_id):
        raise HTTPException(400, "Projekt nicht gefunden")
    kategorie = data.kategorie.strip()
    if not kategorie:
        raise HTTPException(400, "Bitte eine Kategorie angeben (z. B. Rohbau)")

    fotosatz = Fotosatz(
        projekt_id=data.projekt_id,
        kategorie=kategorie,
        datum=data.datum or date.today(),
        notiz=data.notiz.strip(),
    )
    db.add(fotosatz)
    db.commit()
    db.refresh(fotosatz)
    return _zu_detail(db, fotosatz)


@router.get("/{fotosatz_id}", response_model=FotosatzResponse)
def get_fotosatz(fotosatz_id: int, db: Session = Depends(get_db)):
    return _zu_detail(db, _hole(db, fotosatz_id))


@router.patch("/{fotosatz_id}", response_model=FotosatzResponse)
def update_fotosatz(
    fotosatz_id: int, data: FotosatzUpdate, db: Session = Depends(get_db)
):
    """Ändert Kategorie, Datum oder Notiz.

    Achtung, bewusst so: Die schon gespeicherten Fotos werden **nicht**
    umbenannt. Ihre Namen stehen möglicherweise bereits in einem Projektordner;
    ein stilles Umbenennen wäre schlimmer als eine Abweichung. Für einen
    korrigierten Namensstand legt man einen neuen Fotosatz an.
    """
    fotosatz = _hole(db, fotosatz_id)
    for feld, wert in data.model_dump(exclude_unset=True).items():
        if feld == "kategorie" and not (wert or "").strip():
            continue
        setattr(fotosatz, feld, wert.strip() if isinstance(wert, str) else wert)
    db.commit()
    db.refresh(fotosatz)
    return _zu_detail(db, fotosatz)


@router.delete("/{fotosatz_id}", status_code=204)
def delete_fotosatz(fotosatz_id: int, db: Session = Depends(get_db)):
    from app.services.cleanup import delete_fotosatz_cascade

    fotosatz = _hole(db, fotosatz_id)
    delete_fotosatz_cascade(db, fotosatz)
    db.commit()


@router.post("/{fotosatz_id}/fotos", response_model=list[BaufotoResponse],
             status_code=201)
async def upload_fotos(
    fotosatz_id: int,
    dateien: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Nimmt Fotos an, benennt sie um und verkleinert sie.

    Die Umbenennung passiert hier und nicht im Browser: Nur der Server kennt
    die schon vergebenen Nummern des Fotosatzes, und nur so stimmen die Namen
    auch, wenn zwei Personen gleichzeitig hochladen.
    """
    fotosatz = _hole(db, fotosatz_id)
    if len(dateien) > dienst.MAX_FOTOS_PRO_UPLOAD:
        raise HTTPException(
            400, f"Maximal {dienst.MAX_FOTOS_PRO_UPLOAD} Fotos pro Upload"
        )

    grenze = settings.max_file_size_mb * 1024 * 1024
    nummer = dienst.naechste_nummer(db, fotosatz.id)
    neue: list[Baufoto] = []

    for datei in dateien:
        original = datei.filename or "foto.jpg"
        if not dienst.ist_erlaubte_datei(original):
            raise HTTPException(
                400,
                f"'{original}' ist keine Bilddatei "
                f"(erlaubt: {', '.join(sorted(dienst.ERLAUBTE_ENDUNGEN))})",
            )

        rohdaten = await datei.read()
        if len(rohdaten) > grenze:
            raise HTTPException(
                400, f"'{original}' ist größer als {settings.max_file_size_mb} MB"
            )

        inhalt, als_jpeg = dienst.verkleinere(rohdaten)
        name = dienst.foto_dateiname(fotosatz.datum, fotosatz.kategorie, nummer)
        if not als_jpeg:
            # Pillow konnte das Bild nicht lesen (z. B. HEIC ohne Plugin):
            # Originaldaten behalten, aber die Original-Endung setzen, damit die
            # Datei nicht fälschlich .jpg heißt. Nummer und Kategorie im Namen
            # bleiben — der Satz bleibt so als Ganzes sortierbar.
            name = f"{Path(name).stem}{Path(original).suffix.lower()}"

        # Über die Speicherschicht: auf dem Bürorechner die Platte, auf einem
        # Server mit flüchtigem Speicher der Objektspeicher. Ohne das wären
        # Fotos nach dem nächsten Neustart des Dienstes weg, während in der
        # Datenbank noch ihre Verweise stünden.
        rel_pfad = await fotospeicher.schreibe(
            f"baufotos/{fotosatz.id}", name, inhalt
        )
        foto = Baufoto(
            fotosatz_id=fotosatz.id,
            dateipfad=rel_pfad,
            dateiname=name,
            original_dateiname=original,
            reihenfolge=nummer,
            groesse_bytes=len(inhalt),
        )
        db.add(foto)
        neue.append(foto)
        nummer += 1

    db.commit()
    for foto in neue:
        db.refresh(foto)
    return neue


def _zip_name(fotosatz: Fotosatz) -> str:
    """Archivname nach der Büroregel — derselbe Name für Download und Anhang."""
    return dienst.zip_dateiname(
        fotosatz.datum,
        fotosatz.projekt.name if fotosatz.projekt else "Projekt",
        fotosatz.kategorie,
    )


def _anhang_kopfzeile(name: str, ersatz: str) -> str:
    """Content-Disposition mit Umlauten.

    Projektnamen enthalten Umlaute. Ohne die RFC-5987-Fassung (``filename*``)
    kommt beim Browser sonst "Verwaltungsgebude" an; ohne den einfachen
    ``filename`` verstehen ältere Browser gar nichts.
    """
    schlicht = name.encode("ascii", "ignore").decode() or ersatz
    return f'attachment; filename="{schlicht}"; filename*=UTF-8\'\'{quote(name)}'


@router.get("/{fotosatz_id}/zip")
def download_zip(fotosatz_id: int, db: Session = Depends(get_db)):
    """Liefert den kompletten Fotosatz als ZIP — die Datei fürs Projektarchiv."""
    fotosatz = _hole(db, fotosatz_id)
    if not fotosatz.fotos:
        raise HTTPException(404, "Dieser Fotosatz enthält noch keine Fotos")

    daten = dienst.baue_zip(fotosatz)
    name = _zip_name(fotosatz)
    return Response(
        content=daten,
        media_type="application/zip",
        headers={"Content-Disposition": _anhang_kopfzeile(name, "baufotos.zip")},
    )


@router.post("/{fotosatz_id}/melden", response_model=FotosatzVersand)
async def melden(fotosatz_id: int, db: Session = Depends(get_db)):
    """Meldet den Fotosatz mit ZIP-Link in Teams."""
    fotosatz = _hole(db, fotosatz_id)
    gemeldet, kanal, nachricht = await dienst.melde_fotosatz(db, fotosatz)
    return FotosatzVersand(
        fotosatz_id=fotosatz.id,
        gemeldet=gemeldet,
        kanal=kanal,
        nachricht=nachricht,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Per E-Mail verschicken
#
# Zwei Wege, weil das Büro gemischt arbeitet (siehe app.services.fotoversand):
# "senden" geht nur mit hinterlegtem Postausgangsserver, "entwurf" immer.
# Beide bauen dieselbe Nachricht — nur die Zustellung unterscheidet sich.
# ─────────────────────────────────────────────────────────────────────────────


def _mail_bauen(fotosatz: Fotosatz, anfrage: FotosatzMailAnfrage, *,
                als_entwurf: bool):
    """Gemeinsamer Teil beider Wege: prüfen, ZIP bauen, Nachricht bestücken."""
    if not fotosatz.fotos:
        raise HTTPException(400, "Dieser Fotosatz enthält noch keine Fotos")

    zip_bytes = dienst.baue_zip(fotosatz)
    zu_gross = versand.zu_gross(len(zip_bytes))
    if zu_gross:
        # 413: Die Anfrage ist in Ordnung, nur der Anhang passt nicht durch.
        raise HTTPException(413, zu_gross)

    zip_name = _zip_name(fotosatz)
    empfaenger = [str(adresse) for adresse in anfrage.empfaenger]
    kopie = [str(adresse) for adresse in anfrage.kopie]

    nachricht = versand.baue_nachricht(
        fotosatz,
        empfaenger=empfaenger,
        kopie=kopie,
        betreff=anfrage.betreff.strip() or versand.betreff_fuer(fotosatz),
        text=anfrage.nachricht.strip() or versand.standardtext(fotosatz),
        zip_bytes=zip_bytes,
        zip_name=zip_name,
        absender=versand.absender_adresse(),
        als_entwurf=als_entwurf,
    )
    return nachricht, empfaenger + kopie, zip_name


@router.get("/{fotosatz_id}/mail/vorschlag", response_model=FotosatzMailVorschlag)
def mail_vorschlag(fotosatz_id: int, db: Session = Depends(get_db)):
    """Betreff und Text, mit denen der Dialog startet — beides überschreibbar.

    Das Archiv wird dafür wirklich gebaut: Nur so steht schon vor dem Abschicken
    fest, ob es durch eine Mail passt. Bei zwanzig verkleinerten Fotos kostet
    das Bruchteile einer Sekunde.
    """
    fotosatz = _hole(db, fotosatz_id)
    groesse = len(dienst.baue_zip(fotosatz)) if fotosatz.fotos else 0
    zu_gross = versand.zu_gross(groesse)

    return FotosatzMailVorschlag(
        betreff=versand.betreff_fuer(fotosatz),
        nachricht=versand.standardtext(fotosatz),
        zip_dateiname=_zip_name(fotosatz),
        groesse_bytes=groesse,
        passt=zu_gross is None,
        hinweis=zu_gross or "",
    )


@router.post("/{fotosatz_id}/mail/entwurf")
def mail_entwurf(fotosatz_id: int, anfrage: FotosatzMailAnfrage,
                 db: Session = Depends(get_db)):
    """Fertige Mail als ``.eml`` — Outlook öffnet sie als Entwurf zum Senden.

    Der Weg, der ohne jede Serverkonfiguration funktioniert. Deshalb wird auch
    hier der Versand notiert, allerdings als ``weg="entwurf"``: Abgeschickt hat
    die Mail dann Outlook, nicht die App.
    """
    fotosatz = _hole(db, fotosatz_id)
    nachricht, alle, zip_name = _mail_bauen(fotosatz, anfrage, als_entwurf=True)

    versand.notiere_versand(fotosatz, alle, "entwurf")
    db.commit()

    name = f"{Path(zip_name).stem}.eml"
    return Response(
        content=nachricht.as_bytes(),
        media_type="message/rfc822",
        headers={"Content-Disposition": _anhang_kopfzeile(name, "baufotos.eml")},
    )


@router.post("/{fotosatz_id}/mail/senden", response_model=FotosatzMailErgebnis)
def mail_senden(fotosatz_id: int, anfrage: FotosatzMailAnfrage,
                db: Session = Depends(get_db)):
    """Verschickt den Fotosatz wirklich — nur mit hinterlegtem SMTP-Server."""
    fotosatz = _hole(db, fotosatz_id)

    if not versand.smtp_bereit():
        raise HTTPException(
            503,
            "Es ist kein Postausgangsserver hinterlegt (BTB_SMTP_HOST). "
            "Nutze den Outlook-Entwurf — der braucht keinen Server.",
        )

    nachricht, alle, _ = _mail_bauen(fotosatz, anfrage, als_entwurf=False)

    try:
        versand.sende_per_smtp(nachricht)
    except Exception as fehler:                       # noqa: BLE001
        # Bewusst die technische Meldung mitgeben: "Versand fehlgeschlagen"
        # allein hilft niemandem beim Einrichten des Relays.
        raise HTTPException(
            502, f"Versand über {settings.smtp_host} fehlgeschlagen: {fehler}"
        ) from fehler

    versand.notiere_versand(fotosatz, alle, "smtp")
    db.commit()

    return FotosatzMailErgebnis(
        fotosatz_id=fotosatz.id,
        versendet=True,
        empfaenger=alle,
        nachricht=f"Mail mit {len(fotosatz.fotos)} Foto(s) an "
                  f"{', '.join(alle)} versendet.",
    )
