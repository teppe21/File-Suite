# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
