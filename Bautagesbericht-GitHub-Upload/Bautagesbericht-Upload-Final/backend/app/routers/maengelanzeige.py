"""Mängelanzeige: zwei Word-Dokumente aus den erfassten Mängeln.

Drei Endpunkte, die dem Ablauf im Büro folgen:

    GET  /maengelanzeige/vorbelegung   Was das Formular anbieten soll
    POST /maengelanzeige/vorschau      Was entstehen würde, ohne es zu bauen
    POST /maengelanzeige/dokumente     Die beiden Dateien

Der Versand selbst passiert in Outlook — hier entstehen nur die Dokumente.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Gewerk, Mangel, Projekt
from app.schemas import (
    MaengelanzeigeAnfrage,
    MaengelanzeigeBereichVorschau,
    MaengelanzeigeEmpfaenger,
    MaengelanzeigeSachbearbeiter,
    MaengelanzeigeVorbelegung,
    MaengelanzeigeVorschau,
)
from app.services import maengelanzeige_daten as brueck
from app.services import maengelanzeige_generation as erzeugung

router = APIRouter(prefix="/maengelanzeige", tags=["maengelanzeige"])


# ─────────────────────────────────────────────────────────────────────────────
# Hilfen
# ─────────────────────────────────────────────────────────────────────────────


def _projekt(db: Session, projekt_id: int) -> Projekt:
    projekt = db.get(Projekt, projekt_id)
    if projekt is None:
        raise HTTPException(404, "Projekt nicht gefunden")
    return projekt


def _gewerk(db: Session, projekt: Projekt, gewerk_id: int | None) -> Gewerk | None:
    if gewerk_id is None:
        return None
    gewerk = db.get(Gewerk, gewerk_id)
    if gewerk is None:
        raise HTTPException(404, "Firma / Gewerk nicht gefunden")
    if gewerk.projekt_id != projekt.id:
        raise HTTPException(400, "Die Firma gehört zu einem anderen Projekt")
    return gewerk


def _maengel(db: Session, projekt: Projekt, ids: list[int]) -> list[Mangel]:
    """Die gewählten Mängel in der Reihenfolge der Anfrage.

    Die Reihenfolge kommt aus der Oberfläche und bestimmt die Reihenfolge der
    Bereiche in der Anlage — deshalb wird sie nicht wegsortiert.
    """
    gefunden = {
        m.id: m
        for m in db.query(Mangel).filter(Mangel.id.in_(ids)).all()
    }
    fehlend = [i for i in ids if i not in gefunden]
    if fehlend:
        raise HTTPException(
            404, f"Diese Mängel gibt es nicht (mehr): {', '.join(map(str, fehlend))}"
        )
    fremd = [i for i in ids if gefunden[i].projekt_id != projekt.id]
    if fremd:
        raise HTTPException(
            400,
            f"Diese Mängel gehören zu einem anderen Projekt: "
            f"{', '.join(map(str, fremd))}",
        )
    return [gefunden[i] for i in ids]


def _in_dataclass(
    empfaenger: MaengelanzeigeEmpfaenger,
    sachbearbeiter: MaengelanzeigeSachbearbeiter,
) -> tuple[erzeugung.Empfaenger, erzeugung.Sachbearbeiter]:
    return (
        erzeugung.Empfaenger(
            firma=empfaenger.firma,
            ansprechpartner=empfaenger.ansprechpartner,
            strasse_hausnummer=empfaenger.strasse_hausnummer,
            plz_ort=empfaenger.plz_ort,
            versandart=empfaenger.versandart,
            email=str(empfaenger.email or ""),
        ),
        erzeugung.Sachbearbeiter(
            name=sachbearbeiter.name,
            funktion=sachbearbeiter.funktion,
            zeichen=sachbearbeiter.zeichen,
            auftragsnummer=sachbearbeiter.auftragsnummer,
            email=str(sachbearbeiter.email or ""),
        ),
    )


def _sammle(db: Session, anfrage: MaengelanzeigeAnfrage):
    """Anfrage → Daten für den Erzeuger, samt Hinweisen."""
    projekt = _projekt(db, anfrage.projekt_id)
    gewerk = _gewerk(db, projekt, anfrage.gewerk_id)
    maengel = _maengel(db, projekt, anfrage.mangel_ids)
    empfaenger, sachbearbeiter = _in_dataclass(anfrage.empfaenger, anfrage.sachbearbeiter)

    briefdatum = anfrage.briefdatum or date.today()
    frist = anfrage.fristsetzungsdatum or brueck.fristvorschlag(briefdatum, maengel)

    return brueck.sammle(
        db,
        projekt=projekt,
        gewerk=gewerk,
        maengel=maengel,
        empfaenger=empfaenger,
        sachbearbeiter=sachbearbeiter,
        begehungsdatum=anfrage.begehungsdatum,
        briefdatum=briefdatum,
        fristsetzungsdatum=frist,
        anlagedatum=anfrage.anlagedatum,
        projektbezeichnung=anfrage.projektbezeichnung,
        vergabeeinheit=anfrage.vergabeeinheit,
        dokumentkuerzel=anfrage.dokumentkuerzel,
    )


def _anhang_kopfzeile(name: str, ersatz: str) -> str:
    """Content-Disposition mit Umlauten (RFC 5987) — Projektnamen haben welche."""
    from urllib.parse import quote

    schlicht = name.encode("ascii", "ignore").decode() or ersatz
    return f'attachment; filename="{schlicht}"; filename*=UTF-8\'\'{quote(name)}'


# ─────────────────────────────────────────────────────────────────────────────
# Endpunkte
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/vorbelegung", response_model=MaengelanzeigeVorbelegung)
def vorbelegung(
    projekt_id: int,
    gewerk_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Vorschläge für das Formular: Adresse der Firma, Kürzel, Fristvorschlag.

    Damit muss niemand die Vergabeeinheit oder das Dokumentkürzel abtippen —
    beides steht schon in den Stammdaten.
    """
    projekt = _projekt(db, projekt_id)
    gewerk = _gewerk(db, projekt, gewerk_id)
    heute = date.today()

    offene = [
        m for m in (gewerk.maengel if gewerk is not None else projekt.maengel)
        if not m.erledigt_am
    ]
    empfaenger = brueck.empfaenger_aus_gewerk(gewerk)

    return MaengelanzeigeVorbelegung(
        projektbezeichnung=projekt.name,
        vergabeeinheit=brueck.vergabeeinheit_von(gewerk),
        dokumentkuerzel=brueck.dokumentkuerzel_vorschlag(projekt, gewerk),
        begehungsdatum=heute,
        briefdatum=heute,
        fristsetzungsdatum=brueck.fristvorschlag(heute, offene),
        empfaenger=MaengelanzeigeEmpfaenger(
            firma=empfaenger.firma,
            ansprechpartner=empfaenger.ansprechpartner,
            strasse_hausnummer=empfaenger.strasse_hausnummer,
            plz_ort=empfaenger.plz_ort,
            versandart=empfaenger.versandart,
            email=empfaenger.email or None,
        ),
        betreff_dritte_zeile=erzeugung.BETREFF_DRITTE_ZEILE,
    )


@router.post("/vorschau", response_model=MaengelanzeigeVorschau)
def vorschau(anfrage: MaengelanzeigeAnfrage, db: Session = Depends(get_db)):
    """Was entstehen würde — ohne die Dokumente zu bauen.

    Die Oberfläche zeigt damit vor dem Erzeugen, welche Bereiche mit welchen
    Bildunterschriften in der Anlage stehen und welche Mängel fehlen.
    """
    daten, hinweise = _sammle(db, anfrage)
    try:
        erzeugung.pruefe(daten)
    except erzeugung.MaengelanzeigeFehler as fehler:
        # 422: Die Anfrage ist formal in Ordnung, aber inhaltlich unvollständig.
        raise HTTPException(422, str(fehler)) from fehler

    return MaengelanzeigeVorschau(
        dateiname_anschreiben=erzeugung.dateiname_anschreiben(daten),
        dateiname_anlage=erzeugung.dateiname_anlage(daten),
        fristsetzungsdatum=daten.fristsetzungsdatum,
        anzahl_fotos=sum(len(b.eintraege) for b in daten.bereiche),
        bereiche=[
            MaengelanzeigeBereichVorschau(
                bereich=bereich.bereich,
                anzahl_fotos=len(bereich.eintraege),
                beschreibungen=[e.beschreibung for e in bereich.eintraege],
            )
            for bereich in daten.bereiche
        ],
        hinweise=hinweise,
    )


@router.post("/dokumente")
def dokumente(
    anfrage: MaengelanzeigeAnfrage,
    nur: str | None = Query(
        None,
        description="anschreiben oder anlage — ohne Angabe kommen beide als ZIP",
    ),
    db: Session = Depends(get_db),
):
    """Erzeugt die Dokumente.

    Ohne ``nur`` kommt ein ZIP mit **beiden** Dateien: Ein Vorgang besteht aus
    Anschreiben und Anlage, und die gehören zusammen verschickt. Wer nur eines
    braucht (etwa weil die Anlage schon beim Bauherrn liegt), fragt es einzeln
    ab — zusammengeführt wird nie.
    """
    daten, hinweise = _sammle(db, anfrage)

    try:
        if nur == "anschreiben":
            return Response(
                content=erzeugung.erzeuge_anschreiben(daten),
                media_type="application/vnd.openxmlformats-officedocument"
                           ".wordprocessingml.document",
                headers={
                    "Content-Disposition": _anhang_kopfzeile(
                        erzeugung.dateiname_anschreiben(daten), "anschreiben.docx"
                    )
                },
            )
        if nur == "anlage":
            return Response(
                content=erzeugung.erzeuge_anlage(daten),
                media_type="application/vnd.openxmlformats-officedocument"
                           ".wordprocessingml.document",
                headers={
                    "Content-Disposition": _anhang_kopfzeile(
                        erzeugung.dateiname_anlage(daten), "anlage.docx"
                    )
                },
            )
        if nur is not None:
            raise HTTPException(
                400, "Erlaubt sind „anschreiben“, „anlage“ oder keine Angabe."
            )

        dateien = erzeugung.erzeuge_beide(daten)
    except erzeugung.MaengelanzeigeFehler as fehler:
        raise HTTPException(422, str(fehler)) from fehler

    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", compression=zipfile.ZIP_DEFLATED) as archiv:
        for name, inhalt in dateien.items():
            archiv.writestr(name, inhalt)
        if hinweise:
            # Was nicht ins Dokument kam, steht als Zettel im Archiv — sonst
            # fällt es erst auf, wenn die Firma nach einem Mangel fragt.
            archiv.writestr(
                "HINWEISE.txt",
                "Beim Erzeugen der Mängelanzeige übersprungen:\r\n\r\n"
                + "\r\n".join(f"- {h}" for h in hinweise)
                + "\r\n",
            )

    name = f"{erzeugung.dateiname_anschreiben(daten)[:-5]}_Anschreiben+Anlage.zip"
    return Response(
        content=puffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": _anhang_kopfzeile(name, "maengelanzeige.zip")},
    )
