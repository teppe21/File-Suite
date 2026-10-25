"""
macOS behavior tests. The macOS branches are exercised on every OS by
patching ``IS_MACOS`` and the ``macos_flags`` seam; tests that need a real
APFS filesystem are skipped elsewhere.
"""

from __future__ import annotations

import errno
import importlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import core
import platform_utils
from core import validate_folder_name
from duplicates import scan_duplicates
from models import OperationStatus
from operations import (
    build_organization_plan,
    execute_operation_plan,
    move_to_system_trash,
    undo_last_operation,
)
from platform_utils import (
    SF_DATALESS,
    UF_HIDDEN,
    describe_os_error,
    is_cloud_placeholder,
    is_hidden,
    macos_name_problem,
    move_file,
    trash_macos,
    trash_may_be_permanent,
)

ON_MACOS = sys.platform == "darwin"
REAL_TRASH = ON_MACOS and os.environ.get("FILESUITE_REAL_TRASH_TEST") == "1"
NFC = unicodedata.normalize("NFC", "café.txt")
NFD = unicodedata.normalize("NFD", "café.txt")


def _macos(enabled: bool = True):
    """Pretend to run on macOS (or on Linux when ``enabled`` is False)."""
    return patch("platform_utils.IS_MACOS", enabled), patch("platform_utils.IS_WINDOWS", False)


class MacosFlagTests(unittest.TestCase):
    def test_constants_match_xnu(self):
        self.assertEqual(UF_HIDDEN, 0x8000)
        self.assertEqual(SF_DATALESS, 0x40000000)

    def test_macos_flags_reads_lstat(self):
        with patch("platform_utils.IS_MACOS", True):
            with patch.object(Path, "lstat", return_value=SimpleNamespace(st_flags=UF_HIDDEN)):
                self.assertEqual(platform_utils.macos_flags(Path("x")), UF_HIDDEN)
            with patch.object(Path, "lstat", side_effect=PermissionError()):
                self.assertIsNone(platform_utils.macos_flags(Path("x")))
        with patch("platform_utils.IS_MACOS", False), patch.object(Path, "lstat") as lstat:
            self.assertIsNone(platform_utils.macos_flags(Path("x")))
            lstat.assert_not_called()

    def test_hidden_flag(self):
        cases = {
            UF_HIDDEN: True,
            UF_HIDDEN | SF_DATALESS: True,
            SF_DATALESS: False,
            0: False,
            None: True,  # unreadable flags are treated as hidden, as on Windows
        }
        mac, win = _macos()
        for flags, expected in cases.items():
            with mac, win, patch("platform_utils.macos_flags", return_value=flags):
                self.assertEqual(is_hidden(Path("file.txt")), expected, flags)
        with mac, win, patch("platform_utils.macos_flags", return_value=0):
            self.assertTrue(is_hidden(Path(".env")))

    def test_dataless_placeholder(self):
        cases = {
            SF_DATALESS: True,
            SF_DATALESS | UF_HIDDEN: True,
            UF_HIDDEN: False,
            0: False,
            None: False,  # unreadable flags: not a placeholder, as on Windows
        }
        mac, win = _macos()
        for flags, expected in cases.items():
            with mac, win, patch("platform_utils.macos_flags", return_value=flags):
                self.assertEqual(is_cloud_placeholder(Path("file.txt")), expected, flags)

    def test_flags_ignored_off_macos(self):
        mac, win = _macos(False)
        with mac, win, patch.object(Path, "lstat", return_value=SimpleNamespace(st_flags=UF_HIDDEN | SF_DATALESS)):
            self.assertFalse(is_hidden(Path("file.txt")))
            self.assertFalse(is_cloud_placeholder(Path("file.txt")))

    def test_windows_branch_wins_when_both_flags_set(self):
        with patch("platform_utils.IS_MACOS", True), patch("platform_utils.IS_WINDOWS", True), \
                patch("platform_utils.windows_attrs", return_value=0), \
                patch("platform_utils.macos_flags", return_value=UF_HIDDEN | SF_DATALESS):
            self.assertFalse(is_hidden(Path("file.txt")))
            self.assertFalse(is_cloud_placeholder(Path("file.txt")))


class MacosMessageTests(unittest.TestCase):
    def _exc(self, code: int) -> OSError:
        return OSError(code, os.strerror(code), "/Users/me/Downloads")

    def test_eperm_message(self):
        mac, win = _macos()
        with mac, win:
            msg = describe_os_error(self._exc(errno.EPERM))
        for part in ("locked in Finder", "Get Info", "Privacy & Security", "Files and Folders", "Full Disk Access"):
            self.assertIn(part, msg)

    def test_other_errors_unchanged_on_macos(self):
        mac, win = _macos()
        for code in (errno.EACCES, errno.ENOENT, errno.EEXIST):
            exc = self._exc(code)
            with mac, win:
                self.assertEqual(describe_os_error(exc), str(exc))

    def test_eperm_unchanged_off_macos(self):
        exc = self._exc(errno.EPERM)
        mac, win = _macos(False)
        with mac, win:
            self.assertEqual(describe_os_error(exc), str(exc))
        exc.winerror = 5
        with patch("platform_utils.IS_MACOS", True), patch("platform_utils.IS_WINDOWS", True):
            self.assertEqual(describe_os_error(exc), "Access denied (file is locked, read-only, or protected).")

    def test_folder_listing_error_uses_message_on_macos_only(self):
        exc = PermissionError(errno.EPERM, "Operation not permitted", "/Users/me/Downloads")
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, "iterdir", side_effect=exc):
            mac, win = _macos()
            with mac, win, patch("operations.IS_MACOS", True):
                ok, _, err = build_organization_plan(Path(tmp), {".txt"})
            self.assertFalse(ok)
            self.assertIn("Failed to list directory contents: ", err)
            self.assertIn("Privacy & Security", err)
            mac, win = _macos(False)
            with mac, win, patch("operations.IS_MACOS", False):
                ok, _, err = build_organization_plan(Path(tmp), {".txt"})
            self.assertEqual(err, f"Failed to list directory contents: {exc}")


class MacosLabelTests(unittest.TestCase):
    def test_labels(self):
        mac, win = _macos()
        with mac, win:
            self.assertEqual(platform_utils.mono_font(), "Menlo")
            label = platform_utils.trash_label()
        self.assertEqual(label, "Trash")
        # The phrasings built around trash_label() in ui/app.py and ui/duplicates_view.py.
        self.assertEqual(f"Send duplicates to the {label}?", "Send duplicates to the Trash?")
        self.assertEqual(f"Send 3 files to {label}", "Send 3 files to Trash")
        self.assertEqual(f"Move 3 files to {label.title()}", "Move 3 files to Trash")
        self.assertEqual(label[:1].upper() + label[1:], "Trash")

    def test_labels_unchanged_off_macos(self):
        mac, win = _macos(False)
        with mac, win:
            self.assertEqual(platform_utils.mono_font(), "Monospace")
            self.assertEqual(platform_utils.trash_label(), "system trash")
        with patch("platform_utils.IS_MACOS", True), patch("platform_utils.IS_WINDOWS", True):
            self.assertEqual(platform_utils.mono_font(), "Consolas")
            self.assertEqual(platform_utils.trash_label(), "Recycle Bin")


class MacosCoreTests(unittest.TestCase):
    def test_categories_only_on_macos(self):
        try:
            for enabled in (True, False):
                with patch("platform_utils.IS_MACOS", enabled):
                    importlib.reload(core)
                    for ext in (".dmg", ".pkg", ".command"):
                        self.assertEqual(ext in core.CATEGORIES["Installers & Code"], enabled, ext)
                    self.assertEqual(core.classify_extension(".dmg", ".dmg"), "Installers & Code" if enabled else None)
        finally:
            importlib.reload(core)

    def test_colon_rejected_on_macos_only(self):
        self.assertIsNotNone(macos_name_problem("a:b"))
        for name in ("Sorted", "a b", "Ünïcode", "a?b", "a*b", 'a"b'):
            self.assertIsNone(macos_name_problem(name), name)
        with patch("core.IS_MACOS", True), patch("core.IS_WINDOWS", False):
            ok, msg = validate_folder_name("a:b")
            self.assertFalse(ok)
            self.assertIn("Finder", msg)
            self.assertEqual(validate_folder_name("a b"), (True, "a b"))
        with patch("core.IS_MACOS", False), patch("core.IS_WINDOWS", False):
            self.assertEqual(validate_folder_name("a:b"), (True, "a:b"))


class MacosCollisionSeamTests(unittest.TestCase):
    def test_reserved_set_plain_off_macos(self):
        with patch("platform_utils.IS_MACOS", False):
            reserved = platform_utils.new_reserved_set()
            self.assertEqual(platform_utils.collision_key(Path("A.txt")), Path("A.txt"))
        self.assertIs(type(reserved), set)

    def test_case_and_normalization_fold_on_macos(self):
        with patch("platform_utils.IS_MACOS", True):
            reserved = platform_utils.new_reserved_set()
            reserved.add(Path("/d/A.txt"))
            reserved.add(Path("/d") / NFC)
            self.assertIn(Path("/d/a.TXT"), reserved)
            self.assertIn(Path("/d") / NFD, reserved)
            self.assertNotIn(Path("/d/b.txt"), reserved)
            self.assertNotIn(Path("/e/a.txt"), reserved)

    def test_renamed_destination_cannot_shadow_later_source(self):
        # "A.txt" is renamed to "A_1.txt" because Documents has "a.txt"; the later
        # source "a_1.txt" must not be planned onto the same (case-folded) name.
        with tempfile.TemporaryDirectory() as tmp, patch("platform_utils.IS_MACOS", True), \
                patch("platform_utils.macos_flags", return_value=0):
            root = Path(tmp)
            (root / "Documents").mkdir()
            (root / "Documents" / "a.txt").write_text("old")
            (root / "A.txt").write_text("A")
            (root / "a_1.txt").write_text("a1")
            ok, plan, err = build_organization_plan(root, {".txt"})
            self.assertTrue(ok, err)
            names = [i.destination.name for i in plan.executable_items]
            self.assertEqual(len({platform_utils.collision_key(Path(n)) for n in names}), 2, names)


@unittest.skipUnless(ON_MACOS, "macOS only")
class MacosFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)

    def tearDown(self):
        for p in self.target.rglob("*"):
            os.chflags(p, 0, follow_symlinks=False)
        self.tmp.cleanup()

    def _require_case_insensitive(self):
        probe = self.target / "CaseProbe"
        probe.write_text("x")
        insensitive = (self.target / "caseprobe").exists()
        probe.unlink()
        if not insensitive:
            self.skipTest("volume is case-sensitive")

    def _item(self, plan, name: str):
        return next(i for i in plan.items if i.source.name == name)

    def test_real_file_flags(self):
        f = self.target / "a.txt"
        f.write_text("x")
        self.assertEqual(platform_utils.macos_flags(f), 0)
        self.assertFalse(is_hidden(f))
        self.assertFalse(is_cloud_placeholder(f))
        os.chflags(f, UF_HIDDEN)
        self.assertTrue(is_hidden(f))
        self.assertFalse(is_cloud_placeholder(f))

    def test_hidden_flag_skipped_by_organize_and_scan(self):
        for name in ("a.txt", "b.txt", "c.txt"):
            (self.target / name).write_text("same content")
        os.chflags(self.target / "c.txt", UF_HIDDEN)

        ok, plan, err = build_organization_plan(self.target, {".txt"})
        self.assertTrue(ok, err)
        self.assertEqual(self._item(plan, "c.txt").skip_reason, "Hidden file skipped")
        self.assertEqual(self._item(plan, "a.txt").status, OperationStatus.PENDING)

        groups = scan_duplicates(self.target)
        self.assertEqual(len(groups), 1)
        self.assertEqual(sorted(f.path.name for f in groups[0].files), ["a.txt", "b.txt"])

    def test_case_collision_is_renamed_and_undone(self):
        self._require_case_insensitive()
        docs = self.target / "Documents"
        docs.mkdir()
        (docs / "report.pdf").write_text("existing")
        (self.target / "Report.PDF").write_text("new")

        ok, plan, err = build_organization_plan(self.target, {".pdf"})
        self.assertTrue(ok, err)
        item = self._item(plan, "Report.PDF")
        self.assertEqual(item.destination, docs / "Report_1.PDF")
        self.assertTrue(item.is_collision)

        result = execute_operation_plan(plan)
        self.assertEqual(result.failed_moves, [])
        self.assertEqual(sorted(p.name for p in docs.iterdir()), ["Report_1.PDF", "report.pdf"])
        self.assertEqual((docs / "report.pdf").read_text(), "existing")
        self.assertEqual((docs / "Report_1.PDF").read_text(), "new")

        undone, failed, errors, notes = undo_last_operation(result)
        self.assertEqual((undone, failed, errors, notes), (1, 0, [], []))
        self.assertEqual((self.target / "Report.PDF").read_text(), "new")
        self.assertEqual([p.name for p in docs.iterdir()], ["report.pdf"])

    def test_nfc_and_nfd_are_one_name(self):
        docs = self.target / "Documents"
        docs.mkdir()
        (docs / NFD).write_text("existing")
        (self.target / NFC).write_text("new")
        self.assertTrue((self.target / NFD).exists())  # one directory cannot hold both spellings

        ok, plan, err = build_organization_plan(self.target, {".txt"})
        self.assertTrue(ok, err)
        item = self._item(plan, NFC)
        self.assertEqual(unicodedata.normalize("NFC", item.destination.name), "café_1.txt")

        result = execute_operation_plan(plan)
        self.assertEqual(result.failed_moves, [])
        self.assertEqual(len(list(docs.iterdir())), 2)
        self.assertEqual((docs / NFC).read_text(), "existing")

        self.assertEqual(undo_last_operation(result)[:3], (1, 0, []))
        self.assertEqual((self.target / NFC).read_text(), "new")

    def test_batch_rename_chain_plans_distinct_names(self):
        self._require_case_insensitive()
        docs = self.target / "Documents"
        docs.mkdir()
        (docs / "a.txt").write_text("old")
        (self.target / "A.txt").write_text("A")
        (self.target / "a_1.txt").write_text("a1")

        ok, plan, err = build_organization_plan(self.target, {".txt"})
        self.assertTrue(ok, err)
        planned = sorted(i.destination.name for i in plan.executable_items)
        self.assertEqual(planned, ["A_1.txt", "a_1_1.txt"])

        result = execute_operation_plan(plan)
        self.assertEqual(result.failed_moves, [])
        self.assertEqual(sorted(r.destination.name for r in result.successful_moves), planned)
        self.assertEqual(undo_last_operation(result)[:3], (2, 0, []))
        self.assertEqual(sorted(p.name for p in self.target.iterdir()), ["A.txt", "Documents", "a_1.txt"])


def _fake_foundation(ok: bool, description: str = "") -> tuple[SimpleNamespace, MagicMock]:
    """Return a stand-in ``Foundation`` module and its ``trashItemAtURL`` mock."""
    error = SimpleNamespace(localizedDescription=lambda: description)
    trash = MagicMock(return_value=(ok, None, None if ok else error))
    manager = SimpleNamespace(trashItemAtURL_resultingItemURL_error_=trash)
    foundation = SimpleNamespace(
        NSURL=SimpleNamespace(fileURLWithPath_=lambda path: f"file://{path}"),
        NSFileManager=SimpleNamespace(defaultManager=lambda: manager),
    )
    return foundation, trash


def _remove_tree(root: Path) -> None:
    """Delete ``root``, unlocking files first (a locked file cannot be removed)."""
    for path in root.rglob("*"):
        os.chflags(path, 0, follow_symlinks=False)
    # FAT removes "._name" together with "name", so listed entries can vanish.
    shutil.rmtree(root, ignore_errors=True)


def _run(*args: str) -> None:
    subprocess.run(args, check=True, capture_output=True)


class MacosTrashSeamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)
        self.file = self.target / "a.txt"
        self.file.write_text("data")

    def tearDown(self):
        self.tmp.cleanup()

    def _trash(self, path: Path, backend_result=(True, None), **kwargs):
        backend = MagicMock(return_value=backend_result)
        with patch("operations.IS_MACOS", True), patch("operations.IS_WINDOWS", False), patch(
            "operations.trash_macos", backend
        ):
            return move_to_system_trash(path, **kwargs), backend

    def test_dispatches_to_finder_trash(self):
        result, backend = self._trash(self.file)
        self.assertEqual(result, (True, None))
        backend.assert_called_once_with(self.file)
        result, _ = self._trash(self.file, (False, "Failed to trash 'a.txt': no Trash"))
        self.assertEqual(result, (False, "Failed to trash 'a.txt': no Trash"))

    def test_prechecks_run_before_backend(self):
        cases = [
            (self.target / "missing.txt", "File does not exist"),
            (self.target, "Path is not a regular file"),
        ]
        link = self.target / "link.txt"
        try:
            link.symlink_to(self.file)
            cases.append((link, "Refusing to trash symbolic link"))
        except OSError:
            pass  # no symlink privilege on this Windows runner
        for path, message in cases:
            with self.subTest(message):
                (ok, err), backend = self._trash(path)
                self.assertFalse(ok)
                self.assertIn(message, err or "")
                backend.assert_not_called()

    def test_explicit_trash_dir_keeps_freedesktop_layout(self):
        (ok, err), backend = self._trash(self.file, trash_dir=self.target / "Trash")
        self.assertTrue(ok, err)
        backend.assert_not_called()
        self.assertTrue((self.target / "Trash" / "files" / "a.txt").exists())

    def test_never_uses_xdg_trash(self):
        xdg, home = self.target / "xdg", self.target / "home"
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(xdg)}), patch(
            "operations.Path.home", return_value=home
        ):
            self._trash(self.file)
        self.assertFalse(xdg.exists())
        self.assertFalse(home.exists())

    def test_windows_branch_wins_when_both_flags_set(self):
        with patch("operations.IS_MACOS", True), patch("operations.IS_WINDOWS", True), patch(
            "operations.trash_macos"
        ) as mac, patch("operations.trash_windows", return_value=(True, None)) as win:
            self.assertEqual(move_to_system_trash(self.file), (True, None))
        win.assert_called_once_with(self.file)
        mac.assert_not_called()

    def test_backend_call(self):
        foundation, trash = _fake_foundation(ok=True)
        with patch.dict(sys.modules, {"Foundation": foundation}):
            self.assertEqual(trash_macos(self.file), (True, None))
        trash.assert_called_once_with(f"file://{self.file}", None, None)

    def test_backend_error_keeps_file(self):
        description = "“a.txt” couldn’t be moved to the trash."
        foundation, _ = _fake_foundation(ok=False, description=description)
        with patch("operations.IS_MACOS", True), patch("operations.IS_WINDOWS", False), patch.dict(
            sys.modules, {"Foundation": foundation}
        ):
            ok, err = move_to_system_trash(self.file)
        self.assertFalse(ok)
        self.assertEqual(err, f"Failed to trash 'a.txt': {description}")
        self.assertEqual(self.file.read_text(), "data")

    def test_missing_pyobjc_keeps_file(self):
        with patch.dict(sys.modules, {"Foundation": None}):
            ok, err = trash_macos(self.file)
        self.assertFalse(ok)
        self.assertIn("Failed to trash 'a.txt'", err or "")
        self.assertTrue(self.file.exists())

    def test_never_warns_about_permanent_deletion(self):
        with patch("platform_utils.IS_MACOS", True), patch("platform_utils.IS_WINDOWS", False), patch(
            "platform_utils.windows_drive_type"
        ) as seam:
            self.assertFalse(trash_may_be_permanent(self.file))
        seam.assert_not_called()


class MacosMoveSeamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)
        self.src = self.target / "a.txt"
        self.src.write_text("source")
        self.dst = self.target / "b.txt"

    def tearDown(self):
        self.tmp.cleanup()

    def _move(self, macos: bool, link_error: OSError) -> None:
        with patch("platform_utils.IS_MACOS", macos), patch("platform_utils.IS_WINDOWS", False), patch(
            "platform_utils.os.link", side_effect=link_error
        ):
            move_file(self.src, self.dst)

    def test_locked_file_is_not_copied_on_macos(self):
        eperm = PermissionError(errno.EPERM, "Operation not permitted")
        with patch("platform_utils._copy_then_unlink") as copy, self.assertRaises(PermissionError):
            self._move(True, eperm)
        copy.assert_not_called()
        self.assertEqual(self.src.read_text(), "source")
        self.assertFalse(self.dst.exists())

    def test_eperm_still_copies_off_macos(self):
        # Linux: EPERM from link() means "no hard links here" (e.g. vfat), as before.
        self._move(False, PermissionError(errno.EPERM, "Operation not permitted"))
        self.assertFalse(self.src.exists())
        self.assertEqual(self.dst.read_text(), "source")

    def test_other_fallback_errnos_still_copy_on_macos(self):
        for code in (errno.EXDEV, errno.ENOTSUP, errno.EMLINK):
            with self.subTest(errno=errno.errorcode[code]):
                self.src.write_text("source")
                self.dst.unlink(missing_ok=True)
                self._move(True, OSError(code, os.strerror(code)))
                self.assertFalse(self.src.exists())
                self.assertEqual(self.dst.read_text(), "source")


@unittest.skipUnless(ON_MACOS, "macOS only")
class MacosFatVolumeTests(unittest.TestCase):
    """Moves on a real FAT disk image, where hard links are unavailable."""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        image = Path(tmp.name) / "img.dmg"
        cls.volume = Path(tmp.name) / "mnt"
        cls.volume.mkdir()
        _run("hdiutil", "create", "-quiet", "-size", "20m", "-fs", "MS-DOS", "-volname", "FSTEST", str(image))
        _run("hdiutil", "attach", "-quiet", "-nobrowse", "-mountpoint", str(cls.volume), str(image))
        cls.addClassCleanup(_run, "hdiutil", "detach", "-force", str(cls.volume))

    def setUp(self):
        self.fat = Path(tempfile.mkdtemp(dir=self.volume))
        self.addCleanup(_remove_tree, self.fat)
        self.apfs = Path(tempfile.mkdtemp())
        self.addCleanup(_remove_tree, self.apfs)

    def _files(self, folder: Path) -> list[str]:
        # FAT keeps extended attributes in "._name" files; those are hidden anyway.
        return sorted(p.name for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))

    def test_link_errnos(self):
        src = self.fat / "a.txt"
        src.write_text("x")
        with self.assertRaises(OSError) as ctx:
            os.link(src, self.fat / "b.txt", follow_symlinks=False)
        self.assertEqual(ctx.exception.errno, errno.ENOTSUP, errno.errorcode.get(ctx.exception.errno))
        with self.assertRaises(OSError) as ctx:
            os.link(src, self.apfs / "b.txt", follow_symlinks=False)
        self.assertEqual(ctx.exception.errno, errno.EXDEV, errno.errorcode.get(ctx.exception.errno))

    def test_organize_uses_copy_fallback_and_undo_restores(self):
        for name in ("a.txt", "b.txt"):
            (self.fat / name).write_text(name)
        ok, plan, err = build_organization_plan(self.fat, {".txt"})
        self.assertTrue(ok, err)

        result = execute_operation_plan(plan)
        self.assertEqual(result.failed_moves, [])
        self.assertEqual(result.success_count, 2)
        self.assertEqual(self._files(self.fat), [])
        for record in result.successful_moves:
            self.assertEqual(record.destination.read_text(), record.source.name)

        self.assertEqual(undo_last_operation(result)[:3], (2, 0, []))
        self.assertEqual(self._files(self.fat), ["a.txt", "b.txt"])
        self.assertEqual((self.fat / "a.txt").read_text(), "a.txt")

    def test_existing_destination_is_never_replaced(self):
        for src_dir in (self.fat, self.apfs):
            with self.subTest(source=src_dir):
                src, dst = src_dir / "a.txt", self.fat / "b.txt"
                src.write_text("source")
                dst.write_text("existing")
                with self.assertRaises(FileExistsError):
                    move_file(src, dst)
                self.assertEqual(src.read_text(), "source")
                self.assertEqual(dst.read_text(), "existing")
                src.unlink()
                dst.unlink()

    def test_cross_volume_move(self):
        for src_dir, dst_dir in ((self.apfs, self.fat), (self.fat, self.apfs)):
            with self.subTest(source=src_dir):
                src, dst = src_dir / "a.txt", dst_dir / "moved.txt"
                src.write_text("data")
                move_file(src, dst)
                self.assertFalse(src.exists())
                self.assertEqual(dst.read_text(), "data")
                dst.unlink()

    def test_locked_file_is_reported_not_copied(self):
        # link() reports EPERM for a locked file before EXDEV or ENOTSUP.
        for src_dir, dst_dir in ((self.apfs, self.apfs), (self.fat, self.fat), (self.apfs, self.fat)):
            with self.subTest(source=src_dir, destination=dst_dir):
                src, dst = src_dir / "locked.txt", dst_dir / "moved.txt"
                src.write_text("locked")
                os.chflags(src, stat.UF_IMMUTABLE)
                with self.assertRaises(PermissionError) as ctx:
                    move_file(src, dst)
                self.assertIn("locked in Finder", describe_os_error(ctx.exception))
                self.assertEqual(src.read_text(), "locked")
                self.assertFalse(dst.exists())
                os.chflags(src, 0)
                src.unlink()

    def test_locked_file_fails_organize_without_stray_copy(self):
        locked = self.apfs / "locked.txt"
        locked.write_text("locked")
        os.chflags(locked, stat.UF_IMMUTABLE)
        ok, plan, err = build_organization_plan(self.apfs, {".txt"})
        self.assertTrue(ok, err)

        result = execute_operation_plan(plan)
        self.assertEqual(result.success_count, 0)
        self.assertEqual(len(result.failed_moves), 1)
        self.assertIn("locked in Finder", result.failed_moves[0][2])
        self.assertEqual(self._files(self.apfs), ["locked.txt"])
        self.assertEqual([p for p in self.apfs.rglob("*") if p.is_file() and p != locked], [])


@unittest.skipUnless(ON_MACOS, "macOS only")
class MacosExtendedAttributeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_volume_move_keeps_xattrs(self):
        # A hard link is the same file, so Finder tags (an xattr too) survive.
        src, dst = self.target / "a.txt", self.target / "b.txt"
        src.write_text("x")
        _run("/usr/bin/xattr", "-w", "org.filesuite.test", "kept", str(src))
        move_file(src, dst)
        value = subprocess.run(
            ["/usr/bin/xattr", "-p", "org.filesuite.test", str(dst)],
            check=True, capture_output=True, text=True,
        ).stdout
        self.assertEqual(value.strip(), "kept")


@unittest.skipUnless(REAL_TRASH, "set FILESUITE_REAL_TRASH_TEST=1 on macOS to use the real Trash")
class MacosRealTrashTests(unittest.TestCase):
    def test_file_lands_in_finder_trash(self):
        name = f"filesuite-trash-test-{uuid.uuid4().hex}.txt"
        trashed = Path.home() / ".Trash" / name
        with tempfile.TemporaryDirectory(dir=Path.home()) as tmp:
            f = Path(tmp) / name
            f.write_text("trash me")
            try:
                self.assertEqual(move_to_system_trash(f), (True, None))
                self.assertFalse(f.exists())
                # A unique name is kept; looking it up works even where privacy
                # settings block listing ~/.Trash.
                self.assertEqual(trashed.read_text(), "trash me")
            finally:
                trashed.unlink(missing_ok=True)
        self.assertFalse((Path.home() / ".local" / "share" / "Trash" / "files" / name).exists())


if __name__ == "__main__":
    unittest.main()
