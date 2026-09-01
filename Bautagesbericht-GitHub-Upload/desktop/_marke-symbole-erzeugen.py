"""Erzeugt alle Symbole der App aus der einen Markendatei.

EINE QUELLE, VIELE GRÖSSEN
==========================
Verbindlich ist ``frontend/public/marke/hpp-wortmarke.svg`` — die HPP-Wortmarke
als Vektor. Dieses Skript liest deren Pfad und füllt ihn in den Größen, die
Windows und die Mobilgeräte brauchen:

    frontend/public/icons/icon-192.png            App-Symbol (PWA)
    frontend/public/icons/icon-512.png            App-Symbol groß
    frontend/public/icons/icon-maskable-512.png   Android (Ecken werden beschnitten)
    frontend/public/icons/apple-touch-icon.png    iPhone/iPad
    frontend/public/icons/icon-dunkel-512.png     Fassung für dunkle Flächen
    frontend/src/app/favicon.ico                  Symbol im Fenstertitel
    desktop/hpp-app.ico                           Symbol des Windows-Programms

FARBEN WIE IM LOGO
==================
Dunkle Wortmarke auf Weiß — genau die Fassung aus dem Briefkopf. Eine blaue
Kachel mit weißer Marke wäre ein eigener Entwurf und nicht das Logo; die
Akzentfarbe der App gehört in die Oberfläche, nicht ins Firmenzeichen. Für
dunkle Untergründe gibt es ``icon-dunkel-512.png`` mit vertauschten Rollen.

WARUM JEDE ICO-GRÖSSE EINZELN GEZEICHNET WIRD
=============================================
Ein 256er Bild einfach auf 16 px herunterzurechnen ergibt einen grauen Fleck:
Die Wortmarke hat drei Buchstaben, deren Striche bei 16 px unter ein Pixel
fallen. Deshalb bekommt jede Größe ihren eigenen Anteil (``ANTEIL_JE_KANTE``) —
klein heißt: die Marke füllt mehr Fläche, damit die Striche mindestens ein
Pixel breit bleiben. Genau das sieht man in Explorer und Taskleiste.

Und: Größen bis 48 px landen als **BMP** in der ICO, nicht als PNG. Das ist die
Fassung, die auch ältere Windows-Dialoge zuverlässig zeichnen; für 64 px und
größer ist PNG richtig, weil es die Datei klein hält.

HERKUNFT DER WORTMARKE
======================
Nachgezeichnet aus dem Logo der Word-Vorlage
(``backend/templates/Bautagesbericht_HPP_leer.docx``), wo es nur als Rasterbild
mit 205 x 80 Pixeln liegt. Verfahren: Marching Squares auf den Grauwerten, also
mit Subpixel-Genauigkeit statt harter Schwarz-Weiß-Schwelle.

LIEGT EINE ECHTE VEKTORDATEI VOR (SVG oder EPS aus dem Markenhandbuch), dann
ist der Austausch klein:
  1. ``frontend/public/marke/hpp-wortmarke.svg`` ersetzen — ein einziger
     ``<path>`` mit ``fill="currentColor"``, Koordinaten am Tintenrahmen
     ausgerichtet (kein unsichtbarer Rand).
  2. Denselben Pfad in ``frontend/src/components/HppLogo.tsx`` eintragen.
  3. Dieses Skript laufen lassen — alle Symbole entstehen neu.

Aufruf:
    python desktop/_marke-symbole-erzeugen.py
"""

from __future__ import annotations

import io
import re
import struct
from pathlib import Path

from PIL import Image, ImageDraw

PROJEKT = Path(__file__).resolve().parent.parent
MARKE = PROJEKT / "frontend" / "public" / "marke" / "hpp-wortmarke.svg"
ICONS = PROJEKT / "frontend" / "public" / "icons"
FAVICON = PROJEKT / "frontend" / "src" / "app" / "favicon.ico"
PROGRAMM_ICO = PROJEKT / "desktop" / "hpp-app.ico"

# Farben. Das Symbol trägt die Logofarben, nicht die Akzentfarbe der App.
TINTE = (0x17, 0x17, 0x17)    # --color-app-text, das Schwarz des Briefkopfs
WEISS = (0xFF, 0xFF, 0xFF)

#: Anteil der Symbolbreite, den die Wortmarke einnimmt (große Flächen).
ANTEIL = 0.60
#: Wie weit die Marke über die Mitte gehoben wird (optischer Ausgleich).
HOCH = 0.02

#: Je kleiner das Symbol, desto größer die Marke — sonst verschwinden die
#: Striche der Buchstaben unter einem Pixel.
ANTEIL_JE_KANTE = {
    16: 0.86,
    24: 0.82,
    32: 0.78,
    48: 0.70,
    64: 0.66,
    128: 0.62,
    256: 0.60,
}

#: Bis zu dieser Kante wird in der ICO BMP statt PNG abgelegt.
BMP_BIS = 48


def pfad_lesen() -> tuple[list[list[tuple[float, float]]], float, float]:
    """Liest Ringe, Breite und Höhe aus der SVG-Markendatei."""
    text = MARKE.read_text(encoding="utf-8")

    kasten = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', text)
    if not kasten:
        raise SystemExit(f"Kein viewBox in {MARKE}")
    breite, hoehe = float(kasten.group(1)), float(kasten.group(2))

    daten = re.search(r'\sd="([^"]+)"', text)
    if not daten:
        raise SystemExit(f"Kein Pfad in {MARKE}")

    ringe = []
    for teil in daten.group(1).split("M")[1:]:
        zahlen = [float(z) for z in re.findall(r"-?\d+\.?\d*", teil)]
        punkte = list(zip(zahlen[0::2], zahlen[1::2]))
        if len(punkte) > 2:
            ringe.append(punkte)
    return ringe, breite, hoehe


def fuellen(bild: Image.Image, ringe, faktor: float, dx: float, dy: float, farbe):
    """Füllt die Ringe nach der Even-Odd-Regel — Löcher bleiben Löcher."""
    maske = Image.new("L", bild.size, 0)
    ziel = maske.load()
    for ring in ringe:
        einzel = Image.new("L", bild.size, 0)
        ImageDraw.Draw(einzel).polygon(
            [(x * faktor + dx, y * faktor + dy) for x, y in ring], fill=255
        )
        quelle = einzel.load()
        for y in range(bild.height):
            for x in range(bild.width):
                if quelle[x, y]:
                    ziel[x, y] = 0 if ziel[x, y] else 255
    bild.paste(Image.new("RGB", bild.size, farbe), (0, 0), maske)


def symbol(kante: int, ringe, breite, hoehe, *, hintergrund, tinte,
           anteil=ANTEIL) -> Image.Image:
    """Quadratisches Symbol mit zentrierter Wortmarke.

    Gezeichnet wird in vierfacher Größe und dann verkleinert — das ergibt
    weiche Kanten, ohne eine Zeichenbibliothek mit Kantenglättung zu brauchen.
    """
    faktor = (kante * anteil) / breite
    dx = (kante - breite * faktor) / 2
    dy = (kante - hoehe * faktor) / 2 - kante * HOCH

    gross = Image.new("RGB", (kante * 4, kante * 4), hintergrund)
    fuellen(gross, ringe, faktor * 4, dx * 4, dy * 4, tinte)
    return gross.resize((kante, kante), Image.LANCZOS)


def als_bmp(bild: Image.Image) -> bytes:
    """Ein ICO-Eintrag als 32-Bit-BMP: Kopf, BGRA von unten nach oben, Maske.

    Der Kopf trägt die doppelte Höhe — so schreibt es das ICO-Format vor, weil
    hinter den Farbwerten noch die 1-Bit-Maske steht. Unsere Symbole sind
    vollflächig deckend, die Maske ist also überall null.
    """
    breite, hoehe = bild.size
    bild = bild.convert("RGBA")
    punkte = bild.load()

    kopf = struct.pack(
        "<IiiHHIIiiII",
        40,             # biSize
        breite,         # biWidth
        hoehe * 2,      # biHeight — Farbwerte plus Maske
        1,              # biPlanes
        32,             # biBitCount
        0,              # biCompression = BI_RGB
        breite * hoehe * 4,
        0, 0, 0, 0,
    )

    farben = bytearray()
    for y in range(hoehe - 1, -1, -1):       # BMP steht auf dem Kopf
        for x in range(breite):
            r, g, b, a = punkte[x, y]
            farben += bytes((b, g, r, a))    # BGRA

    zeile = ((breite + 31) // 32) * 4        # 1 Bit je Punkt, auf 4 Byte
    maske = bytes(zeile * hoehe)
    return kopf + bytes(farben) + maske


def als_png(bild: Image.Image) -> bytes:
    puffer = io.BytesIO()
    bild.convert("RGBA").save(puffer, format="PNG", optimize=True)
    return puffer.getvalue()


def ico_schreiben(pfad: Path, bilder: list[tuple[int, Image.Image]]) -> None:
    """Schreibt eine ICO-Datei aus einzeln gezeichneten Größen."""
    bloecke = [
        (kante, als_bmp(bild) if kante <= BMP_BIS else als_png(bild))
        for kante, bild in sorted(bilder)
    ]

    kopf = struct.pack("<HHH", 0, 1, len(bloecke))
    versatz = len(kopf) + 16 * len(bloecke)

    verzeichnis = bytearray()
    for kante, block in bloecke:
        verzeichnis += struct.pack(
            "<BBBBHHII",
            0 if kante >= 256 else kante,   # 0 heißt 256
            0 if kante >= 256 else kante,
            0,                              # Farbpalette: keine
            0,                              # reserviert
            1,                              # Ebenen
            32,                             # Bit je Punkt
            len(block),
            versatz,
        )
        versatz += len(block)

    pfad.write_bytes(kopf + bytes(verzeichnis) + b"".join(b for _, b in bloecke))


def main() -> None:
    ringe, breite, hoehe = pfad_lesen()
    print(f"Wortmarke: {breite} x {hoehe} Einheiten, {len(ringe)} Ringe")
    print(f"Quelle:    {MARKE.relative_to(PROJEKT)}\n")

    ICONS.mkdir(parents=True, exist_ok=True)
    symbol(192, ringe, breite, hoehe, hintergrund=WEISS, tinte=TINTE).save(
        ICONS / "icon-192.png")
    symbol(512, ringe, breite, hoehe, hintergrund=WEISS, tinte=TINTE).save(
        ICONS / "icon-512.png")
    symbol(180, ringe, breite, hoehe, hintergrund=WEISS, tinte=TINTE).save(
        ICONS / "apple-touch-icon.png")
    # Maskable: Android beschneidet die Ecken rund, deshalb deutlich mehr Luft.
    symbol(512, ringe, breite, hoehe, hintergrund=WEISS, tinte=TINTE,
           anteil=0.46).save(ICONS / "icon-maskable-512.png")
    # Für dunkle Flächen: Rollen vertauscht, gleiche Marke.
    symbol(512, ringe, breite, hoehe, hintergrund=TINTE, tinte=WEISS).save(
        ICONS / "icon-dunkel-512.png")
    # Die frühere blaue Fassung nicht liegen lassen — sonst liefert das Paket
    # zwei Wahrheiten aus.
    alt = ICONS / "icon-hell-512.png"
    if alt.exists():
        alt.unlink()

    # Jede ICO-Größe einzeln zeichnen, damit die Buchstaben auch bei 16 px
    # noch Striche haben und keinen Fleck.
    stufen = [
        (kante, symbol(kante, ringe, breite, hoehe, hintergrund=WEISS, tinte=TINTE,
                       anteil=ANTEIL_JE_KANTE[kante]))
        for kante in sorted(ANTEIL_JE_KANTE)
    ]
    ico_schreiben(PROGRAMM_ICO, stufen)
    ico_schreiben(FAVICON, stufen)

    for pfad in sorted(ICONS.iterdir()):
        print(f"  {pfad.relative_to(PROJEKT)}")
    for pfad in (PROGRAMM_ICO, FAVICON):
        groessen = ", ".join(f"{k}" for k, _ in stufen)
        print(f"  {pfad.relative_to(PROJEKT)}  ({groessen} px, "
              f"{pfad.stat().st_size:,} Bytes)")


if __name__ == "__main__":
    main()
