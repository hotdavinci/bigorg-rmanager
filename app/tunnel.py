"""Quick Cloudflare Tunnel lifecycle for a local-only installation."""
import asyncio
import re
import subprocess
from pathlib import Path

from .config import settings
from .media_gateway import register_media

_url_pattern = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com", re.IGNORECASE)


class QuickTunnel:
    def __init__(self) -> None:
        self.process: asyncio.subprocess.Process | None = None
        self.url = ""
        self.error = ""
        self._ready = asyncio.Event()
        self._reader_task: asyncio.Task | None = None

    @property
    def executable(self) -> Path:
        return Path(settings.cloudflared_path)

    async def start(self) -> None:
        # A VPS usa um Tunnel nomeado, com endere\u00e7o HTTPS est\u00e1vel. Nessa
        # modalidade o servi\u00e7o cloudflared \u00e9 gerenciado pelo systemd.
        if settings.public_media_base_url.strip():
            self.url = settings.public_media_base_url.strip().rstrip("/")
            self.error = ""
            self._ready.set()
            return
        if self.process and self.process.returncode is None:
            return
        self.url = ""
        self.error = ""
        self._ready.clear()
        if not self.executable.is_file():
            self.error = "cloudflared.exe não foi encontrado. Execute Preparar Reels Manager.bat ou reinstale o conector."
            return
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = await asyncio.create_subprocess_exec(
            str(self.executable), "tunnel", "--url", f"http://127.0.0.1:{settings.tunnel_media_port}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            creationflags=flags,
        )
        self._reader_task = asyncio.create_task(self._read_output())

    async def _read_output(self) -> None:
        assert self.process and self.process.stdout
        async for raw in self.process.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            found = _url_pattern.search(line)
            if found:
                self.url = found.group(0)
                self._ready.set()
        if not self.url and not self.error:
            self.error = "O Cloudflare Tunnel encerrou antes de criar a URL pública."
        self._ready.set()

    async def public_url_for(self, path: Path) -> str:
        await self.start()
        if not self.url:
            try:
                await asyncio.wait_for(self._ready.wait(), timeout=45)
            except TimeoutError:
                self.error = "O Cloudflare Tunnel demorou demais para iniciar."
        if not self.url:
            raise RuntimeError(self.error or "Não foi possível obter a URL pública temporária do Cloudflare.")
        return f"{self.url}/media/{register_media(path)}"

    async def stop(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except TimeoutError:
                self.process.kill()
        if self._reader_task:
            self._reader_task.cancel()

    def status(self) -> dict:
        if settings.public_media_base_url.strip():
            return {"active": True, "url": settings.public_media_base_url.strip().rstrip("/"), "error": ""}
        active = bool(self.process and self.process.returncode is None)
        return {"active": active and bool(self.url), "url": self.url, "error": self.error}


tunnel = QuickTunnel()
