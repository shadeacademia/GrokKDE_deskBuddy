import unittest

from prefs import account_signed_in, autostart_enabled, desktop_entry
from pathlib import Path


class PrefsTest(unittest.TestCase):
    def test_signed_in_requires_a_user_id(self):
        self.assertFalse(account_signed_in(None))
        self.assertFalse(account_signed_in({}))
        self.assertFalse(account_signed_in({"https://auth.example": {"auth_mode": "oidc"}}))
        self.assertTrue(account_signed_in({"https://auth.example": {"user_id": "abc"}}))

    def test_hidden_desktop_file_is_off(self):
        self.assertFalse(autostart_enabled(""))
        self.assertTrue(autostart_enabled("[Desktop Entry]\nName=Grok Corner\n"))
        self.assertFalse(autostart_enabled("[Desktop Entry]\nHidden=true\n"))

    def test_desktop_entry_quotes_paths_with_spaces(self):
        text = desktop_entry(
            exec_path=Path("/home/a b/grok-corner"),
            work_path=Path("/home/a b"),
            icon=Path("/home/a b/icon.png"),
            autostart=True,
            hidden=True,
        )
        self.assertIn('Exec="/home/a b/grok-corner"', text)
        self.assertIn("X-KDE-autostart-phase=2", text)
        self.assertIn("Hidden=true", text)
        self.assertTrue(text.endswith("\n"))

    def test_launcher_entry_has_no_autostart_phase(self):
        text = desktop_entry(
            exec_path=Path("/home/grok/grok-corner/grok-corner"),
            work_path=Path("/home/grok"),
            icon=Path("/home/grok/grok-corner/grok-corner.png"),
            autostart=False,
        )
        self.assertNotIn("X-KDE-autostart-phase", text)
        self.assertNotIn("Hidden=", text)
        self.assertIn("Name=Grok Corner", text)
