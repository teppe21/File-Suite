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

        # Ensure destination directory exists
        dest_dir = dest.parent
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            item.status = OperationStatus.FAILED
            item.error_message = f"Could not create destination directory '{dest_dir.name}': {exc}"
            result.failed_moves.append((src, dest, item.error_message))
            continue

        # TOCTOU check 5: Avoid overwriting existing destination
        actual_dest = dest
        if actual_dest.exists() or actual_dest in allocated_destinations:
            actual_dest = build_collision_safe_path(dest_dir, src.name)
            while actual_dest in allocated_destinations:
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
      - Never overwrites an existing file at original source location.
      - Handles partial failure transparently.

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

    # Process in reverse order of original execution
    for record in reversed(result.successful_moves):
        current_loc = record.destination
        original_loc = record.source

        if not current_loc.exists():
            failed_count += 1
            errors.append(f"Cannot restore '{current_loc.name}': file no longer exists at destination.")
            continue

        if current_loc.is_symlink():
            failed_count += 1
            errors.append(f"Cannot restore '{current_loc.name}': path is a symbolic link.")
            continue

        # Prevent overwriting if original location now has another file
        target_restore = original_loc
        if target_restore.exists():
            target_restore = build_collision_safe_path(original_loc.parent, original_loc.name)
            errors.append(
                f"Original location for '{original_loc.name}' was occupied; restored as '{target_restore.name}'."
            )

        try:
            target_restore.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(current_loc), str(target_restore))
            undone_count += 1
        except OSError as exc:
            failed_count += 1
            errors.append(f"Failed to restore '{current_loc.name}': {exc}")

    # Clear undone items from record to prevent double-undo
    result.successful_moves.clear()
    return undone_count, failed_count, errors


def move_to_system_trash(file_path: Path) -> tuple[bool, str | None]:
    """
    Move a file to the FreeDesktop system trash (~/.local/share/Trash).

    Creates compliant .trashinfo metadata.
    Returns (success: bool, error_message: str | None).
    """
    if not file_path.exists():
        return False, f"File does not exist: {file_path.name}"

    if file_path.is_symlink():
        return False, f"Refusing to trash symbolic link for safety: {file_path.name}"

    trash_files_dir = Path.home() / ".local/share/Trash/files"
    trash_info_dir = Path.home() / ".local/share/Trash/info"

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

    try:
        with open(info_path, "w", encoding="utf-8") as fh:
            fh.write(info_content)
        shutil.move(str(file_path), str(dest_path))
        return True, None
    except OSError as exc:
        return False, f"Failed to trash '{file_path.name}': {exc}"


def build_duplicate_move_plan(
    duplicates: list[Path],
    target_dir: Path,
    subfolder_name: str = "Duplicates",
) -> tuple[bool, OperationPlan, str | None]:
    """
    Build an OperationPlan for moving selected duplicate files into a subfolder.

    Allows duplicate isolation to be previewed and undone using the unified engine.
    """
    dup_folder = target_dir / subfolder_name
    plan = OperationPlan(target_dir=target_dir)

    for f in duplicates:
        if not f.exists() or f.is_symlink() or not f.is_file():
            continue

        try:
            size = f.stat().st_size
        except OSError:
            size = 0

        final_dest = build_collision_safe_path(dup_folder, f.name)
        is_collision = (dup_folder / f.name).exists()

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
