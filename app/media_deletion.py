"""Remove library originals without breaking already scheduled publications."""
from pathlib import Path

from sqlalchemy import delete, select

from .models import (Campaign, CampaignSourceMedia, CampaignStatus, Media,
                     ProcessedCover, ProcessingExecution, ScheduledPost)


DELETED_STATUS = "Excluída"


def delete_library_media(session, media_ids: list[int], data_dir: Path) -> dict:
    deleted, skipped, retained, detached, paths = [], [], [], 0, []
    for media_id in dict.fromkeys(media_ids):
        item = session.get(Media, media_id)
        if not item or item.kind != "original" or item.status == DELETED_STATUS:
            skipped.append({"id": media_id, "reason": "Mídia original não encontrada"})
            continue
        campaigns = list(session.scalars(select(CampaignSourceMedia.campaign_id).where(
            CampaignSourceMedia.media_id == media_id)))
        generating = bool(campaigns and session.scalar(select(Campaign.id).where(
            Campaign.id.in_(campaigns), Campaign.status == CampaignStatus.PROCESSING).limit(1)))
        running = bool(campaigns and session.scalar(select(ProcessingExecution.id).where(
            ProcessingExecution.campaign_id.in_(campaigns),
            ProcessingExecution.status == "RUNNING").limit(1)))
        keep_file = generating or running
        has_children = bool(session.scalar(select(Media.id).where(
            Media.original_media_id == media_id).limit(1)) or
            session.scalar(select(ProcessedCover.id).where(
                ProcessedCover.original_media_id == media_id).limit(1)) or
            session.scalar(select(ScheduledPost.id).where(
                ScheduledPost.processed_media_id == media_id).limit(1)))
        detached += len(campaigns)
        session.execute(delete(CampaignSourceMedia).where(CampaignSourceMedia.media_id == media_id))
        if has_children or keep_file:
            # Historical processed posts/covers still reference this row.
            item.status = DELETED_STATUS
            if keep_file:
                retained.append(media_id)
        else:
            session.delete(item)
        if not keep_file:
            paths.append(data_dir / item.relative_path)
        deleted.append(media_id)
    session.commit()
    # Files are removed only after the database no longer exposes them.
    for path in paths:
        path.unlink(missing_ok=True)
    return {"deleted": deleted, "skipped": skipped,
            "detached_campaigns": detached, "retained_for_processing": retained}


def cleanup_deleted_original_files(session, data_dir: Path) -> int:
    """Free deferred files once no generation can still read a source."""
    if session.scalar(select(Campaign.id).where(
        Campaign.status == CampaignStatus.PROCESSING).limit(1)) or session.scalar(
            select(ProcessingExecution.id).where(
                ProcessingExecution.status == "RUNNING").limit(1)):
        return 0
    removed = 0
    for item in session.scalars(select(Media).where(
        Media.kind == "original", Media.status == DELETED_STATUS)):
        path = data_dir / item.relative_path
        if path.is_file():
            path.unlink()
            removed += 1
    return removed
