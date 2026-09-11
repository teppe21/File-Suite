"""
Pure, GUI-independent helpers for File Suite.

Anything that does not need CustomTkinter or the filesystem UI lives here
so it can be unit-tested without launching a window.
"""

from pathlib import Path
import re


# ---------------------------------------------------------------------------
# File categories
# ---------------------------------------------------------------------------

CATEGORIES: dict[str, set[str]] = {
    "Images": {
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
        ".bmp", ".ico", ".tif", ".tiff", ".heic",
    },
    "Documents": {
        ".txt", ".pdf", ".doc", ".docx", ".odt", ".rtf",
        ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".csv",
    },
    "Archives": {
        ".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2",
        ".tar.xz", ".7z", ".rar", ".gz", ".bz2", ".xz",
    },
    "Media": {
        ".mp4", ".mkv", ".mov", ".avi", ".webm",
        ".mp3", ".flac", ".wav", ".ogg", ".m4a",
    },
    "Installers & Code": {
        ".deb", ".rpm", ".appimage", ".sh", ".py", ".js",
        ".ts", ".json", ".yml", ".yaml", ".toml", ".html",
        ".css", ".c", ".cpp", ".h", ".rs", ".go", ".java",
    },
}

# Extensions that consist of more than one dot-separated component.
# Used for collision-renaming so `backup.tar.gz` becomes `backup_1.tar.gz`
# instead of `backup.tar_1.gz`.
MULTI_EXTENSIONS: tuple[str, ...] = (
    ".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst",
)

# Allow letters, digits, spaces, dashes, underscores, dots (not leading).
_FOLDER_NAME_RE = re.compile(r"^[^\x00/\\]+$")


# ---------------------------------------------------------------------------
# Folder-name validation
# ---------------------------------------------------------------------------

def validate_folder_name(name: str) -> tuple[bool, str]:
    """
    Validate a user-supplied destination subfolder name.

    Returns ``(True, cleaned_name)`` on success or ``(False, error_message)``
    on failure. The name must be a single path component: no separators,
    no absolute paths, no ``.``/``..``, no control characters.
    """
    if name is None:
        return False, "Folder name is required."

    cleaned = name.strip()
    if not cleaned:
        return False, "Folder name cannot be empty."

    if cleaned in (".", ".."):
        return False, "Folder name cannot be '.' or '..'."

    if cleaned.startswith("~"):
        return False, "Folder name cannot start with '~'."

    if Path(cleaned).is_absolute():
        return False, "Folder name cannot be an absolute path."

    if "/" in cleaned or "\\" in cleaned:
        return False, "Folder name cannot contain path separators."

    if not _FOLDER_NAME_RE.match(cleaned):
        return False, "Folder name contains invalid characters."

    return True, cleaned


def resolve_destination(target_dir: Path, folder_name: str) -> tuple[bool, Path | str]:
    """
    Validate ``folder_name`` and confirm that the resulting path stays
    strictly inside ``target_dir``.

    Returns ``(True, path)`` or ``(False, error_message)``.
    """
    ok, result = validate_folder_name(folder_name)
    if not ok:
        return False, result  # type: ignore[return-value]

    try:
        target_resolved = target_dir.resolve(strict=False)
    except OSError as exc:
        return False, f"Selected directory is not accessible: {exc}"

    candidate = (target_resolved / result).resolve(strict=False)

    try:
        candidate.relative_to(target_resolved)
    except ValueError:
        return False, "Destination would escape the selected directory."

    if candidate == target_resolved:
        return False, "Destination cannot be the selected directory itself."

    return True, candidate


# ---------------------------------------------------------------------------
# Extension handling
# ---------------------------------------------------------------------------

def normalize_extension(ext: str) -> str | None:
    """
    Normalize a single user-entered extension.

    - ``"jpg"``  -> ``".jpg"``
    - ``"JPG"``  -> ``".jpg"``
    - ``".JPG"`` -> ``".jpg"``
    - ``""``     -> ``None``
    - anything containing ``/``, ``\\`` or NUL -> ``None``
    """
    if ext is None:
        return None

    cleaned = ext.strip().lower()
    if not cleaned:
        return None

    if any(ch in cleaned for ch in ("/", "\\", "\x00")):
        return None

    if not cleaned.startswith("."):
        cleaned = "." + cleaned

    # Reject a bare dot or a dot followed only by dots.
    if cleaned == "." or set(cleaned) == {"."}:
        return None

    return cleaned


def parse_custom_extensions(raw: str) -> set[str]:
    """Parse a comma-separated string into a set of normalized extensions."""
    if not raw:
        return set()
    result: set[str] = set()
    for token in raw.split(","):
        normalized = normalize_extension(token)
        if normalized:
            result.add(normalized)
    return result


def collect_selected_extensions(
    selected_categories: dict[str, bool],
    custom_input: str,
) -> set[str]:
    """
    Combine checked preset categories and the custom extension input into a
    single normalized set of extensions.
    """
    extensions: set[str] = set()
    for cat_name, is_checked in selected_categories.items():
        if is_checked and cat_name in CATEGORIES:
            extensions.update(CATEGORIES[cat_name])
    extensions.update(parse_custom_extensions(custom_input))
    return extensions


def classify_extension(ext: str, full_ext: str) -> str | None:
    """
    Return the preset category name for the given extension, or ``None``.
    ``full_ext`` is the joined multi-suffix (e.g. ``".tar.gz"``).
    """
    for cat_name, cat_extensions in CATEGORIES.items():
        if ext in cat_extensions or full_ext in cat_extensions:
            return cat_name
    return None


# ---------------------------------------------------------------------------
# Filename collision handling
# ---------------------------------------------------------------------------

def split_stem_and_suffix(filename: str) -> tuple[str, str]:
    """
    Split ``"backup.tar.gz"`` into ``("backup", ".tar.gz")``.
    Falls back to the last suffix for other names.
    """
    name = filename
    lower = name.lower()

    for multi in sorted(MULTI_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(multi):
            return name[: -len(multi)], name[-len(multi):]

    p = Path(name)
    suffix = p.suffix
    if suffix:
        return name[: -len(suffix)], suffix
    return name, ""


def build_collision_safe_path(dest_dir: Path, filename: str) -> Path:
    """
    Return a path inside ``dest_dir`` for ``filename`` that does not yet
    exist. Preserves multi-extension suffixes:

        backup.tar.gz   -> backup_1.tar.gz
        photo.jpg       -> photo_1.jpg
        file            -> file_1
    """
    candidate = dest_dir / filename
    if not candidate.exists():
        return candidate

    stem, suffix = split_stem_and_suffix(filename)
    counter = 1
    while True:
        new_name = f"{stem}_{counter}{suffix}"
        candidate = dest_dir / new_name
        if not candidate.exists():
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Duplicate detection (size grouping)
# ---------------------------------------------------------------------------

def group_by_size(files: list[Path]) -> dict[int, list[Path]]:
    """
    Group candidate files by size. Files whose size is unique cannot be
    duplicates and do not need hashing.
    """
    groups: dict[int, list[Path]] = {}
    for f in files:
        try:
            size = f.stat().st_size
        except OSError:
            continue
        groups.setdefault(size, []).append(f)
    return groups