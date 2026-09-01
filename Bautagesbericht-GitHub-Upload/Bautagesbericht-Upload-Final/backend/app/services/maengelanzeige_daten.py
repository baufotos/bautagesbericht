"""Baut die Angaben einer Mängelanzeige aus den erfassten Mängeln.

WARUM DIESE BRÜCKE
==================
``maengelanzeige_generation`` kennt nur Datenklassen und weiß nichts von der
Datenbank — so bleibt es prüfbar und aus einem Skript benutzbar. Hier wird
übersetzt: Projekt, Gewerk und die ausgewählten Mängel werden zu Bereichen mit
Fotos und Bildunterschriften.

DIE ABBILDUNG IM EINZELNEN
==========================
    Bereich            ``hinweis_ort`` des Mangels, sonst „Raum {raumnummer}“,
                       sonst „Ohne Ortsangabe“. Genau dafür gibt es das Feld:
                       Im Referenzdokument heißen die Bereiche „Ostfassade“,
                       „Südwest Fassadenecke“ — also Orte, keine Gewerke.
    Bildunterschrift   ``bildunterschrift`` des Fotos, sonst
                       ``kurzbezeichnung`` des Mangels. Die Vorlage zeigt kurze
                       Handlungsanweisungen („Loch im WDVS fachgerecht
                       schließen“) — dafür ist die Kurzbezeichnung gedacht.
    Reihenfolge        Bereiche in der Reihenfolge ihres ersten Mangels, Fotos
                       nach ``reihenfolge`` — nicht alphabetisch. Wer die
                       Begehung abläuft, geht in einer Reihenfolge, und die
                       soll die Anlage behalten.

Mängel ohne Foto kommen nicht in die Anlage; sie werden als Hinweis
zurückgemeldet, damit niemand rät, warum ein Mangel fehlt.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Gewerk, Mangel, Projekt
from app.services import maengelanzeige_generation as erzeugung
from app.utils.file_storage import get_absolute_path

#: Vorgabe für die Frist, wenn keine gesetzt wurde: zwei Wochen.
FRIST_TAGE = 14

#: Ortsangabe, wenn am Mangel keine steht.
OHNE_ORT = "Ohne Ortsangabe"


def bereich_von(mangel: Mangel) -> str:
    """Überschrift des Bereichsblocks für einen Mangel."""
    ort = (mangel.hinweis_ort or "").strip()
    if ort:
        return ort
    raum = (mangel.raumnummer or "").strip()
    if raum:
        return f"Raum {raum}"
    return OHNE_ORT


def _dateisicher(wert: str) -> str:
    """Zeichen entfernen, die in Dateinamen oder Mailanhängen Ärger machen."""
    ersetzt = (wert or "").strip().replace(" ", "-")
    for zeichen in ("/", "\\", ":", "*", "?", '"', "<", ">", "|", ","):
        ersetzt = ersetzt.replace(zeichen, "")
    return ersetzt.strip("-")


def dokumentkuerzel_vorschlag(projekt: Projekt, gewerk: Gewerk | None) -> str:
    """Kürzel für Fußzeile und Dateiname, aus Projekt und Vergabeeinheit.

    Ziel ist das kurze Muster des Originals:

        Projekt „G.100-DESYUM-Neubau Besucherzentrum DESY“
        Gewerk  „VE300.04“ + „Putz-, Stuckarbeiten, WDVS“
        ergibt  „G-100-DESYUM_VE300.04-WDVS_Mängelanzeige“

    Die Regel dahinter: vom Projektnamen die ersten zwei Bindestrich-Teile des
    ersten Wortes (das ist die Projektnummer samt Kürzel), von der
    Vergabeeinheit der Code und das **letzte** Wort der Bezeichnung — das ist
    im Bauwesen die Abkürzung, unter der das Gewerk läuft (WDVS, Trockenbau,
    Estrich). Der vollständige Projektname wäre als Dateiname 90 Zeichen lang
    und in jeder Mail abgeschnitten.

    Es bleibt ein Vorschlag: Das Feld ist in der Oberfläche änderbar, weil
    Projektnamen keiner Norm folgen.
    """
    erstes_wort = (projekt.name or "").strip().split(" ")[0]
    stuecke = [s for s in erstes_wort.split("-") if s]
    projektteil = _dateisicher("-".join(stuecke[:2]) or erstes_wort).replace(".", "-")

    teile = [projektteil]
    if gewerk is not None:
        code = _dateisicher(gewerk.vergabeeinheit_code or "")
        bezeichnung = (gewerk.vergabeeinheit_bezeichnung or "").strip()
        letztes = _dateisicher(bezeichnung.replace(",", " ").split()[-1]) if bezeichnung else ""
        einheit = "-".join(t for t in (code, letztes) if t)
        if einheit:
            teile.append(einheit)
    teile.append("Mängelanzeige")
    return "_".join(t for t in teile if t)


def vergabeeinheit_von(gewerk: Gewerk | None) -> str:
    """„VE300.04- Putz-, Stuckarbeiten, WDVS“ aus den Gewerksfeldern."""
    if gewerk is None:
        return ""
    code = (gewerk.vergabeeinheit_code or "").strip()
    bezeichnung = (gewerk.vergabeeinheit_bezeichnung or "").strip()
    if code and bezeichnung:
        return f"{code}- {bezeichnung}"
    return code or bezeichnung


def fristvorschlag(briefdatum: date, maengel: list[Mangel]) -> date:
    """Die früheste am Mangel gesetzte Frist, sonst Briefdatum + 14 Tage.

    Bewusst die früheste und nicht die späteste: Das Schreiben setzt EINE
    Frist, und die muss für den dringendsten Mangel passen.
    """
    fristen = [m.erste_frist_bis for m in maengel if m.erste_frist_bis]
    fristen = [f for f in fristen if f >= briefdatum]
    if fristen:
        return min(fristen)
    return briefdatum + timedelta(days=FRIST_TAGE)


def sammle(
    db: Session,
    *,
    projekt: Projekt,
    gewerk: Gewerk | None,
    maengel: list[Mangel],
    empfaenger: erzeugung.Empfaenger,
    sachbearbeiter: erzeugung.Sachbearbeiter,
    begehungsdatum: date,
    briefdatum: date,
    fristsetzungsdatum: date,
    anlagedatum: date | None,
    projektbezeichnung: str = "",
    vergabeeinheit: str = "",
    dokumentkuerzel: str = "",
) -> tuple[erzeugung.Maengelanzeige, list[str]]:
    """Trägt alles zusammen. Gibt die Daten und eine Liste von Hinweisen zurück.

    Die Hinweise sind keine Fehler: „Mangel 00007 hat kein Foto“ soll in der
    Oberfläche stehen, das Dokument aber trotzdem entstehen — mit den übrigen.
    """
    hinweise: list[str] = []
    bereiche: dict[str, erzeugung.MangelBereich] = {}

    for mangel in maengel:
        fotos = sorted(mangel.fotos, key=lambda f: (f.reihenfolge, f.id))
        if not fotos:
            hinweise.append(
                f"Mangel {mangel.nummer} „{mangel.kurzbezeichnung}“ hat kein "
                f"Foto und steht deshalb nicht in der Anlage."
            )
            continue

        schluessel = bereich_von(mangel)
        block = bereiche.get(schluessel)
        if block is None:
            block = erzeugung.MangelBereich(bereich=schluessel, eintraege=[])
            bereiche[schluessel] = block

        for foto in fotos:
            pfad = get_absolute_path(foto.dateipfad)
            if not pfad.is_file():
                hinweise.append(
                    f"Mangel {mangel.nummer}: Die Bilddatei {foto.dateipfad} "
                    f"liegt nicht mehr im Datenordner."
                )
                continue
            block.eintraege.append(
                erzeugung.MangelFoto(
                    daten=pfad.read_bytes(),
                    beschreibung=(foto.bildunterschrift or "").strip()
                    or mangel.kurzbezeichnung,
                )
            )

    # Leere Blöcke entfernen: Sie entstehen, wenn zu einem Mangel nur fehlende
    # Dateien gehörten.
    gefuellt = [b for b in bereiche.values() if b.eintraege]

    daten = erzeugung.Maengelanzeige(
        projektbezeichnung=projektbezeichnung.strip() or projekt.name,
        vergabeeinheit=vergabeeinheit.strip() or vergabeeinheit_von(gewerk),
        begehungsdatum=begehungsdatum,
        dokumentkuerzel=dokumentkuerzel.strip()
        or dokumentkuerzel_vorschlag(projekt, gewerk),
        empfaenger=empfaenger,
        sachbearbeiter=sachbearbeiter,
        briefdatum=briefdatum,
        fristsetzungsdatum=fristsetzungsdatum,
        anlagedatum=anlagedatum,
        bereiche=gefuellt,
    )
    return daten, hinweise


def empfaenger_aus_gewerk(gewerk: Gewerk | None) -> erzeugung.Empfaenger:
    """Vorbelegung des Adressblocks aus den Stammdaten der Firma."""
    if gewerk is None:
        return erzeugung.Empfaenger(firma="")
    return erzeugung.Empfaenger(
        firma=gewerk.firma_name or "",
        ansprechpartner=(gewerk.ansprechpartner or "").strip(),
        strasse_hausnummer=(gewerk.strasse or "").strip(),
        plz_ort=" ".join(
            teil for teil in ((gewerk.plz or "").strip(), (gewerk.ort or "").strip())
            if teil
        ),
        versandart="per Mail",
        email=(gewerk.email or "").strip(),
    )
