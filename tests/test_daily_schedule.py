import ast
from datetime import date, datetime, timedelta
from pathlib import Path
import unittest

from pydantic import BaseModel, Field, ValidationError, model_validator
from app.daily_schedule import daily_quantity, daily_ranges, utc_deadline_local, windowed_ranges, window_specs, is_windowed, is_recurring


class DailyScheduleTests(unittest.TestCase):
    def test_custom_windows_keep_counts_and_partial_entry(self):
        rules=['recurring:window:08:00-09:00:3-3','recurring:window:11:30-12:30:6-6']
        day=date(2030,1,2)
        full=windowed_ranges(day,datetime(2030,1,1),None,7,8,values=rules)
        self.assertEqual(len(full),9)
        self.assertEqual(len([1 for low,_ in full if 480<=low<540]),3)
        self.assertEqual(len([1 for low,_ in full if 690<=low<750]),6)
        partial=windowed_ranges(day,datetime(2030,1,2,12),None,7,8,values=rules)
        self.assertEqual(len(partial),3)
        self.assertTrue(all(low>=725 for low,_ in partial))
        tomorrow=windowed_ranges(day+timedelta(days=1),datetime(2030,1,2,12),None,7,8,
                                 datetime(2030,1,3,12),rules)
        self.assertEqual(len(tomorrow),6)
        self.assertTrue(all(high<720 for _,high in tomorrow))

    def test_custom_windows_reject_overlap_and_impossible_count(self):
        for rules in (
            ['recurring:window:08:00-09:00:3-3','recurring:window:08:59-10:00:3-3'],
            ['recurring:window:08:00-08:10:1-11'],
            ['recurring:window:23:30-00:30:1-3'],
        ):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                window_specs(rules)

    def test_recurring_horizon_uses_only_full_buckets_inside_24_hours(self):
        day=date(2030,1,2)
        now=datetime(2030,1,2,12)
        today=windowed_ranges(day,now,None,1,2,now+timedelta(hours=24))
        tomorrow=windowed_ranges(day+timedelta(days=1),now,None,1,2,now+timedelta(hours=24))
        self.assertTrue(today)
        self.assertTrue(tomorrow)
        self.assertTrue(all(high<12*60 for _,high in tomorrow))
        self.assertEqual(tomorrow,windowed_ranges(day+timedelta(days=1),now,None,1,2,now+timedelta(hours=24)))
        later=now+timedelta(minutes=10)
        tomorrow_later=windowed_ranges(day+timedelta(days=1),later,None,1,2,later+timedelta(hours=24))
        self.assertTrue(any(12*60<=high<12*60+10 for _,high in tomorrow_later))
        self.assertTrue(all(high<12*60+10 for _,high in tomorrow_later))
        self.assertTrue(set(tomorrow).issubset(tomorrow_later))

    def test_windowed_full_day_and_mid_window_entry(self):
        day = date(2030, 1, 2)
        full = windowed_ranges(day, datetime(2030, 1, 1), None, 1, 2)
        self.assertEqual(len(full), len(set(full)))
        self.assertTrue(36 <= len(full) <= 54)
        for start, end in ((510, 570), (690, 750), (1050, 1110)):
            self.assertTrue(12 <= len([r for r in full if start <= r[0] < end]) <= 18)
        partial = windowed_ranges(day, datetime(2030, 1, 2, 11, 55),
                                  datetime(2030, 1, 2, 12), 1, 2)
        midday_full = [r for r in full if 690 <= r[0] < 750]
        midday_partial = [r for r in partial if 690 <= r[0] < 750]
        self.assertTrue(5 <= len(midday_partial) <= 9)
        self.assertTrue(all(low >= 12 * 60 for low, _ in midday_partial))
        self.assertEqual([high for _, high in midday_partial],
                         [high for _, high in midday_full if high >= 12 * 60])
        self.assertEqual([r for r in partial if r[0] >= 1050],
                         [r for r in full if r[0] >= 1050])

    def test_full_day_is_partitioned_without_overlap(self):
        day = date(2030, 1, 2)
        ranges = daily_ranges(12, day, datetime(2030, 1, 1, 12))
        self.assertEqual(len(ranges), 12)
        self.assertEqual(ranges[0], (0, 119))
        self.assertEqual(ranges[-1], (1320, 1439))
        self.assertTrue(all(ranges[i][1] + 1 == ranges[i+1][0] for i in range(11)))

    def test_today_keeps_quantity_in_remaining_day(self):
        ranges = daily_ranges(7, date(2030, 1, 2), datetime(2030, 1, 2, 16, 0, 30))
        self.assertEqual(len(ranges), 7)
        self.assertEqual(ranges[0][0], 16*60+6)
        self.assertEqual(ranges[-1][1], 1439)

    def test_onboarding_deadline_and_midnight_are_respected(self):
        day = date(2030, 1, 2)
        ranges = daily_ranges(3, day, datetime(2030, 1, 2, 10), datetime(2030, 1, 2, 19, 0, 20))
        self.assertEqual(ranges[0][0], 19*60+1)
        self.assertEqual(daily_ranges(3, day, datetime(2030, 1, 2, 23, 58)), [])
        self.assertEqual(daily_ranges(3, day, datetime(2030, 1, 2, 10), datetime(2030, 1, 3)), [])

    def test_insufficient_minutes_rejected_instead_of_duplicate_slots(self):
        with self.assertRaisesRegex(ValueError, "minutos suficientes"):
            daily_ranges(10, date(2030, 1, 2), datetime(2030, 1, 2, 23, 50))

    def test_utc_account_deadline_is_converted_to_local_schedule(self):
        self.assertEqual(utc_deadline_local(datetime(2030, 1, 2, 20)), datetime(2030, 1, 2, 17))


class QuantityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Compile only contracts/helpers, never import app.main or real settings.
        tree=ast.parse((Path(__file__).resolve().parents[1]/'app/main.py').read_text(encoding='utf-8'))
        names={'QuantityScheduleIn','GenerateScheduleIn','CampaignSetupIn','CampaignDefaultsIn'}
        nodes=[node for node in tree.body if isinstance(node,ast.ClassDef) and node.name in names]
        cls.namespace=dict(BaseModel=BaseModel,Field=Field,model_validator=model_validator,
                           daily_quantity=daily_quantity,is_windowed=is_windowed,is_recurring=is_recurring,window_specs=window_specs,
                           RECURRING_WINDOWED_RULE='recurring:windows:12-18',date=date)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'contracts','exec'),cls.namespace)

    def test_new_quantity_survives_checkpoint_roundtrip(self):
        model=self.namespace['GenerateScheduleIn']
        request=model(start_date='2030-01-02',days=2,reels_per_day=12)
        self.assertEqual(request.intervals,['daily:12'])
        self.assertEqual(model(**request.model_dump()).reels_per_day,12)

    def test_legacy_intervals_are_preserved(self):
        request=self.namespace['GenerateScheduleIn'](start_date='2030-01-02',days=1,intervals=['23:00-01:00'])
        self.assertIsNone(request.reels_per_day)
        self.assertEqual(request.intervals,['23:00-01:00'])

    def test_persisted_rule_marker_is_recognized_on_recovery(self):
        request=self.namespace['GenerateScheduleIn'](start_date='2030-01-02',days=1,intervals=['daily:17'])
        self.assertEqual(request.reels_per_day,17)

    def test_window_rule_survives_checkpoint_roundtrip(self):
        model=self.namespace['GenerateScheduleIn']
        request=model(start_date='2030-01-02',days=2,intervals=['windows:12-18'])
        self.assertIsNone(request.reels_per_day)
        self.assertEqual(model(**request.model_dump()).intervals,['windows:12-18'])

    def test_recurring_rule_needs_no_date_and_keeps_anchor_on_recovery(self):
        model=self.namespace['GenerateScheduleIn']
        request=model(intervals=['recurring:windows:12-18'])
        self.assertIsNotNone(request.start_date)
        self.assertEqual(request.days,2)
        self.assertEqual(model(**request.model_dump()).start_date,request.start_date)
        self.assertIsNone(request.reels_per_day)

    def test_custom_recurring_rule_validates_contract(self):
        model=self.namespace['GenerateScheduleIn']
        rules=['recurring:window:08:00-09:00:3-3','recurring:window:11:30-12:30:6-8']
        request=model(intervals=rules)
        self.assertEqual(request.intervals,rules)
        self.assertIsNotNone(request.start_date)
        self.assertEqual(request.days,2)
        with self.assertRaises(ValidationError):
            model(intervals=['recurring:window:08:00-08:10:1-11'])

    def test_invalid_quantity_is_rejected(self):
        for value in (0,-1,1441,1.5):
            with self.subTest(value=value),self.assertRaises(ValidationError):
                self.namespace['GenerateScheduleIn'](start_date='2030-01-02',days=1,reels_per_day=value)


if __name__ == '__main__':
    unittest.main()
