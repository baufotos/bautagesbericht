"""Welche Bildformate die App lesen kann — und wie HEIC dazukommt.

DAS PROBLEM
===========
iPhones fotografieren seit Jahren in HEIC. Pillow kennt das Format von Haus
aus nicht: ``Image.open`` wirft, die Datei landet unverändert im Projektordner,
und im Word-Dokument taucht sie gar nicht auf. Auf der Baustelle heißt das,
dass die Hälfte der Fotos nicht ankommt — je nachdem, wer sie gemacht hat.

DIE LÖSUNG
==========
``pillow-heif`` bringt libheif mit und meldet HEIC/HEIF bei Pillow an. Danach
funktioniert der gesamte vorhandene Weg unverändert: öffnen, nach EXIF drehen,
verkleinern, als JPEG speichern. Es ist also kein zweiter Pfad für HEIC nötig —
nur diese eine Anmeldung.

WARUM ES HIER STEHT
===================
Die Anmeldung muss einmal je Prozess passieren, bevor das erste Bild geöffnet
wird. Drei Stellen laden Fotos (Baufotos, Mängelfotos, Berichtsfotos); jede
ruft ``registriere()`` beim Import auf. Der Aufruf ist billig und idempotent.

Fehlt das Paket, läuft alles weiter wie vorher — dann bleibt HEIC eben
unlesbar. Ein fehlendes Zusatzpaket darf die App nicht am Starten hindern.
"""

from __future__ import annotations

from pathlib import Path

#: Wurde die Anmeldung schon versucht? Verhindert wiederholte Importe.
_erledigt = False

#: Ob HEIC gelesen werden kann. Erst nach ``registriere()`` aussagekräftig.
_heic_moeglich = False

#: Formate, die die App entgegennimmt. HEIC/HEIF stehen hier auch dann, wenn
#: das Zusatzpaket fehlt — abgewiesen wird eine Datei nie wegen ihrer Endung,
#: sondern höchstens mit einer klaren Meldung, dass sie nicht lesbar war.
BILD_ENDUNGEN = {
    ".jpg", ".jpeg", ".jpe", ".png", ".gif", ".bmp", ".dib",
    ".webp", ".tif", ".tiff", ".heic", ".heif", ".avif",
    ".jfif", ".ico", ".ppm", ".pgm", ".tga",
}

#: Endung, mit der jedes Foto am Ende gespeichert wird. Ein Bautagesbericht
#: geht an Bauherren und Firmen — dort muss jedes Bild ohne Zusatzsoftware
#: aufgehen, und das heißt JPEG.
AUSGABE_ENDUNG = ".jpg"


def registriere() -> bool:
    """Meldet HEIC/HEIF bei Pillow an. Gibt zurück, ob es geklappt hat."""
    global _erledigt, _heic_moeglich
    if _erledigt:
        return _heic_moeglich

    _erledigt = True
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
        _heic_moeglich = True
    except Exception:
        # Kein pillow-heif im Paket, oder die mitgelieferten Bibliotheken
        # passen nicht zum System. Beides ist kein Grund abzubrechen.
        _heic_moeglich = False
    return _heic_moeglich


def heic_moeglich() -> bool:
    """Kann dieser Rechner HEIC lesen? Für Hinweise in der Oberfläche."""
    return registriere()


def ist_bilddatei(dateiname: str) -> bool:
    return Path(dateiname or "").suffix.lower() in BILD_ENDUNGEN


def als_jpeg_name(dateiname: str) -> str:
    """Ersetzt die Endung durch ``.jpg`` — der Name der fertigen Ausgabe."""
    pfad = Path(dateiname or "foto")
    stamm = pfad.stem or "foto"
    return f"{stamm}{AUSGABE_ENDUNG}"
