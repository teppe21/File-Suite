"""
Visual system: colour tokens, type, spacing and the ttk.Treeview style.

Neutral, system-style surfaces with one accent, so the files are the focus.
Colours are CustomTkinter ``(light, dark)`` tuples; every text/background pair
used by the UI is at least 4.5:1 (WCAG AA).
"""

from __future__ import annotations

import sys
import tkinter.font as tkfont
from tkinter import ttk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

# Surfaces. The sidebar is the heavier, structural material; content sits on BG,
# grouped content on SURFACE.
BG = ("#F5F5F7", "#1C1C1E")
SIDEBAR = ("#E8E8ED", "#161618")
SIDEBAR_HOVER = ("#DEDEE3", "#232326")
SIDEBAR_SELECTED = ("#D4D4DA", "#2E2E31")
SURFACE = ("#FFFFFF", "#2C2C2E")
SEPARATOR = ("#E5E5EA", "#38383A")
FIELD = ("#FFFFFF", "#1C1C1E")
FIELD_BORDER = ("#C7C7CC", "#48484A")
GROUP_ROW = ("#F5F5F7", "#323234")  # group rows in the duplicates list

# Neutral controls (secondary buttons, segmented controls, badges)
NEUTRAL = ("#E5E5EA", "#3A3A3C")
NEUTRAL_HOVER = ("#D8D8DE", "#48484A")
NEUTRAL_PRESSED = ("#C7C7CC", "#545458")
SEGMENT_SELECTED = ("#FFFFFF", "#636366")

# Text
TEXT = ("#1D1D1F", "#F5F5F7")
TEXT_MUTED = ("#636366", "#98989D")

# Accent: the default action of a view, selection and focus. White text: 5.26:1.
ACCENT = ("#0068DA", "#0068DA")
ACCENT_HOVER = ("#0058BA", "#0058BA")
ACCENT_PRESSED = ("#004A9C", "#004A9C")
ACCENT_TEXT = ("#0068DA", "#4AA3FF")
ON_ACCENT = "#FFFFFF"

# Status colours, only for results and the destructive action, always with text.
SUCCESS = ("#1F7A35", "#30D158")
WARNING = ("#B25000", "#FF9F0A")
DANGER = ("#BF0012", "#FF8A84")
INFO_TINT = ("#E8F1FD", "#16283D")
SUCCESS_TINT = ("#E7F4EA", "#17291C")
WARNING_TINT = ("#FDF1E3", "#33261A")
DANGER_TINT = ("#FCE8E9", "#3A1D1F")

# Spacing (4/8 px rhythm), radii and sizes: compact, pointer-sized desktop controls
SPACE = 8
MARGIN = 24  # content edge
CARD_RADIUS = 10
BUTTON_RADIUS = 6
BUTTON_HEIGHT = 32
SMALL_BUTTON_HEIGHT = 28
SIDEBAR_WIDTH = 220

# ---------------------------------------------------------------------------
# Type: the platform's own UI font. On Windows 11, Segoe UI Variable has
# separate Display (large) and Text (small) optical sizes and real semibold cuts.
# ---------------------------------------------------------------------------

# role -> (size px, semibold?, display cut?). Nothing below 12 px.
_TYPE_SCALE = {
    "title": (22, True, True),
    "section": (15, True, True),
    "headline": (13, True, False),
    "body": (13, False, False),
    "caption": (12, False, False),
    "caption_bold": (12, True, False),
}
_fonts: dict[str, ctk.CTkFont] = {}
_families: dict[tuple[bool, bool], tuple[str, str]] = {}


def _family(semibold: bool, display: bool) -> tuple[str, str]:
    """(family, weight) for the current platform, picked once."""
    key = (semibold, display)
    if key not in _families:
        available = set(tkfont.families())
        cut = "Display" if display else "Text"
        if sys.platform == "win32":
            names = (
                [f"Segoe UI Variable {cut} Semib", f"Segoe UI Variable {cut} Semibold", "Segoe UI Semibold"]
                if semibold
                else [f"Segoe UI Variable {cut}", "Segoe UI"]
            )
            for name in names:
                if name in available:
                    _families[key] = (name, "normal")  # weight is part of the family
                    break
        if key not in _families:
            default = tkfont.nametofont("TkDefaultFont").actual("family")
            _families[key] = (default, "bold" if semibold else "normal")
    return _families[key]


def font(role: str = "body") -> ctk.CTkFont:
    """Shared CTkFont for a type role (created after the root window exists)."""
    if role == "body_bold":
        role = "headline"
    if role not in _fonts:
        size, semibold, display = _TYPE_SCALE[role]
        family, weight = _family(semibold, display)
        _fonts[role] = ctk.CTkFont(family=family, size=size, weight=weight)
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
        _, semibold, display = _TYPE_SCALE[role]
        _tree_fonts[role] = tkfont.Font(family=_family(semibold, display)[0])
    return _tree_fonts[role]


_check_images: dict[bool, ImageTk.PhotoImage] = {}


def _draw_checkbox(checked: bool, size: int) -> Image.Image:
    """A checkbox matching CTkCheckBox, drawn 4x and scaled down for smooth edges."""
    s = size * 4
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = round(s * 0.22)
    if checked:
        draw.rounded_rectangle((0, 0, s - 1, s - 1), radius, fill=pick(ACCENT))
        points = [(s * 0.26, s * 0.52), (s * 0.43, s * 0.69), (s * 0.75, s * 0.33)]
        draw.line(points, fill=ON_ACCENT, width=round(s * 0.12), joint="curve")
    else:
        edge = round(s * 0.09)
        draw.rounded_rectangle((0, 0, s - 1, s - 1), radius, fill=pick(FIELD), outline=pick(FIELD_BORDER), width=edge)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def checkbox_image(root, checked: bool) -> ImageTk.PhotoImage:
    """Tick-box image for Treeview rows; redrawn in place on theme changes."""
    if checked not in _check_images:
        size = round(16 * ctk.ScalingTracker.get_widget_scaling(root))
        _check_images[checked] = ImageTk.PhotoImage(_draw_checkbox(checked, size), master=root)
    return _check_images[checked]


def apply_treeview_style(root) -> None:
    """
    Style every ttk.Treeview for the current appearance mode and DPI scaling.
    Uses the "clam" theme because the Windows "vista" theme ignores colours.
    Call at start-up and on every appearance-mode change.
    """
    scaling = ctk.ScalingTracker.get_widget_scaling(root)
    for role in ("body", "headline", "caption"):
        size, semibold, display = _TYPE_SCALE[role]
        # Negative size = pixels, scaled like CustomTkinter's own widgets.
        tree_font(role).configure(size=-round(size * scaling), weight=_family(semibold, display)[1])
    row_height = tree_font("body").metrics("linespace") + round(10 * scaling)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        "Treeview",
        background=pick(SURFACE),
        fieldbackground=pick(SURFACE),
        foreground=pick(TEXT),
        bordercolor=pick(SURFACE),
        lightcolor=pick(SURFACE),
        darkcolor=pick(SURFACE),
        borderwidth=0,
        rowheight=row_height,
        font=tree_font("body"),
        indent=round(18 * scaling),
    )
    # Desktop list selection: accent fill, white text.
    style.map(
        "Treeview",
        background=[("selected", pick(ACCENT))],
        foreground=[("selected", ON_ACCENT)],
    )
    style.configure(
        "Treeview.Heading",
        background=pick(SURFACE),
        foreground=pick(TEXT_MUTED),
        bordercolor=pick(SEPARATOR),
        lightcolor=pick(SURFACE),
        darkcolor=pick(SEPARATOR),
        relief="flat",
        font=tree_font("caption"),
        padding=(round(8 * scaling), round(4 * scaling)),
    )
    style.map("Treeview.Heading", background=[("active", pick(GROUP_ROW))])
    # Visible keyboard focus: an accent outline around a focused list.
    style.map("Treeview", bordercolor=[("focus", pick(ACCENT))], lightcolor=[("focus", pick(ACCENT))])

    for checked, image in _check_images.items():
        image.paste(_draw_checkbox(checked, image.width()))
    for tree, tags in list(_tree_tags):
        if tree.winfo_exists():
            _configure_tags(tree, tags)
        else:
            _tree_tags.remove((tree, tags))
