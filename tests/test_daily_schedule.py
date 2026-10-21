import ast
from datetime import date, datetime, timedelta
from pathlib import Path
import unittest

from pydantic import BaseModel, Field, ValidationError, model_validator
from app.daily_schedule import daily_quantity, daily_ranges, utc_deadline_local, windowed_ranges, is_windowed


class DailyScheduleTests(unittest.TestCase):
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
                           daily_quantity=daily_quantity,is_windowed=is_windowed,
                           WINDOWED_RULE='windows:12-18',date=date)
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

    def test_invalid_quantity_is_rejected(self):
        for value in (0,-1,1441,1.5):
            with self.subTest(value=value),self.assertRaises(ValidationError):
                self.namespace['GenerateScheduleIn'](start_date='2030-01-02',days=1,reels_per_day=value)


if __name__ == '__main__':
    unittest.main()
