"""
Unit tests for centralized version management.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import version


class VersionTests(unittest.TestCase):
    def test_version_format(self):
        """Version string follows semantic versioning (MAJOR.MINOR.PATCH)."""
        semver_pattern = r"^\d+\.\d+\.\d+$"
        self.assertRegex(version.__version__, semver_pattern)

    def test_version_imported_in_main(self):
        """main.py imports and uses the centralized __version__."""
        repo_root = Path(__file__).resolve().parent.parent
        main_py = repo_root / "main.py"
        content = main_py.read_text(encoding="utf-8")
        self.assertIn("from version import __version__", content)
        self.assertIn("f\"File Suite v{__version__}", content)

    def test_build_script_uses_version_py(self):
        """build.sh dynamically queries version.py instead of hardcoding a version."""
        repo_root = Path(__file__).resolve().parent.parent
        build_sh = repo_root / "build.sh"
        content = build_sh.read_text(encoding="utf-8")
        self.assertIn("import version; print(version.__version__)", content)


if __name__ == "__main__":
    unittest.main()
