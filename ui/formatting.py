"""
Pure text helpers for the UI. No tkinter import, so they are unit-tested
without a display.
"""

from __future__ import annotations

from typing import NamedTuple

from models import DuplicateGroup, ExecutionResult, OperationPlan
from platform_utils import IS_MACOS

# macOS spellings that are not just "⌘" plus the key. ⌘M is Minimize in every Mac
# app's Window menu, which Tk runs in addition to a binding, so Move uses ⇧⌘M.
_MAC_SHORTCUTS = {"M": "⇧⌘M", "Enter": "⌘↩", "Delete": "⌘⌫"}


def shortcut(key: str) -> str:
    """
    A shortcut as shown in tooltips: ``shortcut("O")`` -> ``"Ctrl+O"``,
    ``shortcut("Enter")`` -> ``"Ctrl+Enter"``, and ``shortcut("Delete")`` -> the
    bare ``"Delete"``. On macOS the command key replaces Ctrl: ``"⌘O"``, ``"⌘↩"``,
    and ``"⌘⌫"`` for the trash key (Mac keyboards send BackSpace for "delete").
    ``"M"`` (move) becomes ``"⇧⌘M"``.
    """
    if IS_MACOS:
        return _MAC_SHORTCUTS.get(key, "⌘" + key)
    return key if key == "Delete" else f"Ctrl+{key}"


def format_size(num_bytes: int) -> str:
    """Human-readable size with binary units: ``0 B``, ``1.0 KB``, ``1.5 MB``."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    value = num_bytes / 1024
    for unit in ("KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def plural(count: int, word: str, plural_word: str | None = None) -> str:
    """``plural(1, "file")`` -> ``"1 file"``; ``plural(2, "copy", "copies")`` -> ``"2 copies"``."""
    return f"{count} {word if count == 1 else (plural_word or word + 's')}"


def extension_preview(extensions: set[str], limit: int = 4) -> str:
    """``{".jpg", ".png", ...}`` -> ``"gif, jpg, png, webp +7"`` (sorted, without dots)."""
    names = sorted(ext.lstrip(".") for ext in extensions)
    shown = ", ".join(names[:limit])
    extra = len(names) - limit
    return f"{shown} +{extra}" if extra > 0 else shown


def truncate_middle(text: str, max_chars: int) -> str:
    """Shorten ``text`` to ``max_chars`` by replacing its middle with an ellipsis."""
    if len(text) <= max_chars:
        return text
    keep = max_chars - 1
    head = (keep + 1) // 2
    tail = keep - head
    return text[:head] + "…" + (text[-tail:] if tail else "")


def category_counts(plan: OperationPlan) -> list[tuple[str, int]]:
    """Files per destination category in a plan, largest first, then by name."""
    counts: dict[str, int] = {}
    for item in plan.executable_items:
        counts[item.category] = counts.get(item.category, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))


class SelectionSummary(NamedTuple):
    groups: int
    extra_copies: int
    reclaimable_bytes: int
    selected_files: int
    selected_bytes: int
    groups_without_kept_copy: int


def selection_summary(groups: list[DuplicateGroup]) -> SelectionSummary:
    """
    Totals for the duplicate view. ``selected_bytes`` counts a hard-linked
    inode once, and not at all while an unselected copy still holds it,
    matching how ``DuplicateGroup.reclaimable_bytes`` counts space.
    """
    extra = reclaimable = selected_files = selected_bytes = unkept = 0
    for g in groups:
        extra += len(g.duplicates)
        reclaimable += g.reclaimable_bytes
        selected = [f for f in g.files if f.selected]
        selected_files += len(selected)
        if g.files and len(selected) == len(g.files):
            unkept += 1
        kept_inodes = {
            (f.device, f.inode)
            for f in g.files
            if not f.selected and f.device is not None and f.inode
        }
        freed: set[tuple[int, int]] = set()
        untracked = 0
        for f in selected:
            if f.device is not None and f.inode:
                if (f.device, f.inode) not in kept_inodes:
                    freed.add((f.device, f.inode))
            else:
                untracked += 1
        selected_bytes += (len(freed) + untracked) * g.size
    return SelectionSummary(len(groups), extra, reclaimable, selected_files, selected_bytes, unkept)


def format_log_line(entry: tuple[str, str, str]) -> str:
    """A ``(time, level, message)`` log entry in the console/log line format."""
    timestamp, level, message = entry
    return f"[{timestamp}] [{level:5}] {message}\n"


def undo_label(result: ExecutionResult | None) -> str:
    """Text for the global Undo button, e.g. ``"Undo: Organize · 17 files · 20:14"``."""
    if result is None or not result.undo_supported or result.success_count == 0:
        return "Undo"
    what = result.description or "Last move"
    return f"Undo: {what} · {plural(result.success_count, 'file')} · {result.timestamp:%H:%M}"
