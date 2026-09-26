"""
File Suite — Modern Linux Desktop Organizer & Deduplication Utility.

A polished, secure, and deterministic utility for organizing files and finding
duplicates inside a selected Linux directory.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

from core import (
    CATEGORIES,
    collect_selected_extensions,
)
from duplicates import scan_duplicates
from models import (
    DuplicateGroup,
    ExecutionResult,
    OperationPlan,
    ScanProgress,
)
from operations import (
    build_duplicate_move_plan,
    build_organization_plan,
    execute_operation_plan,
    move_to_system_trash,
    undo_last_operation,
)
from version import __version__


def _resource_path(name: str) -> Path:
    """Return the on-disk path of a bundled resource (source or PyInstaller)."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent
    return base / name


# ---------------------------------------------------------------------------
# Visual Theme Configuration (Graphite / Slate Developer Aesthetic)
# ---------------------------------------------------------------------------

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

THEME = {
    "bg_main": "#121418",
    "surface": "#1a1d24",
    "surface_card": "#21252f",
    "surface_hover": "#2a2f3c",
    "border": "#2d3340",
    "border_light": "#3b4252",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "accent_subtle": "#1e3a8a",
    "success": "#059669",
    "success_hover": "#047857",
    "danger": "#dc2626",
    "danger_hover": "#b91c1c",
    "warning": "#d97706",
    "text_primary": "#f3f4f6",
    "text_secondary": "#9ca3af",
    "text_muted": "#6b7280",
}


class FileOrganizerApp(ctk.CTk):
    """Primary application controller and UI orchestration."""

    def __init__(self):
        super().__init__()

        self.title(f"File Suite v{__version__} — Filesystem Organizer & Duplicate Cleaner")
        self.geometry("920x760")
        self.minsize(840, 640)
        self.configure(fg_color=THEME["bg_main"])

        self._set_window_icon()

        default_downloads = Path.home() / "Downloads"
        self.current_path: Path = default_downloads if default_downloads.exists() else Path.home()

        # Operational state
        self._is_scanning: bool = False
        self._is_executing: bool = False
        self._is_closing: bool = False
        self._cancel_scan: threading.Event = threading.Event()

        self.current_plan: OperationPlan | None = None
        self.last_execution_result: ExecutionResult | None = None
        self.duplicate_groups: list[DuplicateGroup] = []

        # Form variables
        self.cat_vars: dict[str, ctk.BooleanVar] = {
            cat: ctk.BooleanVar(value=True) for cat in CATEGORIES
        }

        # Window protocol
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Build interface
        self._build_layout()
        self._show_organize_view()
        self.log("INFO", f"File Suite initialized. Active directory: {self.current_path}")

    # ------------------------------------------------------------------
    # Lifecycle & Thread Helpers
    # ------------------------------------------------------------------

    def _set_window_icon(self):
        icon_path = _resource_path("organizer.jpg")
        if not icon_path.exists():
            return
        try:
            pil_img = Image.open(icon_path).convert("RGBA")
            pil_img = pil_img.resize((64, 64), Image.Resampling.LANCZOS)
            self.icon_image = ImageTk.PhotoImage(pil_img)
            self.iconphoto(True, self.icon_image)
        except Exception as exc:
            print(f"[WARNING] Could not load window icon: {exc}")

    def _on_closing(self):
        """Handle window close gracefully, terminating worker threads cooperatively."""
        self._is_closing = True
        self._cancel_scan.set()
        self.destroy()

    def _safe_after(self, func, *args):
        """Thread-safe dispatch to the main Tkinter thread."""
        if not self._is_closing:
            with contextlib.suppress(Exception):
                self.after(0, func, *args)

    # ------------------------------------------------------------------
    # UI Layout Construction
    # ------------------------------------------------------------------

    def _build_layout(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # Workspace area absorbs vertical space

        # 1. Header & Navigation Bar
        self._build_header()

        # 2. Target Directory Bar
        self._build_target_bar()

        # 3. Workspace Area (Organize / Duplicates / Activity Log)
        self.workspace_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.workspace_frame.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="nsew")
        self.workspace_frame.grid_columnconfigure(0, weight=1)
        self.workspace_frame.grid_rowconfigure(0, weight=1)

        # 4. Status Bar
        self._build_status_bar()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=THEME["surface"], corner_radius=0, height=56)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        # App Brand
        brand_frame = ctk.CTkFrame(header, fg_color="transparent")
        brand_frame.grid(row=0, column=0, padx=20, pady=10, sticky="w")

        ctk.CTkLabel(
            brand_frame,
            text="FILE SUITE",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=THEME["text_primary"],
        ).pack(side="left")

        ctk.CTkLabel(
            brand_frame,
            text=f"v{__version__}",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_muted"],
        ).pack(side="left", padx=(8, 0), pady=(3, 0))

        # View Switcher (Segmented Button)
        self.view_selector = ctk.CTkSegmentedButton(
            header,
            values=["Organize Files", "Duplicate Finder", "Activity Log"],
            command=self._on_view_changed,
            height=32,
            corner_radius=6,
            fg_color=THEME["surface_card"],
            selected_color=THEME["accent"],
            selected_hover_color=THEME["accent_hover"],
            unselected_color=THEME["surface_card"],
            unselected_hover_color=THEME["surface_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.view_selector.set("Organize Files")
        self.view_selector.grid(row=0, column=2, padx=20, pady=10, sticky="e")

    def _build_target_bar(self):
        target_card = ctk.CTkFrame(
            self,
            fg_color=THEME["surface"],
            corner_radius=8,
            border_width=1,
            border_color=THEME["border"],
        )
        target_card.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        target_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            target_card,
            text="Target Folder:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=THEME["text_secondary"],
        ).grid(row=0, column=0, padx=(14, 10), pady=10, sticky="w")

        self.path_entry = ctk.CTkEntry(
            target_card,
            height=32,
            corner_radius=6,
            border_width=1,
            border_color=THEME["border"],
            fg_color=THEME["surface_card"],
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(size=12),
        )
        self.path_entry.insert(0, str(self.current_path))
        self.path_entry.configure(state="disabled")
        self.path_entry.grid(row=0, column=1, padx=4, pady=10, sticky="ew")

        ctk.CTkButton(
            target_card,
            text="Browse...",
            height=32,
            corner_radius=6,
            width=90,
            fg_color=THEME["surface_card"],
            hover_color=THEME["surface_hover"],
            border_width=1,
            border_color=THEME["border_light"],
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.select_folder,
        ).grid(row=0, column=2, padx=(8, 14), pady=10)

    def _build_status_bar(self):
        status_bar = ctk.CTkFrame(self, fg_color=THEME["surface"], corner_radius=0, height=32)
        status_bar.grid(row=3, column=0, sticky="ew")
        status_bar.grid_columnconfigure(1, weight=1)

        # Status badge
        self.status_badge = ctk.CTkLabel(
            status_bar,
            text="READY",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#ffffff",
            fg_color=THEME["accent"],
            corner_radius=4,
            width=64,
            height=18,
        )
        self.status_badge.grid(row=0, column=0, padx=(16, 10), pady=6)

        # Status text
        self.status_label = ctk.CTkLabel(
            status_bar,
            text="Ready. Choose an operation to proceed.",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_secondary"],
        )
        self.status_label.grid(row=0, column=1, sticky="w", pady=6)

        # Undo indicator
        self.undo_indicator = ctk.CTkLabel(
            status_bar,
            text="Undo: Inactive",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_muted"],
        )
        self.undo_indicator.grid(row=0, column=2, padx=16, pady=6)

    def set_status(self, badge: str, message: str, color: str = THEME["accent"]):
        """Update the status bar indicators."""
        self.status_badge.configure(text=badge, fg_color=color)
        self.status_label.configure(text=message)

    # ------------------------------------------------------------------
    # View Switching
    # ------------------------------------------------------------------

    def _on_view_changed(self, view_name: str):
        if view_name == "Organize Files":
            self._show_organize_view()
        elif view_name == "Duplicate Finder":
            self._show_duplicates_view()
        elif view_name == "Activity Log":
            self._show_log_view()

    def _clear_workspace(self):
        for widget in self.workspace_frame.winfo_children():
            widget.destroy()

    # ------------------------------------------------------------------
    # View 1: Organize Files
    # ------------------------------------------------------------------

    def _show_organize_view(self):
        self._clear_workspace()

        container = ctk.CTkScrollableFrame(self.workspace_frame, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)

        # Card: Rules & Categories
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

        # Category checkboxes
        cb_grid = ctk.CTkFrame(rules_card, fg_color="transparent")
        cb_grid.grid(row=1, column=0, columnspan=3, padx=16, pady=(0, 10), sticky="ew")

        for idx, (cat_name, var) in enumerate(self.cat_vars.items()):
            col = idx % 3
            row = idx // 3
            ctk.CTkCheckBox(
                cb_grid,
                text=cat_name,
                variable=var,
                font=ctk.CTkFont(size=12),
                text_color=THEME["text_secondary"],
                fg_color=THEME["accent"],
                hover_color=THEME["accent_hover"],
            ).grid(row=row, column=col, padx=(0, 20), pady=6, sticky="w")

        # Additional Extensions
        ctk.CTkLabel(
            rules_card,
            text="Additional Extensions (comma-separated):",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_muted"],
        ).grid(row=2, column=0, columnspan=3, padx=16, pady=(8, 2), sticky="w")

        self.custom_ext_entry = ctk.CTkEntry(
            rules_card,
            height=32,
            corner_radius=6,
            border_width=1,
            border_color=THEME["border"],
            fg_color=THEME["surface_card"],
            placeholder_text="e.g. .iso, .blend, .raw",
        )
        self.custom_ext_entry.grid(row=3, column=0, columnspan=3, padx=16, pady=(0, 10), sticky="ew")

        # Custom Destination
        ctk.CTkLabel(
            rules_card,
            text="Custom Destination Subfolder (optional, leave blank for category folders):",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_muted"],
        ).grid(row=4, column=0, columnspan=3, padx=16, pady=(4, 2), sticky="w")

        self.custom_folder_entry = ctk.CTkEntry(
            rules_card,
            height=32,
            corner_radius=6,
            border_width=1,
            border_color=THEME["border"],
            fg_color=THEME["surface_card"],
            placeholder_text="e.g. Sorted_Archive",
        )
        self.custom_folder_entry.grid(row=5, column=0, columnspan=3, padx=16, pady=(0, 16), sticky="ew")

        # Action Bar (Preview & Undo)
        action_bar = ctk.CTkFrame(container, fg_color="transparent")
        action_bar.grid(row=1, column=0, pady=(0, 12), sticky="ew")
        action_bar.grid_columnconfigure(0, weight=1)

        self.preview_btn = ctk.CTkButton(
            action_bar,
            text="Preview Organization",
            height=36,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=self._generate_organization_preview,
        )
        self.preview_btn.pack(side="left", padx=(0, 10))

        self.undo_btn = ctk.CTkButton(
            action_bar,
            text="Undo Last Move",
            height=36,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=THEME["surface_card"],
            hover_color=THEME["surface_hover"],
            border_width=1,
            border_color=THEME["border_light"],
            text_color=THEME["text_primary"],
            command=self._execute_undo,
        )
        self._update_undo_button_state()
        self.undo_btn.pack(side="left")

        # Preview Container (Populated when user clicks Preview)
        self.preview_container = ctk.CTkFrame(
            container,
            fg_color=THEME["surface"],
            corner_radius=8,
            border_width=1,
            border_color=THEME["border"],
        )
        self.preview_container.grid(row=2, column=0, sticky="ew")
        self.preview_container.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.preview_container,
            text="No organization preview generated yet. Click 'Preview Organization' to inspect changes.",
            font=ctk.CTkFont(size=12),
            text_color=THEME["text_muted"],
        ).pack(padx=20, pady=30)

    def _update_undo_button_state(self):
        if self.last_execution_result and self.last_execution_result.success_count > 0:
            count = self.last_execution_result.success_count
            self.undo_btn.configure(
                state="normal",
                text=f"Undo Last Move ({count} file{'s' if count != 1 else ''})",
            )
            self.undo_indicator.configure(
                text=f"Undo: Available ({count})",
                text_color=THEME["success"],
            )
        else:
            self.undo_btn.configure(state="disabled", text="Undo Last Move")
            self.undo_indicator.configure(text="Undo: None", text_color=THEME["text_muted"])

    def _generate_organization_preview(self):
        selected_exts = collect_selected_extensions(
            {cat: var.get() for cat, var in self.cat_vars.items()},
            self.custom_ext_entry.get(),
        )

        if not selected_exts:
            messagebox.showwarning(
                "No Extensions Selected",
                "Please select at least one category or supply custom extensions.",
            )
            return

        custom_folder = self.custom_folder_entry.get().strip()
        ok, plan, err = build_organization_plan(self.current_path, selected_exts, custom_folder)

        if not ok:
            messagebox.showerror("Invalid Configuration", err or "Unknown configuration error")
            self.log("ERROR", f"Organization configuration rejected: {err}")
            self.set_status("ERROR", str(err), THEME["danger"])
            return

        self.current_plan = plan

        # Render preview UI inside preview_container
        for widget in self.preview_container.winfo_children():
            widget.destroy()

        if plan.affected_count == 0:
            ctk.CTkLabel(
                self.preview_container,
                text="No matching files found in root directory to organize.",
                font=ctk.CTkFont(size=12),
                text_color=THEME["text_muted"],
            ).pack(padx=20, pady=24)
            self.set_status("READY", "Preview: No files match selected criteria.", THEME["accent"])
            return

        header_frame = ctk.CTkFrame(self.preview_container, fg_color="transparent")
        header_frame.pack(fill="x", padx=16, pady=(12, 6))

        size_mb = plan.total_size_bytes / (1024 * 1024)
        ctk.CTkLabel(
            header_frame,
            text=f"Preview: {plan.affected_count} file(s) ({size_mb:.2f} MB) scheduled to move",
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

        # File list
        table = ctk.CTkScrollableFrame(self.preview_container, height=220, fg_color=THEME["surface_card"])
        table.pack(fill="x", padx=16, pady=(0, 12))
        table.grid_columnconfigure(0, weight=1)

        for item in plan.executable_items:
            row = ctk.CTkFrame(table, fg_color="transparent")
            row.pack(fill="x", pady=2)

            dest_rel = item.destination.relative_to(self.current_path) if item.destination else "None"
            col_tag = " [Collision]" if item.is_collision else ""

            ctk.CTkLabel(
                row,
                text=f"{item.original_name}  ➔  {dest_rel}{col_tag}",
                font=ctk.CTkFont(size=11),
                text_color=THEME["warning"] if item.is_collision else THEME["text_secondary"],
                anchor="w",
            ).pack(side="left", padx=4)

        # Apply & Cancel buttons
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
            command=self._apply_organization_plan,
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
            command=self._show_organize_view,
        ).pack(side="left")

        self.set_status(
            "PREVIEW READY",
            f"Review planned changes: {plan.affected_count} file(s) selected.",
            THEME["accent"],
        )
        self.log(
            "INFO",
            f"Preview generated: {plan.affected_count} file(s) ({size_mb:.2f} MB), {plan.collision_count} collision(s).",
        )

    def _apply_organization_plan(self):
        if not self.current_plan or self.current_plan.affected_count == 0:
            return

        self.set_status("PROCESSING", "Executing file moves...", THEME["accent"])
        self.log("INFO", f"Applying organization plan ({self.current_plan.affected_count} files)...")

        result = execute_operation_plan(self.current_plan)
        self.last_execution_result = result
        self._update_undo_button_state()

        if result.success_count > 0:
            self.log(
                "SUCCESS",
                f"Successfully moved {result.success_count} file(s) into category subfolders.",
            )

        if result.failure_count > 0:
            self.log("ERROR", f"{result.failure_count} file(s) could not be moved.")
            for src, _, err in result.failed_moves:
                self.log("ERROR", f"  Failed: {src.name} — {err}")
            messagebox.showwarning(
                "Partial Execution",
                f"What happened:\n{result.success_count} file(s) were organized, but {result.failure_count} encountered errors.\n\n"
                "Why:\nOne or more files were modified, locked, or moved prior to execution.\n\n"
                "Next steps:\nCheck the Activity Log tab for detailed per-file diagnostics.",
            )

        self.set_status(
            "COMPLETED",
            f"Finished: {result.success_count} organized, {result.failure_count} failed.",
            THEME["success"] if result.failure_count == 0 else THEME["warning"],
        )

        # Reset preview area
        self._show_organize_view()

    def _execute_undo(self):
        if not self.last_execution_result or self.last_execution_result.success_count == 0:
            return

        res = self.last_execution_result
        if not messagebox.askyesno(
            "Confirm Undo",
            f"Restore {res.success_count} file(s) back to their original root directory?",
        ):
            return

        self.set_status("PROCESSING", "Undoing file moves...", THEME["accent"])
        undone, failed, errors = undo_last_operation(res)

        self._update_undo_button_state()

        if undone > 0:
            self.log("SUCCESS", f"Undo completed: restored {undone} file(s) to original location.")
        if failed > 0:
            self.log("ERROR", f"Undo encountered {failed} error(s).")
            for err in errors:
                self.log("ERROR", f"  {err}")
            messagebox.showwarning(
                "Undo Finished with Errors",
                f"What happened:\n{undone} file(s) were restored, but {failed} could not be restored.\n\n"
                "Why:\nOriginal locations may be occupied by newly created files, or destination files were modified.\n\n"
                "Next steps:\nReview the Activity Log tab for details on un-restored items.",
            )

        self.set_status(
            "COMPLETED",
            f"Undo complete: {undone} restored, {failed} failed.",
            THEME["success"] if failed == 0 else THEME["danger"],
        )

    # ------------------------------------------------------------------
    # View 2: Duplicate Finder
    # ------------------------------------------------------------------

    def _show_duplicates_view(self):
        self._clear_workspace()

        container = ctk.CTkFrame(self.workspace_frame, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        # Control & Progress Card
        control_card = ctk.CTkFrame(
            container,
            fg_color=THEME["surface"],
            corner_radius=8,
            border_width=1,
            border_color=THEME["border"],
        )
        control_card.grid(row=0, column=0, pady=(0, 10), sticky="ew")
        control_card.grid_columnconfigure(2, weight=1)

        self.scan_dup_btn = ctk.CTkButton(
            control_card,
            text="Scan for Duplicates",
            height=36,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=THEME["success"],
            hover_color=THEME["success_hover"],
            command=self._start_duplicate_scan,
        )
        self.scan_dup_btn.grid(row=0, column=0, padx=(14, 10), pady=12)

        self.cancel_scan_btn = ctk.CTkButton(
            control_card,
            text="Cancel Scan",
            height=36,
            corner_radius=6,
            font=ctk.CTkFont(size=12),
            fg_color=THEME["danger"],
            hover_color=THEME["danger_hover"],
            command=self._cancel_duplicate_scan,
            state="disabled",
        )
        self.cancel_scan_btn.grid(row=0, column=1, padx=(0, 14), pady=12)

        # Live Progress Stats
        self.dup_progress_label = ctk.CTkLabel(
            control_card,
            text="Ready to scan root folder for byte-identical duplicates.",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_secondary"],
            anchor="w",
        )
        self.dup_progress_label.grid(row=0, column=2, padx=10, pady=12, sticky="ew")

        # Progress bar
        self.dup_progress_bar = ctk.CTkProgressBar(
            control_card,
            height=6,
            corner_radius=3,
            progress_color=THEME["success"],
        )
        self.dup_progress_bar.set(0)
        self.dup_progress_bar.grid(row=1, column=0, columnspan=3, padx=14, pady=(0, 12), sticky="ew")
        self.dup_progress_bar.grid_remove()

        # Results area
        self.dup_results_container = ctk.CTkFrame(
            container,
            fg_color=THEME["surface"],
            corner_radius=8,
            border_width=1,
            border_color=THEME["border"],
        )
        self.dup_results_container.grid(row=1, column=0, sticky="nsew")
        self.dup_results_container.grid_columnconfigure(0, weight=1)
        self.dup_results_container.grid_rowconfigure(1, weight=1)

        self._render_duplicate_groups()

    def _start_duplicate_scan(self):
        if self._is_scanning:
            return

        if not self.current_path.exists() or not self.current_path.is_dir():
            messagebox.showerror("Error", "Selected target directory does not exist.")
            return

        self._is_scanning = True
        self._cancel_scan.clear()

        self.scan_dup_btn.configure(state="disabled")
        self.cancel_scan_btn.configure(state="normal")
        self.dup_progress_bar.set(0)
        self.dup_progress_bar.grid()

        self.set_status("SCANNING", f"Scanning {self.current_path.name}...", THEME["accent"])
        self.log("INFO", f"Initiated duplicate scan in: {self.current_path}")

        worker = threading.Thread(
            target=self._duplicate_scan_worker,
            args=(self.current_path,),
            daemon=True,
        )
        worker.start()

    def _cancel_duplicate_scan(self):
        if self._is_scanning:
            self._cancel_scan.set()
            self.dup_progress_label.configure(text="Cancelling scan...")
            self.set_status("CANCELLED", "Cancelling scan...", THEME["warning"])
            self.log("WARN", "User requested duplicate scan cancellation.")

    def _duplicate_scan_worker(self, target_dir: Path):
        def on_prog(progress: ScanProgress):
            self._safe_after(self._on_duplicate_scan_progress, progress)

        groups = scan_duplicates(
            target_dir=target_dir,
            cancel_event=self._cancel_scan,
            on_progress=on_prog,
        )

        self._safe_after(self._on_duplicate_scan_complete, groups)

    def _on_duplicate_scan_progress(self, progress: ScanProgress):
        if self._is_closing or not self.winfo_exists():
            return

        if progress.total > 0:
            fraction = progress.current / progress.total
            self.dup_progress_bar.set(fraction)

        self.dup_progress_label.configure(
            text=f"{progress.step} — Processed: {progress.files_processed}/{progress.total} | Groups: {progress.groups_found}"
        )

    def _on_duplicate_scan_complete(self, groups: list[DuplicateGroup]):
        if self._is_closing or not self.winfo_exists():
            return

        self._is_scanning = False
        self.scan_dup_btn.configure(state="normal")
        self.cancel_scan_btn.configure(state="disabled")
        self.dup_progress_bar.grid_remove()

        if self._cancel_scan.is_set():
            self.set_status("CANCELLED", "Duplicate scan was cancelled.", THEME["warning"])
            self.dup_progress_label.configure(text="Scan cancelled by user.")
            return

        self.duplicate_groups = groups
        total_reclaimable = sum(g.reclaimable_bytes for g in groups) / (1024 * 1024)
        total_dup_files = sum(len(g.duplicates) for g in groups)

        if not groups:
            self.set_status("COMPLETED", "Scan complete: No duplicate files found.", THEME["success"])
            self.dup_progress_label.configure(text="Scan complete: No duplicates found.")
            self.log("INFO", "Duplicate scan completed: 0 duplicates detected.")
        else:
            self.set_status(
                "COMPLETED",
                f"Found {len(groups)} group(s) ({total_dup_files} redundant files, {total_reclaimable:.2f} MB).",
                THEME["success"],
            )
            self.dup_progress_label.configure(
                text=f"Found {len(groups)} group(s) — {total_dup_files} duplicate files ({total_reclaimable:.2f} MB reclaimable)"
            )
            self.log(
                "SUCCESS",
                f"Found {len(groups)} duplicate group(s), {total_dup_files} redundant copies ({total_reclaimable:.2f} MB reclaimable).",
            )

        self._render_duplicate_groups()

    def _render_duplicate_groups(self):
        for widget in self.dup_results_container.winfo_children():
            widget.destroy()

        if not self.duplicate_groups:
            ctk.CTkLabel(
                self.dup_results_container,
                text="No duplicates to display. Click 'Scan for Duplicates' to search the active folder.",
                font=ctk.CTkFont(size=12),
                text_color=THEME["text_muted"],
            ).pack(padx=20, pady=40)
            return

        # Action Toolbar
        toolbar = ctk.CTkFrame(self.dup_results_container, fg_color="transparent")
        toolbar.grid(row=0, column=0, padx=16, pady=10, sticky="ew")

        ctk.CTkButton(
            toolbar,
            text="Select All Duplicates",
            height=28,
            corner_radius=4,
            font=ctk.CTkFont(size=11),
            fg_color=THEME["surface_card"],
            hover_color=THEME["surface_hover"],
            border_width=1,
            border_color=THEME["border"],
            command=self._select_all_duplicates,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            toolbar,
            text="Keep Originals Only",
            height=28,
            corner_radius=4,
            font=ctk.CTkFont(size=11),
            fg_color=THEME["surface_card"],
            hover_color=THEME["surface_hover"],
            border_width=1,
            border_color=THEME["border"],
            command=self._select_originals_only,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            toolbar,
            text="Clear Selection",
            height=28,
            corner_radius=4,
            font=ctk.CTkFont(size=11),
            fg_color=THEME["surface_card"],
            hover_color=THEME["surface_hover"],
            border_width=1,
            border_color=THEME["border"],
            command=self._clear_selection,
        ).pack(side="left", padx=(0, 16))

        # Batch actions
        ctk.CTkButton(
            toolbar,
            text="Move Selected to 'Duplicates/'",
            height=28,
            corner_radius=4,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=self._move_selected_duplicates,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            toolbar,
            text="Move Selected to Trash",
            height=28,
            corner_radius=4,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=THEME["danger"],
            hover_color=THEME["danger_hover"],
            command=self._trash_selected_duplicates,
        ).pack(side="right")

        # Scrollable Duplicate Groups View
        scroll_area = ctk.CTkScrollableFrame(self.dup_results_container, fg_color="transparent")
        scroll_area.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="nsew")
        scroll_area.grid_columnconfigure(0, weight=1)

        self._checkbox_refs: list[tuple[ctk.CTkCheckBox, ctk.BooleanVar, Path]] = []

        for idx, group in enumerate(self.duplicate_groups, 1):
            group_card = ctk.CTkFrame(
                scroll_area,
                fg_color=THEME["surface_card"],
                corner_radius=6,
                border_width=1,
                border_color=THEME["border"],
            )
            group_card.pack(fill="x", pady=6)
            group_card.grid_columnconfigure(0, weight=1)

            # Group Header
            single_mb = group.size / (1024 * 1024)
            gh = ctk.CTkFrame(group_card, fg_color=THEME["surface_hover"], corner_radius=0, height=28)
            gh.pack(fill="x")

            ctk.CTkLabel(
                gh,
                text=f"Group {idx} — {len(group.files)} copies ({single_mb:.2f} MB each) | SHA-256: {group.sha256[:12]}...",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=THEME["text_primary"],
            ).pack(side="left", padx=10, pady=4)

            # File entries
            for f in group.files:
                frow = ctk.CTkFrame(group_card, fg_color="transparent")
                frow.pack(fill="x", padx=10, pady=4)

                var = ctk.BooleanVar(value=f.selected)

                def make_toggle_handler(file_obj, boolean_var):
                    return lambda: setattr(file_obj, "selected", boolean_var.get())

                cb = ctk.CTkCheckBox(
                    frow,
                    text=f.path.name,
                    variable=var,
                    font=ctk.CTkFont(size=11),
                    text_color=THEME["text_primary"],
                    fg_color=THEME["accent"],
                    command=make_toggle_handler(f, var),
                )
                cb.pack(side="left", padx=(0, 10))
                self._checkbox_refs.append((cb, var, f.path))

                if f.is_original:
                    ctk.CTkLabel(
                        frow,
                        text="[Original - Preserved by default]",
                        font=ctk.CTkFont(size=10, weight="bold"),
                        text_color=THEME["success"],
                    ).pack(side="left")
                else:
                    ctk.CTkLabel(
                        frow,
                        text="[Duplicate]",
                        font=ctk.CTkFont(size=10),
                        text_color=THEME["warning"],
                    ).pack(side="left")

    def _select_all_duplicates(self):
        for group in self.duplicate_groups:
            for f in group.files:
                f.selected = True
        self._render_duplicate_groups()

    def _select_originals_only(self):
        """Keep original preserved (unselected), select all redundant copies."""
        for group in self.duplicate_groups:
            for f in group.files:
                f.selected = not f.is_original
        self._render_duplicate_groups()

    def _clear_selection(self):
        for group in self.duplicate_groups:
            for f in group.files:
                f.selected = False
        self._render_duplicate_groups()

    def _get_selected_duplicate_paths(self) -> list[Path]:
        selected: list[Path] = []
        for group in self.duplicate_groups:
            for f in group.files:
                if f.selected:
                    selected.append(f.path)
        return selected

    def _move_selected_duplicates(self):
        selected = self._get_selected_duplicate_paths()
        if not selected:
            messagebox.showinfo("No Files Selected", "Please select at least one duplicate file to isolate.")
            return

        if not messagebox.askyesno(
            "Confirm Isolation",
            f"Move {len(selected)} selected duplicate file(s) into 'Duplicates/' folder?\n(You can undo this operation afterward).",
        ):
            return

        ok, plan, err = build_duplicate_move_plan(selected, self.current_path, "Duplicates")
        if not ok:
            messagebox.showerror("Error", err or "Failed to build move plan")
            return

        result = execute_operation_plan(plan)
        self.last_execution_result = result
        self._update_undo_button_state()

        self.log(
            "SUCCESS",
            f"Moved {result.success_count} duplicate file(s) into 'Duplicates/' folder (Undo supported).",
        )
        self.set_status("COMPLETED", f"Isolated {result.success_count} duplicate(s).", THEME["success"])

        # Re-run quick scan or remove isolated files from view
        self.duplicate_groups.clear()
        self._render_duplicate_groups()

    def _trash_selected_duplicates(self):
        selected = self._get_selected_duplicate_paths()
        if not selected:
            messagebox.showinfo("No Files Selected", "Please select at least one duplicate file to trash.")
            return

        if not messagebox.askyesno(
            "Confirm System Trash",
            f"Send {len(selected)} selected duplicate file(s) to the system trash?\n\nNote: Undo from application is unavailable for trashed files.",
        ):
            return

        success_count = 0
        failed_count = 0

        for f in selected:
            ok, err = move_to_system_trash(f)
            if ok:
                success_count += 1
                self.log("INFO", f"Trashed duplicate: {f.name}")
            else:
                failed_count += 1
                self.log("ERROR", f"Could not trash {f.name}: {err}")

        # Trash operations cannot be cleanly undone from session history
        self.last_execution_result = None
        self._update_undo_button_state()

        self.log("SUCCESS", f"Sent {success_count} file(s) to system trash ({failed_count} failed).")
        self.set_status("COMPLETED", f"Trashed {success_count} file(s).", THEME["success"] if failed_count == 0 else THEME["warning"])

        if failed_count > 0:
            messagebox.showwarning(
                "Trash Finished with Errors",
                f"What happened:\n{success_count} file(s) moved to trash, but {failed_count} encountered errors.\n\n"
                "Why:\nSome files may be locked, symbolic links, or removed externally.\n\n"
                "Next steps:\nReview the Activity Log tab for details.",
            )

        self.duplicate_groups.clear()
        self._render_duplicate_groups()

    # ------------------------------------------------------------------
    # View 3: Activity Log
    # ------------------------------------------------------------------

    def _show_log_view(self):
        self._clear_workspace()

        container = ctk.CTkFrame(self.workspace_frame, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(container, fg_color="transparent")
        header.grid(row=0, column=0, pady=(0, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Diagnostics & Activity Log",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=THEME["text_primary"],
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="Clear Log",
            height=28,
            corner_radius=4,
            font=ctk.CTkFont(size=11),
            fg_color=THEME["surface_card"],
            hover_color=THEME["surface_hover"],
            border_width=1,
            border_color=THEME["border"],
            command=self._clear_log,
        ).pack(side="right")

        self.log_box = ctk.CTkTextbox(
            container,
            font=("Monospace", 11),
            corner_radius=8,
            fg_color=THEME["surface"],
            border_width=1,
            border_color=THEME["border"],
            text_color=THEME["text_primary"],
            activate_scrollbars=True,
        )
        self.log_box.grid(row=1, column=0, sticky="nsew")

        # Repopulate stored logs
        if hasattr(self, "_log_history"):
            for line in self._log_history:
                self.log_box.insert("end", line)
            self.log_box.see("end")

    def log(self, level: str, message: str):
        """Append a structured, timestamped message to the log history and console."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] [{level.upper():5}] {message}\n"

        if not hasattr(self, "_log_history"):
            self._log_history = []
        self._log_history.append(formatted)

        if hasattr(self, "log_box") and self.log_box.winfo_exists():
            with contextlib.suppress(Exception):
                self.log_box.insert("end", formatted)
                self.log_box.see("end")

        # Also print to terminal stdout for CLI diagnostics
        print(formatted.strip())

    def _clear_log(self):
        if hasattr(self, "_log_history"):
            self._log_history.clear()
        if hasattr(self, "log_box") and self.log_box.winfo_exists():
            self.log_box.delete("1.0", "end")

    # ------------------------------------------------------------------
    # Native Directory Selection
    # ------------------------------------------------------------------

    def _ask_directory_native(self, initial_dir: Path) -> str:
        initial_str = str(initial_dir)

        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", "--directory", f"--filename={initial_str}/"]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return res.stdout.strip()
                if res.returncode == 1:
                    return ""
            except (subprocess.SubprocessError, OSError):
                self.log("WARN", "Zenity dialog failed, attempting fallback.")

        if shutil.which("kdialog"):
            try:
                cmd = ["kdialog", "--getexistingdirectory", initial_str]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return res.stdout.strip()
                if res.returncode == 1:
                    return ""
            except (subprocess.SubprocessError, OSError):
                self.log("WARN", "Kdialog dialog failed, attempting fallback.")

        try:
            return filedialog.askdirectory(initialdir=initial_str)
        except Exception as exc:
            self.log("WARN", f"Directory dialog failed: {exc}")
            return ""

    def select_folder(self):
        initial_dir = self.current_path if self.current_path.exists() else Path.home()
        chosen = self._ask_directory_native(initial_dir)
        if not chosen:
            return

        self.current_path = Path(chosen)
        self.path_entry.configure(state="normal")
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, str(self.current_path))
        self.path_entry.configure(state="disabled")

        self.set_status("READY", f"Target folder set to {self.current_path.name}", THEME["accent"])
        self.log("INFO", f"Active folder changed to: {self.current_path}")


if __name__ == "__main__":
    app = FileOrganizerApp()
    app.mainloop()
