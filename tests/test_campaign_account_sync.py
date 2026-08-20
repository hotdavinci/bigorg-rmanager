import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import config
from app.db import Base
from app.models import Campaign, CampaignAccount, CampaignScheduleRule, CampaignSourceMedia, CampaignStatus, InstagramAccount, Media, PostStatus, ScheduledPost
from app import main


class CampaignAccountSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.previous_settings=config.settings
        self.test_settings=SimpleNamespace(data_dir=Path(self.temp.name))
        config.settings=self.test_settings
        main.settings=self.test_settings
        self.engine=create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session=sessionmaker(self.engine,expire_on_commit=False)

    def tearDown(self):
        config.settings=self.previous_settings
        main.settings=self.previous_settings
        self.temp.cleanup()

    def seed(self, session, days=2):
        account=InstagramAccount(meta_account_id="ig-1",username="healthy",encrypted_token="token",active=True,last_verified_at=datetime.utcnow())
        campaign=Campaign(name="Teste",status=CampaignStatus.ACTIVE)
        source=Media(original_name="original.mp4",stored_name="original.mp4",relative_path="media/original/original.mp4",kind="original",extension=".mp4",size=1,sha256="a"*64)
        session.add_all([account,campaign,source]); session.flush()
        processed_path=self.test_settings.data_dir/"media/processed/seed.mp4"; processed_path.parent.mkdir(parents=True); processed_path.write_bytes(b"processed")
        processed=Media(original_name="processed.mp4",stored_name="seed.mp4",relative_path="media/processed/seed.mp4",kind="processed",extension=".mp4",size=processed_path.stat().st_size,sha256="b"*64,original_media_id=source.id)
        session.add_all([processed,CampaignSourceMedia(campaign_id=campaign.id,media_id=source.id),CampaignScheduleRule(campaign_id=campaign.id,start_date=str(date.today()),days=days,intervals="00:00-00:01,23:58-23:59",strategy="sequential")])
        session.commit()
        return campaign,account

    def test_due_healthy_account_is_added_to_active_campaign_once(self):
        with self.Session() as session:
            campaign,account=self.seed(session)
            account.campaign_sync_due_at=datetime.utcnow()-timedelta(seconds=1)
            session.commit()
            main.sync_due_connected_accounts(session)
            self.assertEqual(session.scalar(select(CampaignAccount.account_id).where(CampaignAccount.campaign_id==campaign.id)),account.id)
            self.assertIsNotNone(account.campaign_sync_completed_at)

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

    def test_retry_backoff_is_progressive_and_bounded(self):
        self.assertEqual(main.retry_delay(1),30)
        self.assertEqual(main.retry_delay(2),60)
        self.assertEqual(main.retry_delay(3),120)
        self.assertEqual(main.retry_delay(20),120)


if __name__ == "__main__":
    unittest.main()
