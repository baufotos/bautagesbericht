"""PDF-Seiten rendern, ohne den Speicher volllaufen zu lassen.

WARUM DIESE REIHE
=================
``pypdfium2`` haelt jede ueber ``dokument[i]`` geoeffnete Seite bis zum
``dokument.close()`` im Speicher. Vier Stellen im Backend haben in einer
Schleife gerendert und dabei das ganze Dokument angesammelt — bei 300 dpi
sind das 12 MB je Blatt.

Aufgefallen ist es an der Wochenanalyse ("Tage erkennen"): Auf Render hat der
Container 512 MB, darin laeuft neben dem Backend auch Next.js. Bei
``seitenlesung.MAX_SEITEN`` = 40 Seiten brauchte der alte Weg gemessene
690 MB — der Speicherwaechter raeumte uvicorn ab, Next.js lief weiter und
beantwortete jeden ``/api``-Aufruf mit seinem eigenen "Internal Server Error".

Der Speicher ist deshalb hier eine ZUGESICHERTE EIGENSCHAFT und keine
Feinheit: Die Reihe prueft nicht nur, dass richtig gerendert wird, sondern
auch, dass der Verbrauch nicht mit der Seitenzahl waechst.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from io import BytesIO
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STORAGE = Path(tempfile.gettempdir()) / "hpp-test-pdf-seiten"
if STORAGE.exists():
    shutil.rmtree(STORAGE)
STORAGE.mkdir(parents=True)

WIN = str(STORAGE).replace("\\", "/")
os.environ["BTB_DATABASE_URL"] = f"sqlite:///{WIN}/test.db"
os.environ["BTB_UPLOAD_DIR"] = f"{WIN}/uploads"
os.environ["BTB_OUTPUT_DIR"] = f"{WIN}/output"

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from PIL import Image, ImageDraw  # noqa: E402

from app.services import pdf_seiten, seitenlesung  # noqa: E402

ok = 0
fehler: list[str] = []


def pruefe(bedingung, text):
    global ok
    if bedingung:
        ok += 1
    else:
        fehler.append(text)


def gleich(ist, soll, text):
    pruefe(ist == soll, f"{text}: {ist!r} statt {soll!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Speicher des eigenen Prozesses — auf Windows wie auf Linux
# ─────────────────────────────────────────────────────────────────────────────


def _speicher_mb():
    """Belegter Arbeitsspeicher in MB, oder ``None`` wenn nicht messbar.

    Zwei Wege, weil die Reihe auf dem Buerorechner (Windows) und im
    Linux-Container laufen soll. Ist keiner verfuegbar, entfaellt die
    Speicherpruefung — der Rest der Reihe laeuft trotzdem.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            kernel = ctypes.windll.kernel32
            kernel.GetCurrentProcess.restype = ctypes.c_void_p
            psapi = ctypes.windll.psapi
            psapi.GetProcessMemoryInfo.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(PMC), wintypes.DWORD]
            angabe = PMC()
            angabe.cb = ctypes.sizeof(PMC)
            geholt = psapi.GetProcessMemoryInfo(
                kernel.GetCurrentProcess(), ctypes.byref(angabe), angabe.cb)
            if not geholt:
                return None
            return angabe.WorkingSetSize / 1e6
        except Exception:
            return None
    try:
        with open("/proc/self/statm", encoding="ascii") as datei:
            seitenzahl = int(datei.read().split()[1])
        return seitenzahl * os.sysconf("SC_PAGE_SIZE") / 1e6
    except Exception:
        return None


def scan_pdf(ziel: Path, seiten: int) -> Path:
    """Ein PDF, in dem jede Seite ein Bild ist — wie ein Buero-Scan.

    Bewusst mit Linien und Raster: Eine weisse Seite haette kaum JPEG-Daten
    und der Speicherverlauf waere nicht aussagekraeftig.
    """
    def blatt(nummer: int):
        bild = Image.new("RGB", (1654, 2339), "white")
        stift = ImageDraw.Draw(bild)
        stift.text((120, 150), f"Bautagesbericht Seite {nummer}", fill="black")
        stift.text((120, 260), f"Datum: {(nummer % 28) + 1:02d}.01.2024",
                   fill="black")
        for y in range(400, 2200, 60):
            stift.line((120, y, 1500, y), fill=(180, 180, 180))
        for x in range(120, 1500, 140):
            stift.line((x, 400, x, 2200), fill=(210, 210, 210))
        return bild

    blaetter = [blatt(i + 1) for i in range(seiten)]
    blaetter[0].save(ziel, save_all=True, append_images=blaetter[1:],
                     resolution=200.0)
    return ziel


ARBEIT = STORAGE / "arbeit"
ARBEIT.mkdir()

print("─── Seiten kommen vollstaendig und in der richtigen Reihenfolge ───")

sechs = scan_pdf(ARBEIT / "sechs.pdf", 6)
gleich(pdf_seiten.seitenzahl(sechs), 6, "seitenzahl() zaehlt richtig")

geholt = list(pdf_seiten.seiten(sechs, dpi=100))
gleich(len(geholt), 6, "alle sechs Seiten gerendert")
gleich([n for n, _ in geholt], [0, 1, 2, 3, 4, 5],
       "Nummern sind nullbasiert und aufsteigend")
pruefe(all(bild.size[0] > 0 and bild.size[1] > 0 for _, bild in geholt),
       "jede Seite hat eine Groesse")

grob = list(pdf_seiten.seiten(sechs, dpi=50))
pruefe(grob[0][1].size[0] < geholt[0][1].size[0],
       "kleinere dpi ergeben ein kleineres Bild")

print("─── Obergrenze und Auswahl einzelner Seiten ───")

gleich(len(list(pdf_seiten.seiten(sechs, dpi=50, max_seiten=2))), 2,
       "max_seiten begrenzt")
gleich([n for n, _ in pdf_seiten.seiten(sechs, dpi=50, nummern=[1, 3, 5])],
       [1, 3, 5], "nummern waehlt genau diese Seiten")
gleich([n for n, _ in pdf_seiten.seiten(sechs, dpi=50, nummern=[4, 99, -1])],
       [4], "Nummern ausserhalb des Dokuments werden uebergangen")
gleich(list(pdf_seiten.seiten(sechs, dpi=50, nummern=[])), [],
       "leere Auswahl ergibt nichts")

# Das ist der Fehler, der in _seiten_per_ocr steckte: Wird eine Seite
# uebergangen, darf sich die Zuordnung Nummer -> Text nicht verschieben.
# Deshalb liefert seiten() die Dokumentnummer mit und nicht bloss das Bild.
paare = list(pdf_seiten.seiten(sechs, dpi=50, nummern=[0, 42, 2]))
gleich([n for n, _ in paare], [0, 2],
       "die mitgelieferte Nummer bleibt die des Dokuments")

print("─── Was nicht zu lesen ist, wirft nicht ───")

kaputt = ARBEIT / "kaputt.pdf"
kaputt.write_bytes(b"das ist kein PDF")
gleich(list(pdf_seiten.seiten(kaputt)), [], "kaputte Datei ergibt nichts")
gleich(pdf_seiten.seitenzahl(kaputt), 0, "und die Seitenzahl 0")

fehlt = ARBEIT / "gibtesnicht.pdf"
gleich(list(pdf_seiten.seiten(fehlt)), [], "fehlende Datei ergibt nichts")
gleich(pdf_seiten.seitenzahl(fehlt), 0, "fehlende Datei hat 0 Seiten")

leer = ARBEIT / "leer.pdf"
leer.write_bytes(b"")
gleich(list(pdf_seiten.seiten(leer)), [], "leere Datei ergibt nichts")

print("─── Der Speicher waechst NICHT mit der Seitenzahl ───")

if _speicher_mb() is None:
    print("   (auf diesem System nicht messbar — Pruefung entfaellt)")
else:
    # Gemessen wird der Zuwachs beim Rendern. Entscheidend ist nicht der
    # absolute Wert, sondern dass 32 Seiten nicht deutlich mehr kosten als 4:
    # genau daran ist der alte Weg gescheitert.
    def zuwachs(seitenzahl: int) -> float:
        pfad = scan_pdf(ARBEIT / f"speicher_{seitenzahl}.pdf", seitenzahl)
        vorher = _speicher_mb()
        hoechst = vorher
        for _, bild in pdf_seiten.seiten(pfad, dpi=300):
            bild.convert("L")          # etwas tun, wie ein echter Aufrufer
            gemessen = _speicher_mb()
            if gemessen is not None and gemessen > hoechst:
                hoechst = gemessen
        return hoechst - vorher

    klein = zuwachs(4)
    gross = zuwachs(32)
    print(f"   4 Seiten: +{klein:.0f} MB     32 Seiten: +{gross:.0f} MB")

    # Achtfache Seitenzahl. Der alte Weg brauchte dafuer achtfach so viel;
    # 60 MB Spielraum lassen Messrauschen und die Bildpuffer des Aufrufers zu.
    pruefe(gross < klein + 60,
           f"32 Seiten brauchen nicht mehr Speicher als 4 "
           f"(+{klein:.0f} MB gegen +{gross:.0f} MB)")

print("─── seitenlesung baut daraus unveraenderte Seitenbilder ───")

zwei = scan_pdf(ARBEIT / "zwei.pdf", 2)
bilder = seitenlesung._seitenbilder(zwei)
gleich(len(bilder), 2, "beide Seiten aufbereitet")
for nummer, seitenbild in enumerate(bilder, start=1):
    pruefe(seitenbild.uebersicht[:2] == b"\xff\xd8",
           f"Seite {nummer}: Uebersicht ist ein JPEG")
    gleich(len(seitenbild.ausschnitte), 2,
           f"Seite {nummer}: zwei Ausschnitte")
    lange_kante = max(Image.open(BytesIO(seitenbild.uebersicht)).size)
    gleich(lange_kante, seitenlesung.MAX_KANTE,
           f"Seite {nummer}: Uebersicht nutzt MAX_KANTE aus")
    for teil in seitenbild.ausschnitte:
        gleich(max(Image.open(BytesIO(teil)).size), seitenlesung.MAX_KANTE,
               f"Seite {nummer}: Ausschnitt nutzt MAX_KANTE aus")

# Die Ausschnitte muessen sich unterscheiden — sonst waere der zweite
# Durchgang wertlos, und genau das passiert, wenn Bildpuffer zu frueh
# freigegeben werden und alle Seiten denselben Inhalt zeigen.
pruefe(bilder[0].ausschnitte[0] != bilder[0].ausschnitte[1],
       "obere und untere Haelfte sind verschieden")
pruefe(bilder[0].uebersicht != bilder[1].uebersicht,
       "verschiedene Seiten ergeben verschiedene Bilder")

# Ein Blatt, das fast quadratisch ist, gewinnt durch das Teilen nichts.
quadrat = Image.new("RGB", (1000, 1020), "white")
gleich(seitenlesung._ausschnitte(quadrat), [],
       "fast quadratisches Blatt bekommt keine Ausschnitte")

print()
if fehler:
    print(f"{ok} Pruefungen ok, {len(fehler)} Fehler:")
    for eintrag in fehler:
        print("  -", eintrag)
    raise SystemExit(1)
print(f"{ok} Pruefungen ok, 0 Fehler")
