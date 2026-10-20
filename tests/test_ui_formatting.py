"""
Unit tests for ui/formatting.py (pure helpers, no display needed).
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core import CATEGORIES
from models import DuplicateFile, DuplicateGroup, ExecutionResult, MoveRecord
from operations import build_organization_plan
from ui.formatting import (
    category_counts,
    extension_preview,
    format_log_line,
    format_size,
    plural,
    selection_summary,
    truncate_middle,
    undo_label,
)


def _group(*files: DuplicateFile, size: int = 100) -> DuplicateGroup:
    return DuplicateGroup(group_id="g", sha256="0" * 64, size=size, files=list(files))


class FormatSizeTests(unittest.TestCase):
    def test_edges(self):
        self.assertEqual(format_size(0), "0 B")
        self.assertEqual(format_size(1023), "1023 B")
        self.assertEqual(format_size(1024), "1.0 KB")
        self.assertEqual(format_size(int(1.5 * 1024 * 1024)), "1.5 MB")
        self.assertEqual(format_size(3 * 1024**3), "3.0 GB")
        self.assertEqual(format_size(2 * 1024**4), "2.0 TB")


class PluralTests(unittest.TestCase):
    def test_plural(self):
        self.assertEqual(plural(0, "file"), "0 files")
        self.assertEqual(plural(1, "file"), "1 file")
        self.assertEqual(plural(2, "file"), "2 files")
        self.assertEqual(plural(1, "copy", "copies"), "1 copy")
        self.assertEqual(plural(3, "copy", "copies"), "3 copies")


class ExtensionPreviewTests(unittest.TestCase):
    def test_short_list_has_no_suffix(self):
        self.assertEqual(extension_preview({".png", ".jpg"}), "jpg, png")

    def test_long_list_shows_remaining_count(self):
        exts = {".a", ".b", ".c", ".d", ".e", ".f"}
        self.assertEqual(extension_preview(exts), "a, b, c, d +2")

    def test_real_category(self):
        text = extension_preview(CATEGORIES["Images"])
        self.assertTrue(text.endswith(f"+{len(CATEGORIES['Images']) - 4}"))
        self.assertNotIn(".", text.split(" +")[0])


class TruncateMiddleTests(unittest.TestCase):
    def test_short_text_unchanged(self):
        self.assertEqual(truncate_middle("abc", 5), "abc")

    def test_long_text_keeps_both_ends(self):
        out = truncate_middle("C:/Users/someone/Downloads", 11)
        self.assertEqual(len(out), 11)
        self.assertTrue(out.startswith("C:/Us"))
        self.assertTrue(out.endswith("loads"))
        self.assertIn("…", out)


class CategoryCountsTests(unittest.TestCase):
    def test_counts_from_real_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("a.jpg", "b.png", "c.pdf", "d.zip", "e.jpg", "f.xyz"):
                (root / name).write_text("x")
            exts = CATEGORIES["Images"] | CATEGORIES["Documents"] | CATEGORIES["Archives"]
            ok, plan, _ = build_organization_plan(root, exts)
            self.assertTrue(ok)
            self.assertEqual(
                category_counts(plan),
                [("Images", 3), ("Archives", 1), ("Documents", 1)],
            )

    def test_custom_destination_is_one_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.jpg").write_text("x")
            (root / "b.pdf").write_text("x")
            ok, plan, _ = build_organization_plan(root, {".jpg", ".pdf"}, "Sorted")
            self.assertTrue(ok)
            self.assertEqual(category_counts(plan), [("Sorted", 2)])


class SelectionSummaryTests(unittest.TestCase):
    def test_totals(self):
        g1 = _group(
            DuplicateFile(Path("a"), 100, is_original=True),
            DuplicateFile(Path("b"), 100, selected=True),
            DuplicateFile(Path("c"), 100),
        )
        g2 = _group(
            DuplicateFile(Path("d"), 50, is_original=True),
            DuplicateFile(Path("e"), 50),
            size=50,
        )
        s = selection_summary([g1, g2])
        self.assertEqual(s.groups, 2)
        self.assertEqual(s.extra_copies, 3)
        self.assertEqual(s.reclaimable_bytes, 250)
        self.assertEqual(s.selected_files, 1)
        self.assertEqual(s.selected_bytes, 100)
        self.assertEqual(s.groups_without_kept_copy, 0)

    def test_every_copy_selected(self):
        g = _group(
            DuplicateFile(Path("a"), 100, is_original=True, selected=True),
            DuplicateFile(Path("b"), 100, selected=True),
        )
        self.assertEqual(selection_summary([g]).groups_without_kept_copy, 1)

    def test_hard_links_counted_once_and_not_while_kept(self):
        g = _group(
            DuplicateFile(Path("a"), 100, is_original=True, device=1, inode=7),
            DuplicateFile(Path("b"), 100, selected=True, device=1, inode=7),
            DuplicateFile(Path("c"), 100, selected=True, device=1, inode=9),
            DuplicateFile(Path("d"), 100, selected=True, device=1, inode=9),
        )
        s = selection_summary([g])
        self.assertEqual(s.selected_files, 3)
        # b shares the kept original's inode; c and d share one inode.
        self.assertEqual(s.selected_bytes, 100)

    def test_unknown_inode_counts_each_file(self):
        g = _group(
            DuplicateFile(Path("a"), 100, is_original=True),
            DuplicateFile(Path("b"), 100, selected=True, device=1, inode=0),
            DuplicateFile(Path("c"), 100, selected=True),
        )
        self.assertEqual(selection_summary([g]).selected_bytes, 200)

    def test_empty(self):
        self.assertEqual(tuple(selection_summary([])), (0, 0, 0, 0, 0, 0))


class FormatLogLineTests(unittest.TestCase):
    def test_format_matches_previous_output(self):
        self.assertEqual(
            format_log_line(("20:14:03", "WARN", "Skipped a.jpg")),
            "[20:14:03] [WARN ] Skipped a.jpg\n",
        )


class UndoLabelTests(unittest.TestCase):
    def _result(self, moves: int, **kw) -> ExecutionResult:
        r = ExecutionResult(
            plan_target_dir=Path("root"),
            timestamp=datetime(2026, 10, 20, 20, 14),
            **kw,
        )
        r.successful_moves = [MoveRecord(Path(f"s{i}"), Path(f"d{i}")) for i in range(moves)]
        return r

    def test_nothing_to_undo(self):
        self.assertEqual(undo_label(None), "Undo")
        self.assertEqual(undo_label(self._result(0)), "Undo")
        self.assertEqual(undo_label(self._result(2, undo_supported=False)), "Undo")

    def test_label(self):
        r = self._result(6, description="Duplicates moved")
        self.assertEqual(undo_label(r), "Undo: Duplicates moved · 6 files · 20:14")
        self.assertEqual(undo_label(self._result(1)), "Undo: Last move · 1 file · 20:14")


if __name__ == "__main__":
    unittest.main()
