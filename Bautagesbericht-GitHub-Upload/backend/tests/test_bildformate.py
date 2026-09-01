"""Prueft, dass jedes hochgeladene Foto als JPEG herauskommt.

Der Anlass: iPhones fotografieren in HEIC. Pillow kennt das Format nicht von
sich aus — ohne pillow-heif landete so eine Datei unveraendert im
Projektordner, und im Word-Dokument tauchte sie gar nicht auf. Hier wird
geprueft, dass aus jedem gaengigen Format ein JPEG wird.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ARBEIT = Path(tempfile.gettempdir()) / "hpp-test-bildformate"
ARBEIT.mkdir(exist_ok=True)
os.environ.setdefault("BTB_OUTPUT_DIR", str(ARBEIT / "output"))
os.environ.setdefault("BTB_UPLOAD_DIR", str(ARBEIT / "uploads"))
os.environ.setdefault("BTB_DATABASE_URL", f"sqlite:///{(ARBEIT / 'x.db').as_posix()}")

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from PIL import Image  # noqa: E402

from app.services import baufotos as bf  # noqa: E402
from app.services import bilder, bildformate  # noqa: E402

ok = 0
fehler: list[str] = []


def pruefe(bedingung, text):
    global ok
    if bedingung:
        ok += 1
    else:
        fehler.append(text)


def gleich(ist, soll, text):
    pruefe(ist == soll, f"{text}: erwartet {soll!r}, war {ist!r}")


def als_bytes(format_name: str, groesse=(1800, 1200), modus="RGB", **opt) -> bytes:
    bild = Image.new(modus, groesse, (90, 120, 160) if modus != "L" else 128)
    puffer = io.BytesIO()
    bild.save(puffer, format=format_name, **opt)
    return puffer.getvalue()


def ist_jpeg(daten: bytes) -> bool:
    try:
        with Image.open(io.BytesIO(daten)) as bild:
            return bild.format == "JPEG"
    except Exception:
        return False


print("─── Welche Formate angenommen werden ───")

for endung in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif",
               ".tiff", ".heic", ".heif", ".avif"):
    pruefe(bildformate.ist_bilddatei("foto" + endung), f"{endung} ist erlaubt")
    pruefe(bf.ist_erlaubte_datei("foto" + endung),
           f"{endung} auch beim Baufoto-Upload")

pruefe(not bildformate.ist_bilddatei("bericht.pdf"), "PDF ist kein Foto")
pruefe(not bildformate.ist_bilddatei("liste.docx"), "Word ist kein Foto")
gleich(bildformate.als_jpeg_name("IMG_4711.HEIC"), "IMG_4711.jpg",
       "Ausgabename bekommt .jpg")
gleich(bildformate.als_jpeg_name("foto.mit.punkten.png"), "foto.mit.punkten.jpg",
       "Punkte im Namen bleiben erhalten")


print("─── Aus jedem Format wird ein JPEG ───")

for name, daten in [
    ("PNG", als_bytes("PNG")),
    ("BMP", als_bytes("BMP")),
    ("TIFF", als_bytes("TIFF")),
    ("WEBP", als_bytes("WEBP")),
    ("GIF", als_bytes("GIF", modus="P")),
    ("Graustufen-JPEG", als_bytes("JPEG", modus="L")),
]:
    inhalt, als_jpeg = bf.verkleinere(daten)
    pruefe(als_jpeg, f"{name}: umgewandelt")
    pruefe(ist_jpeg(inhalt), f"{name}: Ergebnis ist wirklich ein JPEG")


print("─── HEIC vom iPhone ───")

heic_moeglich = bildformate.heic_moeglich()
print(f"   HEIC lesbar: {heic_moeglich}")

if not heic_moeglich:
    fehler.append("pillow-heif fehlt — HEIC-Fotos kaemen unverarbeitet an")
else:
    ok += 1
    heic = als_bytes("HEIF", quality=80)
    pruefe(len(heic) > 0, "HEIC-Testdatei erzeugt")

    inhalt, als_jpeg = bf.verkleinere(heic)
    pruefe(als_jpeg, "HEIC wurde umgewandelt")
    pruefe(ist_jpeg(inhalt), "aus HEIC wird ein JPEG")

    with Image.open(io.BytesIO(inhalt)) as bild:
        pruefe(max(bild.size) <= bf.MAX_KANTE,
               f"auch verkleinert (war {bild.size})")

    # Derselbe Weg fuer Maengel- und Berichtsfotos.
    daten, name = bilder.normalisiere_foto(heic, "IMG_4711.HEIC")
    gleich(name, "IMG_4711.jpg", "Maengelfoto bekommt .jpg")
    pruefe(ist_jpeg(daten), "und ist wirklich ein JPEG")


print("─── Transparenz wird nicht schwarz ───")

# Ein PNG mit durchsichtigem Hintergrund: ohne Behandlung wird die
# Transparenz beim Umwandeln schwarz und das Bild ein dunkler Klotz.
durchsichtig = Image.new("RGBA", (600, 400), (255, 0, 0, 0))
puffer = io.BytesIO()
durchsichtig.save(puffer, format="PNG")

inhalt, als_jpeg = bf.verkleinere(puffer.getvalue())
pruefe(als_jpeg, "PNG mit Alpha umgewandelt")
with Image.open(io.BytesIO(inhalt)) as bild:
    ecke = bild.convert("RGB").getpixel((5, 5))
    pruefe(min(ecke) > 200,
           f"durchsichtige Flaeche wurde weiss, nicht schwarz (war {ecke})")


print("─── Kaputte Datei geht nicht verloren ───")

kaputt = b"das ist kein Bild"
inhalt, als_jpeg = bf.verkleinere(kaputt)
pruefe(not als_jpeg, "unlesbare Datei wird als solche gemeldet")
gleich(inhalt, kaputt, "und die Originaldaten bleiben erhalten")

daten, name = bilder.normalisiere_foto(kaputt, "kaputt.png")
gleich(name, "kaputt.png", "Name bleibt, wenn nichts umgewandelt wurde")

print()
if fehler:
    print(f"{ok} Pruefungen ok, {len(fehler)} Fehler:")
    for f in fehler:
        print("  -", f)
    raise SystemExit(1)
print(f"{ok} Pruefungen ok, 0 Fehler")
