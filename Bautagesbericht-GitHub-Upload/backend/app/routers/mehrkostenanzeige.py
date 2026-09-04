"""Anzeigen der Baufirmen beantworten: auslesen, prüfen, Schreiben, Outlook.

ACHT ENDPUNKTE ENTLANG DES ABLAUFS IM BÜRO
==========================================
    POST /anzeigen/auslesen        Dateien hoch, Angaben zurück
    GET  /anzeigen/vorbelegung     Was das Formular anbieten soll
    GET  /anzeigen/bausteine       Die Standardsätze des Büros
    POST /anzeigen/glaetten        Stichworte in Briefform bringen
    POST /anzeigen/formulieren     Stichpunkte -> Absatztext fürs Infofeld
    POST /anzeigen/vorschau        Was entstehen würde, ohne es zu bauen
    POST /anzeigen/dokument        Das Schreiben als .docx (oder .pdf)
    POST /anzeigen/mail/entwurf    Fertige Outlook-Mail mit Schreiben im Anhang

Der Vorgang wird **nicht** gespeichert. Das ist eine Entscheidung, keine
Auslassung: Das Ergebnis ist eine Datei im Projektordner und eine Mail im
Postausgang, und beides ist das Archiv des Büros. Eine zweite Ablage in der
App wäre eine zweite Wahrheit, die niemand pflegt.

„Anzeigen“ heißt hier ausdrücklich nicht nur Mehrkostenanzeige. Ausgelesen und
beantwortet werden auch Behinderungsanzeigen, Behinderungs- und
Mehrkostenanzeigen, Bedenkenanmeldungen, Nachtragsangebote,
Stundenlohn- und Störungsanzeigen; welche Art es ist, erkennt
``mehrkostenanzeige_lesen`` am Text und am Kürzel und trägt sie in Betreff und
Mailbetreff (siehe ``ARTEN`` dort).
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Bearbeiter, Gewerk, Projekt
from app.schemas import (
    AnschriftSchema,
    AnzeigeAbsatzVorschau,
    AnzeigeAntwortAnfrage,
    AnzeigeAntwortVorschau,
    AnzeigeAuslesenErgebnis,
    AnzeigeBausteinGruppeSchema,
    AnzeigeBausteinSchema,
    AnzeigeBausteineErgebnis,
    AnzeigeEmpfaengerSchema,
    AnzeigeFormulierenAnfrage,
    AnzeigeFormulierenErgebnis,
    AnzeigeGlaettenAnfrage,
    AnzeigeGlaettenErgebnis,
    AnzeigeMailAnfrage,
    AnzeigeSachbearbeiterSchema,
    GelesenerPunktSchema,
    GelesenesSchreibenSchema,
)
from app.services import anzeige_bausteine as bausteine
from app.services import anzeige_formulierung as formulierung
from app.services import mehrkostenanzeige_generation as erzeugung
from app.services import mehrkostenanzeige_lesen as leser
from app.services import word_pdf

router = APIRouter(prefix="/anzeigen", tags=["anzeigen"])

#: Endungen, die das Auslesen annimmt.
ERLAUBTE_ENDUNGEN = (".pdf", ".docx", ".docm", ".dotx", ".txt", ".text", ".md")

WORD_TYP = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


# ─────────────────────────────────────────────────────────────────────────────
# Hilfen
# ─────────────────────────────────────────────────────────────────────────────


def _anhang_kopfzeile(name: str, ersatz: str) -> str:
    """Content-Disposition mit Umlauten (RFC 5987) — Projektnamen haben welche."""
    schlicht = name.encode("ascii", "ignore").decode() or ersatz
    return f'attachment; filename="{schlicht}"; filename*=UTF-8\'\'{quote(name)}'


def _in_schreiben(anfrage: AnzeigeAntwortAnfrage) -> erzeugung.Schreiben:
    """Anfrage der Oberfläche in die Datenklasse des Erzeugers."""
    return erzeugung.Schreiben(
        empfaenger=erzeugung.Empfaenger(
            firma=anfrage.empfaenger.firma,
            anrede=anfrage.empfaenger.anrede,
            ansprechpartner=anfrage.empfaenger.ansprechpartner,
            strasse=anfrage.empfaenger.strasse,
            plz=anfrage.empfaenger.plz,
            ort=anfrage.empfaenger.ort,
            email=str(anfrage.empfaenger.email or ""),
        ),
        sachbearbeiter=erzeugung.Sachbearbeiter(
            name=anfrage.sachbearbeiter.name,
            funktion=anfrage.sachbearbeiter.funktion,
            zeichen=anfrage.sachbearbeiter.zeichen,
            durchwahl=anfrage.sachbearbeiter.durchwahl,
            email=str(anfrage.sachbearbeiter.email or ""),
        ),
        anzeige=erzeugung.Anzeige(
            art=anfrage.anzeige.art,
            nummer=anfrage.anzeige.nummer,
            kennung=anfrage.anzeige.kennung,
            datum=anfrage.anzeige.datum,
            kurzbezeichnung=anfrage.anzeige.kurzbezeichnung,
            bauzeit=anfrage.anzeige.bauzeit,
        ),
        projektzeile=anfrage.projektzeile,
        vergabeeinheit=anfrage.vergabeeinheit,
        betreff=anfrage.betreff,
        briefdatum=anfrage.briefdatum or date.today(),
        stellungnahme=anfrage.stellungnahme,
        einleitung=anfrage.einleitung,
        haltung=anfrage.haltung,
        schlusssatz=anfrage.schlusssatz,
        bauzeit_ablehnen=anfrage.bauzeit_ablehnen,
        anlagen=anfrage.anlagen,
        verteiler=anfrage.verteiler,
        dateikuerzel=anfrage.dateikuerzel,
    )


def _erzeuge(daten: erzeugung.Schreiben) -> bytes:
    try:
        return erzeugung.erzeuge(daten)
    except erzeugung.MehrkostenanzeigeFehler as fehler:
        # 422: Die Anfrage ist formal in Ordnung, aber inhaltlich unvollständig.
        raise HTTPException(422, str(fehler)) from fehler


def _in_schema(gelesen: leser.GelesenesSchreiben) -> GelesenesSchreibenSchema:
    return GelesenesSchreibenSchema(
        quelle=gelesen.quelle,
        seiten=gelesen.seiten,
        art=gelesen.art,
        nummer=gelesen.nummer,
        kennung=gelesen.kennung,
        datum=gelesen.datum,
        betreff=gelesen.betreff,
        kurzbezeichnung=gelesen.kurzbezeichnung,
        absender=AnschriftSchema(**vars(gelesen.absender)),
        absender_email=gelesen.absender_email,
        absender_telefon=gelesen.absender_telefon,
        ansprechpartner=gelesen.ansprechpartner,
        ansprechpartner_email=gelesen.ansprechpartner_email,
        empfaenger=AnschriftSchema(**vars(gelesen.empfaenger)),
        projektnummer=gelesen.projektnummer,
        leistungsort=gelesen.leistungsort,
        gewerk=gelesen.gewerk,
        rechtsgrundlage=gelesen.rechtsgrundlage,
        punkte=[GelesenerPunktSchema(**vars(p)) for p in gelesen.punkte],
        lv_positionen=gelesen.lv_positionen,
        bauzeit=gelesen.bauzeit,
        forderung=gelesen.forderung,
        unterzeichner=gelesen.unterzeichner,
        unterzeichner_funktion=gelesen.unterzeichner_funktion,
        volltext=gelesen.volltext,
        hinweise=gelesen.hinweise,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Auslesen
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/auslesen", response_model=AnzeigeAuslesenErgebnis)
async def auslesen(dateien: list[UploadFile] = File(...)):
    """Hochgeladene Anzeigen auslesen — eine Antwort je Datei.

    Mehrere Dateien sind ausdrücklich erlaubt: Oft kommen zwei oder drei
    Anzeigen derselben Firma an einem Tag, und dann will man sie hintereinander
    beantworten, ohne jedes Mal neu hochzuladen.

    Eine unlesbare Datei lässt die anderen nicht scheitern. Sie steht mit ihrem
    Grund in ``fehlgeschlagen`` — wer drei Dateien hochlädt und eine ist ein
    Scan ohne Textebene, soll die anderen zwei trotzdem bearbeiten können.
    """
    if not dateien:
        raise HTTPException(400, "Es wurde keine Datei hochgeladen.")
    if len(dateien) > settings.max_files_per_submission:
        raise HTTPException(
            400,
            f"Höchstens {settings.max_files_per_submission} Dateien auf "
            f"einmal.",
        )

    grenze = settings.max_file_size_mb * 1024 * 1024
    gelesen: list[GelesenesSchreibenSchema] = []
    fehler: list[str] = []

    for datei in dateien:
        name = datei.filename or "unbenannt"
        endung = Path(name).suffix.lower()
        if endung not in ERLAUBTE_ENDUNGEN:
            fehler.append(
                f"{name}: „{endung or 'ohne Endung'}“ kann nicht gelesen "
                f"werden. Möglich sind PDF, Word (.docx) und Textdateien."
            )
            continue

        inhalt = await datei.read()
        if not inhalt:
            fehler.append(f"{name}: Die Datei ist leer.")
            continue
        if len(inhalt) > grenze:
            fehler.append(
                f"{name}: {len(inhalt) / 1024 / 1024:.1f} MB sind zu groß "
                f"(erlaubt sind {settings.max_file_size_mb} MB)."
            )
            continue

        # Auf Platte, weil pdfplumber und python-docx einen Pfad brauchen. Der
        # Ordner verschwindet mit dem Block — hochgeladene Fremdschreiben
        # sollen nicht in der Ablage der App liegen bleiben.
        with tempfile.TemporaryDirectory(prefix="hpp-anzeige-") as ordner:
            pfad = Path(ordner) / f"schreiben{endung}"
            pfad.write_bytes(inhalt)
            try:
                gelesen.append(_in_schema(leser.lies(pfad, quelle=name)))
            except leser.Lesefehler as lesefehler:
                fehler.append(str(lesefehler))

    if not gelesen and fehler:
        raise HTTPException(422, " ".join(fehler))
    return AnzeigeAuslesenErgebnis(schreiben=gelesen, fehlgeschlagen=fehler)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Vorbelegung aus den Stammdaten
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/vorbelegung")
def vorbelegung(
    projekt_id: int | None = None,
    gewerk_id: int | None = None,
    bearbeiter_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Was aus den Stammdaten kommen kann — Projektzeile, Firma, Bearbeiter.

    Alle drei Angaben sind freiwillig. Eine Anzeige lässt sich vollständig aus
    dem hochgeladenen Schreiben beantworten; die Stammdaten ersparen nur das
    Abtippen. Deshalb ist auch ``projekt_id`` nicht Pflicht — sonst könnte man
    auf eine Anzeige zu einem Bauvorhaben, das in der App noch nicht angelegt
    ist, gar nicht antworten.
    """
    antwort: dict = {
        "projektzeile": "",
        "vergabeeinheit": "",
        "dateikuerzel": "",
        "briefdatum": date.today(),
        "empfaenger": None,
        "sachbearbeiter": None,
        "bearbeiter": [],
        "gewerke": [],
        "haltungen": erzeugung.HALTUNGEN,
        "arten": [name for _, name in leser.ARTEN],
        "word_vorhanden": word_pdf.word_vorhanden(),
        "formulieren_verfuegbar": formulierung.ist_verfuegbar(),
        "formulieren_hinweis": (
            "" if formulierung.ist_verfuegbar() else formulierung.warum_nicht()
        ),
    }

    if projekt_id is not None:
        projekt = db.get(Projekt, projekt_id)
        if projekt is None:
            raise HTTPException(404, "Projekt nicht gefunden")
        nummer = (projekt.projekt_nummer or "").strip()
        antwort["projektzeile"] = f"{nummer}_{projekt.name}" if nummer \
            else projekt.name
        antwort["dateikuerzel"] = nummer or projekt.name
        antwort["gewerke"] = [
            {
                "id": g.id,
                "firma_name": g.firma_name,
                "vergabeeinheit_code": g.vergabeeinheit_code,
                "vergabeeinheit_bezeichnung": g.vergabeeinheit_bezeichnung,
            }
            for g in projekt.gewerke
        ]

    if gewerk_id is not None:
        gewerk = db.get(Gewerk, gewerk_id)
        if gewerk is None:
            raise HTTPException(404, "Firma / Gewerk nicht gefunden")
        if projekt_id is not None and gewerk.projekt_id != projekt_id:
            raise HTTPException(400, "Die Firma gehört zu einem anderen Projekt")
        antwort["vergabeeinheit"] = " ".join(
            teil for teil in (
                (gewerk.vergabeeinheit_code or "").strip(),
                (gewerk.vergabeeinheit_bezeichnung or "").strip(),
            ) if teil
        )
        antwort["empfaenger"] = AnzeigeEmpfaengerSchema(
            firma=gewerk.firma_name,
            ansprechpartner=(gewerk.ansprechpartner or "").strip(),
            strasse=(gewerk.strasse or "").strip(),
            plz=(gewerk.plz or "").strip(),
            ort=(gewerk.ort or "").strip(),
            email=(gewerk.email or "").strip() or None,
        )

    antwort["bearbeiter"] = [
        {
            "id": b.id, "name": b.name, "kuerzel": b.kuerzel,
            "durchwahl": b.durchwahl, "email": b.email or "",
        }
        for b in db.query(Bearbeiter).order_by(Bearbeiter.name).all()
    ]

    if bearbeiter_id is not None:
        bearbeiter = db.get(Bearbeiter, bearbeiter_id)
        if bearbeiter is None:
            raise HTTPException(404, "Bearbeiter nicht gefunden")
        antwort["sachbearbeiter"] = AnzeigeSachbearbeiterSchema(
            name=bearbeiter.name,
            zeichen=(bearbeiter.kuerzel or "").strip(),
            durchwahl=(bearbeiter.durchwahl or "").strip(),
            email=(bearbeiter.email or "").strip() or None,
        )
    return antwort


# ─────────────────────────────────────────────────────────────────────────────
# 2b. Die Stellungnahme schreiben — ohne Schlüssel
#
# Zwei Endpunkte, die kein Sprachmodell brauchen und deshalb überall
# funktionieren: der Katalog der Standardsätze und das Glätten von Stichworten.
# Siehe ``app.services.anzeige_bausteine``.
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/bausteine", response_model=AnzeigeBausteineErgebnis)
def bausteine_liste(haltung: str = ""):
    """Die Standardsätze des Büros, passend zur gewählten Haltung.

    Gefiltert und nicht nur sortiert: Wer eine Anzeige ablehnt, soll "Dies ist
    eine Zusatzleistung" nicht angeboten bekommen — ein Fehlklick dorthin
    schriebe das Gegenteil des Gemeinten in ein rechtserhebliches Schreiben.
    """
    if haltung and haltung not in erzeugung.HALTUNGEN:
        raise HTTPException(
            400,
            f"„{haltung}“ ist keine bekannte Haltung. Möglich sind: "
            + ", ".join(erzeugung.HALTUNGEN),
        )
    return AnzeigeBausteineErgebnis(
        gruppen=[
            AnzeigeBausteinGruppeSchema(
                kennung=gruppe.kennung,
                titel=gruppe.titel,
                bausteine=[
                    AnzeigeBausteinSchema(
                        kennung=b.kennung, titel=b.titel, text=b.text,
                        zitat=b.zitat,
                    )
                    for b in gruppe.bausteine
                ],
            )
            for gruppe in bausteine.fuer_haltung(haltung)
        ],
        luecke=bausteine.LUECKE,
    )


@router.post("/glaetten", response_model=AnzeigeGlaettenErgebnis)
def glaetten(anfrage: AnzeigeGlaettenAnfrage):
    """Stichworte in Briefform bringen — Form, nicht Inhalt.

    Aus "- pos 3.11 ep abgegolten" wird "1) Pos. 3.11 EP abgegolten." Es
    entsteht kein Satz, wo keiner war; dafür sind die Bausteine da. Was das
    Glätten nicht konnte, steht in ``hinweise`` — etwa die Großschreibung der
    Substantive, für die es ein Wörterbuch bräuchte.
    """
    if not anfrage.text.strip():
        raise HTTPException(422, "Es steht kein Text im Infofeld.")
    text, hinweise = bausteine.glaette(anfrage.text)
    return AnzeigeGlaettenErgebnis(text=text, hinweise=hinweise)


# ─────────────────────────────────────────────────────────────────────────────
# 2c. Stichpunkte ausformulieren — mit Schlüssel
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/formulieren", response_model=AnzeigeFormulierenErgebnis)
async def formulieren(anfrage: AnzeigeFormulierenAnfrage):
    """Aus Stichpunkten den Absatztext der Stellungnahme machen.

    Der Text landet **im Infofeld** der Oberfläche, nicht im Dokument. Damit
    bleibt der Weg ins Schreiben derselbe wie ohne diesen Endpunkt: Ein Mensch
    liest den Vorschlag, ändert ihn und erzeugt danach das Dokument. Es gibt
    bewusst keinen Weg, auf dem formulierter Text ungelesen in ein
    rechtserhebliches Schreiben gerät.

    Ohne Anthropic-Schlüssel antwortet der Endpunkt mit 422 und dem Satz, der
    sagt, wo der Schlüssel hingehört — das Infofeld bleibt von Hand nutzbar.
    """
    auftrag = formulierung.Auftrag(
        stichpunkte=anfrage.stichpunkte,
        art=anfrage.anzeige.art,
        nummer=anfrage.anzeige.nummer,
        datum=anfrage.anzeige.datum.strftime("%d.%m.%Y")
        if anfrage.anzeige.datum else "",
        kurzbezeichnung=anfrage.anzeige.kurzbezeichnung,
        punkte=anfrage.punkte,
        lv_positionen=anfrage.lv_positionen,
        bauzeit=anfrage.anzeige.bauzeit,
        rechtsgrundlage=anfrage.rechtsgrundlage,
        anzeigetext=anfrage.anzeigetext,
        haltung=anfrage.haltung,
        projekt=anfrage.projektzeile,
        vergabeeinheit=anfrage.vergabeeinheit,
    )
    try:
        ergebnis = await formulierung.formuliere(auftrag)
    except formulierung.FormulierungFehler as fehler:
        raise HTTPException(422, str(fehler)) from fehler

    return AnzeigeFormulierenErgebnis(
        stellungnahme=ergebnis.stellungnahme,
        offene_fragen=ergebnis.offene_fragen,
        hinweise=ergebnis.hinweise,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Vorschau
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/vorschau", response_model=AnzeigeAntwortVorschau)
def vorschau(anfrage: AnzeigeAntwortAnfrage):
    """Was im Schreiben und in der Mail stehen würde — ohne eine Datei zu bauen.

    Der Zwischenschritt ist der Kern der Kontrolle: Ein solches Schreiben wehrt
    Vergütungsansprüche ab, da liest man vorher gegen. Angezeigt wird genau
    das, was später im Dokument steht — dieselben Funktionen, keine zweite
    Fassung des Textes.
    """
    daten = _in_schreiben(anfrage)
    # Dieselbe Reihenfolge wie in ``erzeugung.erzeuge``: erst die Angaben aus
    # dem Infofeld an ihren Platz, dann prüfen. Sonst zeigte die Vorschau
    # etwas anderes als das Dokument.
    uebernommen = erzeugung.vorbereiten(daten)
    try:
        erzeugung.pruefe(daten)
    except erzeugung.MehrkostenanzeigeFehler as fehler:
        raise HTTPException(422, str(fehler)) from fehler

    anlagen = [z for z in daten.anlagen.split("\n") if z.strip()]
    verteiler = [z for z in daten.verteiler.split("\n") if z.strip()]
    verteilerseite: list[str] = []
    if anlagen:
        verteilerseite += ["Anlage:" if len(anlagen) == 1 else "Anlagen:"]
        verteilerseite += [z.strip() for z in anlagen]
    if verteiler:
        if verteilerseite:
            verteilerseite.append("")
        verteilerseite += ["Verteiler:"] + [z.strip() for z in verteiler]

    bearbeiter = daten.sachbearbeiter
    datumszeile = [
        (daten.briefdatum or date.today()).strftime("%d.%m.%Y"),
        f"Ze: {bearbeiter.zeichen}" if bearbeiter.zeichen.strip() else "",
        f"T - {bearbeiter.durchwahl}" if bearbeiter.durchwahl.strip() else "",
        bearbeiter.email,
    ]

    hinweise: list[str] = []
    if uebernommen:
        # Was aus dem Infofeld an einen anderen Platz gewandert ist, muss
        # sichtbar sein. Sonst verschwindet eine Zeile und niemand weiß, ob
        # sie angekommen ist.
        hinweise.append(
            "Aus dem Infofeld übernommen — "
            + "; ".join(uebernommen)
            + ". Diese Zeilen stehen nicht mehr im Brieftext."
        )
    if not daten.empfaenger.email.strip():
        hinweise.append(
            "Ohne E-Mail-Adresse der Firma bleibt das Adressfeld ohne die "
            "Zeile „per E-Mail:“ und der Outlook-Entwurf ohne Empfänger."
        )

    return AnzeigeAntwortVorschau(
        dateiname=erzeugung.dateiname(daten),
        projektzeile=daten.projektzeile,
        vergabeeinheit=daten.vergabeeinheit,
        betreff=erzeugung.betreffzeile(daten),
        anrede=erzeugung.anredezeile(daten.empfaenger),
        adressblock=erzeugung.adressblock(daten),
        datumszeile=datumszeile,
        absaetze=[
            AnzeigeAbsatzVorschau(text=block.text, zitat=block.zitat)
            for block in erzeugung.koerper(daten)
        ],
        verteilerseite=verteilerseite,
        mail_betreff=erzeugung.mail_betreff(daten),
        mail_text=erzeugung.mail_text(daten),
        mail_an=daten.empfaenger.email,
        hinweise=hinweise,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Das Schreiben
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/dokument")
def dokument(
    anfrage: AnzeigeAntwortAnfrage,
    format: str = Query("docx", description="docx oder pdf"),
):
    """Das Antwortschreiben.

    Word ist die verbindliche Ausgabe — das Schreiben wird im Büro noch
    gelesen und unterschrieben. Das PDF gibt es zusätzlich, aber nur dort, wo
    Word installiert ist (siehe ``app.services.word_pdf``).
    """
    if format not in ("docx", "pdf"):
        raise HTTPException(400, "Erlaubt sind „docx“ und „pdf“.")

    daten = _in_schreiben(anfrage)
    inhalt = _erzeuge(daten)
    name = erzeugung.dateiname(daten)

    if format == "docx":
        return Response(
            content=inhalt,
            media_type=WORD_TYP,
            headers={"Content-Disposition": _anhang_kopfzeile(name, "anzeige.docx")},
        )

    try:
        pdf = word_pdf.nach_pdf(inhalt)
    except word_pdf.PdfNichtMoeglich as fehler:
        raise HTTPException(422, str(fehler)) from fehler
    pdfname = name[:-5] + ".pdf" if name.endswith(".docx") else name + ".pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": _anhang_kopfzeile(pdfname, "anzeige.pdf")},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Outlook-Entwurf
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/mail/entwurf")
def mail_entwurf(anfrage: AnzeigeMailAnfrage):
    """Fertige Mail als ``.eml`` — Outlook öffnet sie als Entwurf zum Senden.

    Empfänger, Betreff, Text und das Schreiben als Anhang sind drin; der Kopf
    ``X-Unsent: 1`` macht daraus in Outlook einen Entwurf mit Senden-Knopf und
    keine empfangene Nachricht. Der Absender bleibt leer, damit Outlook das
    Konto des Kollegen nimmt. Denselben Weg geht schon der Fotoversand — siehe
    ``app.services.fotoversand``.

    Verschickt wird hier nichts. Das letzte Wort hat der Mensch: erst das
    Schreiben gegenlesen, dann in Outlook auf Senden drücken.
    """
    from email.message import EmailMessage

    daten = _in_schreiben(anfrage.antwort)
    inhalt = _erzeuge(daten)
    name = erzeugung.dateiname(daten)

    empfaenger = [a.strip() for a in anfrage.an if a.strip()]
    if not empfaenger and daten.empfaenger.email.strip():
        empfaenger = [daten.empfaenger.email.strip()]
    if not empfaenger:
        raise HTTPException(
            422,
            "Für den Outlook-Entwurf fehlt die Empfängeradresse. Bitte im "
            "Feld „E-Mail der Firma“ eine Adresse eintragen.",
        )

    nachricht = EmailMessage()
    nachricht["To"] = ", ".join(empfaenger)
    kopie = [a.strip() for a in anfrage.kopie if a.strip()]
    if kopie:
        nachricht["Cc"] = ", ".join(kopie)
    nachricht["Subject"] = anfrage.betreff.strip() or erzeugung.mail_betreff(daten)
    # Zwei Fassungen desselben Textes: der Textteil als Rückfallebene, der
    # HTML-Teil in Arial 10. Ohne HTML nimmt Outlook die Schrift aus den
    # Einstellungen des Absenders — auf jedem Bürorechner eine andere.
    mailtext = anfrage.text.strip() or erzeugung.mail_text(daten).rstrip()
    nachricht.set_content(mailtext + "\n")
    nachricht.add_alternative(erzeugung.mail_html(mailtext), subtype="html")

    if anfrage.dokument_anhaengen:
        nachricht.add_attachment(
            inhalt,
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=name,
        )
    nachricht["X-Unsent"] = "1"

    emlname = (name[:-5] if name.endswith(".docx") else name) + ".eml"
    return Response(
        content=nachricht.as_bytes(),
        media_type="message/rfc822",
        headers={"Content-Disposition": _anhang_kopfzeile(emlname, "anzeige.eml")},
    )
