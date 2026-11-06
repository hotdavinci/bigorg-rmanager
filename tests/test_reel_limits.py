import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app import main
from app.db import Base
from app.models import ApplicationSetting, Campaign, CampaignAccount, CampaignStatus, InstagramAccount, Media, PostStatus, ScheduledPost, Script
from app.reel_limits import published_total, save_published_total, preserve_published_totals


class ReelLimitTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session=sessionmaker(self.engine,expire_on_commit=False)
        self.s=self.Session()
        self.account=InstagramAccount(meta_account_id="synthetic",encrypted_token="synthetic",active=True,last_verified_at=datetime.utcnow())
        self.other=InstagramAccount(meta_account_id="synthetic-other",encrypted_token="synthetic",active=True,last_verified_at=datetime.utcnow())
        self.c=Campaign(name="Synthetic",status=CampaignStatus.ACTIVE)
        self.media=Media(original_name="test.mp4",stored_name="test.mp4",relative_path="test.mp4",kind="processed",extension=".mp4",size=1,sha256="a"*64)
        self.s.add_all([self.account,self.other,self.c,self.media]); self.s.commit()

    def tearDown(self):
        self.s.close(); self.engine.dispose()

    def limit(self, value):
        main.save_account_reel_limit_settings(main.AccountReelLimitIn(limit=value),self.s)

    def post(self, status, account=None):
        p=ScheduledPost(campaign_id=self.c.id,account_id=(account or self.account).id,processed_media_id=self.media.id,status=status,scheduled_for=datetime.now()-timedelta(minutes=1),position=self.s.query(ScheduledPost).count())
        self.s.add(p); self.s.commit(); return p

    def test_default_and_validation(self):
        self.assertEqual(main.account_reel_limit_settings(self.s),{"limit":0})
        for value in [-1,1.5,True,"2",2147483648]:
            with self.assertRaises(ValidationError): main.AccountReelLimitIn(limit=value)

    def test_only_successes_count_per_account(self):
        self.post(PostStatus.PUBLISHED)
        self.post(PostStatus.PUBLISHED,self.other)
        self.post(PostStatus.FAILED); self.post(PostStatus.PENDING)
        self.limit(2)
        self.assertEqual(published_total(self.s,self.account.id),1)
        self.assertTrue(main.account_can_publish(self.s,self.account))
        self.post(PostStatus.PUBLISHED)
        self.assertFalse(main.account_can_publish(self.s,self.account))
        self.assertTrue(self.account.active)
        self.assertEqual(self.account.last_error,"")

    def test_limited_account_not_linked_or_materialized(self):
        self.post(PostStatus.PUBLISHED); self.limit(1)
        self.assertEqual(main.sync_account_to_active_campaigns(self.s,self.account),(0,0))
        self.assertEqual(main.materialize_missing_schedule_for_account(self.s,self.c,self.account),0)
        self.assertIsNone(self.s.scalar(select(CampaignAccount)))

    def test_setup_excludes_limited_account(self):
        self.post(PostStatus.PUBLISHED); self.limit(1)
        self.c.status=CampaignStatus.DRAFT
        self.media.kind="original"; self.s.commit()
        script=Script(name="Synthetic",relative_path="synthetic.py",active=True)
        self.s.add(script); self.s.commit()
        body=main.CampaignSetupIn(source_ids=[self.media.id],script_ids=[script.id],intervals=["recurring:windows:12-18"])
        main.setup_campaign(self.c.id,body,self.s)
        ids=list(self.s.scalars(select(CampaignAccount.account_id)))
        self.assertEqual(ids,[self.other.id])

    def test_claim_skips_limited_accounts_without_starving_others(self):
        self.post(PostStatus.PUBLISHED); self.limit(1)
        for _ in range(8): self.post(PostStatus.PENDING)
        other_post=self.post(PostStatus.PENDING,self.other)
        claimed=main.claim_due_posts(self.s,set(),datetime.now(),1)
        self.assertEqual(claimed,[other_post.id])

    def test_executor_rechecks_limit_without_external_calls(self):
        self.post(PostStatus.PUBLISHED); self.limit(1)
        p=self.post(PostStatus.CLAIMED)
        in_flight={self.account.id}
        with patch.object(main,"DbSession",self.Session),patch.object(main.meta,"publish_reel",new_callable=AsyncMock) as publish:
            asyncio.run(main.publish_claimed_post(p.id,in_flight,asyncio.Semaphore(1)))
            publish.assert_not_called()
        self.s.refresh(p)
        self.assertEqual(p.status,PostStatus.PENDING)
        self.assertEqual(in_flight,set())

    def test_raise_or_disable_limit_releases_existing_queue(self):
        self.post(PostStatus.PUBLISHED); p=self.post(PostStatus.PENDING)
        self.limit(1)
        self.assertEqual(main.claim_due_posts(self.s,set(),datetime.now(),1),[])
        self.limit(2)
        self.assertTrue(main.account_can_publish(self.s,self.account))
        self.limit(0)
        self.assertEqual(main.claim_due_posts(self.s,set(),datetime.now(),1),[p.id])

    def test_clear_history_preserves_counter(self):
        self.media.kind="original"
        self.post(PostStatus.PUBLISHED); self.limit(1)
        main.clear_history(self.s)
        self.assertEqual(published_total(self.s,self.account.id),1)
        self.assertFalse(main.account_can_publish(self.s,self.account))

    def test_persisted_total_survives_new_sessions_and_new_successes(self):
        self.post(PostStatus.PUBLISHED)
        preserve_published_totals(self.s); self.s.commit()
        save_published_total(self.s,self.account.id,published_total(self.s,self.account.id)+1)
        self.s.commit()
        with self.Session() as fresh:
            self.assertEqual(published_total(fresh,self.account.id),2)

    def test_success_records_total_before_cleanup(self):
        self.post(PostStatus.PUBLISHED)
        p=self.post(PostStatus.CLAIMED); self.limit(2)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"test.mp4"; path.write_bytes(b"synthetic")
            with patch.object(main,"DbSession",self.Session),patch.object(main,"data_path",return_value=path),patch.object(main.tunnel,"public_url_for",new_callable=AsyncMock,return_value="https://synthetic.invalid/video"),patch.object(main.meta,"decrypt",return_value="synthetic"),patch.object(main.meta,"publish_reel",new_callable=AsyncMock,return_value="synthetic-media"),patch.object(main,"archive_published_reel_video",side_effect=RuntimeError("synthetic cleanup failure")):
                asyncio.run(main.publish_claimed_post(p.id,set(),asyncio.Semaphore(1)))
        self.s.expire_all()
        self.assertEqual(self.s.get(ScheduledPost,p.id).status,PostStatus.PUBLISHED)
        self.assertEqual(published_total(self.s,self.account.id),2)
        self.assertFalse(main.account_can_publish(self.s,self.account))

    def test_campaign_deletion_preserves_counter(self):
        self.post(PostStatus.PUBLISHED); self.limit(1)
        self.media.kind="original"; self.s.commit()
        with tempfile.TemporaryDirectory() as directory, patch.object(main,"progress_file",return_value=Path(directory)/"progress.json"):
            main.purge_campaign(self.s,self.c.id)
        self.assertEqual(published_total(self.s,self.account.id),1)
        self.assertFalse(main.account_can_publish(self.s,self.account))

    def test_due_sync_does_not_queue_limited_account(self):
        self.post(PostStatus.PUBLISHED); self.limit(1)
        self.account.campaign_sync_due_at=datetime.utcnow()-timedelta(days=1)
        self.s.commit()
        with patch.object(main,"queue_account_campaign_sync") as queue:
            main.sync_due_connected_accounts(self.s)
            queue.assert_not_called()
