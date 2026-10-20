"""
Visual system: colour tokens, type scale, spacing and the ttk.Treeview style.

Colours are CustomTkinter ``(light, dark)`` tuples derived from the app icon.
Values were adjusted from the icon only where WCAG contrast was below 4.5:1.
"""

from __future__ import annotations

import tkinter.font as tkfont
from tkinter import ttk

import customtkinter as ctk

# Surfaces and text
BG = ("#FAF7F2", "#1C1B1A")
SURFACE = ("#FFFFFF", "#262423")  # cards, sidebar, status bar
SURFACE_2 = ("#F2EEE7", "#2E2C2A")  # inputs, tables
BORDER = ("#E3DDD3", "#3A3734")
TEXT = ("#2B2B2B", "#F2EEE7")
TEXT_MUTED = ("#6B6560", "#A39D96")

# Accent = the primary action of a view. White text on it is 4.98:1.
ACCENT = ("#B4532F", "#B4532F")
ACCENT_HOVER = ("#9A4527", "#9A4527")
ACCENT_SOFT = ("#F6E3DA", "#45302A")  # active navigation, selected rows
ACCENT_TEXT = ("#B4532F", "#E58A63")  # accent used as text
ON_ACCENT = "#FFFFFF"

# Results and the destructive action only (used as text/borders, never as a fill
# behind body text, so each has a light and a dark variant).
SUCCESS = ("#2A7046", "#5CB884")
WARNING = ("#8A5A10", "#E3A748")
DANGER = ("#B42318", "#F2867A")
DANGER_SOFT = ("#FBE4E1", "#4A2522")

# Spacing (8 px grid), radii and sizes
SPACE = 8
CARD_RADIUS = 10
BUTTON_RADIUS = 8
BUTTON_HEIGHT = 36
SMALL_BUTTON_HEIGHT = 30
SIDEBAR_WIDTH = 220

# Type scale: role -> (size in px, weight). Nothing below 12.
_TYPE_SCALE = {
    "title": (20, "bold"),
    "section": (15, "bold"),
    "body": (13, "normal"),
    "body_bold": (13, "bold"),
    "caption": (12, "normal"),
}
_fonts: dict[str, ctk.CTkFont] = {}


def font(role: str = "body") -> ctk.CTkFont:
    """Shared CTkFont for a type-scale role (created after the root window exists)."""
    if role not in _fonts:
        size, weight = _TYPE_SCALE[role]
        _fonts[role] = ctk.CTkFont(size=size, weight=weight)
    return _fonts[role]


def pick(token: tuple[str, str] | str) -> str:
    """Resolve a (light, dark) token for widgets that take one colour (ttk, tk.Text tags)."""
    if isinstance(token, str):
        return token
    return token[0] if ctk.get_appearance_mode() == "Light" else token[1]


# ---------------------------------------------------------------------------
# ttk.Treeview
# ---------------------------------------------------------------------------

_tree_fonts: dict[str, tkfont.Font] = {}
# Trees and their tag colours, re-applied on every theme change.
_tree_tags: list[tuple[ttk.Treeview, dict[str, dict]]] = []


def register_tree_tags(tree: ttk.Treeview, tags: dict[str, dict]) -> None:
    """Remember a tree's tags ({tag: {"foreground": TOKEN, ...}}) and apply them now."""
    _tree_tags.append((tree, tags))
    _configure_tags(tree, tags)


def _configure_tags(tree: ttk.Treeview, tags: dict[str, dict]) -> None:
    for tag, options in tags.items():
        resolved = {k: (v if k == "font" else pick(v)) for k, v in options.items()}
        tree.tag_configure(tag, **resolved)


def tree_font(role: str) -> tkfont.Font:
    """A plain Tk font for the tree (ttk does not take CTkFont), sized by apply_treeview_style."""
    if role not in _tree_fonts:
        _tree_fonts[role] = tkfont.Font(family=font().cget("family"))
    return _tree_fonts[role]


def apply_treeview_style(root) -> None:
    """
    Style every ttk.Treeview for the current appearance mode and DPI scaling.
    Uses the "clam" theme because the Windows "vista" theme ignores colours.
    Call at start-up and on every appearance-mode change.
    """
    scaling = ctk.ScalingTracker.get_widget_scaling(root)
    for role in ("body", "body_bold", "caption"):
        size, weight = _TYPE_SCALE[role]
        # Negative size = pixels, scaled like CustomTkinter's own widgets.
        tree_font(role).configure(size=-round(size * scaling), weight=weight)
    row_height = tree_font("body").metrics("linespace") + round(12 * scaling)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        "Treeview",
        background=pick(SURFACE_2),
        fieldbackground=pick(SURFACE_2),
        foreground=pick(TEXT),
        bordercolor=pick(BORDER),
        lightcolor=pick(SURFACE_2),
        darkcolor=pick(SURFACE_2),
        borderwidth=0,
        rowheight=row_height,
        font=tree_font("body"),
        indent=round(18 * scaling),
    )
    style.map(
        "Treeview",
        background=[("selected", pick(ACCENT_SOFT))],
        foreground=[("selected", pick(TEXT))],
    )
    style.configure(
        "Treeview.Heading",
        background=pick(SURFACE),
        foreground=pick(TEXT_MUTED),
        bordercolor=pick(BORDER),
        lightcolor=pick(SURFACE),
        darkcolor=pick(SURFACE),
        relief="flat",
        font=tree_font("caption"),
        padding=(round(8 * scaling), round(6 * scaling)),
    )
    style.map("Treeview.Heading", background=[("active", pick(SURFACE_2))])

    for tree, tags in list(_tree_tags):
        if tree.winfo_exists():
            _configure_tags(tree, tags)
        else:
            _tree_tags.remove((tree, tags))
