"""
Unit tests for models.py dataclasses and properties.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from models import (
    DuplicateFile,
    DuplicateGroup,
    ExecutionResult,
    MoveRecord,
    OperationItem,
    OperationPlan,
    OperationStatus,
    OperationType,
    ScanProgress,
    clear_duplicate_selection,
    select_all_duplicates,
    update_duplicate_groups_after_removal,
)


class ModelsTests(unittest.TestCase):
    def test_operation_item_defaults(self):
        item = OperationItem(source=Path("/tmp/test.txt"), destination=Path("/tmp/Docs/test.txt"))
        self.assertEqual(item.original_name, "test.txt")
        self.assertEqual(item.final_name, "test.txt")
        self.assertEqual(item.action, OperationType.MOVE)
        self.assertEqual(item.status, OperationStatus.PENDING)

    def test_operation_plan_properties(self):
        item1 = OperationItem(
            source=Path("/tmp/a.txt"),
            destination=Path("/tmp/b.txt"),
            size=100,
            status=OperationStatus.PENDING,
            is_collision=False,
        )
        item2 = OperationItem(
            source=Path("/tmp/c.txt"),
            destination=Path("/tmp/c_1.txt"),
            size=250,
            status=OperationStatus.PENDING,
            is_collision=True,
        )
        item3 = OperationItem(
            source=Path("/tmp/d.txt"),
            destination=None,
            size=500,
            status=OperationStatus.SKIPPED,
        )

        plan = OperationPlan(target_dir=Path("/tmp"), items=[item1, item2, item3])
        self.assertEqual(plan.affected_count, 2)
        self.assertEqual(plan.total_size_bytes, 350)
        self.assertEqual(plan.collision_count, 1)
        self.assertEqual(plan.skipped_count, 1)
        self.assertEqual(len(plan.executable_items), 2)

    def test_execution_result_properties(self):
        res = ExecutionResult(plan_target_dir=Path("/tmp"))
        self.assertEqual(res.success_count, 0)
        self.assertEqual(res.failure_count, 0)
        self.assertFalse(res.is_partial_failure)

        res.successful_moves.append(
            MoveRecord(source=Path("/tmp/1.txt"), destination=Path("/tmp/2.txt"), size=10)
        )
        self.assertEqual(res.success_count, 1)
        self.assertFalse(res.is_partial_failure)

        res.failed_moves.append((Path("/tmp/3.txt"), Path("/tmp/4.txt"), "Error"))
        self.assertEqual(res.failure_count, 1)
        self.assertTrue(res.is_partial_failure)

    def test_duplicate_group_properties(self):
        f_orig = DuplicateFile(path=Path("/tmp/orig.jpg"), size=1024, is_original=True, selected=False)
        f_dup1 = DuplicateFile(path=Path("/tmp/copy1.jpg"), size=1024, is_original=False, selected=True)
        f_dup2 = DuplicateFile(path=Path("/tmp/copy2.jpg"), size=1024, is_original=False, selected=False)

        group = DuplicateGroup(
            group_id="group-1",
            sha256="abcdef123456",
            size=1024,
            files=[f_orig, f_dup1, f_dup2],
        )

        self.assertEqual(group.original, f_orig)
        self.assertEqual(len(group.duplicates), 2)
        self.assertEqual(len(group.selected_duplicates), 1)
        self.assertEqual(group.selected_duplicates[0], f_dup1)
        # 2 duplicates * 1024 = 2048 bytes
        self.assertEqual(group.reclaimable_bytes, 2048)

    def test_select_all_duplicates_preserves_originals(self):
        f_orig = DuplicateFile(path=Path("/tmp/orig.jpg"), size=100, is_original=True, selected=False)
        f_dup1 = DuplicateFile(path=Path("/tmp/dup1.jpg"), size=100, is_original=False, selected=False)
        f_dup2 = DuplicateFile(path=Path("/tmp/dup2.jpg"), size=100, is_original=False, selected=False)
        group = DuplicateGroup(group_id="1", sha256="hash", size=100, files=[f_orig, f_dup1, f_dup2])

        select_all_duplicates([group])
        self.assertFalse(f_orig.selected, "Preserved original must remain unselected")
        self.assertTrue(f_dup1.selected)
        self.assertTrue(f_dup2.selected)

        clear_duplicate_selection([group])
        self.assertFalse(f_orig.selected)
        self.assertFalse(f_dup1.selected)
        self.assertFalse(f_dup2.selected)

    def test_update_duplicate_groups_after_removal(self):
        p1 = Path("/tmp/f1.txt")
        p2 = Path("/tmp/f2.txt")
        p3 = Path("/tmp/f3.txt")
        f1 = DuplicateFile(path=p1, size=50, is_original=True, selected=False)
        f2 = DuplicateFile(path=p2, size=50, is_original=False, selected=True)
        f3 = DuplicateFile(path=p3, size=50, is_original=False, selected=False)
        group = DuplicateGroup(group_id="g1", sha256="h1", size=50, files=[f1, f2, f3])

        # Remove f2: 2 files remain, group remains
        updated = update_duplicate_groups_after_removal([group], {p2})
        self.assertEqual(len(updated), 1)
        self.assertEqual(len(updated[0].files), 2)
        self.assertEqual([f.path for f in updated[0].files], [p1, p3])

        # Remove f1 (the original): only f3 remains (< 2 files), group pruned entirely
        updated2 = update_duplicate_groups_after_removal(updated, {p1})
        self.assertEqual(len(updated2), 0)

        # Empty removal does not alter groups
        updated_empty = update_duplicate_groups_after_removal([group], set())
        self.assertEqual(len(updated_empty), 1)

    def test_scan_progress(self):
        prog = ScanProgress(step="Scanning", current=5, total=20, files_discovered=25)
        self.assertEqual(prog.step, "Scanning")
        self.assertEqual(prog.current, 5)
        self.assertEqual(prog.total, 20)
        self.assertEqual(prog.files_discovered, 25)


if __name__ == "__main__":
    unittest.main()
