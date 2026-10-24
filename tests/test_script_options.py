import unittest
from pathlib import Path
from types import SimpleNamespace

from app.services import script_command


class ScriptOptionsTests(unittest.TestCase):
    def test_name_preservation_option_is_passed_only_when_stored(self):
        script = SimpleNamespace(id=3)
        source = Path('cleanM.py')
        no_option = SimpleNamespace(get=lambda model, key: None)
        command = script_command(no_option, script, source)
        self.assertEqual(command[-1], 'cleanM.py')
        stored_option = SimpleNamespace(get=lambda model, key: SimpleNamespace(value='["--no-rename"]'))
        command = script_command(stored_option, script, source)
        self.assertEqual(command[-2:], ['cleanM.py', '--no-rename'])

    def test_unexpected_options_are_rejected(self):
        script = SimpleNamespace(id=3)
        stored_option = SimpleNamespace(get=lambda model, key: SimpleNamespace(value='["--dir", "/tmp"]'))
        with self.assertRaises(ValueError):
            script_command(stored_option, script, Path('cleanM.py'))


if __name__ == '__main__':
    unittest.main()
