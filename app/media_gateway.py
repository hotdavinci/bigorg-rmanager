"""Endpoint local, mínimo e temporário usado pela Meta para baixar um vídeo."""
from datetime import datetime, timedelta
from pathlib import Path
import secrets
import mimetypes

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

media_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_files: dict[str, tuple[Path, datetime]] = {}


def register_media(path: Path, lifetime_minutes: int = 120) -> str:
    """Return an opaque, short-lived token. Paths are never accepted from HTTP."""
    if not path.is_file():
        raise FileNotFoundError("Vídeo processado não encontrado")
    token = secrets.token_urlsafe(32)
    _files[token] = (path.resolve(), datetime.utcnow() + timedelta(minutes=lifetime_minutes))
    return token


@media_app.get("/media/{token}")
async def download_media(token: str):
    item = _files.get(token)
    if not item:
        raise HTTPException(404, "Arquivo temporário não encontrado")
    path, expires_at = item
    if expires_at <= datetime.utcnow():
        _files.pop(token, None)
        raise HTTPException(410, "Link temporário expirado")
    if not path.is_file():
        raise HTTPException(404, "Arquivo local não encontrado")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name)
