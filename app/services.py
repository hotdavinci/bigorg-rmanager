import hashlib, shutil, subprocess, uuid, os
from datetime import datetime
from pathlib import Path
from sqlalchemy import select, delete
from .config import settings, data_path
from .models import Media, Campaign, CampaignStatus, ProcessingExecution, Script, CampaignScript, ProcessedCover

MEDIA_EXT={".mp4", ".mov"}; IMAGE_EXT={".jpg", ".jpeg", ".png", ".webp"}
def sha(path: Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024), b""): h.update(block)
    return h.hexdigest()
def dirs():
    for p in (settings.data_dir/"media/original", settings.data_dir/"media/processed", settings.data_dir/"media/covers", settings.data_dir/"media/thumbnails", settings.data_dir/"scripts", settings.data_dir/"captions", settings.data_dir/"workspaces"): p.mkdir(parents=True, exist_ok=True)
def copy_media(src: Path):
    if src.suffix.lower() not in MEDIA_EXT: raise ValueError("Apenas .mp4 e .mov são aceitos")
    dirs(); stored=f"{uuid.uuid4().hex}{src.suffix.lower()}"; dst=settings.data_dir/"media/original"/stored; shutil.copy2(src,dst)
    return Media(original_name=src.name, stored_name=stored, relative_path=str(dst.relative_to(settings.data_dir)), kind="original", extension=src.suffix.lower(), size=dst.stat().st_size, sha256=sha(dst))
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
            execution.status="FAILED"; execution.stderr=(execution.stderr+"\n"+str(exc))[-20000:]; execution.finished_at=datetime.utcnow(); raise
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
