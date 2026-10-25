"""
Platform-specific helpers for File Suite.

Every function keeps the existing Linux behavior on non-Windows systems and
adds the Windows equivalent behind ``IS_WINDOWS``; macOS equivalents sit
behind ``IS_MACOS``. This module must not import any other project module.
"""

from __future__ import annotations

import contextlib
import errno
import os
import shutil
import stat
import sys
import unicodedata
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

# Windows file attribute bits and reparse tags, defined here because the
# ``stat`` module only exposes them on Windows (and not all of them).
FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
IO_REPARSE_TAG_SYMLINK = 0xA000000C
DRIVE_FIXED = 3  # GetDriveTypeW result for a local fixed disk

# macOS file flags (``st_flags``), defined here because the ``stat`` module
# lacks ``SF_DATALESS`` before Python 3.13. Values from Apple's xnu
# bsd/sys/stat.h (github.com/apple-oss-distributions/xnu, and the macOS SDK).
UF_HIDDEN = 0x8000  # hidden in Finder
SF_DATALESS = 0x40000000  # iCloud placeholder, content not on disk

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
    ["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"]
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


def macos_flags(path: Path) -> int | None:
    """Return the macOS file flags of ``path`` (not following links)."""
    if not IS_MACOS:
        return None
    try:
        return path.lstat().st_flags
    except OSError:
        return None


def is_hidden(path: Path) -> bool:
    """
    Return True for dot-files and, on Windows, for files marked hidden or
    system. On macOS the Finder "hidden" flag counts too. Unreadable
    attributes or flags count as hidden.
    """
    if path.name.startswith("."):
        return True
    # Windows wins if both are set: tests patch IS_WINDOWS on macOS runners.
    if IS_MACOS and not IS_WINDOWS:
        flags = macos_flags(path)
        return flags is None or bool(flags & UF_HIDDEN)
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
    """Return True for Windows or iCloud files whose content is not on disk."""
    if IS_MACOS and not IS_WINDOWS:
        flags = macos_flags(path)
        return flags is not None and bool(flags & SF_DATALESS)
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


def macos_name_problem(name: str) -> str | None:
    """Return why ``name`` is not a good macOS folder name, or None."""
    # POSIX accepts ":" but Finder shows it as "/" (and the reverse).
    if ":" in name:
        return "Folder name cannot contain ':' on macOS (Finder shows it as '/')."
    return None


def collision_key(path: Path) -> Path:
    """
    Return ``path`` normalized the way the filesystem compares names: on
    macOS APFS ignores case and Unicode normalization (NFC vs NFD), elsewhere
    the path is returned unchanged.
    """
    if not IS_MACOS:
        return path
    decomposed = unicodedata.normalize("NFD", str(path))
    return Path(unicodedata.normalize("NFD", decomposed.casefold()))


class _FoldedPathSet(set):
    """Set of paths that treats names the filesystem sees as equal as one."""

    def add(self, path: Path) -> None:
        super().add(collision_key(path))

    def __contains__(self, path: object) -> bool:
        return isinstance(path, Path) and super().__contains__(collision_key(path))


def new_reserved_set() -> set[Path]:
    """
    Return an empty set for planned destinations. A plain ``set`` except on
    macOS, where ``A.txt`` and ``a.txt`` (or NFC/NFD spellings) are one name.
    """
    return _FoldedPathSet() if IS_MACOS else set()


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------

# os.link errors meaning "hard links unavailable here" (other drive, FAT/exFAT)
_NO_HARDLINK_ERRNOS = {errno.EXDEV, errno.EPERM, errno.ENOTSUP, errno.EMLINK}


def move_file(src: Path, dst: Path) -> None:
    """
    Move ``src`` to ``dst`` without ever replacing an existing ``dst``.
    Errors propagate as ``OSError`` (``FileExistsError`` if ``dst`` exists).

    On Windows a plain rename is used with no copy fallback: when another
    program has the file open, ``shutil.move`` would copy it and then fail
    to delete the source, leaving a stray copy behind.

    On Linux ``rename`` silently replaces ``dst``, so the file is hard-linked
    to ``dst`` (atomic, fails if ``dst`` exists) and then unlinked from
    ``src``. Where hard links are unavailable it is copied into an
    exclusively created ``dst`` instead.
    """
    if IS_WINDOWS:
        os.rename(src, dst)
        return

    try:
        os.link(src, dst, follow_symlinks=False)
    except OSError as exc:
        # On macOS EPERM means a locked (uchg) file, not missing hard links:
        # the copy would inherit the lock and could not be removed again.
        if IS_MACOS and exc.errno == errno.EPERM:
            raise
        if exc.errno not in _NO_HARDLINK_ERRNOS:
            raise
        _copy_then_unlink(src, dst)
        return

    try:
        os.unlink(src)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(dst)
        raise


def _copy_then_unlink(src: Path, dst: Path) -> None:
    """Copy ``src`` into a new ``dst``, then remove ``src``; never leaves a partial ``dst``."""
    with open(src, "rb") as fin:
        fout = open(dst, "xb")  # FileExistsError here leaves dst untouched
        try:
            with fout:
                shutil.copyfileobj(fin, fout)
            shutil.copystat(src, dst)
            os.unlink(src)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(dst)
            raise


def trash_windows(path: Path) -> tuple[bool, str | None]:
    """Send ``path`` to the Windows Recycle Bin."""
    from send2trash import send2trash

    try:
        send2trash(str(path))
    except OSError as exc:
        return False, f"Failed to trash '{path.name}': {exc}"
    return True, None


def trash_macos(path: Path) -> tuple[bool, str | None]:
    """
    Send ``path`` to the Finder Trash, where Put Back works. On a volume
    without a Trash this fails and leaves the file in place.
    """
    try:
        from Foundation import NSURL, NSFileManager
    except ImportError as exc:
        return False, f"Failed to trash '{path.name}': {exc}"

    url = NSURL.fileURLWithPath_(str(path))
    manager = NSFileManager.defaultManager()
    ok, _, error = manager.trashItemAtURL_resultingItemURL_error_(url, None, None)
    if not ok:
        # localizedFailureReason() is often None; the description never is.
        return False, f"Failed to trash '{path.name}': {error.localizedDescription()}"
    return True, None


def windows_drive_type(root: str) -> int:
    """Return the ``GetDriveTypeW`` result for the drive root ``root``."""
    import ctypes

    get_drive_type = ctypes.windll.kernel32.GetDriveTypeW
    get_drive_type.argtypes = [ctypes.c_wchar_p]
    get_drive_type.restype = ctypes.c_uint
    return get_drive_type(root)


def trash_may_be_permanent(path: Path) -> bool:
    """
    Return True if sending ``path`` to the Recycle Bin may delete it
    permanently: on drives other than fixed local disks (USB sticks,
    network shares) there may be no Recycle Bin. Always False off Windows.
    A missing drive root or a failed lookup counts as True.
    """
    # macOS: trashItemAtURL fails instead of deleting where there is no Trash.
    if not IS_WINDOWS:
        return False
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    if not drive:
        return True
    try:
        return windows_drive_type(drive + "\\") != DRIVE_FIXED
    except Exception:
        return True


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
    elif IS_MACOS and exc.errno == errno.EPERM:
        # EPERM, not EACCES: both a Finder lock and a privacy (TCC) denial
        # report "Operation not permitted".
        return (
            "The item is locked in Finder, or macOS privacy settings block File "
            "Suite (or the terminal it runs from). Unlock it in Get Info, or allow "
            "access under System Settings › Privacy & Security › Files and "
            "Folders (or Full Disk Access)."
        )
    return str(exc)


# ---------------------------------------------------------------------------
# User interface
# ---------------------------------------------------------------------------

def mono_font() -> str:
    """Return the monospace font family name for the log view."""
    if IS_WINDOWS:
        return "Consolas"
    return "Menlo" if IS_MACOS else "Monospace"


def trash_label() -> str:
    """Return the user-facing name of the system trash."""
    if IS_WINDOWS:
        return "Recycle Bin"
    return "Trash" if IS_MACOS else "system trash"
