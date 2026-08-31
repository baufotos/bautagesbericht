"""Baufotos: Benennen, Verkleinern, Zippen — die Regeln des Büros.

HERKUNFT DIESER REGELN
======================
Das Büro benutzt bisher ein lokales Windows-Programm ("Baustellenfotos-Tool"),
das Baustellenfotos umbenennt, verkleinert, in eine ZIP-Datei packt und per
Outlook verschickt. Dieses Modul übernimmt dessen Regeln **unverändert**, damit
die hier erzeugten ZIP-Dateien genauso aussehen wie die bisherigen und ohne
Umgewöhnung in denselben Projektordner wandern können:

    sanitize      Leerzeichen -> "_", alles außer Wortzeichen, lateinischen
                  Sonderbuchstaben und "-" entfällt. Umlaute und ß bleiben.
    Datum         JJMMTT, z. B. 260819
    Fotoname      {datum}_{kategorie}_{nummer}.jpg   (Nummer 1-basiert)
    ZIP-Name      {datum}_{projekt}_{kategorie}.zip
    Bildgröße     längste Kante 1600 px, JPEG-Qualität 70

Wer diese Werte ändert, ändert die Dateinamen in den Projektordnern des ganzen
Büros — deshalb stehen sie hier als benannte Konstanten und nicht verstreut im
Code.

WARUM DAS ZIP NICHT GESPEICHERT WIRD
====================================
Das Archiv wird bei jedem Abruf frisch aus den Einzelfotos gebaut. Ein
zwischengespeichertes ZIP wäre nach dem Nachreichen eines Fotos still veraltet —
und der kostenlose Render-Container hat ohnehin wenig Platz. Der Aufwand ist
klein: Die Fotos sind nach dem Verkleinern nur wenige hundert Kilobyte groß.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date
from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Baufoto, Fotosatz, Projekt
from app.services import bildformate, fotospeicher

# HEIC/HEIF bei Pillow anmelden, bevor das erste Foto geöffnet wird. Ohne das
# kommen iPhone-Fotos unverarbeitet im Projektordner an (siehe bildformate).
bildformate.registriere()

# --- Regeln des Büros (siehe Modulkopf; bitte nicht "aufräumen") -------------

#: Längste Bildkante nach dem Verkleinern.
MAX_KANTE = 1600
#: JPEG-Qualität. 70 ist der Wert des bisherigen Werkzeugs — sichtbar sparsam,
#: für die Dokumentation eines Bauzustands aber völlig ausreichend.
JPEG_QUALITAET = 70

#: Was hochgeladen werden darf. Die Liste steht in ``bildformate`` — dort
#: gehört sie hin, weil Mängel- und Berichtsfotos denselben Bestand annehmen.
#: Was am Ende im Projektordner liegt, ist unabhängig davon immer ein JPEG.
ERLAUBTE_ENDUNGEN = bildformate.BILD_ENDUNGEN

#: Maximale Anzahl Fotos in einem Upload-Aufruf. Das Frontend schickt einzeln;
#: die Grenze schützt nur vor Ausrutschern.
MAX_FOTOS_PRO_UPLOAD = 40


class BaufotoFehler(Exception):
    """Eingabefehler, der dem Nutzer im Klartext gezeigt werden kann."""


def sanitize(wert: str) -> str:
    """Projekt-/Kategoriename für einen Dateinamen bereinigen.

    ``\\w`` ist in Python unicode-bewusst, deshalb bleiben Umlaute und ß
    erhalten — genau wie im bisherigen Werkzeug, wo "Kita Nord" zu "Kita_Nord"
    und "Grünanlage" zu "Grünanlage" wird.
    """
    text = str(wert or "").strip()
    text = re.sub(r"\s+", "_", text)
    # À-ſ = lateinische Sonderbuchstaben. Als Escape-Folge
    # geschrieben, damit die Regel unabhängig von der Dateikodierung gilt.
    text = re.sub(r"[^\wÀ-ſ-]", "", text)
    return text


def datum_stempel(tag: date | None = None) -> str:
    """Datum als JJMMTT."""
    return (tag or date.today()).strftime("%y%m%d")


def foto_dateiname(tag: date, kategorie: str, nummer: int) -> str:
    """``{JJMMTT}_{Kategorie}_{Nummer}.jpg`` — die Nummer beginnt bei 1."""
    return f"{datum_stempel(tag)}_{sanitize(kategorie)}_{nummer}.jpg"


def zip_dateiname(tag: date, projekt_name: str, kategorie: str) -> str:
    """``{JJMMTT}_{Projekt}_{Kategorie}.zip``."""
    return f"{datum_stempel(tag)}_{sanitize(projekt_name)}_{sanitize(kategorie)}.zip"


def ist_erlaubte_datei(dateiname: str) -> bool:
    return Path(dateiname or "").suffix.lower() in ERLAUBTE_ENDUNGEN


def verkleinere(rohdaten: bytes) -> tuple[bytes, bool]:
    """Foto drehen, verkleinern und als JPEG zurückgeben.

    Das Ergebnis ist immer ein JPEG, gleich womit fotografiert wurde — HEIC vom
    iPhone, PNG aus einem Screenshot, TIFF aus einer Kamera. Der Bericht geht
    an Bauherren und Nachunternehmer; dort muss jedes Bild ohne Zusatzsoftware
    aufgehen.

    ``als_jpeg=False`` heißt: Pillow konnte die Datei nicht lesen. Dann kommen
    die Originaldaten unverändert zurück — ein Foto darf nie verloren gehen,
    nur weil die Umwandlung scheitert. Der Aufrufer behält in dem Fall die
    ursprüngliche Endung bei, damit die Datei nicht fälschlich .jpg heißt.
    """
    try:
        with Image.open(io.BytesIO(rohdaten)) as bild:
            # EXIF-Drehung anwenden: Hochformat-Fotos vom Handy lägen sonst quer.
            gedreht = ImageOps.exif_transpose(bild)
            # Transparenz auf Weiß setzen statt auf Schwarz: Ein PNG mit
            # durchsichtigem Hintergrund wird sonst zu einem dunklen Klotz.
            if gedreht.mode in ("RGBA", "LA", "P"):
                mit_alpha = gedreht.convert("RGBA")
                hintergrund = Image.new("RGB", mit_alpha.size, (255, 255, 255))
                hintergrund.paste(mit_alpha, mask=mit_alpha.split()[-1])
                gedreht = hintergrund
            else:
                gedreht = gedreht.convert("RGB")
            gedreht.thumbnail((MAX_KANTE, MAX_KANTE), Image.Resampling.LANCZOS)
            puffer = io.BytesIO()
            gedreht.save(puffer, format="JPEG", quality=JPEG_QUALITAET, optimize=True)
    except Exception:
        return rohdaten, False
    return puffer.getvalue(), True


def naechste_nummer(db: Session, fotosatz_id: int) -> int:
    """Nächste laufende Nummer innerhalb eines Fotosatzes (1-basiert).

    Bewusst über das Maximum und nicht über die Anzahl: Wird ein Foto gelöscht,
    soll keine Nummer doppelt vergeben werden — im ZIP wären sonst zwei
    Dateien mit demselben Namen.
    """
    from sqlalchemy import func as sql_func

    hoechste = (
        db.query(sql_func.max(Baufoto.reihenfolge))
        .filter(Baufoto.fotosatz_id == fotosatz_id)
        .scalar()
    )
    return int(hoechste or 0) + 1


def baue_zip(fotosatz: Fotosatz) -> bytes:
    """Alle Fotos eines Satzes als ZIP-Archiv im Speicher.

    Fehlende Dateien werden übersprungen, nicht als Fehler behandelt: Ein
    verlorenes Einzelfoto darf nicht verhindern, dass die übrigen 19 beim
    Bauleiter ankommen. Was fehlt, steht in der beigelegten ``FEHLT.txt``.
    """
    puffer = io.BytesIO()
    fehlend: list[str] = []

    with zipfile.ZipFile(puffer, "w", compression=zipfile.ZIP_DEFLATED) as archiv:
        for foto in sorted(fotosatz.fotos, key=lambda f: (f.reihenfolge, f.id)):
            # Ueber die Speicherschicht, damit es gleich funktioniert, ob das
            # Foto auf der Platte oder im Objektspeicher liegt.
            daten = fotospeicher.lies(foto.dateipfad)
            if daten is None:
                fehlend.append(foto.dateiname)
                continue
            archiv.writestr(foto.dateiname, daten)

        if fehlend:
            archiv.writestr(
                "FEHLT.txt",
                "Diese Fotos waren auf dem Server nicht mehr vorhanden und "
                "fehlen in diesem Archiv:\n\n" + "\n".join(fehlend) + "\n",
            )

    return puffer.getvalue()


def webhook_fuer(projekt: Projekt | None) -> str:
    """Teams-Kanal des Projekts, sonst leer (dann greift der globale Fallback).

    Anders als beim Mangel gibt es hier keine Firma — ein Fotosatz geht an das
    eigene Team, nicht an einen Nachunternehmer.
    """
    if projekt is not None and (projekt.teams_webhook_url or "").strip():
        return projekt.teams_webhook_url.strip()
    return ""


async def melde_fotosatz(db: Session, fotosatz: Fotosatz) -> tuple[bool, str, str]:
    """Meldet einen Fotosatz mit Download-Link in Teams.

    Gibt ``(gemeldet, kanal, nachricht)`` zurück. ``gemeldet=False`` heißt
    ausdrücklich auch dann "nicht gemeldet", wenn einfach kein Kanal hinterlegt
    ist — "nichts zu tun" darf in der Oberfläche nicht als Erfolg erscheinen.
    """
    from app.services.teams_notifier import send_fotosatz_notification

    if not fotosatz.fotos:
        return False, "keiner", "Der Fotosatz enthält noch keine Fotos."

    projekt = fotosatz.projekt
    try:
        gemeldet = await send_fotosatz_notification(
            fotosatz_id=fotosatz.id,
            projekt_name=projekt.name if projekt else "",
            kategorie=fotosatz.kategorie,
            datum=fotosatz.datum,
            anzahl=len(fotosatz.fotos),
            zip_name=zip_dateiname(
                fotosatz.datum,
                projekt.name if projekt else "Projekt",
                fotosatz.kategorie,
            ),
            webhook_url=webhook_fuer(projekt),
        )
    except Exception as fehler:
        return False, "teams", f"Teams-Meldung fehlgeschlagen: {fehler}"

    if not gemeldet:
        return False, "keiner", (
            "Kein Teams-Kanal hinterlegt (Projekt oder BTB_TEAMS_WEBHOOK_URL). "
            "Die ZIP-Datei lässt sich weiterhin direkt herunterladen."
        )

    fotosatz.zuletzt_gemeldet_am = date.today()
    db.commit()
    return True, "teams", "In Teams gemeldet, mit Link auf die ZIP-Datei."
