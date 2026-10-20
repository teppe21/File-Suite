"""Organize view: category rules, dry-run preview and apply."""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from core import CATEGORIES, collect_selected_extensions
from models import OperationPlan
from operations import build_organization_plan
from ui.formatting import format_size
from ui.theme import THEME


class OrganizeView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.plan: OperationPlan | None = None

        self.cat_vars: dict[str, ctk.BooleanVar] = {
            cat: ctk.BooleanVar(value=True) for cat in CATEGORIES
        }
        self.extra_ext_var = ctk.StringVar()
        self.custom_folder_var = ctk.StringVar()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)

        rules_card = ctk.CTkFrame(
            container,
            fg_color=THEME["surface"],
            corner_radius=8,
            border_width=1,
            border_color=THEME["border"],
        )
        rules_card.grid(row=0, column=0, pady=(0, 12), sticky="ew")
        rules_card.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(
            rules_card,
            text="Category Presets",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=THEME["text_primary"],
        ).grid(row=0, column=0, columnspan=3, padx=16, pady=(12, 8), sticky="w")

        cb_grid = ctk.CTkFrame(rules_card, fg_color="transparent")
        cb_grid.grid(row=1, column=0, columnspan=3, padx=16, pady=(0, 10), sticky="ew")

        for idx, (cat_name, var) in enumerate(self.cat_vars.items()):
            ctk.CTkCheckBox(
                cb_grid,
                text=cat_name,
                variable=var,
                font=ctk.CTkFont(size=12),
                text_color=THEME["text_secondary"],
                fg_color=THEME["accent"],
                hover_color=THEME["accent_hover"],
            ).grid(row=idx // 3, column=idx % 3, padx=(0, 20), pady=6, sticky="w")

        ctk.CTkLabel(
            rules_card,
            text="Additional Extensions (comma-separated):",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_muted"],
        ).grid(row=2, column=0, columnspan=3, padx=16, pady=(8, 2), sticky="w")

        ctk.CTkEntry(
            rules_card,
            textvariable=self.extra_ext_var,
            height=32,
            corner_radius=6,
            border_width=1,
            border_color=THEME["border"],
            fg_color=THEME["surface_card"],
            placeholder_text="e.g. .iso, .blend, .raw",
        ).grid(row=3, column=0, columnspan=3, padx=16, pady=(0, 10), sticky="ew")

        ctk.CTkLabel(
            rules_card,
            text="Custom Destination Subfolder (optional, leave blank for category folders):",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_muted"],
        ).grid(row=4, column=0, columnspan=3, padx=16, pady=(4, 2), sticky="w")

        ctk.CTkEntry(
            rules_card,
            textvariable=self.custom_folder_var,
            height=32,
            corner_radius=6,
            border_width=1,
            border_color=THEME["border"],
            fg_color=THEME["surface_card"],
            placeholder_text="e.g. Sorted_Archive",
        ).grid(row=5, column=0, columnspan=3, padx=16, pady=(0, 16), sticky="ew")

        action_bar = ctk.CTkFrame(container, fg_color="transparent")
        action_bar.grid(row=1, column=0, pady=(0, 12), sticky="ew")
        action_bar.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            action_bar,
            text="Preview Organization",
            height=36,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=self.generate_preview,
        ).pack(side="left", padx=(0, 10))

        self.preview_container = ctk.CTkFrame(
            container,
            fg_color=THEME["surface"],
            corner_radius=8,
            border_width=1,
            border_color=THEME["border"],
        )
        self.preview_container.grid(row=2, column=0, sticky="ew")
        self.preview_container.grid_columnconfigure(0, weight=1)
        self.clear_preview()

    def _reset_preview_area(self, message: str | None = None):
        for widget in self.preview_container.winfo_children():
            widget.destroy()
        if message:
            ctk.CTkLabel(
                self.preview_container,
                text=message,
                font=ctk.CTkFont(size=12),
                text_color=THEME["text_muted"],
            ).pack(padx=20, pady=30)

    def clear_preview(self):
        self.plan = None
        self._reset_preview_area(
            "No organization preview generated yet. Click 'Preview Organization' to inspect changes."
        )

    def generate_preview(self):
        app = self.app
        selected_exts = collect_selected_extensions(
            {cat: var.get() for cat, var in self.cat_vars.items()},
            self.extra_ext_var.get(),
        )

        if not selected_exts:
            messagebox.showwarning(
                "No Extensions Selected",
                "Please select at least one category or supply custom extensions.",
            )
            return

        custom_folder = self.custom_folder_var.get().strip()
        ok, plan, err = build_organization_plan(app.current_path, selected_exts, custom_folder)

        if not ok:
            messagebox.showerror("Invalid Configuration", err or "Unknown configuration error")
            app.log("ERROR", f"Organization configuration rejected: {err}")
            app.set_status("error", str(err))
            return

        self.plan = plan

        if plan.affected_count == 0:
            self._reset_preview_area("No matching files found in root directory to organize.")
            app.set_status("info", "Preview: no files match the selected rules.")
            return

        self._reset_preview_area()
        header_frame = ctk.CTkFrame(self.preview_container, fg_color="transparent")
        header_frame.pack(fill="x", padx=16, pady=(12, 6))

        size_text = format_size(plan.total_size_bytes)
        ctk.CTkLabel(
            header_frame,
            text=f"Preview: {plan.affected_count} file(s) ({size_text}) scheduled to move",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=THEME["text_primary"],
        ).pack(side="left")

        if plan.collision_count > 0:
            ctk.CTkLabel(
                header_frame,
                text=f"[{plan.collision_count} collision rename(s)]",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=THEME["warning"],
            ).pack(side="left", padx=8)

        table = ctk.CTkScrollableFrame(self.preview_container, height=220, fg_color=THEME["surface_card"])
        table.pack(fill="x", padx=16, pady=(0, 12))
        table.grid_columnconfigure(0, weight=1)

        for item in plan.executable_items:
            dest_rel = item.destination.relative_to(app.current_path) if item.destination else "None"
            col_tag = " [Collision]" if item.is_collision else ""
            ctk.CTkLabel(
                table,
                text=f"{item.original_name}  ➔  {dest_rel}{col_tag}",
                font=ctk.CTkFont(size=11),
                text_color=THEME["warning"] if item.is_collision else THEME["text_secondary"],
                anchor="w",
            ).pack(fill="x", padx=4, pady=2)

        btn_bar = ctk.CTkFrame(self.preview_container, fg_color="transparent")
        btn_bar.pack(fill="x", padx=16, pady=(0, 14))

        ctk.CTkButton(
            btn_bar,
            text=f"Apply Changes ({plan.affected_count} files)",
            height=34,
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=THEME["success"],
            hover_color=THEME["success_hover"],
            command=self.apply,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_bar,
            text="Cancel",
            height=34,
            corner_radius=6,
            font=ctk.CTkFont(size=12),
            fg_color=THEME["surface_card"],
            hover_color=THEME["surface_hover"],
            border_width=1,
            border_color=THEME["border"],
            command=self.clear_preview,
        ).pack(side="left")

        app.set_status("info", f"Preview ready: {plan.affected_count} files will move. Nothing has changed yet.")
        app.log(
            "INFO",
            f"Preview generated: {plan.affected_count} file(s) ({size_text}), {plan.collision_count} collision(s).",
        )

    def apply(self):
        if self.plan is None:
            return
        if self.app.apply_plan(self.plan) is not None:
            self.clear_preview()
