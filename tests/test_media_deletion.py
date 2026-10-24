"""Synthetic library deletion tests with foreign keys enabled."""
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session

from app.db import Base
from app.media_deletion import DELETED_STATUS, cleanup_deleted_original_files, delete_library_media
from app.models import (Campaign, CampaignSourceMedia, CampaignStatus, Media,
                        PostStatus, ScheduledPost)


class MediaDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = create_engine("sqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        event.listen(self.engine, "connect", lambda dbapi, _: dbapi.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)

    def media(self, name, kind="original", original_id=None):
        relative = f"media/{name}.mp4"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic")
        item = Media(original_name=name, stored_name=f"{name}.mp4", relative_path=relative,
                     kind=kind, extension=".mp4", size=9, sha256=name,
                     status="Disponível", original_media_id=original_id)
        self.session.add(item)
        self.session.flush()
        return item

    def test_campaign_media_disappears_without_breaking_scheduled_post(self):
        source = self.media("source")
        campaign = Campaign(name="synthetic", status=CampaignStatus.ACTIVE)
        self.session.add(campaign)
        self.session.flush()
        self.session.add(CampaignSourceMedia(campaign_id=campaign.id, media_id=source.id))
        processed = self.media("processed", "processed", source.id)
        post = ScheduledPost(campaign_id=campaign.id, account_id=1,
                             processed_media_id=processed.id, scheduled_for=__import__("datetime").datetime.now(),
                             status=PostStatus.PENDING)
        self.session.add(post)
        self.session.commit()
        result = delete_library_media(self.session, [source.id], self.root)
        self.assertEqual(result["deleted"], [source.id])
        self.assertEqual(result["detached_campaigns"], 1)
        self.assertEqual(self.session.get(Media, source.id).status, DELETED_STATUS)
        self.assertTrue((self.root / source.relative_path).exists())
        self.assertEqual(cleanup_deleted_original_files(self.session, self.root), 1)
        self.assertFalse((self.root / source.relative_path).exists())
        self.assertIsNotNone(self.session.get(ScheduledPost, post.id))
        self.assertFalse(self.session.scalar(select(CampaignSourceMedia.id)))

    def test_unreferenced_media_is_removed_from_database_and_disk(self):
        source = self.media("unused")
        self.session.commit()
        media_id, path = source.id, self.root / source.relative_path
        result = delete_library_media(self.session, [media_id, media_id, 999999], self.root)
        self.assertEqual(result["deleted"], [media_id])
        self.assertEqual(len(result["skipped"]), 1)
        self.assertIsNone(self.session.get(Media, media_id))
        self.assertFalse(path.exists())

    def test_legacy_windows_relative_path_is_removed(self):
        source = self.media("legacy")
        path = self.root / source.relative_path
        source.relative_path = source.relative_path.replace("/", "\\")
        self.session.commit()
        delete_library_media(self.session, [source.id], self.root)
        self.assertFalse(path.exists())

    def test_legacy_cover_reference_keeps_historical_row(self):
        source = self.media("legacy-cover")
        self.session.execute(text("CREATE TABLE processed_covers_legacy (id INTEGER PRIMARY KEY, original_media_id INTEGER NOT NULL REFERENCES media_files(id))"))
        self.session.execute(text("INSERT INTO processed_covers_legacy (original_media_id) VALUES (:id)"), {"id": source.id})
        self.session.commit()
        result = delete_library_media(self.session, [source.id], self.root)
        self.assertEqual(result["deleted"], [source.id])
        self.assertEqual(self.session.get(Media, source.id).status, DELETED_STATUS)
        self.assertFalse((self.root / source.relative_path).exists())

    def test_processing_campaign_keeps_source_file_until_job_finishes(self):
        source = self.media("running")
        campaign = Campaign(name="synthetic", status=CampaignStatus.PROCESSING)
        self.session.add(campaign)
        self.session.flush()
        self.session.add(CampaignSourceMedia(campaign_id=campaign.id, media_id=source.id))
        self.session.commit()
        result = delete_library_media(self.session, [source.id], self.root)
        self.assertEqual(result["retained_for_processing"], [source.id])
        self.assertEqual(self.session.get(Media, source.id).status, DELETED_STATUS)
        self.assertTrue((self.root / source.relative_path).exists())
        self.assertEqual(cleanup_deleted_original_files(self.session, self.root), 0)
        campaign.status = CampaignStatus.ACTIVE
        self.session.commit()
        self.assertEqual(cleanup_deleted_original_files(self.session, self.root), 1)
        self.assertFalse((self.root / source.relative_path).exists())


if __name__ == "__main__":
    unittest.main()
