"""McDonald's — Standort aus der SLS-Mail, Ordner, Einzelabrufe an Subplaner.

Der Router bleibt dünn: HTTP annehmen, prüfen, an die Dienste weitergeben.
Die Fachlichkeit steckt in ``app.services.mcdonalds_*``.

DIE ZWEI ENTSCHEIDUNGEN, DIE HIER FALLEN
========================================
**Erstens: Regeln zuerst, Modell nur als Notausgang.** Die SLS-Anfrage wird
von ``mcdonalds_sls`` nach Regeln gelesen — ohne Schlüssel, ohne Netz, ohne
Kosten. Nur wenn das nichts findet UND ein Anthropic-Schlüssel hinterlegt ist,
fragt der Upload zusätzlich das Modell. So funktioniert der Ablauf überall
vollständig, auch auf einer Installation ohne Schlüssel.

**Zweitens: Ein Upload scheitert fast nie.** Ist die Datei lesbar, entsteht
ein Standort — auch wenn kein Feld erkannt wurde. Der Mailtext ist dann
gespeichert, die Hinweise sagen, was fehlt, und die Angaben lassen sich per
``PATCH`` nachtragen. Wer eine Mail hochgeladen hat, soll nicht mit leeren
Händen dastehen.

PHASE 1 = ZWEI ENTWÜRFE AUS EINEM AUFRUF
========================================
``POST /standorte/{id}/beauftragungen`` erzeugt für jeden Subplaner der Phase
einen Einzelabruf, legt ihn im Vertragsordner der Firma ab und gibt die
``.eml``-Dateien als ZIP zurück — bei Phase 1 also Kocks und RKA in einem
Zug. Ein Aufruf je Firma wäre eine Gelegenheit, die zweite zu vergessen.
"""

import io
import zipfile
from datetime import date, datetime
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
from app.models import (
    MCDONALDS_PHASEN,
    McdonaldsBeauftragung,
    McdonaldsStandort,
    McdonaldsSubplaner,
)
from app.schemas import (
    BeauftragungAnfrage,
    BeauftragungVorschau,
    McdonaldsBeauftragungResponse,
    McdonaldsFaehigkeiten,
    McdonaldsStandortManuell,
    McdonaldsStandortResponse,
    McdonaldsStandortUpdate,
    TextvarianteInfo,
    UnlocodeLadeErgebnis,
    UnlocodeTreffer,
)
from app.services import mcdonalds_beauftragung as brief
from app.services import mcdonalds_email_analyse as analyse
from app.services import mcdonalds_ordner as ordner_dienst
from app.services import mcdonalds_sls as sls
from app.services import mcdonalds_unlocode as unlocode
from app.services import mcdonalds_versand as versand

router = APIRouter(prefix="/mcdonalds", tags=["mcdonalds"])

#: Größere Dateien sind keine exportierte Mail mehr, sondern ein Versehen.
MAX_EML_MB = 25


# ─────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────────────────────


def _hole(db: Session, standort_id: int) -> McdonaldsStandort:
    standort = db.get(McdonaldsStandort, standort_id)
    if not standort:
        raise HTTPException(404, "Standort nicht gefunden")
    return standort


def _beauftragung_antwort(
    eintrag: McdonaldsBeauftragung,
) -> McdonaldsBeauftragungResponse:
    planer = eintrag.subplaner
    return McdonaldsBeauftragungResponse(
        id=eintrag.id,
        standort_id=eintrag.standort_id,
        subplaner_id=eintrag.subplaner_id,
        subplaner_name=planer.name if planer else "",
        subplaner_kuerzel=planer.kuerzel if planer else "",
        phase=eintrag.phase,
        betreff=eintrag.betreff or "",
        text=eintrag.text or "",
        beauftragung_am=eintrag.beauftragung_am,
        leistungsbeginn=eintrag.leistungsbeginn,
        projektplanung=eintrag.projektplanung,
        klaerung=eintrag.klaerung,
        abgabe=eintrag.abgabe,
        empfaenger=eintrag.empfaenger or [],
        eml_pfad=eintrag.eml_pfad,
        mail_versendet_am=eintrag.mail_versendet_am,
        mail_weg=eintrag.mail_weg or "",
        erstellt_am=eintrag.erstellt_am,
    )


def _antwort(
    standort: McdonaldsStandort,
    *,
    mit_text: bool = False,
    hinweise: list[str] | None = None,
) -> McdonaldsStandortResponse:
    """Ein Standort als Antwort. ``mit_text`` nur in der Detailansicht."""
    return McdonaldsStandortResponse(
        id=standort.id,
        quelle=standort.quelle,
        eml_dateiname=standort.eml_dateiname or "",
        sls_erkannt=bool(standort.sls_erkannt),
        analysiert_am=standort.analysiert_am,
        phase=standort.phase,
        ort=standort.ort or "",
        plz=standort.plz or "",
        strasse=standort.strasse or "",
        standort_name=standort.standort_name or "",
        abgabetermin=standort.abgabetermin,
        leistungsbeginn=standort.leistungsbeginn,
        sls_vorgang=standort.sls_vorgang or "",
        anhaenge=standort.anhaenge or [],
        unlocode=standort.unlocode,
        ordner_name=standort.ordner_name or "",
        ordner_status=standort.ordner_status,
        ordner_pfad=standort.ordner_pfad,
        ordner_pfad_sharepoint=standort.ordner_pfad_sharepoint,
        ordner_anzahl=standort.ordner_anzahl or 0,
        fehlermeldung=standort.fehlermeldung,
        erstellt_am=standort.erstellt_am,
        aktualisiert_am=standort.aktualisiert_am,
        roh_text=(standort.roh_text or "") if mit_text else "",
        beauftragungen=[
            _beauftragung_antwort(b)
            for b in sorted(standort.beauftragungen, key=lambda b: b.id)
        ],
        hinweise=hinweise or [],
    )


def _anhang_kopfzeile(name: str, ersatz: str) -> str:
    """Content-Disposition mit Umlauten — wie in ``routers.baufotos``."""
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
        ordner_laufwerk=bool(
            (settings.mcdonalds_basis_standorte or "").strip()
        ),
        musterordner=ordner_dienst.musterordner() is not None,
        unterordner=len(ordner_dienst.UNTERORDNER),
        ordner_sharepoint=bool(
            (settings.mcdonalds_basis_sharepoint or "").strip()
        ),
        unlocode_eintraege=unlocode.anzahl_eintraege(db),
        textvarianten=[
            TextvarianteInfo(kennung=k, beschriftung=b)
            for k, b in brief.TEXTVARIANTEN_AUSWAHL
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Standorte
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/standorte", response_model=list[McdonaldsStandortResponse])
def list_standorte(db: Session = Depends(get_db)):
    standorte = (
        db.query(McdonaldsStandort)
        .order_by(McdonaldsStandort.erstellt_am.desc())
        .all()
    )
    return [_antwort(s) for s in standorte]


@router.get("/standorte/{standort_id}", response_model=McdonaldsStandortResponse)
def get_standort(standort_id: int, db: Session = Depends(get_db)):
    return _antwort(_hole(db, standort_id), mit_text=True)


@router.post("/standorte", response_model=McdonaldsStandortResponse,
             status_code=201)
async def upload_eml(
    background_tasks: BackgroundTasks,
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Nimmt die als ``.eml`` exportierte SLS-Anfrage an.

    Ablauf: zerlegen, nach Regeln lesen, notfalls das Modell fragen, Standort
    anlegen, Ordneranlage als Hintergrundaufgabe anstoßen.
    """
    rohdaten = await datei.read()
    if len(rohdaten) > MAX_EML_MB * 1024 * 1024:
        raise HTTPException(
            413,
            f"Die Datei ist {len(rohdaten) / 1024 / 1024:.1f} MB groß; "
            f"höchstens {MAX_EML_MB} MB sind vorgesehen. Bitte die Mail ohne "
            "ihre Anhänge exportieren.",
        )

    name = datei.filename or "sls-anfrage.eml"
    try:
        inhalt = analyse.lies_eml(rohdaten, name)
    except analyse.AnalyseFehler as fehler:
        # Eine unlesbare Datei ist etwas anderes als eine nicht ausgewertete:
        # Hier gibt es nichts zu speichern, was später zu retten wäre.
        raise HTTPException(400, str(fehler)) from fehler

    # ── Hauptweg: die Regeln ──
    angaben = sls.lies_sls(inhalt)
    hinweise = list(angaben.hinweise)
    analysiert_am = None

    # ── Notausgang: das Modell, nur wenn die Regeln nichts fanden ──
    if not angaben.erkannt and analyse.ist_verfuegbar():
        try:
            vom_modell = await analyse.analysiere(inhalt)
            angaben.ort = angaben.ort or vom_modell.ort
            angaben.plz = angaben.plz or vom_modell.plz
            angaben.strasse = angaben.strasse or vom_modell.strasse
            angaben.phase = angaben.phase or vom_modell.phase
            analysiert_am = datetime.now()
            hinweise += vom_modell.hinweise
            hinweise.append(
                "Die Angaben stammen aus der KI-Auswertung des Freitexts, "
                "nicht aus dem festen SLS-Format. Bitte gegenlesen."
            )
        except analyse.AnalyseFehler as fehler:
            hinweise.append(f"{fehler}")

    standort = McdonaldsStandort(
        quelle="eml",
        eml_dateiname=name,
        roh_text=inhalt.text or "",
        anhaenge=inhalt.anhaenge,
        sls_erkannt=angaben.erkannt,
        analysiert_am=analysiert_am,
        phase=angaben.phase,
        ort=angaben.ort,
        plz=angaben.plz,
        strasse=angaben.strasse,
        standort_name=angaben.ort,
        abgabetermin=angaben.abgabetermin,
        leistungsbeginn=angaben.leistungsbeginn,
        sls_vorgang=angaben.sls_vorgang,
        ordner_status="ausstehend",
    )
    db.add(standort)
    db.commit()
    db.refresh(standort)

    background_tasks.add_task(
        ordner_dienst.erzeuge_projektordner_im_hintergrund, standort.id
    )
    return _antwort(standort, mit_text=True, hinweise=hinweise)


@router.post("/standorte/manuell", response_model=McdonaldsStandortResponse,
             status_code=201)
def standort_manuell(
    daten: McdonaldsStandortManuell,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Standort von Hand erfassen — dieselbe Weiterverarbeitung ohne Mail."""
    standort = McdonaldsStandort(
        quelle="manuell",
        roh_text=daten.notiz.strip(),
        anhaenge=[],
        sls_erkannt=False,
        phase=daten.phase,
        ort=daten.ort.strip(),
        plz=daten.plz.strip(),
        strasse=daten.strasse.strip(),
        standort_name=daten.standort_name.strip() or daten.ort.strip(),
        abgabetermin=daten.abgabetermin,
        leistungsbeginn=daten.leistungsbeginn,
        sls_vorgang=daten.sls_vorgang.strip(),
        ordner_status="ausstehend",
    )
    db.add(standort)
    db.commit()
    db.refresh(standort)

    background_tasks.add_task(
        ordner_dienst.erzeuge_projektordner_im_hintergrund, standort.id
    )
    return _antwort(standort, mit_text=True)


@router.patch("/standorte/{standort_id}",
              response_model=McdonaldsStandortResponse)
def update_standort(
    standort_id: int,
    daten: McdonaldsStandortUpdate,
    db: Session = Depends(get_db),
):
    """Korrigiert die Angaben — siehe Schema, warum es das gibt."""
    standort = _hole(db, standort_id)
    werte = daten.model_dump(exclude_unset=True)

    for feld in ("ort", "plz", "strasse", "standort_name", "sls_vorgang"):
        if werte.get(feld) is not None:
            setattr(standort, feld, werte[feld].strip())
    for feld in ("phase", "abgabetermin", "leistungsbeginn"):
        if feld in werte:
            setattr(standort, feld, werte[feld])
    if werte.get("unlocode") is not None:
        standort.unlocode = werte["unlocode"].strip().upper()

    db.commit()
    db.refresh(standort)
    return _antwort(standort, mit_text=True)


@router.post("/standorte/{standort_id}/ordner",
             response_model=McdonaldsStandortResponse)
def ordner_anlegen(standort_id: int, db: Session = Depends(get_db)):
    """Stößt die Ordneranlage erneut an — nach einer Korrektur.

    Bewusst *nicht* im Hintergrund: Wer diesen Knopf drückt, hat gerade etwas
    geändert und will wissen, ob es jetzt geht.
    """
    standort = _hole(db, standort_id)
    ergebnis = ordner_dienst.erzeuge_projektordner(standort, db)
    db.commit()
    db.refresh(standort)
    return _antwort(
        standort, mit_text=True,
        hinweise=[ergebnis.meldung] if ergebnis.meldung else [],
    )


@router.delete("/standorte/{standort_id}", status_code=204)
def delete_standort(standort_id: int, db: Session = Depends(get_db)):
    """Löscht den Standort samt seiner Beauftragungen.

    Der angelegte Ordner im Projektlaufwerk bleibt stehen. Das ist Absicht:
    Dort liegen inzwischen vielleicht Unterlagen, und ein Löschknopf in einer
    Weboberfläche darf kein Projektlaufwerk leerräumen.
    """
    db.delete(_hole(db, standort_id))
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# UN/LOCODE-Referenztabelle
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/unlocode-tabelle", response_model=UnlocodeLadeErgebnis)
async def upload_unlocode_tabelle(
    datei: UploadFile = File(...), db: Session = Depends(get_db)
):
    """Nimmt die Anlage 5.1 (Excel) an und ersetzt die Nachschlagetabelle."""
    rohdaten = await datei.read()
    if not rohdaten:
        raise HTTPException(400, "Die hochgeladene Datei ist leer.")

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
    """Schlägt einen Ort nach — für das Feld „UN/LOCODE“ in der Oberfläche."""
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
        code=treffer.code, ort=treffer.ort, bundesland=treffer.bundesland,
        art=treffer.art, guete=treffer.guete,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Einzelabrufe an die Subplaner
# ─────────────────────────────────────────────────────────────────────────────


def _subplaner_der_phase(
    db: Session, phase: int, nur: list[int] | None = None
) -> list[McdonaldsSubplaner]:
    frage = db.query(McdonaldsSubplaner).filter(
        McdonaldsSubplaner.phase == phase
    )
    if nur:
        frage = frage.filter(McdonaldsSubplaner.id.in_(nur))
    return frage.order_by(
        McdonaldsSubplaner.sortierung, McdonaldsSubplaner.id
    ).all()


def _termine(
    standort: McdonaldsStandort, angaben
) -> tuple[date, date | None, date | None, date | None, date | None]:
    """Die Termine des Schreibens — Vorgabe aus dem Standort, sonst die Regel.

    Reihenfolge der Vorrangigkeit: Was im Formular steht, gilt. Sonst was am
    Standort steht. Sonst die Regel (siehe ``mcdonalds_beauftragung``).
    """
    beauftragung = angaben.beauftragung_am or date.today()
    leistungsbeginn = angaben.leistungsbeginn or standort.leistungsbeginn
    abgabe = angaben.abgabe or standort.abgabetermin
    # "Erstellung der Projektplanung" fällt im Musterschreiben mit dem
    # Abgabetermin zusammen.
    projektplanung = angaben.projektplanung or abgabe
    klaerung = angaben.klaerung or brief.klaerungstermin(beauftragung)
    return beauftragung, leistungsbeginn, projektplanung, klaerung, abgabe


def _vorschau(
    standort: McdonaldsStandort, planer: McdonaldsSubplaner, angaben
) -> BeauftragungVorschau:
    beauftragung, beginn, planung, klaerung, abgabe = _termine(standort, angaben)
    empfaenger = [str(a) for a in (planer.emails or []) if str(a).strip()]

    hindernis = ""
    if not empfaenger:
        hindernis = (
            f"Für „{planer.name}“ ist keine E-Mail-Adresse hinterlegt. Sie "
            "steht in den Stammdaten unter Subplaner."
        )
    elif not standort.ort:
        hindernis = "Zum Standort ist kein Ort hinterlegt."

    return BeauftragungVorschau(
        subplaner_id=planer.id,
        subplaner_name=planer.name,
        subplaner_kuerzel=planer.kuerzel or "",
        empfaenger=empfaenger,
        betreff=brief.betreff(
            beauftragung=beauftragung,
            unlocode=standort.unlocode or "",
            phase=angaben.phase,
            kuerzel=planer.kuerzel or planer.name,
        ),
        text=brief.aus_daten(
            variante=planer.textvariante,
            anrede=planer.anrede,
            firma=planer.name,
            phase=angaben.phase,
            angebot_datum=planer.angebot_datum,
            projekt=standort.standort_name or standort.ort,
            leistungsbeginn=beginn,
            projektplanung=planung,
            klaerung=klaerung,
            abgabe=abgabe,
        ),
        ablage=brief.ablagepfad(planer.ordner),
        bereit=not hindernis,
        hindernis=hindernis,
    )


@router.post("/standorte/{standort_id}/beauftragungen/vorschau",
             response_model=list[BeauftragungVorschau])
def beauftragungen_vorschau(
    standort_id: int,
    anfrage: BeauftragungAnfrage,
    db: Session = Depends(get_db),
):
    """Zeigt für jeden Subplaner der Phase, was verschickt würde.

    Der Schritt vor dem Erzeugen: Betreff, Termine und Wortlaut lesen, bevor
    zwei Vertragsschreiben entstehen.
    """
    standort = _hole(db, standort_id)
    planer = _subplaner_der_phase(db, anfrage.phase, anfrage.subplaner_ids)
    if not planer:
        raise HTTPException(
            400,
            f"Für Phase {anfrage.phase} sind keine Subplaner hinterlegt. Sie "
            "stehen in den Stammdaten unter Subplaner.",
        )
    return [_vorschau(standort, p, anfrage) for p in planer]


@router.post("/standorte/{standort_id}/beauftragungen")
def beauftragungen_erzeugen(
    standort_id: int,
    anfrage: BeauftragungAnfrage,
    db: Session = Depends(get_db),
):
    """Erzeugt die Einzelabrufe, legt sie ab und gibt die Entwürfe zurück.

    Bei einem einzigen Subplaner kommt die ``.eml`` direkt zurück, bei
    mehreren ein ZIP mit allen — in Phase 1 also eine Datei mit den Entwürfen
    für Kocks und RKA. Ein Browser kann nicht zwei Dateien aus einer Antwort
    speichern, und zwei Aufrufe wären zwei Gelegenheiten, den zweiten zu
    vergessen.
    """
    standort = _hole(db, standort_id)
    planer = _subplaner_der_phase(db, anfrage.phase, anfrage.subplaner_ids)
    if not planer:
        raise HTTPException(
            400,
            f"Für Phase {anfrage.phase} sind keine Subplaner hinterlegt.",
        )

    vorschauen = [_vorschau(standort, p, anfrage) for p in planer]
    blockiert = [v for v in vorschauen if not v.bereit]
    if blockiert:
        # Alles oder nichts: Ein halb beauftragtes Projekt (Kocks ja, RKA
        # nein) ist schlimmer als eines, bei dem noch nichts passiert ist —
        # den fehlenden Abruf merkt sonst niemand.
        raise HTTPException(
            400,
            " ".join(v.hindernis for v in blockiert),
        )

    beauftragung_am, beginn, planung, klaerung, abgabe = _termine(
        standort, anfrage
    )
    dateien: list[tuple[str, bytes]] = []
    meldungen: list[str] = []

    for planer_eintrag, vorschau in zip(planer, vorschauen):
        nachricht = versand.baue_nachricht(
            empfaenger=vorschau.empfaenger,
            kopie=[],
            betreff=vorschau.betreff,
            text=vorschau.text,
            als_entwurf=True,
        )
        rohdaten = nachricht.as_bytes()
        dateiname = brief.dateiname(vorschau.betreff)

        eintrag = McdonaldsBeauftragung(
            standort_id=standort.id,
            subplaner_id=planer_eintrag.id,
            phase=anfrage.phase,
            betreff=vorschau.betreff,
            text=vorschau.text,
            beauftragung_am=beauftragung_am,
            leistungsbeginn=beginn,
            projektplanung=planung,
            klaerung=klaerung,
            abgabe=abgabe,
        )
        db.add(eintrag)
        db.flush()          # für die id, die in der Antwort steht

        pfad, meldung = ordner_dienst.lege_datei_ab(
            standort, brief.ablagepfad(planer_eintrag.ordner), dateiname,
            rohdaten,
        )
        eintrag.eml_pfad = pfad
        if meldung and meldung not in meldungen:
            meldungen.append(meldung)

        versand.notiere_versand(eintrag, vorschau.empfaenger, "entwurf")
        dateien.append((dateiname, rohdaten))

    db.commit()

    if len(dateien) == 1:
        name, rohdaten = dateien[0]
        return Response(
            content=rohdaten,
            media_type="message/rfc822",
            headers={
                "Content-Disposition": _anhang_kopfzeile(name, "beauftragung.eml"),
                "X-Ablage-Hinweis": "1" if meldungen else "0",
            },
        )

    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as archiv:
        for name, rohdaten in dateien:
            archiv.writestr(name, rohdaten)

    zipname = (
        f"{standort.ordner_name or standort.ort}_"
        f"Beauftragungen Phase {anfrage.phase}.zip"
    )
    return Response(
        content=puffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": _anhang_kopfzeile(zipname, "beauftragungen.zip"),
            "X-Ablage-Hinweis": "1" if meldungen else "0",
        },
    )


@router.get("/beauftragungen/{beauftragung_id}/entwurf")
def entwurf_erneut(beauftragung_id: int, db: Session = Depends(get_db)):
    """Liefert den Entwurf eines schon erzeugten Einzelabrufs erneut.

    Aus dem gespeicherten Wortlaut, nicht neu gerechnet: Was herausgegangen
    ist, bleibt, wie es war (siehe models.McdonaldsBeauftragung).
    """
    eintrag = db.get(McdonaldsBeauftragung, beauftragung_id)
    if not eintrag:
        raise HTTPException(404, "Beauftragung nicht gefunden")

    nachricht = versand.baue_nachricht(
        empfaenger=eintrag.empfaenger or [],
        kopie=[],
        betreff=eintrag.betreff,
        text=eintrag.text,
        als_entwurf=True,
    )
    name = brief.dateiname(eintrag.betreff)
    return Response(
        content=nachricht.as_bytes(),
        media_type="message/rfc822",
        headers={"Content-Disposition": _anhang_kopfzeile(name, "beauftragung.eml")},
    )


@router.delete("/beauftragungen/{beauftragung_id}", status_code=204)
def delete_beauftragung(beauftragung_id: int, db: Session = Depends(get_db)):
    """Entfernt den Eintrag. Die abgelegte ``.eml`` bleibt im Projektordner."""
    eintrag = db.get(McdonaldsBeauftragung, beauftragung_id)
    if not eintrag:
        raise HTTPException(404, "Beauftragung nicht gefunden")
    db.delete(eintrag)
    db.commit()


@router.get("/phasen")
def phasen():
    """Die Phasen, für die es Stammdaten und Beauftragungen gibt."""
    return {"phasen": list(MCDONALDS_PHASEN)}
