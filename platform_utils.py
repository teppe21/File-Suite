"""
Platform-specific helpers for File Suite.

Every function keeps the existing Linux behavior on non-Windows systems and
adds the Windows equivalent behind ``IS_WINDOWS``. This module must not
import any other project module.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"

# Windows file attribute bits and reparse tags, defined here because the
# ``stat`` module only exposes them on Windows (and not all of them).
FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
IO_REPARSE_TAG_SYMLINK = 0xA000000C

_CLOUD_PLACEHOLDER_ATTRS = (
    FILE_ATTRIBUTE_OFFLINE
    | FILE_ATTRIBUTE_RECALL_ON_OPEN
    | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
)

# Reparse tags that redirect to another location. Other reparse points,
# such as OneDrive cloud folders, are ordinary folders for our purposes.
_LINK_REPARSE_TAGS = (
    IO_REPARSE_TAG_SYMLINK,
    IO_REPARSE_TAG_MOUNT_POINT,  # junctions and mounted volumes
)

_WINDOWS_FORBIDDEN_CHARS = frozenset('<>:"|?*/\\')

_WINDOWS_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"{dev}{n}" for dev in ("COM", "LPT") for n in "123456789¹²³"]
)


# ---------------------------------------------------------------------------
# File attributes
# ---------------------------------------------------------------------------

def windows_attrs(path: Path) -> int | None:
    """Return the Windows file attributes of ``path`` (not following links)."""
    if not IS_WINDOWS:
        return None
    try:
        return path.lstat().st_file_attributes
    except OSError:
        return None


def is_hidden(path: Path) -> bool:
    """
    Return True for dot-files and, on Windows, for files marked hidden or
    system. Unreadable attributes on Windows count as hidden.
    """
    if path.name.startswith("."):
        return True
    if not IS_WINDOWS:
        return False
    attrs = windows_attrs(path)
    if attrs is None:
        return True
    return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))


def is_link_like(path: Path) -> bool:
    """
    Return True if ``path`` is a symbolic link or, on Windows, a junction.

    On Windows the decision is made by reparse tag rather than by the
    reparse-point attribute, so OneDrive folders are not treated as links.
    A missing path is not a link; any other error counts as one.
    """
    if not IS_WINDOWS:
        return path.is_symlink()
    try:
        st = path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return stat.S_ISLNK(st.st_mode) or st.st_reparse_tag in _LINK_REPARSE_TAGS


def is_cloud_placeholder(path: Path) -> bool:
    """Return True for Windows cloud files whose content is not on disk."""
    attrs = windows_attrs(path)
    return attrs is not None and bool(attrs & _CLOUD_PLACEHOLDER_ATTRS)


# ---------------------------------------------------------------------------
# Folder names
# ---------------------------------------------------------------------------

def windows_name_problem(name: str) -> str | None:
    """Return why ``name`` is not a valid Windows folder name, or None."""
    # NTFS counts UTF-16 code units, not code points.
    if len(name.encode("utf-16-le")) // 2 > 255:
        return "Folder name is too long (maximum 255 characters)."

    if any(ch in _WINDOWS_FORBIDDEN_CHARS or ord(ch) < 32 for ch in name):
        return 'Folder name cannot contain < > : " | ? * or control characters on Windows.'

    if name.endswith((" ", ".")):
        return "Folder name cannot end with a space or a dot on Windows."

    # Windows ignores the extension and trailing spaces/dots here, so
    # "nul.txt" and "CON " are reserved too.
    device = name.rstrip(" .").split(".")[0].rstrip(" ").upper()
    if device in _WINDOWS_RESERVED_NAMES:
        return f"'{device}' is a reserved device name on Windows."

    return None


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------

def move_file(src: Path, dst: Path) -> None:
    """
    Move ``src`` to ``dst``. Errors propagate as ``OSError``.

    On Windows a plain rename is used with no copy fallback: when another
    program has the file open, ``shutil.move`` would copy it and then fail
    to delete the source, leaving a stray copy behind.
    """
    if IS_WINDOWS:
        os.rename(src, dst)
    else:
        shutil.move(str(src), str(dst))


def trash_windows(path: Path) -> tuple[bool, str | None]:
    """Send ``path`` to the Windows Recycle Bin."""
    from send2trash import send2trash

    try:
        send2trash(str(path))
    except OSError as exc:
        return False, f"Failed to trash '{path.name}': {exc}"
    return True, None


def describe_os_error(exc: OSError) -> str:
    """Return a user-facing description of ``exc``."""
    if IS_WINDOWS:
        messages = {
            32: "The file is open in another program.",
            5: "Access denied (file is locked, read-only, or protected).",
            183: "A file with that name already exists.",
        }
        winerror = getattr(exc, "winerror", None)
        if winerror in messages:
            return messages[winerror]
    return str(exc)


# ---------------------------------------------------------------------------
# User interface
# ---------------------------------------------------------------------------

def mono_font() -> str:
    """Return the monospace font family name for the log view."""
    return "Consolas" if IS_WINDOWS else "Monospace"


def trash_label() -> str:
    """Return the user-facing name of the system trash."""
    return "Recycle Bin" if IS_WINDOWS else "system trash"
