import asyncio, shutil, uuid, secrets, os, sys, subprocess, json
from contextlib import asynccontextmanager
from datetime import datetime, date, time, timedelta
import random
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, delete, func, text
from sqlalchemy.orm import Session
from .config import settings, ROOT, reload_runtime_settings, data_path
from .db import Base, engine, Session as DbSession
from .models import Media, Script, Campaign, CampaignStatus, ScheduledPost, PostStatus, InstagramAccount, OAuthState, CampaignAccount, CampaignSourceMedia, CampaignScript, ProcessingExecution, CampaignScheduleRule, ProcessedCover, ScheduledPostCover, PublicationAttempt, CaptionList, ApplicationSetting
from .services import dirs, copy_media, process, process_slot, thumbnail
from . import meta
from .tunnel import tunnel
from .media_gateway import media_app
import uvicorn

def db():
    s=DbSession()
    try: yield s
    finally: s.close()
async def scheduler():
    while True:
        with DbSession() as s:
            # A agenda guarda horários locais. No Windows, use o relógio local do
            # computador para não depender da base opcional de fusos do Python.
            local_now=datetime.now()
            due=s.scalars(select(ScheduledPost).join(Campaign).where(ScheduledPost.status==PostStatus.PENDING, ScheduledPost.scheduled_for<=local_now, Campaign.status==CampaignStatus.ACTIVE).order_by(ScheduledPost.scheduled_for).limit(20)).all()
            for post in due:
                if post.scheduled_for < local_now - timedelta(minutes=5):
                    post.status=PostStatus.SKIPPED
                    s.add(PublicationAttempt(post_id=post.id, status="SKIPPED", message="Horário perdido: o sistema não publica automaticamente fora da janela de 5 minutos."))
                    s.commit()
                    continue
                post.status=PostStatus.CLAIMED; post.attempts+=1; s.commit()
                attempt=PublicationAttempt(post_id=post.id,status="UPLOADING"); s.add(attempt); s.commit()
                try:
                    account=s.get(InstagramAccount,post.account_id); media=s.get(Media,post.processed_media_id)
                    if not account or not media: raise RuntimeError("Conta ou mídia processada não encontrada")
                    post.status=PostStatus.UPLOADING; s.commit()
                    public_url=await tunnel.public_url_for(data_path(media.relative_path))
                    link=s.scalar(select(ScheduledPostCover).where(ScheduledPostCover.post_id==post.id)); cover_url=""
                    if link:
                        cover=s.get(ProcessedCover,link.cover_id)
                        if cover: cover_url=await tunnel.public_url_for(data_path(cover.relative_path))
                    media_id=await meta.publish_reel(account.meta_account_id,meta.decrypt(account.encrypted_token),public_url,post.caption,cover_url)
                    post.status=PostStatus.PUBLISHED; attempt.status="PUBLISHED"; attempt.meta_media_id=media_id
                    # A processed file belongs to a single post. Only remove it after
                    # Meta confirmed publication; failed posts keep their files for retry.
                    other_uses=s.scalar(select(func.count()).select_from(ScheduledPost).where(ScheduledPost.processed_media_id==media.id,ScheduledPost.id!=post.id,ScheduledPost.status.not_in([PostStatus.PUBLISHED,PostStatus.CANCELLED,PostStatus.SKIPPED]))) or 0
                    if not other_uses:
                        data_path(media.relative_path).unlink(missing_ok=True)
                        media.status="Publicado (arquivo descartado)"
                    if link and cover:
                        data_path(cover.relative_path).unlink(missing_ok=True)
                except Exception as exc:
                    post.status=PostStatus.FAILED; attempt.status="FAILED"; attempt.message=str(exc)[:4000]
                attempt.finished_at=datetime.utcnow(); s.commit()
        await asyncio.sleep(15)
@asynccontextmanager
async def life(app):
    dirs(); Base.metadata.create_all(engine)
    with engine.begin() as connection:
        columns={row[1] for row in connection.exec_driver_sql("PRAGMA table_info(campaigns)")}
        if "cover_path" not in columns: connection.exec_driver_sql("ALTER TABLE campaigns ADD COLUMN cover_path VARCHAR(500) NOT NULL DEFAULT ''")
        if "caption_list_id" not in columns: connection.exec_driver_sql("ALTER TABLE campaigns ADD COLUMN caption_list_id INTEGER")
        if "caption_text" not in columns: connection.exec_driver_sql("ALTER TABLE campaigns ADD COLUMN caption_text TEXT NOT NULL DEFAULT ''")
        cover_columns={row[1] for row in connection.exec_driver_sql("PRAGMA table_info(processed_covers)")}
        if cover_columns and "post_id" not in cover_columns:
            # SQLite cannot remove the old unique constraint in place. Keep the
            # legacy cover tables intact for history and create slot-based tables.
            connection.exec_driver_sql("ALTER TABLE scheduled_post_covers RENAME TO scheduled_post_covers_legacy")
            connection.exec_driver_sql("ALTER TABLE processed_covers RENAME TO processed_covers_legacy")
            connection.exec_driver_sql("CREATE TABLE processed_covers (id INTEGER NOT NULL PRIMARY KEY, campaign_id INTEGER NOT NULL REFERENCES campaigns(id), original_media_id INTEGER NOT NULL REFERENCES media_files(id), post_id INTEGER UNIQUE REFERENCES scheduled_posts(id), relative_path VARCHAR(500) NOT NULL, sha256 VARCHAR(64) NOT NULL, created_at DATETIME NOT NULL)")
            connection.exec_driver_sql("CREATE TABLE scheduled_post_covers (id INTEGER NOT NULL PRIMARY KEY, post_id INTEGER NOT NULL UNIQUE REFERENCES scheduled_posts(id), cover_id INTEGER NOT NULL REFERENCES processed_covers(id))")
    media_server=uvicorn.Server(uvicorn.Config(media_app, host="127.0.0.1", port=settings.tunnel_media_port, log_level="warning", access_log=False))
    media_task=asyncio.create_task(media_server.serve())
    await tunnel.start()
    task=asyncio.create_task(scheduler())
    try:
        yield
    finally:
        task.cancel(); media_server.should_exit=True; media_task.cancel(); await tunnel.stop()
app=FastAPI(title="Reels Automation Manager", lifespan=life)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_encryption_key or "troque-a-chave-local",
    # Mantém o login mesmo após fechar o navegador ou reiniciar o painel.
    max_age=60*60*24*180,
    # O painel Vercel e a API da VPS estão em domínios HTTPS diferentes.
    # Sem SameSite=None, o navegador descarta a sessão ao navegar/atualizar.
    same_site="none" if settings.session_https_only else "lax",
    https_only=settings.session_https_only,
)
BUILD_ID = "oauth-instagram-login-20260731-2"
class CampaignIn(BaseModel): name:str; description:str=""; timezone:str="America/Sao_Paulo"; script_id:int|None=None
class CampaignSetupIn(BaseModel): account_ids:list[int]; source_ids:list[int]; script_ids:list[int]; start_date:date; days:int; intervals:list[str]; strategy:str="sequential"; cover_path:str=""; caption_list_id:int|None=None; caption_text:str=""
class ProcessIn(BaseModel): source_ids:list[int]
class ScheduleIn(BaseModel): account_id:int; processed_media_id:int; caption:str=""; scheduled_for:datetime; position:int=0
class GenerateScheduleIn(BaseModel): start_date:date; days:int; intervals:list[str]; strategy:str="sequential"
class CampaignDefaultsIn(BaseModel): intervals:list[str]=["11:00-13:00"]; days:int=7; strategy:str="sequential"; script_ids:list[int]=[]; cover_path:str=""; caption_list_id:int|None=None; caption_text:str=""
class LoginIn(BaseModel): email:str; password:str
@app.get("/api/auth/status")
def auth_status(request:Request): return {"authenticated":request.session.get("user")==settings.admin_email,"email":settings.admin_email}
@app.post("/api/auth/login")
def auth_login(body:LoginIn, request:Request):
    if not settings.admin_password or body.email.strip().lower()!=settings.admin_email.lower() or not secrets.compare_digest(body.password,settings.admin_password): raise HTTPException(401,"E-mail ou senha incorretos")
    request.session["user"]=settings.admin_email; return {"ok":True}
@app.post("/api/auth/logout")
def auth_logout(request:Request): request.session.clear(); return {"ok":True}
@app.get("/api/health")
def health(s:Session=Depends(db)): return {"scheduler":"ativo","build_id":BUILD_ID,"meta_configurada":bool(settings.meta_app_id and settings.meta_app_secret),"tunnel":tunnel.status(),"pendentes":s.query(ScheduledPost).filter_by(status=PostStatus.PENDING).count()}
@app.get("/api/tunnel/status")
def tunnel_status(): return tunnel.status()
@app.post("/api/app/restart")
def restart_app():
    # As configurações editáveis são reaplicadas sem derrubar a porta local.
    reload_runtime_settings()
    return {"ok":True, "message":"Configurações aplicadas"}
@app.get("/api/meta/accounts")
def accounts(s:Session=Depends(db)):
    return [{"id":a.id,"username":a.username,"nome":a.display_name,"ativo":a.active,"conectada_em":a.connected_at,"expira_em":a.token_expires_at,"erro":a.last_error} for a in s.scalars(select(InstagramAccount).order_by(InstagramAccount.connected_at.desc()))]
@app.get("/api/meta/oauth/start")
def oauth_start(s:Session=Depends(db)):
    # OAuth settings can be changed through .env without taking the local app down.
    reload_runtime_settings()
    meta.require_config(); state=secrets.token_urlsafe(32); s.add(OAuthState(state=state)); s.commit()
    return RedirectResponse(meta.authorization_url(state))
@app.get("/api/meta/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(code:str|None=None,state:str|None=None,error:str|None=None,s:Session=Depends(db)):
    item=s.get(OAuthState,state) if state else None
    if not item: return HTMLResponse("<h2>Conexão inválida ou expirada.</h2><p>Volte ao Reels Manager e tente novamente.</p>",400)
    s.delete(item); s.commit()
    if error or not code: return HTMLResponse("<h2>A conexão foi cancelada pela Meta.</h2><p>Você pode fechar esta janela.</p>",400)
    try:
        token,expires=await meta.exchange_code(code); profile=await meta.profile(token)
        account=s.scalar(select(InstagramAccount).where(InstagramAccount.meta_account_id==profile["account_id"]))
        if not account:
            account=InstagramAccount(meta_account_id=profile["account_id"],encrypted_token=meta.encrypt(token)); s.add(account)
        else: account.encrypted_token=meta.encrypt(token)
        account.username=profile.get("username",""); account.display_name=profile.get("name",account.username); account.profile_picture_url=profile.get("profile_picture_url",""); account.token_expires_at=expires; account.active=True; account.last_verified_at=datetime.utcnow(); account.last_error=""
        s.commit()
        return HTMLResponse("<script>window.opener&&window.opener.location.reload();window.close()</script><h2>Conta conectada com sucesso.</h2><p>Você já pode fechar esta janela e voltar ao Reels Manager.</p>")
    except HTTPException as e: return HTMLResponse(f"<h2>Não foi possível conectar a conta.</h2><p>{e.detail}</p>",e.status_code)
@app.delete("/api/meta/accounts/{account_id}")
def remove_account(account_id:int,s:Session=Depends(db)):
    item=s.get(InstagramAccount,account_id)
    if not item: raise HTTPException(404,"Conta não encontrada")
    campaign_ids=list(s.scalars(select(CampaignAccount.campaign_id).where(CampaignAccount.account_id==account_id)))
    s.query(ScheduledPost).filter(ScheduledPost.account_id==account_id,ScheduledPost.status.in_([PostStatus.PENDING,PostStatus.CLAIMED,PostStatus.PAUSED])).update({ScheduledPost.status:PostStatus.CANCELLED},synchronize_session=False)
    s.execute(delete(CampaignAccount).where(CampaignAccount.account_id==account_id))
    for campaign_id in campaign_ids:
        if not s.scalar(select(func.count()).select_from(CampaignAccount).where(CampaignAccount.campaign_id==campaign_id)):
            campaign=s.get(Campaign,campaign_id)
            if campaign and campaign.status==CampaignStatus.ACTIVE: campaign.status=CampaignStatus.PAUSED
    s.delete(item);s.commit();return {"ok":True}
@app.get("/api/dashboard")
def dashboard(s:Session=Depends(db)):
    return {"originais":s.query(Media).filter_by(kind="original").count(),"processadas":s.query(Media).filter_by(kind="processed").count(),"campanhas_ativas":s.query(Campaign).filter_by(status=CampaignStatus.ACTIVE).count(),"pendentes":s.query(ScheduledPost).filter_by(status=PostStatus.PENDING).count(),"proximas":[{"id":p.id,"quando":p.scheduled_for,"legenda":p.caption} for p in s.scalars(select(ScheduledPost).order_by(ScheduledPost.scheduled_for).limit(5))]}
@app.get("/api/scheduled-posts")
def scheduled_posts(s:Session=Depends(db)):
    posts=s.scalars(select(ScheduledPost).order_by(ScheduledPost.scheduled_for)).all()
    result=[]
    for p in posts:
        attempt=s.scalar(select(PublicationAttempt).where(PublicationAttempt.post_id==p.id).order_by(PublicationAttempt.id.desc()))
        result.append({
            "id":p.id, "quando":p.scheduled_for, "status":p.status,
            "campanha":s.get(Campaign,p.campaign_id).name if s.get(Campaign,p.campaign_id) else "",
            "conta":s.get(InstagramAccount,p.account_id).username if s.get(InstagramAccount,p.account_id) else "",
            "midia":s.get(Media,p.processed_media_id).original_name if s.get(Media,p.processed_media_id) else "",
            "erro":attempt.message if p.status==PostStatus.FAILED and attempt and attempt.status=="FAILED" else "",
        })
    return result
@app.get("/api/activity")
def activity(s:Session=Depends(db)):
    """Recent processing and publication events, including the current run."""
    items=[]
    executions=s.scalars(select(ProcessingExecution).order_by(ProcessingExecution.id.desc()).limit(60)).all()
    for execution in executions:
        campaign=s.get(Campaign,execution.campaign_id); script=s.get(Script,execution.script_id)
        detail=(execution.stderr or execution.stdout or "").strip()
        items.append({
            "id":f"process-{execution.id}", "type":"PROCESSAMENTO", "status":execution.status,
            "title":f"{campaign.name if campaign else 'Campanha removida'} · {script.name if script else 'Script removido'}",
            "when":execution.finished_at or execution.started_at,
            "detail":detail[-3000:],
            "running":execution.status=="RUNNING",
        })
    attempts=s.scalars(select(PublicationAttempt).order_by(PublicationAttempt.id.desc()).limit(60)).all()
    for attempt in attempts:
        post=s.get(ScheduledPost,attempt.post_id)
        campaign=s.get(Campaign,post.campaign_id) if post else None
        account=s.get(InstagramAccount,post.account_id) if post else None
        items.append({
            "id":f"publish-{attempt.id}", "type":"PUBLICAÇÃO", "status":attempt.status,
            "title":f"{campaign.name if campaign else 'Campanha removida'} · @{account.username if account else 'conta removida'}",
            "when":attempt.finished_at or attempt.created_at,
            "detail":attempt.message or (f"Publicado na Meta: {attempt.meta_media_id}" if attempt.meta_media_id else "Enviando para a Meta..."),
            "running":attempt.status in {"UPLOADING", "WAITING_META", "PUBLISHING"},
        })
    return sorted(items, key=lambda item:item["when"] or datetime.min, reverse=True)[:100]
@app.get("/api/activity/summary")
def activity_summary(s:Session=Depends(db)):
    return {
        "processed": s.query(Media).filter_by(kind="processed").count(),
        "processing": s.query(ProcessingExecution).filter_by(status="RUNNING").count(),
        "published": s.query(ScheduledPost).filter_by(status=PostStatus.PUBLISHED).count(),
        "pending": s.query(ScheduledPost).filter_by(status=PostStatus.PENDING).count(),
        "failed": s.query(ScheduledPost).filter_by(status=PostStatus.FAILED).count(),
    }
@app.delete("/api/activity")
def clear_history(s:Session=Depends(db)):
    finished=[PostStatus.PUBLISHED,PostStatus.FAILED,PostStatus.SKIPPED,PostStatus.CANCELLED]
    post_ids=select(ScheduledPost.id).where(ScheduledPost.status.in_(finished))
    s.execute(delete(PublicationAttempt).where(PublicationAttempt.post_id.in_(post_ids)))
    # Databases created before per-post covers retain this legacy link table.
    # It must be cleared first or SQLite correctly protects the posts from deletion.
    legacy=s.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='scheduled_post_covers_legacy'")).scalar()
    if legacy: s.execute(text("DELETE FROM scheduled_post_covers_legacy WHERE post_id IN (SELECT id FROM scheduled_posts WHERE status IN ('PUBLISHED','FAILED','SKIPPED','CANCELLED'))"))
    s.execute(delete(ScheduledPostCover).where(ScheduledPostCover.post_id.in_(post_ids)))
    s.execute(delete(ScheduledPost).where(ScheduledPost.status.in_(finished)))
    s.execute(delete(ProcessingExecution))
    s.commit()
    # Discard only processed files that no longer belong to a future post.
    for media in list(s.scalars(select(Media).where(Media.kind=="processed"))):
        if not s.scalar(select(func.count()).select_from(ScheduledPost).where(ScheduledPost.processed_media_id==media.id)):
            data_path(media.relative_path).unlink(missing_ok=True); s.delete(media)
    for cover in list(s.scalars(select(ProcessedCover))):
        if not s.scalar(select(func.count()).select_from(ScheduledPostCover).where(ScheduledPostCover.cover_id==cover.id)):
            data_path(cover.relative_path).unlink(missing_ok=True); s.delete(cover)
    s.commit(); return {"ok":True}
@app.post("/api/scheduled-posts/{post_id}/retry-now")
def retry_post_now(post_id:int,s:Session=Depends(db)):
    post=s.get(ScheduledPost,post_id); campaign=s.get(Campaign,post.campaign_id) if post else None
    if not post or not campaign: raise HTTPException(404,"Publicação não encontrada")
    if campaign.status!=CampaignStatus.ACTIVE: raise HTTPException(409,"A campanha precisa estar ativa")
    post.status=PostStatus.PENDING
    post.scheduled_for=datetime.now()
    s.commit(); return {"ok":True}
@app.get("/api/media")
def media(kind:str|None=None,s:Session=Depends(db)):
    q=select(Media); q=q.where(Media.kind==kind) if kind else q
    return [{"id":m.id,"nome":m.original_name,"tipo":m.kind,"status":m.status,"tamanho":m.size,"caminho":m.relative_path,"original_media_id":m.original_media_id,"thumbnail_url":f"/api/media/{m.id}/thumbnail"} for m in s.scalars(q.order_by(Media.created_at.desc()))]
@app.get("/api/media/{media_id}/thumbnail")
def media_thumbnail(media_id:int,s:Session=Depends(db)):
    item=s.get(Media,media_id)
    if not item: raise HTTPException(404,"Mídia não encontrada")
    image=thumbnail(item)
    if not image: raise HTTPException(404,"Não foi possível gerar a miniatura")
    return FileResponse(image,media_type="image/jpeg")
@app.delete("/api/media/{media_id}")
def remove_media(media_id:int,s:Session=Depends(db)):
    item=s.get(Media,media_id)
    if not item: raise HTTPException(404,"Mídia não encontrada")
    if s.scalar(select(func.count()).select_from(CampaignSourceMedia).where(CampaignSourceMedia.media_id==media_id)):
        raise HTTPException(409,"Remova esta mídia das campanhas antes de excluí-la")
    if s.scalar(select(func.count()).select_from(ScheduledPost).where(ScheduledPost.processed_media_id==media_id,ScheduledPost.status.in_([PostStatus.PENDING,PostStatus.CLAIMED,PostStatus.UPLOADING]))):
        raise HTTPException(409,"Esta mídia está em uma publicação pendente")
    data_path(item.relative_path).unlink(missing_ok=True)
    (settings.data_dir/"media/thumbnails"/f"{item.sha256}.jpg").unlink(missing_ok=True)
    s.delete(item); s.commit(); return {"ok":True}
@app.post("/api/media/import")
async def import_media(files:list[UploadFile]=File(...),s:Session=Depends(db)):
    result=[]
    for f in files:
        suffix=Path(f.filename or "").suffix.lower()
        if suffix not in {".mp4",".mov"}: raise HTTPException(400,"Apenas MP4 e MOV")
        temp=settings.data_dir/f".{uuid.uuid4().hex}{suffix}"; temp.parent.mkdir(exist_ok=True); temp.write_bytes(await f.read())
        try: m=copy_media(temp,Path(f.filename or "vídeo").name); s.add(m); s.flush(); thumbnail(m); result.append(m.id)
        finally: temp.unlink(missing_ok=True)
    s.commit(); return {"ids":result}
@app.post("/api/campaign-covers/import")
async def import_campaign_cover(file:UploadFile=File(...)):
    suffix=Path(file.filename or "").suffix.lower()
    if suffix not in {".jpg",".jpeg",".png",".webp"}: raise HTTPException(400,"Envie JPG, PNG ou WebP")
    target=settings.data_dir/"media/covers/source"/f"{uuid.uuid4().hex}{suffix}"; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(await file.read())
    return {"path":str(target.relative_to(settings.data_dir)),"name":Path(file.filename or "capa").name}
@app.get("/api/caption-lists")
def caption_lists(s:Session=Depends(db)): return [{"id":x.id,"nome":x.name,"quantidade":len(json.loads(x.items_json))} for x in s.scalars(select(CaptionList))]
@app.delete("/api/caption-lists/{list_id}")
def remove_caption_list(list_id:int,s:Session=Depends(db)):
    item=s.get(CaptionList,list_id)
    if not item: raise HTTPException(404,"Lista de legendas não encontrada")
    s.query(Campaign).filter(Campaign.caption_list_id==list_id).update({Campaign.caption_list_id:None},synchronize_session=False)
    data_path(item.relative_path).unlink(missing_ok=True); s.delete(item); s.commit(); return {"ok":True}
@app.post("/api/caption-lists/import")
async def import_caption_list(file:UploadFile=File(...),s:Session=Depends(db)):
    try: raw=json.loads((await file.read()).decode("utf-8-sig"))
    except Exception: raise HTTPException(400,"JSON inv\u00e1lido")
    if not isinstance(raw,list): raise HTTPException(400,"O JSON precisa ser uma lista")
    items=[]
    for value in raw:
        if isinstance(value,str): items.append(value)
        elif isinstance(value,dict) and isinstance(value.get("texto"),str) and value.get("ativo",True): items.append(value["texto"])
        else: raise HTTPException(400,"Formato de legenda inv\u00e1lido")
    path=settings.data_dir/"captions"/f"{uuid.uuid4().hex}.json"; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(items,ensure_ascii=False),encoding="utf-8")
    x=CaptionList(name=Path(file.filename or "legendas").stem,items_json=json.dumps(items,ensure_ascii=False),relative_path=str(path.relative_to(settings.data_dir))); s.add(x); s.commit(); return {"id":x.id,"nome":x.name,"quantidade":len(items)}
@app.get("/api/scripts")
def scripts(s:Session=Depends(db)): return [{"id":x.id,"nome":x.name,"ativo":x.active,"descricao":x.description} for x in s.scalars(select(Script))]
@app.delete("/api/scripts/{script_id}")
def remove_script(script_id:int,s:Session=Depends(db)):
    item=s.get(Script,script_id)
    if not item: raise HTTPException(404,"Script não encontrado")
    campaign_ids=list(s.scalars(select(CampaignScript.campaign_id).where(CampaignScript.script_id==script_id)))
    s.query(Campaign).filter(Campaign.script_id==script_id).update({Campaign.script_id:None},synchronize_session=False)
    s.execute(delete(CampaignScript).where(CampaignScript.script_id==script_id))
    s.execute(delete(ProcessingExecution).where(ProcessingExecution.script_id==script_id))
    for campaign_id in campaign_ids:
        if not s.scalar(select(func.count()).select_from(CampaignScript).where(CampaignScript.campaign_id==campaign_id)):
            campaign=s.get(Campaign,campaign_id)
            if campaign and campaign.status==CampaignStatus.ACTIVE: campaign.status=CampaignStatus.PAUSED
    data_path(item.relative_path).unlink(missing_ok=True); s.delete(item); s.commit(); return {"ok":True}
@app.get("/api/campaign-defaults")
def campaign_defaults(s:Session=Depends(db)):
    item=s.get(ApplicationSetting,"campaign_defaults")
    try: payload=(CampaignDefaultsIn.model_validate_json(item.value).model_dump() if item else CampaignDefaultsIn().model_dump())
    except Exception: payload=CampaignDefaultsIn().model_dump()
    # O caminho Ã© o dado persistido; o nome Ã© apenas para a interface mostrar
    # claramente que a capa continua selecionada depois de atualizar a tela.
    payload["cover_name"]=Path(payload["cover_path"]).name if payload.get("cover_path") else ""
    return payload
@app.put("/api/campaign-defaults")
def save_campaign_defaults(body:CampaignDefaultsIn,s:Session=Depends(db)):
    if body.days<1 or body.days>366 or not body.intervals: raise HTTPException(422,"Informe os dias e ao menos um intervalo")
    item=s.get(ApplicationSetting,"campaign_defaults") or ApplicationSetting(key="campaign_defaults")
    item.value=body.model_dump_json(); s.add(item); s.commit()
    payload=body.model_dump(); payload["cover_name"]=Path(payload["cover_path"]).name if payload.get("cover_path") else ""
    return payload
@app.post("/api/scripts/import")
async def import_script(file:UploadFile=File(...),s:Session=Depends(db)):
    if Path(file.filename or "").suffix.lower()!=".py": raise HTTPException(400,"Envie um arquivo .py")
    dirs(); name=f"{uuid.uuid4().hex}.py"; target=settings.data_dir/"scripts"/name; target.write_bytes(await file.read()); x=Script(name=Path(file.filename).stem,relative_path=str(target.relative_to(settings.data_dir))); s.add(x); s.commit(); return {"id":x.id}
@app.get("/api/campaigns")
def campaigns(s:Session=Depends(db)):
    result=[]
    for x in s.scalars(select(Campaign)):
        rule=s.scalar(select(CampaignScheduleRule).where(CampaignScheduleRule.campaign_id==x.id))
        result.append({"id":x.id,"nome":x.name,"status":x.status,"cover_path":x.cover_path,"caption_list_id":x.caption_list_id,"caption_text":x.caption_text,"script_ids":list(s.scalars(select(CampaignScript.script_id).where(CampaignScript.campaign_id==x.id).order_by(CampaignScript.position))),"account_ids":list(s.scalars(select(CampaignAccount.account_id).where(CampaignAccount.campaign_id==x.id))),"source_ids":list(s.scalars(select(CampaignSourceMedia.media_id).where(CampaignSourceMedia.campaign_id==x.id))),"schedule":{"start_date":rule.start_date,"days":rule.days,"intervals":rule.intervals.split(","),"strategy":rule.strategy} if rule else None})
    return result
@app.post("/api/campaigns")
def create_campaign(body:CampaignIn,s:Session=Depends(db)):
    x=Campaign(**body.model_dump()); s.add(x); s.commit(); return {"id":x.id,"status":x.status}
@app.delete("/api/campaigns/{campaign_id}")
def delete_campaign(campaign_id:int,s:Session=Depends(db)):
    c=s.get(Campaign,campaign_id)
    if not c: raise HTTPException(404,"Campanha não encontrada")
    post_ids=select(ScheduledPost.id).where(ScheduledPost.campaign_id==campaign_id); s.execute(delete(PublicationAttempt).where(PublicationAttempt.post_id.in_(post_ids))); s.execute(delete(ScheduledPostCover).where(ScheduledPostCover.post_id.in_(post_ids))); s.execute(delete(ScheduledPost).where(ScheduledPost.campaign_id==campaign_id)); s.execute(delete(ProcessedCover).where(ProcessedCover.campaign_id==campaign_id)); s.execute(delete(ProcessingExecution).where(ProcessingExecution.campaign_id==campaign_id)); s.execute(delete(CampaignScheduleRule).where(CampaignScheduleRule.campaign_id==campaign_id)); s.execute(delete(CampaignAccount).where(CampaignAccount.campaign_id==campaign_id)); s.execute(delete(CampaignSourceMedia).where(CampaignSourceMedia.campaign_id==campaign_id)); s.execute(delete(CampaignScript).where(CampaignScript.campaign_id==campaign_id)); s.delete(c); s.commit(); return {"ok":True}
@app.post("/api/campaigns/{campaign_id}/cancel")
def cancel_campaign(campaign_id:int,s:Session=Depends(db)):
    c=s.get(Campaign,campaign_id)
    if not c: raise HTTPException(404,"Campanha não encontrada")
    s.query(ScheduledPost).filter(ScheduledPost.campaign_id==campaign_id, ScheduledPost.status.in_([PostStatus.PENDING,PostStatus.PAUSED,PostStatus.CLAIMED])).update({ScheduledPost.status:PostStatus.CANCELLED},synchronize_session=False)
    c.status=CampaignStatus.CANCELLED; s.commit(); return {"ok":True,"status":c.status}
@app.put("/api/campaigns/{campaign_id}/setup")
def setup_campaign(campaign_id:int, body:CampaignSetupIn, s:Session=Depends(db)):
    c=s.get(Campaign,campaign_id)
    if not c or c.status not in (CampaignStatus.DRAFT,CampaignStatus.PROCESSING_FAILED,CampaignStatus.READY_TO_SCHEDULE): raise HTTPException(409,"Esta campanha não pode ser alterada agora")
    accounts=list(s.scalars(select(InstagramAccount).where(InstagramAccount.id.in_(body.account_ids),InstagramAccount.active==True)))
    sources=list(s.scalars(select(Media).where(Media.id.in_(body.source_ids),Media.kind=="original")))
    scripts=list(s.scalars(select(Script).where(Script.id.in_(body.script_ids),Script.active==True)))
    if len(accounts)!=len(set(body.account_ids)): raise HTTPException(422,"Selecione apenas contas conectadas")
    if len(sources)!=len(set(body.source_ids)): raise HTTPException(422,"Selecione mídias originais disponíveis")
    if len(scripts)!=len(set(body.script_ids)): raise HTTPException(422,"Selecione scripts ativos")
    if body.days<1 or not body.intervals: raise HTTPException(422,"Informe os dias e ao menos um intervalo")
    s.execute(delete(CampaignAccount).where(CampaignAccount.campaign_id==c.id)); s.execute(delete(CampaignSourceMedia).where(CampaignSourceMedia.campaign_id==c.id)); s.execute(delete(CampaignScript).where(CampaignScript.campaign_id==c.id))
    if body.cover_path and not data_path(body.cover_path).is_file(): raise HTTPException(422,"A capa selecionada não existe")
    if body.caption_list_id and not s.get(CaptionList,body.caption_list_id): raise HTTPException(422,"A lista de legendas selecionada não existe")
    s.add_all([CampaignAccount(campaign_id=c.id,account_id=x.id) for x in accounts]+[CampaignSourceMedia(campaign_id=c.id,media_id=x.id) for x in sources]+[CampaignScript(campaign_id=c.id,script_id=script_id,position=i) for i,script_id in enumerate(body.script_ids)]); c.script_id=body.script_ids[0]; c.cover_path=body.cover_path; c.caption_list_id=body.caption_list_id; c.caption_text=body.caption_text.strip()
    rule=s.scalar(select(CampaignScheduleRule).where(CampaignScheduleRule.campaign_id==c.id)) or CampaignScheduleRule(campaign_id=c.id,start_date=str(body.start_date),days=body.days,intervals=",".join(body.intervals),strategy=body.strategy)
    rule.start_date=str(body.start_date); rule.days=body.days; rule.intervals=",".join(body.intervals); rule.strategy=body.strategy; s.add(rule); s.commit(); return {"ok":True}
@app.post("/api/campaigns/{campaign_id}/process")
def run_processing(campaign_id:int, body:ProcessIn,s:Session=Depends(db)):
    execution=process(s,campaign_id,body.source_ids); campaign=s.get(Campaign,campaign_id)
    return {"execution_id":execution.id if execution else None,"status":campaign.status,"stdout":execution.stdout[-4000:] if execution else "","stderr":execution.stderr[-4000:] if execution else ""}
@app.get("/api/campaigns/{campaign_id}/executions")
def campaign_executions(campaign_id:int,s:Session=Depends(db)):
    return [{"id":e.id,"script_id":e.script_id,"status":e.status,"exit_code":e.exit_code,"started_at":e.started_at,"finished_at":e.finished_at,"stdout":e.stdout,"stderr":e.stderr} for e in s.scalars(select(ProcessingExecution).where(ProcessingExecution.campaign_id==campaign_id).order_by(ProcessingExecution.id.desc()))]
@app.post("/api/campaigns/{campaign_id}/schedule")
def schedule(campaign_id:int,body:ScheduleIn,s:Session=Depends(db)):
    c=s.get(Campaign,campaign_id); m=s.get(Media,body.processed_media_id)
    if not c or c.status not in (CampaignStatus.READY_TO_SCHEDULE,CampaignStatus.SCHEDULE_GENERATED): raise HTTPException(409,"A campanha precisa estar pronta para agendar")
    if not m or m.kind!="processed": raise HTTPException(422,"Uma publicação exige mídia processada")
    x=ScheduledPost(campaign_id=campaign_id,**body.model_dump()); s.add(x); c.status=CampaignStatus.SCHEDULE_GENERATED; s.commit(); return {"id":x.id}
@app.post("/api/campaigns/{campaign_id}/generate-schedule")
def generate_schedule(campaign_id:int,body:GenerateScheduleIn,s:Session=Depends(db)):
    c=s.get(Campaign,campaign_id)
    if not c or c.status not in (CampaignStatus.DRAFT,CampaignStatus.PROCESSING_FAILED,CampaignStatus.READY_TO_SCHEDULE): raise HTTPException(409,"Esta campanha não pode gerar uma nova agenda agora")
    if body.days<1 or body.days>366 or not body.intervals: raise HTTPException(422,"Informe dias e ao menos um intervalo")
    accounts=list(s.scalars(select(CampaignAccount.account_id).where(CampaignAccount.campaign_id==campaign_id)))
    sources=list(s.scalars(select(CampaignSourceMedia.media_id).where(CampaignSourceMedia.campaign_id==campaign_id)))
    caption_items=json.loads(s.get(CaptionList,c.caption_list_id).items_json) if c.caption_list_id and s.get(CaptionList,c.caption_list_id) else []
    if not accounts or not sources: raise HTTPException(422,"Selecione ao menos uma conta e uma mídia original")
    ranges=[]
    for item in body.intervals:
        try:
            left,right=item.split("-"); a=datetime.strptime(left.strip(),"%H:%M").time(); b=datetime.strptime(right.strip(),"%H:%M").time()
            if a>=b: raise ValueError()
            ranges.append((a,b))
        except ValueError: raise HTTPException(422,f"Intervalo inválido: {item}. Use HH:MM-HH:MM")
    post_ids=select(ScheduledPost.id).where(ScheduledPost.campaign_id==campaign_id)
    s.execute(delete(ScheduledPostCover).where(ScheduledPostCover.post_id.in_(post_ids)))
    s.execute(delete(ScheduledPost).where(ScheduledPost.campaign_id==campaign_id))
    c.status=CampaignStatus.PROCESSING; s.commit()
    ordered=sources[:]
    if body.strategy=="random": random.shuffle(ordered)
    index=0; position=0; previous_caption_by_account={}
    try:
        for day_offset in range(body.days):
            current=body.start_date+timedelta(days=day_offset)
            for start,end in ranges:
                low=start.hour*60+start.minute; high=end.hour*60+end.minute
                for account_id in accounts:
                    minute=random.randint(low,high); when=datetime.combine(current,time(minute//60,minute%60))
                    source_id=random.choice(sources) if body.strategy=="random" else ordered[index%len(ordered)]
                    index+=1
                    if c.caption_text: caption=c.caption_text
                    elif caption_items:
                        choices=[text for text in caption_items if text!=previous_caption_by_account.get(account_id)] or caption_items
                        caption=random.choice(choices); previous_caption_by_account[account_id]=caption
                    else: caption=""
                    # No processed file is ever shared: this call executes the full
                    # script chain in a unique workspace for this exact occurrence.
                    media, cover_data=process_slot(s,campaign_id,source_id,f"slot-{uuid.uuid4().hex}")
                    post=ScheduledPost(campaign_id=campaign_id,account_id=account_id,processed_media_id=media.id,caption=caption,scheduled_for=when,position=position)
                    s.add(post); s.flush()
                    if cover_data:
                        cover=ProcessedCover(campaign_id=campaign_id,original_media_id=source_id,post_id=post.id,relative_path=cover_data[0],sha256=cover_data[1])
                        s.add(cover); s.flush(); s.add(ScheduledPostCover(post_id=post.id,cover_id=cover.id))
                    position+=1
        c.status=CampaignStatus.ACTIVE; s.commit(); return {"count":position,"status":c.status}
    except Exception as exc:
        s.rollback()
        c=s.get(Campaign,campaign_id); c.status=CampaignStatus.PROCESSING_FAILED; s.commit()
        raise HTTPException(422,f"O processamento falhou antes de concluir a agenda: {exc}")
@app.post("/api/campaigns/{campaign_id}/activate")
def activate(campaign_id:int,s:Session=Depends(db)):
    c=s.get(Campaign,campaign_id)
    if not c or c.status!=CampaignStatus.SCHEDULE_GENERATED: raise HTTPException(409,"Gere a agenda antes de ativar")
    c.status=CampaignStatus.ACTIVE; s.commit(); return {"status":c.status}
frontend=Path(__file__).resolve().parents[1]/"frontend"/"dist"
if frontend.exists(): app.mount("/",StaticFiles(directory=frontend,html=True),name="frontend")
