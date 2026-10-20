"""Duplicate finder view: scan controls, results and selection."""

from __future__ import annotations

import customtkinter as ctk

from models import ScanProgress, clear_duplicate_selection, select_all_duplicates
from ui.formatting import format_size
from ui.theme import THEME


class DuplicatesView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        control_card = ctk.CTkFrame(
            self,
            fg_color=THEME["surface"],
            corner_radius=8,
            border_width=1,
            border_color=THEME["border"],
        )
        control_card.grid(row=0, column=0, pady=(0, 10), sticky="ew")
        control_card.grid_columnconfigure(2, weight=1)

        self.scan_btn = ctk.CTkButton(
            control_card,
            text="Scan for Duplicates",
            height=36,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=THEME["success"],
            hover_color=THEME["success_hover"],
            command=app.start_duplicate_scan,
        )
        self.scan_btn.grid(row=0, column=0, padx=(14, 10), pady=12)

        self.cancel_btn = ctk.CTkButton(
            control_card,
            text="Cancel Scan",
            height=36,
            corner_radius=6,
            font=ctk.CTkFont(size=12),
            fg_color=THEME["danger"],
            hover_color=THEME["danger_hover"],
            command=app.cancel_duplicate_scan,
            state="disabled",
        )
        self.cancel_btn.grid(row=0, column=1, padx=(0, 14), pady=12)

        self.progress_label = ctk.CTkLabel(
            control_card,
            text="Ready to scan root folder for byte-identical duplicates.",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_secondary"],
            anchor="w",
        )
        self.progress_label.grid(row=0, column=2, padx=10, pady=12, sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(
            control_card,
            height=6,
            corner_radius=3,
            progress_color=THEME["success"],
        )
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, columnspan=3, padx=14, pady=(0, 12), sticky="ew")
        self.progress_bar.grid_remove()

        self.results_container = ctk.CTkFrame(
            self,
            fg_color=THEME["surface"],
            corner_radius=8,
            border_width=1,
            border_color=THEME["border"],
        )
        self.results_container.grid(row=1, column=0, sticky="nsew")
        self.results_container.grid_columnconfigure(0, weight=1)
        self.results_container.grid_rowconfigure(1, weight=1)

        self.render_groups()

    # Scan state (driven by the app)

    def set_scanning(self, scanning: bool):
        self.scan_btn.configure(state="disabled" if scanning else "normal")
        self.cancel_btn.configure(state="normal" if scanning else "disabled")
        if scanning:
            self.progress_bar.set(0)
            self.progress_bar.grid()
        else:
            self.progress_bar.grid_remove()

    def set_progress_text(self, text: str):
        self.progress_label.configure(text=text)

    def show_progress(self, progress: ScanProgress):
        if progress.total > 0:
            self.progress_bar.set(progress.current / progress.total)
        self.set_progress_text(
            f"{progress.step} — Processed: {progress.files_processed}/{progress.total} | Groups: {progress.groups_found}"
        )

    # Results

    def render_groups(self):
        groups = self.app.duplicate_groups
        for widget in self.results_container.winfo_children():
            widget.destroy()

        if not groups:
            ctk.CTkLabel(
                self.results_container,
                text="No duplicates to display. Click 'Scan for Duplicates' to search the active folder.",
                font=ctk.CTkFont(size=12),
                text_color=THEME["text_muted"],
            ).pack(padx=20, pady=40)
            return

        toolbar = ctk.CTkFrame(self.results_container, fg_color="transparent")
        toolbar.grid(row=0, column=0, padx=16, pady=10, sticky="ew")

        for text, command, side, padx in (
            ("Select Duplicates", self._select_all, "left", (0, 6)),
            ("Clear Selection", self._clear_selection, "left", (0, 16)),
        ):
            ctk.CTkButton(
                toolbar,
                text=text,
                height=28,
                corner_radius=4,
                font=ctk.CTkFont(size=11),
                fg_color=THEME["surface_card"],
                hover_color=THEME["surface_hover"],
                border_width=1,
                border_color=THEME["border"],
                command=command,
            ).pack(side=side, padx=padx)

        ctk.CTkButton(
            toolbar,
            text="Move Selected to 'Duplicates/'",
            height=28,
            corner_radius=4,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=self.app.move_selected_duplicates,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            toolbar,
            text="Move Selected to Trash",
            height=28,
            corner_radius=4,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=THEME["danger"],
            hover_color=THEME["danger_hover"],
            command=self.app.trash_selected_duplicates,
        ).pack(side="right")

        scroll_area = ctk.CTkScrollableFrame(self.results_container, fg_color="transparent")
        scroll_area.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="nsew")
        scroll_area.grid_columnconfigure(0, weight=1)

        for idx, group in enumerate(groups, 1):
            group_card = ctk.CTkFrame(
                scroll_area,
                fg_color=THEME["surface_card"],
                corner_radius=6,
                border_width=1,
                border_color=THEME["border"],
            )
            group_card.pack(fill="x", pady=6)

            gh = ctk.CTkFrame(group_card, fg_color=THEME["surface_hover"], corner_radius=0, height=28)
            gh.pack(fill="x")
            ctk.CTkLabel(
                gh,
                text=f"Group {idx} — {len(group.files)} copies ({format_size(group.size)} each) | SHA-256: {group.sha256[:12]}...",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=THEME["text_primary"],
            ).pack(side="left", padx=10, pady=4)

            for f in group.files:
                frow = ctk.CTkFrame(group_card, fg_color="transparent")
                frow.pack(fill="x", padx=10, pady=4)

                var = ctk.BooleanVar(value=f.selected)
                ctk.CTkCheckBox(
                    frow,
                    text=f.path.name,
                    variable=var,
                    font=ctk.CTkFont(size=11),
                    text_color=THEME["text_primary"],
                    fg_color=THEME["accent"],
                    command=lambda f=f, var=var: setattr(f, "selected", var.get()),
                ).pack(side="left", padx=(0, 10))

                ctk.CTkLabel(
                    frow,
                    text="[Original - Preserved by default]" if f.is_original else "[Duplicate]",
                    font=ctk.CTkFont(size=10, weight="bold" if f.is_original else "normal"),
                    text_color=THEME["success"] if f.is_original else THEME["warning"],
                ).pack(side="left")

    def _select_all(self):
        select_all_duplicates(self.app.duplicate_groups)
        self.render_groups()

    def _clear_selection(self):
        clear_duplicate_selection(self.app.duplicate_groups)
        self.render_groups()
