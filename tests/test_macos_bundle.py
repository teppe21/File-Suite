"""
The window icon inside the macOS .app: the bundle's .icns is the Dock icon, so
``_set_window_icon`` must not replace it with ``iconphoto``. Everywhere else the
icon code behaves as before. Display-free: the window is a mock.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent


class SetWindowIconTests(unittest.TestCase):
    def _call(self, *, macos: bool, frozen: bool) -> MagicMock:
        try:
            from ui.app import FileOrganizerApp
        except ImportError as exc:
            self.skipTest(f"ui.app needs tkinter: {exc}")
        window = MagicMock()
        with (
            patch("ui.app.IS_MACOS", macos),
            patch("ui.app.IS_WINDOWS", False),
            patch.object(sys, "frozen", frozen, create=True),
            patch("ui.app._resource_path", lambda name: ROOT / name),
            patch("ui.app.ImageTk.PhotoImage"),
        ):
            FileOrganizerApp._set_window_icon(window)
        return window

    def test_frozen_macos_keeps_the_bundle_icon(self):
        self.assertFalse(self._call(macos=True, frozen=True).iconphoto.called)

    def test_macos_from_source_still_sets_the_icon(self):
        self.assertTrue(self._call(macos=True, frozen=False).iconphoto.called)

    def test_frozen_elsewhere_still_sets_the_icon(self):
        self.assertTrue(self._call(macos=False, frozen=True).iconphoto.called)


if __name__ == "__main__":
    unittest.main()
