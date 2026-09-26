"""
Data models for File Suite.

Defines dataclasses for filesystem operation plans, execution tracking,
undo records, and duplicate detection results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class OperationType(str, Enum):
    MOVE = "move"
    TRASH = "trash"


class OperationStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class OperationItem:
    """Represents a single planned filesystem mutation."""

    source: Path
    destination: Path | None
    action: OperationType = OperationType.MOVE
    size: int = 0
    category: str = "Misc"
    status: OperationStatus = OperationStatus.PENDING
    is_collision: bool = False
    original_name: str = ""
    final_name: str = ""
    skip_reason: str | None = None
    error_message: str | None = None

    def __post_init__(self):
        if not self.original_name:
            self.original_name = self.source.name
        if not self.final_name:
            self.final_name = self.destination.name if self.destination else self.original_name


@dataclass
class OperationPlan:
    """Pre-calculated plan of filesystem operations before any mutation."""

    target_dir: Path
    items: list[OperationItem] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def executable_items(self) -> list[OperationItem]:
        """Items that are scheduled to be executed (not skipped)."""
        return [item for item in self.items if item.status == OperationStatus.PENDING]

    @property
    def affected_count(self) -> int:
        return len(self.executable_items)

    @property
    def total_size_bytes(self) -> int:
        return sum(item.size for item in self.executable_items)

    @property
    def collision_count(self) -> int:
        return sum(1 for item in self.executable_items if item.is_collision)

    @property
    def skipped_count(self) -> int:
        return sum(1 for item in self.items if item.status == OperationStatus.SKIPPED)


@dataclass
class MoveRecord:
    """Record of an individual successful file move for undo support."""

    source: Path
    destination: Path
    timestamp: datetime = field(default_factory=datetime.now)
    size: int = 0


@dataclass
class ExecutionResult:
    """Result of executing an OperationPlan, with undo tracking."""

    plan_target_dir: Path
    successful_moves: list[MoveRecord] = field(default_factory=list)
    failed_moves: list[tuple[Path, Path | None, str]] = field(default_factory=list)
    description: str = ""
    undo_supported: bool = True
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def success_count(self) -> int:
        return len(self.successful_moves)

    @property
    def failure_count(self) -> int:
        return len(self.failed_moves)

    @property
    def is_partial_failure(self) -> bool:
        return self.success_count > 0 and self.failure_count > 0


@dataclass
class DuplicateFile:
    """Represents a file inside a duplicate group."""

    path: Path
    size: int
    is_original: bool = False
    selected: bool = False  # Checked for action (e.g. move to Duplicates or Trash)


@dataclass
class DuplicateGroup:
    """Group of byte-identical files matching the same SHA-256 hash."""

    group_id: str
    sha256: str
    size: int
    files: list[DuplicateFile] = field(default_factory=list)

    @property
    def original(self) -> DuplicateFile | None:
        for f in self.files:
            if f.is_original:
                return f
        return self.files[0] if self.files else None

    @property
    def duplicates(self) -> list[DuplicateFile]:
        return [f for f in self.files if not f.is_original]

    @property
    def selected_duplicates(self) -> list[DuplicateFile]:
        return [f for f in self.files if not f.is_original and f.selected]

    @property
    def reclaimable_bytes(self) -> int:
        """Space that would be freed if all non-original duplicates were removed."""
        return max(0, len(self.files) - 1) * self.size


@dataclass
class ScanProgress:
    """Progress feedback emitted during background operations."""

    step: str = ""
    current: int = 0
    total: int = 0
    current_file: str = ""
    files_discovered: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    groups_found: int = 0
    message: str = ""
