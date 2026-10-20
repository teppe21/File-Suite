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
            self.header.grid(row=0, column=0, padx=2 * t.SPACE, pady=(2 * t.SPACE, t.SPACE), sticky="ew")

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
