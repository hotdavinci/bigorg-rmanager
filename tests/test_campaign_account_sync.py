import tempfile
import unittest
import sys
import asyncio
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import config
from app.db import Base
from app.models import Campaign, CampaignAccount, CampaignScheduleRule, CampaignSourceMedia, CampaignStatus, InstagramAccount, Media, PostStatus, ScheduledPost, Script, CampaignScript, ProcessedCover, ScheduledPostCover
from app import main
from app import services


class CampaignAccountSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.previous_settings=config.settings
        self.previous_service_settings=services.settings
        self.test_settings=SimpleNamespace(data_dir=Path(self.temp.name),processing_batch_size=2,
            python_executable=sys.executable,processing_timeout_seconds=10,scheduler_max_attempts=3)
        config.settings=self.test_settings
        main.settings=self.test_settings
        services.settings=self.test_settings
        self.engine=create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session=sessionmaker(self.engine,expire_on_commit=False)

    def tearDown(self):
        config.settings=self.previous_settings
        main.settings=self.previous_settings
        services.settings=self.previous_service_settings
        self.temp.cleanup()

    def seed(self, session, days=2):
        account=InstagramAccount(meta_account_id="ig-1",username="healthy",encrypted_token="token",active=True,last_verified_at=datetime.utcnow())
        campaign=Campaign(name="Teste",status=CampaignStatus.ACTIVE)
        source=Media(original_name="original.mp4",stored_name="original.mp4",relative_path="media/original/original.mp4",kind="original",extension=".mp4",size=1,sha256="a"*64)
        session.add_all([account,campaign,source]); session.flush()
        original=self.test_settings.data_dir/source.relative_path
        original.parent.mkdir(parents=True);original.write_bytes(b"original-video")
        script_path=self.test_settings.data_dir/'scripts/synthetic.py'
        script_path.parent.mkdir(parents=True)
        script_path.write_text("from pathlib import Path\nfor p in Path('.').iterdir():\n if p.suffix in ('.mp4','.jpg'): p.write_bytes(b'processed:'+p.read_bytes())\n")
        script=Script(name='synthetic',relative_path='scripts/synthetic.py',active=True)
        session.add(script);session.flush()
        session.add(CampaignScript(campaign_id=campaign.id,script_id=script.id,position=0))
        processed_path=self.test_settings.data_dir/"media/processed/seed.mp4"; processed_path.parent.mkdir(parents=True); processed_path.write_bytes(b"processed")
        processed=Media(original_name="processed.mp4",stored_name="seed.mp4",relative_path="media/processed/seed.mp4",kind="processed",extension=".mp4",size=processed_path.stat().st_size,sha256="b"*64,original_media_id=source.id)
        session.add_all([processed,CampaignSourceMedia(campaign_id=campaign.id,media_id=source.id),CampaignScheduleRule(campaign_id=campaign.id,start_date=str(date.today()),days=days,intervals="00:00-00:01,23:58-23:59",strategy="sequential")])
        session.commit()
        return campaign,account

    def test_due_healthy_account_is_queued_without_running_worker_in_request(self):
        with self.Session() as session:
            campaign,account=self.seed(session)
            account.campaign_sync_due_at=datetime.utcnow()-timedelta(seconds=1)
            session.commit()
            with patch.object(main,'queue_account_campaign_sync',return_value=True) as queue:
                result=main.sync_due_connected_accounts(session)
            queue.assert_called_once_with(account.id)
            self.assertEqual(result['queued'],1)
            self.assertIsNone(account.campaign_sync_completed_at)

    def test_past_slots_are_never_created(self):
        with self.Session() as session:
            campaign,account=self.seed(session)
            created=main.materialize_missing_schedule_for_account(session,campaign,account)
            session.commit()
            posts=session.scalars(select(ScheduledPost)).all()
            self.assertGreaterEqual(created,0)
            self.assertTrue(all(post.scheduled_for>datetime.now() for post in posts))

    def test_repeat_sync_does_not_duplicate_schedule(self):
        with self.Session() as session:
            campaign,account=self.seed(session)
            main.materialize_missing_schedule_for_account(session,campaign,account); session.commit()
            before=session.scalar(select(__import__('sqlalchemy').func.count()).select_from(ScheduledPost))
            main.materialize_missing_schedule_for_account(session,campaign,account); session.commit()
            after=session.scalar(select(__import__('sqlalchemy').func.count()).select_from(ScheduledPost))
            self.assertEqual(before,after)

    def test_sync_processes_original_video_and_cover_for_each_post(self):
        with self.Session() as session:
            campaign,account=self.seed(session)
            cover=self.test_settings.data_dir/'source-cover.jpg';cover.write_bytes(b'original-cover')
            campaign.cover_path='source-cover.jpg';session.commit()
            count=main.materialize_missing_schedule_for_account(session,campaign,account)
            posts=list(session.scalars(select(ScheduledPost)))
            self.assertGreater(count,0)
            paths=[]
            for post in posts:
                video=session.get(Media,post.processed_media_id)
                self.assertEqual((self.test_settings.data_dir/video.relative_path).read_bytes(),b'processed:original-video')
                link=session.scalar(select(ScheduledPostCover).where(ScheduledPostCover.post_id==post.id))
                self.assertIsNotNone(link)
                image=session.get(ProcessedCover,link.cover_id)
                self.assertEqual((self.test_settings.data_dir/image.relative_path).read_bytes(),b'processed:original-cover')
                paths.append(image.relative_path)
            self.assertEqual(len(set(paths)),count)

    def test_cover_not_processed_prevents_scheduling(self):
        with self.Session() as session:
            campaign,account=self.seed(session)
            (self.test_settings.data_dir/'source-cover.jpg').write_bytes(b'original-cover')
            campaign.cover_path='source-cover.jpg';session.commit()
            (self.test_settings.data_dir/'scripts/synthetic.py').write_text("from pathlib import Path\nfor p in Path('.').glob('*.mp4'): p.write_bytes(b'processed:'+p.read_bytes())\n")
            with self.assertRaises(RuntimeError):
                main.materialize_missing_schedule_for_account(session,campaign,account)
            self.assertEqual(list(session.scalars(select(ScheduledPost))),[])

    def test_publication_with_missing_required_cover_never_calls_meta(self):
        with self.Session() as session:
            campaign,account=self.seed(session)
            campaign.cover_path='required.jpg'
            video=session.scalar(select(Media).where(Media.kind=='processed'))
            post=ScheduledPost(campaign_id=campaign.id,account_id=account.id,
                processed_media_id=video.id,scheduled_for=datetime.now(),status=PostStatus.CLAIMED,attempts=1)
            session.add(post);session.commit();post_id=post.id
        publish=AsyncMock(return_value='synthetic-meta')
        with patch.object(main,'DbSession',self.Session),patch.object(main.tunnel,'public_url_for',AsyncMock(return_value='https://media.example/video')),patch.object(main.meta,'publish_reel',publish):
            asyncio.run(main.publish_claimed_post(post_id,set(),asyncio.Semaphore(1)))
        publish.assert_not_awaited()
        with self.Session() as session:
            self.assertIn('Capa processada',session.get(ScheduledPost,post_id).last_error)

    def test_publication_receives_processed_cover_url(self):
        with self.Session() as session:
            campaign,account=self.seed(session)
            (self.test_settings.data_dir/'source-cover.jpg').write_bytes(b'original-cover')
            campaign.cover_path='source-cover.jpg';session.commit()
            main.materialize_missing_schedule_for_account(session,campaign,account)
            post=session.scalar(select(ScheduledPost));post.status=PostStatus.CLAIMED;post.attempts=1
            session.commit();post_id=post.id
        async def public_url(path):return 'https://media.example/'+path.name
        publish=AsyncMock(return_value='synthetic-meta')
        with patch.object(main,'DbSession',self.Session),patch.object(main.tunnel,'public_url_for',side_effect=public_url),patch.object(main.meta,'decrypt',return_value='synthetic-token'),patch.object(main.meta,'publish_reel',publish),patch.object(main,'archive_published_reel_video'):
            asyncio.run(main.publish_claimed_post(post_id,set(),asyncio.Semaphore(1)))
        publish.assert_awaited_once()
        self.assertTrue(publish.await_args.args[4].startswith('https://media.example/'))
        self.assertNotEqual(publish.await_args.args[2],publish.await_args.args[4])

    def test_retry_backoff_is_progressive_and_bounded(self):
        self.assertEqual(main.retry_delay(1),30)
        self.assertEqual(main.retry_delay(2),60)
        self.assertEqual(main.retry_delay(3),120)
        self.assertEqual(main.retry_delay(20),120)

    def test_interval_crossing_midnight_is_valid(self):
        self.assertEqual(main.parse_intervals(["23:00-00:00", "23:30-01:15"]),[(1380,1440),(1410,1515)])

    def test_interval_with_same_start_and_end_is_rejected(self):
        with self.assertRaises(ValueError): main.parse_intervals(["00:00-00:00"])


if __name__ == "__main__":
    unittest.main()
