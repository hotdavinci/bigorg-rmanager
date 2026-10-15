import unittest
from datetime import datetime, timedelta
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from fastapi import HTTPException
from pydantic import ValidationError
from app.db import Base
from app import main
from app.models import InstagramAccount, ApplicationSetting, Campaign, CampaignStatus, Media, ScheduledPost, PostStatus

class AccountPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.s=Session(self.engine,expire_on_commit=False)
        self.connected=datetime.utcnow()-timedelta(days=2)
        self.a=InstagramAccount(meta_account_id="synthetic-a",encrypted_token="synthetic",connected_at=self.connected)
        self.b=InstagramAccount(meta_account_id="synthetic-b",encrypted_token="synthetic",connected_at=self.connected)
        self.s.add_all([self.a,self.b]); self.s.commit()
    def tearDown(self):
        self.s.close(); self.engine.dispose()
    def test_bulk_override_and_group_independent(self):
        main.save_account_preferences(main.AccountPreferencesIn(account_ids=[self.a.id,self.b.id],posting_delay_days=5,account_group=" Grupo A "),self.s)
        for a in (self.a,self.b):
            self.assertEqual(a.posting_delay_days,5)
            self.assertEqual(a.campaign_sync_due_at,self.connected+timedelta(days=5))
            self.assertEqual(a.account_group,"Grupo A")
        main.save_account_preferences(main.AccountPreferencesIn(account_ids=[self.a.id],account_group="Outro"),self.s)
        self.assertEqual(self.a.posting_delay_days,5)
        self.assertEqual(self.b.account_group,"Grupo A")
    def test_global_fallback_and_zero_override(self):
        main.save_account_preferences(main.AccountPreferencesIn(account_ids=[self.a.id],posting_delay_days=0),self.s)
        main.save_account_campaign_sync_settings(9,self.s)
        self.assertEqual(main.account_campaign_sync_delay_days(self.s,self.a),0)
        self.assertEqual(self.a.campaign_sync_due_at,self.connected)
        self.assertEqual(self.b.campaign_sync_due_at,self.connected+timedelta(days=9))
        main.save_account_preferences(main.AccountPreferencesIn(account_ids=[self.a.id],posting_delay_days=None),self.s)
        self.assertEqual(self.a.campaign_sync_due_at,self.connected+timedelta(days=9))
        self.assertIsNone(self.a.posting_delay_days)
    def test_reconnect_preserves_override(self):
        self.a.posting_delay_days=7
        self.a.connected_at=datetime.utcnow()
        self.assertEqual(main.schedule_account_campaign_sync(self.s,self.a),7)
        self.assertEqual(self.a.campaign_sync_due_at,self.a.connected_at+timedelta(days=7))
    def test_missing_account_does_not_partially_update(self):
        with self.assertRaises(HTTPException):
            main.save_account_preferences(main.AccountPreferencesIn(account_ids=[self.a.id,999],posting_delay_days=4),self.s)
        self.assertIsNone(self.a.posting_delay_days)
    def test_validation(self):
        for value in (-1,366):
            with self.assertRaises(ValidationError): main.AccountPreferencesIn(account_ids=[1],posting_delay_days=value)
        with self.assertRaises(ValidationError): main.AccountPreferencesIn(account_ids=[],account_group="x")
    def test_existing_queue_waits_and_published_preserved(self):
        campaign=Campaign(name="synthetic",status=CampaignStatus.ACTIVE)
        media=Media(original_name="x.mp4",stored_name="x.mp4",relative_path="synthetic/x.mp4",kind="processed",extension=".mp4",size=1,sha256="a"*64)
        self.s.add_all([campaign,media]); self.s.flush()
        pending=ScheduledPost(campaign_id=campaign.id,account_id=self.a.id,processed_media_id=media.id,caption="",scheduled_for=datetime.now()-timedelta(minutes=5),position=0,status=PostStatus.PENDING)
        published=ScheduledPost(campaign_id=campaign.id,account_id=self.a.id,processed_media_id=media.id,caption="",scheduled_for=datetime.now()-timedelta(hours=1),position=1,status=PostStatus.PUBLISHED)
        self.s.add_all([pending,published]); self.s.commit()
        main.save_account_preferences(main.AccountPreferencesIn(account_ids=[self.a.id],posting_delay_days=5),self.s)
        self.assertEqual(main.claim_due_posts(self.s,set(),datetime.now(),3),[])
        self.assertEqual(published.status,PostStatus.PUBLISHED)
        main.save_account_preferences(main.AccountPreferencesIn(account_ids=[self.a.id],posting_delay_days=0),self.s)
        self.assertEqual(main.claim_due_posts(self.s,set(),datetime.now(),3),[pending.id])

if __name__=="__main__": unittest.main()
