import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Make `core` importable when running from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import (  # noqa: E402
    build_collision_safe_path,
    collect_selected_extensions,
    normalize_extension,
    parse_custom_extensions,
    resolve_destination,
    split_stem_and_suffix,
    validate_folder_name,
)


class ValidateFolderNameTests(unittest.TestCase):
    def test_valid_names(self):
        for name in ["MyFiles", "Sorted", "Code", "Photos", "a-b_c.d", "  Padded  "]:
            ok, cleaned = validate_folder_name(name)
            self.assertTrue(ok, f"{name!r} should be valid")
            self.assertNotEqual(cleaned.strip(), "")

    def test_empty(self):
        for name in ["", "   ", None]:
            ok, msg = validate_folder_name(name)
            self.assertFalse(ok)

    def test_dot_and_dotdot(self):
        for name in [".", "..", " ./"]:
            ok, _ = validate_folder_name(name)
            self.assertFalse(ok, f"{name!r} should be rejected")

    def test_separators(self):
        for name in ["foo/bar", "foo\\bar", "/abs", "..\\x", "a/b/c"]:
            ok, _ = validate_folder_name(name)
            self.assertFalse(ok, f"{name!r} should be rejected")

    def test_absolute(self):
        ok, _ = validate_folder_name("/tmp")
        self.assertFalse(ok)

    def test_tilde_prefix(self):
        for name in ["~", "~/foo", "~user"]:
            ok, _ = validate_folder_name(name)
            self.assertFalse(ok, f"{name!r} should be rejected")

    def test_control_characters(self):
        # ASCII control characters (tab, newline, CR, NUL, escape) and
        # DEL must all be rejected.
        for name in [
            "foo\tbar",
            "foo\nbar",
            "foo\rbar",
            "foo\x00bar",
            "foo\x01bar",
            "foo\x1bbar",
            "foo\x7fbar",
        ]:
            ok, _ = validate_folder_name(name)
            self.assertFalse(ok, f"{name!r} should be rejected")

    def test_unicode_names_are_allowed(self):
        # Unicode folder names are legal on Linux and must be accepted.
        for name in ["Képek", "Dokumentumok", "日本語", "café", "naïve_folder"]:
            ok, cleaned = validate_folder_name(name)
            self.assertTrue(ok, f"{name!r} should be accepted")
            self.assertEqual(cleaned, name)

    def test_symbols_in_names(self):
        # Colon, question mark, asterisk etc. are legal on Linux.
        for name in ["foo:bar", "foo?bar", "foo*bar", "a'b", 'a"b']:
            ok, _ = validate_folder_name(name)
            self.assertTrue(ok, f"{name!r} should be accepted")

    def test_resolve_destination_rejects_escape(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp)
            for bad in ["../escape", "../../escape", "/tmp", ".", ".."]:
                ok, _ = resolve_destination(target, bad)
                self.assertFalse(ok, f"{bad!r} should be rejected")

    def test_resolve_destination_accepts_plain(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp)
            ok, path = resolve_destination(target, "Sorted")
            self.assertTrue(ok)
            self.assertTrue(str(path).startswith(str(target.resolve())))


class ExtensionTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_extension("jpg"), ".jpg")
        self.assertEqual(normalize_extension("JPG"), ".jpg")
        self.assertEqual(normalize_extension(".JPG"), ".jpg")
        self.assertEqual(normalize_extension(" .png "), ".png")
        self.assertIsNone(normalize_extension(""))
        self.assertIsNone(normalize_extension("/etc/passwd"))
        self.assertIsNone(normalize_extension("a/b"))
        self.assertIsNone(normalize_extension("."))

    def test_parse_custom(self):
        result = parse_custom_extensions("jpg, .PNG, bad/path, , iso")
        self.assertEqual(result, {".jpg", ".png", ".iso"})

    def test_collect(self):
        selected = {"Images": True, "Documents": False}
        result = collect_selected_extensions(selected, ".iso")
        self.assertIn(".jpg", result)
        self.assertIn(".iso", result)
        self.assertNotIn(".pdf", result)


class CollisionTests(unittest.TestCase):
    def test_split_single(self):
        self.assertEqual(split_stem_and_suffix("photo.jpg"), ("photo", ".jpg"))

    def test_split_multi(self):
        self.assertEqual(
            split_stem_and_suffix("backup.tar.gz"), ("backup", ".tar.gz")
        )
        self.assertEqual(
            split_stem_and_suffix("archive.tar.bz2"), ("archive", ".tar.bz2")
        )

    def test_split_none(self):
        self.assertEqual(split_stem_and_suffix("README"), ("README", ""))

    def test_collision_none(self):
        with TemporaryDirectory() as tmp:
            dest = Path(tmp)
            path = build_collision_safe_path(dest, "photo.jpg")
            self.assertEqual(path.name, "photo.jpg")

    def test_collision_sequence(self):
        with TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "photo.jpg").touch()
            self.assertEqual(build_collision_safe_path(dest, "photo.jpg").name, "photo_1.jpg")
            (dest / "photo_1.jpg").touch()
            self.assertEqual(build_collision_safe_path(dest, "photo.jpg").name, "photo_2.jpg")

    def test_collision_multi_ext(self):
        with TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "backup.tar.gz").touch()
            path = build_collision_safe_path(dest, "backup.tar.gz")
            self.assertEqual(path.name, "backup_1.tar.gz")

    def test_collision_no_extension(self):
        with TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "README").touch()
            self.assertEqual(build_collision_safe_path(dest, "README").name, "README_1")


if __name__ == "__main__":
    unittest.main()