"""Organize view: category rules, dry-run preview and apply."""

from __future__ import annotations

from tkinter import ttk

import customtkinter as ctk

from core import CATEGORIES, collect_selected_extensions
from models import ExecutionResult, OperationItem, OperationPlan
from operations import build_organization_plan
from ui import theme as t
from ui.formatting import category_counts, extension_preview, format_size, plural
from ui.widgets import (
    Banner,
    Card,
    EmptyState,
    hairline,
    primary_button,
    scrollbar,
    secondary_button,
    set_default,
    set_enabled,
    text_field,
    tooltip,
)

_COLUMNS = (
    # id, heading, width, stretch, anchor. Widths fit the 880 px minimum window;
    # ttk only stretches columns when there is extra room, never shrinks them.
    ("file", "File", 190, True, "w"),
    ("dest", "Moves to", 120, True, "w"),
    ("size", "Size", 76, False, "e"),
    ("note", "Note", 140, True, "w"),
)


class OrganizeView(ctk.CTkFrame):
    TITLE = "Organize"
    SUBTITLE = "Sort the loose files in this folder into category folders."

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.plan: OperationPlan | None = None
        self._items: dict[str, OperationItem] = {}
        self._sort: tuple[str, bool] | None = None  # (column, descending)

        self.cat_vars: dict[str, ctk.BooleanVar] = {
            cat: ctk.BooleanVar(value=True) for cat in CATEGORIES
        }
        self.extra_ext_var = ctk.StringVar()
        self.custom_folder_var = ctk.StringVar()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.banner = Banner(self)
        self.banner.grid(row=1, column=0, sticky="ew", pady=(0, 2 * t.SPACE))
        self.banner.hide()

        self._build_rules().grid(row=2, column=0, sticky="ew", pady=(0, 2 * t.SPACE))
        self._build_preview().grid(row=3, column=0, sticky="nsew")
        self._build_footer().grid(row=4, column=0, sticky="ew", pady=(2 * t.SPACE, 0))

        for var in (*self.cat_vars.values(), self.extra_ext_var, self.custom_folder_var):
            var.trace_add("write", self._on_rules_changed)
        self.clear_preview()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_rules(self) -> Card:
        card = Card(self, "Categories")
        body = card.body
        # Two pairs of grid columns (box, hint) so the hints line up without fixed widths.
        cats = ctk.CTkFrame(body, fg_color="transparent")
        cats.grid(row=0, column=0, columnspan=2, sticky="ew")
        cats.grid_columnconfigure((1, 3), weight=1)

        for idx, (cat_name, var) in enumerate(self.cat_vars.items()):
            row, col = idx // 2, (idx % 2) * 2
            ctk.CTkCheckBox(
                cats,
                text=cat_name,
                width=0,
                variable=var,
                font=t.font("body"),
                text_color=t.TEXT,
                fg_color=t.ACCENT,
                hover_color=t.ACCENT_HOVER,
                border_color=t.FIELD_BORDER,
                border_width=2,
                checkmark_color=t.ON_ACCENT,
                checkbox_width=18,
                checkbox_height=18,
                corner_radius=4,
            ).grid(row=row, column=col, sticky="w", pady=2)
            ctk.CTkLabel(
                cats,
                text=extension_preview(CATEGORIES[cat_name]),
                font=t.font("caption"),
                text_color=t.TEXT_MUTED,
                anchor="w",
            ).grid(row=row, column=col + 1, sticky="w", padx=(12, 2 * t.SPACE))

        hairline(body).grid(row=3, column=0, columnspan=2, sticky="ew", pady=12)

        # Options and the Preview button share one row to leave height for the preview.
        inputs = ctk.CTkFrame(body, fg_color="transparent")
        inputs.grid(row=4, column=0, columnspan=2, sticky="ew")
        inputs.grid_columnconfigure((0, 1), weight=1, uniform="inputs")
        for col, (label, var, hint) in enumerate(
            (
                ("Extra extensions", self.extra_ext_var, "For example: .iso, .blend"),
                ("Put everything in one folder", self.custom_folder_var, "Optional. Leave empty for one folder per category."),
            )
        ):
            padx = (0, 2 * t.SPACE)
            ctk.CTkLabel(inputs, text=label, font=t.font("caption_bold"), text_color=t.TEXT, anchor="w").grid(
                row=0, column=col, sticky="w", padx=padx, pady=(0, 4)
            )
            entry = text_field(inputs, var)
            entry.grid(row=1, column=col, sticky="ew", padx=padx)
            entry.bind("<Return>", lambda _e: self.generate_preview())
            tooltip(entry, hint)

        self.preview_button = primary_button(inputs, "Preview", self.generate_preview, width=96)
        self.preview_button.grid(row=1, column=2, sticky="e")
        tooltip(self.preview_button, "Show what would move. Nothing changes yet.  (Ctrl+Enter)")
        return card

    def _build_preview(self) -> Card:
        card = Card(self, "Preview")
        # Summary sits on the title line: "Preview      17 files · 42.3 MB · 1 rename"
        self.summary_label = ctk.CTkLabel(card.header, text="", font=t.font("body"), text_color=t.TEXT_MUTED)
        self.summary_label.grid(row=0, column=1, sticky="e")
        body = card.body
        body.grid_rowconfigure(0, weight=1)

        self.empty = EmptyState(body)
        self.empty.grid(row=0, column=0, sticky="nsew")

        self.table = ctk.CTkFrame(body, fg_color="transparent")
        self.table.grid(row=0, column=0, sticky="nsew")
        self.table.grid_columnconfigure(0, weight=1)
        self.table.grid_rowconfigure(1, weight=1)
        self.categories_label = ctk.CTkLabel(
            self.table, text="", font=t.font("caption"), text_color=t.TEXT_MUTED, anchor="w"
        )
        self.categories_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        self.tree = ttk.Treeview(
            self.table, columns=[c[0] for c in _COLUMNS], show="headings", selectmode="browse"
        )
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        for col, heading, width, stretch, anchor in _COLUMNS:
            self.tree.heading(col, text=heading, anchor=anchor, command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=round(width * scale), minwidth=round(48 * scale), stretch=stretch, anchor=anchor)
        self.tree.grid(row=1, column=0, sticky="nsew")
        scroll = scrollbar(self.table, self.tree)
        scroll.grid(row=1, column=1, sticky="ns")
        t.register_tree_tags(self.tree, {"collision": {"foreground": t.WARNING}})
        return card

    def _build_footer(self) -> ctk.CTkFrame:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        self.move_button = primary_button(footer, "Move Files", self.apply, width=120)
        self.move_button.pack(side="right")
        tooltip(self.move_button, "Move the previewed files into their folders. You can undo this.  (Ctrl+M)")
        self.discard_button = secondary_button(footer, "Discard Preview", self.clear_preview)
        self.discard_button.pack(side="right", padx=(0, t.SPACE))
        return footer

    # ------------------------------------------------------------------
    # Preview state
    # ------------------------------------------------------------------

    def _show_empty(self, title: str, text: str = ""):
        self.empty.set(title, text)
        self.table.grid_remove()
        self.empty.grid()
        self.summary_label.configure(text="")

    def _set_footer(self, count: int):
        set_enabled(self.discard_button, self.plan is not None)
        set_enabled(self.move_button, count > 0)
        self.move_button.configure(text=f"Move {plural(count, 'File', 'Files')}" if count else "Move Files")
        # One default action at a time: Preview until there is something to move, then Move.
        set_default(self.preview_button, count == 0)

    def clear_preview(self, title: str = "No preview yet", text: str | None = None):
        """Forget the current plan; rules and inputs are kept."""
        self.plan = None
        self.tree.delete(*self.tree.get_children())
        self._items.clear()
        self._show_empty(title, text or "Choose the rules above, then preview. Nothing moves until you confirm.")
        self._set_footer(0)

    def _on_rules_changed(self, *_):
        if self.plan is not None:
            self.clear_preview("Rules changed", "Preview again to see what will move.")

    def generate_preview(self):
        app = self.app
        self.banner.hide()
        selected_exts = collect_selected_extensions(
            {cat: var.get() for cat, var in self.cat_vars.items()},
            self.extra_ext_var.get(),
        )
        if not selected_exts:
            self.banner.show("error", "Nothing to look for", "Tick at least one category or add an extension.")
            return

        custom_folder = self.custom_folder_var.get().strip()
        ok, plan, err = build_organization_plan(app.current_path, selected_exts, custom_folder)
        if not ok:
            self.banner.show("error", "These rules can't be used", err or "Unknown configuration error")
            app.log("ERROR", f"Organization configuration rejected: {err}")
            app.set_status("error", str(err))
            return

        self.plan = plan
        self.tree.delete(*self.tree.get_children())
        self._items.clear()
        self._sort = None
        self._refresh_headings()

        if plan.affected_count == 0:
            self._show_empty("Nothing to move", "No loose files in this folder match the selected rules.")
            self._set_footer(0)
            app.set_status("info", "Preview: no files match the selected rules.")
            return

        for item in plan.executable_items:
            iid = self.tree.insert(
                "",
                "end",
                values=(
                    item.original_name,
                    f"{item.category}/",
                    format_size(item.size),
                    f"renamed to {item.final_name}" if item.is_collision else "",
                ),
                tags=("collision",) if item.is_collision else (),
            )
            self._items[iid] = item

        summary = f"{plural(plan.affected_count, 'file')} · {format_size(plan.total_size_bytes)}"
        if plan.collision_count:
            summary += f" · {plural(plan.collision_count, 'rename')}"
        self.summary_label.configure(text=summary)
        self.categories_label.configure(
            text=" · ".join(f"{name} {count}" for name, count in category_counts(plan))
        )
        self.empty.grid_remove()
        self.table.grid()
        self._set_footer(plan.affected_count)

        app.set_status(
            "info", f"Preview ready: {plural(plan.affected_count, 'file')} will move. Nothing has changed yet."
        )
        app.log(
            "INFO",
            f"Preview generated: {plan.affected_count} file(s) ({format_size(plan.total_size_bytes)}), {plan.collision_count} collision(s).",
        )

    # ------------------------------------------------------------------
    # Sorting
    # ------------------------------------------------------------------

    _SORT_KEYS = {
        "file": lambda i: i.original_name.lower(),
        "dest": lambda i: (i.category.lower(), i.original_name.lower()),
        "size": lambda i: i.size,
        "note": lambda i: (not i.is_collision, i.original_name.lower()),
    }

    def _sort_by(self, column: str):
        descending = self._sort == (column, False)
        self._sort = (column, descending)
        key = self._SORT_KEYS[column]
        ordered = sorted(self._items, key=lambda iid: key(self._items[iid]), reverse=descending)
        for index, iid in enumerate(ordered):
            self.tree.move(iid, "", index)
        self._refresh_headings()

    def _refresh_headings(self):
        for col, heading, *_ in _COLUMNS:
            arrow = ""
            if self._sort and self._sort[0] == col:
                arrow = " ▼" if self._sort[1] else " ▲"
            self.tree.heading(col, text=heading + arrow)

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply(self):
        if self.plan is None or self.plan.affected_count == 0:
            return
        result = self.app.apply_plan(self.plan)
        if result is None:
            return
        self.clear_preview("Done", "Preview again to organize more files.")
        self.show_result(result)

    def show_result(self, result: ExecutionResult):
        moved, failed = result.success_count, result.failure_count
        if failed == 0:
            self.banner.show(
                "success",
                f"Moved {plural(moved, 'file')}",
                "They are in their new folders. Use Undo in the toolbar to put them back.",
                ("Undo", self.app.execute_undo),
            )
            return
        self.banner.show(
            "warning" if moved else "error",
            f"Moved {moved} of {plural(moved + failed, 'file')}",
            f"What happened: {plural(failed, 'file')} could not be moved.  "
            "Why: they were changed, locked or moved after the preview.  "
            "Next steps: open Activity for the reason per file.",
            ("Open Activity", lambda: self.app.show_view("activity")),
        )
