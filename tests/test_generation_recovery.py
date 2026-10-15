import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app import main
from app.db import Base
from app.models import (ApplicationSetting, Campaign, CampaignAccount,
    CampaignSourceMedia, CampaignStatus, InstagramAccount, Media,
    PostStatus, ScheduledPost)


class GenerationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        self.settings = patch.object(main, 'settings', SimpleNamespace(
            data_dir=Path(self.temp.name), processing_batch_size=1))
        self.settings.start()
        with self.Session() as s:
            c = Campaign(name='Recovery', status=CampaignStatus.PROCESSING)
            a = InstagramAccount(meta_account_id='test', encrypted_token='test')
            m = Media(original_name='test.mp4', stored_name='test.mp4',
                relative_path='test.mp4', kind='original', extension='.mp4',
                size=1, sha256='a'*64)
            s.add_all([c, a, m]); s.flush()
            s.add_all([CampaignAccount(campaign_id=c.id, account_id=a.id),
                CampaignSourceMedia(campaign_id=c.id, media_id=m.id)])
            s.commit()
            self.campaign_id = c.id
        self.body = main.GenerateScheduleIn(start_date=date.today()+timedelta(days=1),
            days=1, intervals=['11:00-12:00', '13:00-14:00', '15:00-16:00'],
            strategy='sequential')

    def tearDown(self):
        self.settings.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def process(self, session, campaign_id, slots):
        results = []
        for job in slots:
            media = Media(original_name='out.mp4', stored_name=job['slot_key'],
                relative_path=job['slot_key'], kind='processed', extension='.mp4',
                size=1, sha256='b'*64, original_media_id=job['source_id'])
            session.add(media); session.flush()
            results.append((job, media, None))
        return results

    def test_restart_keeps_published_batch_and_resumes_only_remaining_jobs(self):
        calls = []
        def interrupted(session, campaign_id, slots):
            calls.append(slots[0]['slot_key'])
            if len(calls) == 2:
                raise InterruptedError('SIGTERM')
            return self.process(session, campaign_id, slots)
        with patch.object(main, 'account_is_eligible', return_value=True):
            with self.Session() as s, patch.object(main, 'process_slots_batch', side_effect=interrupted):
                main.generate_schedule(self.campaign_id, self.body, s, True)
                post = s.scalar(select(ScheduledPost))
                original_id = post.id
                post.status = PostStatus.PUBLISHED; s.commit()
                self.assertEqual(s.get(Campaign, self.campaign_id).status, CampaignStatus.PROCESSING)
                plan = json.loads(s.get(ApplicationSetting, f'generation-plan-{self.campaign_id}').value)
                self.assertEqual(plan['completed'], 1)
            with self.Session() as s, patch.object(main, 'process_slots_batch', side_effect=self.process) as processor:
                main.generate_schedule(self.campaign_id, self.body, s, True)
                self.assertEqual(processor.call_count, 2)
                posts = list(s.scalars(select(ScheduledPost)))
                self.assertEqual(len(posts), 3)
                self.assertEqual(s.get(ScheduledPost, original_id).status, PostStatus.PUBLISHED)
                self.assertEqual(s.get(Campaign, self.campaign_id).status, CampaignStatus.ACTIVE)

    def test_quantity_generates_exact_daily_count_and_recovers_without_duplicates(self):
        body=main.GenerateScheduleIn(start_date=date.today()+timedelta(days=1),
            days=2,reels_per_day=4,strategy='sequential')
        calls=[]
        def interrupted(session,campaign_id,slots):
            calls.append(1)
            if len(calls)==3: raise InterruptedError('synthetic restart')
            return self.process(session,campaign_id,slots)
        with patch.object(main,'account_is_eligible',return_value=True):
            with self.Session() as session,patch.object(main,'process_slots_batch',side_effect=interrupted):
                main.generate_schedule(self.campaign_id,body,session,True)
            with self.Session() as session,patch.object(main,'process_slots_batch',side_effect=self.process):
                main.generate_schedule(self.campaign_id,body,session,True)
                posts=list(session.scalars(select(ScheduledPost)))
                self.assertEqual(len(posts),8)
                for offset in range(2):
                    day=body.start_date+timedelta(days=offset)
                    daily=[post for post in posts if post.scheduled_for.date()==day]
                    self.assertEqual(len(daily),4)
                    self.assertEqual(len({post.scheduled_for.hour//6 for post in daily}),4)

    def test_campaign_processes_earliest_slots_across_accounts(self):
        with self.Session() as session:
            account=InstagramAccount(meta_account_id='second-test',encrypted_token='test')
            session.add(account);session.flush()
            session.add(CampaignAccount(campaign_id=self.campaign_id,account_id=account.id));session.commit()
        body=main.GenerateScheduleIn(start_date=date.today()+timedelta(days=1),days=1,reels_per_day=4)
        seen=[]
        def process(session,campaign_id,slots):
            seen.extend((job['planned_minute'],job['account_id']) for job in slots)
            return self.process(session,campaign_id,slots)
        with self.Session() as session,patch.object(main,'account_is_eligible',return_value=True),patch.object(main,'process_slots_batch',side_effect=process):
            main.generate_schedule(self.campaign_id,body,session,True)
            self.assertEqual(len(seen),8)
            self.assertEqual([minute for minute,_ in seen],sorted(minute for minute,_ in seen))
            self.assertEqual(len({account for _,account in seen[:2]}),2)
            self.assertEqual(len(list(session.scalars(select(ScheduledPost)))),8)

    def test_only_new_failed_campaigns_publish_and_paused_campaigns_stay_blocked(self):
        with self.Session() as s:
            for status, has_plan in [(CampaignStatus.PROCESSING_FAILED, True),
                    (CampaignStatus.PROCESSING_FAILED, False), (CampaignStatus.PAUSED, True),
                    (CampaignStatus.CANCELLED, True)]:
                c = Campaign(name='test', status=status); s.add(c); s.flush()
                if has_plan:
                    s.add(ApplicationSetting(key=f'generation-plan-{c.id}', value='{}'))
                s.add(ScheduledPost(campaign_id=c.id, account_id=1, processed_media_id=1,
                    scheduled_for=datetime.now()-timedelta(minutes=1), status=PostStatus.PENDING))
            s.commit()
            claimed = main.claim_due_posts(s, set(), datetime.now(), 10)
            self.assertEqual(len(claimed), 1)
            post = s.get(ScheduledPost, claimed[0])
            self.assertEqual(s.get(Campaign, post.campaign_id).status, CampaignStatus.PROCESSING_FAILED)

    def test_startup_uses_saved_request_and_preserves_progress(self):
        with self.Session() as s:
            s.add(ApplicationSetting(key=f'generation-plan-{self.campaign_id}',
                value=json.dumps({'request': self.body.model_dump(mode='json')})))
            s.commit()
        main.save_generation_progress(self.campaign_id, status='INTERRUPTED',
            total=3, completed=1, scheduled=1)
        with patch.object(main, 'DbSession', self.Session), patch.object(main.threading, 'Thread') as thread:
            main.resume_interrupted_campaign_generations()
            thread.return_value.start.assert_called_once()
            self.assertEqual(thread.call_args.kwargs['args'][0], self.campaign_id)
            self.assertEqual(thread.call_args.kwargs['args'][1].start_date, self.body.start_date)
        progress = main.load_generation_progress(self.campaign_id)
        self.assertEqual(progress['completed'], 1)
        self.assertEqual(progress['scheduled'], 1)


if __name__ == '__main__':
    unittest.main()
