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
    primary_button,
    secondary_button,
    set_enabled,
    view_header,
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

        view_header(
            self, "Organize files", "Sort the loose files in this folder into category subfolders."
        ).grid(row=0, column=0, sticky="ew", pady=(0, 12))

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
        card = Card(self, "Rules")
        body = card.body
        body.grid_columnconfigure((0, 1), weight=1, uniform="rules")

        for idx, (cat_name, var) in enumerate(self.cat_vars.items()):
            cell = ctk.CTkFrame(body, fg_color="transparent")
            cell.grid(row=idx // 2, column=idx % 2, sticky="w", pady=1)
            ctk.CTkCheckBox(
                cell,
                text=cat_name,
                variable=var,
                font=t.font("body"),
                text_color=t.TEXT,
                fg_color=t.ACCENT,
                hover_color=t.ACCENT_HOVER,
                border_color=t.TEXT_MUTED,
                checkmark_color=t.ON_ACCENT,
                checkbox_width=20,
                checkbox_height=20,
                corner_radius=4,
            ).pack(side="left")
            ctk.CTkLabel(
                cell,
                text=extension_preview(CATEGORIES[cat_name]),
                font=t.font("caption"),
                text_color=t.TEXT_MUTED,
            ).pack(side="left", padx=(t.SPACE, 0))

        # Inputs and the Preview button share one row to leave height for the preview.
        inputs = ctk.CTkFrame(body, fg_color="transparent")
        inputs.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(t.SPACE, 0))
        inputs.grid_columnconfigure((0, 1), weight=1, uniform="inputs")
        for col, (label, var, hint) in enumerate(
            (
                ("Extra extensions", self.extra_ext_var, "e.g. .iso, .blend"),
                ("One subfolder for everything", self.custom_folder_var, "optional"),
            )
        ):
            padx = (0, 2 * t.SPACE)
            heading = ctk.CTkFrame(inputs, fg_color="transparent")
            heading.grid(row=0, column=col, sticky="w", padx=padx)
            ctk.CTkLabel(heading, text=label, font=t.font("caption"), text_color=t.TEXT).pack(side="left")
            ctk.CTkLabel(heading, text=f"  {hint}", font=t.font("caption"), text_color=t.TEXT_MUTED).pack(
                side="left"
            )
            entry = ctk.CTkEntry(
                inputs,
                textvariable=var,
                height=t.BUTTON_HEIGHT,
                corner_radius=t.BUTTON_RADIUS,
                border_width=1,
                border_color=t.BORDER,
                fg_color=t.SURFACE_2,
                text_color=t.TEXT,
                font=t.font("body"),
            )
            entry.grid(row=1, column=col, sticky="ew", padx=padx)
            entry.bind("<Return>", lambda _e: self.generate_preview())

        ctk.CTkLabel(inputs, text="Ctrl+Enter", font=t.font("caption"), text_color=t.TEXT_MUTED).grid(
            row=0, column=2, sticky="e"
        )
        primary_button(inputs, "Preview changes", self.generate_preview).grid(row=1, column=2, sticky="e")
        return card

    def _build_preview(self) -> Card:
        card = Card(self, "Preview")
        # Summary sits on the title line: "Preview   17 files · 42.3 MB · 1 rename"
        self.summary_label = ctk.CTkLabel(card.header, text="", font=t.font("body"), text_color=t.TEXT)
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
        self.categories_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        self.tree = ttk.Treeview(
            self.table, columns=[c[0] for c in _COLUMNS], show="headings", selectmode="browse"
        )
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        for col, heading, width, stretch, anchor in _COLUMNS:
            self.tree.heading(col, text=heading, anchor=anchor, command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=round(width * scale), minwidth=round(48 * scale), stretch=stretch, anchor=anchor)
        self.tree.grid(row=1, column=0, sticky="nsew")
        scroll = ctk.CTkScrollbar(self.table, command=self.tree.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        t.register_tree_tags(self.tree, {"collision": {"foreground": t.WARNING}})
        return card

    def _build_footer(self) -> ctk.CTkFrame:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        self.move_button = primary_button(footer, "Move files", self.apply)
        self.move_button.pack(side="right")
        self.discard_button = secondary_button(footer, "Discard", self.clear_preview)
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
        self.move_button.configure(text=f"Move {plural(count, 'file')}" if count else "Move files")

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
                "They are in their new folders. Undo is in the sidebar (Ctrl+Z).",
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
