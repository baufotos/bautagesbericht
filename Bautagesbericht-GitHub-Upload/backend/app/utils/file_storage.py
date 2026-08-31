from pathlib import Path

from fastapi import UploadFile

from app.config import settings


def _eindeutiger_pfad(dest_dir: Path, dateiname: str) -> Path:
    """Zielpfad, der eine bestehende Datei nicht überschreibt."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / dateiname
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{dest.stem}_{counter}{dest.suffix}"
        counter += 1
    return dest


async def save_upload(einreichung_id: int, file: UploadFile) -> str:
    dest_dir = settings.upload_dir / str(einreichung_id)
    safe_name = Path(file.filename).name if file.filename else f"upload_{id(file)}"
    dest = _eindeutiger_pfad(dest_dir, safe_name)
    content = await file.read()
    dest.write_bytes(content)
    return str(dest.relative_to(settings.upload_dir.parent))


async def save_upload_in(unterordner: str, file: UploadFile,
                         inhalt: bytes | None = None) -> str:
    """Speichert einen Upload in einem beliebigen Unterordner des Upload-Verzeichnisses.

    Wird vom Mängelmanagement genutzt (``maengel/<id>/fotos``,
    ``maengel/<id>/dateien``, ``plaene/<projekt_id>``). ``inhalt`` erlaubt es,
    bereits verarbeitete Bytes zu schreiben (z. B. das serverseitig
    verkleinerte Foto) statt der Rohdatei.

    Gibt den Pfad relativ zum Storage-Wurzelverzeichnis zurück — genauso wie
    ``save_upload``, damit ``get_absolute_path`` für beide passt.
    """
    dest_dir = settings.upload_dir / unterordner
    safe_name = Path(file.filename).name if file.filename else f"upload_{id(file)}"
    dest = _eindeutiger_pfad(dest_dir, safe_name)
    content = inhalt if inhalt is not None else await file.read()
    dest.write_bytes(content)
    return str(dest.relative_to(settings.upload_dir.parent))


def get_absolute_path(relative_path: str) -> Path:
    return settings.upload_dir.parent / relative_path
