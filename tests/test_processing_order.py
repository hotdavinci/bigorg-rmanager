from copy import deepcopy
from datetime import date
import unittest
from app.processing_order import order_pending_jobs


class ProcessingOrderTests(unittest.TestCase):
    def jobs(self):
        return [dict(slot_key=key,account_id=account,current=date(2030,1,1),low=minute,high=minute)
                for key,account,minute in [('a-late',1,1000),('a-early',1,100),('b-late',2,900),('b-early',2,90)]]

    def test_orders_actual_minutes_across_accounts(self):
        jobs=self.jobs();order_pending_jobs(jobs)
        self.assertEqual([job['slot_key'] for job in jobs],['b-early','a-early','b-late','a-late'])

    def test_completed_prefix_is_untouched(self):
        jobs=self.jobs();prefix=deepcopy(jobs[0]);order_pending_jobs(jobs,1)
        self.assertEqual(jobs[0],prefix)
        self.assertNotIn('planned_minute',jobs[0])
        self.assertEqual([job['planned_minute'] for job in jobs[1:]],[90,100,900])

    def test_repeat_and_restart_keep_planned_times(self):
        jobs=self.jobs();order_pending_jobs(jobs);snapshot=deepcopy(jobs)
        order_pending_jobs(jobs)
        self.assertEqual(jobs,snapshot)

    def test_midnight_rollover_orders_by_real_date(self):
        jobs=self.jobs()[:2]
        jobs[0].update(current=date(2030,1,1),low=1500,high=1500)
        jobs[1].update(current=date(2030,1,2),low=30,high=30)
        order_pending_jobs(jobs)
        self.assertEqual(jobs[0]['slot_key'],'a-early')

    def test_preserves_existing_planned_minutes(self):
        jobs=self.jobs();jobs[0]['planned_minute']=10
        order_pending_jobs(jobs)
        self.assertEqual(jobs[0]['slot_key'],'a-late')

    def test_invalid_cursor_is_rejected(self):
        with self.assertRaises(ValueError):order_pending_jobs(self.jobs(),5)


if __name__=='__main__':unittest.main()
