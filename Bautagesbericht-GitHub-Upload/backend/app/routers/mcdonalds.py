"""McDonald's — Beauftragung hochladen, Ordner anlegen, Angebot verschicken.

Der Router bleibt dünn: HTTP annehmen, prüfen, an die Dienste weitergeben.
Die Fachlichkeit steckt in ``app.services.mcdonalds_*``.

DIE EINE ENTSCHEIDUNG, DIE HIER FÄLLT
=====================================
Die Mail-Analyse braucht einen Anthropic-Schlüssel, und auf dem Bürorechner
ist oft keiner hinterlegt (siehe einstellungen.txt). Der Upload scheitert
deshalb *nicht*, wenn die Analyse nicht möglich ist: Der Fall wird angelegt,
der Mailtext gespeichert und ein Hinweis mitgegeben. Die Angaben lassen sich
dann von Hand nachtragen (``PATCH``), und der Ordner wird danach angelegt.

Dasselbe gilt für eine fehlgeschlagene Analyse. Wer eine Mail hochgeladen hat,
soll nicht mit leeren Händen dastehen, weil die Schnittstelle gerade
überlastet war — der Text ist dann schon in der App, und ein zweiter Versuch
kostet keinen neuen Upload.
"""

from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Fachplaner, McdonaldsAngebot, McdonaldsFall
from app.schemas import (
    McdonaldsAngebotCreate,
    McdonaldsAngebotResponse,
    McdonaldsFaehigkeiten,
    McdonaldsFallManuell,
    McdonaldsFallResponse,
    McdonaldsFallUpdate,
    McdonaldsMailAnfrage,
    McdonaldsMailErgebnis,
    McdonaldsMailVorschlag,
    Mehrleistung,
    UnlocodeLadeErgebnis,
    UnlocodeTreffer,
)
from app.services import mcdonalds_angebot_generation as angebot_dienst
from app.services import mcdonalds_email_analyse as analyse
from app.services import mcdonalds_ordner as ordner_dienst
from app.services import mcdonalds_unlocode as unlocode
from app.services import mcdonalds_versand as versand

router = APIRouter(prefix="/mcdonalds", tags=["mcdonalds"])

#: Größere Dateien sind keine exportierte Mail mehr, sondern ein Versehen.
#: Eine Auftragsmail mit Verlauf liegt bei einigen Hundert Kilobyte; Anhänge
#: treiben sie hoch, werden aber nicht übernommen.
MAX_EML_MB = 25


# ─────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────────────────────


def _hole(db: Session, fall_id: int) -> McdonaldsFall:
    fall = db.get(McdonaldsFall, fall_id)
    if not fall:
        raise HTTPException(404, "Fall nicht gefunden")
    return fall


def _hole_angebot(db: Session, angebot_id: int) -> McdonaldsAngebot:
    angebot = db.get(McdonaldsAngebot, angebot_id)
    if not angebot:
        raise HTTPException(404, "Angebot nicht gefunden")
    return angebot


def _angebot_antwort(angebot: McdonaldsAngebot) -> McdonaldsAngebotResponse:
    planer = angebot.fachplaner
    return McdonaldsAngebotResponse(
        id=angebot.id,
        fall_id=angebot.fall_id,
        fachplaner_id=angebot.fachplaner_id,
        fachplaner_name=planer.name if planer else "",
        fachplaner_email=planer.email if planer else "",
        betreff=angebot.betreff or "",
        leistungsphase=angebot.leistungsphase,
        angaben=angebot.angaben or {},
        mehrleistungen=[
            Mehrleistung(**e) for e in (angebot.mehrleistungen or [])
            if isinstance(e, dict)
        ],
        dokument_vorhanden=bool(angebot.dokument_pfad),
        mail_versendet_am=angebot.mail_versendet_am,
        mail_weg=angebot.mail_weg or "",
        erstellt_am=angebot.erstellt_am,
    )


def _antwort(
    fall: McdonaldsFall, *, mit_text: bool = False, hinweise: list[str] | None = None
) -> McdonaldsFallResponse:
    """Ein Fall als Antwort. ``mit_text`` nur in der Detailansicht.

    Der Mailtext bleibt in der Liste weg: Bei fünfzig Fällen wären das
    einige Hundert Kilobyte, die niemand ansieht.
    """
    return McdonaldsFallResponse(
        id=fall.id,
        quelle=fall.quelle,
        eml_dateiname=fall.eml_dateiname or "",
        analysiert_am=fall.analysiert_am,
        auftraggeber=fall.auftraggeber or "",
        standort_name=fall.standort_name or "",
        standort_adresse=fall.standort_adresse or "",
        standort_ort=fall.standort_ort or "",
        leistungsphase=fall.leistungsphase,
        eckdaten=fall.eckdaten or {},
        anhaenge=fall.anhaenge or [],
        unlocode=fall.unlocode,
        ordner_name=fall.ordner_name or "",
        ordner_status=fall.ordner_status,
        ordner_pfad_h=fall.ordner_pfad_h,
        ordner_pfad_sharepoint=fall.ordner_pfad_sharepoint,
        fehlermeldung=fall.fehlermeldung,
        erstellt_am=fall.erstellt_am,
        aktualisiert_am=fall.aktualisiert_am,
        roh_text=(fall.roh_text or "") if mit_text else "",
        angebote=[_angebot_antwort(a) for a in fall.angebote],
        hinweise=hinweise or [],
    )


def _anhang_kopfzeile(name: str, ersatz: str) -> str:
    """Content-Disposition mit Umlauten — wie in ``routers.baufotos``.

    Standortnamen enthalten Umlaute. Ohne die RFC-5987-Fassung
    (``filename*``) kommt beim Browser "Munchen" an; ohne den schlichten
    ``filename`` verstehen ältere Browser gar nichts.
    """
    schlicht = name.encode("ascii", "ignore").decode() or ersatz
    return f'attachment; filename="{schlicht}"; filename*=UTF-8\'\'{quote(name)}'


# ─────────────────────────────────────────────────────────────────────────────
# Was der Server in diesem Bereich kann
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/faehigkeiten", response_model=McdonaldsFaehigkeiten)
def faehigkeiten(db: Session = Depends(get_db)):
    """Steuert die Knöpfe der Oberfläche — siehe Schema."""
    return McdonaldsFaehigkeiten(
        analyse=analyse.ist_verfuegbar(),
        smtp=versand.smtp_bereit(),
        absender=versand.absender_adresse(),
        ordner_h=bool((settings.mcdonalds_basis_h or "").strip()),
        ordner_sharepoint=bool((settings.mcdonalds_basis_sharepoint or "").strip()),
        unlocode_eintraege=unlocode.anzahl_eintraege(db),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Fälle
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/faelle", response_model=list[McdonaldsFallResponse])
def list_faelle(db: Session = Depends(get_db)):
    faelle = (
        db.query(McdonaldsFall)
        .order_by(McdonaldsFall.erstellt_am.desc())
        .all()
    )
    return [_antwort(fall) for fall in faelle]


@router.get("/faelle/{fall_id}", response_model=McdonaldsFallResponse)
def get_fall(fall_id: int, db: Session = Depends(get_db)):
    return _antwort(_hole(db, fall_id), mit_text=True)


@router.post("/faelle", response_model=McdonaldsFallResponse, status_code=201)
async def upload_eml(
    background_tasks: BackgroundTasks,
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Nimmt eine als ``.eml`` exportierte Auftragsmail an.

    Ablauf: lesen (immer), analysieren (wenn möglich), Fall anlegen,
    Ordneranlage als Hintergrundaufgabe anstoßen. Warum eine gescheiterte
    Analyse den Upload nicht scheitern lässt, steht im Modultext.
    """
    rohdaten = await datei.read()
    grenze = MAX_EML_MB * 1024 * 1024
    if len(rohdaten) > grenze:
        raise HTTPException(
            413,
            f"Die Datei ist {len(rohdaten) / 1024 / 1024:.1f} MB groß; "
            f"höchstens {MAX_EML_MB} MB sind vorgesehen. Bitte die Mail ohne "
            "ihre Anhänge exportieren — die Anhänge gehören in den "
            "Projektordner, nicht in die App.",
        )

    name = datei.filename or "beauftragung.eml"

    try:
        inhalt = analyse.lies_eml(rohdaten, name)
    except analyse.AnalyseFehler as fehler:
        # Eine unlesbare Datei ist etwas anderes als eine nicht ausgewertete:
        # Hier gibt es nichts zu speichern, was später zu retten wäre.
        raise HTTPException(400, str(fehler)) from fehler

    hinweise = list(inhalt.hinweise)
    angaben = analyse.FallAngaben()
    analysiert = False

    if analyse.ist_verfuegbar() and (inhalt.text or "").strip():
        try:
            angaben = await analyse.analysiere(inhalt)
            analysiert = True
            hinweise = list(angaben.hinweise)
        except analyse.AnalyseFehler as fehler:
            hinweise.append(
                f"{fehler} Die Mail ist gespeichert — die Angaben lassen sich "
                "von Hand nachtragen."
            )
    else:
        hinweise.append(
            "Die Mail wurde nicht automatisch ausgewertet"
            + (
                " (kein Anthropic-Schlüssel hinterlegt)."
                if not analyse.ist_verfuegbar()
                else "."
            )
            + " Bitte die Angaben von Hand eintragen."
        )

    fall = McdonaldsFall(
        quelle="eml",
        eml_dateiname=name,
        roh_text=inhalt.text or "",
        anhaenge=inhalt.anhaenge,
        analysiert_am=None,
        auftraggeber=angaben.auftraggeber,
        standort_name=angaben.standort_name,
        standort_adresse=angaben.standort_adresse,
        standort_ort=angaben.standort_ort,
        leistungsphase=angaben.leistungsphase,
        eckdaten=angaben.eckdaten,
        ordner_status="ausstehend",
    )
    if analysiert:
        fall.analysiert_am = datetime.now()

    db.add(fall)
    db.commit()
    db.refresh(fall)

    background_tasks.add_task(
        ordner_dienst.erzeuge_projektordner_im_hintergrund, fall.id
    )
    return _antwort(fall, mit_text=True, hinweise=hinweise)


@router.post("/faelle/manuell", response_model=McdonaldsFallResponse,
             status_code=201)
def fall_manuell(
    daten: McdonaldsFallManuell,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Telefonische Beauftragung — dieselbe Weiterverarbeitung ohne Analyse.

    Siehe Konzeptblatt: "bei telefonischer Beauftragung Eingabe der Daten in
    die App". Der Ordner entsteht danach genauso im Hintergrund.
    """
    ort = daten.standort_ort.strip()
    if not ort and daten.standort_adresse.strip():
        ort = unlocode.ort_aus_adresse(daten.standort_adresse)

    fall = McdonaldsFall(
        quelle="telefon",
        eml_dateiname="",
        roh_text=daten.notiz.strip(),
        anhaenge=[],
        # Kein ``analysiert_am``: Diese Angaben hat ein Mensch eingetragen,
        # und die Oberfläche soll das auch so zeigen.
        analysiert_am=None,
        auftraggeber=daten.auftraggeber.strip(),
        standort_name=daten.standort_name.strip(),
        standort_adresse=daten.standort_adresse.strip(),
        standort_ort=ort,
        leistungsphase=daten.leistungsphase,
        eckdaten=daten.eckdaten,
        ordner_status="ausstehend",
    )
    db.add(fall)
    db.commit()
    db.refresh(fall)

    background_tasks.add_task(
        ordner_dienst.erzeuge_projektordner_im_hintergrund, fall.id
    )
    return _antwort(fall, mit_text=True)


@router.patch("/faelle/{fall_id}", response_model=McdonaldsFallResponse)
def update_fall(
    fall_id: int, daten: McdonaldsFallUpdate, db: Session = Depends(get_db)
):
    """Korrigiert die Angaben eines Falls — siehe Schema, warum es das gibt."""
    fall = _hole(db, fall_id)
    werte = daten.model_dump(exclude_unset=True)

    for feld in ("standort_name", "standort_adresse", "standort_ort",
                 "auftraggeber"):
        if feld in werte and werte[feld] is not None:
            setattr(fall, feld, werte[feld].strip())
    if "leistungsphase" in werte:
        fall.leistungsphase = werte["leistungsphase"]
    if "eckdaten" in werte and werte["eckdaten"] is not None:
        fall.eckdaten = werte["eckdaten"]
    if "unlocode" in werte and werte["unlocode"] is not None:
        fall.unlocode = werte["unlocode"].strip().upper()

    db.commit()
    db.refresh(fall)
    return _antwort(fall, mit_text=True)


@router.post("/faelle/{fall_id}/ordner", response_model=McdonaldsFallResponse)
def ordner_erneut_anlegen(fall_id: int, db: Session = Depends(get_db)):
    """Stößt die Ordneranlage erneut an — nach einer Korrektur oder Konfiguration.

    Bewusst *nicht* im Hintergrund: Wer diesen Knopf drückt, hat gerade etwas
    geändert und will wissen, ob es jetzt geht. Ein zweiter Versuch, der
    wieder nur "wird angelegt" anzeigt, wäre keine Antwort.
    """
    fall = _hole(db, fall_id)
    ergebnis = ordner_dienst.erzeuge_projektordner(fall, db)
    db.commit()
    db.refresh(fall)
    return _antwort(
        fall,
        mit_text=True,
        hinweise=[ergebnis.meldung] if ergebnis.meldung else [],
    )


@router.delete("/faelle/{fall_id}", status_code=204)
def delete_fall(fall_id: int, db: Session = Depends(get_db)):
    """Löscht einen Fall samt seiner Angebote.

    Der angelegte Ordner im Netzlaufwerk bleibt stehen. Das ist Absicht: Dort
    liegen inzwischen vielleicht Unterlagen, und ein Löschknopf in einer
    Weboberfläche darf kein Netzlaufwerk leerräumen.
    """
    fall = _hole(db, fall_id)
    db.delete(fall)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# UN/LOCODE-Referenztabelle
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/unlocode-tabelle", response_model=UnlocodeLadeErgebnis)
async def upload_unlocode_tabelle(
    datei: UploadFile = File(...), db: Session = Depends(get_db)
):
    """Nimmt die Anlage 5.1 (Excel) an und ersetzt damit die Nachschlagetabelle."""
    rohdaten = await datei.read()
    if not rohdaten:
        raise HTTPException(400, "Die hochgeladene Datei ist leer.")

    # Die Zwischendatei liegt im Upload-Ordner der App und nicht im
    # Systemtemp: Auf Render ist das dasselbe Dateisystem, und im
    # Windows-Paket ist der Ordner der, der beim Aufräumen mitgenommen wird.
    ziel = settings.upload_dir / "mcdonalds"
    ziel.mkdir(parents=True, exist_ok=True)
    pfad = ziel / (datei.filename or "unlocode.xlsx")
    pfad.write_bytes(rohdaten)

    try:
        ergebnis = unlocode.lade_unlocode_tabelle(pfad, db)
    except unlocode.UnlocodeFehler as fehler:
        raise HTTPException(400, str(fehler)) from fehler
    finally:
        pfad.unlink(missing_ok=True)

    return UnlocodeLadeErgebnis(
        eingelesen=ergebnis.eingelesen,
        uebersprungen=ergebnis.uebersprungen,
        blatt=ergebnis.blatt,
        hinweise=ergebnis.hinweise,
    )


@router.get("/unlocode", response_model=UnlocodeTreffer)
def unlocode_nachschlagen(
    ort: str, bundesland: str = "", db: Session = Depends(get_db)
):
    """Schlägt einen Ort nach — für das Feld "UN/LOCODE" in der Oberfläche."""
    treffer = unlocode.ermittle(db, ort, bundesland)
    if not treffer:
        raise HTTPException(
            404,
            f"Für „{ort}“ war in der UN/LOCODE-Tabelle kein Eintrag zu finden."
            + (
                " Die Tabelle ist noch nicht hochgeladen."
                if unlocode.anzahl_eintraege(db) == 0
                else ""
            ),
        )
    return UnlocodeTreffer(
        code=treffer.code,
        ort=treffer.ort,
        bundesland=treffer.bundesland,
        art=treffer.art,
        guete=treffer.guete,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Angebote
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/faelle/{fall_id}/angebote", response_model=McdonaldsAngebotResponse,
             status_code=201)
def create_angebot(
    fall_id: int, daten: McdonaldsAngebotCreate, db: Session = Depends(get_db)
):
    """Legt ein Angebot an. Das Dokument entsteht im nächsten Schritt."""
    fall = _hole(db, fall_id)
    planer = db.get(Fachplaner, daten.fachplaner_id)
    if not planer:
        raise HTTPException(400, "Fachplaner nicht gefunden")

    angebot = McdonaldsAngebot(
        fall_id=fall.id,
        fachplaner_id=planer.id,
        betreff=daten.betreff.strip(),
        # Ohne eigene Angabe die Phase des Falls — das ist der Normalfall,
        # und ein leeres Pflichtfeld im Formular wäre reine Tipparbeit.
        leistungsphase=daten.leistungsphase or fall.leistungsphase,
        angaben=daten.angaben,
        mehrleistungen=[e.model_dump() for e in daten.mehrleistungen],
    )
    db.add(angebot)
    db.commit()
    db.refresh(angebot)
    return _angebot_antwort(angebot)


@router.get("/angebote/{angebot_id}", response_model=McdonaldsAngebotResponse)
def get_angebot(angebot_id: int, db: Session = Depends(get_db)):
    return _angebot_antwort(_hole_angebot(db, angebot_id))


@router.post("/angebote/{angebot_id}/dokument")
def erzeuge_dokument(angebot_id: int, db: Session = Depends(get_db)):
    """Erzeugt das Angebotsdokument, legt es ab und gibt es zum Download."""
    angebot = _hole_angebot(db, angebot_id)

    daten, name = angebot_dienst.erzeuge_angebot(angebot)
    pfad = angebot_dienst.ablegen(angebot, daten, name)
    angebot.dokument_pfad = str(pfad)
    db.commit()

    return Response(
        content=daten,
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
        headers={"Content-Disposition": _anhang_kopfzeile(name, "angebot.docx")},
    )


@router.get("/angebote/{angebot_id}/dokument")
def hole_dokument(angebot_id: int, db: Session = Depends(get_db)):
    """Liefert das schon erzeugte Dokument erneut.

    Ist die Datei nicht mehr da (auf Render startet der Container leer, siehe
    ``config.Settings``), wird sie neu gebaut statt einen 404 zu melden — die
    Angaben stehen in der Datenbank, und ein zweiter Klick ist keine Lösung,
    die jemand von selbst findet.
    """
    angebot = _hole_angebot(db, angebot_id)

    if angebot.dokument_pfad and Path(angebot.dokument_pfad).is_file():
        pfad = Path(angebot.dokument_pfad)
        daten = pfad.read_bytes()
        name = pfad.name.split("_", 1)[-1]
    else:
        daten, name = angebot_dienst.erzeuge_angebot(angebot)

    return Response(
        content=daten,
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
        headers={"Content-Disposition": _anhang_kopfzeile(name, "angebot.docx")},
    )


@router.delete("/angebote/{angebot_id}", status_code=204)
def delete_angebot(angebot_id: int, db: Session = Depends(get_db)):
    angebot = _hole_angebot(db, angebot_id)
    db.delete(angebot)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Versand
#
# Zwei Wege wie bei den Baufotos (siehe app.services.mailversand): "entwurf"
# geht immer, "senden" nur mit hinterlegtem Postausgangsserver. Beide bauen
# dieselbe Nachricht — nur die Zustellung unterscheidet sich.
# ─────────────────────────────────────────────────────────────────────────────


def _dokument_fuer(angebot: McdonaldsAngebot) -> tuple[bytes, str]:
    """Das Dokument für den Anhang — vorhandenes nehmen, sonst erzeugen."""
    if angebot.dokument_pfad and Path(angebot.dokument_pfad).is_file():
        pfad = Path(angebot.dokument_pfad)
        return pfad.read_bytes(), pfad.name.split("_", 1)[-1]
    return angebot_dienst.erzeuge_angebot(angebot)


def _empfaenger_fuer(
    angebot: McdonaldsAngebot, anfrage: McdonaldsMailAnfrage
) -> list[str]:
    """Die Adressen aus dem Dialog, sonst die des Fachplaners."""
    aus_dialog = [str(adresse) for adresse in anfrage.empfaenger]
    if aus_dialog:
        return aus_dialog
    planer = angebot.fachplaner
    if planer and (planer.email or "").strip():
        return [planer.email.strip()]
    raise HTTPException(
        400,
        "Für dieses Angebot ist keine Empfängeradresse hinterlegt. Bitte beim "
        "Fachplaner in den Stammdaten eine E-Mail eintragen.",
    )


def _mail_bauen(
    angebot: McdonaldsAngebot, anfrage: McdonaldsMailAnfrage, *, als_entwurf: bool
):
    """Gemeinsamer Teil beider Wege: prüfen, Dokument holen, Nachricht bauen."""
    empfaenger = _empfaenger_fuer(angebot, anfrage)
    kopie = [str(adresse) for adresse in anfrage.kopie]
    daten, name = _dokument_fuer(angebot)

    nachricht = versand.baue_nachricht(
        angebot,
        empfaenger=empfaenger,
        kopie=kopie,
        betreff=anfrage.betreff.strip() or versand.betreff_fuer(angebot),
        text=anfrage.nachricht.strip() or versand.standardtext_fuer(angebot),
        dokument=daten,
        dokument_name=name,
        absender=versand.absender_adresse(),
        als_entwurf=als_entwurf,
    )
    return nachricht, empfaenger + kopie, name


@router.get("/angebote/{angebot_id}/mail/vorschlag",
            response_model=McdonaldsMailVorschlag)
def mail_vorschlag(angebot_id: int, db: Session = Depends(get_db)):
    """Empfänger, Betreff und Text, mit denen der Dialog startet."""
    angebot = _hole_angebot(db, angebot_id)
    planer = angebot.fachplaner
    return McdonaldsMailVorschlag(
        empfaenger=[planer.email] if planer and planer.email else [],
        betreff=versand.betreff_fuer(angebot),
        nachricht=versand.standardtext_fuer(angebot),
        dokument_dateiname=angebot_dienst.dateiname(angebot),
        dokument_vorhanden=bool(
            angebot.dokument_pfad and Path(angebot.dokument_pfad).is_file()
        ),
    )


@router.post("/angebote/{angebot_id}/versenden")
def mail_entwurf(
    angebot_id: int,
    anfrage: McdonaldsMailAnfrage | None = None,
    db: Session = Depends(get_db),
):
    """Fertige Mail als ``.eml`` — Outlook öffnet sie als Entwurf zum Senden.

    Der Weg, der ohne jede Serverkonfiguration funktioniert. Deshalb wird auch
    hier der Versand notiert, allerdings als ``weg="entwurf"``: Abgeschickt
    hat die Mail dann Outlook, nicht die App.
    """
    angebot = _hole_angebot(db, angebot_id)
    nachricht, alle, dokument_name = _mail_bauen(
        angebot, anfrage or McdonaldsMailAnfrage(), als_entwurf=True
    )

    versand.notiere_versand(angebot, "entwurf")
    db.commit()

    name = f"{Path(dokument_name).stem}.eml"
    return Response(
        content=nachricht.as_bytes(),
        media_type="message/rfc822",
        headers={"Content-Disposition": _anhang_kopfzeile(name, "angebot.eml")},
    )


@router.post("/angebote/{angebot_id}/mail/senden",
             response_model=McdonaldsMailErgebnis)
def mail_senden(
    angebot_id: int,
    anfrage: McdonaldsMailAnfrage | None = None,
    db: Session = Depends(get_db),
):
    """Verschickt das Angebot wirklich — nur mit hinterlegtem SMTP-Server."""
    angebot = _hole_angebot(db, angebot_id)

    if not versand.smtp_bereit():
        raise HTTPException(
            503,
            "Es ist kein Postausgangsserver hinterlegt (BTB_SMTP_HOST). "
            "Nutze den Outlook-Entwurf — der braucht keinen Server.",
        )

    nachricht, alle, _ = _mail_bauen(
        angebot, anfrage or McdonaldsMailAnfrage(), als_entwurf=False
    )

    try:
        versand.sende_per_smtp(nachricht)
    except Exception as fehler:  # noqa: BLE001
        # Bewusst die technische Meldung mitgeben: "Versand fehlgeschlagen"
        # allein hilft niemandem beim Einrichten des Relays.
        raise HTTPException(
            502, f"Versand über {settings.smtp_host} fehlgeschlagen: {fehler}"
        ) from fehler

    versand.notiere_versand(angebot, "smtp")
    db.commit()

    return McdonaldsMailErgebnis(
        angebot_id=angebot.id,
        versendet=True,
        empfaenger=alle,
        nachricht=f"Angebot an {', '.join(alle)} verschickt.",
    )
