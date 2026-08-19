from pathlib import Path

from fastapi import UploadFile

from app.config import settings


async def save_upload(einreichung_id: int, file: UploadFile) -> str:
    dest_dir = settings.upload_dir / str(einreichung_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename).name if file.filename else f"upload_{id(file)}"
    dest = dest_dir / safe_name
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{dest.stem}_{counter}{dest.suffix}"
        counter += 1
    content = await file.read()
    dest.write_bytes(content)
    return str(dest.relative_to(settings.upload_dir.parent))


def get_absolute_path(relative_path: str) -> Path:
    return settings.upload_dir.parent / relative_path
