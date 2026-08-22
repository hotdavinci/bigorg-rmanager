import asyncio, shutil, uuid, secrets, os, sys, subprocess, json, threading, re
from contextlib import asynccontextmanager
from datetime import datetime, date, time, timedelta
import random
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import httpx
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request, Body
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, delete, func, text, update, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from .config import settings, ROOT, reload_runtime_settings, data_path
from .db import Base, engine, Session as DbSession
from .models import Media, Script, Campaign, CampaignStatus, ScheduledPost, PostStatus, InstagramAccount, OAuthState, CampaignAccount, CampaignAccountExclusion, SchedulerLock, AuditLog, InstagramReel, InstagramReelSnapshot, CampaignSourceMedia, CampaignScript, ProcessingExecution, CampaignScheduleRule, ProcessedCover, ScheduledPostCover, PublicationAttempt, CaptionList, ApplicationSetting
from .services import dirs, copy_media, process, process_slot, process_slots_batch, thumbnail, commit_with_retry
from . import meta
from .tunnel import tunnel
from .media_gateway import media_app
import uvicorn

def db():
    s=DbSession()
    try: yield s
    finally: s.close()

def account_is_eligible(account: InstagramAccount, now: datetime|None=None) -> bool:
    """One conservative definition used by the UI, setup and scheduler."""
    now=now or datetime.utcnow()
    return bool(not account.deleted_at and account.active and account.encrypted_token and account.last_verified_at and not (account.last_error or "").strip() and (not account.token_expires_at or account.token_expires_at>now))

def is_definitive_account_error(error: Exception) -> bool:
    message=str(error).lower()
    return any(token in message for token in ("invalid token","error validating access token","oauth","permission","not authorized","unsupported post request","checkpoint","code 190","code=190"))

def audit(session: Session, event_type: str, message: str, campaign_id: int|None=None, account_id: int|None=None):
    session.add(AuditLog(event_type=event_type,message=message,campaign_id=campaign_id,account_id=account_id))

def cancel_account_from_active_campaigns(session: Session, account: InstagramAccount, reason: str) -> int:
    """Makes a fallen account ineligible and preserves completed/history records."""
    now=datetime.now()
    account.active=False
    account.last_error=reason[:4000]
    account.last_verified_at=datetime.utcnow()
    campaign_ids=list(session.scalars(select(CampaignAccount.campaign_id).join(Campaign).where(CampaignAccount.account_id==account.id,Campaign.status.in_([CampaignStatus.ACTIVE,CampaignStatus.PROCESSING]))))
    cancelled=0
    for campaign_id in campaign_ids:
        count=session.query(ScheduledPost).filter(
            ScheduledPost.campaign_id==campaign_id, ScheduledPost.account_id==account.id,
            ScheduledPost.scheduled_for>now,
            ScheduledPost.status.in_([PostStatus.PENDING,PostStatus.CLAIMED,PostStatus.UPLOADING,PostStatus.WAITING_META,PostStatus.PUBLISHING,PostStatus.PAUSED])
        ).update({ScheduledPost.status:PostStatus.CANCELLED},synchronize_session=False)
        cancelled+=count
        excluded=session.scalar(select(CampaignAccountExclusion).where(CampaignAccountExclusion.campaign_id==campaign_id,CampaignAccountExclusion.account_id==account.id))
        if excluded:
            excluded.reason=reason[:4000]; excluded.removed_at=datetime.utcnow()
        else:
            session.add(CampaignAccountExclusion(campaign_id=campaign_id,account_id=account.id,reason=reason[:4000]))
        session.execute(delete(CampaignAccount).where(CampaignAccount.campaign_id==campaign_id,CampaignAccount.account_id==account.id))
        audit(session,"ACCOUNT_REMOVED",f"Conta removida da campanha: {reason}",campaign_id,account.id)
        if count: audit(session,"SCHEDULES_CANCELLED",f"{count} agendamento(s) futuro(s) cancelado(s): {reason}",campaign_id,account.id)
    audit(session,"ACCOUNT_INELIGIBLE",f"Conta marcada como não apta: {reason}",account_id=account.id)
    return cancelled

def parse_intervals(values: list[str]):
    ranges=[]
    for item in values:
        left,right=item.split("-"); start=datetime.strptime(left.strip(),"%H:%M").time(); end=datetime.strptime(right.strip(),"%H:%M").time()
        low=start.hour*60+start.minute; high=end.hour*60+end.minute
        if low==high: raise ValueError(f"Intervalo inválido: {item}. O início e o fim não podem ser iguais")
        # 23:00-00:00 and 23:30-01:00 are valid ranges crossing midnight.
        if high<low: high+=24*60
        ranges.append((low,high))
    return ranges

def _clone_processed_for_schedule(session: Session, campaign_id: int, original_media_id: int, seed_media: Media, account_id: int, position: int) -> Media:
    source=data_path(seed_media.relative_path)
    if not source.is_file(): raise ValueError("Arquivo processado de referência não está disponível")
    target_dir=settings.data_dir/"media/processed"/str(campaign_id)/f"sync-{account_id}-{position}"
    target_dir.mkdir(parents=True,exist_ok=True)
    target=target_dir/f"{uuid.uuid4().hex}{source.suffix.lower()}"
    shutil.copy2(source,target)
    from .services import sha
    output=Media(original_name=seed_media.original_name,stored_name=target.name,relative_path=str(target.relative_to(settings.data_dir)),kind="processed",extension=target.suffix.lower(),size=target.stat().st_size,sha256=sha(target),status="Processada",original_media_id=original_media_id)
    session.add(output); session.flush()
    return output

def materialize_missing_schedule_for_account(session: Session, campaign: Campaign, account: InstagramAccount, not_before: datetime|None=None) -> int:
    """Adds only future, missing slots. It never edits an existing publication."""
    rule=session.scalar(select(CampaignScheduleRule).where(CampaignScheduleRule.campaign_id==campaign.id))
    if not rule: return 0
    try: ranges=parse_intervals([x.strip() for x in rule.intervals.split(",") if x.strip()]); start_date=date.fromisoformat(rule.start_date)
    except (ValueError, TypeError):
        audit(session,"SCHEDULE_SYNC_FAILED","Regras de horário inválidas; nenhum agendamento foi criado.",campaign.id,account.id); return 0
    sources=list(session.scalars(select(CampaignSourceMedia.media_id).where(CampaignSourceMedia.campaign_id==campaign.id)))
    if not sources: return 0
    now=datetime.now(); captions=[]
    if campaign.caption_list_id:
        caption_list=session.get(CaptionList,campaign.caption_list_id)
        if caption_list:
            try: captions=json.loads(caption_list.items_json)
            except json.JSONDecodeError: captions=[]
    existing_positions=set(session.scalars(select(ScheduledPost.position).where(ScheduledPost.campaign_id==campaign.id,ScheduledPost.account_id==account.id)))
    previous=session.scalar(select(ScheduledPost.caption).where(ScheduledPost.account_id==account.id,ScheduledPost.campaign_id==campaign.id).order_by(ScheduledPost.scheduled_for.desc()))
    created=0
    for day_offset in range(rule.days):
        current=start_date+timedelta(days=day_offset)
        for range_index,(low,high) in enumerate(ranges):
            position=day_offset*1000+range_index
            if position in existing_positions: continue
            # Stable randomness means a restart calculates the same occurrence.
            rng=random.Random(f"campaign:{campaign.id}:account:{account.id}:slot:{position}")
            minute=rng.randint(low,high); when=datetime.combine(current,time())+timedelta(minutes=minute)
            if when<=now or (not_before and when<not_before): continue
            source_id=rng.choice(sources) if rule.strategy=="random" else sources[position%len(sources)]
            seeds=list(session.scalars(select(Media).where(Media.kind=="processed",Media.original_media_id==source_id)))
            seed=next((media for media in reversed(seeds) if data_path(media.relative_path).is_file()),None)
            if not seed:
                audit(session,"SCHEDULE_SYNC_SKIPPED","Não há mídia processada disponível para este slot.",campaign.id,account.id); continue
            output=_clone_processed_for_schedule(session,campaign.id,source_id,seed,account.id,position)
            if campaign.caption_text: caption=campaign.caption_text
            elif captions:
                choices=[item for item in captions if item!=previous] or captions; caption=rng.choice(choices); previous=caption
            else: caption=""
            session.add(ScheduledPost(campaign_id=campaign.id,account_id=account.id,processed_media_id=output.id,caption=caption,scheduled_for=when,position=position,status=PostStatus.PENDING))
            existing_positions.add(position); created+=1
    if created:
        audit(session,"SCHEDULES_CREATED",f"{created} novo(s) agendamento(s) futuro(s) criado(s) automaticamente.",campaign.id,account.id)
    return created

def account_campaign_sync_delay_days(session: Session) -> int:
    item=session.get(ApplicationSetting,"account_campaign_sync_delay_days")
    try: return max(0,min(365,int(item.value if item else 1)))
    except (TypeError,ValueError): return 1

def schedule_account_campaign_sync(session: Session, account: InstagramAccount) -> int:
    """Sets the first allowed publication time for a newly connected account."""
    days=account_campaign_sync_delay_days(session)
    account.campaign_sync_due_at=account.connected_at+timedelta(days=days)
    account.campaign_sync_completed_at=None
    audit(session,"ACCOUNT_SYNC_WAITING",f"Conta validada; os horários anteriores a {account.campaign_sync_due_at:%d/%m/%Y %H:%M} serão ignorados.",account_id=account.id)
    return days

def sync_account_to_active_campaigns(session: Session, account: InstagramAccount, not_before: datetime|None=None) -> tuple[int,int]:
    """Links a valid account once and materializes only still-allowed future slots."""
    added=created=0
    for campaign in session.scalars(select(Campaign).where(Campaign.status==CampaignStatus.ACTIVE)):
        linked=session.scalar(select(CampaignAccount).where(CampaignAccount.campaign_id==campaign.id,CampaignAccount.account_id==account.id))
        if linked: continue
        exclusion=session.scalar(select(CampaignAccountExclusion).where(CampaignAccountExclusion.campaign_id==campaign.id,CampaignAccountExclusion.account_id==account.id))
        if exclusion and account.connected_at<=exclusion.removed_at: continue
        session.add(CampaignAccount(campaign_id=campaign.id,account_id=account.id)); session.flush()
        count=materialize_missing_schedule_for_account(session,campaign,account,not_before=not_before)
        audit(session,"ACCOUNT_ADDED",f"Conta adicionada automaticamente; {count} agendamento(s) futuro(s) criado(s).",campaign.id,account.id)
        added+=1; created+=count
    return added,created

def sync_due_connected_accounts(session: Session) -> dict:
    """One-time, database-backed sync for accounts whose configured wait ended."""
    now=datetime.utcnow(); added=created=completed=0
    due=list(session.scalars(select(InstagramAccount).where(
        InstagramAccount.campaign_sync_due_at.is_not(None),
        InstagramAccount.campaign_sync_due_at<=now,
        InstagramAccount.campaign_sync_completed_at.is_(None),
    )))
    for account in due:
        # A disconnected, expired or failed account is never admitted. A future
        # OAuth reconnection resets due_at and is the only way it can return.
        if not account_is_eligible(account,now):
            continue
        linked_count,created_count=sync_account_to_active_campaigns(session,account)
        added+=linked_count; created+=created_count
        account.campaign_sync_completed_at=now
        audit(session,"ACCOUNT_SYNC_COMPLETED",f"Sincronização automática concluída: {added} vínculo(s) e {created} agendamento(s) futuro(s).",account_id=account.id)
        completed+=1
    if completed: commit_with_retry(session)
    return {"completed":completed,"added":added,"created":created}

def as_local_datetime(value: str|None) -> datetime|None:
    if not value: return None
    try:
        normalized=value.replace("Z","+00:00")
        # Meta returns offsets such as +0000. Python's parser on this VPS only
        # accepts the ISO form +00:00, otherwise publication dates become NULL
        # and every 24h/7d/30d filter is inevitably empty.
        if re.search(r"[+-]\d{4}$",normalized): normalized=f"{normalized[:-2]}:{normalized[-2:]}"
        parsed=datetime.fromisoformat(normalized)
        if parsed.tzinfo:
            return parsed.astimezone(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)
        return parsed
    except ValueError: return None

async def cache_reel_thumbnail(reel: InstagramReel, source_url: str) -> None:
    """Keep a small local visual record even when Instagram later removes a Reel.

    The downloaded image replaces the fragile Instagram iframe/CDN URL. Failures
    deliberately retain the last good image rather than making an old Reel blank.
    """
    if not source_url:
        return

async def cache_reel_video(reel: InstagramReel, source_url: str) -> None:
    """Download a winner's official media URL once, while the CDN URL is valid."""
    if not source_url or (reel.cached_video_path and data_path(reel.cached_video_path).is_file()):
        return
    safe_id=re.sub(r"[^a-zA-Z0-9_-]", "_", reel.meta_media_id)
    extension=Path(urlparse(source_url).path).suffix.lower() or ".mp4"
    if extension not in {".mp4", ".mov"}: extension=".mp4"
    relative=Path("insights") / "videos" / f"reel-{reel.account_id}-{safe_id}{extension}"
    target=data_path(relative)
    try:
        async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
            async with client.stream("GET",source_url) as response:
                content_type=response.headers.get("content-type", "").lower()
                if response.status_code!=200 or not content_type.startswith("video/"):
                    return
                target.parent.mkdir(parents=True,exist_ok=True)
                temporary=target.with_suffix(target.suffix+".tmp")
                total=0
                with temporary.open("wb") as output:
                    async for chunk in response.aiter_bytes(1024*1024):
                        total+=len(chunk)
                        if total>500*1024*1024:
                            output.close(); temporary.unlink(missing_ok=True); return
                        output.write(chunk)
        if target.with_suffix(target.suffix+".tmp").is_file():
            target.with_suffix(target.suffix+".tmp").replace(target)
            reel.cached_video_path=str(relative).replace("\\", "/")
    except (httpx.HTTPError,OSError):
        return
    safe_id=re.sub(r"[^a-zA-Z0-9_-]", "_", reel.meta_media_id)
    relative=Path("insights") / "thumbnails" / f"reel-{reel.account_id}-{safe_id}.jpg"
    target=data_path(relative)
    if target.is_file() and reel.cached_thumbnail_path:
        return
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            response=await client.get(source_url)
        content_type=response.headers.get("content-type", "").lower()
        if response.status_code != 200 or not content_type.startswith("image/") or not response.content or len(response.content)>10*1024*1024:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary=target.with_suffix(".tmp")
        temporary.write_bytes(response.content)
        temporary.replace(target)
        reel.cached_thumbnail_path=str(relative).replace("\\", "/")
    except (httpx.HTTPError, OSError):
        # Insight sync must never fail just because the optional visual cache did.
        return

def archive_published_reel_video(session: Session, account_id: int, meta_media_id: str, source: Path) -> None:
    """Preserve the exact processed file sent to Meta for a future winner card.

    Meta does not reliably expose a downloadable media_url after a Reel is
    published. Keeping this copy at publication time is what makes the ranking
    survive a later deletion/takedown of the Reel itself.
    """
    if not source.is_file():
        return
    reel=session.scalar(select(InstagramReel).where(InstagramReel.account_id==account_id,InstagramReel.meta_media_id==str(meta_media_id)))
    if not reel:
        reel=InstagramReel(account_id=account_id,meta_media_id=str(meta_media_id))
        session.add(reel); session.flush()
    if reel.cached_video_path and data_path(reel.cached_video_path).is_file():
        return
    safe_id=re.sub(r"[^a-zA-Z0-9_-]", "_", str(meta_media_id))
    relative=Path("insights") / "videos" / f"reel-{account_id}-{safe_id}{source.suffix.lower()}"
    target=data_path(relative)
    try:
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
        reel.cached_video_path=str(relative).replace("\\", "/")
    except OSError:
        return

async def sync_reel_insights(session: Session) -> dict:
    synced=unsupported=0; video_candidates=[]
    # Insights are independent from publishing health. An account may publish
    # normally while its token does not have the insights scope yet.
    for account in session.scalars(select(InstagramAccount).where(InstagramAccount.active==True)):
        try:
            items=await meta.reels_with_views(account.meta_account_id,meta.decrypt(account.encrypted_token),settings.insights_reels_limit)
            for item in items:
                reel=session.scalar(select(InstagramReel).where(InstagramReel.account_id==account.id,InstagramReel.meta_media_id==str(item["id"])))
                if not reel:
                    reel=InstagramReel(account_id=account.id,meta_media_id=str(item["id"])); session.add(reel); session.flush()
                reel.caption=str(item.get("caption") or ""); reel.permalink=str(item.get("permalink") or ""); reel.thumbnail_url=str(item.get("thumbnail_url") or ""); reel.video_url=str(item.get("media_url") or ""); reel.published_at=as_local_datetime(item.get("timestamp")); reel.views=int(item.get("views") or 0); reel.likes=int(item.get("like_count") or 0); reel.comments=int(item.get("comments_count") or 0); reel.synced_at=datetime.utcnow()
                await cache_reel_thumbnail(reel,reel.thumbnail_url)
                video_candidates.append((reel,reel.video_url,reel.views))
                session.add(InstagramReelSnapshot(reel_id=reel.id,views=reel.views,likes=reel.likes,comments=reel.comments))
                synced+=1
            account.last_insights_error=""
        except Exception as exc:
            # Keep the account publishable; just expose the unavailable insights.
            account.last_insights_error=str(exc)[:1000]; unsupported+=1
    # Only retain the globally configured winners. The file is downloaded from
    # Meta now, then served locally even if its CDN URL or the Reel disappears.
    winner_settings=saved_insight_winner_settings(session)
    kept=0
    for reel,url,_ in sorted(video_candidates,key=lambda item:item[2],reverse=True):
        if reel.views<winner_settings["minimum_views"]: continue
        if kept>=winner_settings["limit"]: break
        await cache_reel_video(reel,url)
        if reel.cached_video_path and data_path(reel.cached_video_path).is_file(): kept+=1
    session.commit(); return {"synced":synced,"unsupported":unsupported}

async def run_insights_sync_if_due(force: bool=False) -> dict|None:
    now=datetime.utcnow(); lock_name="instagram-insights-sync"
    with DbSession() as session:
        lock=session.get(SchedulerLock,lock_name)
        if lock and lock.locked_until and lock.locked_until>now: return None
        if not force and lock and lock.last_run_at and lock.last_run_at>now-timedelta(hours=max(1,settings.insights_sync_hours)): return None
        if not lock: lock=SchedulerLock(name=lock_name); session.add(lock)
        lock.locked_until=now+timedelta(minutes=45); session.commit()
    try:
        with DbSession() as session:
            result=await sync_reel_insights(session)
            lock=session.get(SchedulerLock,lock_name); lock.last_run_at=datetime.utcnow(); lock.locked_until=datetime.utcnow(); session.commit()
            return result
    except Exception:
        with DbSession() as session:
            lock=session.get(SchedulerLock,lock_name)
            if lock: lock.locked_until=datetime.utcnow(); session.commit()
        return None

async def insights_scheduler():
    while True:
        await run_insights_sync_if_due()
        await asyncio.sleep(300)

async def run_account_health_check(force: bool=False) -> dict|None:
    """Verify publish tokens without keeping SQLite write locks during HTTP calls."""
    now=datetime.utcnow(); lock_name="instagram-account-health"
    with DbSession() as session:
        lock=session.get(SchedulerLock,lock_name)
        interval=timedelta(minutes=max(5,settings.account_health_check_minutes))
        if lock and lock.locked_until and lock.locked_until>now: return None
        if not force and lock and lock.last_run_at and lock.last_run_at>now-interval: return None
        if not lock: lock=SchedulerLock(name=lock_name); session.add(lock)
        lock.locked_until=now+timedelta(minutes=10); session.commit()
        account_ids=list(session.scalars(select(InstagramAccount.id).where(InstagramAccount.active==True,InstagramAccount.deleted_at.is_(None))))
    checked=healthy=removed=transient=0
    try:
        for account_id in account_ids:
            with DbSession() as session:
                account=session.get(InstagramAccount,account_id)
                if not account or not account.active or account.deleted_at: continue
                checked+=1
                try:
                    profile=await meta.profile(meta.decrypt(account.encrypted_token))
                    # A different profile is not a healthy reconnection either.
                    if str(profile.get("account_id") or "")!=str(account.meta_account_id):
                        raise RuntimeError("A validação retornou uma conta diferente da vinculada")
                    account.username=profile.get("username") or account.username
                    account.display_name=profile.get("name") or account.display_name
                    account.profile_picture_url=profile.get("profile_picture_url") or account.profile_picture_url
                    account.last_verified_at=datetime.utcnow(); account.last_error=""; healthy+=1
                    commit_with_retry(session)
                except Exception as exc:
                    if is_definitive_account_error(exc):
                        reason=f"Falha na verificação automática: {str(exc)[:700]}"
                        cancel_account_from_active_campaigns(session,account,reason)
                        commit_with_retry(session); removed+=1
                    else:
                        # Network/API instabilities do not wrongly deactivate a
                        # good account. The next scheduled check tries again.
                        audit(session,"ACCOUNT_HEALTH_RETRY",f"Verificação adiada por falha temporária: {str(exc)[:500]}",account_id=account.id)
                        commit_with_retry(session); transient+=1
        return {"checked":checked,"healthy":healthy,"removed":removed,"transient":transient}
    finally:
        with DbSession() as session:
            lock=session.get(SchedulerLock,lock_name)
            if lock: lock.last_run_at=datetime.utcnow(); lock.locked_until=datetime.utcnow(); session.commit()

async def account_health_scheduler():
    while True:
        await run_account_health_check()
        await asyncio.sleep(300)

def is_definitive_publish_error(error: Exception) -> bool:
    message=str(error).lower()
    return any(token in message for token in ("invalid token","expired","permission","oauth","401","403","unsupported post request","not authorized","checkpoint"))

def retry_delay(attempt_number: int) -> int:
    """30s, 60s, 120s — short enough for a late post, bounded for the API."""
    return min(30*(2**max(attempt_number-1,0)),120)

def recover_stalled_claims(session: Session, now: datetime) -> int:
    cutoff=now-timedelta(seconds=max(60,settings.scheduler_claim_timeout_seconds))
    stuck=session.scalars(select(ScheduledPost).where(
        ScheduledPost.status.in_([PostStatus.CLAIMED,PostStatus.UPLOADING,PostStatus.WAITING_META,PostStatus.PUBLISHING]),
        ScheduledPost.claimed_at<cutoff,
    )).all()
    for post in stuck:
        post.status=PostStatus.PENDING; post.next_attempt_at=now; post.last_error="Execução interrompida; tarefa recuperada automaticamente após reinício/timeout."
        session.add(PublicationAttempt(post_id=post.id,status="RECOVERED",message=post.last_error,finished_at=datetime.utcnow()))
    if stuck: session.commit()
    return len(stuck)

def claim_due_posts(session: Session, account_ids_in_flight: set[int], now: datetime, limit: int) -> list[int]:
    due=session.scalars(select(ScheduledPost).join(Campaign).where(
        ScheduledPost.status==PostStatus.PENDING, ScheduledPost.scheduled_for<=now,
        or_(ScheduledPost.next_attempt_at.is_(None),ScheduledPost.next_attempt_at<=now),
        # Posts de um lote já validado podem sair enquanto os lotes seguintes
        # ainda estão sendo processados. Nunca há mídia original nesta fila.
        Campaign.status.in_((CampaignStatus.PROCESSING,CampaignStatus.ACTIVE)),
    ).order_by(ScheduledPost.scheduled_for).limit(limit*4)).all()
    claimed=[]
    for post in due:
        if post.account_id in account_ids_in_flight or len(claimed)>=limit: continue
        result=session.execute(update(ScheduledPost).where(ScheduledPost.id==post.id,ScheduledPost.status==PostStatus.PENDING).values(
            status=PostStatus.CLAIMED, claimed_at=now, attempts=ScheduledPost.attempts+1, next_attempt_at=None,
        ))
        if result.rowcount:
            account_ids_in_flight.add(post.account_id); claimed.append(post.id)
    if claimed: session.commit()
    return claimed

async def publish_claimed_post(post_id: int, account_ids_in_flight: set[int], semaphore: asyncio.Semaphore):
    account_id=None
    try:
        async with semaphore:
            with DbSession() as s:
                post=s.get(ScheduledPost,post_id)
                if not post or post.status!=PostStatus.CLAIMED: return
                account_id=post.account_id; account=s.get(InstagramAccount,post.account_id); media=s.get(Media,post.processed_media_id)
                if not account or not media: raise RuntimeError("Conta ou mídia processada não encontrada")
                if not account_is_eligible(account):
                    cancel_account_from_active_campaigns(s,account,"Conta não está apta a publicar")
                    s.commit(); return
                post.status=PostStatus.UPLOADING; attempt=PublicationAttempt(post_id=post.id,status="UPLOADING"); s.add(attempt); s.commit()
                media_path=data_path(media.relative_path)
                if not media_path.is_file(): raise RuntimeError("Arquivo processado não existe mais")
                public_url=await tunnel.public_url_for(media_path)
                link=s.scalar(select(ScheduledPostCover).where(ScheduledPostCover.post_id==post.id)); cover=None; cover_url=""
                if link:
                    cover=s.get(ProcessedCover,link.cover_id)
                    if cover and data_path(cover.relative_path).is_file(): cover_url=await tunnel.public_url_for(data_path(cover.relative_path))
                post.status=PostStatus.WAITING_META; s.commit()
                media_id=await meta.publish_reel(account.meta_account_id,meta.decrypt(account.encrypted_token),public_url,post.caption,cover_url)
                post.status=PostStatus.PUBLISHED; post.last_error=""; attempt.status="PUBLISHED"; attempt.meta_media_id=media_id; attempt.finished_at=datetime.utcnow()
                archive_published_reel_video(s,account.id,media_id,media_path)
                other_uses=s.scalar(select(func.count()).select_from(ScheduledPost).where(ScheduledPost.processed_media_id==media.id,ScheduledPost.id!=post.id,ScheduledPost.status.not_in([PostStatus.PUBLISHED,PostStatus.CANCELLED,PostStatus.SKIPPED]))) or 0
                if not other_uses:
                    media_path.unlink(missing_ok=True); media.status="Publicado (arquivo descartado)"
                if cover: data_path(cover.relative_path).unlink(missing_ok=True)
                s.commit()
    except Exception as exc:
        with DbSession() as s:
            post=s.get(ScheduledPost,post_id)
            if post and post.status not in (PostStatus.PUBLISHED,PostStatus.CANCELLED):
                account=s.get(InstagramAccount,post.account_id); message=str(exc)[:4000]
                attempt=s.scalar(select(PublicationAttempt).where(PublicationAttempt.post_id==post.id).order_by(PublicationAttempt.id.desc()))
                post.last_error=message
                if account and is_definitive_publish_error(exc):
                    post.status=PostStatus.FAILED
                    cancel_account_from_active_campaigns(s,account,f"Erro definitivo de publicação: {message[:500]}")
                    state="FAILED"
                elif post.attempts<max(1,settings.scheduler_max_attempts):
                    wait=retry_delay(post.attempts); post.status=PostStatus.PENDING; post.next_attempt_at=datetime.now()+timedelta(seconds=wait); state="RETRYING"
                    audit(s,"PUBLICATION_RETRY",f"Tentativa {post.attempts}/{settings.scheduler_max_attempts} falhou; nova tentativa em {wait}s.",post.campaign_id,post.account_id)
                else:
                    post.status=PostStatus.FAILED; state="FAILED"
                if attempt: attempt.status=state; attempt.message=message; attempt.finished_at=datetime.utcnow()
                else: s.add(PublicationAttempt(post_id=post.id,status=state,message=message,finished_at=datetime.utcnow()))
                s.commit()
    finally:
        if account_id is not None: account_ids_in_flight.discard(account_id)

async def scheduler():
    """Publication queue: independent from processing and safe across restarts."""
    semaphore=asyncio.Semaphore(max(1,settings.scheduler_parallelism)); in_flight_accounts:set[int]=set(); tasks:set[asyncio.Task]=set()
    resume_interrupted_campaign_generations()
    while True:
        now=datetime.now()
        post_ids=[]
        try:
            with DbSession() as s:
                # This does not perform a global health sweep. It only admits an
                # OAuth-validated account once its configured waiting period ends.
                sync_due_connected_accounts(s)
                recover_stalled_claims(s,now)
                free=max(0,settings.scheduler_parallelism-len(tasks))
                post_ids=claim_due_posts(s,in_flight_accounts,now,free)
        except OperationalError as exc:
            # A transient SQLite writer collision must never kill the loop. The
            # next short polling cycle retries claims without creating duplicates.
            if "locked" not in str(exc).lower():
                raise
        for post_id in post_ids:
            task=asyncio.create_task(publish_claimed_post(post_id,in_flight_accounts,semaphore),name=f"publish-{post_id}")
            tasks.add(task); task.add_done_callback(tasks.discard)
        await asyncio.sleep(max(2,settings.scheduler_poll_seconds))
@asynccontextmanager
async def life(app):
    dirs(); Base.metadata.create_all(engine)
    with engine.begin() as connection:
        columns={row[1] for row in connection.exec_driver_sql("PRAGMA table_info(campaigns)")}
        if "cover_path" not in columns: connection.exec_driver_sql("ALTER TABLE campaigns ADD COLUMN cover_path VARCHAR(500) NOT NULL DEFAULT ''")
        if "caption_list_id" not in columns: connection.exec_driver_sql("ALTER TABLE campaigns ADD COLUMN caption_list_id INTEGER")
        if "caption_text" not in columns: connection.exec_driver_sql("ALTER TABLE campaigns ADD COLUMN caption_text TEXT NOT NULL DEFAULT ''")
        account_columns={row[1] for row in connection.exec_driver_sql("PRAGMA table_info(instagram_accounts)")}
        if "last_insights_error" not in account_columns: connection.exec_driver_sql("ALTER TABLE instagram_accounts ADD COLUMN last_insights_error TEXT NOT NULL DEFAULT ''")
        if "campaign_sync_due_at" not in account_columns: connection.exec_driver_sql("ALTER TABLE instagram_accounts ADD COLUMN campaign_sync_due_at DATETIME")
        if "campaign_sync_completed_at" not in account_columns: connection.exec_driver_sql("ALTER TABLE instagram_accounts ADD COLUMN campaign_sync_completed_at DATETIME")
        if "deleted_at" not in account_columns: connection.exec_driver_sql("ALTER TABLE instagram_accounts ADD COLUMN deleted_at DATETIME")
        post_columns={row[1] for row in connection.exec_driver_sql("PRAGMA table_info(scheduled_posts)")}
        if "next_attempt_at" not in post_columns: connection.exec_driver_sql("ALTER TABLE scheduled_posts ADD COLUMN next_attempt_at DATETIME")
        if "last_error" not in post_columns: connection.exec_driver_sql("ALTER TABLE scheduled_posts ADD COLUMN last_error TEXT NOT NULL DEFAULT ''")
        snapshot_columns={row[1] for row in connection.exec_driver_sql("PRAGMA table_info(instagram_reel_snapshots)")}
        if "likes" not in snapshot_columns: connection.exec_driver_sql("ALTER TABLE instagram_reel_snapshots ADD COLUMN likes INTEGER NOT NULL DEFAULT 0")
        if "comments" not in snapshot_columns: connection.exec_driver_sql("ALTER TABLE instagram_reel_snapshots ADD COLUMN comments INTEGER NOT NULL DEFAULT 0")
        reel_columns={row[1] for row in connection.exec_driver_sql("PRAGMA table_info(instagram_reels)")}
        if "video_url" not in reel_columns: connection.exec_driver_sql("ALTER TABLE instagram_reels ADD COLUMN video_url VARCHAR(1500) NOT NULL DEFAULT ''")
        if "cached_thumbnail_path" not in reel_columns: connection.exec_driver_sql("ALTER TABLE instagram_reels ADD COLUMN cached_thumbnail_path VARCHAR(500) NOT NULL DEFAULT ''")
        if "cached_video_path" not in reel_columns: connection.exec_driver_sql("ALTER TABLE instagram_reels ADD COLUMN cached_video_path VARCHAR(500) NOT NULL DEFAULT ''")
        cover_columns={row[1] for row in connection.exec_driver_sql("PRAGMA table_info(processed_covers)")}
        if cover_columns and "post_id" not in cover_columns:
            # SQLite cannot remove the old unique constraint in place. Keep the
            # legacy cover tables intact for history and create slot-based tables.
            connection.exec_driver_sql("ALTER TABLE scheduled_post_covers RENAME TO scheduled_post_covers_legacy")
            connection.exec_driver_sql("ALTER TABLE processed_covers RENAME TO processed_covers_legacy")
            connection.exec_driver_sql("CREATE TABLE processed_covers (id INTEGER NOT NULL PRIMARY KEY, campaign_id INTEGER NOT NULL REFERENCES campaigns(id), original_media_id INTEGER NOT NULL REFERENCES media_files(id), post_id INTEGER UNIQUE REFERENCES scheduled_posts(id), relative_path VARCHAR(500) NOT NULL, sha256 VARCHAR(64) NOT NULL, created_at DATETIME NOT NULL)")
            connection.exec_driver_sql("CREATE TABLE scheduled_post_covers (id INTEGER NOT NULL PRIMARY KEY, post_id INTEGER NOT NULL UNIQUE REFERENCES scheduled_posts(id), cover_id INTEGER NOT NULL REFERENCES processed_covers(id))")
        duplicate_slots=connection.exec_driver_sql("SELECT 1 FROM scheduled_posts GROUP BY campaign_id, account_id, position HAVING COUNT(*)>1 LIMIT 1").fetchone()
        if not duplicate_slots:
            connection.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduled_post_campaign_account_position ON scheduled_posts(campaign_id, account_id, position)")
        # Early builds created audit IDs as foreign keys. Audit must survive a
        # user deleting the referenced account/campaign, so migrate it once.
        audit_fks=connection.exec_driver_sql("PRAGMA foreign_key_list(application_audit_logs)").fetchall()
        if audit_fks:
            connection.exec_driver_sql("ALTER TABLE application_audit_logs RENAME TO application_audit_logs_legacy")
            connection.exec_driver_sql("CREATE TABLE application_audit_logs (id INTEGER NOT NULL PRIMARY KEY, event_type VARCHAR(80) NOT NULL, message TEXT NOT NULL DEFAULT '', campaign_id INTEGER, account_id INTEGER, created_at DATETIME NOT NULL)")
            connection.exec_driver_sql("INSERT INTO application_audit_logs (id,event_type,message,campaign_id,account_id,created_at) SELECT id,event_type,message,campaign_id,account_id,created_at FROM application_audit_logs_legacy")
            connection.exec_driver_sql("DROP TABLE application_audit_logs_legacy")
    media_server=uvicorn.Server(uvicorn.Config(media_app, host="127.0.0.1", port=settings.tunnel_media_port, log_level="warning", access_log=False))
    media_task=asyncio.create_task(media_server.serve())
    await tunnel.start()
    task=asyncio.create_task(scheduler())
    insights_task=asyncio.create_task(insights_scheduler())
    account_health_task=asyncio.create_task(account_health_scheduler())
    try:
        yield
    finally:
        task.cancel(); insights_task.cancel(); account_health_task.cancel(); media_server.should_exit=True; media_task.cancel(); await tunnel.stop()
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
class CampaignSetupIn(BaseModel): account_ids:list[int]=[]; source_ids:list[int]; script_ids:list[int]; start_date:date; days:int; intervals:list[str]; strategy:str="sequential"; cover_path:str=""; caption_list_id:int|None=None; caption_text:str=""
class ProcessIn(BaseModel): source_ids:list[int]
class ScheduleIn(BaseModel): account_id:int; processed_media_id:int; caption:str=""; scheduled_for:datetime; position:int=0
class GenerateScheduleIn(BaseModel): start_date:date; days:int; intervals:list[str]; strategy:str="sequential"
class CampaignDefaultsIn(BaseModel): intervals:list[str]=["11:00-13:00"]; days:int=7; strategy:str="sequential"; script_ids:list[int]=[]; cover_path:str=""; caption_list_id:int|None=None; caption_text:str=""
class LoginIn(BaseModel): email:str; password:str

def progress_file(campaign_id:int) -> Path:
    return settings.data_dir/"workspaces"/str(campaign_id)/"generation-progress.json"

def save_generation_progress(campaign_id:int, **values):
    """Progresso fora do SQLite: ele aparece mesmo durante a transação longa."""
    path=progress_file(campaign_id); path.parent.mkdir(parents=True,exist_ok=True)
    # Um pedido de exclusão pode chegar enquanto o lote está no FFmpeg. As
    # atualizações normais de progresso não podem apagar esse sinal.
    previous=load_generation_progress(campaign_id) or {}
    if previous.get("deletion_requested") and "deletion_requested" not in values:
        values["deletion_requested"]=True
    payload={"campaign_id":campaign_id,"updated_at":datetime.utcnow().isoformat(),**values}
    temporary=path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
    temporary.replace(path)

def load_generation_progress(campaign_id:int):
    path=progress_file(campaign_id)
    try: return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError,json.JSONDecodeError): return None

def generation_cancelled(session: Session, campaign_id: int) -> bool:
    """Reads the cancellation flag without flushing the current batch's results."""
    return session.execute(
        select(Campaign.status).where(Campaign.id==campaign_id).execution_options(autoflush=False)
    ).scalar_one_or_none()==CampaignStatus.CANCELLED

def discard_processed_files_for_terminal_posts(session: Session, campaign_id: int) -> int:
    """Descarta arquivos de trabalho que já não podem mais ser publicados.

    Mantemos só o metadado no post cancelado/publicado para o histórico; o
    vídeo processado em si nunca precisa permanecer no disco ou na Biblioteca.
    """
    terminal=[PostStatus.PUBLISHED,PostStatus.CANCELLED,PostStatus.SKIPPED]
    removed=0
    posts=list(session.scalars(select(ScheduledPost).where(ScheduledPost.campaign_id==campaign_id, ScheduledPost.status.in_(terminal))))
    for post in posts:
        media=session.get(Media,post.processed_media_id)
        if not media: continue
        active_uses=session.scalar(select(func.count()).select_from(ScheduledPost).where(
            ScheduledPost.processed_media_id==media.id,
            ScheduledPost.status.not_in(terminal)
        )) or 0
        if not active_uses and data_path(media.relative_path).is_file():
            data_path(media.relative_path).unlink(missing_ok=True)
            media.status="Arquivo temporário descartado"
            removed+=1
    return removed

def purge_campaign(session: Session, campaign_id: int) -> bool:
    """Remove uma campanha somente quando nenhuma rotina usa seus registros.

    A geração roda em segundo plano e mantém referências aos registros de
    execução do lote atual. Por isso o endpoint de exclusão nunca pode apagar
    esses registros enquanto a campanha ainda está PROCESSING.
    """
    campaign=session.get(Campaign,campaign_id)
    if not campaign:
        return False
    post_ids=select(ScheduledPost.id).where(ScheduledPost.campaign_id==campaign_id)
    legacy_links=session.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='scheduled_post_covers_legacy'")).scalar()
    if legacy_links:
        session.execute(text("DELETE FROM scheduled_post_covers_legacy WHERE post_id IN (SELECT id FROM scheduled_posts WHERE campaign_id=:campaign_id)"),{"campaign_id":campaign_id})
    session.execute(delete(PublicationAttempt).where(PublicationAttempt.post_id.in_(post_ids)))
    session.execute(delete(ScheduledPostCover).where(ScheduledPostCover.post_id.in_(post_ids)))
    session.execute(delete(ProcessedCover).where(ProcessedCover.campaign_id==campaign_id))
    session.execute(delete(ScheduledPost).where(ScheduledPost.campaign_id==campaign_id))
    legacy_covers=session.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='processed_covers_legacy'")).scalar()
    if legacy_covers:
        session.execute(text("DELETE FROM processed_covers_legacy WHERE campaign_id=:campaign_id"),{"campaign_id":campaign_id})
    session.execute(delete(ProcessingExecution).where(ProcessingExecution.campaign_id==campaign_id))
    session.execute(delete(CampaignScheduleRule).where(CampaignScheduleRule.campaign_id==campaign_id))
    session.execute(delete(CampaignAccountExclusion).where(CampaignAccountExclusion.campaign_id==campaign_id))
    session.execute(delete(CampaignAccount).where(CampaignAccount.campaign_id==campaign_id))
    session.execute(delete(CampaignSourceMedia).where(CampaignSourceMedia.campaign_id==campaign_id))
    session.execute(delete(CampaignScript).where(CampaignScript.campaign_id==campaign_id))
    session.delete(campaign)
    # Após apagar a campanha, registros processados que não pertencem a nenhum
    # post restante são lixo de trabalho e podem ser removidos por completo.
    session.flush()
    for media in list(session.scalars(select(Media).where(Media.kind=="processed"))):
        if not session.scalar(select(func.count()).select_from(ScheduledPost).where(ScheduledPost.processed_media_id==media.id)):
            data_path(media.relative_path).unlink(missing_ok=True)
            session.delete(media)
    commit_with_retry(session)
    progress_file(campaign_id).unlink(missing_ok=True)
    return True
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
    now=datetime.utcnow()
    return [{"id":a.id,"username":a.username,"nome":a.display_name,"ativo":a.active,"conectada_em":a.connected_at,"expira_em":a.token_expires_at,"verificada_em":a.last_verified_at,"erro":a.last_error,"sincronizacao_devida_em":a.campaign_sync_due_at,"sincronizada_em":a.campaign_sync_completed_at,"apta":account_is_eligible(a,now),"status":"APTA" if account_is_eligible(a,now) else ("TOKEN_EXPIRADO" if a.token_expires_at and a.token_expires_at<=now else "COM_ERRO" if a.last_error else "DESCONECTADA")} for a in s.scalars(select(InstagramAccount).where(InstagramAccount.deleted_at.is_(None)).order_by(InstagramAccount.connected_at.desc()))]

@app.post("/api/meta/accounts/refresh-health")
async def refresh_accounts_health():
    result=await run_account_health_check(force=True)
    return result or {"checked":0,"healthy":0,"removed":0,"transient":0}

@app.get("/api/account-campaign-sync-settings")
def account_campaign_sync_settings(s:Session=Depends(db)):
    return {"delay_days":account_campaign_sync_delay_days(s)}

@app.put("/api/account-campaign-sync-settings")
def save_account_campaign_sync_settings(delay_days:int=Body(...,embed=True),s:Session=Depends(db)):
    if delay_days<0 or delay_days>365: raise HTTPException(422,"Informe entre 0 e 365 dias")
    item=s.get(ApplicationSetting,"account_campaign_sync_delay_days") or ApplicationSetting(key="account_campaign_sync_delay_days")
    item.value=str(delay_days); s.add(item); commit_with_retry(s)
    return {"delay_days":delay_days}
@app.get("/api/meta/oauth/start")
def oauth_start(s:Session=Depends(db)):
    # OAuth settings can be changed through .env without taking the local app down.
    reload_runtime_settings()
    meta.require_config(); state=secrets.token_urlsafe(32); s.add(OAuthState(state=state)); s.commit()
    return RedirectResponse(meta.authorization_url(state))
@app.get("/api/meta/oauth/url")
def oauth_url(s:Session=Depends(db)):
    """Cria um link de autorização de uso único para ser aberto em qualquer navegador."""
    reload_runtime_settings()
    meta.require_config(); state=secrets.token_urlsafe(32); s.add(OAuthState(state=state)); s.commit()
    return {"url":meta.authorization_url(state)}
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
        account.username=profile.get("username",""); account.display_name=profile.get("name",account.username); account.profile_picture_url=profile.get("profile_picture_url",""); account.token_expires_at=expires; account.active=True; account.deleted_at=None; account.connected_at=datetime.utcnow(); account.last_verified_at=datetime.utcnow(); account.last_error=""
        days=schedule_account_campaign_sync(s,account)
        added,created=sync_account_to_active_campaigns(s,account,not_before=account.campaign_sync_due_at)
        account.campaign_sync_completed_at=datetime.utcnow()
        audit(s,"ACCOUNT_RECONNECTED",f"Conta reconectada e validada via OAuth; {added} campanha(s) vinculada(s), {created} horário(s) futuro(s) criado(s) após o prazo de {days} dia(s).",account_id=account.id)
        commit_with_retry(s)
        return HTMLResponse("<script>window.opener&&window.opener.location.reload();window.close()</script><h2>Conta conectada com sucesso.</h2><p>Você já pode fechar esta janela e voltar ao Reels Manager.</p>")
    except HTTPException as e: return HTMLResponse(f"<h2>Não foi possível conectar a conta.</h2><p>{e.detail}</p>",e.status_code)
def delete_account_safely(s: Session, item: InstagramAccount) -> None:
    """Remove the account from operation but retain published Reel history and insights."""
    account_id=item.id
    campaign_ids=list(s.scalars(select(CampaignAccount.campaign_id).where(CampaignAccount.account_id==account_id)))
    s.query(ScheduledPost).filter(ScheduledPost.account_id==account_id,ScheduledPost.status.in_([PostStatus.PENDING,PostStatus.CLAIMED,PostStatus.UPLOADING,PostStatus.WAITING_META,PostStatus.PUBLISHING,PostStatus.PAUSED])).update({ScheduledPost.status:PostStatus.CANCELLED},synchronize_session=False)
    s.execute(delete(CampaignAccount).where(CampaignAccount.account_id==account_id))
    s.execute(delete(CampaignAccountExclusion).where(CampaignAccountExclusion.account_id==account_id))
    for campaign_id in campaign_ids:
        if not s.scalar(select(func.count()).select_from(CampaignAccount).where(CampaignAccount.campaign_id==campaign_id)):
            campaign=s.get(Campaign,campaign_id)
            if campaign and campaign.status==CampaignStatus.ACTIVE: campaign.status=CampaignStatus.PAUSED
    item.active=False
    item.encrypted_token=""
    item.token_expires_at=None
    item.campaign_sync_due_at=None
    item.campaign_sync_completed_at=datetime.utcnow()
    item.deleted_at=datetime.utcnow()
    audit(s,"ACCOUNT_REMOVED","Conta removida manualmente; vínculos e agendamentos futuros foram cancelados. Histórico de Reels e insights preservado.",account_id=account_id)

def remove_cached_insight_files(paths: list[str]) -> None:
    for relative_path in set(paths):
        try:
            path=data_path(relative_path)
            if path.is_file(): path.unlink()
        except OSError:
            pass

@app.delete("/api/meta/accounts")
def remove_accounts_bulk(account_ids:list[int]=Body(...),s:Session=Depends(db)):
    ids=list(dict.fromkeys(account_ids))
    if not ids: raise HTTPException(400,"Selecione ao menos uma conta")
    removed=[]; missing=[]
    for account_id in ids:
        item=s.get(InstagramAccount,account_id)
        if not item: missing.append(account_id); continue
        delete_account_safely(s,item); removed.append(account_id)
    commit_with_retry(s)
    return {"removed":removed,"missing":missing}
@app.delete("/api/meta/accounts/{account_id}")
def remove_account(account_id:int,s:Session=Depends(db)):
    item=s.get(InstagramAccount,account_id)
    if not item: raise HTTPException(404,"Conta não encontrada")
    delete_account_safely(s,item)
    commit_with_retry(s)
    return {"ok":True}
@app.get("/api/dashboard")
def dashboard(period:str="total",s:Session=Depends(db)):
    now=datetime.utcnow(); windows={"24h":timedelta(hours=24),"7d":timedelta(days=7),"30d":timedelta(days=30)}
    period=period if period in {"total",*windows} else "total"; cutoff=now-windows[period] if period in windows else None
    healthy=[account for account in s.scalars(select(InstagramAccount)) if account_is_eligible(account,now)]
    healthy_ids={account.id for account in healthy}
    posts=[post for post in s.scalars(select(ScheduledPost)) if post.account_id in healthy_ids]
    queued={PostStatus.PENDING,PostStatus.CLAIMED,PostStatus.UPLOADING,PostStatus.WAITING_META,PostStatus.PUBLISHING}
    future=[post for post in posts if post.status in queued and post.scheduled_for>=now and (not cutoff or post.scheduled_for<=now+windows[period])]
    # "Pendentes" no painel não são publicações esperando horário. São apenas
    # slots que a geração ainda precisa processar e materializar no banco.
    pending=0
    for campaign in s.scalars(select(Campaign).where(Campaign.status==CampaignStatus.PROCESSING)):
        linked_ids=list(s.scalars(select(CampaignAccount.account_id).where(CampaignAccount.campaign_id==campaign.id)))
        if not any(account_id in healthy_ids for account_id in linked_ids): continue
        progress=load_generation_progress(campaign.id) or {}
        pending+=max(0,int(progress.get("total",0))-int(progress.get("completed",0)))
    published=[post for post in posts if post.status==PostStatus.PUBLISHED and (not cutoff or cutoff<=post.scheduled_for<=now)]
    upcoming=sorted(future,key=lambda post:post.scheduled_for)[:5]
    return {"period":period,"contas_aptas":len(healthy),"agendados":len(future),"pendentes":pending,"publicados":len(published),"proximas":[{"id":post.id,"quando":post.scheduled_for,"legenda":post.caption} for post in upcoming]}

@app.get("/api/insights/views-chart")
def insight_views_chart(period:str="24h",start:str|None=None,end:str|None=None,s:Session=Depends(db)):
    """Current views grouped by Reel publication hour/day for the chosen period."""
    now=datetime.utcnow()
    if period=="24h":
        first=(now.replace(minute=0,second=0,microsecond=0)-timedelta(hours=23)); totals={first+timedelta(hours=index):0 for index in range(24)}; cutoff=first
        def bucket(value:datetime): return value.replace(minute=0,second=0,microsecond=0)
    elif period in {"7d","30d"}:
        days=7 if period=="7d" else 30; first=(now.date()-timedelta(days=days-1)); totals={first+timedelta(days=index):0 for index in range(days)}; cutoff=datetime.combine(first,time.min)
        def bucket(value:datetime): return value.date()
    else:
        try: start_date=date.fromisoformat(start) if start else now.date()
        except ValueError: raise HTTPException(422,"Data inicial inválida")
        try: end_date=date.fromisoformat(end) if end else start_date
        except ValueError: raise HTTPException(422,"Data final inválida")
        if end_date<start_date: raise HTTPException(422,"A data final deve ser igual ou posterior à inicial")
        if (end_date-start_date).days>366: raise HTTPException(422,"Escolha um intervalo de até 366 dias")
        totals={start_date+timedelta(days=index):0 for index in range((end_date-start_date).days+1)}; cutoff=datetime.combine(start_date,time.min)
        def bucket(value:datetime): return value.date()
    for reel in s.scalars(select(InstagramReel)):
        # Insights são um histórico: Reels já publicados continuam no gráfico
        # mesmo se a conta cair depois. Só a fila operacional exclui contas inaptas.
        if not reel.published_at or reel.published_at<cutoff: continue
        key=bucket(reel.published_at)
        if key in totals: totals[key]+=reel.views
    return {"period":period,"points":[{"date":key.isoformat(),"views":views} for key,views in totals.items()]}
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
            "conta_apta":bool(s.get(InstagramAccount,p.account_id) and account_is_eligible(s.get(InstagramAccount,p.account_id))),
            "midia":s.get(Media,p.processed_media_id).original_name if s.get(Media,p.processed_media_id) else "",
            "erro":attempt.message if p.status==PostStatus.FAILED and attempt and attempt.status=="FAILED" else "",
        })
    return result
@app.get("/api/activity")
def activity(s:Session=Depends(db)):
    """Uma linha por post. Logs de scripts ficam nos detalhes da campanha, não poluem o histórico."""
    items=[]
    # Ordenamos depois de separar recentes e futuros. Limitar aqui antes da
    # ordenação escondia os primeiros dias de campanhas maiores.
    posts=s.scalars(select(ScheduledPost)).all()
    for post in posts:
        campaign=s.get(Campaign,post.campaign_id)
        account=s.get(InstagramAccount,post.account_id)
        media=s.get(Media,post.processed_media_id)
        attempt=s.scalar(select(PublicationAttempt).where(PublicationAttempt.post_id==post.id).order_by(PublicationAttempt.id.desc()))
        items.append({
            "id":f"post-{post.id}", "status":post.status,
            "title":f"@{account.username if account else 'conta removida'} · {media.original_name if media else 'Mídia removida'}",
            "campaign":campaign.name if campaign else "Campanha removida",
            "when":attempt.finished_at or attempt.created_at if attempt else post.scheduled_for,
            "scheduled_for":post.scheduled_for,
            "sort_when":attempt.finished_at or attempt.created_at if attempt else post.scheduled_for,
            "media_name":media.original_name if media else "Mídia removida",
            "detail":attempt.message if attempt and attempt.message else (f"Publicado na Meta: {attempt.meta_media_id}" if attempt and attempt.meta_media_id else ""),
            "running":post.status in {PostStatus.CLAIMED,PostStatus.UPLOADING,PostStatus.WAITING_META,PostStatus.PUBLISHING},
        })
    # Histórico prioriza o que acabou de acontecer; agendados ficam depois,
    # em ordem do próximo horário, para não esconder os publicados.
    items.sort(key=lambda item: (item["status"]==PostStatus.PENDING, -(item["sort_when"] or item["when"]).timestamp() if item["status"]!=PostStatus.PENDING else item["when"].timestamp()))
    for item in items: item.pop("sort_when",None)
    return items[:100]
@app.get("/api/activity/summary")
def activity_summary(s:Session=Depends(db)):
    return {
        "processed": s.query(Media).filter_by(kind="processed").count(),
        "processing": s.query(ProcessingExecution).filter_by(status="RUNNING").count(),
        "published": s.query(ScheduledPost).filter_by(status=PostStatus.PUBLISHED).count(),
        "pending": s.query(ScheduledPost).filter_by(status=PostStatus.PENDING).count(),
        "failed": s.query(ScheduledPost).filter_by(status=PostStatus.FAILED).count(),
    }
def saved_insight_winner_settings(session: Session) -> dict:
    def integer(key: str, default: int, minimum: int, maximum: int) -> int:
        item=session.get(ApplicationSetting,key)
        try: return min(maximum,max(minimum,int(item.value if item else default)))
        except (TypeError,ValueError): return default
    return {"limit":integer("insights_winners_limit",20,1,100),"minimum_views":integer("insights_winners_minimum_views",0,0,2_000_000_000)}

class InsightWinnerSettingsIn(BaseModel):
    limit: int=20
    minimum_views: int=0

@app.get("/api/insights/settings")
def get_insight_winner_settings(s:Session=Depends(db)):
    return saved_insight_winner_settings(s)

@app.put("/api/insights/settings")
def update_insight_winner_settings(payload:InsightWinnerSettingsIn,s:Session=Depends(db)):
    values={"insights_winners_limit":str(min(100,max(1,payload.limit))),"insights_winners_minimum_views":str(min(2_000_000_000,max(0,payload.minimum_views)))}
    for key,value in values.items():
        item=s.get(ApplicationSetting,key)
        if item: item.value=value
        else: s.add(ApplicationSetting(key=key,value=value))
    commit_with_retry(s)
    return saved_insight_winner_settings(s)

@app.get("/api/insights/reels/{reel_id}/thumbnail")
def cached_insight_thumbnail(reel_id:int,s:Session=Depends(db)):
    reel=s.get(InstagramReel,reel_id)
    if not reel or not reel.cached_thumbnail_path: raise HTTPException(404,"Miniatura salva não encontrada")
    target=data_path(reel.cached_thumbnail_path)
    if not target.is_file(): raise HTTPException(404,"Arquivo de miniatura não encontrado")
    return FileResponse(target,media_type="image/jpeg",headers={"Cache-Control":"private, max-age=86400"})

@app.get("/api/insights/reels/{reel_id}/video")
def cached_insight_video(reel_id:int,s:Session=Depends(db)):
    reel=s.get(InstagramReel,reel_id)
    if not reel or not reel.cached_video_path: raise HTTPException(404,"Vídeo salvo não encontrado")
    target=data_path(reel.cached_video_path)
    if not target.is_file(): raise HTTPException(404,"Arquivo de vídeo não encontrado")
    media_type="video/quicktime" if target.suffix.lower()==".mov" else "video/mp4"
    return FileResponse(target,media_type=media_type,headers={"Cache-Control":"private, max-age=86400"})

@app.get("/api/insights/reels")
def insight_reels(period:str="total",s:Session=Depends(db)):
    windows={"24h":timedelta(hours=24),"7d":timedelta(days=7),"30d":timedelta(days=30)}
    period=period if period in {"total",*windows} else "total"
    cutoff=datetime.utcnow()-windows[period] if period in windows else None
    winner_settings=saved_insight_winner_settings(s)
    rows=[]
    published_attempts={str(attempt.meta_media_id):attempt for attempt in s.scalars(select(PublicationAttempt).where(PublicationAttempt.status=="PUBLISHED",PublicationAttempt.meta_media_id!=""))}
    for reel in s.scalars(select(InstagramReel)).all():
        account=s.get(InstagramAccount,reel.account_id)
        # The period selector is deliberately based on when the Reel was
        # published, then uses its current official totals. This works from the
        # first sync; snapshot deltas cannot honestly calculate 7/30 days until
        # the application itself has accumulated that much history.
        if cutoff and (not reel.published_at or reel.published_at<cutoff):
            continue
        library_media=None
        # Reels publicados por este sistema trazem o ID da Meta na tentativa de
        # publicação. Daí percorremos post -> processado -> original, sem usar
        # aproximação por nome ou legenda.
        attempt=published_attempts.get(str(reel.meta_media_id))
        if attempt:
            post=s.get(ScheduledPost,attempt.post_id)
            processed=s.get(Media,post.processed_media_id) if post else None
            original=s.get(Media,processed.original_media_id) if processed and processed.original_media_id else None
            if original and original.kind=="original":
                library_media={"id":original.id,"name":original.original_name,"thumbnail_url":f"/api/media/{original.id}/thumbnail","video_url":f"/api/media/{original.id}/stream"}
        rows.append({"id":reel.id,"meta_media_id":reel.meta_media_id,"conta":account.username if account else "conta removida","caption":reel.caption,"permalink":reel.permalink,"thumbnail_url":reel.thumbnail_url,"cached_thumbnail_url":f"/api/insights/reels/{reel.id}/thumbnail" if reel.cached_thumbnail_path else "","cached_video_url":f"/api/insights/reels/{reel.id}/video" if reel.cached_video_path and data_path(reel.cached_video_path).is_file() else "","library_media":library_media,"published_at":reel.published_at,"views":reel.views,"likes":reel.likes,"comments":reel.comments,"growth":reel.views,"likes_value":reel.likes,"comments_value":reel.comments,"has_baseline":True})
    # Totals are over every Reel selected by the chosen publication period,
    # independently of the winner card cap/minimum.
    summary={"views":sum(item["views"] for item in rows),"likes":sum(item["likes"] for item in rows),"comments":sum(item["comments"] for item in rows),"reels":len(rows),"measured_reels":len(rows),"awaiting_history":0}
    ranked=[item for item in rows if item["views"]>=winner_settings["minimum_views"]]
    ranked.sort(key=lambda item:(item["growth"],item["views"]),reverse=True)
    return {"period":period,"reels":ranked[:winner_settings["limit"]],"summary":summary,"settings":winner_settings,"accounts":[{"id":account.id,"username":account.username,"error":account.last_insights_error,"synced_at":max([reel.synced_at for reel in s.scalars(select(InstagramReel).where(InstagramReel.account_id==account.id))],default=None)} for account in s.scalars(select(InstagramAccount).where(InstagramAccount.deleted_at.is_(None)))]}
@app.post("/api/insights/sync")
def request_insight_sync():
    threading.Thread(target=lambda: asyncio.run(run_insights_sync_if_due(True)),daemon=True,name="instagram-insights-sync").start()
    return {"accepted":True,"message":"Sincronização de insights iniciada."}
@app.get("/api/insights/status")
def insight_status(s:Session=Depends(db)):
    lock=s.get(SchedulerLock,"instagram-insights-sync"); now=datetime.utcnow()
    return {"updating":bool(lock and lock.locked_until and lock.locked_until>now),"last_run_at":lock.last_run_at if lock else None}
@app.get("/api/audit")
def audit_log(limit:int=100,s:Session=Depends(db)):
    """Audit trail for automatic account/campaign changes."""
    return [{"id":item.id,"type":item.event_type,"message":item.message,"campaign_id":item.campaign_id,"account_id":item.account_id,"created_at":item.created_at} for item in s.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(max(limit,1),500)))]
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
@app.post("/api/media/refresh-thumbnails")
def refresh_media_thumbnails(s:Session=Depends(db)):
    items=list(s.scalars(select(Media).where(Media.kind=="original")))
    # A geração usa FFmpeg e pode levar segundos por arquivo. Solte o SQLite
    # antes desse trabalho para não prender o painel inteiro.
    s.expunge_all(); s.close()
    return {"ok":True,"generated":sum(1 for item in items if thumbnail(item,force=True)),"total":len(items)}
@app.get("/api/media/{media_id}/thumbnail")
def media_thumbnail(media_id:int,s:Session=Depends(db)):
    item=s.get(Media,media_id)
    if not item: raise HTTPException(404,"Mídia não encontrada")
    # Não mantenha uma conexão do pool enquanto o FFmpeg extrai o frame. Abrir
    # a Biblioteca dispara muitos pedidos de miniatura em paralelo.
    s.expunge(item); s.close()
    image=thumbnail(item)
    if not image: raise HTTPException(404,"Não foi possível gerar a miniatura")
    return FileResponse(image,media_type="image/jpeg")
@app.get("/api/media/{media_id}/stream")
def stream_original_media(media_id:int,s:Session=Depends(db)):
    item=s.get(Media,media_id)
    if not item or item.kind!="original": raise HTTPException(404,"Vídeo original não encontrado")
    path=data_path(item.relative_path)
    if not path.is_file(): raise HTTPException(404,"O arquivo original não existe mais")
    media_type="video/mp4" if item.extension.lower()==".mp4" else "video/quicktime"
    return FileResponse(path,media_type=media_type,filename=item.original_name)
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
@app.delete("/api/media")
def remove_media_bulk(media_ids:list[int]=Body(...),s:Session=Depends(db)):
    ids=list(dict.fromkeys(media_ids))
    if not ids: raise HTTPException(400,"Select at least one media file")
    deleted=[]; skipped=[]; files=[]
    active_statuses=[PostStatus.PENDING,PostStatus.CLAIMED,PostStatus.UPLOADING,PostStatus.WAITING_META,PostStatus.PUBLISHING]
    for media_id in ids:
        item=s.get(Media,media_id)
        if not item: skipped.append({"id":media_id,"reason":"Media not found"}); continue
        in_campaign=s.scalar(select(func.count()).select_from(CampaignSourceMedia).where(CampaignSourceMedia.media_id==media_id))
        in_post=s.scalar(select(func.count()).select_from(ScheduledPost).where(ScheduledPost.processed_media_id==media_id,ScheduledPost.status.in_(active_statuses)))
        if in_campaign or in_post:
            skipped.append({"id":media_id,"reason":"Protected by a campaign or pending post"}); continue
        files.extend([data_path(item.relative_path),settings.data_dir/"media/thumbnails"/f"{item.sha256}.jpg"])
        s.delete(item); deleted.append(media_id)
    s.commit()
    for file in files: file.unlink(missing_ok=True)
    return {"deleted":deleted,"skipped":skipped}
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
        result.append({"id":x.id,"nome":x.name,"status":x.status,"progress":load_generation_progress(x.id),"cover_path":x.cover_path,"caption_list_id":x.caption_list_id,"caption_text":x.caption_text,"script_ids":list(s.scalars(select(CampaignScript.script_id).where(CampaignScript.campaign_id==x.id).order_by(CampaignScript.position))),"account_ids":list(s.scalars(select(CampaignAccount.account_id).where(CampaignAccount.campaign_id==x.id))),"source_ids":list(s.scalars(select(CampaignSourceMedia.media_id).where(CampaignSourceMedia.campaign_id==x.id))),"schedule":{"start_date":rule.start_date,"days":rule.days,"intervals":rule.intervals.split(","),"strategy":rule.strategy} if rule else None})
    return result
@app.get("/api/campaigns/{campaign_id}/progress")
def campaign_progress(campaign_id:int,s:Session=Depends(db)):
    campaign=s.get(Campaign,campaign_id)
    if not campaign: raise HTTPException(404,"Campanha não encontrada")
    return load_generation_progress(campaign_id) or {"campaign_id":campaign_id,"status":campaign.status,"completed":0,"total":0}
@app.post("/api/campaigns")
def create_campaign(body:CampaignIn,s:Session=Depends(db)):
    x=Campaign(**body.model_dump()); s.add(x); s.commit(); return {"id":x.id,"status":x.status}
@app.delete("/api/campaigns/{campaign_id}")
def delete_campaign(campaign_id:int,s:Session=Depends(db)):
    c=s.get(Campaign,campaign_id)
    if not c: raise HTTPException(404,"Campanha não encontrada")
    if c.status==CampaignStatus.PROCESSING:
        # O subprocesso atual termina, vê este estado e não cria mais posts.
        # A remoção definitiva ocorre na própria tarefa em segundo plano, após
        # ela abandonar as referências ORM do lote.
        s.query(ScheduledPost).filter(ScheduledPost.campaign_id==campaign_id, ScheduledPost.status.in_([PostStatus.PENDING,PostStatus.PAUSED,PostStatus.CLAIMED])).update({ScheduledPost.status:PostStatus.CANCELLED},synchronize_session=False)
        c.status=CampaignStatus.CANCELLED
        audit(s,"CAMPAIGN_DELETE_REQUESTED","Exclusão solicitada durante processamento; aguardando o lote atual parar com segurança.",campaign_id)
        commit_with_retry(s)
        save_generation_progress(campaign_id,status="CANCELLED",deletion_requested=True,message="Exclusão solicitada; o lote atual será descartado ao terminar.",finished_at=datetime.utcnow().isoformat())
        return {"ok":True,"pending_cleanup":True}
    purge_campaign(s,campaign_id)
    return {"ok":True}
@app.post("/api/campaigns/{campaign_id}/cancel")
def cancel_campaign(campaign_id:int,s:Session=Depends(db)):
    c=s.get(Campaign,campaign_id)
    if not c: raise HTTPException(404,"Campanha não encontrada")
    s.query(ScheduledPost).filter(ScheduledPost.campaign_id==campaign_id, ScheduledPost.status.in_([PostStatus.PENDING,PostStatus.PAUSED,PostStatus.CLAIMED])).update({ScheduledPost.status:PostStatus.CANCELLED},synchronize_session=False)
    c.status=CampaignStatus.CANCELLED; discarded=discard_processed_files_for_terminal_posts(s,campaign_id); audit(s,"CAMPAIGN_CANCELLED",f"Campanha cancelada pelo usuário; agendamentos futuros interrompidos. {discarded} arquivo(s) temporário(s) descartado(s).",campaign_id)
    commit_with_retry(s); save_generation_progress(campaign_id,status="CANCELLED",message="Cancelamento solicitado; o lote atual será encerrado sem iniciar outro.",finished_at=datetime.utcnow().isoformat())
    return {"ok":True,"status":c.status}
@app.put("/api/campaigns/{campaign_id}/setup")
def setup_campaign(campaign_id:int, body:CampaignSetupIn, s:Session=Depends(db)):
    c=s.get(Campaign,campaign_id)
    if not c or c.status not in (CampaignStatus.DRAFT,CampaignStatus.PROCESSING_FAILED,CampaignStatus.READY_TO_SCHEDULE): raise HTTPException(409,"Esta campanha não pode ser alterada agora")
    # Campaigns always start with every account that was successfully checked and
    # is publishable. `account_ids` remains accepted only for old clients.
    accounts=[account for account in s.scalars(select(InstagramAccount)).all() if account_is_eligible(account)]
    sources=list(s.scalars(select(Media).where(Media.id.in_(body.source_ids),Media.kind=="original")))
    scripts=list(s.scalars(select(Script).where(Script.id.in_(body.script_ids),Script.active==True)))
    if not accounts: raise HTTPException(422,"Não há contas saudáveis e aptas a publicar. Reconecte e valide uma conta antes de criar a campanha.")
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
def generate_schedule(campaign_id:int,body:GenerateScheduleIn,s:Session=Depends(db),background_claim:bool=False):
    c=s.get(Campaign,campaign_id)
    # The background endpoint reserves the campaign as PROCESSING before this worker starts.
    if background_claim and c and c.status==CampaignStatus.PROCESSING:
        c.status=CampaignStatus.READY_TO_SCHEDULE; s.commit()
    if not c or c.status not in (CampaignStatus.DRAFT,CampaignStatus.PROCESSING_FAILED,CampaignStatus.READY_TO_SCHEDULE): raise HTTPException(409,"Esta campanha não pode gerar uma nova agenda agora")
    if body.days<1 or body.days>366 or not body.intervals: raise HTTPException(422,"Informe dias e ao menos um intervalo")
    accounts=list(s.scalars(select(CampaignAccount.account_id).where(CampaignAccount.campaign_id==campaign_id)))
    sources=list(s.scalars(select(CampaignSourceMedia.media_id).where(CampaignSourceMedia.campaign_id==campaign_id)))
    caption_items=json.loads(s.get(CaptionList,c.caption_list_id).items_json) if c.caption_list_id and s.get(CaptionList,c.caption_list_id) else []
    if not accounts or not sources: raise HTTPException(422,"Selecione ao menos uma conta e uma mídia original")
    ranges=[]
    for item in body.intervals:
        # Aceita texto colado com rótulos, por exemplo "9h: 08:30-09:00",
        # mas só usa as faixas reais de horário encontradas nele.
        matches=re.findall(r"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})",item)
        if not matches: raise HTTPException(422,f"Intervalo inválido: {item}. Use HH:MM-HH:MM")
        for left,right in matches:
            try:
                a=datetime.strptime(left,"%H:%M").time(); b=datetime.strptime(right,"%H:%M").time()
                low=a.hour*60+a.minute; high=b.hour*60+b.minute
                if low==high: raise ValueError()
                if high<low: high+=24*60
                ranges.append((low,high))
            except ValueError: raise HTTPException(422,f"Intervalo inválido: {left}-{right}. Use HH:MM-HH:MM")
    post_ids=select(ScheduledPost.id).where(ScheduledPost.campaign_id==campaign_id)
    s.execute(delete(ScheduledPostCover).where(ScheduledPostCover.post_id.in_(post_ids)))
    s.execute(delete(ScheduledPost).where(ScheduledPost.campaign_id==campaign_id))
    c.status=CampaignStatus.PROCESSING; s.commit()
    # Primeiro montamos as ocorrências. A mídia ainda é original neste ponto;
    # a agenda só recebe registros depois de o lote devolver cada resultado validado.
    ordered=sources[:]
    if body.strategy=="random": random.shuffle(ordered)
    index=0; position=0; previous_caption_by_account={}; jobs=[]
    for day_offset in range(body.days):
        current=body.start_date+timedelta(days=day_offset)
        if current<date.today(): continue
        for low,high in ranges:
            for account_id in accounts:
                if current==date.today():
                    earliest=datetime.now()+timedelta(minutes=5)
                    if high < earliest.hour*60+earliest.minute: continue
                source_id=random.choice(sources) if body.strategy=="random" else ordered[index%len(ordered)]
                index+=1
                if c.caption_text: caption=c.caption_text
                elif caption_items:
                    choices=[text for text in caption_items if text!=previous_caption_by_account.get(account_id)] or caption_items
                    caption=random.choice(choices); previous_caption_by_account[account_id]=caption
                else: caption=""
                jobs.append({"slot_key":f"slot-{uuid.uuid4().hex}","source_id":source_id,"account_id":account_id,"current":current,"low":low,"high":high,"caption":caption})
    batch_size=max(1,min(settings.processing_batch_size,50))
    save_generation_progress(campaign_id,status="RUNNING",total=len(jobs),completed=0,scheduled=0,failed=0,batch_size=batch_size,message="Preparando os lotes de vídeos...",started_at=datetime.utcnow().isoformat())
    scheduled=0
    try:
        for first in range(0,len(jobs),batch_size):
            if generation_cancelled(s,campaign_id):
                save_generation_progress(campaign_id,status="CANCELLED",total=len(jobs),completed=first,scheduled=scheduled,failed=0,batch_size=batch_size,message="Campanha cancelada; nenhum novo lote será processado.",finished_at=datetime.utcnow().isoformat())
                return {"count":scheduled,"status":CampaignStatus.CANCELLED}
            batch=jobs[first:first+batch_size]
            names=[s.get(Media,item["source_id"]).original_name for item in batch]
            save_generation_progress(campaign_id,status="RUNNING",total=len(jobs),completed=first,scheduled=scheduled,failed=0,batch_size=batch_size,current_batch=f"{first+1}-{first+len(batch)}",current_media=names[0] if names else "",message=f"Processando lote {first//batch_size+1} com {len(batch)} vídeos...")
            # Cada item mantém uma cópia e uma saída exclusiva, embora o script
            # seja iniciado uma vez para o lote inteiro.
            results=process_slots_batch(s,campaign_id,batch)
            if generation_cancelled(s,campaign_id):
                for _,media,cover_data in results:
                    data_path(media.relative_path).unlink(missing_ok=True)
                    if cover_data: data_path(cover_data[0]).unlink(missing_ok=True)
                s.rollback()
                save_generation_progress(campaign_id,status="CANCELLED",total=len(jobs),completed=first,scheduled=scheduled,failed=0,batch_size=batch_size,message="Campanha cancelada após concluir o lote atual.",finished_at=datetime.utcnow().isoformat())
                return {"count":scheduled,"status":CampaignStatus.CANCELLED}
            for job,media,cover_data in results:
                target_account=s.get(InstagramAccount,job["account_id"])
                if not target_account or not account_is_eligible(target_account):
                    data_path(media.relative_path).unlink(missing_ok=True); s.delete(media)
                    if cover_data: data_path(cover_data[0]).unlink(missing_ok=True)
                    continue
                effective_low=job["low"]
                if job["current"]==date.today():
                    earliest=datetime.now()+timedelta(minutes=5)
                    effective_low=max(job["low"],earliest.hour*60+earliest.minute)
                if effective_low>job["high"]:
                    data_path(media.relative_path).unlink(missing_ok=True); s.delete(media)
                    if cover_data: data_path(cover_data[0]).unlink(missing_ok=True)
                    continue
                minute=random.randint(effective_low,job["high"]); when=datetime.combine(job["current"],time())+timedelta(minutes=minute)
                post=ScheduledPost(campaign_id=campaign_id,account_id=job["account_id"],processed_media_id=media.id,caption=job["caption"],scheduled_for=when,position=position)
                s.add(post); s.flush()
                if cover_data:
                    cover=ProcessedCover(campaign_id=campaign_id,original_media_id=job["source_id"],post_id=post.id,relative_path=cover_data[0],sha256=cover_data[1])
                    s.add(cover); s.flush(); s.add(ScheduledPostCover(post_id=post.id,cover_id=cover.id))
                position+=1; scheduled+=1
            # Torna este lote disponível para o scheduler imediatamente. Assim
            # uma publicação próxima não espera todos os demais lotes.
            commit_with_retry(s)
            save_generation_progress(campaign_id,status="RUNNING",total=len(jobs),completed=first+len(batch),scheduled=scheduled,failed=0,batch_size=batch_size,current_batch=f"{first+1}-{first+len(batch)}",message="Lote validado; preparando o próximo...")
        if generation_cancelled(s,campaign_id):
            save_generation_progress(campaign_id,status="CANCELLED",total=len(jobs),completed=len(jobs),scheduled=scheduled,failed=0,batch_size=batch_size,message="Campanha cancelada.",finished_at=datetime.utcnow().isoformat())
            return {"count":scheduled,"status":CampaignStatus.CANCELLED}
        # Uma campanha só pode ficar ativa se existir ao menos uma publicação
        # futura materializada. Sem isso (por exemplo, todos os intervalos já
        # passaram hoje), "Ativa" seria enganoso e não haveria progresso nem
        # nada para o scheduler executar.
        c=s.get(Campaign,campaign_id)
        if scheduled==0:
            c.status=CampaignStatus.PROCESSING_FAILED
            commit_with_retry(s)
            save_generation_progress(campaign_id,status="FAILED",total=len(jobs),completed=len(jobs),scheduled=0,failed=0,batch_size=batch_size,message="Nenhum horário futuro disponível para agendar. Ajuste a data inicial ou os intervalos.",finished_at=datetime.utcnow().isoformat())
            return {"count":0,"status":c.status}
        c.status=CampaignStatus.ACTIVE; commit_with_retry(s)
        save_generation_progress(campaign_id,status="COMPLETED",total=len(jobs),completed=len(jobs),scheduled=scheduled,failed=0,batch_size=batch_size,message=f"Concluído: {scheduled} posts agendados.",finished_at=datetime.utcnow().isoformat())
        return {"count":position,"status":c.status}
    except Exception as exc:
        s.rollback()
        c=s.get(Campaign,campaign_id); c.status=CampaignStatus.PROCESSING_FAILED; s.commit()
        prior=load_generation_progress(campaign_id) or {}
        save_generation_progress(campaign_id,status="FAILED",total=prior.get("total",0),completed=prior.get("completed",0),scheduled=prior.get("scheduled",0),failed=1,batch_size=prior.get("batch_size",batch_size),message="O processamento parou com erro.",error=str(exc)[:2000],finished_at=datetime.utcnow().isoformat())
        raise HTTPException(422,f"O processamento falhou antes de concluir a agenda: {exc}")
def run_schedule_background(campaign_id:int,body:GenerateScheduleIn):
    with DbSession() as session:
        try:
            result=generate_schedule(campaign_id,body,session,True)
            # A exclusão durante PROCESSING é intencionalmente em duas fases:
            # primeiro cancela, depois esta própria tarefa remove os registros
            # após o subprocesso encerrar e soltar suas referências ORM.
            progress=load_generation_progress(campaign_id) or {}
            if result.get("status")==CampaignStatus.CANCELLED and progress.get("deletion_requested"):
                purge_campaign(session,campaign_id)
        except Exception as exc:
            # Falhas na preparação não podem deixar a campanha muda em READY.
            session.rollback()
            campaign=session.get(Campaign,campaign_id)
            if campaign and campaign.status not in (CampaignStatus.ACTIVE,CampaignStatus.CANCELLED):
                campaign.status=CampaignStatus.PROCESSING_FAILED
                session.commit()
            prior=load_generation_progress(campaign_id) or {}
            save_generation_progress(campaign_id,status="FAILED",total=prior.get("total",0),completed=prior.get("completed",0),scheduled=prior.get("scheduled",0),failed=1,batch_size=prior.get("batch_size",settings.processing_batch_size),message="A preparação automática parou com erro.",error=str(exc)[:2000],finished_at=datetime.utcnow().isoformat())

def resume_interrupted_campaign_generations():
    """Recupera uma geração interrompida apenas quando o serviço inicia."""
    pending:list[tuple[int,GenerateScheduleIn]]=[]
    with DbSession() as session:
        campaigns=list(session.scalars(select(Campaign).where(Campaign.status.in_([CampaignStatus.READY_TO_SCHEDULE,CampaignStatus.PROCESSING]))))
        for campaign in campaigns:
            rule=session.scalar(select(CampaignScheduleRule).where(CampaignScheduleRule.campaign_id==campaign.id))
            if not rule: continue
            try:
                body=GenerateScheduleIn(start_date=date.fromisoformat(rule.start_date),days=rule.days,intervals=[item for item in rule.intervals.split(",") if item],strategy=rule.strategy)
            except (TypeError,ValueError) as exc:
                campaign.status=CampaignStatus.PROCESSING_FAILED
                save_generation_progress(campaign.id,status="FAILED",total=0,completed=0,scheduled=0,failed=1,message="A agenda automática tem uma configuração inválida.",error=str(exc)[:2000],finished_at=datetime.utcnow().isoformat())
                continue
            campaign.status=CampaignStatus.PROCESSING
            pending.append((campaign.id,body))
        session.commit()
    for campaign_id,body in pending:
        save_generation_progress(campaign_id,status="RUNNING",total=0,completed=0,scheduled=0,failed=0,message="Retomando a preparação automática da campanha...")
        threading.Thread(target=run_schedule_background,args=(campaign_id,body),daemon=True,name=f"schedule-resume-{campaign_id}").start()
@app.post("/api/campaigns/{campaign_id}/start-generation")
def start_generation(campaign_id:int,body:GenerateScheduleIn,s:Session=Depends(db)):
    campaign=s.get(Campaign,campaign_id)
    allowed=(CampaignStatus.DRAFT,CampaignStatus.PROCESSING_FAILED,CampaignStatus.READY_TO_SCHEDULE)
    if not campaign or campaign.status not in allowed: raise HTTPException(409,"Campaign is already processing or cannot be scheduled")
    if body.days<1 or body.days>366 or not body.intervals: raise HTTPException(422,"Inform days and at least one interval")
    account_count=s.scalar(select(func.count()).select_from(CampaignAccount).where(CampaignAccount.campaign_id==campaign_id)) or 0
    campaign.status=CampaignStatus.PROCESSING; s.commit()
    threading.Thread(target=run_schedule_background,args=(campaign_id,body),daemon=True,name=f"schedule-{campaign_id}").start()
    return {"accepted":True,"status":CampaignStatus.PROCESSING,"count":account_count*body.days*len(body.intervals)}
@app.post("/api/campaigns/{campaign_id}/activate")
def activate(campaign_id:int,s:Session=Depends(db)):
    c=s.get(Campaign,campaign_id)
    if not c or c.status!=CampaignStatus.SCHEDULE_GENERATED: raise HTTPException(409,"Gere a agenda antes de ativar")
    c.status=CampaignStatus.ACTIVE; s.commit(); return {"status":c.status}
frontend=Path(__file__).resolve().parents[1]/"frontend"/"dist"
if frontend.exists(): app.mount("/",StaticFiles(directory=frontend,html=True),name="frontend")
