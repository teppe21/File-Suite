"""
GUI tests for the macOS port: they build the real window, so they run only on
macOS with a window server (the CI runners have one) and are skipped elsewhere.

Key presses are real ``NSEvent`` key-down events handed to ``NSApp.sendEvent_``,
the same entry point the window server uses, so Tk's key handling and the Cocoa
menu bar both see them. Everything that closes the app runs in a subprocess.
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
ON_MACOS = sys.platform == "darwin"
REAL_APPEARANCE = ON_MACOS and os.environ.get("FILESUITE_REAL_APPEARANCE_TEST") == "1"

# Handlers the window-wide shortcuts call. They are replaced before the window is
# built (the bindings keep the bound method), so a key press can be observed.
_RECORDED = (
    "select_folder",
    "execute_undo",
    "_move_shortcut",
    "_run_shortcut",
    "_on_closing",
    "trash_selected_duplicates",
)

# ANSI key codes
KEY_O, KEY_Z, KEY_M, KEY_W, KEY_1, KEY_2, KEY_3 = 31, 6, 46, 13, 18, 19, 20
KEY_RETURN, KEY_BACKSPACE, KEY_FORWARD_DELETE, KEY_PERIOD, KEY_A = 36, 51, 117, 47, 0

_state: dict = {}


def _probe(message: str):
    """Facts for the CI log; stderr, so a crash cannot swallow buffered output."""
    print(message, file=sys.stderr, flush=True)


def _fail_or_skip(message: str):
    """A CI runner always has a window server: missing one is a failure there."""
    if os.environ.get("CI"):
        raise RuntimeError(message)
    raise unittest.SkipTest(message)


def setUpModule():
    if not ON_MACOS:
        raise unittest.SkipTest("macOS only")
    try:
        import tkinter
    except ImportError as exc:
        _fail_or_skip(f"no Tk in this Python: {exc}")

    # Imported only here, so the other platforms never need pyobjc or Tk.
    import AppKit

    import ui.app as ui_app
    from ui import widgets

    texts: list = []
    real_init = widgets.Tooltip.__init__

    def spy(self, widget, text):
        texts.append(text)
        real_init(self, widget, text)

    patches = [patch.object(widgets.Tooltip, "__init__", spy)]
    mocks = {}
    for name in _RECORDED:
        mocks[name] = MagicMock(name=name)
        patches.append(patch.object(ui_app.FileOrganizerApp, name, mocks[name]))
    for p in patches:
        p.start()
    printed = io.StringIO()
    try:
        # One Tk root per process: a second one after a destroyed first aborts on key events.
        with contextlib.redirect_stdout(printed):
            app = ui_app.FileOrganizerApp()
    except tkinter.TclError as exc:
        for p in patches:
            p.stop()
        _fail_or_skip(f"no window server: {exc}")
    app.update()
    _state.update(app=app, mocks=mocks, texts=texts, printed=printed.getvalue(), patches=patches, AppKit=AppKit)


def tearDownModule():
    for p in _state.get("patches", ()):
        p.stop()
    app = _state.get("app")
    if app is not None:
        app.destroy()


def _app():
    return _state["app"]


def _window():
    appkit = _state["AppKit"]
    window = appkit.NSApp.keyWindow()
    if window is None:
        window = next(w for w in appkit.NSApp.windows() if w.isVisible())
    return window


def _activate():
    """Make the Tk window the key window of the foreground app."""
    appkit = _state["AppKit"]
    appkit.NSApp.activateIgnoringOtherApps_(True)
    _window().makeKeyAndOrderFront_(None)
    _app().lift()
    _app().focus_force()
    _app().update()


def press(chars: str, keycode: int, command: bool = True, widget=None):
    """Send one key press (down and up) to the app, as the window server would."""
    appkit = _state["AppKit"]
    import Foundation

    _activate()
    if widget is not None:
        widget.focus_force()
        _app().update()
    flags = appkit.NSEventModifierFlagCommand if command else 0
    window_number = _window().windowNumber()
    for kind in (appkit.NSEventTypeKeyDown, appkit.NSEventTypeKeyUp):
        event = appkit.NSEvent.keyEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_(
            kind,
            Foundation.NSMakePoint(0, 0),
            flags,
            Foundation.NSProcessInfo.processInfo().systemUptime(),
            window_number,
            None,
            chars,
            chars,
            False,
            keycode,
        )
        appkit.NSApp.sendEvent_(event)
    _app().update()


def calls(name: str) -> int:
    return _state["mocks"][name].call_count


def run_app_script(body: str) -> subprocess.CompletedProcess:
    """Run a script that builds its own app, so closing it cannot affect this process."""
    prelude = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, %r)
        from pathlib import Path
        from AppKit import NSApp
        import ui.app as ui_app
        """
    ) % str(ROOT)
    return subprocess.run(
        [sys.executable, "-c", prelude + textwrap.dedent(body)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )


class WindowTests(unittest.TestCase):
    def test_icon_loads_without_a_warning(self):
        self.assertNotIn("Could not load window icon", _state["printed"])
        self.assertTrue(hasattr(_app(), "icon_image"))

    def test_tooltips_show_command_glyphs(self):
        shown = {t for t in _state["texts"] if isinstance(t, str)}
        for expected in (
            "Choose another folder  (⌘O)",
            "⌘1",
            "⌘3",
            "Compare every file directly in this folder. Nothing changes.  (⌘↩)",
            "Show what would move. Nothing changes yet.  (⌘↩)",
        ):
            self.assertIn(expected, shown)
        self.assertFalse([t for t in shown if "Ctrl" in t])

    def test_quit_command_is_registered(self):
        commands = _app().tk.call("info", "commands", "::tk::mac::Quit")
        self.assertIn("tk::mac::Quit", str(commands))

    def test_restore_hint_says_finder(self):
        view = _app().duplicates
        view.report_trash(1, 0, 0, False)
        self.assertEqual(
            view.banner.text_label.cget("text"), "Restore them from the Trash in Finder if needed."
        )
        with patch("ui.duplicates_view.IS_MACOS", False):  # the other platforms' wording
            view.report_trash(1, 0, 0, False)
        self.assertEqual(
            view.banner.text_label.cget("text"),
            "Restore them from the Trash in your file manager if needed.",
        )


class FontTests(unittest.TestCase):
    def test_fonts_resolve_to_the_system_font(self):
        import tkinter.font as tkfont

        from ui import theme as t

        default = tkfont.nametofont("TkDefaultFont")
        _probe(f"[probe] TkDefaultFont {default.actual()} linespace={default.metrics('linespace')}")
        for role in ("title", "section", "headline", "body", "caption", "caption_bold"):
            ctk_font = t.font(role)
            actual = ctk_font.actual()
            _probe(f"[probe] font {role}: configured={ctk_font.cget('family')!r} {actual}")
            self.assertEqual(actual["family"], default.actual("family"), role)
        for role in ("body", "headline", "caption"):
            tree_font = t.tree_font(role)
            _probe(f"[probe] tree {role}: {tree_font.actual()} linespace={tree_font.metrics('linespace')}")
            self.assertEqual(tree_font.actual("family"), default.actual("family"), role)
        self.assertEqual(t.font("headline").actual("weight"), "bold")
        self.assertEqual(t.font("body").actual("weight"), "normal")

    def test_row_height_fits_the_text(self):
        from tkinter import ttk

        from ui import theme as t

        row = int(ttk.Style(_app()).lookup("Treeview", "rowheight"))
        line = t.tree_font("body").metrics("linespace")
        _probe(f"[probe] rowheight={row} linespace={line} tk scaling={_app().tk.call('tk', 'scaling')}")
        self.assertGreater(row, line)


class AppearanceTests(unittest.TestCase):
    def tearDown(self):
        import customtkinter as ctk

        ctk.set_appearance_mode("System")
        _app().update()

    def _surface(self):
        from tkinter import ttk

        return ttk.Style(_app()).lookup("Treeview", "background")

    def test_tree_is_restyled_when_the_mode_changes(self):
        import customtkinter as ctk

        from ui import theme as t

        ctk.set_appearance_mode("Dark")
        _app().update()
        self.assertEqual(self._surface(), t.SURFACE[1])
        ctk.set_appearance_mode("Light")
        _app().update()
        self.assertEqual(self._surface(), t.SURFACE[0])

    @unittest.skipUnless(REAL_APPEARANCE, "set FILESUITE_REAL_APPEARANCE_TEST=1 to flip the system appearance")
    def test_follows_the_system_appearance_live(self):
        import time

        import customtkinter as ctk

        from ui import theme as t

        ctk.set_appearance_mode("System")
        self.addCleanup(subprocess.run, ["defaults", "delete", "-g", "AppleInterfaceStyle"], check=False)
        subprocess.run(["defaults", "write", "-g", "AppleInterfaceStyle", "Dark"], check=True)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and ctk.get_appearance_mode() != "Dark":
            _app().update()
            time.sleep(0.05)
        _probe(f"[probe] after switching macOS to Dark: ctk mode={ctk.get_appearance_mode()} tree={self._surface()}")
        self.assertEqual(ctk.get_appearance_mode(), "Dark")
        self.assertEqual(self._surface(), t.SURFACE[1])


class ShortcutKeyTests(unittest.TestCase):
    """Real key events: window-wide shortcuts, the Cocoa menu bar and Tk's own editing keys."""

    def setUp(self):
        for mock in _state["mocks"].values():
            mock.reset_mock()
        _app().show_view("organize")

    def test_cmd_o_chooses_a_folder(self):
        press("o", KEY_O)
        self.assertEqual(calls("select_folder"), 1)

    def test_cmd_z_undoes(self):
        press("z", KEY_Z)
        self.assertEqual(calls("execute_undo"), 1)

    def test_cmd_return_runs_the_view_action(self):
        press("\r", KEY_RETURN)
        self.assertEqual(calls("_run_shortcut"), 1)

    def test_cmd_1_2_3_switch_views(self):
        press("2", KEY_2)
        self.assertEqual(_app().current_view, "duplicates")
        press("3", KEY_3)
        self.assertEqual(_app().current_view, "activity")
        press("1", KEY_1)
        self.assertEqual(_app().current_view, "organize")

    def test_cmd_w_closes(self):
        press("w", KEY_W)
        _probe(f"[probe] Cmd+W -> _on_closing called {calls('_on_closing')}x")
        self.assertGreaterEqual(calls("_on_closing"), 1)

    def test_cmd_m(self):
        window = _window()
        press("m", KEY_M)
        for _ in range(20):
            _app().update()
            if window.isMiniaturized():
                break
            _state["AppKit"].NSRunLoop.currentRunLoop().runUntilDate_(
                _state["AppKit"].NSDate.dateWithTimeIntervalSinceNow_(0.1)
            )
        minimized = window.isMiniaturized()
        _probe(f"[probe] Cmd+M -> _move_shortcut called {calls('_move_shortcut')}x, window minimized={minimized}")
        if minimized:
            window.deminiaturize_(None)
            _app().update()

    def test_delete_keys_trash_in_the_duplicates_list(self):
        _app().show_view("duplicates")
        tree = _app().duplicates.tree
        for chars, keycode, command in (
            ("\x7f", KEY_BACKSPACE, False),  # the Mac "delete" key
            ("\x7f", KEY_BACKSPACE, True),  # Cmd+Delete, Finder's Move to Trash
            ("", KEY_FORWARD_DELETE, False),
        ):
            _state["mocks"]["trash_selected_duplicates"].reset_mock()
            press(chars, keycode, command=command, widget=tree)
            self.assertEqual(calls("trash_selected_duplicates"), 1, (keycode, command))

    def test_rule_entries_keep_their_editing_keys(self):
        field = _find_entry(_app().organize)
        field.delete(0, "end")
        field.insert(0, "abc")
        press("a", KEY_A, widget=field)
        _probe(f"[probe] Cmd+A in entry -> selection_present={field.selection_present()}")
        self.assertTrue(field.selection_present())
        press("z", KEY_Z, widget=field)
        _probe(f"[probe] Cmd+Z in entry -> execute_undo called {calls('execute_undo')}x, text={field.get()!r}")


def _find_entry(widget):
    import tkinter

    for child in widget.winfo_children():
        if isinstance(child, tkinter.Entry):
            return child
        found = _find_entry(child)
        if found is not None:
            return found
    return None


class QuitTests(unittest.TestCase):
    """Cmd+Q is ``NSApp.terminate:``; Tk turns it into the ``::tk::mac::Quit`` command."""

    def test_quit_cancels_a_running_scan_and_exits(self):
        result = run_app_script(
            """
            import tempfile, threading
            seen = threading.Event()

            def fake_scan(target_dir, cancel_event, on_progress):
                if cancel_event.wait(20):
                    seen.set()
                return []

            ui_app.scan_duplicates = fake_scan
            app = ui_app.FileOrganizerApp()
            with tempfile.TemporaryDirectory() as tmp:
                app.current_path = Path(tmp)
                app.update()
                app.start_duplicate_scan()
                app.after(600, lambda: NSApp.terminate_(None))
                app.mainloop()
            print("RESULT closing=%s worker_cancelled=%s" % (app._is_closing, seen.wait(5)))
            """
        )
        _probe(f"[probe] quit during scan: rc={result.returncode} out={result.stdout[-300:]!r} err={result.stderr[-300:]!r}")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RESULT closing=True worker_cancelled=True", result.stdout)

    def test_quit_while_a_confirmation_is_open_leaves_no_traceback(self):
        result = run_app_script(
            """
            from ui.widgets import confirm_dialog
            app = ui_app.FileOrganizerApp()
            app.update()
            app.after(600, lambda: NSApp.terminate_(None))
            answer = confirm_dialog(app, "Title", "Message", confirm_text="Do it")
            print("RESULT answer=%s closing=%s" % (answer, app._is_closing))
            """
        )
        _probe(f"[probe] quit with dialog: rc={result.returncode} out={result.stdout[-300:]!r} err={result.stderr[-300:]!r}")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RESULT answer=False closing=True", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_closing_twice_is_safe(self):
        result = run_app_script(
            """
            app = ui_app.FileOrganizerApp()
            app.update()
            app._on_closing()
            app._on_closing()
            print("RESULT twice ok")
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RESULT twice ok", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
