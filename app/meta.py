"""Integração do Instagram API with Instagram Login (OAuth oficial da Meta)."""
import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from cryptography.fernet import Fernet, InvalidToken
import httpx
import asyncio
import re
from fastapi import HTTPException
from .config import settings

SCOPES = "instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_comments,instagram_business_content_publish,instagram_business_manage_insights"
UNIFIED_TOKEN_TYPE = "unified_system_user"

def unified_graph_base() -> str:
    return f"https://graph.facebook.com/v{settings.meta_graph_api_version.removeprefix('v')}"

def safe_meta_error(response: httpx.Response) -> str:
    """Expose Meta's useful OAuth reason without ever echoing tokens or secrets."""
    try:
        payload=response.json(); error=payload.get("error",payload) if isinstance(payload,dict) else {}
        message=str(error.get("message") or error.get("error_user_msg") or "")
        code=error.get("code"); subcode=error.get("error_subcode"); kind=error.get("type")
        details=", ".join(str(item) for item in (kind, f"código {code}" if code is not None else "", f"subcódigo {subcode}" if subcode is not None else "") if item)
        if not message:
            message=re.sub(r"(?i)(access_token|client_secret|code)=?[^&\\s\"']+",r"\1=OCULTO",response.text or "").strip() or "resposta vazia"
        return f"Meta respondeu HTTP {response.status_code}{f' ({details})' if details else ''}: {message[:700]}"
    except Exception:
        raw=re.sub(r"(?i)(access_token|client_secret|code)=?[^&\\s\"']+",r"\1=OCULTO",response.text or "").strip()
        return f"Meta respondeu HTTP {response.status_code} ao trocar o código OAuth. Resposta: {raw[:700] or 'vazia'}"

def default_client_id() -> str:
    return settings.meta_instagram_app_id or settings.meta_app_id

def default_client_secret() -> str:
    return settings.meta_instagram_app_secret or settings.meta_app_secret

def cipher() -> Fernet:
    if not settings.app_encryption_key:
        raise HTTPException(503, "Gere a APP_ENCRYPTION_KEY com o arquivo 'Gerar chave de proteção.vbs'")
    try: return Fernet(settings.app_encryption_key.encode())
    except (ValueError, TypeError): raise HTTPException(503, "APP_ENCRYPTION_KEY inválida")

def encrypt(value: str) -> str: return cipher().encrypt(value.encode()).decode()
def decrypt(value: str) -> str:
    try: return cipher().decrypt(value.encode()).decode()
    except InvalidToken: raise HTTPException(500, "Não foi possível ler o token armazenado")

def authorization_url(state: str, client_id: str, redirect_uri: str, config_id: str|None=None) -> str:
    if config_id:
        return str(httpx.URL("https://www.facebook.com/dialog/oauth").copy_merge_params({
            "client_id": client_id, "config_id": config_id, "redirect_uri": redirect_uri,
            "response_type": "code", "override_default_response_type": "true",
            "prompt": "login", "state": state,
        }))
    # Match the Business Login URL emitted by the Meta dashboard.  In
    # particular, force_reauth is the current documented flag for this flow.
    return str(httpx.URL(settings.meta_oauth_authorize_url).copy_merge_params({"force_reauth":"true","client_id":client_id,"redirect_uri":redirect_uri,"response_type":"code","scope":SCOPES,"state":state}))

async def exchange_code(code: str, client_id: str, secret: str, redirect_uri: str) -> tuple[str, datetime|None]:
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        # The Instagram Login token endpoint expects multipart/form-data.  A
        # urlencoded body can be accepted by the edge but later fail with the
        # misleading "Error validating verification code" response.
        response = await client.post(settings.meta_oauth_token_url, files={
            "client_id": (None, client_id),
            "client_secret": (None, secret),
            "grant_type": (None, "authorization_code"),
            "redirect_uri": (None, redirect_uri),
            "code": (None, code),
        })
        if response.is_error:
            raise HTTPException(400, "A Meta recusou o código de autorização. Confira a configuração do app e tente novamente.")
        short = response.json().get("access_token")
        if not short: raise HTTPException(400, "A Meta não retornou um token de acesso")
        long = await client.get(f"{settings.meta_graph_base_url}/access_token", params={"grant_type":"ig_exchange_token","client_secret":secret,"access_token":short})
        payload = long.json() if long.is_success else {"access_token":short, "expires_in":None}
        token=payload.get("access_token",short); days=payload.get("expires_in")
        return token, (datetime.utcnow()+timedelta(seconds=int(days)) if days else None)

async def exchange_unified_code(code: str, client_id: str, secret: str, redirect_uri: str) -> tuple[str, datetime|None]:
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        response = await client.get(f"{unified_graph_base()}/oauth/access_token", params={
            "client_id": client_id, "client_secret": secret, "redirect_uri": redirect_uri, "code": code,
        })
    if response.is_error:
        raise HTTPException(400, "A Meta recusou o código do Unified Login. Confira o app, a configuração e o endereço de retorno.")
    payload = response.json()
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise HTTPException(400, "O Unified Login não retornou um token de acesso.")
    seconds = payload.get("expires_in")
    return token, datetime.utcnow()+timedelta(seconds=seconds) if isinstance(seconds, int) and seconds > 0 else None

async def unified_account_id(token: str, expected_id: str|None) -> str:
    params = {"fields": "id", "limit": "100"}
    accounts = set()
    cursors = set()
    async with httpx.AsyncClient(timeout=10, trust_env=False, headers={"Authorization": f"Bearer {token}"}) as client:
        for _ in range(3):
            response = await client.get(f"{unified_graph_base()}/me/assigned_instagram_accounts", params=params)
            if response.is_error:
                raise HTTPException(400, "A Meta recusou a consulta das contas compartilhadas pelo Unified Login.")
            data = response.json()
            rows = data.get("data")
            if not isinstance(rows, list):
                raise HTTPException(502, "A Meta devolveu uma lista de contas inválida.")
            accounts.update(str(row["id"]) for row in rows if row.get("id"))
            if expected_id and expected_id in accounts:
                return expected_id
            if not expected_id and len(accounts) > 1:
                raise HTTPException(409, "Compartilhe somente a conta do Instagram que deseja conectar e tente novamente.")
            cursor = (data.get("paging") or {}).get("cursors", {}).get("after")
            if not rows or not cursor:
                break
            if cursor in cursors:
                raise HTTPException(502, "A Meta repetiu uma página de contas compartilhadas.")
            cursors.add(cursor)
            params["after"] = cursor
        else:
            raise HTTPException(409, "Compartilhe somente a conta desejada para concluir a conexão.")
    if expected_id:
        raise HTTPException(409, "Compartilhe a mesma conta do Instagram selecionada no painel.")
    if not accounts:
        raise HTTPException(400, "Nenhuma conta profissional do Instagram foi compartilhada.")
    return accounts.pop()

async def profile(token: str, *, unified_account: str|None=None) -> dict:
    if unified_account:
        url = f"{unified_graph_base()}/{unified_account}"
        fields = "id,username,name,profile_picture_url"
    else:
        url = f"{settings.meta_graph_base_url}/me"
        fields = "id,user_id,username,name,profile_picture_url"
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        response=await client.get(url, params={"fields":fields, "access_token":token})
        if response.is_error:
            # The caller needs Meta's reason (especially OAuth 190) to decide
            # whether a token is definitively invalid or a network retry.
            raise HTTPException(400, f"Não foi possível validar a conta: {response.text[:700]}")
        data=response.json(); data["account_id"]=str(data.get("user_id") or data.get("id") or "")
        if not data["account_id"]: raise HTTPException(400, "A Meta não retornou o ID da conta")
        return data

async def reels_with_views(account_id: str, token: str, limit: int=100, *, unified: bool=False) -> list[dict]:
    """Fetch recent Reel metadata, then the single views metric per Reel.

    Insight permission errors are deliberately returned to the caller; they must
    never invalidate an otherwise healthy publishing token.
    """
    fields="id,caption,permalink,thumbnail_url,media_url,timestamp,media_type,media_product_type,like_count,comments_count"
    base=unified_graph_base() if unified else settings.meta_graph_base_url
    async with httpx.AsyncClient(timeout=45, trust_env=False) as client:
        response=await client.get(f"{base}/{account_id}/media",params={"fields":fields,"limit":min(max(limit,1),100),"access_token":token})
        if response.is_error: raise RuntimeError(f"Não foi possível listar Reels: {response.text[:500]}")
        reels=[]
        for item in response.json().get("data",[]):
            if str(item.get("media_product_type"," ")).upper()!="REELS": continue
            insight=await client.get(f"{base}/{item['id']}/insights",params={"metric":"views","access_token":token})
            if insight.is_error: raise RuntimeError(f"Insights indisponíveis: {insight.text[:500]}")
            values=insight.json().get("data",[])
            item["views"]=int(values[0].get("values",[{"value":0}])[0].get("value",0)) if values else 0
            reels.append(item)
        return reels

async def publish_reel(account_id: str, token: str, video_url: str, caption: str="", cover_url: str="", *, unified: bool=False) -> str:
    """Publish by URL using direct connections for POSTs and status polling."""
    try:
        base=unified_graph_base() if unified else f"{settings.meta_graph_base_url}/v{settings.meta_graph_api_version}"
        return await _publish_reel(account_id, token, video_url, caption, cover_url, base)
    except httpx.HTTPError as exc:
        # Exceptions may contain authenticated URLs; do not persist credentials.
        raise RuntimeError(f"Falha de conexão na publicação Meta ({type(exc).__name__})") from None


async def _publish_reel(account_id: str, token: str, video_url: str, caption: str, cover_url: str, base: str) -> str:
    async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
        # Multipart text fields; Meta downloads the binary from video_url.
        fields = {"media_type": (None, "REELS"), "video_url": (None, video_url), "caption": (None, caption), "share_to_feed": (None, "true"), "access_token": (None, token)}
        if cover_url: fields["cover_url"] = (None, cover_url)
        create=await client.post(
            f"{base}/{account_id}/media",
            files=fields,
            headers={"Authorization": f"Bearer {token}"},
        )
        if create.is_error: raise RuntimeError(f"Meta recusou o container: {create.text[:1000]}")
        container=create.json().get("id")
        if not container: raise RuntimeError("A Meta não retornou o ID do container")
        # Meta fetches the file from video_url; no binary transfer is needed here.
        for _ in range(40):
            status=await client.get(f"{base}/{container}",params={"fields":"status_code,status","access_token":token})
            data=status.json() if status.is_success else {}
            code=data.get("status_code")
            if code=="FINISHED": break
            if code in {"ERROR","EXPIRED"}: raise RuntimeError(f"A Meta não processou o vídeo: {data}")
            await asyncio.sleep(5)
        else: raise RuntimeError("A Meta demorou demais para processar o vídeo")
        published=await client.post(f"{base}/{account_id}/media_publish",data={"creation_id":container,"access_token":token})
        if published.is_error: raise RuntimeError(f"Falha ao publicar Reel: {published.text[:1000]}")
        return str(published.json().get("id") or container)
