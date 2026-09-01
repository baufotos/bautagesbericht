"""OCR-Modul (Platzhalter).

Die frühere Fassung nutzte EasyOCR/PyMuPDF für lokale Texterkennung von
Scan-PDFs. Für den Server-Betrieb wurde das entfernt: EasyOCR lädt ~1 GB
Modelldaten und passt nicht in die freie Speicherstufe von Render/Fly.
Scans werden jetzt ausschließlich über die Claude-Vision-API extrahiert
(siehe ``pdf_extraction._extract_scan_via_claude``).

Falls ``pdf_extraction`` doch eine der Funktionen hier aufruft, geben wir
ein leeres Ergebnis zurück, damit die Pipeline mit einer klaren Warnung
statt einem Absturz endet.
"""

from __future__ import annotations

from pathlib import Path


def ocr_pdf(file_path: Path) -> str:  # pragma: no cover - Fallback
    return ""


def ocr_image(file_path: Path) -> str:  # pragma: no cover - Fallback
    return ""
