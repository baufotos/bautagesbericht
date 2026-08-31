"""Projektberichte: anlegen, pflegen, erzeugen, wiederfinden.

Der Bericht ist ein Datensatz, kein Wegwerf-Export: Er lebt am Projekt, kann
über Wochen weitergeschrieben werden, und das erzeugte Dokument bleibt am
Bericht hängen. „Nochmal erzeugen“ überschreibt es — dieselbe Nummer ergibt
denselben Dateinamen, und im Ablageordner soll nicht dreimal derselbe Bericht
in leicht verschiedenen Fassungen liegen.

Feste Pfade (``/gliederung``, ``/vorlage``, ``/fotos/...``) stehen vor den
Pfaden mit ``/{bericht_id}`` — FastAPI prüft in Registrierungsreihenfolge.
"""

from __future__ import annotations

from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Projekt, Projektbericht, ProjektberichtFoto
from app.schemas import (
    GliederungHauptkapitel,
    GliederungUnterkapitel,
    ProjektberichtCreate,
    ProjektberichtFotoResponse,
    ProjektberichtFotoUpdate,
    ProjektberichtListItem,
    ProjektberichtResponse,
    ProjektberichtUpdate,
    ProjektberichtVorschau,
    ProjektberichtVorschauKapitel,
)
from app.services import projektbericht_generation as erzeugung
from app.services import projektbericht_gliederung as gliederung
from app.services import word_pdf
from app.utils.file_storage import get_absolute_path, save_upload_in

router = APIRouter(prefix="/projektberichte", tags=["projektberichte"])


# ─────────────────────────────────────────────────────────────────────────────
# Umwandlung Datenbank ↔ Erzeuger
# ─────────────────────────────────────────────────────────────────────────────


def _hole(db: Session, bericht_id: int) -> Projektbericht:
    bericht = db.get(Projektbericht, bericht_id)
    if bericht is None:
        raise HTTPException(404, "Projektbericht nicht gefunden")
    return bericht


def _zu_listitem(bericht: Projektbericht) -> ProjektberichtListItem:
    eintrag = ProjektberichtListItem.model_validate(bericht)
    eintrag.projekt_name = bericht.projekt.name if bericht.projekt else ""
    eintrag.anzahl_fotos = len(bericht.fotos)
    eintrag.anzahl_kapitel = len(gliederung.nummeriere(_inhalte(bericht)))
    eintrag.hat_dokument = bool(bericht.dokument_pfad)
    eintrag.hat_pdf = bool(bericht.pdf_pfad)
    return eintrag


def _zu_detail(bericht: Projektbericht) -> ProjektberichtResponse:
    antwort = ProjektberichtResponse.model_validate(bericht)
    antwort.projekt_name = bericht.projekt.name if bericht.projekt else ""
    antwort.anzahl_fotos = len(bericht.fotos)
    antwort.anzahl_kapitel = len(gliederung.nummeriere(_inhalte(bericht)))
    antwort.hat_dokument = bool(bericht.dokument_pfad)
    antwort.hat_pdf = bool(bericht.pdf_pfad)
    antwort.fotos = [
        ProjektberichtFotoResponse.model_validate(f)
        for f in sorted(bericht.fotos, key=lambda f: (f.reihenfolge, f.id))
    ]
    return antwort


def _inhalte(bericht: Projektbericht) -> dict[str, object]:
    """Kapitelschlüssel → Inhalt, so wie die Nummerierung es erwartet."""
    werte: dict[str, object] = dict(bericht.kapitel or {})
    werte["baubegehungen"] = list(bericht.baubegehungen or [])
    werte["besprechungen"] = list(bericht.besprechungen or [])
    werte["soll_ist"] = list(bericht.soll_ist or [])
    werte["fotos"] = list(bericht.fotos or [])
    return werte


def _in_erzeuger(bericht: Projektbericht) -> erzeugung.Projektbericht:
    """Datensatz → Datenklasse des Erzeugers, samt Fotobytes."""
    fotos: list[erzeugung.Berichtsfoto] = []
    for foto in sorted(bericht.fotos, key=lambda f: (f.reihenfolge, f.id)):
        pfad = get_absolute_path(foto.dateipfad)
        if not pfad.is_file():
            # Ein verlorenes Bild darf den ganzen Bericht nicht verhindern.
            continue
        fotos.append(erzeugung.Berichtsfoto(
            daten=pfad.read_bytes(),
            bildunterschrift=foto.bildunterschrift or "",
        ))

    projektname = (bericht.projektname or "").strip() or (
        bericht.projekt.name if bericht.projekt else ""
    )
    return erzeugung.Projektbericht(
        projektname=projektname,
        projektkuerzel=bericht.projektkuerzel or "",
        nummer=bericht.nummer,
        berichtsdatum=bericht.berichtsdatum,
        ersteller=bericht.ersteller or "",
        buero=bericht.buero or "HPP",
        zeitraum_von=bericht.zeitraum_von,
        zeitraum_bis=bericht.zeitraum_bis,
        kapitel=dict(bericht.kapitel or {}),
        baubegehungen=[erzeugung.Baubegehung(**e) for e in (bericht.baubegehungen or [])],
        besprechungen=[erzeugung.Besprechung(**e) for e in (bericht.besprechungen or [])],
        soll_ist=[erzeugung.SollIstZeile(**e) for e in (bericht.soll_ist or [])],
        fotos=fotos,
    )


def _naechste_nummer(db: Session, projekt_id: int) -> int:
    """Höchste vergebene Nummer plus eins.

    Bewusst Maximum statt Anzahl: Wird ein Bericht gelöscht, soll die Nummer
    nicht ein zweites Mal vergeben werden — draußen liegt sie längst im
    Posteingang des Bauherrn.
    """
    hoechste = (
        db.query(func.max(Projektbericht.nummer))
        .filter(Projektbericht.projekt_id == projekt_id)
        .scalar()
    )
    return int(hoechste or 0) + 1


def _kuerzel_vorschlag(projekt: Projekt) -> str:
    """„BOB Boulevard Berlin“ → „BOB“ — das erste Wort, wie im Original."""
    erstes = (projekt.name or "").strip().split(" ")[0]
    sauber = "".join(z for z in erstes if z.isalnum() or z in "-_.")
    return sauber or "Projekt"


def _anhang_kopfzeile(name: str, ersatz: str) -> str:
    schlicht = name.encode("ascii", "ignore").decode() or ersatz
    return f'attachment; filename="{schlicht}"; filename*=UTF-8\'\'{quote(name)}'


# ─────────────────────────────────────────────────────────────────────────────
# Feste Pfade
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/gliederung", response_model=list[GliederungHauptkapitel])
def gliederung_lesen():
    """Die Standardgliederung — daraus baut die Oberfläche ihr Formular.

    Ein neues Kapitel wird in ``services/projektbericht_gliederung`` ergänzt
    und erscheint danach von selbst im Formular und im Dokument.
    """
    return [
        GliederungHauptkapitel(
            schluessel=haupt.schluessel,
            titel=haupt.titel,
            art=haupt.art,
            ohne_ueberschrift=haupt.ohne_ueberschrift,
            unterkapitel=[
                GliederungUnterkapitel(
                    schluessel=u.schluessel, titel=u.titel, art=u.art,
                    immer_zeigen=u.immer_zeigen,
                )
                for u in haupt.unterkapitel
            ],
        )
        for haupt in gliederung.GLIEDERUNG
    ]


@router.get("/vorlage", response_model=ProjektberichtCreate)
def vorlage(projekt_id: int, db: Session = Depends(get_db)):
    """Vorschlag für einen neuen Bericht: nächste Nummer, Kürzel, Kopfzeile."""
    projekt = db.get(Projekt, projekt_id)
    if projekt is None:
        raise HTTPException(404, "Projekt nicht gefunden")

    letzter = (
        db.query(Projektbericht)
        .filter(Projektbericht.projekt_id == projekt_id)
        .order_by(Projektbericht.nummer.desc())
        .first()
    )
    return ProjektberichtCreate(
        projekt_id=projekt_id,
        nummer=_naechste_nummer(db, projekt_id),
        berichtsdatum=date.today(),
        ersteller=letzter.ersteller if letzter else "",
        projektname=(letzter.projektname if letzter else "") or projekt.name,
        projektkuerzel=(letzter.projektkuerzel if letzter else "")
        or _kuerzel_vorschlag(projekt),
        buero=letzter.buero if letzter else "HPP",
    )


@router.get("/fotos/{foto_id}/bild")
def foto_bild(foto_id: int, db: Session = Depends(get_db)):
    foto = db.get(ProjektberichtFoto, foto_id)
    if foto is None:
        raise HTTPException(404, "Foto nicht gefunden")
    pfad = get_absolute_path(foto.dateipfad)
    if not pfad.is_file():
        raise HTTPException(404, "Bilddatei nicht gefunden")
    return FileResponse(pfad, headers={"Cache-Control": "private, max-age=86400"})


@router.patch("/fotos/{foto_id}", response_model=ProjektberichtFotoResponse)
def foto_aendern(foto_id: int, daten: ProjektberichtFotoUpdate,
                 db: Session = Depends(get_db)):
    """Bildunterschrift oder Reihenfolge ändern (Ziehen und Ablegen)."""
    foto = db.get(ProjektberichtFoto, foto_id)
    if foto is None:
        raise HTTPException(404, "Foto nicht gefunden")
    for feld, wert in daten.model_dump(exclude_unset=True).items():
        setattr(foto, feld, wert)
    db.commit()
    db.refresh(foto)
    return ProjektberichtFotoResponse.model_validate(foto)


@router.delete("/fotos/{foto_id}", status_code=204)
def foto_loeschen(foto_id: int, db: Session = Depends(get_db)):
    foto = db.get(ProjektberichtFoto, foto_id)
    if foto is None:
        raise HTTPException(404, "Foto nicht gefunden")
    pfad = get_absolute_path(foto.dateipfad)
    if pfad.is_file():
        pfad.unlink()
    db.delete(foto)
    db.commit()
    return Response(status_code=204)


# ─────────────────────────────────────────────────────────────────────────────
# Berichte
# ─────────────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[ProjektberichtListItem])
def liste(projekt_id: int | None = None, db: Session = Depends(get_db)):
    abfrage = db.query(Projektbericht)
    if projekt_id is not None:
        abfrage = abfrage.filter(Projektbericht.projekt_id == projekt_id)
    berichte = abfrage.order_by(
        Projektbericht.projekt_id, Projektbericht.nummer.desc()
    ).all()
    return [_zu_listitem(b) for b in berichte]


@router.post("", response_model=ProjektberichtResponse, status_code=201)
def anlegen(daten: ProjektberichtCreate, db: Session = Depends(get_db)):
    projekt = db.get(Projekt, daten.projekt_id)
    if projekt is None:
        raise HTTPException(400, "Projekt nicht gefunden")

    nummer = daten.nummer or _naechste_nummer(db, daten.projekt_id)
    doppelt = (
        db.query(Projektbericht)
        .filter(Projektbericht.projekt_id == daten.projekt_id,
                Projektbericht.nummer == nummer)
        .first()
    )
    if doppelt is not None:
        raise HTTPException(
            409,
            f"Für dieses Projekt gibt es bereits einen Bericht Nr. {nummer} "
            f"(vom {doppelt.berichtsdatum:%d.%m.%Y}). Bitte eine andere Nummer "
            f"wählen oder den vorhandenen Bericht bearbeiten.",
        )

    bericht = Projektbericht(
        projekt_id=daten.projekt_id,
        nummer=nummer,
        berichtsdatum=daten.berichtsdatum or date.today(),
        zeitraum_von=daten.zeitraum_von,
        zeitraum_bis=daten.zeitraum_bis,
        ersteller=daten.ersteller.strip(),
        projektname=(daten.projektname or "").strip() or projekt.name,
        projektkuerzel=(daten.projektkuerzel or "").strip()
        or _kuerzel_vorschlag(projekt),
        buero=(daten.buero or "HPP").strip(),
        kapitel=dict(daten.kapitel or {}),
        baubegehungen=[e.model_dump() for e in daten.baubegehungen],
        besprechungen=[e.model_dump() for e in daten.besprechungen],
        soll_ist=[e.model_dump() for e in daten.soll_ist],
    )

    if daten.aus_letztem_bericht:
        _uebernehme_vom_letzten(db, bericht)

    db.add(bericht)
    db.commit()
    db.refresh(bericht)
    return _zu_detail(bericht)


def _uebernehme_vom_letzten(db: Session, bericht: Projektbericht) -> None:
    """Inhalte des zuletzt erstellten Berichts als Ausgangsbasis übernehmen.

    Ein Monatsbericht schreibt den vorigen fort — Meilensteine, Besprechungen
    und SOLL-IST ändern sich in Teilen, nicht in Gänze. Übernommen wird nur,
    was der neue Bericht noch nicht selbst mitbringt; Fotos bleiben außen vor,
    die gehören zum jeweiligen Monat.
    """
    letzter = (
        db.query(Projektbericht)
        .filter(Projektbericht.projekt_id == bericht.projekt_id,
                Projektbericht.nummer < bericht.nummer)
        .order_by(Projektbericht.nummer.desc())
        .first()
    )
    if letzter is None:
        return
    if not bericht.kapitel:
        bericht.kapitel = dict(letzter.kapitel or {})
    if not bericht.baubegehungen:
        bericht.baubegehungen = list(letzter.baubegehungen or [])
    if not bericht.besprechungen:
        bericht.besprechungen = list(letzter.besprechungen or [])
    if not bericht.soll_ist:
        bericht.soll_ist = list(letzter.soll_ist or [])


@router.get("/{bericht_id}", response_model=ProjektberichtResponse)
def lesen(bericht_id: int, db: Session = Depends(get_db)):
    return _zu_detail(_hole(db, bericht_id))


@router.patch("/{bericht_id}", response_model=ProjektberichtResponse)
def aendern(bericht_id: int, daten: ProjektberichtUpdate,
            db: Session = Depends(get_db)):
    bericht = _hole(db, bericht_id)
    werte = daten.model_dump(exclude_unset=True)

    if "nummer" in werte and werte["nummer"] and werte["nummer"] != bericht.nummer:
        doppelt = (
            db.query(Projektbericht)
            .filter(Projektbericht.projekt_id == bericht.projekt_id,
                    Projektbericht.nummer == werte["nummer"],
                    Projektbericht.id != bericht.id)
            .first()
        )
        if doppelt is not None:
            raise HTTPException(
                409, f"Bericht Nr. {werte['nummer']} gibt es in diesem Projekt schon."
            )

    for feld in ("baubegehungen", "besprechungen", "soll_ist"):
        if feld in werte and werte[feld] is not None:
            werte[feld] = [
                e if isinstance(e, dict) else e.model_dump() for e in werte[feld]
            ]

    for feld, wert in werte.items():
        if wert is None and feld in ("nummer", "berichtsdatum"):
            continue          # Pflichtfelder nicht versehentlich leeren
        setattr(bericht, feld, wert)

    db.commit()
    db.refresh(bericht)
    return _zu_detail(bericht)


@router.delete("/{bericht_id}", status_code=204)
def loeschen(bericht_id: int, db: Session = Depends(get_db)):
    from app.services.cleanup import delete_projektbericht_cascade

    bericht = _hole(db, bericht_id)
    delete_projektbericht_cascade(db, bericht)
    db.commit()
    return Response(status_code=204)


@router.post("/{bericht_id}/fotos", response_model=list[ProjektberichtFotoResponse],
             status_code=201)
async def fotos_hochladen(bericht_id: int, dateien: list[UploadFile] = File(...),
                          db: Session = Depends(get_db)):
    """Fotos anhängen. Reihenfolge zunächst nach Upload, später änderbar."""
    bericht = _hole(db, bericht_id)
    hoechste = max((f.reihenfolge for f in bericht.fotos), default=-1)

    neue: list[ProjektberichtFoto] = []
    for lauf, datei in enumerate(dateien, start=1):
        pfad = await save_upload_in(f"projektberichte/{bericht.id}", datei)
        foto = ProjektberichtFoto(
            bericht_id=bericht.id,
            dateipfad=pfad,
            bildunterschrift="",
            reihenfolge=hoechste + lauf,
        )
        db.add(foto)
        neue.append(foto)

    db.commit()
    for foto in neue:
        db.refresh(foto)
    return [ProjektberichtFotoResponse.model_validate(f) for f in neue]


@router.get("/{bericht_id}/vorschau", response_model=ProjektberichtVorschau)
def vorschau(bericht_id: int, db: Session = Depends(get_db)):
    """Welche Kapitel erscheinen, mit welcher Nummer — und was entfällt.

    Das ist die Kontrolle vor dem Erzeugen: Genau hier sieht man, dass aus
    „2.3 Verzögerungen“ eine „2.2“ wird, weil „Fortschritt“ leer geblieben ist.
    """
    bericht = _hole(db, bericht_id)
    inhalte = _inhalte(bericht)
    kapitel = gliederung.nummeriere(inhalte)
    gezeigt = {k.schluessel for k in kapitel}

    entfallen = [
        f"{haupt.titel} / {unter.titel}" if haupt.unterkapitel else haupt.titel
        for haupt in gliederung.GLIEDERUNG
        for unter in (haupt.unterkapitel or (haupt,))
        if unter.schluessel not in gezeigt
    ]

    daten = _in_erzeuger(bericht)
    return ProjektberichtVorschau(
        dateiname_docx=erzeugung.dateiname(daten, "docx"),
        dateiname_pdf=erzeugung.dateiname(daten, "pdf"),
        kapitel=[
            ProjektberichtVorschauKapitel(
                nummer=k.nummer, titel=k.titel, ebene=k.ebene,
                schluessel=k.schluessel, art=k.art,
                hat_inhalt=not gliederung.ist_leer(k.inhalt),
            )
            for k in kapitel
        ],
        entfallen=entfallen,
        anzahl_fotos=len(bericht.fotos),
        pdf_moeglich=word_pdf.word_vorhanden(),
    )


@router.post("/{bericht_id}/dokument")
def dokument(bericht_id: int,
             format: str = Query("docx", pattern="^(docx|pdf)$"),
             db: Session = Depends(get_db)):
    """Erzeugt den Bericht, legt ihn am Projekt ab und liefert ihn aus."""
    bericht = _hole(db, bericht_id)
    daten = _in_erzeuger(bericht)

    try:
        inhalt = erzeugung.erzeuge_bericht(daten)
    except erzeugung.ProjektberichtFehler as fehler:
        raise HTTPException(422, str(fehler)) from fehler

    ordner = settings.output_dir / "projektberichte" / str(bericht.id)
    ordner.mkdir(parents=True, exist_ok=True)

    name_docx = erzeugung.dateiname(daten, "docx")
    (ordner / name_docx).write_bytes(inhalt)
    bericht.dokument_pfad = str((ordner / name_docx).relative_to(settings.output_dir))
    bericht.erzeugt_am = datetime.now()

    if format == "pdf":
        try:
            pdf = word_pdf.nach_pdf(inhalt)
        except word_pdf.PdfNichtMoeglich as fehler:
            db.commit()          # das Word-Dokument ist trotzdem entstanden
            raise HTTPException(503, str(fehler)) from fehler
        name_pdf = erzeugung.dateiname(daten, "pdf")
        (ordner / name_pdf).write_bytes(pdf)
        bericht.pdf_pfad = str((ordner / name_pdf).relative_to(settings.output_dir))
        db.commit()
        return Response(
            content=pdf, media_type="application/pdf",
            headers={"Content-Disposition": _anhang_kopfzeile(name_pdf, "bericht.pdf")},
        )

    db.commit()
    return Response(
        content=inhalt,
        media_type="application/vnd.openxmlformats-officedocument"
                   ".wordprocessingml.document",
        headers={"Content-Disposition": _anhang_kopfzeile(name_docx, "bericht.docx")},
    )


@router.get("/{bericht_id}/dokument")
def dokument_abrufen(bericht_id: int,
                     format: str = Query("docx", pattern="^(docx|pdf)$"),
                     db: Session = Depends(get_db)):
    """Das zuletzt erzeugte Dokument — ohne es neu zu bauen.

    Für die Historie: Der Bericht von vorletztem Monat soll genau die Datei
    liefern, die damals verschickt wurde.
    """
    bericht = _hole(db, bericht_id)
    pfad_teil = bericht.pdf_pfad if format == "pdf" else bericht.dokument_pfad
    if not pfad_teil:
        raise HTTPException(
            404,
            "Für diesen Bericht wurde noch kein "
            + ("PDF" if format == "pdf" else "Word-Dokument")
            + " erzeugt.",
        )
    pfad = settings.output_dir / pfad_teil
    if not pfad.is_file():
        raise HTTPException(404, "Die abgelegte Datei ist nicht mehr vorhanden.")
    return FileResponse(
        pfad,
        headers={"Content-Disposition": _anhang_kopfzeile(pfad.name, "bericht")},
    )
