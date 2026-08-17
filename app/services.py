import hashlib, shutil, subprocess, uuid, os, time as time_module
from datetime import datetime
from pathlib import Path
from sqlalchemy import select, delete
from sqlalchemy.exc import OperationalError
from .config import settings, data_path
from .models import Media, Campaign, CampaignStatus, ProcessingExecution, Script, CampaignScript, ProcessedCover

MEDIA_EXT={".mp4", ".mov"}; IMAGE_EXT={".jpg", ".jpeg", ".png", ".webp"}

def commit_with_retry(session, attempts: int=5):
    """Commits only short SQLite writes; never keep a transaction during FFmpeg."""
    for attempt in range(attempts):
        try:
            session.commit()
            return
        except OperationalError as exc:
            session.rollback()
            if "locked" not in str(exc).lower() or attempt == attempts-1:
                raise
            time_module.sleep(0.15*(attempt+1))
def sha(path: Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024), b""): h.update(block)
    return h.hexdigest()
def dirs():
    for p in (settings.data_dir/"media/original", settings.data_dir/"media/processed", settings.data_dir/"media/covers", settings.data_dir/"media/thumbnails", settings.data_dir/"scripts", settings.data_dir/"captions", settings.data_dir/"workspaces"): p.mkdir(parents=True, exist_ok=True)
def thumbnail(media: Media, force: bool=False) -> Path|None:
    source=data_path(media.relative_path)
    if not source.is_file(): return None
    dirs(); target=settings.data_dir/"media/thumbnails"/f"{media.sha256}.jpg"
    if target.is_file() and not force: return target
    if force: target.unlink(missing_ok=True)
    try:
        # The 0:00 frame is frequently black because of fade-ins or codec keyframes.
        run=subprocess.run([shutil.which("ffmpeg") or "ffmpeg","-y","-ss","1","-i",str(source),"-frames:v","1","-vf","scale=480:-2",str(target)],capture_output=True,timeout=45)
        return target if run.returncode==0 and target.is_file() else None
    except (OSError,subprocess.TimeoutExpired): return None
def copy_media(src: Path, original_name: str|None=None):
    if src.suffix.lower() not in MEDIA_EXT: raise ValueError("Apenas .mp4 e .mov são aceitos")
    dirs(); stored=f"{uuid.uuid4().hex}{src.suffix.lower()}"; dst=settings.data_dir/"media/original"/stored; shutil.copy2(src,dst)
    return Media(original_name=original_name or src.name, stored_name=stored, relative_path=str(dst.relative_to(settings.data_dir)), kind="original", extension=src.suffix.lower(), size=dst.stat().st_size, sha256=sha(dst))
def process(session, campaign_id: int, source_ids: list[int]):
    c=session.get(Campaign,campaign_id)
    scripts=list(session.scalars(select(Script).join(CampaignScript, CampaignScript.script_id==Script.id).where(CampaignScript.campaign_id==campaign_id).order_by(CampaignScript.position)))
    sources=list(session.scalars(select(Media).where(Media.id.in_(source_ids),Media.kind=="original")))
    cover_source=data_path(c.cover_path) if c and c.cover_path else None
    if not c or not scripts or len(sources)!=len(source_ids) or (cover_source and not cover_source.is_file()): raise ValueError("Campanha, scripts, mídias ou capa não encontrados")
    execution_id=uuid.uuid4().hex; root=settings.data_dir/"workspaces"/str(c.id)/execution_id; c.status=CampaignStatus.PROCESSING; session.commit(); last=None
    try:
        session.execute(delete(ProcessedCover).where(ProcessedCover.campaign_id==c.id))
        for source in sources:
            work=root/str(source.id); work.mkdir(parents=True)
            video=work/source.original_name; shutil.copy2(data_path(source.relative_path),video)
            if cover_source: shutil.copy2(cover_source, work/cover_source.name)
            before={p.name:sha(p) for p in work.iterdir() if p.is_file()}
            for script in scripts:
                script_file=data_path(script.relative_path); local_script=work/script_file.name; shutil.copy2(script_file,local_script)
                e=ProcessingExecution(campaign_id=c.id,script_id=script.id,workspace=str(work.relative_to(settings.data_dir))); session.add(e); session.commit(); last=e
                run=subprocess.run([settings.python_executable,local_script.name],cwd=work,capture_output=True,text=True,encoding="utf-8",errors="replace",env={**os.environ,"PYTHONIOENCODING":"utf-8"},timeout=settings.processing_timeout_seconds)
                e.stdout=run.stdout[-20000:]; e.stderr=run.stderr[-20000:]; e.exit_code=run.returncode; e.finished_at=datetime.utcnow(); e.status="SUCCESS" if run.returncode==0 else "FAILED"
                if run.returncode: raise RuntimeError(f"O script {script.name} falhou para {source.original_name}")
            videos=[p for p in work.iterdir() if p.suffix.lower() in MEDIA_EXT and (p.name not in before or sha(p)!=before[p.name])]
            covers=[p for p in work.iterdir() if p.suffix.lower() in IMAGE_EXT]
            if not videos: raise RuntimeError(f"Não foi possível identificar vídeo processado para {source.original_name}")
            final_video=videos[0]; final_cover=next((p for p in covers if not cover_source or p.name!=cover_source.name or sha(p)!=before.get(p.name)),covers[0] if covers else None)
            outdir=settings.data_dir/"media/processed"/str(c.id)/execution_id; outdir.mkdir(parents=True,exist_ok=True)
            vtarget=outdir/f"{uuid.uuid4().hex}{final_video.suffix.lower()}"; shutil.copy2(final_video,vtarget)
            session.add(Media(original_name=final_video.name,stored_name=vtarget.name,relative_path=str(vtarget.relative_to(settings.data_dir)),kind="processed",extension=vtarget.suffix.lower(),size=vtarget.stat().st_size,sha256=sha(vtarget),status="Processada",original_media_id=source.id))
            if final_cover:
                cdir=settings.data_dir/"media/covers"/str(c.id)/execution_id; cdir.mkdir(parents=True,exist_ok=True)
                ctarget=cdir/f"{uuid.uuid4().hex}{final_cover.suffix.lower()}"; shutil.copy2(final_cover,ctarget)
                session.add(ProcessedCover(campaign_id=c.id,original_media_id=source.id,relative_path=str(ctarget.relative_to(settings.data_dir)),sha256=sha(ctarget)))
        c.status=CampaignStatus.READY_TO_SCHEDULE
    except Exception as ex:
        c.status=CampaignStatus.PROCESSING_FAILED
        if last: last.status="FAILED"; last.stderr=(last.stderr+"\n"+str(ex))[-20000:]; last.finished_at=datetime.utcnow()
    session.commit(); return last

def process_slot(session, campaign_id: int, source_id: int, slot_key: str):
    """Creates a fresh processed video (and optional cover) for exactly one scheduled post."""
    campaign=session.get(Campaign,campaign_id)
    source=session.get(Media,source_id)
    scripts=list(session.scalars(select(Script).join(CampaignScript, CampaignScript.script_id==Script.id).where(CampaignScript.campaign_id==campaign_id).order_by(CampaignScript.position)))
    cover_source=data_path(campaign.cover_path) if campaign and campaign.cover_path else None
    if not campaign or not source or source.kind!="original" or not scripts: raise ValueError("Campanha, mídia original ou scripts não encontrados")
    if cover_source and not cover_source.is_file(): raise ValueError("A capa selecionada não existe mais")
    work=settings.data_dir/"workspaces"/str(campaign_id)/slot_key; work.mkdir(parents=True,exist_ok=False)
    video=work/source.original_name; shutil.copy2(data_path(source.relative_path),video)
    if cover_source: shutil.copy2(cover_source,work/cover_source.name)
    before={p.name:sha(p) for p in work.iterdir() if p.is_file()}
    for script in scripts:
        script_file=data_path(script.relative_path); local_script=work/script_file.name; shutil.copy2(script_file,local_script)
        execution=ProcessingExecution(campaign_id=campaign_id,script_id=script.id,workspace=str(work.relative_to(settings.data_dir)))
        session.add(execution); session.flush()
        try:
            run=subprocess.run([settings.python_executable,local_script.name],cwd=work,capture_output=True,text=True,encoding="utf-8",errors="replace",env={**os.environ,"PYTHONIOENCODING":"utf-8"},timeout=settings.processing_timeout_seconds)
            execution.stdout=run.stdout[-20000:]; execution.stderr=run.stderr[-20000:]; execution.exit_code=run.returncode; execution.finished_at=datetime.utcnow(); execution.status="SUCCESS" if run.returncode==0 else "FAILED"
            if run.returncode: raise RuntimeError(f"O script {script.name} falhou para {source.original_name}")
        except Exception as exc:
            execution.status="FAILED"; execution.stderr=(execution.stderr+"\n"+str(exc))[-20000:]; execution.finished_at=datetime.utcnow()
            commit_with_retry(session)
            raise
    videos=[p for p in work.iterdir() if p.suffix.lower() in MEDIA_EXT and (p.name not in before or sha(p)!=before[p.name])]
    if not videos: raise RuntimeError(f"Não foi possível identificar vídeo processado para {source.original_name}")
    final_video=videos[0]
    outdir=settings.data_dir/"media/processed"/str(campaign_id)/slot_key; outdir.mkdir(parents=True,exist_ok=True)
    target=outdir/f"{uuid.uuid4().hex}{final_video.suffix.lower()}"; shutil.copy2(final_video,target)
    media=Media(original_name=final_video.name,stored_name=target.name,relative_path=str(target.relative_to(settings.data_dir)),kind="processed",extension=target.suffix.lower(),size=target.stat().st_size,sha256=sha(target),status="Processada",original_media_id=source.id)
    session.add(media); session.flush()
    cover_result=None
    if cover_source:
        covers=[p for p in work.iterdir() if p.suffix.lower() in IMAGE_EXT]
        final_cover=next((p for p in covers if p.name!=cover_source.name or sha(p)!=before.get(p.name)), None)
        if not final_cover: raise RuntimeError("Não foi possível identificar a capa processada")
        cdir=settings.data_dir/"media/covers"/str(campaign_id)/slot_key; cdir.mkdir(parents=True,exist_ok=True)
        ctarget=cdir/f"{uuid.uuid4().hex}{final_cover.suffix.lower()}"; shutil.copy2(final_cover,ctarget)
        cover_result=(str(ctarget.relative_to(settings.data_dir)),sha(ctarget))
    return media, cover_result

def process_slots_batch(session, campaign_id: int, slots: list[dict]):
    """Processa várias cópias independentes na mesma workspace.

    Cada post recebe nomes com um identificador próprio. Assim, mesmo quando uma
    fonte se repete para contas diferentes, o arquivo resultante nunca é compartilhado.
    Scripts que varrem todos os arquivos da pasta rodam apenas uma vez por lote.
    """
    campaign=session.get(Campaign,campaign_id)
    scripts=list(session.scalars(select(Script).join(CampaignScript, CampaignScript.script_id==Script.id).where(CampaignScript.campaign_id==campaign_id).order_by(CampaignScript.position)))
    cover_source=data_path(campaign.cover_path) if campaign and campaign.cover_path else None
    if not campaign or not scripts or not slots: raise ValueError("Campanha, scripts ou lote não encontrados")
    if cover_source and not cover_source.is_file(): raise ValueError("A capa selecionada não existe mais")
    batch_id=f"batch-{uuid.uuid4().hex}"
    work=settings.data_dir/"workspaces"/str(campaign_id)/batch_id
    work.mkdir(parents=True,exist_ok=False)
    before={}; inputs=[]
    for index, slot in enumerate(slots):
        source=session.get(Media,slot["source_id"])
        if not source or source.kind!="original": raise ValueError("Mídia original não encontrada")
        token=f"post{index:03d}_{slot['slot_key'][-8:]}"
        video=work/f"{token}__video{source.extension.lower()}"
        shutil.copy2(data_path(source.relative_path),video); before[video.name]=sha(video)
        cover_name=None
        if cover_source:
            cover_name=f"{token}__cover{cover_source.suffix.lower()}"
            cover=work/cover_name; shutil.copy2(cover_source,cover); before[cover.name]=sha(cover)
        inputs.append({"slot":slot,"source":source,"token":token,"cover_name":cover_name})
    for script in scripts:
        script_file=data_path(script.relative_path); local_script=work/script_file.name; shutil.copy2(script_file,local_script)
        execution=ProcessingExecution(campaign_id=campaign_id,script_id=script.id,workspace=str(work.relative_to(settings.data_dir)))
        # Persist and RELEASE the SQLite writer before the user script starts.
        # FFmpeg can run for minutes; holding a transaction here blocks OAuth,
        # cancellation and the publication scheduler.
        session.add(execution); commit_with_retry(session)
        try:
            run=subprocess.run([settings.python_executable,local_script.name],cwd=work,capture_output=True,text=True,encoding="utf-8",errors="replace",env={**os.environ,"PYTHONIOENCODING":"utf-8"},timeout=settings.processing_timeout_seconds)
            execution.stdout=run.stdout[-20000:]; execution.stderr=run.stderr[-20000:]; execution.exit_code=run.returncode; execution.finished_at=datetime.utcnow(); execution.status="SUCCESS" if run.returncode==0 else "FAILED"
            commit_with_retry(session)
            if run.returncode: raise RuntimeError(f"O script {script.name} falhou no lote")
        except Exception as exc:
            execution.status="FAILED"; execution.stderr=(execution.stderr+"\n"+str(exc))[-20000:]; execution.finished_at=datetime.utcnow(); raise
    changed_videos=[p for p in work.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXT and (p.name not in before or sha(p)!=before[p.name])]
    changed_covers=[p for p in work.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT and (p.name not in before or sha(p)!=before[p.name])]
    if len(changed_videos)<len(inputs): raise RuntimeError(f"O lote gerou {len(changed_videos)} vídeos para {len(inputs)} posts")
    used_videos=set(); used_covers=set(); results=[]
    fallback_videos=iter(sorted(changed_videos,key=lambda p:p.name))
    fallback_covers=iter(sorted(changed_covers,key=lambda p:p.name))
    for item in inputs:
        matches=[p for p in changed_videos if item["token"] in p.name and p not in used_videos]
        final_video=matches[0] if matches else next((p for p in fallback_videos if p not in used_videos),None)
        if not final_video: raise RuntimeError("Não foi possível relacionar o resultado processado ao post")
        used_videos.add(final_video)
        slot_key=item["slot"]["slot_key"]; outdir=settings.data_dir/"media/processed"/str(campaign_id)/slot_key; outdir.mkdir(parents=True,exist_ok=True)
        target=outdir/f"{uuid.uuid4().hex}{final_video.suffix.lower()}"; shutil.copy2(final_video,target)
        media=Media(original_name=final_video.name,stored_name=target.name,relative_path=str(target.relative_to(settings.data_dir)),kind="processed",extension=target.suffix.lower(),size=target.stat().st_size,sha256=sha(target),status="Processada",original_media_id=item["source"].id)
        # The caller persists all result media/posts together at the end of the
        # batch.  Do not acquire the SQLite writer while files are being copied.
        session.add(media); cover_result=None
        if cover_source:
            cover_matches=[p for p in changed_covers if item["token"] in p.name and p not in used_covers]
            final_cover=cover_matches[0] if cover_matches else next((p for p in fallback_covers if p not in used_covers),None)
            if not final_cover: raise RuntimeError("Não foi possível relacionar a capa processada ao post")
            used_covers.add(final_cover); cdir=settings.data_dir/"media/covers"/str(campaign_id)/slot_key; cdir.mkdir(parents=True,exist_ok=True)
            ctarget=cdir/f"{uuid.uuid4().hex}{final_cover.suffix.lower()}"; shutil.copy2(final_cover,ctarget); cover_result=(str(ctarget.relative_to(settings.data_dir)),sha(ctarget))
        results.append((item["slot"],media,cover_result))
    # Os posts abaixo referenciam ``processed_media_id`` diretamente, sem um
    # relacionamento ORM. Gere os IDs agora, em uma escrita curta, antes de a
    # agenda usar cada mídia. Sem este flush o valor ainda é None e o SQLite
    # corretamente recusa o agendamento.
    session.flush()
    return results
