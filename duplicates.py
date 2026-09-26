"""
Duplicate detection engine with size pre-filtering, chunked SHA-256 hashing,
symlink protection, cooperative cancellation, and structured result grouping.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from pathlib import Path

from core import group_by_size
from models import DuplicateFile, DuplicateGroup, ScanProgress


def calculate_sha256(
    file_path: Path,
    chunk_size: int = 64 * 1024,
    cancel_event: threading.Event | None = None,
) -> str | None:
    """
    Calculate the SHA-256 hash of a file in 64 KB memory-friendly chunks.

    Returns the hexadecimal digest, or None if cancelled or unreadable.
    """
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as fh:
            while chunk := fh.read(chunk_size):
                if cancel_event is not None and cancel_event.is_set():
                    return None
                sha256.update(chunk)
        return sha256.hexdigest()
    except OSError:
        return None


def scan_duplicates(
    target_dir: Path,
    cancel_event: threading.Event | None = None,
    on_progress: Callable[[ScanProgress], None] | None = None,
) -> list[DuplicateGroup]:
    """
    Scan target_dir for byte-identical duplicate files.

    Pipeline:
      1. Discovery: List direct non-hidden, non-symlink files.
      2. Size grouping: Filter out files with unique sizes (cannot be duplicates).
      3. Chunked hashing: Compute SHA-256 only for size-colliding candidates.
      4. Grouping: Form structured DuplicateGroup objects.

    Safety:
      - Strictly ignores symlinks and subdirectories.
      - Never loads full files into memory.
      - Checks cancel_event cooperatively between files and chunks.
    """
    if not target_dir.exists() or not target_dir.is_dir():
        return []

    progress = ScanProgress(step="Discovering files")
    if on_progress:
        on_progress(progress)

    try:
        raw_entries = list(target_dir.iterdir())
    except OSError:
        return []

    files: list[Path] = []
    skipped_count = 0

    for item in raw_entries:
        if cancel_event is not None and cancel_event.is_set():
            return []

        # Safety: skip symlinks, directories, and hidden files
        if item.is_symlink() or item.is_dir() or item.name.startswith("."):
            skipped_count += 1
            continue

        if item.is_file():
            files.append(item)
        else:
            skipped_count += 1

    progress.files_discovered = len(files)
    progress.files_skipped = skipped_count
    progress.step = "Analyzing file sizes"
    if on_progress:
        on_progress(progress)

    if cancel_event is not None and cancel_event.is_set():
        return []

    # Stage 1: Group by file size. Candidates must share size with >= 1 other file.
    size_groups = group_by_size(files)
    candidate_files: list[Path] = [
        f for group in size_groups.values() if len(group) >= 2 for f in group
    ]

    total_candidates = len(candidate_files)
    progress.total = total_candidates
    progress.step = "Hashing candidate files"
    if on_progress:
        on_progress(progress)

    if not candidate_files:
        progress.step = "Complete"
        if on_progress:
            on_progress(progress)
        return []

    # Stage 2: Hash candidates and build duplicate groups
    hash_map: dict[str, list[Path]] = {}

    for idx, file_path in enumerate(candidate_files, 1):
        if cancel_event is not None and cancel_event.is_set():
            return []

        progress.current = idx
        progress.current_file = file_path.name
        progress.files_processed = idx

        file_hash = calculate_sha256(file_path, cancel_event=cancel_event)
        if file_hash is None:
            # File unreadable or cancelled
            continue

        hash_map.setdefault(file_hash, []).append(file_path)

        # Count groups found so far
        progress.groups_found = sum(1 for flist in hash_map.values() if len(flist) >= 2)
        if on_progress:
            on_progress(progress)

    # Form structured DuplicateGroup objects
    groups: list[DuplicateGroup] = []
    group_counter = 1

    for file_hash, matching_paths in hash_map.items():
        if len(matching_paths) >= 2:
            try:
                single_size = matching_paths[0].stat().st_size
            except OSError:
                single_size = 0

            # First occurrence is the original (not selected for removal)
            # Subsequent occurrences are duplicates (selected for action by default)
            dup_files: list[DuplicateFile] = []
            for i, p in enumerate(matching_paths):
                try:
                    f_size = p.stat().st_size
                except OSError:
                    f_size = single_size

                dup_files.append(
                    DuplicateFile(
                        path=p,
                        size=f_size,
                        is_original=(i == 0),
                        selected=(i > 0),
                    )
                )

            groups.append(
                DuplicateGroup(
                    group_id=f"group-{group_counter}",
                    sha256=file_hash,
                    size=single_size,
                    files=dup_files,
                )
            )
            group_counter += 1

    progress.step = "Complete"
    if on_progress:
        on_progress(progress)

    return groups
