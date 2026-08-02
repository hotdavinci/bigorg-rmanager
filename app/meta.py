"""Integração do Instagram API with Instagram Login (OAuth oficial da Meta)."""
import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from cryptography.fernet import Fernet, InvalidToken
import httpx
import asyncio
from pathlib import Path
from fastapi import HTTPException
from .config import settings

SCOPES = "instagram_business_basic,instagram_business_content_publish"

def require_config() -> None:
    if not (settings.meta_instagram_app_id or settings.meta_app_id) or not (settings.meta_instagram_app_secret or settings.meta_app_secret) or not settings.meta_graph_api_version:
        raise HTTPException(503, "Preencha META_INSTAGRAM_APP_ID, META_INSTAGRAM_APP_SECRET e META_GRAPH_API_VERSION no arquivo .env")
    if not settings.app_encryption_key:
        raise HTTPException(503, "Gere a APP_ENCRYPTION_KEY com o arquivo 'Gerar chave de proteção.vbs'")

def cipher() -> Fernet:
    require_config()
    try: return Fernet(settings.app_encryption_key.encode())
    except (ValueError, TypeError): raise HTTPException(503, "APP_ENCRYPTION_KEY inválida")

def encrypt(value: str) -> str: return cipher().encrypt(value.encode()).decode()
def decrypt(value: str) -> str:
    try: return cipher().decrypt(value.encode()).decode()
    except InvalidToken: raise HTTPException(500, "Não foi possível ler o token armazenado")

def authorization_url(state: str) -> str:
    require_config()
    client_id=settings.meta_instagram_app_id or settings.meta_app_id
    return str(httpx.URL(settings.meta_oauth_authorize_url).copy_merge_params({"enable_fb_login":"0","force_authentication":"1","client_id":client_id,"redirect_uri":settings.meta_redirect_uri,"response_type":"code","scope":SCOPES,"state":state}))

async def exchange_code(code: str) -> tuple[str, datetime|None]:
    require_config()
    async with httpx.AsyncClient(timeout=30) as client:
        client_id=settings.meta_instagram_app_id or settings.meta_app_id
        secret=settings.meta_instagram_app_secret or settings.meta_app_secret
        response = await client.post(settings.meta_oauth_token_url, data={"client_id":client_id,"client_secret":secret,"grant_type":"authorization_code","redirect_uri":settings.meta_redirect_uri,"code":code})
        if response.is_error: raise HTTPException(400, "A Meta recusou a autorização. Confira a Redirect URI e as permissões.")
        short = response.json().get("access_token")
        if not short: raise HTTPException(400, "A Meta não retornou um token de acesso")
        long = await client.get(f"{settings.meta_graph_base_url}/access_token", params={"grant_type":"ig_exchange_token","client_secret":secret,"access_token":short})
        payload = long.json() if long.is_success else {"access_token":short, "expires_in":None}
        token=payload.get("access_token",short); days=payload.get("expires_in")
        return token, (datetime.utcnow()+timedelta(seconds=int(days)) if days else None)

async def profile(token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response=await client.get(f"{settings.meta_graph_base_url}/me", params={"fields":"id,user_id,username,name,profile_picture_url", "access_token":token})
        if response.is_error: raise HTTPException(400, "Token recebido, mas não foi possível identificar a conta profissional")
        data=response.json(); data["account_id"]=str(data.get("user_id") or data.get("id") or "")
        if not data["account_id"]: raise HTTPException(400, "A Meta não retornou o ID da conta")
        return data

async def publish_reel(account_id: str, token: str, video_url: str, caption: str="", cover_url: str="") -> str:
    """Official resumable Reel upload for Instagram API with Instagram Login."""
    version=settings.meta_graph_api_version
    async with httpx.AsyncClient(timeout=120) as client:
        # The Instagram Login collection specifies multipart form-data and Bearer
        # authentication when opening a resumable upload session. Sending this as
        # urlencoded data makes Meta fall back to the video_url flow.
        fields = {"media_type": (None, "REELS"), "video_url": (None, video_url), "caption": (None, caption), "share_to_feed": (None, "true"), "access_token": (None, token)}
        if cover_url: fields["cover_url"] = (None, cover_url)
        create=await client.post(
            f"{settings.meta_graph_base_url}/v{version}/{account_id}/media",
            files=fields,
            headers={"Authorization": f"Bearer {token}"},
        )
        if create.is_error: raise RuntimeError(f"Meta recusou o container: {create.text[:1000]}")
        container=create.json().get("id")
        if not container: raise RuntimeError("A Meta não retornou o ID do container")
        # Meta fetches the file from video_url; no binary transfer is needed here.
        for _ in range(40):
            status=await client.get(f"{settings.meta_graph_base_url}/v{version}/{container}",params={"fields":"status_code,status","access_token":token})
            data=status.json() if status.is_success else {}
            code=data.get("status_code")
            if code=="FINISHED": break
            if code in {"ERROR","EXPIRED"}: raise RuntimeError(f"A Meta não processou o vídeo: {data}")
            await asyncio.sleep(5)
        else: raise RuntimeError("A Meta demorou demais para processar o vídeo")
        published=await client.post(f"{settings.meta_graph_base_url}/v{version}/{account_id}/media_publish",data={"creation_id":container,"access_token":token})
        if published.is_error: raise RuntimeError(f"Falha ao publicar Reel: {published.text[:1000]}")
        return str(published.json().get("id") or container)
