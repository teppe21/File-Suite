"""
Filesystem operations, plan building, execution, and undo engine.

Separates all filesystem mutations from UI code, ensuring deterministic
behavior, TOCTOU safety, symlink rejection, and reliable undo capability.
"""

from __future__ import annotations

import datetime
import shutil
import urllib.parse
from collections.abc import Callable
from pathlib import Path

from core import (
    build_collision_safe_path,
    classify_extension,
    resolve_destination,
)
from models import (
    ExecutionResult,
    MoveRecord,
    OperationItem,
    OperationPlan,
    OperationStatus,
    OperationType,
)


def build_organization_plan(
    target_dir: Path,
    selected_extensions: set[str],
    custom_folder_name: str | None = None,
) -> tuple[bool, OperationPlan, str | None]:
    """
    Scan target_dir and build a dry-run OperationPlan without modifying the filesystem.

    Enforces safety invariants:
      - Non-recursive: only direct children of target_dir are considered.
      - Hidden files (starting with '.') are skipped.
      - Subdirectories are skipped.
      - Symbolic links (symlink files or symlink dirs) are strictly skipped.
      - Path traversal is prevented through resolve_destination.
      - Collisions are detected and collision-safe destination paths pre-computed.

    Returns:
      (success: bool, plan: OperationPlan, error_message: str | None)
    """
    if not target_dir.exists() or not target_dir.is_dir():
        return False, OperationPlan(target_dir=target_dir), "Target directory does not exist or is not a directory."

    validated_custom_dest: Path | None = None
    if custom_folder_name and custom_folder_name.strip():
        ok, res = resolve_destination(target_dir, custom_folder_name.strip())
        if not ok:
            return False, OperationPlan(target_dir=target_dir), str(res)
        validated_custom_dest = res  # type: ignore[assignment]

    plan = OperationPlan(target_dir=target_dir)

    try:
        entries = list(target_dir.iterdir())
    except OSError as exc:
        return False, plan, f"Failed to list directory contents: {exc}"

    for item in sorted(entries, key=lambda p: p.name.lower()):
        # Safety rule: strictly skip symbolic links to avoid external mutations
        if item.is_symlink():
            plan.items.append(
                OperationItem(
                    source=item,
                    destination=None,
                    status=OperationStatus.SKIPPED,
                    skip_reason="Symbolic link skipped for safety",
                )
            )
            continue

        # Safety rule: skip subdirectories (non-recursive guarantee)
        if item.is_dir():
            plan.items.append(
                OperationItem(
                    source=item,
                    destination=None,
                    status=OperationStatus.SKIPPED,
                    skip_reason="Directory skipped (non-recursive)",
                )
            )
            continue

        # Safety rule: skip hidden files
        if item.name.startswith("."):
            plan.items.append(
                OperationItem(
                    source=item,
                    destination=None,
                    status=OperationStatus.SKIPPED,
                    skip_reason="Hidden file skipped",
                )
            )
            continue

        if not item.is_file():
            plan.items.append(
                OperationItem(
                    source=item,
                    destination=None,
                    status=OperationStatus.SKIPPED,
                    skip_reason="Special/non-regular file skipped",
                )
            )
            continue

        # Extension extraction (single and compound e.g. .tar.gz)
        try:
            ext = item.suffix.lower()
            full_ext = "".join(item.suffixes).lower()
            size = item.stat().st_size
        except OSError as exc:
            plan.items.append(
                OperationItem(
                    source=item,
                    destination=None,
                    status=OperationStatus.SKIPPED,
                    skip_reason=f"Inaccessible file: {exc}",
                )
            )
            continue

        if ext not in selected_extensions and full_ext not in selected_extensions:
            plan.items.append(
                OperationItem(
                    source=item,
                    destination=None,
                    size=size,
                    status=OperationStatus.SKIPPED,
                    skip_reason="Extension not selected",
                )
            )
            continue

        # Determine target folder
        if validated_custom_dest is not None:
            dest_dir = validated_custom_dest
            cat_label = validated_custom_dest.name
        else:
            cat_label = classify_extension(ext, full_ext) or "Misc"
            dest_dir = target_dir / cat_label

        # Collision detection against existing files or previously planned items in this plan
        candidate_dest = dest_dir / item.name
        is_collision = candidate_dest.exists()

        final_dest = (
            build_collision_safe_path(dest_dir, item.name)
            if is_collision
            else candidate_dest
        )

        plan.items.append(
            OperationItem(
                source=item,
                destination=final_dest,
                action=OperationType.MOVE,
                size=size,
                category=cat_label,
                status=OperationStatus.PENDING,
                is_collision=is_collision,
                original_name=item.name,
                final_name=final_dest.name,
            )
        )

    return True, plan, None


def _validate_destination_containment(dest: Path, target_root: Path) -> tuple[bool, str | None]:
    """
    Validate that destination directory and path strictly resolve within target_root,
    rejecting any symbolic link path components to prevent directory traversal attacks.
    """
    try:
        resolved_root = target_root.resolve(strict=True)
    except OSError as exc:
        return False, f"Target root directory is inaccessible: {exc}"

    # Verify no parent directory component between target_root and dest is a symlink
    curr = dest.parent
    while curr != target_root and curr != curr.parent:
        if curr.is_symlink():
            return False, f"Destination path component '{curr.name}' is a symbolic link"
        curr = curr.parent

    dest_dir = dest.parent
    if dest_dir.exists():
        if dest_dir.is_symlink():
            return False, f"Destination directory '{dest_dir.name}' is a symbolic link"
        try:
            resolved_dest_dir = dest_dir.resolve(strict=True)
            if not resolved_dest_dir.is_relative_to(resolved_root):
                return False, "Destination directory escapes the target root directory"
        except OSError as exc:
            return False, f"Failed to resolve destination directory: {exc}"

    if dest.is_symlink():
        return False, f"Destination path '{dest.name}' is already an existing symbolic link"

    return True, None


def execute_operation_plan(
    plan: OperationPlan,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> ExecutionResult:
    """
    Execute all pending items in an OperationPlan with TOCTOU checks.

    Re-checks immediately before moving:
      - Source still exists.
      - Source is not a symlink.
      - Source is a regular file.
      - Destination parent containment inside target_dir (no symlink traversal).
      - Destination directory exists or is safely created.
      - Destination does not overwrite existing file (collision fallback applied).

    Records successful moves for full undo support.
    """
    result = ExecutionResult(
        plan_target_dir=plan.target_dir,
        description=f"Organized {plan.affected_count} file(s)",
        undo_supported=True,
    )

    items_to_exec = plan.executable_items
    total = len(items_to_exec)

    # Track destinations used during this execution to prevent collisions within batch
    allocated_destinations: set[Path] = set()

    for idx, item in enumerate(items_to_exec, 1):
        if on_progress:
            on_progress(idx, total, item.original_name)

        src = item.source
        dest = item.destination

        if dest is None:
            item.status = OperationStatus.FAILED
            item.error_message = "No destination specified"
            result.failed_moves.append((src, None, item.error_message))
            continue

        # TOCTOU check 1: Source file still exists
        if not src.exists():
            item.status = OperationStatus.FAILED
            item.error_message = "Source file no longer exists (removed or renamed externally)"
            result.failed_moves.append((src, dest, item.error_message))
            continue

        # TOCTOU check 2: Symlink safety
        if src.is_symlink():
            item.status = OperationStatus.FAILED
            item.error_message = "Source was replaced with a symbolic link before execution"
            result.failed_moves.append((src, dest, item.error_message))
            continue

        # TOCTOU check 3: Regular file
        if not src.is_file():
            item.status = OperationStatus.FAILED
            item.error_message = "Source is no longer a regular file"
            result.failed_moves.append((src, dest, item.error_message))
            continue

        # TOCTOU check 4: Source and destination must not be the exact same path
        try:
            if src.resolve() == dest.resolve():
                item.status = OperationStatus.SKIPPED
                item.skip_reason = "Source and destination are the same file"
                continue
        except OSError:
            pass

        # TOCTOU check 5: Destination containment and symlink protection
        ok_dest, dest_err = _validate_destination_containment(dest, plan.target_dir)
        if not ok_dest:
            item.status = OperationStatus.FAILED
            item.error_message = dest_err or "Destination validation failed"
            result.failed_moves.append((src, dest, item.error_message))
            continue

        # Ensure destination directory exists safely
        dest_dir = dest.parent
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            item.status = OperationStatus.FAILED
            item.error_message = f"Could not create destination directory '{dest_dir.name}': {exc}"
            result.failed_moves.append((src, dest, item.error_message))
            continue

        # Post-mkdir containment verification
        try:
            resolved_dest_dir = dest_dir.resolve(strict=True)
            if not resolved_dest_dir.is_relative_to(plan.target_dir.resolve(strict=True)):
                item.status = OperationStatus.FAILED
                item.error_message = "Destination directory escapes the target root directory"
                result.failed_moves.append((src, dest, item.error_message))
                continue
        except OSError as exc:
            item.status = OperationStatus.FAILED
            item.error_message = f"Destination directory resolution failed: {exc}"
            result.failed_moves.append((src, dest, item.error_message))
            continue

        # TOCTOU check 6: Avoid overwriting existing destination or symlink
        actual_dest = dest
        if actual_dest.exists() or actual_dest.is_symlink() or actual_dest in allocated_destinations:
            actual_dest = build_collision_safe_path(dest_dir, src.name)
            while (
                actual_dest in allocated_destinations
                or actual_dest.exists()
                or actual_dest.is_symlink()
            ):
                actual_dest = build_collision_safe_path(dest_dir, actual_dest.name)

        allocated_destinations.add(actual_dest)

        try:
            shutil.move(str(src), str(actual_dest))
            item.status = OperationStatus.APPLIED
            item.destination = actual_dest
            item.final_name = actual_dest.name
            result.successful_moves.append(
                MoveRecord(source=src, destination=actual_dest, size=item.size)
            )
        except OSError as exc:
            item.status = OperationStatus.FAILED
            item.error_message = f"Move failed: {exc}"
            result.failed_moves.append((src, actual_dest, str(exc)))

    return result


def undo_last_operation(result: ExecutionResult) -> tuple[int, int, list[str]]:
    """
    Reverse the successful moves recorded in an ExecutionResult.

    Reverses: destination -> source.
    Safety checks:
      - Validates destination still exists, is a regular file, and is not a symlink.
      - Re-validates original source parent containment inside plan_target_dir.
      - Never overwrites an existing file or symlink at the original location (collision suffix applied).
      - Handles partial failure transparently and retains only un-restored records for retry.

    Returns:
      (undone_count: int, failed_count: int, error_messages: list[str])
    """
    if not result.undo_supported:
        return 0, 0, ["Undo is not supported for this operation (e.g. system trash)."]

    if not result.successful_moves:
        return 0, 0, ["No operations to undo."]

    undone_count = 0
    failed_count = 0
    errors: list[str] = []
    retained_moves: list[MoveRecord] = []

    try:
        resolved_root = result.plan_target_dir.resolve(strict=True)
    except OSError as exc:
        return 0, len(result.successful_moves), [f"Target root directory inaccessible: {exc}"]

    # Process in reverse order of original execution
    for record in reversed(list(result.successful_moves)):
        current_loc = record.destination
        original_loc = record.source

        if not current_loc.exists():
            failed_count += 1
            errors.append(f"Cannot restore '{current_loc.name}': file no longer exists at destination.")
            retained_moves.append(record)
            continue

        if current_loc.is_symlink():
            failed_count += 1
            errors.append(f"Cannot restore '{current_loc.name}': destination path is a symbolic link.")
            retained_moves.append(record)
            continue

        if not current_loc.is_file():
            failed_count += 1
            errors.append(f"Cannot restore '{current_loc.name}': destination path is not a regular file.")
            retained_moves.append(record)
            continue

        orig_parent = original_loc.parent
        if orig_parent.is_symlink():
            failed_count += 1
            errors.append(f"Cannot restore '{current_loc.name}': original folder is a symbolic link.")
            retained_moves.append(record)
            continue

        try:
            resolved_orig_parent = orig_parent.resolve(strict=False)
            if not resolved_orig_parent.is_relative_to(resolved_root):
                failed_count += 1
                errors.append(f"Cannot restore '{current_loc.name}': original location escapes root directory.")
                retained_moves.append(record)
                continue
        except OSError as exc:
            failed_count += 1
            errors.append(f"Cannot restore '{current_loc.name}': original folder inaccessible: {exc}")
            retained_moves.append(record)
            continue

        # Prevent overwriting if original location now has another file or symlink
        target_restore = original_loc
        if target_restore.exists() or target_restore.is_symlink():
            target_restore = build_collision_safe_path(orig_parent, original_loc.name)
            errors.append(
                f"Original location for '{original_loc.name}' was occupied; restored as '{target_restore.name}'."
            )

        try:
            target_restore.parent.mkdir(parents=True, exist_ok=True)
            resolved_restore_parent = target_restore.parent.resolve(strict=True)
            if not resolved_restore_parent.is_relative_to(resolved_root):
                failed_count += 1
                errors.append(f"Cannot restore '{current_loc.name}': restored parent directory escapes root.")
                retained_moves.append(record)
                continue
            shutil.move(str(current_loc), str(target_restore))
            undone_count += 1
        except OSError as exc:
            failed_count += 1
            errors.append(f"Failed to restore '{current_loc.name}': {exc}")
            retained_moves.append(record)

    # Retain only failed moves in result so subsequent retries only process un-restored items
    result.successful_moves = list(reversed(retained_moves))
    return undone_count, failed_count, errors


def move_to_system_trash(
    file_path: Path,
    trash_dir: Path | None = None,
) -> tuple[bool, str | None]:
    """
    Move a file to the FreeDesktop system trash (~/.local/share/Trash).

    Creates compliant .trashinfo metadata. Cleans up orphaned metadata
    if moving the file fails.
    Returns (success: bool, error_message: str | None).
    """
    if not file_path.exists():
        return False, f"File does not exist: {file_path.name}"

    if file_path.is_symlink():
        return False, f"Refusing to trash symbolic link for safety: {file_path.name}"

    if not file_path.is_file():
        return False, f"Path is not a regular file: {file_path.name}"

    base_trash = trash_dir if trash_dir is not None else Path.home() / ".local/share/Trash"
    trash_files_dir = base_trash / "files"
    trash_info_dir = base_trash / "info"

    try:
        trash_files_dir.mkdir(parents=True, exist_ok=True)
        trash_info_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"Could not access trash directory: {exc}"

    dest_path = build_collision_safe_path(trash_files_dir, file_path.name)
    info_path = trash_info_dir / f"{dest_path.name}.trashinfo"

    deletion_date = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    escaped_path = urllib.parse.quote(str(file_path.resolve()))
    info_content = (
        f"[Trash Info]\nPath={escaped_path}\nDeletionDate={deletion_date}\n"
    )

    info_created = False
    try:
        with open(info_path, "w", encoding="utf-8") as fh:
            fh.write(info_content)
        info_created = True

        shutil.move(str(file_path), str(dest_path))
        return True, None
    except OSError as exc:
        if info_created:
            try:
                info_path.unlink(missing_ok=True)
            except OSError:
                pass
        return False, f"Failed to trash '{file_path.name}': {exc}"


def build_duplicate_move_plan(
    duplicates: list[Path],
    target_dir: Path,
    subfolder_name: str = "Duplicates",
) -> tuple[bool, OperationPlan, str | None]:
    """
    Build an OperationPlan for moving selected duplicate files into a subfolder.

    Enforces safety invariants:
      - Validates destination subfolder name and ensures it does not escape target_dir.
      - Enforces source root containment within target_dir.
      - Strictly ignores symbolic links and non-regular files.
      - Rejects sources that are already located inside the duplicate destination folder.
      - Tracks allocated destinations to avoid intra-batch collisions.

    Returns:
      (success: bool, plan: OperationPlan, error_message: str | None)
    """
    if not target_dir.exists() or not target_dir.is_dir():
        return False, OperationPlan(target_dir=target_dir), "Target directory does not exist or is not a directory."

    ok, res = resolve_destination(target_dir, subfolder_name)
    if not ok:
        return False, OperationPlan(target_dir=target_dir), str(res)

    dup_folder: Path = res  # type: ignore[assignment]

    try:
        target_dir_resolved = target_dir.resolve(strict=True)
    except OSError as exc:
        return False, OperationPlan(target_dir=target_dir), f"Target directory is inaccessible: {exc}"

    dup_folder_resolved = dup_folder.resolve(strict=False)

    plan = OperationPlan(target_dir=target_dir)
    planned_destinations: set[Path] = set()

    for f in duplicates:
        if not f.exists() or f.is_symlink() or not f.is_file():
            continue

        try:
            f_resolved = f.resolve(strict=True)
            # Enforce source containment inside target_dir
            if not f_resolved.is_relative_to(target_dir_resolved):
                continue
            # Reject sources already inside the duplicate destination folder
            if f_resolved.is_relative_to(dup_folder_resolved):
                continue
            size = f.stat().st_size
        except OSError:
            continue

        candidate_dest = dup_folder / f.name
        is_collision = candidate_dest.exists() or candidate_dest in planned_destinations

        final_dest = (
            build_collision_safe_path(dup_folder, f.name)
            if is_collision
            else candidate_dest
        )
        while (
            final_dest in planned_destinations
            or final_dest.exists()
            or final_dest.is_symlink()
        ):
            final_dest = build_collision_safe_path(dup_folder, final_dest.name)

        planned_destinations.add(final_dest)

        plan.items.append(
            OperationItem(
                source=f,
                destination=final_dest,
                action=OperationType.MOVE,
                size=size,
                category=subfolder_name,
                status=OperationStatus.PENDING,
                is_collision=is_collision,
                original_name=f.name,
                final_name=final_dest.name,
            )
        )

    return True, plan, None
