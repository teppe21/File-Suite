"""
Windows-only tests that need a real Windows filesystem (NTFS attributes,
junctions, case-insensitive names, file locking). Skipped on other systems.
"""

from __future__ import annotations

import ctypes
import os
import sys
import tempfile
import unittest
from pathlib import Path

from core import validate_folder_name
from duplicates import scan_duplicates
from models import OperationStatus
from operations import build_organization_plan, execute_operation_plan
from platform_utils import (
    FILE_ATTRIBUTE_HIDDEN,
    FILE_ATTRIBUTE_SYSTEM,
    is_cloud_placeholder,
    move_file,
    windows_attrs,
)

ON_WINDOWS = sys.platform == "win32"


@unittest.skipUnless(ON_WINDOWS, "Windows only")
class WindowsFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _item(self, plan, name: str):
        return next(i for i in plan.items if i.source.name == name)

    def _set_attrs(self, path: Path, attrs: int) -> None:
        if not ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs):
            raise ctypes.WinError()

    def test_windows_attrs_real_files(self):
        f = self.target / "a.txt"
        f.write_text("data")
        self.assertIsInstance(windows_attrs(f), int)
        self.assertIsNone(windows_attrs(self.target / "missing.txt"))
        self.assertFalse(is_cloud_placeholder(f))

    def test_hidden_attribute_skipped_by_plan_and_scan(self):
        for attrs in (FILE_ATTRIBUTE_HIDDEN, FILE_ATTRIBUTE_SYSTEM):
            with self.subTest(attrs=attrs), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp)
                for name in ("a.txt", "b.txt", "h.txt"):
                    (target / name).write_text("same")
                self._set_attrs(target / "h.txt", attrs)

                ok, plan, _ = build_organization_plan(target, {".txt"})
                self.assertTrue(ok)
                self.assertEqual(self._item(plan, "h.txt").skip_reason, "Hidden file skipped")
                self.assertEqual(self._item(plan, "a.txt").status, OperationStatus.PENDING)

                groups = scan_duplicates(target)
                self.assertEqual(len(groups), 1)
                self.assertEqual({f.path.name for f in groups[0].files}, {"a.txt", "b.txt"})

    def test_junction_swapped_in_as_destination_is_rejected(self):
        import _winapi

        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        (self.target / "photo.jpg").write_text("img")
        ok, plan, _ = build_organization_plan(self.target, {".jpg"})
        self.assertTrue(ok)

        # Destination folder appears as a junction pointing outside after planning
        junction = self.target / "Images"
        _winapi.CreateJunction(outside.name, str(junction))
        try:
            result = execute_operation_plan(plan)
        finally:
            junction.rmdir()
        item = self._item(plan, "photo.jpg")
        self.assertEqual(item.status, OperationStatus.FAILED)
        self.assertEqual(len(result.successful_moves), 0)
        self.assertTrue((self.target / "photo.jpg").exists())
        self.assertEqual(list(Path(outside.name).iterdir()), [])

    def test_case_only_collision_gets_safe_name(self):
        (self.target / "Images").mkdir()
        (self.target / "Images" / "Photo.JPG").write_text("existing")
        (self.target / "photo.jpg").write_text("new")

        ok, plan, _ = build_organization_plan(self.target, {".jpg"})
        self.assertTrue(ok)
        item = self._item(plan, "photo.jpg")
        self.assertTrue(item.is_collision)

        execute_operation_plan(plan)
        self.assertEqual(item.status, OperationStatus.APPLIED)
        self.assertEqual(item.final_name, "photo_1.jpg")
        self.assertEqual((self.target / "Images" / "Photo.JPG").read_text(), "existing")
        self.assertEqual((self.target / "Images" / "photo_1.jpg").read_text(), "new")

    def test_open_file_move_fails_without_stray_copy(self):
        src = self.target / "notes.txt"
        src.write_text("data")
        ok, plan, _ = build_organization_plan(self.target, {".txt"})
        self.assertTrue(ok)

        with open(src, "rb"):
            result = execute_operation_plan(plan)

        item = self._item(plan, "notes.txt")
        self.assertEqual(item.status, OperationStatus.FAILED)
        self.assertIn("open in another program", item.error_message or "")
        self.assertEqual(len(result.failed_moves), 1)
        self.assertIn("open in another program", result.failed_moves[0][2])
        self.assertTrue(src.exists())
        self.assertEqual(list((self.target / "Documents").iterdir()), [])

    def test_move_file_never_overwrites(self):
        src, dst = self.target / "a.txt", self.target / "b.txt"
        src.write_text("src")
        dst.write_text("dst")
        with self.assertRaises(FileExistsError):
            move_file(src, dst)
        self.assertEqual(src.read_text(), "src")
        self.assertEqual(dst.read_text(), "dst")

    def test_reserved_folder_name_rejected_by_plan(self):
        (self.target / "a.txt").write_text("data")
        for name in ("NUL", "con", "nul.txt"):
            ok, plan, err = build_organization_plan(self.target, {".txt"}, custom_folder_name=name)
            self.assertFalse(ok, name)
            self.assertIn("reserved", err or "")
            self.assertEqual(plan.items, [])

    def test_validate_folder_name_rejects_windows_symbols(self):
        # Counterpart of test_core.test_symbols_in_names, which is skipped on Windows
        for name in ("foo:bar", "foo?bar", "foo*bar", 'a"b'):
            self.assertFalse(validate_folder_name(name)[0], name)
        self.assertEqual(validate_folder_name("a'b"), (True, "a'b"))

    @unittest.skipUnless(os.environ.get("CI"), "only enforced on CI")
    def test_symlinks_available_on_ci(self):
        # The existing symlink tests skip silently when symlinks are unavailable
        target = self.target / "real.txt"
        target.write_text("data")
        os.symlink(target, self.target / "link.txt")
        self.assertTrue((self.target / "link.txt").is_symlink())


if __name__ == "__main__":
    unittest.main()
