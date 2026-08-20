import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    app_encryption_key: str = ""
    meta_app_id: str = ""
    meta_instagram_app_id: str = ""
    meta_instagram_app_secret: str = ""
    meta_app_secret: str = ""
    meta_redirect_uri: str = "http://localhost:8000/api/meta/oauth/callback"
    meta_graph_api_version: str = ""
    meta_oauth_authorize_url: str = "https://www.instagram.com/oauth/authorize"
    meta_oauth_token_url: str = "https://api.instagram.com/oauth/access_token"
    meta_graph_base_url: str = "https://graph.instagram.com"
    python_executable: str = "python"
    processing_timeout_seconds: int = 1800
    # Um lote reduz a quantidade de inícios do Python/ffmpeg, sem encher o disco
    # com a campanha inteira de uma vez. Pode ser ajustado no .env da VPS.
    processing_batch_size: int = 12
    # Processamento e publicação usam filas separadas. Publicar poucos itens em
    # paralelo evita sobrecarregar a VPS e respeita a latência da Meta.
    scheduler_poll_seconds: int = 5
    scheduler_parallelism: int = 2
    scheduler_max_attempts: int = 3
    scheduler_claim_timeout_seconds: int = 900
    insights_sync_hours: int = 6
    insights_reels_limit: int = 100
    admin_email: str = "hotdavinci@gmail.com"
    admin_password: str = ""
    campaign_cover_path: str = ""
    cloudflared_path: str = str(ROOT / "tools" / ("cloudflared.exe" if os.name == "nt" else "cloudflared"))
    tunnel_media_port: int = 8001
    # Em produ\u00e7\u00e3o, a URL fixa do host media do Cloudflare Tunnel.
    # Vazia = usa o Quick Tunnel local, apenas para testes.
    public_media_base_url: str = ""
    # Origens do painel web permitidas a chamar esta API. Use dom\u00ednios completos,
    # separados por v\u00edrgula; nunca use "*" em produ\u00e7\u00e3o.
    cors_allowed_origins: str = "http://127.0.0.1:8000,http://localhost:8000"
    session_https_only: bool = False
    database_url: str = f"sqlite:///{ROOT / 'data' / 'app.db'}"
    @property
    def data_dir(self) -> Path: return ROOT / "data"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_allowed_origins.split(",") if origin.strip()]
settings = Settings()

def data_path(relative_path: str | Path) -> Path:
    """Resolve data paths created on either Windows or Linux."""
    return settings.data_dir / Path(str(relative_path).replace("\\", "/"))

def reload_runtime_settings() -> None:
    """Rele o .env sem interromper o servidor local."""
    updated = Settings()
    for field in ("app_encryption_key", "meta_app_id", "meta_instagram_app_id", "meta_instagram_app_secret", "meta_app_secret", "meta_redirect_uri", "meta_graph_api_version", "meta_oauth_authorize_url", "meta_oauth_token_url", "meta_graph_base_url", "python_executable", "processing_timeout_seconds", "processing_batch_size", "scheduler_poll_seconds", "scheduler_parallelism", "scheduler_max_attempts", "scheduler_claim_timeout_seconds", "insights_sync_hours", "insights_reels_limit", "admin_email", "admin_password", "campaign_cover_path", "cloudflared_path", "tunnel_media_port", "public_media_base_url", "cors_allowed_origins", "session_https_only"):
        setattr(settings, field, getattr(updated, field))
