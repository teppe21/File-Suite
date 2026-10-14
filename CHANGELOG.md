# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

## [1.2.0] - 2026-10-14

### Added
- **Windows Support (Experimental)**: File Suite runs on Windows 10 22H2+ and Windows 11 (x64) from source. Adds `platform_utils.py` for platform-specific behavior; Linux behavior is unchanged except for the inode `0` change below.
  - Windows hidden and system files, cloud-only OneDrive files, and junctions and mount points are skipped or rejected; Windows-invalid folder names are rejected; files are moved without overwriting.
  - Deleted duplicates go to the Recycle Bin via `send2trash` (installed on Windows only).
  - On drives other than fixed local disks (for example USB sticks and network shares), the app warns before deleting duplicates and in the log that files may be deleted permanently instead of going to the Recycle Bin.
  - `CONIN$` and `CONOUT$` are rejected as reserved folder names.
  - Windows window icon (`organizer.ico`) and monospace log font.
- **Windows Packaging**: `packaging/windows/build.ps1` builds a PyInstaller one-dir bundle and writes `FileSuite-windows-x64-v<version>.zip` with a SHA-256 checksum file.
- **Windows CI**: `windows.yml` runs the test suite on Python 3.10-3.13 and builds the bundle, which is uploaded as a workflow artifact.
- **Windows Release Asset**: `release.yml` builds the Windows zip and attaches it and its `.sha256` file to the GitHub Release next to the Linux binary.
- Windows-specific and cross-platform unit tests (`test_platform_utils.py`, `test_windows.py`).

### Fixed
- **Duplicates: last copy protected**: Moving or trashing duplicates is refused while every copy of a group is selected; the dialog names the affected groups. Any copy can still be chosen as the one to keep.
- **Duplicates: stale scan results**: Scans record each file's modification time. Before moving or trashing, selected files whose size, modification time or inode changed are skipped, and a group with no unchanged kept copy is skipped entirely. Each skip is logged.
- **No-clobber moves on Linux**: Moves no longer use `shutil.move`, which silently replaced a destination created after the checks. Files are hard-linked then unlinked, with an exclusive-create copy fallback where hard links are unavailable (other drive, FAT/exFAT). The Linux trash uses the same move.
- **Duplicate scan stuck after a folder change**: Changing folders during a scan now resets the scan buttons and progress bar, and each scan gets its own cancel event so a new scan cannot revive the old one.
- **Undo renames hidden**: Files restored under a new name because the original location was taken are always logged as warnings, not only when another file failed.
- **Colliding preview destinations**: The organization preview tracks destinations already planned in the batch (e.g. `a.jpg` and `a_1.jpg` no longer both map to `Images/a_1.jpg`).
- **Possible hang when planning moves**: Planning duplicate moves (and executing a batch) could loop forever when a suffixed name was already planned in the batch.
- **Silent skips in duplicate moves**: Selected files that cannot be moved are recorded as skipped with a reason and logged.
- **FreeDesktop trash**: Honors `$XDG_DATA_HOME`, and `.trashinfo` files are created exclusively so another application's trash entry is never overwritten.

### Changed
- Hard-link accounting treats inode `0` as unknown, so files on filesystems that report no inode numbers are no longer counted as hard links of each other.
- `undo_last_operation` returns a fourth value: notes about files restored under a new name.
- Duplicate-group progress is counted incrementally instead of rescanning all hashes for every file.
- CI: `tests.yml` and `windows.yml` run with a read-only token.
- README: Linux primary / Windows experimental wording, `platform_utils.py` in the architecture, updated safety model, no hard-coded test counts, new "Development process" section.

### Removed
- Unused `_select_originals_only` method in `main.py`.

---

## [1.1.1] - 2026-09-27

### Added
- **Dependency CVE Hardening**: Updated `Pillow>=12.3.0,<13` in `requirements.txt` to resolve 35 known CVEs; added `pip-audit` dependency scanning to CI.
- **State Invalidation & Generation Guarding**: Centralized `_invalidate_target_dependent_state(new_path)` in `main.py` to reset organization preview, duplicate groups, and increment scan generation tokens, discarding stale worker callbacks upon directory changes.
- **Duplicate Scan Thread Safety & Error Handling**: Wrapped scan worker in robust exception handling to restore UI state on worker exceptions without freezing buttons.
- **Pre- and Post-Hash Stat Consistency**: Added size, mtime, inode, and device consistency checks before and after chunked SHA-256 calculation in `duplicates.py` to detect and safely skip concurrently modified files.
- **Duplicate Model Partial State Updates**: Added `update_duplicate_groups_after_removal` in `models.py` to prune only successfully moved or trashed files from duplicate cards, leaving unaffected groups and files visible.
- **Target Folder Containment for Duplicates**: Hardened `build_duplicate_move_plan` in `operations.py` with `resolve_destination` subfolder validation, source root containment checks, symlink rejection, and self-containment rejection.
- **Post-Mkdir Undo Containment Check**: Hardened `undo_last_operation` with strict post-mkdir containment verification to prevent directory escape.
- **Release Tag Verification**: Added automated GitHub Actions step in `release.yml` verifying `GITHUB_REF_NAME` matches `version.__version__`.
- **Archive Extension Parity**: Added `.zst` and `.tar.zst` to `CATEGORIES["Archives"]` in `core.py`.
- **Edge-Case Unit Tests**: Expanded test suite to 63 headless unit tests covering duplicate selections, model updates, post-hash file mutation, duplicate move plan safety, and archive classification.

### Changed
- **Duplicate Action Safety**: Replaced confusing button controls with "Select Duplicates" (strictly selects redundant copies, leaving originals preserved) and "Clear Selection".
- **Undo Independence**: Trashing duplicate files no longer clears `last_execution_result`, preserving undo capability for previous file organization operations.
- **Execution Concurrency Guards**: Protected plan execution, undo, duplicate moves, and duplicate trashing with `_is_executing` flags to prevent UI double-click re-entrancy.
- **CI Runners Pinned**: Pinned GitHub Actions runners to `ubuntu-24.04` to avoid runner drift.
- **Documentation Precision**: Revised `README.md` with accurate test counts (63 tests), logical reclaimable space terminology, single-level undo documentation, and updated architecture diagrams.

---

## [1.1.0] - 2026-09-26

### Added
- Architectural decoupling into `models.py`, `operations.py`, and `duplicates.py`.
- Dry-run preview workflow requiring explicit confirmation before filesystem mutations.
- Session-based undo capability restoring moved files back to root directory.
- Structured duplicate manager with card layout, SHA-256 digests, and selection controls.
- In-app activity and diagnostics log with timestamped event recording.
- Multi-version test matrix in CI (Python 3.10, 3.11, 3.12, 3.13).
- Automated SHA-256 release checksum generation in `build.sh`.

### Changed
- UI styling migrated to a restrained, professional graphite dark palette (`#1E1E22`, `#26262B`, `#2E2E35`, `#388BFD`).
- Removed informal emoji decorations from buttons and headers.

### Security
- Hardened `.gitignore` against credential and key leaks.
- Configured Ruff linter with security rules (`S`).

---

## [1.0.0] - 2026-09-20

### Added
- Initial release of File Suite for Linux desktop.
- File organization by preset category extensions.
- Custom subfolder organization.
- Background threaded duplicate scanning.
- FreeDesktop trash integration.
- Native directory dialog detection (`zenity`, `kdialog`).
- Standalone PyInstaller build script (`build.sh`) and user installer (`install.sh`).
