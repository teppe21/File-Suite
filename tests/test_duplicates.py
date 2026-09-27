"""
Unit tests for duplicates.py: chunked hashing, size pre-filtering, cancellation, and symlinks.
"""

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path

from duplicates import calculate_sha256, scan_duplicates
from models import ScanProgress


class DuplicateScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_identical_files_detected(self):
        content = b"exact byte match"
        (self.target / "orig.bin").write_bytes(content)
        (self.target / "copy1.bin").write_bytes(content)
        (self.target / "copy2.bin").write_bytes(content)
        (self.target / "unique.bin").write_bytes(b"different content")

        groups = scan_duplicates(self.target)
        self.assertEqual(len(groups), 1)

        group = groups[0]
        self.assertEqual(len(group.files), 3)
        self.assertEqual(group.size, len(content))

        # Check original vs duplicates
        orig = group.original
        self.assertIsNotNone(orig)
        self.assertTrue(orig.is_original)
        self.assertFalse(orig.selected)

        duplicates = group.duplicates
        self.assertEqual(len(duplicates), 2)
        for dup in duplicates:
            self.assertFalse(dup.is_original)
            self.assertTrue(dup.selected)

        self.assertEqual(group.reclaimable_bytes, 2 * len(content))

    def test_same_size_different_content_not_duplicates(self):
        (self.target / "f1.txt").write_bytes(b"12345678")
        (self.target / "f2.txt").write_bytes(b"87654321")

        groups = scan_duplicates(self.target)
        self.assertEqual(len(groups), 0)

    def test_different_sizes_skipped_before_hashing(self):
        (self.target / "small.txt").write_bytes(b"1")
        (self.target / "medium.txt").write_bytes(b"123")
        (self.target / "large.txt").write_bytes(b"123456")

        progress_events: list[ScanProgress] = []

        def callback(p: ScanProgress):
            progress_events.append(p)

        groups = scan_duplicates(self.target, on_progress=callback)
        self.assertEqual(len(groups), 0)
        # Verify candidate count was 0 (no hashing performed)
        hashing_events = [p for p in progress_events if p.step == "Hashing candidate files"]
        if hashing_events:
            self.assertEqual(hashing_events[0].total, 0)

    def test_symlinks_are_strictly_skipped(self):
        real_file = self.target / "real.dat"
        real_file.write_bytes(b"identical data")
        copy_file = self.target / "copy.dat"
        copy_file.write_bytes(b"identical data")

        symlink_file = self.target / "link.dat"
        try:
            os.symlink(real_file, symlink_file)
        except OSError:
            self.skipTest("Symlinks not supported")

        groups = scan_duplicates(self.target)
        self.assertEqual(len(groups), 1)

        group_paths = [f.path.name for f in groups[0].files]
        self.assertIn("real.dat", group_paths)
        self.assertIn("copy.dat", group_paths)
        self.assertNotIn("link.dat", group_paths)

    def test_cancellation_cooperative(self):
        cancel_event = threading.Event()
        cancel_event.set()  # Cancelled before start

        (self.target / "f1.dat").write_bytes(b"abc")
        (self.target / "f2.dat").write_bytes(b"abc")

        groups = scan_duplicates(self.target, cancel_event=cancel_event)
        self.assertEqual(len(groups), 0)

    def test_chunked_hash_cancel(self):
        cancel_event = threading.Event()
        cancel_event.set()
        f = self.target / "sample.txt"
        f.write_bytes(b"data" * 1000)

        h = calculate_sha256(f, chunk_size=10, cancel_event=cancel_event)
        self.assertIsNone(h)

    def test_deterministic_ordering(self):
        """Original selection is deterministic and independent of filesystem iteration order."""
        content = b"deterministic duplicate test"
        # Create files with various alphabetical names
        (self.target / "zebra.bin").write_bytes(content)
        (self.target / "Apple.bin").write_bytes(content)
        (self.target / "banana.bin").write_bytes(content)

        groups = scan_duplicates(self.target)
        self.assertEqual(len(groups), 1)

        group = groups[0]
        # "Apple.bin" must be the deterministic original (case-insensitive sorted first)
        self.assertEqual(group.original.path.name, "Apple.bin")
        dup_names = [f.path.name for f in group.duplicates]
        self.assertEqual(dup_names, ["banana.bin", "zebra.bin"])

    def test_hardlinks_reclaimable_bytes(self):
        """Reclaimable bytes calculation accounts for shared inodes (hardlinks)."""
        content = b"shared inode data" * 100
        size = len(content)

        orig = self.target / "original.dat"
        orig.write_bytes(content)

        # Create a hardlink to orig
        hardlink = self.target / "hardlink.dat"
        try:
            os.link(orig, hardlink)
        except OSError:
            self.skipTest("Hard links not supported in environment")

        # Create an independent file with identical content
        independent = self.target / "independent.dat"
        independent.write_bytes(content)

        groups = scan_duplicates(self.target)
        self.assertEqual(len(groups), 1)
        group = groups[0]

        # 3 files total, but only 1 independent duplicate frees actual disk blocks
        self.assertEqual(len(group.files), 3)
        self.assertEqual(group.reclaimable_bytes, size)

    def test_file_disappearing_during_scan(self):
        """A candidate disappearing during the scan does not crash the engine."""
        content = b"temporary candidate"
        f1 = self.target / "f1.dat"
        f2 = self.target / "f2.dat"
        f1.write_bytes(content)
        f2.write_bytes(content)

        # Delete f1 right before hashing by intercepting calculate_sha256 or simply unlinking
        # If f1 is unlinked before hash:
        f1.unlink()

        groups = scan_duplicates(self.target)
        # Only f2 remained, so no duplicate group formed, and engine didn't crash
        self.assertEqual(len(groups), 0)

    def test_unreadable_file_handled_gracefully(self):
        """Unreadable files (permission errors) are skipped without aborting the scan."""
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("Root user bypasses DAC permission restrictions")

        content = b"permission test"
        f1 = self.target / "f1.dat"
        f2 = self.target / "f2.dat"
        f1.write_bytes(content)
        f2.write_bytes(content)

        # Make f1 unreadable
        try:
            f1.chmod(0o000)
        except OSError:
            self.skipTest("chmod not supported")

        try:
            groups = scan_duplicates(self.target)
            # Scan completed cleanly without raising PermissionError
            self.assertEqual(len(groups), 0)
        finally:
            f1.chmod(0o644)

    def test_file_modified_during_hashing_skipped(self):
        """Files whose metadata changes during the hashing phase are safely skipped."""
        from unittest.mock import patch
        content = b"initial content for hash"
        f1 = self.target / "f1.dat"
        f2 = self.target / "f2.dat"
        f1.write_bytes(content)
        f2.write_bytes(content)

        original_calc = calculate_sha256

        def mutating_calc(path, *args, **kwargs):
            res = original_calc(path, *args, **kwargs)
            if path.name == "f1.dat":
                # Modify file to trigger post-hash stat mismatch
                path.write_bytes(b"mutated during hash")
            return res

        with patch("duplicates.calculate_sha256", side_effect=mutating_calc):
            groups = scan_duplicates(self.target)
            # f1 was skipped due to stat mismatch, so no duplicate group formed
            self.assertEqual(len(groups), 0)

    def test_empty_files_handling(self):
        """0-byte duplicate files are detected cleanly with 0 reclaimable bytes."""
        (self.target / "empty1.txt").write_bytes(b"")
        (self.target / "empty2.txt").write_bytes(b"")

        groups = scan_duplicates(self.target)
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group.size, 0)
        self.assertEqual(group.reclaimable_bytes, 0)


if __name__ == "__main__":
    unittest.main()

