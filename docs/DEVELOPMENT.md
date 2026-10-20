# Development

[Back to README](../README.md)

## Development process

File Suite is developed with AI assistance. Every pull request to `main` and every push to `main` runs the unit tests on Linux and Windows, plus Ruff, Bandit and pip-audit, in GitHub Actions. The author reviews each change before it is merged.

## Architecture

The presentation layer, domain logic and filesystem access are kept in separate modules:

```mermaid
graph TD
    subgraph Presentation ["Presentation Layer (CustomTkinter)"]
        UI["ui/app.py: FileOrganizerApp + views"]
        LOG["In-App Activity Log"]
        DLG["Native File Dialogs (zenity / kdialog)"]
    end

    subgraph Domain ["Domain & Business Logic"]
        VER["version.py: Version Authority"]
        MOD["models.py: Data Models & Plans"]
        OPS["operations.py: Plan Generation, Execution & Undo"]
        DUP["duplicates.py: Chunked SHA-256 Engine"]
        CORE["core.py: Path Validation & Categories"]
        PLAT["platform_utils.py: Linux/Windows Platform Helpers"]
    end

    subgraph Storage ["Filesystem (Linux shown)"]
        FS["Root Directory (Non-Recursive)"]
        TRASH["$XDG_DATA_HOME/Trash (FreeDesktop)"]
        XDG["~/.local/share/applications (Desktop Launcher)"]
    end

    UI --> OPS
    UI --> DUP
    UI --> MOD
    UI --> VER
    UI --> CORE
    OPS --> MOD
    OPS --> CORE
    DUP --> MOD
    DUP --> CORE
    OPS --> PLAT
    DUP --> PLAT
    CORE --> PLAT
    UI --> PLAT
    OPS --> FS
    OPS --> TRASH
    DUP --> FS
```

### Module responsibilities

| Module | Responsibility |
| :--- | :--- |
| `version.py` | Single source of truth for the application version. |
| `core.py` | Pure path validation, category mappings and collision-safe renaming. |
| `models.py` | Typed dataclasses for operation plans, items, execution results, duplicate groups and scan progress. |
| `operations.py` | Dry-run plan building, containment checks, moves, FreeDesktop trash and session undo. |
| `duplicates.py` | Size grouping, chunked SHA-256 hashing, deterministic sorting and cooperative cancellation. |
| `platform_utils.py` | Linux/Windows differences: hidden files, link detection, no-clobber moves, Recycle Bin, folder name rules. |
| `main.py` | Entry point: creates the window and runs the main loop. |
| `ui/app.py` | Main window, shared state, logging, undo, folder change and the safety checks around every move or trash. |
| `ui/organize_view.py`, `ui/duplicates_view.py`, `ui/activity_view.py` | The three views, built once at start-up and shown or hidden. |
| `ui/theme.py`, `ui/formatting.py` | Colours and fonts; pure text helpers (sizes, plurals, summaries), unit-tested without a display. |

`packaging/windows/` holds the PyInstaller spec, `build.ps1` and `make_icon.py`, which regenerates `organizer.ico` from `organizer.jpg`.

### Behavior details

- **Duplicate scan**: Runs on a background thread with 64 KB SHA-256 chunks, live progress and immediate cancellation.
- **Deterministic originals**: Files in a group are sorted case-insensitively, so the default original is the same regardless of directory iteration order.
- **Duplicate view**: Groups are shown in a tree (one row per group, one per file with a tick box, size, modified time and role). "Select all extra copies" ticks every copy except the original; "Clear selection" clears it. A group with every copy ticked is highlighted live. Selected files go into a `Duplicates/` folder (undoable) or to the system trash.
- **Reclaimable space**: Hard links that share an inode are counted once.
- **Logging**: Timestamped records go to the in-app Activity view (filter by level, copy, save as text) and to the console.
- **UI**: CustomTkinter with `ttk.Treeview` tables. Views are built once and shown or hidden, so their state survives switching. Colours follow the app icon in light and dark mode (`ui/theme.py`). Keyboard: Ctrl+O folder, Ctrl+1/2/3 views, Ctrl+Enter preview or scan, Ctrl+M move, Ctrl+Z undo, Space tick, Delete trash (duplicates list), Esc closes dialogs.
- **Folder picker**: On Linux, `zenity` (GTK/GNOME) or `kdialog` (KDE) is used if installed, with the Tkinter dialog as fallback.

Safety rules are listed in [SAFETY.md](SAFETY.md).

## Tests and checks

```bash
python3 -m unittest discover -s tests -v
ruff check .
bandit -c pyproject.toml -r .
pip-audit -r requirements.txt
```

Windows-only and Linux-only tests are skipped on the other platform. Ruff and Bandit are configured in `pyproject.toml`; Ruff checks pycodestyle, Pyflakes, isort, pyupgrade, Bugbear and flake8-bandit rules.

## Continuous integration

- **`tests.yml`** (push and pull request to `main`, `ubuntu-24.04`): Ruff; Bandit and pip-audit; unit tests on Python 3.10, 3.11, 3.12 and 3.13, each followed by a 5-second GUI start under Xvfb; then builds the Linux binary with `build.sh`, verifies its SHA-256 checksum and uploads it as the artifact `FileSuite-linux-x86_64`.
- **`windows.yml`** (push and pull request to `main`, `windows-2025`): unit tests on Python 3.10 to 3.13 and pip-audit on 3.12; then builds the bundle with `packaging/windows/build.ps1`, verifies the checksum and bundle contents, runs a 5-second start-up smoke test and uploads the artifact `FileSuite-windows-x64`.
- **`release.yml`** (tag `v*`): see below.

## Release process

Pushing a version tag (`v<version>`) runs `release.yml`:

1. Verifies that the tag matches `version.py`, then runs Ruff, Bandit, pip-audit and the unit tests.
2. Builds the Windows zip with `packaging/windows/build.ps1` and verifies its checksum.
3. Builds the Linux binary with `build.sh` and verifies its checksum.
4. Creates a GitHub Release with the Linux binary, the Windows zip and their `.sha256` files attached, with generated release notes.

Release history is in [CHANGELOG.md](../CHANGELOG.md).
