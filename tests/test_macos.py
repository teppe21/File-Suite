"""
macOS behavior tests. The macOS branches are exercised on every OS by
patching ``IS_MACOS``; real-filesystem checks run only on macOS.
"""

from __future__ import annotations

import errno
import importlib
import stat
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import core
import platform_utils
from core import build_collision_safe_path, validate_folder_name
from models import OperationStatus
from operations import (
    build_organization_plan,
    execute_operation_plan,
    undo_last_operation,
)
from platform_utils import (
    SF_DATALESS,
    describe_os_error,
    is_cloud_placeholder,
    is_hidden,
)

ON_MACOS = sys.platform == "darwin"


def _flags(value: int):
    return patch.object(Path, "lstat", return_value=SimpleNamespace(st_flags=value))


class FlagTests(unittest.TestCase):
    def test_hidden_flag(self):
        with patch("platform_utils.IS_MACOS", True), patch("platform_utils.IS_WINDOWS", False):
            with _flags(stat.UF_HIDDEN):
                self.assertTrue(is_hidden(Path("file.txt")))
            with _flags(0):
                self.assertFalse(is_hidden(Path("file.txt")))
            with patch.object(Path, "lstat", side_effect=PermissionError()):
                self.assertFalse(is_hidden(Path("file.txt")))
            self.assertTrue(is_hidden(Path(".env")))

    def test_hidden_flag_ignored_off_macos(self):
        with patch("platform_utils.IS_MACOS", False), patch("platform_utils.IS_WINDOWS", False):
            with _flags(stat.UF_HIDDEN):
                self.assertFalse(is_hidden(Path("file.txt")))

    def test_dataless_placeholder(self):
        self.assertEqual(SF_DATALESS, 0x40000000)
        with patch("platform_utils.IS_MACOS", True), patch("platform_utils.IS_WINDOWS", False):
            with _flags(SF_DATALESS | stat.UF_HIDDEN):
                self.assertTrue(is_cloud_placeholder(Path("x")))
            with _flags(stat.UF_HIDDEN):
                self.assertFalse(is_cloud_placeholder(Path("x")))
            with patch.object(Path, "lstat", side_effect=FileNotFoundError()):
                self.assertFalse(is_cloud_placeholder(Path("x")))

    def test_dataless_ignored_off_macos(self):
        with patch("platform_utils.IS_MACOS", False), patch("platform_utils.IS_WINDOWS", False):
            with _flags(SF_DATALESS):
                self.assertFalse(is_cloud_placeholder(Path("x")))

    @unittest.skipUnless(ON_MACOS, "macOS only")
    def test_real_file_is_not_hidden_or_dataless(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "a.txt"
            f.write_text("x")
            self.assertFalse(is_hidden(f))
            self.assertFalse(is_cloud_placeholder(f))


class MessageTests(unittest.TestCase):
    def _exc(self, code: int, filename: str | None = "x") -> OSError:
        return OSError(code, "raw", filename)

    def test_permission_message(self):
        for code in (errno.EPERM, errno.EACCES):
            with patch("platform_utils.IS_MACOS", True), patch("platform_utils.IS_WINDOWS", False), _flags(0):
                msg = describe_os_error(self._exc(code))
            self.assertIn("Privacy & Security", msg)

    def test_locked_file_message(self):
        with patch("platform_utils.IS_MACOS", True), patch("platform_utils.IS_WINDOWS", False), _flags(stat.UF_IMMUTABLE):
            self.assertIn("locked in Finder", describe_os_error(self._exc(errno.EPERM)))

    def test_other_errors_and_platforms_unchanged(self):
        exc = self._exc(errno.EPERM)
        with patch("platform_utils.IS_MACOS", True), patch("platform_utils.IS_WINDOWS", False):
            self.assertEqual(describe_os_error(self._exc(errno.ENOENT)), str(self._exc(errno.ENOENT)))
        with patch("platform_utils.IS_MACOS", False), patch("platform_utils.IS_WINDOWS", False):
            self.assertEqual(describe_os_error(exc), str(exc))

    def test_labels(self):
        with patch("platform_utils.IS_MACOS", True), patch("platform_utils.IS_WINDOWS", False):
            self.assertEqual(platform_utils.mono_font(), "Menlo")
            self.assertEqual(platform_utils.trash_label(), "Trash")
            label = platform_utils.trash_label()
            self.assertEqual(label.title(), "Trash")
            self.assertEqual(label[:1].upper() + label[1:], "Trash")
        with patch("platform_utils.IS_MACOS", False), patch("platform_utils.IS_WINDOWS", False):
            self.assertEqual(platform_utils.mono_font(), "Monospace")
            self.assertEqual(platform_utils.trash_label(), "system trash")


class CoreTests(unittest.TestCase):
    def test_categories_only_on_macos(self):
        for flag in (True, False):
            with patch("platform_utils.IS_MACOS", flag):
                importlib.reload(core)
                for ext in (".dmg", ".pkg", ".command"):
                    self.assertEqual(ext in core.CATEGORIES["Installers & Code"], flag)
        importlib.reload(core)

    def test_colon_rejected_on_macos_only(self):
        with patch("core.IS_MACOS", True), patch("core.IS_WINDOWS", False):
            ok, msg = validate_folder_name("a:b")
            self.assertFalse(ok)
            self.assertIn(":", msg)
            self.assertEqual(validate_folder_name("a b"), (True, "a b"))
        with patch("core.IS_MACOS", False), patch("core.IS_WINDOWS", False):
            self.assertEqual(validate_folder_name("a:b"), (True, "a:b"))


class CollisionTests(unittest.TestCase):
    def test_reserved_set_plain_off_macos(self):
        with patch("platform_utils.IS_MACOS", False):
            reserved = platform_utils.new_reserved_set()
            self.assertEqual(platform_utils.collision_key(Path("A.txt")), Path("A.txt"))
        self.assertIs(type(reserved), set)

    def test_case_and_normalization_collide_on_macos(self):
        nfc = unicodedata.normalize("NFC", "é.txt")
        nfd = unicodedata.normalize("NFD", "é.txt")
        with patch("platform_utils.IS_MACOS", True):
            reserved = platform_utils.new_reserved_set()
            reserved.add(Path("/d/A.txt"))
            reserved.add(Path("/d") / nfc)
            self.assertIn(Path("/d/a.TXT"), reserved)
            self.assertIn(Path("/d") / nfd, reserved)
            self.assertNotIn(Path("/d/b.txt"), reserved)
            with tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                r = platform_utils.new_reserved_set()
                r.add(d / "A.txt")
                self.assertEqual(build_collision_safe_path(d, "a.txt", r), d / "a_1.txt")

    def test_case_sensitive_off_macos(self):
        with patch("platform_utils.IS_MACOS", False), tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            r = platform_utils.new_reserved_set()
            r.add(d / "A.txt")
            self.assertEqual(build_collision_safe_path(d, "a.txt", r), d / "a.txt")

    def test_batch_with_case_variants_organizes_and_undoes(self):
        with patch("platform_utils.IS_MACOS", True), tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            names = ["A.txt", "a.txt", unicodedata.normalize("NFC", "é.txt"), unicodedata.normalize("NFD", "é.txt")]
            made = []
            for n in names:
                p = root / n
                if p.exists():  # case/normalization-insensitive filesystem
                    continue
                p.write_text(n)
                made.append(n)
            ok, plan, err = build_organization_plan(root, {".txt"})
            self.assertTrue(ok, err)
            dests = {platform_utils.collision_key(i.destination) for i in plan.items}
            self.assertEqual(len(dests), len(plan.items))
            result = execute_operation_plan(plan)
            self.assertEqual(result.failed_moves, [])
            self.assertTrue(all(i.status == OperationStatus.APPLIED for i in plan.items))
            self.assertEqual(sorted(p.name for p in (root / "Documents").iterdir()).__len__(), len(made))
            restored, failed, errors, _ = undo_last_operation(result)
            self.assertEqual((restored, failed, errors), (len(made), 0, []))
            self.assertEqual(sorted(p.name for p in root.iterdir() if p.is_file()).__len__(), len(made))


if __name__ == "__main__":
    unittest.main()
