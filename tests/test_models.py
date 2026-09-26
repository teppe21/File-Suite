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

    def test_scan_progress(self):
        prog = ScanProgress(step="Scanning", current=5, total=20, files_discovered=25)
        self.assertEqual(prog.step, "Scanning")
        self.assertEqual(prog.current, 5)
        self.assertEqual(prog.total, 20)
        self.assertEqual(prog.files_discovered, 25)


if __name__ == "__main__":
    unittest.main()
