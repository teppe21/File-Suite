# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] - 2026-09-26

### Added
- **Destination Containment Hardening**: Added `_validate_destination_containment` in `operations.py` to revalidate destination directory components immediately prior to execution, rejecting any intermediate symbolic link injected after the dry-run preview.
- **Deterministic Duplicate Ordering**: Implemented stable, case-insensitive sorting (`key=lambda p: (p.name.casefold(), str(p))`) for candidate files in `duplicates.py`, ensuring the default original file is identical regardless of OS directory iteration order.
- **Hard Link Disk Reclaim Accounting**: Updated `DuplicateFile` and `DuplicateGroup.reclaimable_bytes` to evaluate device and inode pairs, ensuring shared hard links do not artificially inflate reclaimable storage metrics.
- **Trash Transaction Rollback**: Enhanced `move_to_system_trash` with automatic metadata cleanup, ensuring `.trashinfo` files are deleted if the physical file move fails.
- **Resilient Reverse Undo**: `undo_last_operation` processes records in reverse order, protects against destination symlinks, avoids overwriting newly created source files, and retains failed records for subsequent retry.
- **Centralized Version Management**: Introduced `version.py` as the single source of truth for application versioning, consumed by `main.py`, `build.sh`, and unit tests.
- **Tagged Release Automation**: Added `.github/workflows/release.yml` triggering on `v*` tags to validate tests, run Bandit, compile standalone binaries with `build.sh`, verify SHA-256 checksums, and publish GitHub Release assets.
- **Dedicated CI Security Job**: Added Bandit security scanning to `.github/workflows/tests.yml` alongside Ruff and multi-version Python testing.
- **Edge-Case Unit Tests**: Expanded test suite to 58 headless unit tests covering destination symlink injection, trash rollback, deterministic duplicate ordering, hard links, and version consistency.

### Changed
- **Documentation Precision**: Revised `README.md` to remove inaccurate claims ("zero data loss", "zero latency", "atomic moves") in favor of precise technical explanations and an explicit Limitations section.
- **User-Facing Error Formatting**: Restructured UI error dialogs into clear "What happened / Why / Next steps" messages with details logged to the activity viewer.
- **Collision Path Checks**: Updated `build_collision_safe_path` to treat existing broken symlinks as occupied to prevent accidental file clobbering.

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
