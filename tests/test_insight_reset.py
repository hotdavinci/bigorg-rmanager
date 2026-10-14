import unittest
from app.insight_reset import include_after_reset


class InsightResetTests(unittest.TestCase):
    def test_without_reset_keeps_legacy_behavior(self):
        self.assertTrue(include_after_reset(None,None))

    def test_old_reel_is_not_reimported(self):
        self.assertFalse(include_after_reset('2030-01-01T14:00:00Z','2030-01-01T15:00:00'))

    def test_new_reel_is_included(self):
        self.assertTrue(include_after_reset('2030-01-01T15:00:01+0000','2030-01-01T15:00:00'))

    def test_offsets_are_compared_as_instants(self):
        self.assertTrue(include_after_reset('2030-01-01T12:00:00-03:00','2030-01-01T15:00:00'))
        self.assertFalse(include_after_reset('2030-01-01T11:59:59-03:00','2030-01-01T15:00:00'))

    def test_missing_or_invalid_timestamp_does_not_restore_old_history(self):
        for value in (None,'invalid'):
            self.assertFalse(include_after_reset(value,'2030-01-01T15:00:00'))


if __name__=='__main__':
    unittest.main()
