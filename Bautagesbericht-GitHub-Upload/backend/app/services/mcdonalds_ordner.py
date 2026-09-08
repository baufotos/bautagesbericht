"""Den Projektordner eines McDonald's-Standorts anlegen.

DER ORDNERNAME
==============
``<3-stelliger UNLOCODE>_<Standortname>`` — zum Beispiel
``AAH_Aachen Europaplatz``. Der Code kommt aus der Referenztabelle
(``mcdonalds_unlocode``), der Name aus der Mail. Ist kein Code zu ermitteln,
steht ``XXX`` davor: Ein Ordner mit sichtbarer Lücke ist besser als keiner
und besser als einer, dessen falscher Code später niemandem auffällt.

WARUM DAS IM HINTERGRUND LÄUFT
==============================
Ein Netzlaufwerk antwortet manchmal in Millisekunden und manchmal in zwanzig
Sekunden — und SharePoint kommt später noch dazu. Der Bauleiter hat seine Mail
hochgeladen und soll weiterarbeiten können; deshalb legt der Endpunkt den Fall
an und übergibt die Ablage an eine Hintergrundaufgabe (FastAPI
``BackgroundTasks``, wie in ``routers.einreichungen``). Was daraus wurde, steht
danach am Fall: ``ordner_status``, die beiden Pfade und im Fehlerfall eine
Meldung im Klartext.

WARUM HIER NICHTS ABSTÜRZT
==========================
Die Zielpfade sind noch nicht konfiguriert (siehe ``config.Settings``), und
auch später wird ein Netzlaufwerk mal nicht verbunden sein. Eine
Hintergrundaufgabe, die eine Ausnahme wirft, verschwindet im Serverprotokoll —
in der App sähe der Fall dann für immer nach "wird angelegt" aus. Deshalb
endet jeder Weg hier in einem Zustand, den die Oberfläche anzeigen kann.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import McdonaldsFall
from app.services import mcdonalds_unlocode as unlocode

#: Platzhalter, wenn kein Code ermittelt werden konnte.
CODE_UNBEKANNT = "XXX"

#: Die Unterordner des Musterordners, die in jedem Standortordner entstehen.
#:
#: TODO McDonald's: Musterordner-Struktur ergänzen. Sobald die Liste des Büros
#: vorliegt, hier die Ordnernamen in der gewünschten Reihenfolge eintragen —
#: Unterebenen mit Schrägstrich, z. B. "02 PLANUNG/01 Entwurf". Mehr ist nicht
#: zu tun: ``_lege_unterordner_an`` arbeitet die Liste ab, und eine leere
#: Liste bedeutet schlicht, dass nur der übergeordnete Ordner entsteht.
UNTERORDNER: list[str] = []

#: Zeichen, die Windows in Ordnernamen nicht zulässt. Ein Standortname wie
#: "Köln Ring / Nord" käme sonst als Fehler zurück, den niemand einem
#: Schrägstrich zuordnet.
_VERBOTEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class OrdnerErgebnis:
    """Was die Anlage bewirkt hat — auch der Fehlerfall ist ein Ergebnis."""

    status: str                     # "angelegt" | "fehler"
    ordner_name: str = ""
    pfad_h: str | None = None
    pfad_sharepoint: str | None = None
    #: Klartext für die Oberfläche: was fehlt, was schiefging, was aussteht.
    meldung: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Der Name
# ─────────────────────────────────────────────────────────────────────────────


def saubere_bezeichnung(text: str) -> str:
    """Macht aus einem Standortnamen einen zulässigen Ordnernamen."""
    ohne = _VERBOTEN.sub(" ", text or "")
    # Windows verschluckt Punkte und Leerzeichen am Ende eines Ordnernamens
    # stillschweigend — dann heißt der Ordner anders als der Pfad in der
    # Datenbank, und die Abholung findet ihn nicht wieder.
    return " ".join(ohne.split()).rstrip(". ")


def ordnername(code: str | None, standort_name: str) -> str:
    """``<UNLOCODE>_<Standortname>``, siehe Modultext."""
    kennung = (code or CODE_UNBEKANNT).strip().upper() or CODE_UNBEKANNT
    name = saubere_bezeichnung(standort_name)
    return f"{kennung}_{name}" if name else kennung


# ─────────────────────────────────────────────────────────────────────────────
# Die beiden Ablagen
# ─────────────────────────────────────────────────────────────────────────────


def _lege_unterordner_an(wurzel: Path) -> None:
    """Legt die Musterordner-Struktur unter dem Standortordner an.

    Siehe ``UNTERORDNER``: Solange die Liste leer ist, tut diese Funktion
    nichts, und der Aufrufpunkt bleibt trotzdem stehen.
    """
    for teil in UNTERORDNER:
        (wurzel / teil).mkdir(parents=True, exist_ok=True)


def _lege_h_ordner_an(name: str) -> tuple[str | None, str]:
    """Legt den Ordner im Netzlaufwerk an. Ergebnis: (Pfad, Meldung)."""
    basis = (settings.mcdonalds_basis_h or "").strip()
    if not basis:
        return None, (
            "Basispfad H: noch nicht konfiguriert. Der Projektordner wurde "
            "nicht angelegt — bitte in einstellungen.txt bei "
            "„mcdonalds_ordner_h=“ eintragen (oder BTB_MCDONALDS_BASIS_H "
            "setzen) und die Anlage erneut anstoßen."
        )

    wurzel = Path(basis)
    if not wurzel.is_dir():
        return None, (
            f"Der Basispfad „{basis}“ ist nicht erreichbar. Ist das "
            "Netzlaufwerk verbunden?"
        )

    ziel = wurzel / name
    try:
        ziel.mkdir(parents=True, exist_ok=True)
        _lege_unterordner_an(ziel)
    except OSError as fehler:
        return None, f"Der Ordner „{ziel}“ ließ sich nicht anlegen: {fehler}"
    return str(ziel), ""


def _lege_sharepoint_ordner_an(name: str) -> tuple[str | None, str]:
    """Legt den Ordner auf SharePoint an — noch nicht implementiert.

    TODO McDonald's: SharePoint-Anbindung. Der Aufrufpunkt steht, die
    Zielbibliothek kommt aus ``settings.mcdonalds_basis_sharepoint``. Was
    fehlt, ist der Zugriff selbst (Microsoft Graph mit einer Registrierung des
    Büros, ``POST /drives/{id}/items/{id}/children`` mit ``folder``-Facette).

    Bis dahin gibt diese Funktion ehrlich zurück, dass nichts passiert ist.
    Bewusst kein Fehler: Der Ordner im Netzlaufwerk ist der, mit dem im Büro
    gearbeitet wird — der ganze Vorgang daran scheitern zu lassen, dass die
    zweite Ablage noch fehlt, würde das Feature unbenutzbar machen.
    """
    ziel = (settings.mcdonalds_basis_sharepoint or "").strip()
    if not ziel:
        return None, (
            "SharePoint-Ziel noch nicht konfiguriert — dort wurde kein Ordner "
            "angelegt."
        )
    return None, (
        f"Der Ordner „{name}“ muss auf SharePoint noch von Hand angelegt "
        f"werden ({ziel}). Die automatische Anbindung ist vorbereitet, aber "
        "noch nicht in Betrieb."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Der Ablauf
# ─────────────────────────────────────────────────────────────────────────────


def _code_ermitteln(fall: McdonaldsFall, db: Session) -> str:
    """Setzt ``fall.unlocode``, falls noch keiner dransteht. Meldet Probleme."""
    if fall.unlocode:
        return ""

    ort = (fall.standort_ort or "").strip()
    if not ort and fall.standort_adresse:
        ort = unlocode.ort_aus_adresse(fall.standort_adresse)
        if ort:
            fall.standort_ort = ort

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

    fall.unlocode = treffer.code
    if treffer.art == "unscharf":
        return (
            f"Der Code {treffer.code} wurde über einen unscharfen Vergleich "
            f"gefunden („{ort}“ → „{treffer.ort}“). Bitte gegenlesen."
        )
    return ""


def erzeuge_projektordner(fall: McdonaldsFall, db: Session) -> OrdnerErgebnis:
    """Legt Ordner und Unterstruktur an und schreibt das Ergebnis an den Fall.

    Der Aufrufer committet nicht — das tut ``erzeuge_projektordner_im_hintergrund``
    bzw. der Endpunkt, der diese Funktion direkt benutzt.
    """
    meldungen: list[str] = []

    hinweis = _code_ermitteln(fall, db)
    if hinweis:
        meldungen.append(hinweis)

    name = ordnername(fall.unlocode, fall.standort_name or fall.standort_ort)
    fall.ordner_name = name

    pfad_h, meldung_h = _lege_h_ordner_an(name)
    if meldung_h:
        meldungen.append(meldung_h)

    pfad_sp, meldung_sp = _lege_sharepoint_ordner_an(name)
    if meldung_sp:
        meldungen.append(meldung_sp)

    # "angelegt" bedeutet: Der Ordner, mit dem im Büro gearbeitet wird, ist da.
    # Die noch fehlende SharePoint-Ablage steht als Meldung daneben, damit
    # sichtbar bleibt, was aussteht — aber sie macht aus einem geglückten
    # Vorgang keinen gescheiterten.
    status = "angelegt" if pfad_h else "fehler"

    ergebnis = OrdnerErgebnis(
        status=status,
        ordner_name=name,
        pfad_h=pfad_h,
        pfad_sharepoint=pfad_sp,
        meldung=" ".join(meldungen).strip(),
    )

    fall.ordner_status = ergebnis.status
    fall.ordner_pfad_h = ergebnis.pfad_h
    fall.ordner_pfad_sharepoint = ergebnis.pfad_sharepoint
    fall.fehlermeldung = ergebnis.meldung or None
    return ergebnis


def erzeuge_projektordner_im_hintergrund(fall_id: int) -> None:
    """Einsprungpunkt für ``BackgroundTasks`` — mit eigener Sitzung.

    Die Sitzung des Endpunkts ist beendet, wenn diese Aufgabe läuft (siehe
    ``routers.einreichungen._run_process``, dasselbe Muster). Ausnahmen werden
    hier abgefangen und am Fall vermerkt: Eine Hintergrundaufgabe, die wirft,
    hinterlässt sonst einen Fall, der für immer "ausstehend" anzeigt.
    """
    db = SessionLocal()
    try:
        fall = db.get(McdonaldsFall, fall_id)
        if fall is None:
            return
        try:
            erzeuge_projektordner(fall, db)
        except Exception as fehler:  # noqa: BLE001 — siehe Funktionstext
            fall.ordner_status = "fehler"
            fall.fehlermeldung = (
                "Beim Anlegen des Projektordners ist ein unerwarteter Fehler "
                f"aufgetreten: {fehler}"
            )
        db.commit()
    finally:
        db.close()
