"""
Unit tests for operations.py: plan building, execution, TOCTOU safety, and undo.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from models import ExecutionResult, OperationStatus
from operations import (
    build_duplicate_move_plan,
    build_organization_plan,
    execute_operation_plan,
    move_to_system_trash,
    undo_last_operation,
)


class OperationPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_categories_and_extensions(self):
        # Create files
        (self.target / "photo.jpg").write_text("image")
        (self.target / "doc.pdf").write_text("pdf document")
        (self.target / "archive.tar.gz").write_text("archive data")
        (self.target / "unwanted.xyz").write_text("ignore")

        selected = {".jpg", ".pdf", ".tar.gz"}
        ok, plan, err = build_organization_plan(self.target, selected)
        self.assertTrue(ok)
        self.assertIsNone(err)

        exec_items = plan.executable_items
        self.assertEqual(len(exec_items), 3)

        categories = {item.source.name: item.category for item in exec_items}
        self.assertEqual(categories["photo.jpg"], "Images")
        self.assertEqual(categories["doc.pdf"], "Documents")
        self.assertEqual(categories["archive.tar.gz"], "Archives")

        # Check skipped item
        skipped = [i for i in plan.items if i.status == OperationStatus.SKIPPED]
        skipped_names = [i.source.name for i in skipped]
        self.assertIn("unwanted.xyz", skipped_names)

    def test_plan_skips_symlinks(self):
        real_file = self.target / "real.txt"
        real_file.write_text("real content")
        symlink_file = self.target / "link.txt"
        try:
            os.symlink(real_file, symlink_file)
        except OSError:
            self.skipTest("Symlinks not supported in environment")

        ok, plan, _ = build_organization_plan(self.target, {".txt"})
        self.assertTrue(ok)

        # Real file is executable, symlink file is skipped
        exec_sources = [i.source.name for i in plan.executable_items]
        self.assertIn("real.txt", exec_sources)
        self.assertNotIn("link.txt", exec_sources)

        symlink_item = next(i for i in plan.items if i.source.name == "link.txt")
        self.assertEqual(symlink_item.status, OperationStatus.SKIPPED)
        self.assertIn("Symbolic link", symlink_item.skip_reason)

    def test_plan_skips_hidden_and_subdirectories(self):
        (self.target / ".hidden.txt").write_text("secret")
        (self.target / "subfolder").mkdir()
        (self.target / "subfolder" / "nested.txt").write_text("nested")
        (self.target / "normal.txt").write_text("normal")

        ok, plan, _ = build_organization_plan(self.target, {".txt"})
        self.assertTrue(ok)

        exec_sources = [i.source.name for i in plan.executable_items]
        self.assertEqual(exec_sources, ["normal.txt"])

    def test_plan_custom_destination_folder(self):
        (self.target / "file1.txt").write_text("data")
        (self.target / "file2.jpg").write_text("data")

        ok, plan, _ = build_organization_plan(self.target, {".txt", ".jpg"}, "My_Custom_Folder")
        self.assertTrue(ok)
        for item in plan.executable_items:
            self.assertEqual(item.destination.parent.name, "My_Custom_Folder")

    def test_plan_rejects_path_traversal(self):
        (self.target / "file.txt").write_text("data")
        ok, plan, err = build_organization_plan(self.target, {".txt"}, "../escape")
        self.assertFalse(ok)
        self.assertIsNotNone(err)


class ExecutionAndUndoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_execution_and_undo_cycle(self):
        f1 = self.target / "f1.txt"
        f2 = self.target / "f2.txt"
        f1.write_text("content 1")
        f2.write_text("content 2")

        ok, plan, _ = build_organization_plan(self.target, {".txt"})
        self.assertTrue(ok)

        # Execute
        result = execute_operation_plan(plan)
        self.assertEqual(result.success_count, 2)
        self.assertEqual(result.failure_count, 0)
        self.assertFalse(f1.exists())
        self.assertFalse(f2.exists())
        self.assertTrue((self.target / "Documents" / "f1.txt").exists())
        self.assertTrue((self.target / "Documents" / "f2.txt").exists())

        # Undo
        undone, failed, errors = undo_last_operation(result)
        self.assertEqual(undone, 2)
        self.assertEqual(failed, 0)
        self.assertEqual(len(errors), 0)
        self.assertTrue(f1.exists())
        self.assertTrue(f2.exists())
        self.assertEqual(f1.read_text(), "content 1")
        self.assertEqual(f2.read_text(), "content 2")

    def test_collision_during_execution(self):
        # Create existing file in destination folder
        docs_dir = self.target / "Documents"
        docs_dir.mkdir()
        (docs_dir / "notes.txt").write_text("existing note")

        # Source file in root with same name
        (self.target / "notes.txt").write_text("new note")

        ok, plan, _ = build_organization_plan(self.target, {".txt"})
        self.assertTrue(ok)

        result = execute_operation_plan(plan)
        self.assertEqual(result.success_count, 1)

        # Confirm original destination was NOT overwritten
        self.assertEqual((docs_dir / "notes.txt").read_text(), "existing note")
        # Confirm moved file received collision-safe name
        self.assertTrue((docs_dir / "notes_1.txt").exists())
        self.assertEqual((docs_dir / "notes_1.txt").read_text(), "new note")

    def test_undo_preserves_newly_created_file_at_source(self):
        f = self.target / "file.txt"
        f.write_text("original content")

        ok, plan, _ = build_organization_plan(self.target, {".txt"})
        result = execute_operation_plan(plan)
        self.assertEqual(result.success_count, 1)

        # While file was in Documents, someone created another file.txt at root!
        f.write_text("brand new content at root")

        # Undo must NOT overwrite the new file
        undone, failed, errors = undo_last_operation(result)
        self.assertEqual(undone, 1)
        self.assertEqual(failed, 0)
        # Original file at root is intact
        self.assertEqual(f.read_text(), "brand new content at root")
        # Restored file was placed at collision-safe location (e.g. file_1.txt)
        self.assertTrue((self.target / "file_1.txt").exists())
        self.assertEqual((self.target / "file_1.txt").read_text(), "original content")
        self.assertTrue(any("occupied" in err for err in errors))

    def test_toctou_source_deleted_before_execution(self):
        f = self.target / "ghost.txt"
        f.write_text("content")

        ok, plan, _ = build_organization_plan(self.target, {".txt"})
        # Delete source before execute
        f.unlink()

        result = execute_operation_plan(plan)
        self.assertEqual(result.success_count, 0)
        self.assertEqual(result.failure_count, 1)
        self.assertTrue(result.failed_moves[0][2].startswith("Source file no longer exists"))

    def test_duplicate_move_plan_and_undo(self):
        f1 = self.target / "dup1.jpg"
        f2 = self.target / "dup2.jpg"
        f1.write_text("data")
        f2.write_text("data")

        ok, plan, _ = build_duplicate_move_plan([f1, f2], self.target, "Duplicates")
        self.assertTrue(ok)
        self.assertEqual(plan.affected_count, 2)

        result = execute_operation_plan(plan)
        self.assertEqual(result.success_count, 2)
        self.assertTrue((self.target / "Duplicates" / "dup1.jpg").exists())

        undone, failed, _ = undo_last_operation(result)
        self.assertEqual(undone, 2)
        self.assertTrue(f1.exists())
        self.assertTrue(f2.exists())

    def test_destination_replaced_by_symlink_before_execution(self):
        """Prevent traversal if destination folder is replaced by a symlink before execution."""
        f = self.target / "contract.pdf"
        f.write_text("sensitive")

        ok, plan, _ = build_organization_plan(self.target, {".pdf"})
        self.assertTrue(ok)

        # Before execute, external party creates a symlink named 'Documents' pointing elsewhere
        outside_dir = self.target.parent / "outside_dir"
        outside_dir.mkdir(exist_ok=True)
        symlink_docs = self.target / "Documents"
        try:
            os.symlink(outside_dir, symlink_docs)
        except OSError:
            self.skipTest("Symlinks not supported")

        result = execute_operation_plan(plan)
        self.assertEqual(result.success_count, 0)
        self.assertEqual(result.failure_count, 1)
        self.assertTrue(any("symbolic link" in err for _, _, err in result.failed_moves))
        # Ensure file was not moved into outside_dir
        self.assertFalse((outside_dir / "contract.pdf").exists())
        self.assertTrue(f.exists())

    def test_undo_destination_is_symlink(self):
        """Undo refuses to restore a file if its destination was replaced by a symlink."""
        f = self.target / "file.txt"
        f.write_text("data")

        ok, plan, _ = build_organization_plan(self.target, {".txt"})
        self.assertTrue(ok)
        result = execute_operation_plan(plan)
        self.assertEqual(result.success_count, 1)

        moved_dest = self.target / "Documents" / "file.txt"
        self.assertTrue(moved_dest.exists())

        # Replace moved file with a symlink before undo
        outside_file = self.target.parent / "outside.txt"
        outside_file.write_text("outside")
        moved_dest.unlink()
        try:
            os.symlink(outside_file, moved_dest)
        except OSError:
            self.skipTest("Symlinks not supported")

        undone, failed, errors = undo_last_operation(result)
        self.assertEqual(undone, 0)
        self.assertEqual(failed, 1)
        self.assertTrue(any("symbolic link" in err for err in errors))

    def test_undo_partial_failure_and_retry(self):
        """Undo tracks un-restored items so repeated undo only retries failed moves."""
        f1 = self.target / "f1.txt"
        f2 = self.target / "f2.txt"
        f1.write_text("1")
        f2.write_text("2")

        ok, plan, _ = build_organization_plan(self.target, {".txt"})
        self.assertTrue(ok)
        result = execute_operation_plan(plan)
        self.assertEqual(result.success_count, 2)

        # Delete one destination file to force partial undo failure
        (self.target / "Documents" / "f1.txt").unlink()

        undone, failed, _ = undo_last_operation(result)
        self.assertEqual(undone, 1)
        self.assertEqual(failed, 1)
        self.assertTrue(f2.exists())
        self.assertFalse(f1.exists())

        # Result now retains only the 1 failed move
        self.assertEqual(len(result.successful_moves), 1)

        # Repeated undo without fixing f1 still fails gracefully
        undone2, failed2, _ = undo_last_operation(result)
        self.assertEqual(undone2, 0)
        self.assertEqual(failed2, 1)

    def test_repeated_undo_no_op(self):
        """Calling undo with no successful moves returns clear no-op message."""
        res = ExecutionResult(plan_target_dir=self.target, successful_moves=[])
        undone, failed, errors = undo_last_operation(res)
        self.assertEqual(undone, 0)
        self.assertEqual(failed, 0)
        self.assertIn("No operations to undo.", errors)


class SystemTrashTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)
        self.trash_dir = self.target / "Trash"

    def tearDown(self):
        self.tmp.cleanup()

    def test_trash_success(self):
        f = self.target / "to_delete.txt"
        f.write_text("trash me")

        ok, err = move_to_system_trash(f, trash_dir=self.trash_dir)
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertFalse(f.exists())

        # Check file was placed in Trash/files
        trashed_file = self.trash_dir / "files" / "to_delete.txt"
        self.assertTrue(trashed_file.exists())
        self.assertEqual(trashed_file.read_text(), "trash me")

        # Check metadata was created in Trash/info
        info_file = self.trash_dir / "info" / "to_delete.txt.trashinfo"
        self.assertTrue(info_file.exists())
        info_content = info_file.read_text()
        self.assertIn("[Trash Info]", info_content)
        self.assertIn("Path=", info_content)
        self.assertIn("DeletionDate=", info_content)

    def test_trash_collision(self):
        f1 = self.target / "dup.txt"
        f1.write_text("first")
        ok, _ = move_to_system_trash(f1, trash_dir=self.trash_dir)
        self.assertTrue(ok)

        # Another file with identical name
        f2 = self.target / "dup.txt"
        f2.write_text("second")
        ok2, _ = move_to_system_trash(f2, trash_dir=self.trash_dir)
        self.assertTrue(ok2)

        # Both exist in trash with collision-safe names
        self.assertTrue((self.trash_dir / "files" / "dup.txt").exists())
        self.assertTrue((self.trash_dir / "files" / "dup_1.txt").exists())
        self.assertTrue((self.trash_dir / "info" / "dup.txt.trashinfo").exists())
        self.assertTrue((self.trash_dir / "info" / "dup_1.txt.trashinfo").exists())

    def test_trash_symlink_rejected(self):
        real_file = self.target / "real.txt"
        real_file.write_text("real")
        symlink_file = self.target / "link.txt"
        try:
            os.symlink(real_file, symlink_file)
        except OSError:
            self.skipTest("Symlinks not supported")

        ok, err = move_to_system_trash(symlink_file, trash_dir=self.trash_dir)
        self.assertFalse(ok)
        self.assertIn("Refusing to trash symbolic link", err or "")
        self.assertTrue(symlink_file.exists())

    def test_trash_move_failure_cleans_metadata(self):
        f = self.target / "fail.txt"
        f.write_text("fail data")

        # Mock shutil.move to fail, simulating failure between metadata creation and file move
        with patch("shutil.move", side_effect=OSError("Disk full")):
            ok, err = move_to_system_trash(f, trash_dir=self.trash_dir)

        self.assertFalse(ok)
        self.assertIn("Disk full", err or "")
        # Original file still exists
        self.assertTrue(f.exists())
        # Metadata must have been cleaned up and not left orphaned
        info_file = self.trash_dir / "info" / "fail.txt.trashinfo"
        self.assertFalse(info_file.exists())


if __name__ == "__main__":
    unittest.main()

