"""Small shared widgets: buttons, fields, groups, banners, tooltips and dialogs."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ui import theme as t

# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------


def _button(master, text, command, small, fg, hover, pressed, text_color, **kw) -> ctk.CTkButton:
    fg = kw.pop("fg_color", fg)  # e.g. a lighter fill on the grey sidebar
    button = ctk.CTkButton(
        master,
        text=text,
        command=command,
        height=kw.pop("height", t.SMALL_BUTTON_HEIGHT if small else t.BUTTON_HEIGHT),
        width=kw.pop("width", 0),  # size to the label
        corner_radius=t.BUTTON_RADIUS,
        font=kw.pop("font", t.font("caption" if small else "body")),
        fg_color=fg,
        hover_color=hover,
        text_color=text_color,
        text_color_disabled=t.TEXT_MUTED,
        border_width=0,
        **kw,
    )
    # Current style (fill, pressed fill); CTkButton has no disabled or pressed fill colour.
    button.fs_style = (fg, pressed)

    # Feedback the instant the pointer goes down, not after the click completes.
    def press(_event):
        if button.cget("state") == "normal":
            button.configure(fg_color=button.fs_style[1])

    def release(_event):
        if button.winfo_exists() and button.cget("state") == "normal":
            button.configure(fg_color=button.fs_style[0])

    button.bind("<ButtonPress-1>", press, add="+")
    button.bind("<ButtonRelease-1>", release, add="+")
    return button


_PRIMARY = (t.ACCENT, t.ACCENT_HOVER, t.ACCENT_PRESSED, t.ON_ACCENT)
_NEUTRAL = (t.NEUTRAL, t.NEUTRAL_HOVER, t.NEUTRAL_PRESSED, t.TEXT)


def primary_button(master, text, command=None, small=False, **kw) -> ctk.CTkButton:
    """The default action of a view: accent fill, one per view."""
    return _button(master, text, command, small, *_PRIMARY, **kw)


def secondary_button(master, text, command=None, small=False, **kw) -> ctk.CTkButton:
    """Neutral fill, for everything that is not the default action."""
    return _button(master, text, command, small, *_NEUTRAL, **kw)


def danger_button(master, text, command=None, small=False, **kw) -> ctk.CTkButton:
    """Destructive: neutral fill with red text, so it never outshines the default action."""
    return _button(master, text, command, small, t.NEUTRAL, t.NEUTRAL_HOVER, t.NEUTRAL_PRESSED, t.DANGER, **kw)


def set_enabled(button: ctk.CTkButton, enabled: bool) -> None:
    """Enable/disable a helper button; a disabled accent button turns neutral."""
    if enabled:
        button.configure(state="normal", fg_color=button.fs_style[0])
    else:
        button.configure(state="disabled", fg_color=t.NEUTRAL)


def set_default(button: ctk.CTkButton, is_default: bool) -> None:
    """Switch a button between the accent (default action) and neutral styles."""
    fg, hover, pressed, text = _PRIMARY if is_default else _NEUTRAL
    button.fs_style = (fg, pressed)
    button.configure(hover_color=hover, text_color=text)
    if button.cget("state") == "normal":
        button.configure(fg_color=fg)


def scrollbar(master, widget) -> ctk.CTkScrollbar:
    """Slim scrollbar wired to a Treeview or Text."""
    bar = ctk.CTkScrollbar(
        master,
        command=widget.yview,
        width=12,
        fg_color="transparent",
        button_color=t.FIELD_BORDER,
        button_hover_color=t.TEXT_MUTED,
    )
    widget.configure(yscrollcommand=bar.set)
    return bar


def segmented(master, values: list[str], command) -> ctk.CTkSegmentedButton:
    """Native-style segmented control: a light pill marks the chosen segment."""
    return ctk.CTkSegmentedButton(
        master,
        values=values,
        command=command,
        height=t.SMALL_BUTTON_HEIGHT - 2,
        corner_radius=t.BUTTON_RADIUS,
        border_width=2,
        font=t.font("caption"),
        fg_color=t.NEUTRAL,
        selected_color=t.SEGMENT_SELECTED,
        selected_hover_color=t.SEGMENT_SELECTED,
        unselected_color=t.NEUTRAL,
        unselected_hover_color=t.NEUTRAL_HOVER,
        text_color=t.TEXT,
    )


def text_field(master, variable) -> ctk.CTkEntry:
    """Single-line input with an accent focus ring."""
    entry = ctk.CTkEntry(
        master,
        textvariable=variable,
        height=t.BUTTON_HEIGHT,
        corner_radius=t.BUTTON_RADIUS,
        border_width=1,
        border_color=t.FIELD_BORDER,
        fg_color=t.FIELD,
        text_color=t.TEXT,
        font=t.font("body"),
    )
    entry.bind("<FocusIn>", lambda _e: entry.configure(border_color=t.ACCENT, border_width=2))
    entry.bind("<FocusOut>", lambda _e: entry.configure(border_color=t.FIELD_BORDER, border_width=1))
    return entry


# ---------------------------------------------------------------------------
# Tooltip (shortcuts and longer explanations live here, not on screen)
# ---------------------------------------------------------------------------


class Tooltip:
    """Small delayed tooltip. ``text`` may be a string or a function returning one."""

    DELAY_MS = 600

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self._after = None
        self._tip: tk.Toplevel | None = None
        add = "+" if isinstance(widget, ctk.CTkBaseClass) else True
        widget.bind("<Enter>", self._schedule, add=add)
        widget.bind("<Leave>", self._hide, add=add)
        widget.bind("<ButtonPress>", self._hide, add=add)

    def _schedule(self, _event=None):
        self._cancel()
        self._after = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self):
        if self._after:
            self.widget.after_cancel(self._after)
            self._after = None

    def _show(self):
        text = self.text() if callable(self.text) else self.text
        if not text or not self.widget.winfo_exists():
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        frame = tk.Frame(tip, bg=t.pick(t.FIELD_BORDER), padx=1, pady=1)  # hairline border
        frame.pack()
        tk.Label(
            frame,
            text=text,
            justify="left",
            bg=t.pick(t.SURFACE),
            fg=t.pick(t.TEXT),
            font=t.tree_font("caption"),
            padx=8,
            pady=4,
            wraplength=320,
        ).pack()
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide(self, _event=None):
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


def tooltip(widget, text) -> Tooltip:
    return Tooltip(widget, text)


# ---------------------------------------------------------------------------
# Containers and messages
# ---------------------------------------------------------------------------


class Card(ctk.CTkFrame):
    """Grouped content on a white surface with a hairline edge: optional ``header`` row and a ``body``."""

    def __init__(self, master, title: str | None = None, **kw):
        super().__init__(
            master,
            fg_color=t.SURFACE,
            corner_radius=t.CARD_RADIUS,
            border_width=1,
            border_color=t.SEPARATOR,
            **kw,
        )
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.grid_columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(
            self.header, text=title or "", font=t.font("headline"), text_color=t.TEXT, anchor="w"
        )
        self.title_label.grid(row=0, column=0, sticky="w")
        if title:
            self.header.grid(row=0, column=0, padx=2 * t.SPACE, pady=(12, 4), sticky="ew")

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, padx=2 * t.SPACE, pady=(0 if title else 12, 12), sticky="nsew")
        self.body.grid_columnconfigure(0, weight=1)


class Banner(ctk.CTkFrame):
    """
    Inline, dismissible message inside a view (replaces post-operation message boxes).
    Grid it once, then call show()/hide(); it starts hidden.
    """

    _KINDS = {
        "info": (t.ACCENT_TEXT, t.INFO_TINT),
        "success": (t.SUCCESS, t.SUCCESS_TINT),
        "warning": (t.WARNING, t.WARNING_TINT),
        "error": (t.DANGER, t.DANGER_TINT),
    }

    def __init__(self, master):
        super().__init__(master, corner_radius=t.CARD_RADIUS, border_width=0)
        self.grid_columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(self, text="", font=t.font("headline"), anchor="w", justify="left")
        self.title_label.grid(row=0, column=0, padx=(2 * t.SPACE, t.SPACE), pady=(10, 0), sticky="ew")
        self.text_label = ctk.CTkLabel(
            self, text="", font=t.font("caption"), text_color=t.TEXT, anchor="w", justify="left"
        )
        self.text_label.grid(row=1, column=0, padx=(2 * t.SPACE, t.SPACE), pady=(0, 10), sticky="ew")
        self.action_button = secondary_button(self, "", small=True)
        self.action_button.grid(row=0, column=1, rowspan=2, padx=t.SPACE)
        close = ctk.CTkButton(
            self,
            text="✕",
            width=26,
            height=26,
            corner_radius=t.BUTTON_RADIUS,
            font=t.font("caption"),
            fg_color="transparent",
            hover_color=t.NEUTRAL_HOVER,
            text_color=t.TEXT_MUTED,
            command=self.hide,
        )
        close.grid(row=0, column=2, rowspan=2, padx=(0, t.SPACE))
        tooltip(close, "Dismiss")
        self.bind("<Configure>", self._rewrap)

    def _rewrap(self, event):
        # Keep long texts inside the banner; leave room for the buttons.
        self.text_label.configure(wraplength=max(200, event.width - 220))

    def show(self, kind: str, title: str, text: str = "", action: tuple[str, object] | None = None):
        color, tint = self._KINDS[kind]
        self.configure(fg_color=tint)
        self.title_label.configure(text=title, text_color=color)
        self.text_label.configure(text=text)
        if text:
            self.text_label.grid()
        else:
            self.text_label.grid_remove()
        if action:
            self.action_button.configure(text=action[0], command=action[1])
            self.action_button.grid()
        else:
            self.action_button.grid_remove()
        self.grid()

    def hide(self):
        self.grid_remove()


class EmptyState(ctk.CTkFrame):
    """Centred message with an optional button that resolves it."""

    def __init__(self, master, button_text: str | None = None, command=None):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure((0, 2), weight=1)
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.grid(row=1, column=0)
        self.title_label = ctk.CTkLabel(inner, text="", font=t.font("section"), text_color=t.TEXT)
        self.title_label.pack()
        self.text_label = ctk.CTkLabel(
            inner, text="", font=t.font("body"), text_color=t.TEXT_MUTED, wraplength=420, justify="center"
        )
        self.text_label.pack(pady=(2, 0))
        self.button = primary_button(inner, button_text or "", command)
        if button_text:
            self.button.pack(pady=(2 * t.SPACE, 0))

    def set(self, title: str, text: str = "", button_text: str | None = None):
        """Change the message; ``button_text`` relabels the button, an empty string hides it."""
        self.title_label.configure(text=title)
        self.text_label.configure(text=text)
        if button_text:
            self.button.configure(text=button_text)
            self.button.pack(pady=(2 * t.SPACE, 0))
        elif button_text == "":
            self.button.pack_forget()


def hairline(master) -> ctk.CTkFrame:
    """1 px separator."""
    return ctk.CTkFrame(master, height=1, corner_radius=0, fg_color=t.SEPARATOR)


# ---------------------------------------------------------------------------
# Confirmation dialog
# ---------------------------------------------------------------------------


def confirm_dialog(
    parent,
    title: str,
    message: str,
    details: list[tuple[str, str]] = (),
    confirm_text: str = "OK",
    destructive: bool = False,
    warning: str | None = None,
) -> bool:
    """
    Themed modal confirmation. Returns True only when the confirm button is used.
    Esc cancels; Enter/Space press the focused button; Tab or arrows move focus.
    Destructive confirmations start with focus on Cancel.
    """
    previous_focus = parent.focus_get()
    dialog = ctk.CTkToplevel(parent)
    dialog.withdraw()
    dialog.title(title)
    dialog.configure(fg_color=t.SURFACE)
    dialog.resizable(False, False)
    dialog.transient(parent)
    confirmed = False
    pad = t.MARGIN

    ctk.CTkLabel(dialog, text=title, font=t.font("section"), text_color=t.TEXT, anchor="w").pack(
        fill="x", padx=pad, pady=(pad, 4)
    )
    ctk.CTkLabel(
        dialog, text=message, font=t.font("body"), text_color=t.TEXT, anchor="w", justify="left", wraplength=400
    ).pack(fill="x", padx=pad)

    if details:
        grid = ctk.CTkFrame(dialog, fg_color="transparent")
        grid.pack(fill="x", padx=pad, pady=(12, 0))
        for row, (label, value) in enumerate(details):
            ctk.CTkLabel(grid, text=label, font=t.font("body"), text_color=t.TEXT_MUTED, anchor="w").grid(
                row=row, column=0, sticky="nw", padx=(0, 2 * t.SPACE), pady=1
            )
            ctk.CTkLabel(
                grid, text=value, font=t.font("body"), text_color=t.TEXT, anchor="w", justify="left", wraplength=300
            ).grid(row=row, column=1, sticky="w", pady=1)

    if warning:
        ctk.CTkLabel(
            dialog,
            text=warning,
            font=t.font("headline"),
            text_color=t.DANGER,
            anchor="w",
            justify="left",
            wraplength=400,
        ).pack(fill="x", padx=pad, pady=(12, 0))

    def finish(ok: bool):
        nonlocal confirmed
        confirmed = ok
        dialog.grab_release()
        dialog.destroy()

    # Command area: a band at the bottom with the buttons on the right.
    band = ctk.CTkFrame(dialog, fg_color=t.BG, corner_radius=0)
    band.pack(fill="x", pady=(pad, 0))
    make = danger_button if destructive else primary_button
    ok_button = make(band, confirm_text, lambda: finish(True), width=96)
    ok_button.pack(side="right", padx=(0, pad), pady=2 * t.SPACE)
    cancel_button = secondary_button(band, "Cancel", lambda: finish(False), width=96)
    cancel_button.pack(side="right", padx=(0, t.SPACE), pady=2 * t.SPACE)

    order = [cancel_button, ok_button]
    focus = [0 if destructive else 1]

    def show_focus():
        # CTkButtons take no keyboard focus, so draw the focus ring ourselves.
        for idx, button in enumerate(order):
            if idx == focus[0]:
                button.configure(border_width=2, border_color=t.ACCENT_TEXT)
            else:
                button.configure(border_width=0)

    def move_focus(_event=None):
        focus[0] = 1 - focus[0]
        show_focus()
        return "break"

    dialog.bind("<Escape>", lambda _e: finish(False))
    for key in ("<Return>", "<KP_Enter>", "<space>"):
        dialog.bind(key, lambda _e: order[focus[0]].invoke())
    for key in ("<Tab>", "<Shift-Tab>", "<ISO_Left_Tab>", "<Left>", "<Right>"):
        dialog.bind(key, move_focus)
    dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
    show_focus()

    # Centre over the parent window, then make it modal.
    dialog.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - dialog.winfo_reqwidth()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - dialog.winfo_reqheight()) // 3
    dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    dialog.deiconify()
    dialog.wait_visibility()
    dialog.grab_set()
    dialog.focus_force()
    parent.wait_window(dialog)
    # Give keyboard focus back (e.g. to the duplicates tree) so shortcuts keep working.
    target = previous_focus if previous_focus is not None and previous_focus.winfo_exists() else parent
    target.focus_force()
    return confirmed
