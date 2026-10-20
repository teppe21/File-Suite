"""Small shared widgets: button styles and cards."""

from __future__ import annotations

import customtkinter as ctk

from ui import theme as t


def _button(master, text, command, small, fg, hover, text_color, border, **kw) -> ctk.CTkButton:
    button = ctk.CTkButton(
        master,
        text=text,
        command=command,
        height=kw.pop("height", t.SMALL_BUTTON_HEIGHT if small else t.BUTTON_HEIGHT),
        corner_radius=t.BUTTON_RADIUS,
        font=kw.pop("font", t.font("caption" if small else "body_bold")),
        fg_color=fg,
        hover_color=hover,
        text_color=text_color,
        text_color_disabled=t.TEXT_MUTED,
        border_width=1 if border else 0,
        border_color=border or fg,
        **kw,
    )
    # Colours restored by set_enabled(); CTkButton has no disabled fill colour.
    button.fs_enabled = (fg, border)
    return button


def primary_button(master, text, command=None, small=False, **kw) -> ctk.CTkButton:
    """The one main action of a view (accent fill)."""
    return _button(master, text, command, small, t.ACCENT, t.ACCENT_HOVER, t.ON_ACCENT, None, **kw)


def secondary_button(master, text, command=None, small=False, **kw) -> ctk.CTkButton:
    """Neutral, outlined."""
    return _button(master, text, command, small, "transparent", t.SURFACE_2, t.TEXT, t.BORDER, **kw)


def danger_button(master, text, command=None, small=False, **kw) -> ctk.CTkButton:
    """Destructive but visually secondary: danger-coloured outline and text."""
    return _button(master, text, command, small, "transparent", t.DANGER_SOFT, t.DANGER, t.DANGER, **kw)


def set_enabled(button: ctk.CTkButton, enabled: bool) -> None:
    """Enable/disable a helper button and make the disabled state visible."""
    fg, border = button.fs_enabled
    if enabled:
        button.configure(state="normal", fg_color=fg, border_color=border or fg)
    else:
        disabled_fg = t.SURFACE_2 if fg != "transparent" else fg
        button.configure(state="disabled", fg_color=disabled_fg, border_color=t.BORDER if border else disabled_fg)


class Card(ctk.CTkFrame):
    """Surface frame with a title, an optional subtitle and a ``body`` frame for content."""

    def __init__(self, master, title: str | None = None, subtitle: str | None = None, **kw):
        super().__init__(
            master,
            fg_color=t.SURFACE,
            corner_radius=t.CARD_RADIUS,
            border_width=1,
            border_color=t.BORDER,
            **kw,
        )
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.grid_columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(
            self.header, text=title or "", font=t.font("section"), text_color=t.TEXT, anchor="w"
        )
        self.title_label.grid(row=0, column=0, sticky="w")
        self.subtitle_label = ctk.CTkLabel(
            self.header, text=subtitle or "", font=t.font("caption"), text_color=t.TEXT_MUTED, anchor="w"
        )
        if subtitle:
            self.subtitle_label.grid(row=1, column=0, sticky="w")
        if title:
            self.header.grid(row=0, column=0, padx=2 * t.SPACE, pady=(12, t.SPACE), sticky="ew")

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(
            row=1, column=0, padx=2 * t.SPACE, pady=(0 if title else 2 * t.SPACE, 2 * t.SPACE), sticky="nsew"
        )
        self.body.grid_columnconfigure(0, weight=1)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.configure(text=text)
        if text:
            self.subtitle_label.grid(row=1, column=0, sticky="w")
        else:
            self.subtitle_label.grid_remove()


def view_header(master, title: str, description: str) -> ctk.CTkFrame:
    """Title plus a one-sentence description at the top of a view."""
    frame = ctk.CTkFrame(master, fg_color="transparent")
    ctk.CTkLabel(frame, text=title, font=t.font("title"), text_color=t.TEXT, anchor="w").pack(anchor="w")
    ctk.CTkLabel(
        frame, text=description, font=t.font("body"), text_color=t.TEXT_MUTED, anchor="w"
    ).pack(anchor="w")
    return frame


class Banner(ctk.CTkFrame):
    """
    Inline, dismissible message inside a view (replaces post-operation message boxes).
    Grid it once, then call show()/hide(); it starts hidden.
    """

    _KIND_COLORS = {"info": t.ACCENT_TEXT, "success": t.SUCCESS, "warning": t.WARNING, "error": t.DANGER}

    def __init__(self, master):
        super().__init__(master, fg_color=t.SURFACE, corner_radius=t.CARD_RADIUS, border_width=2)
        self.grid_columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(self, text="", font=t.font("body_bold"), anchor="w", justify="left")
        self.title_label.grid(row=0, column=0, padx=(2 * t.SPACE, t.SPACE), pady=(12, 0), sticky="ew")
        self.text_label = ctk.CTkLabel(
            self, text="", font=t.font("caption"), text_color=t.TEXT, anchor="w", justify="left"
        )
        self.text_label.grid(row=1, column=0, padx=(2 * t.SPACE, t.SPACE), pady=(0, 12), sticky="ew")
        self.action_button = secondary_button(self, "", small=True)
        self.action_button.grid(row=0, column=1, rowspan=2, padx=t.SPACE)
        ctk.CTkButton(
            self,
            text="✕",
            width=30,
            height=30,
            corner_radius=t.BUTTON_RADIUS,
            font=t.font("body"),
            fg_color="transparent",
            hover_color=t.SURFACE_2,
            text_color=t.TEXT_MUTED,
            command=self.hide,
        ).grid(row=0, column=2, rowspan=2, padx=(0, t.SPACE))
        self.bind("<Configure>", self._rewrap)

    def _rewrap(self, event):
        # Keep long texts inside the banner; leave room for the buttons.
        self.text_label.configure(wraplength=max(200, event.width - 220))

    def show(self, kind: str, title: str, text: str = "", action: tuple[str, object] | None = None):
        color = self._KIND_COLORS[kind]
        self.configure(border_color=color)
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
        self.text_label.pack(pady=(4, 0))
        if button_text:
            primary_button(inner, button_text, command).pack(pady=(2 * t.SPACE, 0))

    def set(self, title: str, text: str = ""):
        self.title_label.configure(text=title)
        self.text_label.configure(text=text)
