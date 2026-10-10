import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.core.session_context import CurrentSession
from app.ui.shell import ShellWindow


class SessionPersistenceTest(unittest.TestCase):
    def test_missing_persisted_user_falls_back_to_first_user(self):
        profiles = [
            {"type": "user", "id": "first-user"},
            {"type": "user", "id": "second-user"},
        ]

        selected = ShellWindow._resolve_current_user_id(
            profiles,
            "user-from-another-database",
        )

        self.assertEqual(selected, "first-user")

    def test_existing_persisted_user_is_retained(self):
        profiles = [
            {"type": "user", "id": "first-user"},
            {"type": "user", "id": "second-user"},
        ]

        selected = ShellWindow._resolve_current_user_id(profiles, "second-user")

        self.assertEqual(selected, "second-user")

    def test_no_users_clears_the_persisted_user(self):
        selected = ShellWindow._resolve_current_user_id([], "missing-user")

        self.assertIsNone(selected)

    def test_selecting_personal_profile_caches_that_user(self):
        dashboard = object()
        shell = SimpleNamespace(
            session=CurrentSession(current_user_id="old-user"),
            sidebar=SimpleNamespace(
                profiles=[
                    {
                        "key": "user:new-user",
                        "type": "user",
                        "id": "new-user",
                        "name": "New User",
                    }
                ],
                set_current_page=MagicMock(),
            ),
            settings_page=SimpleNamespace(set_current_user=MagicMock()),
            categories_page=SimpleNamespace(set_current_user=MagicMock()),
            user_management_page=SimpleNamespace(set_current_user=MagicMock()),
            pages=SimpleNamespace(setCurrentWidget=MagicMock()),
            dashboard_page=dashboard,
            _apply_profile=MagicMock(),
            _management_user_id=ShellWindow._management_user_id,
        )

        with patch("app.ui.shell.set_last_user_id") as cache_user:
            ShellWindow.handle_profile_changed(shell, "user:new-user")

        self.assertEqual(shell.session.current_user_id, "new-user")
        self.assertEqual(shell.session.active_profile_key, "user:new-user")
        cache_user.assert_called_once_with("new-user")
        shell.settings_page.set_current_user.assert_called_once_with(
            "new-user", "New User"
        )


if __name__ == "__main__":
    unittest.main()
