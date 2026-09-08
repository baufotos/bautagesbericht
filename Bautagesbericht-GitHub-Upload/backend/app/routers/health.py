"""Auskunft über den Zustand des Dienstes.

``/health`` ist knapp, weil Render es zum Aufwecken benutzt. ``/health/speicher``
beantwortet die eine Frage, die man von außen sonst nicht klären kann: Wo
liegen die hochgeladenen Fotos gerade, und übersteht das einen Neustart?
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import fotospeicher

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/speicher")
def speicher(db: Session = Depends(get_db)):
    """Wo die Fotos liegen und wie viel Platz sie belegen.

    Gebraucht beim Einrichten: Auf einem Server mit flüchtigem Dateisystem
    muss hier ``dauerhaft: true`` stehen — sonst sind über Nacht hochgeladene
    Fotos am Morgen verschwunden.
    """
    art = fotospeicher.art()
    belegt = fotospeicher.belegung_bytes(db)
    return {
        "art": art,
        "dauerhaft": art in ("db", "objekt"),
        "belegt_bytes": belegt,
        "belegt_mb": round(belegt / (1024 * 1024), 1),
        "erklaerung": fotospeicher.beschreibung(),
    }


@router.get("/health/dokumente")
def dokumente():
    """Womit dieser Dienst Dokumente ausgibt und Scans liest.

    Beim Einrichten die schnellste Antwort auf die zwei Fragen, die sich von
    außen sonst nicht klären lassen, ohne erst Daten anzulegen:

      - Funktioniert „Als PDF"? Auf dem Bürorechner über Word, auf dem
        Server über LibreOffice — steht keins von beidem bereit, gibt es
        nur das Word-Dokument (siehe ``app.services.word_pdf``).
      - Wird ein hochgeladener Scan überhaupt gelesen? Im Linux-Container
        gibt es keine Windows-Texterkennung; ohne Anthropic-Schlüssel bleibt
        dort gar kein Weg (siehe ``services/pdf_extraction``).

    Bewusst unter ``/health``: Diese Auskunft ist vom Seiten-Passwort
    ausgenommen und damit auch dann abrufbar, wenn beim Einrichten noch
    niemand angemeldet ist. Sie verrät nichts über Projekte oder Daten —
    nur, was der Rechner kann.
    """
    import os
    from pathlib import Path

    from app.services import word_pdf
    from app.services.pdf_extraction import erkennung_beschreibung

    scan_moeglich, scan_hinweis = erkennung_beschreibung()

    # Der Umfang steckt im JavaScript-Bündel und wird beim BAUEN eingesetzt.
    # Die Datei schreibt die Dockerfile in genau dem Lauf, der auch das Bündel
    # erzeugt hat — sie kann also nicht lügen. Die Umgebungsvariable dagegen
    # schon: Ändert man sie bei Render allein am Dienst, wird nur neu
    # gestartet, nicht neu gebaut.
    gebaut = ""
    quelle = Path("/app/umfang-beim-bauen.txt")
    try:
        gebaut = quelle.read_text(encoding="utf-8").strip()
    except OSError:
        pass                       # Windows-Paket, lokale Entwicklung

    laufzeit = (os.environ.get("APP_UMFANG") or "").strip()
    umfang = gebaut or laufzeit or "voll"

    antwort = {
        "umfang": umfang,
        "pdf_moeglich": word_pdf.pdf_moeglich(),
        "pdf_weg": word_pdf.pdf_weg(),
        "scan_erkennung": scan_moeglich,
        "scan_hinweis": scan_hinweis,
    }

    if gebaut and laufzeit and gebaut != laufzeit:
        antwort["warnung"] = (
            f"Die Oberfläche wurde mit APP_UMFANG={gebaut} gebaut, am Dienst "
            f"steht inzwischen {laufzeit}. Eine geänderte Umgebungsvariable "
            "allein startet den Dienst nur neu — das Bündel bleibt, wie es "
            "war. Ein neues Deploy (Push oder „Clear build cache & deploy“) "
            "bringt beide wieder zusammen."
        )
    return antwort
