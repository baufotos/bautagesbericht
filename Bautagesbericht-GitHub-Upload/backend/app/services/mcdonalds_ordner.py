"""Den Standortordner eines McDonald's-Projekts anlegen — mit voller Struktur.

DER ORDNERNAME
==============
``<3-stelliger UNLOCODE>_<Standortname>`` — für die SLS-Anfrage
"56132 Nievern, Auf d. Lay" also ``NIV_Nievern``. Der Code kommt aus der
Referenztabelle (``mcdonalds_unlocode``), der Name aus der Anfrage. Ist kein
Code zu ermitteln, steht ``XXX`` davor: Ein Ordner mit sichtbarer Lücke ist
besser als einer, dessen falscher Code später niemandem auffällt.

DARIN DIE 163 UNTERORDNER DES MUSTERORDNERS
===========================================
Nicht ein leerer Ordner, sondern die ganze Ablage des Büros: ``18-GP``,
``PHASE 0`` bis ``PHASE 4 & 5``, die Vertragsordner der Subplaner, alles.
Zwei Quellen, in dieser Reihenfolge:

1. **Der echte Musterordner**, wenn er erreichbar ist. Er ist die Wahrheit:
   Ändert das Büro ihn, bekommt der nächste Standort die neue Struktur, ohne
   dass jemand Programmcode anfasst. Die beiden PDF-Vorlagen im
   StaffSafe-Ordner kommen nur auf diesem Weg mit.
2. **Die mitgelieferte Liste** (``mcdonalds_musterstruktur``), sonst. Damit
   entsteht dieselbe Struktur auch ohne Zugriff auf den Musterordner.

Platzhalternamen wie ``JJMMTT_Bauantrag`` oder ``0XX_Sachverhalt xy`` werden
unverändert übernommen — das ist die Schreibvorgabe des Büros für den Tag, an
dem es diesen Vorgang gibt. Ein beim Anlegen eingesetztes Datum wäre geraten
und stünde für immer falsch im Pfad.

DREI ZUSTÄNDE, UND "VORBEREITET" IST KEIN FEHLER
================================================
    angelegt      Der Ordner steht wirklich auf dem Laufwerk.
    vorbereitet   Name und Struktur sind ermittelt, aber es gibt hier kein
                  Laufwerk. Das ist der Normalzustand auf der Website: Ein
                  Dienst im Internet erreicht das Büronetz nicht, und daran
                  ist nichts kaputt. Der Ordner wird später von einem Rechner
                  im Büro angelegt.
    fehler        Es gibt ein Laufwerk, aber das Anlegen ging schief
                  (Pfad nicht verbunden, keine Rechte, Name unzulässig).

Der Unterschied ist wichtig: Wer auf der Büro-Website fünfzig Standorte anlegt
und fünfzigmal "Fehler" liest, hört auf hinzuschauen. Genau dann fällt der
echte Fehler nicht mehr auf.

WARUM DAS IM HINTERGRUND LÄUFT
==============================
Ein Netzlaufwerk antwortet manchmal in Millisekunden und manchmal in zwanzig
Sekunden, und es sind 163 Ordner. Der Bauleiter hat seine Mail hochgeladen und
soll weiterarbeiten können; deshalb übergibt der Endpunkt die Ablage an eine
Hintergrundaufgabe (FastAPI ``BackgroundTasks``, wie in
``routers.einreichungen``). Was daraus wurde, steht danach am Standort.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import McdonaldsStandort
from app.services import mcdonalds_unlocode as unlocode
from app.services.mcdonalds_musterstruktur import (
    MUSTERDATEIEN,
    MUSTERORDNER_NAME,
    UNTERORDNER,
)

#: Platzhalter, wenn kein Ortscode ermittelt werden konnte.
CODE_UNBEKANNT = "XXX"

#: Zeichen, die Windows in Ordnernamen nicht zulässt. Ein Standortname wie
#: "Köln Ring / Nord" käme sonst als Fehler zurück, den niemand einem
#: Schrägstrich zuordnet.
_VERBOTEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class OrdnerErgebnis:
    """Was die Anlage bewirkt hat — auch "vorbereitet" ist ein Ergebnis."""

    status: str                       # "angelegt" | "vorbereitet" | "fehler"
    ordner_name: str = ""
    pfad: str | None = None
    pfad_sharepoint: str | None = None
    #: Wie viele Unterordner entstanden sind.
    anzahl: int = 0
    #: Klartext für die Oberfläche: was fehlt, was schiefging, was aussteht.
    meldung: str = ""
    hinweise: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Der Name
# ─────────────────────────────────────────────────────────────────────────────


def saubere_bezeichnung(text: str) -> str:
    """Macht aus einem Standortnamen einen zulässigen Ordnernamen."""
    ohne = _VERBOTEN.sub(" ", text or "")
    # Windows verschluckt Punkte und Leerzeichen am Ende eines Ordnernamens
    # stillschweigend — dann heißt der Ordner anders als der Pfad in der
    # Datenbank, und niemand findet ihn wieder.
    return " ".join(ohne.split()).rstrip(". ")


def ordnername(code: str | None, standort_name: str) -> str:
    """``NIV_Nievern`` — siehe Modultext."""
    kennung = (code or CODE_UNBEKANNT).strip().upper() or CODE_UNBEKANNT
    name = saubere_bezeichnung(standort_name)
    return f"{kennung}_{name}" if name else kennung


# ─────────────────────────────────────────────────────────────────────────────
# Die Quelle der Struktur
# ─────────────────────────────────────────────────────────────────────────────


def musterordner() -> Path | None:
    """Der echte Musterordner, wenn er erreichbar ist — sonst ``None``."""
    ausdruecklich = (settings.mcdonalds_musterordner or "").strip()
    if ausdruecklich:
        pfad = Path(ausdruecklich)
        return pfad if pfad.is_dir() else None

    basis = (settings.mcdonalds_basis_standorte or "").strip()
    if not basis:
        return None
    pfad = Path(basis) / MUSTERORDNER_NAME
    return pfad if pfad.is_dir() else None


def _aus_musterordner(quelle: Path, ziel: Path) -> tuple[int, list[str]]:
    """Kopiert den Musterordner. Ergebnis: (Anzahl Unterordner, Hinweise).

    BEWUSST NICHT ``shutil.copytree``
    =================================
    Der Musterordner des Büros ist schreibgeschützt (Attribut ``R``, Modus
    0555) — vermutlich, damit niemand versehentlich in der Vorlage arbeitet.
    ``copytree`` überträgt diese Attribute mit, und dann wäre **jeder neue
    Projektordner schreibgeschützt**: Dateien ließen sich zwar noch
    hineinlegen, aber Umbenennen und Löschen von Unterordnern schlägt fehl,
    und niemand käme auf die Vorlage als Ursache. Beim Aufräumen der
    Testablage ist genau das aufgefallen.

    Deshalb wird hier von Hand kopiert: Ordner mit ``mkdir`` (also mit den
    normalen Rechten des Anwenders) und Dateien mit ``copyfile``, das nur den
    Inhalt überträgt und keine Attribute.

    Ein zweiter Lauf auf einem vorhandenen Standort ergänzt, was fehlt, und
    überschreibt keine Datei, die schon dort liegt — man will die
    Musterstruktur nachziehen können, ohne die Arbeit von Wochen zu
    zerstören.
    """
    anzahl = 0
    for eintrag in sorted(quelle.rglob("*")):
        relativ = eintrag.relative_to(quelle)
        neuer_pfad = ziel / relativ
        if eintrag.is_dir():
            neuer_pfad.mkdir(parents=True, exist_ok=True)
            anzahl += 1
        elif eintrag.is_file() and not neuer_pfad.exists():
            neuer_pfad.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(eintrag, neuer_pfad)
    ziel.mkdir(parents=True, exist_ok=True)
    return anzahl, []


def _aus_liste(ziel: Path) -> tuple[int, list[str]]:
    """Legt die Struktur aus der mitgelieferten Liste an."""
    for teil in UNTERORDNER:
        (ziel / teil).mkdir(parents=True, exist_ok=True)
    anzahl = sum(1 for p in ziel.rglob("*") if p.is_dir())
    hinweise = [
        f"Der Musterordner „{MUSTERORDNER_NAME}“ war nicht erreichbar. Die "
        f"{len(UNTERORDNER)} Ordner sind aus der mitgelieferten Liste "
        f"entstanden; die {len(MUSTERDATEIEN)} Vorlagendateien daraus fehlen "
        "und sind bei Bedarf von Hand zu kopieren."
    ]
    return anzahl, hinweise


# ─────────────────────────────────────────────────────────────────────────────
# Die beiden Ablagen
# ─────────────────────────────────────────────────────────────────────────────


def _lege_standortordner_an(name: str) -> tuple[str | None, str, int, list[str]]:
    """Legt den Standortordner samt Struktur an.

    Ergebnis: (Pfad, Meldung, Anzahl Unterordner, Hinweise). Pfad ``None``
    heißt: nicht angelegt — die Meldung sagt, warum.
    """
    basis = (settings.mcdonalds_basis_standorte or "").strip()
    if not basis:
        return None, "", 0, []          # "vorbereitet", siehe erzeuge_…

    wurzel = Path(basis)
    if not wurzel.is_dir():
        return None, (
            f"Der Standorte-Ordner „{basis}“ ist nicht erreichbar. Ist das "
            "Projektlaufwerk verbunden?"
        ), 0, []

    ziel = wurzel / name
    quelle = musterordner()
    try:
        if quelle is not None:
            anzahl, hinweise = _aus_musterordner(quelle, ziel)
        else:
            ziel.mkdir(parents=True, exist_ok=True)
            anzahl, hinweise = _aus_liste(ziel)
    except OSError as fehler:
        return None, f"Der Ordner „{ziel}“ ließ sich nicht anlegen: {fehler}", 0, []

    return str(ziel), "", anzahl, hinweise


def _lege_sharepoint_ordner_an(name: str) -> tuple[str | None, str]:
    """Legt den Ordner auf SharePoint an — noch nicht implementiert.

    TODO McDonald's: SharePoint-Anbindung. Der Aufrufpunkt steht, das Ziel
    kommt aus ``settings.mcdonalds_basis_sharepoint``. Was fehlt, ist der
    Zugriff selbst (Microsoft Graph mit einer Registrierung des Büros,
    ``POST /drives/{id}/items/{id}/children`` mit ``folder``-Facette).

    Bewusst kein Fehler: Der Ordner im Projektlaufwerk ist der, mit dem
    gearbeitet wird — den ganzen Vorgang daran scheitern zu lassen, dass die
    zweite Ablage noch fehlt, würde das Feature unbenutzbar machen.
    """
    ziel = (settings.mcdonalds_basis_sharepoint or "").strip()
    if not ziel:
        return None, ""
    return None, (
        f"Auf SharePoint muss „{name}“ noch von Hand angelegt werden "
        f"({ziel}) — die automatische Anbindung ist vorbereitet, aber noch "
        "nicht in Betrieb."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Der Ablauf
# ─────────────────────────────────────────────────────────────────────────────


def _code_ermitteln(standort: McdonaldsStandort, db: Session) -> str:
    """Setzt ``standort.unlocode``, falls noch keiner dransteht."""
    if standort.unlocode:
        return ""

    ort = (standort.ort or "").strip()
    if not ort:
        return (
            "Zum Standort ist kein Ort hinterlegt — ohne ihn gibt es keinen "
            f"UN/LOCODE. Der Ordner heißt deshalb „{CODE_UNBEKANNT}_…“."
        )

    if unlocode.anzahl_eintraege(db) == 0:
        return (
            "Die UN/LOCODE-Tabelle ist noch nicht hochgeladen (Anlage 5.1 des "
            f"Projekthandbuchs). Der Ordner heißt deshalb „{CODE_UNBEKANNT}_…“."
        )

    treffer = unlocode.ermittle(db, ort)
    if not treffer:
        return (
            f"Für den Ort „{ort}“ war in der UN/LOCODE-Tabelle kein Eintrag zu "
            f"finden. Der Ordner heißt deshalb „{CODE_UNBEKANNT}_…“."
        )

    standort.unlocode = treffer.code
    if treffer.art == "unscharf":
        return (
            f"Der Code {treffer.code} wurde über einen unscharfen Vergleich "
            f"gefunden („{ort}“ → „{treffer.ort}“). Bitte gegenlesen."
        )
    return ""


def erzeuge_projektordner(
    standort: McdonaldsStandort, db: Session
) -> OrdnerErgebnis:
    """Legt Standortordner und Struktur an und schreibt das Ergebnis dran.

    Der Aufrufer committet.
    """
    meldungen: list[str] = []

    hinweis = _code_ermitteln(standort, db)
    if hinweis:
        meldungen.append(hinweis)

    name = ordnername(standort.unlocode, standort.standort_name or standort.ort)
    standort.ordner_name = name

    pfad, fehler, anzahl, hinweise = _lege_standortordner_an(name)
    meldungen += hinweise
    if fehler:
        meldungen.append(fehler)

    pfad_sp, meldung_sp = _lege_sharepoint_ordner_an(name)
    if meldung_sp:
        meldungen.append(meldung_sp)

    if pfad:
        status = "angelegt"
    elif fehler:
        status = "fehler"
    else:
        status = "vorbereitet"
        meldungen.append(
            f"Der Ordner „{name}“ ist noch nicht angelegt: Von hier aus gibt "
            "es keinen Zugriff auf das Projektlaufwerk. Name und Struktur "
            f"({len(UNTERORDNER)} Unterordner) stehen fest — anlegen muss ihn "
            "ein Rechner im Büronetz."
        )

    ergebnis = OrdnerErgebnis(
        status=status,
        ordner_name=name,
        pfad=pfad,
        pfad_sharepoint=pfad_sp,
        anzahl=anzahl,
        meldung=" ".join(meldungen).strip(),
        hinweise=hinweise,
    )

    standort.ordner_status = ergebnis.status
    standort.ordner_pfad = ergebnis.pfad
    standort.ordner_pfad_sharepoint = ergebnis.pfad_sharepoint
    standort.ordner_anzahl = ergebnis.anzahl
    standort.fehlermeldung = ergebnis.meldung or None
    return ergebnis


def erzeuge_projektordner_im_hintergrund(standort_id: int) -> None:
    """Einsprungpunkt für ``BackgroundTasks`` — mit eigener Sitzung.

    Die Sitzung des Endpunkts ist beendet, wenn diese Aufgabe läuft (siehe
    ``routers.einreichungen._run_process``, dasselbe Muster). Ausnahmen werden
    hier abgefangen und am Standort vermerkt: Eine Hintergrundaufgabe, die
    wirft, hinterlässt sonst einen Standort, der für immer "wird angelegt"
    anzeigt.
    """
    db = SessionLocal()
    try:
        standort = db.get(McdonaldsStandort, standort_id)
        if standort is None:
            return
        try:
            erzeuge_projektordner(standort, db)
        except Exception as fehler:  # noqa: BLE001 — siehe Funktionstext
            standort.ordner_status = "fehler"
            standort.fehlermeldung = (
                "Beim Anlegen des Standortordners ist ein unerwarteter Fehler "
                f"aufgetreten: {fehler}"
            )
        db.commit()
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Ablage einer Datei im Standortordner
# ─────────────────────────────────────────────────────────────────────────────


def lege_datei_ab(
    standort: McdonaldsStandort, unterpfad: str, dateiname: str, daten: bytes
) -> tuple[str | None, str]:
    """Legt eine Datei in einen Unterordner des Standorts. (Pfad, Meldung).

    Damit landet der Einzelabruf im Vertragsordner des Subplaners, ohne dass
    jemand ihn von Hand hineinzieht (siehe ``mcdonalds_beauftragung``).

    Ist kein Laufwerk da, ist das kein Fehler — der Outlook-Entwurf entsteht
    trotzdem, und die Meldung sagt, dass die Ablage aussteht. Auf der Website
    ist das der Normalfall.
    """
    if not standort.ordner_pfad:
        return None, (
            "Die Beauftragung wurde nicht im Projektordner abgelegt: Der "
            "Standortordner ist hier noch nicht angelegt."
        )

    ziel = Path(standort.ordner_pfad) / unterpfad
    try:
        ziel.mkdir(parents=True, exist_ok=True)
        datei = ziel / dateiname
        datei.write_bytes(daten)
    except OSError as fehler:
        return None, (
            f"Die Beauftragung ließ sich nicht in „{ziel}“ ablegen: {fehler}"
        )
    return str(datei), ""
