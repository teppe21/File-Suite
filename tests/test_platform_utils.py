"""
Unit tests for platform_utils.py and the Windows-specific behavior at its call sites.

Windows branches are exercised on every OS by patching ``IS_WINDOWS`` and the
``windows_attrs`` seam; tests that need a real Windows filesystem are skipped elsewhere.
"""

from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import platform_utils
from core import CATEGORIES, validate_folder_name
from duplicates import scan_duplicates
from models import DuplicateFile, DuplicateGroup, OperationStatus
from operations import (
    build_organization_plan,
    execute_operation_plan,
    move_to_system_trash,
)
from platform_utils import (
    FILE_ATTRIBUTE_HIDDEN,
    FILE_ATTRIBUTE_OFFLINE,
    FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS,
    FILE_ATTRIBUTE_RECALL_ON_OPEN,
    FILE_ATTRIBUTE_SYSTEM,
    IO_REPARSE_TAG_MOUNT_POINT,
    IO_REPARSE_TAG_SYMLINK,
    describe_os_error,
    is_cloud_placeholder,
    is_hidden,
    is_link_like,
    move_file,
    trash_windows,
    windows_name_problem,
)

ON_WINDOWS = sys.platform == "win32"
IO_REPARSE_TAG_CLOUD_6 = 0x9000601A  # OneDrive folder


class WindowsNameProblemTests(unittest.TestCase):
    def test_valid_names(self):
        for name in ("Sorted_Archive", "Photos", "my.folder", "Ünïcode", "CONSOLE", "COM0", "nulx", "a" * 255):
            self.assertIsNone(windows_name_problem(name), name)

    def test_forbidden_characters(self):
        for name in ("foo<", "foo>", "foo:bar", 'a"b', "a|b", "a?b", "a*b", "a\x01b", "a\x1fb", "a/b", "a\\b"):
            self.assertIsNotNone(windows_name_problem(name), name)

    def test_trailing_space_or_dot(self):
        self.assertIsNotNone(windows_name_problem("name."))
        self.assertIsNotNone(windows_name_problem("name "))

    def test_reserved_device_names(self):
        for name in ("CON", "con", "Nul", "NUL.txt", "nul.txt", "AUX.tar.gz", "COM1", "lpt9", "COM¹", "LPT³", "NUL .txt"):
            self.assertIsNotNone(windows_name_problem(name), name)

    def test_length_limit_counts_utf16_units(self):
        self.assertIsNotNone(windows_name_problem("a" * 256))
        self.assertIsNotNone(windows_name_problem("😀" * 128))  # 256 UTF-16 units

    def test_validate_folder_name_strict_only_on_windows(self):
        with patch("core.IS_WINDOWS", True):
            self.assertFalse(validate_folder_name("foo:bar")[0])
            self.assertFalse(validate_folder_name("nul")[0])
        with patch("core.IS_WINDOWS", False):
            self.assertEqual(validate_folder_name("foo:bar"), (True, "foo:bar"))

    def test_windows_categories(self):
        self.assertEqual(".exe" in CATEGORIES["Installers & Code"], ON_WINDOWS)
        self.assertIn(".sh", CATEGORIES["Installers & Code"])


class AttributeTests(unittest.TestCase):
    def test_dotfile_hidden_everywhere(self):
        for windows in (False, True):
            with patch("platform_utils.IS_WINDOWS", windows):
                self.assertTrue(is_hidden(Path(".env")))

    def test_hidden_on_linux_is_name_only(self):
        with patch("platform_utils.IS_WINDOWS", False), patch("platform_utils.windows_attrs") as attrs:
            self.assertFalse(is_hidden(Path("file.txt")))
            attrs.assert_not_called()

    def test_hidden_on_windows_uses_attributes(self):
        cases = {
            FILE_ATTRIBUTE_HIDDEN: True,
            FILE_ATTRIBUTE_SYSTEM: True,
            FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM: True,
            0x20: False,  # FILE_ATTRIBUTE_ARCHIVE
            0: False,
            None: True,  # unreadable attributes are treated as hidden
        }
        for attrs, expected in cases.items():
            with patch("platform_utils.IS_WINDOWS", True), patch("platform_utils.windows_attrs", return_value=attrs):
                self.assertEqual(is_hidden(Path("file.txt")), expected, attrs)

    def test_cloud_placeholder(self):
        for attrs in (FILE_ATTRIBUTE_OFFLINE, FILE_ATTRIBUTE_RECALL_ON_OPEN, FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS):
            with patch("platform_utils.IS_WINDOWS", True), patch("platform_utils.windows_attrs", return_value=attrs):
                self.assertTrue(is_cloud_placeholder(Path("file.txt")))
        for attrs in (0, FILE_ATTRIBUTE_HIDDEN, None):
            with patch("platform_utils.IS_WINDOWS", True), patch("platform_utils.windows_attrs", return_value=attrs):
                self.assertFalse(is_cloud_placeholder(Path("file.txt")))

    def test_windows_attrs_reads_lstat(self):
        with patch("platform_utils.IS_WINDOWS", True):
            with patch.object(Path, "lstat", return_value=SimpleNamespace(st_file_attributes=0x22)):
                self.assertEqual(platform_utils.windows_attrs(Path("x")), 0x22)
            with patch.object(Path, "lstat", side_effect=PermissionError()):
                self.assertIsNone(platform_utils.windows_attrs(Path("x")))

    @unittest.skipIf(ON_WINDOWS, "non-Windows behavior")
    def test_windows_attrs_none_off_windows(self):
        self.assertIsNone(platform_utils.windows_attrs(Path(__file__)))
        self.assertFalse(is_cloud_placeholder(Path(__file__)))


class IsLinkLikeTests(unittest.TestCase):
    def _windows_lstat(self, mode: int = stat.S_IFDIR, tag: int = 0, error: OSError | None = None):
        fake = MagicMock(
            side_effect=error,
            return_value=SimpleNamespace(st_mode=mode, st_reparse_tag=tag),
        )
        return patch("platform_utils.IS_WINDOWS", True), patch.object(Path, "lstat", fake)

    def _check(self, expected: bool, **kwargs):
        win, lstat = self._windows_lstat(**kwargs)
        with win, lstat:
            self.assertEqual(is_link_like(Path("x")), expected, kwargs)

    def test_windows_reparse_tags(self):
        self._check(True, tag=IO_REPARSE_TAG_MOUNT_POINT)
        self._check(True, mode=stat.S_IFLNK, tag=IO_REPARSE_TAG_SYMLINK)
        self._check(True, mode=stat.S_IFLNK)
        self._check(True, mode=stat.S_IFREG, tag=IO_REPARSE_TAG_SYMLINK)
        self._check(False, tag=IO_REPARSE_TAG_CLOUD_6)  # OneDrive folders are not links
        self._check(False)

    def test_windows_errors(self):
        self._check(False, error=FileNotFoundError())
        self._check(True, error=PermissionError())

    def test_linux_uses_is_symlink_only(self):
        for result in (False, True):
            with patch("platform_utils.IS_WINDOWS", False), patch.object(
                Path, "is_symlink", return_value=result
            ), patch.object(Path, "lstat") as lstat:
                self.assertEqual(is_link_like(Path("x")), result)
            lstat.assert_not_called()

    def test_real_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(is_link_like(root))
            self.assertFalse(is_link_like(root / "missing" / "child"))
            try:
                (root / "link").symlink_to(root)
            except OSError:
                self.skipTest("Symlinks not supported")
            self.assertTrue(is_link_like(root / "link"))


class OsErrorAndUiTests(unittest.TestCase):
    def _exc(self, winerror: int) -> OSError:
        exc = OSError("raw message")
        exc.winerror = winerror
        return exc

    def test_describe_os_error(self):
        with patch("platform_utils.IS_WINDOWS", True):
            self.assertIn("open in another program", describe_os_error(self._exc(32)))
            self.assertIn("Access denied", describe_os_error(self._exc(5)))
            self.assertIn("already exists", describe_os_error(self._exc(183)))
            self.assertEqual(describe_os_error(self._exc(2)), "raw message")
        with patch("platform_utils.IS_WINDOWS", False):
            self.assertEqual(describe_os_error(self._exc(32)), "raw message")

    def test_labels(self):
        with patch("platform_utils.IS_WINDOWS", False):
            self.assertEqual(platform_utils.mono_font(), "Monospace")
            self.assertEqual(platform_utils.trash_label(), "system trash")
        with patch("platform_utils.IS_WINDOWS", True):
            self.assertEqual(platform_utils.mono_font(), "Consolas")
            self.assertEqual(platform_utils.trash_label(), "Recycle Bin")


class MoveAndTrashTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_move_file(self):
        src = self.target / "a.txt"
        src.write_text("data")
        move_file(src, self.target / "b.txt")
        self.assertFalse(src.exists())
        self.assertEqual((self.target / "b.txt").read_text(), "data")

    def test_move_file_dispatch(self):
        src, dst = self.target / "a.txt", self.target / "b.txt"
        with patch("platform_utils.os.rename") as rename, patch("platform_utils.shutil.move") as move:
            with patch("platform_utils.IS_WINDOWS", True):
                move_file(src, dst)
            rename.assert_called_once_with(src, dst)
            move.assert_not_called()  # no copy fallback on Windows
            rename.reset_mock()
            with patch("platform_utils.IS_WINDOWS", False):
                move_file(src, dst)
            move.assert_called_once_with(str(src), str(dst))
            rename.assert_not_called()

    def test_move_file_windows_errors_propagate(self):
        with patch("platform_utils.IS_WINDOWS", True), patch(
            "platform_utils.os.rename", side_effect=FileExistsError()
        ), patch("platform_utils.shutil.move") as move, self.assertRaises(FileExistsError):
            move_file(self.target / "a.txt", self.target / "b.txt")
        move.assert_not_called()

    @unittest.skipUnless(ON_WINDOWS, "Windows file locking")
    def test_move_open_file_leaves_no_copy(self):
        src = self.target / "a.txt"
        src.write_text("data")
        dst = self.target / "b.txt"
        with open(src, "rb"), self.assertRaises(PermissionError) as ctx:
            move_file(src, dst)
        self.assertTrue(src.exists())
        self.assertFalse(dst.exists())
        self.assertIn("open in another program", describe_os_error(ctx.exception))

    def test_trash_windows(self):
        fake = MagicMock()
        with patch.dict(sys.modules, {"send2trash": SimpleNamespace(send2trash=fake)}):
            self.assertEqual(trash_windows(self.target / "a.txt"), (True, None))
            fake.side_effect = PermissionError("locked")
            ok, err = trash_windows(self.target / "a.txt")
        self.assertFalse(ok)
        self.assertIn("Failed to trash 'a.txt'", err or "")

    def test_move_to_system_trash_dispatch(self):
        f = self.target / "a.txt"
        f.write_text("data")
        fake = MagicMock()
        with patch("operations.IS_WINDOWS", True), patch.dict(
            sys.modules, {"send2trash": SimpleNamespace(send2trash=fake)}
        ):
            self.assertEqual(move_to_system_trash(self.target / "missing.txt")[0], False)
            self.assertEqual(move_to_system_trash(self.target)[0], False)  # not a regular file
            fake.assert_not_called()
            self.assertEqual(move_to_system_trash(f), (True, None))
            fake.assert_called_once_with(str(f))
            fake.side_effect = PermissionError("locked")
            ok, err = move_to_system_trash(f)
            self.assertFalse(ok)
            self.assertIn("Failed to trash 'a.txt'", err or "")
            fake.side_effect = None
            # An explicit trash_dir always uses the FreeDesktop layout
            ok, _ = move_to_system_trash(f, trash_dir=self.target / "Trash")
        self.assertTrue(ok)
        self.assertEqual(fake.call_count, 2)
        self.assertTrue((self.target / "Trash" / "files" / "a.txt").exists())


class CloudPlaceholderCallSiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)
        for name in ("a.txt", "b.txt"):
            (self.target / name).write_text("same")

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_skips_cloud_files(self):
        with patch("platform_utils.IS_WINDOWS", True), patch(
            "platform_utils.windows_attrs", return_value=FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
        ):
            ok, plan, _ = build_organization_plan(self.target, {".txt"})
        self.assertTrue(ok)
        self.assertEqual(plan.affected_count, 0)
        self.assertEqual(
            {i.skip_reason for i in plan.items},
            {"Cloud-only file skipped (would trigger download)"},
        )

    def test_scan_skips_cloud_files(self):
        with patch("platform_utils.IS_WINDOWS", True), patch(
            "platform_utils.windows_attrs", return_value=FILE_ATTRIBUTE_OFFLINE
        ), patch(
            "duplicates.calculate_sha256"
        ) as calc:
            self.assertEqual(scan_duplicates(self.target), [])
        calc.assert_not_called()


class UnknownInodeTests(unittest.TestCase):
    def test_zero_inodes_are_never_hard_links(self):
        files = [
            DuplicateFile(path=Path(f"/x/{n}"), size=10, is_original=(n == 0), inode=0, device=7)
            for n in range(3)
        ]
        group = DuplicateGroup(group_id="g", sha256="h", size=10, files=files)
        self.assertEqual(group.reclaimable_bytes, 20)


@unittest.skipUnless(ON_WINDOWS, "NTFS junctions")
class JunctionTests(unittest.TestCase):
    def setUp(self):
        import _winapi

        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)
        (self.target / "Real").mkdir()
        # Junction that stays inside the target: only the link check can reject it
        _winapi.CreateJunction(str(self.target / "Real"), str(self.target / "Images"))

    def tearDown(self):
        (self.target / "Images").rmdir()
        self.tmp.cleanup()

    def test_junction_is_link_like(self):
        self.assertFalse((self.target / "Images").is_symlink())
        self.assertTrue(is_link_like(self.target / "Images"))

    def test_execution_rejects_junction_destination(self):
        (self.target / "photo.jpg").write_text("img")
        ok, plan, _ = build_organization_plan(self.target, {".jpg"})
        self.assertTrue(ok)
        execute_operation_plan(plan)
        item = plan.items[[i.source.name for i in plan.items].index("photo.jpg")]
        self.assertEqual(item.status, OperationStatus.FAILED)
        self.assertIn("symbolic link", item.error_message or "")
        self.assertTrue((self.target / "photo.jpg").exists())


if __name__ == "__main__":
    unittest.main()
