"""
GUI tests for the macOS port: they build the real window, so they run only on
macOS with a window server (the CI runners have one) and are skipped elsewhere.

Key presses are real ``NSEvent`` key events put on the application's event
queue, which is where the window server's events arrive: Tk's event loop takes
them off the queue and the Cocoa menu bar sees them afterwards, as for a real
key. (``NSApp.sendEvent_`` would skip Tk.) Everything that closes the app runs
in a subprocess.
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import textwrap
import time
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

def _letter_keycodes() -> dict[str, int]:
    """
    Key code of each unshifted character in the keyboard layout in use, or ``{}``
    if it cannot be read. Tk 9 turns a key code into a keysym through the layout,
    so a hard-coded US code types ``y`` instead of ``z`` on a Hungarian or German keyboard.
    """
    if not ON_MACOS:
        return {}
    import ctypes
    import ctypes.util

    try:
        carbon = ctypes.CDLL(ctypes.util.find_library("Carbon"))
        core = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
        carbon.TISCopyCurrentASCIICapableKeyboardLayoutInputSource.restype = ctypes.c_void_p
        carbon.TISGetInputSourceProperty.restype = ctypes.c_void_p
        carbon.TISGetInputSourceProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        carbon.LMGetKbdType.restype = ctypes.c_ubyte
        carbon.UCKeyTranslate.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint16,
            ctypes.c_uint16,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_uint16),
        ]
        core.CFDataGetBytePtr.restype = ctypes.c_void_p
        core.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
        source = carbon.TISCopyCurrentASCIICapableKeyboardLayoutInputSource()
        data = carbon.TISGetInputSourceProperty(source, ctypes.c_void_p.in_dll(carbon, "kTISPropertyUnicodeKeyLayoutData"))
        layout = core.CFDataGetBytePtr(data)
        keyboard_type = carbon.LMGetKbdType()
        codes: dict[str, int] = {}
        for keycode in range(128):
            dead_keys = ctypes.c_uint32(0)
            length = ctypes.c_ulong(0)
            chars = (ctypes.c_uint16 * 4)()
            # Action 0 (key down), no modifiers, dead keys off (option bit 0).
            status = carbon.UCKeyTranslate(layout, keycode, 0, 0, keyboard_type, 1, ctypes.byref(dead_keys), 4, ctypes.byref(length), chars)
            if status == 0 and length.value == 1:
                codes.setdefault(chr(chars[0]), keycode)
        return codes
    except (OSError, AttributeError, ValueError):
        return {}


_LAYOUT = _letter_keycodes()


def _letter_key(char: str, ansi_code: int) -> int:
    """The key that types ``char`` here; the US code if the layout is unknown."""
    return _LAYOUT.get(char, ansi_code)


# Letter keys follow the keyboard layout; the others are the same on every layout.
KEY_O, KEY_Z, KEY_M, KEY_W, KEY_A = (_letter_key(c, code) for c, code in (("o", 31), ("z", 6), ("m", 46), ("w", 13), ("a", 0)))
KEY_1, KEY_2, KEY_3 = 18, 19, 20
KEY_RETURN, KEY_BACKSPACE, KEY_FORWARD_DELETE, KEY_PERIOD, KEY_ESCAPE = 36, 51, 117, 47, 53

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
        window = next(w for w in appkit.NSApp.windows() if w.isVisible() or w.isMiniaturized())
    return window


def _activate():
    """
    Bring the app to the front through Tk. AppKit calls that make Tk run Python
    callbacks (such as ``makeKeyAndOrderFront_``) abort the interpreter from here.
    """
    _state["AppKit"].NSApp.activateIgnoringOtherApps_(True)
    _app().lift()
    _app().focus_force()
    _app().update()


def modifier_flags(command: bool = False, shift: bool = False) -> int:
    import AppKit

    return (AppKit.NSEventModifierFlagCommand if command else 0) | (
        AppKit.NSEventModifierFlagShift if shift else 0
    )


def post_key(chars: str, keycode: int, flags: int = 0, window_number: int | None = None):
    """Queue a key down and up for the key window; Tk takes them off the queue as it runs."""
    import AppKit
    import Foundation

    if window_number is None:
        window_number = AppKit.NSApp.keyWindow().windowNumber()
    for kind in (AppKit.NSEventTypeKeyDown, AppKit.NSEventTypeKeyUp):
        event = AppKit.NSEvent.keyEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_(
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
        AppKit.NSApp.postEvent_atStart_(event, False)


def press(chars: str, keycode: int, command: bool = True, shift: bool = False, widget=None):
    """Send one key press to the app the way the window server does, and let Tk handle it."""
    _activate()
    if widget is not None:
        widget.focus_force()
        _app().update()
    post_key(chars, keycode, modifier_flags(command, shift), _window().windowNumber())
    for _ in range(10):
        _app().update()
        time.sleep(0.02)


def calls(name: str) -> int:
    return _state["mocks"][name].call_count


def run_app_script(body: str) -> subprocess.CompletedProcess:
    """Run a script that builds its own app, so closing it cannot affect this process."""
    prelude = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, %r)
        sys.path.insert(0, %r)
        from pathlib import Path
        from AppKit import NSApp
        import test_macos_gui as keys
        import ui.app as ui_app
        """
    ) % (str(ROOT), str(ROOT / "tests"))
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
            "Move the previewed files into their folders. You can undo this.  (⇧⌘M)",
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

    def test_shift_cmd_m_moves(self):
        press("M", KEY_M, shift=True)
        self.assertEqual(calls("_move_shortcut"), 1)
        self.assertNotEqual(_app().state(), "iconic")

    def test_z_cmd_m_only_minimizes(self):
        """Last of the key tests: it minimizes the window. Plain Cmd+M must not also move files."""
        press("m", KEY_M)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and _app().state() != "iconic":
            _app().update()
            time.sleep(0.05)
        _probe(f"[probe] Cmd+M -> window state={_app().state()}, _move_shortcut called {calls('_move_shortcut')}x")
        _app().deiconify()
        _app().update()
        self.assertEqual(calls("_move_shortcut"), 0)

    def test_delete_keys_trash_in_the_duplicates_list(self):
        from models import DuplicateFile, DuplicateGroup

        app = _app()
        files = [
            DuplicateFile(Path("/tmp/a.txt"), 5, is_original=True),
            DuplicateFile(Path("/tmp/b.txt"), 5, selected=True),
        ]
        app.duplicate_groups = [DuplicateGroup("g", "0" * 64, 5, files)]
        app.duplicates.render_groups()  # the list is only on screen when there are results
        self.addCleanup(self._clear_results)
        app.show_view("duplicates")
        app.update()
        tree = app.duplicates.tree
        for chars, keycode, command in (
            ("\x7f", KEY_BACKSPACE, False),  # the Mac "delete" key
            ("\x7f", KEY_BACKSPACE, True),  # Cmd+Delete, Finder's Move to Trash
            ("\uf728", KEY_FORWARD_DELETE, False),
        ):
            _state["mocks"]["trash_selected_duplicates"].reset_mock()
            press(chars, keycode, command=command, widget=tree)
            self.assertEqual(calls("trash_selected_duplicates"), 1, (keycode, command))

    @staticmethod
    def _clear_results():
        _app().duplicate_groups = []
        _app().duplicates.render_groups()

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


class DialogTests(unittest.TestCase):
    """The confirmation dialog on this Tk (Tk 8.6.12 of Python 3.10 lacks the ISO_Left_Tab keysym)."""

    def _assert_cancelled_by(self, chars: str, keycode: int, command: bool):
        result = run_app_script(
            f"""
            from ui.widgets import confirm_dialog
            app = ui_app.FileOrganizerApp()
            app.update()
            app.after(700, lambda: keys.post_key({chars!r}, {keycode}, keys.modifier_flags(command={command})))
            app.after(8000, lambda: (print("TIMEOUT"), app.destroy()))
            answer = confirm_dialog(app, "Title", "Message", confirm_text="Do it")
            print("RESULT answer=%s" % answer)
            """
        )
        _probe(f"[probe] dialog key {keycode}: rc={result.returncode} out={result.stdout[-120:]!r} err={result.stderr[-300:]!r}")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("TIMEOUT", result.stdout)
        self.assertIn("RESULT answer=False", result.stdout)

    def test_escape_cancels(self):
        self._assert_cancelled_by("\x1b", KEY_ESCAPE, command=False)

    def test_cmd_period_cancels(self):
        self._assert_cancelled_by(".", KEY_PERIOD, command=True)


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
