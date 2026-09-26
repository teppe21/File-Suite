# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-09-26

### Added
- **Architectural Decoupling**: Separated business logic into dedicated, GUI-independent modules:
  - `models.py`: Strongly-typed dataclasses (`OperationItem`, `OperationPlan`, `MoveRecord`, `ExecutionResult`, `DuplicateFile`, `DuplicateGroup`, `ScanProgress`).
  - `operations.py`: Plan generation, preview validation, atomic move execution, TOCTOU safety, FreeDesktop trash handling, and undo tracking.
  - `duplicates.py`: Background duplicate engine with size pre-filtering, 64 KB chunked SHA-256 hashing, and cooperative thread cancellation.
- **Dry-Run Preview Workflow**: Two-phase operation system requiring user confirmation of planned moves, source/target destinations, file counts, and collision resolutions before any disk mutation.
- **Session-Based Undo**: Added `undo_last_operation` allowing instant, single-click restoration of organized or isolated files back to their original root locations, with collision protection for newly created source files.
- **Structured Duplicate Manager**:
  - Group-by-group card view displaying SHA-256 digest prefixes and per-file byte sizes.
  - Individual selection checkboxes per duplicate file.
  - Quick action buttons: "Select All Duplicates", "Keep Originals Only", "Clear Selection".
  - Choice of isolation into `Duplicates/` folder (undoable) or moving to FreeDesktop system trash (`~/.local/share/Trash`).
- **Activity & Diagnostics Log**: In-app scrollable log view displaying timestamped operational records and error traces alongside standard CLI stdout output.
- **Enhanced Filesystem Safety**:
  - Symlink rejection: Both organization and deduplication engines strictly skip symlinks (`is_symlink()`) to prevent directory traversal or accidental target deletion.
  - TOCTOU mitigation: File existence and non-symlink status are verified both at preview creation and immediately prior to file movement.
  - Destination collision avoidance: Dynamic extension-aware renaming (`name_1.ext`, `archive_1.tar.gz`) for files already present at destination.
- **Comprehensive Test Suite**: Expanded test suite from 21 to 42 headless unit tests covering models, operation plans, collision handling, symlinks, deduplication engine, and undo semantics.
- **Continuous Integration & Automation**:
  - Expanded GitHub Actions workflow with a Python matrix across versions `3.10`, `3.11`, `3.12`, and `3.13`.
  - Automated Ruff linting and Bandit security scanning.
  - Automated PyInstaller executable build test and SHA-256 release checksum validation.
- **Release Verification**: `build.sh` automatically generates `dist/FileSuite.sha256` for release integrity checks.

### Changed
- **UI Design System**: Migrated from high-contrast accent colors and emojis to a restrained, professional graphite/slate desktop aesthetic (`#1E1E22`, `#26262B`, `#2E2E35`, `#388BFD`).
- Cleaned button, status, and tab labels of informal emoji characters in favor of crisp typography and status badges.
- Native folder picker integration with `zenity` and `kdialog` now features graceful exception handling and standard Tkinter fallback.
- Window close handler now signals cooperative thread cancellation to running background scan tasks before terminating.

### Security
- Hardened `.gitignore` to reject environment credentials, SSH/TLS keys, and local secrets.
- Enforced Bandit security linting (`S`) across repository code in `pyproject.toml`.

---

## [1.0.0] - 2026-09-20

### Added
- Initial release of File Suite for Linux desktop.
- File organization by preset category extensions (Images, Documents, Archives, Audio/Video, Code).
- Custom subfolder organization.
- Background threaded SHA-256 duplicate scanning.
- FreeDesktop trash support via `~/.local/share/Trash/files` and `.trashinfo`.
- Native directory dialog detection (`zenity`, `kdialog`).
- Standalone PyInstaller build script (`build.sh`) and user installer (`install.sh`).
- Basic unit test suite for path safety and collision avoidance.
