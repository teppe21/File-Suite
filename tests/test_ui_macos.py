"""
UI behaviour for macOS that needs no display: shortcut labels and the key
sequences ``_bind_shortcuts`` registers. Off macOS both must stay exactly what
they were before the macOS port; the expected values below are copied from
``main``.
"""

from __future__ import annotations

import ast
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from platform_utils import trash_label
from ui.formatting import shortcut, undo_label

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

# Every tooltip with a shortcut, character for character as on main.
MAIN_TOOLTIPS = {
    "Choose another folder  (Ctrl+O)",
    "Ctrl+1",
    "Ctrl+2",
    "Ctrl+3",
    "Undo  (Ctrl+Z)",
    "Compare every file directly in this folder. Nothing changes.  (Ctrl+Enter)",
    f"Send the ticked copies to the {trash_label()}. This can't be undone from File Suite.  (Delete)",
    "Move the ticked copies into a “Duplicates” folder here. You can undo this.  (Ctrl+M)",
    "Show what would move. Nothing changes yet.  (Ctrl+Enter)",
    "Move the previewed files into their folders. You can undo this.  (Ctrl+M)",
}

MACOS_TOOLTIPS = {
    "Choose another folder  (⌘O)",
    "⌘1",
    "⌘2",
    "⌘3",
    "Undo  (⌘Z)",
    "Compare every file directly in this folder. Nothing changes.  (⌘↩)",
    f"Send the ticked copies to the {trash_label()}. This can't be undone from File Suite.  (⌘⌫)",
    "Move the ticked copies into a “Duplicates” folder here. You can undo this.  (⌘M)",
    "Show what would move. Nothing changes yet.  (⌘↩)",
    "Move the previewed files into their folders. You can undo this.  (⌘M)",
}

# Window-wide sequences, in registration order, as on main.
MAIN_SEQUENCES = [
    "<Control-o>",
    "<Control-O>",
    "<Control-z>",
    "<Control-Z>",
    "<Control-m>",
    "<Control-M>",
    "<Control-Key-1>",
    "<Control-Key-2>",
    "<Control-Key-3>",
    "<Control-Return>",
    "<Control-KP_Enter>",
]
MACOS_SEQUENCES = [seq.replace("Control", "Command") for seq in MAIN_SEQUENCES] + [
    "<Command-w>",
    "<Command-W>",
]


def _is_shortcut_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "shortcut"


def _tooltip_expressions() -> list[ast.expr]:
    """
    Every expression in ``ui/`` that builds a tooltip around ``shortcut()``: an
    f-string containing a call, or a bare call used as the whole text.
    """
    found: list[ast.expr] = []
    for path in sorted(UI_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        nested: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                calls = [n for n in ast.walk(node) if _is_shortcut_call(n)]
                if calls:
                    found.append(node)
                    nested.update(id(call) for call in calls)
        found.extend(n for n in ast.walk(tree) if _is_shortcut_call(n) and id(n) not in nested)
    return found


def _evaluate(node: ast.expr, idx: int) -> str:
    """Run a tooltip expression from the real source with the names it uses."""
    code = compile(ast.fix_missing_locations(ast.Expression(node)), "<ui>", "eval")
    names = {
        "__builtins__": {"str": str},
        "shortcut": shortcut,
        "trash_label": trash_label,
        "undo_label": undo_label,
        "res": None,  # nothing to undo
        "idx": idx,
    }
    return eval(code, names)  # noqa: S307 - our own source, parsed above


def _built_tooltips() -> set[str]:
    return {_evaluate(node, idx) for node in _tooltip_expressions() for idx in range(3)}


class ShortcutTests(unittest.TestCase):
    def test_off_macos_forms(self):
        with patch("ui.formatting.IS_MACOS", False):
            self.assertEqual(shortcut("O"), "Ctrl+O")
            self.assertEqual(shortcut("1"), "Ctrl+1")
            self.assertEqual(shortcut("Enter"), "Ctrl+Enter")
            self.assertEqual(shortcut("Delete"), "Delete")

    def test_macos_forms(self):
        with patch("ui.formatting.IS_MACOS", True):
            self.assertEqual(shortcut("O"), "⌘O")
            self.assertEqual(shortcut("1"), "⌘1")
            self.assertEqual(shortcut("Enter"), "⌘↩")
            self.assertEqual(shortcut("Delete"), "⌘⌫")


class TooltipTextTests(unittest.TestCase):
    def test_off_macos_every_tooltip_is_byte_identical_to_main(self):
        with patch("ui.formatting.IS_MACOS", False):
            self.assertEqual(_built_tooltips(), MAIN_TOOLTIPS)

    def test_macos_uses_command_glyphs(self):
        with patch("ui.formatting.IS_MACOS", True):
            self.assertEqual(_built_tooltips(), MACOS_TOOLTIPS)

    def test_no_hardcoded_shortcut_text_is_left_in_ui(self):
        stray = []
        for path in sorted(UI_DIR.glob("*.py")):
            if path.name == "formatting.py":  # where the text is made
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = {
                id(node.value)
                for node in ast.walk(tree)
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            }
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and id(node) not in docstrings
                    and ("Ctrl" in node.value or "(Delete)" in node.value)
                ):
                    stray.append(f"{path.name}:{node.lineno}: {node.value!r}")
        self.assertEqual(stray, [])


class BindingTests(unittest.TestCase):
    """The sequences ``_bind_shortcuts`` registers, captured without a window."""

    def _sequences(self, macos: bool) -> list[str]:
        try:
            from ui.app import FileOrganizerApp
        except ImportError as exc:  # no tkinter in this Python
            self.skipTest(f"ui.app needs tkinter: {exc}")
        bound: list[str] = []
        app = SimpleNamespace(
            bind=lambda sequence, _handler: bound.append(sequence),
            select_folder=MagicMock(),
            execute_undo=MagicMock(),
            _move_shortcut=MagicMock(),
            _run_shortcut=MagicMock(),
            _on_closing=MagicMock(),
            show_view=MagicMock(),
        )
        with patch("ui.app.IS_MACOS", macos):
            FileOrganizerApp._bind_shortcuts(app)
        return bound

    def test_off_macos_sequences_are_unchanged(self):
        self.assertEqual(self._sequences(False), MAIN_SEQUENCES)

    def test_macos_binds_command_and_closes_with_cmd_w(self):
        self.assertEqual(self._sequences(True), MACOS_SEQUENCES)


class ClosingTests(unittest.TestCase):
    def test_closing_twice_cancels_the_scan_and_destroys_once(self):
        """Cmd+W arrives as a key and as the Close menu item; Cmd+Q as the Quit command."""
        try:
            from ui.app import FileOrganizerApp
        except ImportError as exc:  # no tkinter in this Python
            self.skipTest(f"ui.app needs tkinter: {exc}")
        app = SimpleNamespace(
            _is_closing=False,
            _cancel_scan=threading.Event(),
            _on_appearance_change=MagicMock(),
            destroy=MagicMock(),
        )
        FileOrganizerApp._on_closing(app)
        FileOrganizerApp._on_closing(app)
        self.assertTrue(app._is_closing)
        self.assertTrue(app._cancel_scan.is_set())
        app.destroy.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
