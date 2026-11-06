import asyncio
import threading
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from app import main
from app.db import Base
from app.models import Campaign, CampaignStatus, InstagramAccount, Media, ScheduledPost, PostStatus, PublicationAttempt


class AvailabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_blocked_health_commit_does_not_block_http_loop(self):
        entered = threading.Event()
        release = threading.Event()
        class FakeSession:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def get(self, *args): return None
            def add(self, item): pass
            def scalars(self, *args): return []
            def commit(self):
                entered.set()
                if not release.wait(3): raise RuntimeError("test commit timeout")
        with patch.object(main, "DbSession", FakeSession):
            task = asyncio.create_task(main.run_account_health_check())
            try:
                for _ in range(100):
                    if entered.is_set(): break
                    await asyncio.sleep(.005)
                self.assertTrue(entered.is_set())
                # This heartbeat must run before the SQLite-like wait is released.
                await asyncio.wait_for(asyncio.sleep(.01), .2)
                self.assertFalse(task.done())
            finally:
                release.set()
                result = await task
            self.assertEqual(result["checked"], 0)


class HistoryQueryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.s = sessionmaker(self.engine, expire_on_commit=False)()
        c = Campaign(name="Synthetic", status=CampaignStatus.ACTIVE)
        a = InstagramAccount(meta_account_id="synthetic", encrypted_token="synthetic", active=True, last_verified_at=datetime.utcnow())
        m = Media(original_name="test.mp4", stored_name="test.mp4", relative_path="test.mp4", kind="processed", extension=".mp4", size=1, sha256="a"*64)
        self.s.add_all([c,a,m]); self.s.flush()
        self.posts=[]
        for i in range(120):
            p=ScheduledPost(campaign_id=c.id, account_id=a.id if i else 9999, processed_media_id=m.id, status=PostStatus.FAILED if i%2 else PostStatus.PENDING, scheduled_for=datetime(2026,1,1)+timedelta(minutes=i), position=i)
            self.s.add(p);self.s.flush();self.posts.append(p)
            if i%2:
                self.s.add_all([PublicationAttempt(post_id=p.id,status="FAILED",message="old"),PublicationAttempt(post_id=p.id,status="FAILED",message="latest")])
        self.s.commit(); self.s.expunge_all()

    def tearDown(self):
        self.s.close();self.engine.dispose()

    def test_agenda_preserves_all_posts_and_latest_attempt_with_one_query(self):
        calls=[]
        def count(*args): calls.append(1)
        event.listen(self.engine,"before_cursor_execute",count)
        try: rows=main.scheduled_posts(self.s)
        finally: event.remove(self.engine,"before_cursor_execute",count)
        self.assertEqual(len(rows),120)
        self.assertEqual(len(calls),1)
        self.assertEqual(rows[0]["conta"],"")
        self.assertFalse(rows[0]["conta_apta"])
        self.assertEqual(rows[1]["erro"],"latest")
        self.assertEqual(rows[2]["erro"],"")
        self.assertEqual([r["quando"] for r in rows],sorted(r["quando"] for r in rows))

    def test_activity_latest_attempt_and_pending_order_preserved(self):
        rows=main.activity(self.s)
        self.assertEqual(len(rows),100)
        self.assertEqual(sum(r["status"]==PostStatus.FAILED for r in rows),60)
        self.assertTrue(all(r["detail"]=="latest" for r in rows[:60]))
        self.assertTrue(all(r["status"]==PostStatus.PENDING for r in rows[60:]))
        self.assertEqual(rows[60]["title"].split(" · ")[0],"@conta removida")
        self.assertNotIn("sort_when",rows[0])
