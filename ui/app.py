"""
Main window: shared state, routing, logging, folder change, undo, and the
safety-relevant file operations. Views call back into this object.
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

from duplicates import scan_duplicates
from models import (
    DuplicateGroup,
    ExecutionResult,
    OperationPlan,
    OperationStatus,
    ScanProgress,
    groups_without_kept_copy,
    update_duplicate_groups_after_removal,
)
from operations import (
    build_duplicate_move_plan,
    execute_operation_plan,
    filter_unchanged_duplicates,
    move_to_system_trash,
    undo_last_operation,
)
from platform_utils import IS_WINDOWS, trash_label, trash_may_be_permanent
from ui import theme as t
from ui.activity_view import ActivityView
from ui.duplicates_view import DuplicatesView
from ui.formatting import format_log_line, format_size, truncate_middle, undo_label
from ui.organize_view import OrganizeView
from ui.widgets import secondary_button, set_enabled
from version import __version__


def _resource_path(name: str) -> Path:
    """Return the on-disk path of a bundled resource (source or PyInstaller)."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent  # project root, one level above ui/
    return base / name


class FileOrganizerApp(ctk.CTk):
    """Primary application controller and UI orchestration."""

    def __init__(self):
        ctk.set_appearance_mode("System")
        super().__init__()

        self.title(f"File Suite v{__version__}")
        self.geometry("1040x720")
        self.minsize(880, 600)
        self.configure(fg_color=t.BG)

        self._set_window_icon()

        default_downloads = Path.home() / "Downloads"
        self.current_path: Path = default_downloads if default_downloads.exists() else Path.home()

        # Operational state
        self._is_scanning: bool = False
        self._is_executing: bool = False
        self._is_closing: bool = False
        self._scan_generation: int = 0
        self._cancel_scan: threading.Event = threading.Event()

        self.last_execution_result: ExecutionResult | None = None
        self.duplicate_groups: list[DuplicateGroup] = []
        self.duplicate_scan_dir: Path | None = None

        # Activity log store: (time, level, message)
        self.log_entries: list[tuple[str, str, str]] = []
        self._unseen_problems = 0  # WARN/ERROR lines since Activity was last opened
        self.current_view = ""

        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        t.apply_treeview_style(self)
        ctk.AppearanceModeTracker.add(self._on_appearance_change, self)
        self._build_layout()
        self.show_view("organize")
        self.log("INFO", f"File Suite initialized. Active directory: {self.current_path}")

    # ------------------------------------------------------------------
    # Lifecycle & Thread Helpers
    # ------------------------------------------------------------------

    def _set_window_icon(self):
        ico_path = _resource_path("organizer.ico")
        if IS_WINDOWS and ico_path.exists():
            try:
                self.iconbitmap(default=str(ico_path))
                # CustomTkinter applies its own default icon shortly after start-up.
                self.after(250, lambda: self.iconbitmap(default=str(ico_path)))
            except Exception as exc:
                print(f"[WARNING] Could not load window icon: {exc}")
            return

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
        ctk.AppearanceModeTracker.remove(self._on_appearance_change)
        self.destroy()

    def _safe_after(self, func, *args):
        """Thread-safe dispatch to the main Tkinter thread."""
        if not self._is_closing:
            with contextlib.suppress(Exception):
                self.after(0, func, *args)

    # ------------------------------------------------------------------
    # Layout: sidebar | view, status bar below
    # ------------------------------------------------------------------

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=0, column=1, padx=3 * t.SPACE, pady=(3 * t.SPACE, 2 * t.SPACE), sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self._build_status_bar()

        # Views are built once and toggled, so their state survives switching.
        self.organize = OrganizeView(content, self)
        self.duplicates = DuplicatesView(content, self)
        self.activity = ActivityView(content, self)
        self.views = {"organize": self.organize, "duplicates": self.duplicates, "activity": self.activity}
        self.update_undo_state()

    def _build_sidebar(self):
        bar = ctk.CTkFrame(self, fg_color=t.SURFACE, corner_radius=0, width=t.SIDEBAR_WIDTH)
        bar.grid(row=0, column=0, sticky="ns")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_rowconfigure(4, weight=1)
        pad = 2 * t.SPACE

        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.grid(row=0, column=0, padx=pad, pady=(pad + 4, pad), sticky="w")
        icon_path = _resource_path("organizer-small.png")
        if icon_path.exists():
            with contextlib.suppress(Exception):
                self.brand_icon = ctk.CTkImage(Image.open(icon_path), size=(28, 28))
                ctk.CTkLabel(brand, image=self.brand_icon, text="").pack(side="left", padx=(0, t.SPACE))
        ctk.CTkLabel(brand, text="File Suite", font=t.font("section"), text_color=t.TEXT).pack(side="left")

        # Folder card: replaces the old disabled path entry
        ctk.CTkLabel(
            bar, text="FOLDER", font=t.font("caption"), text_color=t.TEXT_MUTED, anchor="w"
        ).grid(row=1, column=0, padx=pad, sticky="w")
        folder = ctk.CTkFrame(bar, fg_color=t.SURFACE_2, corner_radius=t.CARD_RADIUS)
        folder.grid(row=2, column=0, padx=pad - 4, pady=(4, pad), sticky="ew")
        folder.grid_columnconfigure(0, weight=1)
        self.folder_name_label = ctk.CTkLabel(
            folder, text="", font=t.font("body_bold"), text_color=t.TEXT, anchor="w"
        )
        self.folder_name_label.grid(row=0, column=0, padx=12, pady=(10, 0), sticky="ew")
        self.folder_path_label = ctk.CTkLabel(
            folder, text="", font=t.font("caption"), text_color=t.TEXT_MUTED, anchor="w"
        )
        self.folder_path_label.grid(row=1, column=0, padx=12, sticky="ew")
        secondary_button(folder, "Change folder…  Ctrl+O", self.select_folder, small=True).grid(
            row=2, column=0, padx=12, pady=(6, 12), sticky="ew"
        )
        self._show_folder()

        nav = ctk.CTkFrame(bar, fg_color="transparent")
        nav.grid(row=3, column=0, padx=pad - 4, sticky="ew")
        nav.grid_columnconfigure(0, weight=1)
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for idx, (key, label) in enumerate(
            (("organize", "Organize"), ("duplicates", "Duplicates"), ("activity", "Activity"))
        ):
            button = ctk.CTkButton(
                nav,
                text=label,
                anchor="w",
                height=t.BUTTON_HEIGHT,
                corner_radius=t.BUTTON_RADIUS,
                font=t.font("body"),
                fg_color="transparent",
                hover_color=t.SURFACE_2,
                text_color=t.TEXT,
                command=lambda k=key: self.show_view(k),
            )
            button.grid(row=idx, column=0, pady=2, sticky="ew")
            self.nav_buttons[key] = button
        ctk.CTkLabel(
            nav, text="Ctrl+1 / 2 / 3 to switch", font=t.font("caption"), text_color=t.TEXT_MUTED, anchor="w"
        ).grid(row=3, column=0, padx=12, pady=(2, 0), sticky="w")

        self.undo_button = secondary_button(bar, "Undo", self.execute_undo, height=48, font=t.font("caption"))
        self.undo_button.grid(row=5, column=0, padx=pad - 4, pady=(0, t.SPACE), sticky="ew")

        foot = ctk.CTkFrame(bar, fg_color="transparent")
        foot.grid(row=6, column=0, padx=pad, pady=(0, pad), sticky="ew")
        ctk.CTkLabel(foot, text=f"v{__version__}", font=t.font("caption"), text_color=t.TEXT_MUTED).pack(side="left")
        self.theme_button = secondary_button(foot, "", self._toggle_theme, small=True, width=84)
        self.theme_button.pack(side="right")
        self._update_theme_button()

    def _show_folder(self):
        path = self.current_path
        self.folder_name_label.configure(text=truncate_middle(path.name or str(path), 22))
        self.folder_path_label.configure(text=truncate_middle(str(path), 26))

    def _build_status_bar(self):
        bar = ctk.CTkFrame(self, fg_color=t.SURFACE, corner_radius=0, height=32)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        self.status_dot = ctk.CTkLabel(bar, text="●", font=t.font("caption"), text_color=t.TEXT_MUTED)
        self.status_dot.grid(row=0, column=0, padx=(2 * t.SPACE, t.SPACE), pady=4)
        self.status_label = ctk.CTkLabel(
            bar, text="Ready.", font=t.font("caption"), text_color=t.TEXT, anchor="w"
        )
        self.status_label.grid(row=0, column=1, sticky="ew", pady=4)

    _STATUS_COLORS = {
        "info": t.TEXT_MUTED,
        "busy": t.ACCENT_TEXT,
        "success": t.SUCCESS,
        "warning": t.WARNING,
        "error": t.DANGER,
    }

    def set_status(self, kind: str, message: str):
        """Status bar: coloured dot (info/busy/success/warning/error) and one sentence."""
        self.status_dot.configure(text_color=self._STATUS_COLORS[kind])
        self.status_label.configure(text=message)

    def show_view(self, name: str):
        self.current_view = name
        for key, view in self.views.items():
            active = key == name
            if active:
                view.grid(row=0, column=0, sticky="nsew")
            else:
                view.grid_remove()
            self.nav_buttons[key].configure(
                fg_color=t.ACCENT_SOFT if active else "transparent",
                font=t.font("body_bold" if active else "body"),
            )
        if name == "activity":
            self._unseen_problems = 0
            self._update_activity_badge()

    def _update_activity_badge(self):
        n = self._unseen_problems
        self.nav_buttons["activity"].configure(text=f"Activity  ({n})" if n else "Activity")

    def _toggle_theme(self):
        ctk.set_appearance_mode("Dark" if ctk.get_appearance_mode() == "Light" else "Light")

    def _update_theme_button(self):
        light = ctk.get_appearance_mode() == "Light"
        self.theme_button.configure(text="☾ Dark" if light else "☀ Light")

    def _on_appearance_change(self, _mode: str):
        if self._is_closing:
            return
        t.apply_treeview_style(self)
        self._update_theme_button()

    # ------------------------------------------------------------------
    # Activity log
    # ------------------------------------------------------------------

    def log(self, level: str, message: str):
        """Append a structured, timestamped message to the log history and console."""
        entry = (datetime.now().strftime("%H:%M:%S"), level.upper(), message)
        self.log_entries.append(entry)
        self.activity.append(entry)
        if entry[1] in ("WARN", "ERROR") and self.current_view != "activity":
            self._unseen_problems += 1
            self._update_activity_badge()
        # Also print to terminal stdout for CLI diagnostics
        print(format_log_line(entry).strip())

    def clear_log(self):
        self.log_entries.clear()
        self.activity.reload()

    # ------------------------------------------------------------------
    # Organize & undo
    # ------------------------------------------------------------------

    def update_undo_state(self):
        """Global Undo button: says what will be undone, disabled when nothing can be."""
        res = self.last_execution_result
        available = bool(res and res.success_count > 0)
        label = undo_label(res)
        # Two lines so the description fits the sidebar width
        text = "↶ " + label.replace(": ", "  Ctrl+Z\n", 1) if available else "↶ Undo"
        self.undo_button.configure(text=text)
        set_enabled(self.undo_button, available)

    def apply_plan(self, plan: OperationPlan) -> ExecutionResult | None:
        """Execute a previewed organization plan; the view reports the result. None if nothing ran."""
        if self._is_executing:
            return None
        if not plan or plan.affected_count == 0:
            return None

        self._is_executing = True
        try:
            self.set_status("busy", f"Moving {plan.affected_count} files…")
            self.log("INFO", f"Applying organization plan ({plan.affected_count} files)...")

            result = execute_operation_plan(plan)
            result.description = "Organize"  # label for the Undo button
            self.last_execution_result = result
            self.update_undo_state()

            if result.success_count > 0:
                self.log(
                    "SUCCESS",
                    f"Successfully moved {result.success_count} file(s) into category subfolders.",
                )

            if result.failure_count > 0:
                self.log("ERROR", f"{result.failure_count} file(s) could not be moved.")
                for src, _, err in result.failed_moves:
                    self.log("ERROR", f"  Failed: {src.name} — {err}")

            self.set_status(
                "success" if result.failure_count == 0 else "warning",
                f"Organized {result.success_count} files, {result.failure_count} failed.",
            )
            return result
        finally:
            self._is_executing = False

    def execute_undo(self):
        if self._is_executing:
            return
        if not self.last_execution_result or self.last_execution_result.success_count == 0:
            return

        res = self.last_execution_result
        if not messagebox.askyesno(
            "Confirm Undo",
            f"Restore {res.success_count} file(s) back to their original root directory?",
        ):
            return

        self._is_executing = True
        try:
            self.set_status("busy", "Undoing the last move…")
            undone, failed, errors, notes = undo_last_operation(res)

            self.update_undo_state()
            self.organize.banner.hide()  # its "Moved N files" no longer holds

            for note in notes:
                self.log("WARN", note)

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
                    "Next steps:\nReview the Activity view for details on un-restored items.",
                )

            self.set_status(
                "success" if failed == 0 else "error",
                f"Undo finished: {undone} restored, {failed} failed.",
            )
        finally:
            self._is_executing = False

    # ------------------------------------------------------------------
    # Duplicate scan (background thread)
    # ------------------------------------------------------------------

    def start_duplicate_scan(self):
        if self._is_scanning or self._is_executing:
            return

        if not self.current_path.exists() or not self.current_path.is_dir():
            messagebox.showerror("Error", "Selected target directory does not exist.")
            return

        self._is_scanning = True
        # A fresh event per scan, so a stale worker can never be revived
        self._cancel_scan = threading.Event()
        self._scan_generation += 1
        current_gen = self._scan_generation
        target_dir = self.current_path

        self.duplicates.set_scanning(True)

        self.set_status("busy", f"Scanning {self.current_path.name} for duplicates…")
        self.log("INFO", f"Initiated duplicate scan in: {self.current_path}")

        worker = threading.Thread(
            target=self._duplicate_scan_worker,
            args=(target_dir, current_gen, self._cancel_scan),
            daemon=True,
        )
        worker.start()

    def cancel_duplicate_scan(self):
        if self._is_scanning:
            self._cancel_scan.set()
            self.duplicates.set_progress_text("Cancelling scan...")
            self.set_status("warning", "Cancelling the scan…")
            self.log("WARN", "User requested duplicate scan cancellation.")

    def _duplicate_scan_worker(self, target_dir: Path, gen: int, cancel_event: threading.Event):
        def on_prog(progress: ScanProgress):
            self._safe_after(self._on_duplicate_scan_progress, progress, gen)

        try:
            groups = scan_duplicates(
                target_dir=target_dir,
                cancel_event=cancel_event,
                on_progress=on_prog,
            )
            self._safe_after(self._on_duplicate_scan_complete, groups, target_dir, gen)
        except Exception as exc:
            self._safe_after(self._on_duplicate_scan_error, str(exc), gen)

    def _on_duplicate_scan_error(self, err_msg: str, gen: int):
        if self._is_closing or not self.winfo_exists():
            return
        if gen != self._scan_generation:
            return

        self._is_scanning = False
        self.duplicates.set_scanning(False)

        self.set_status("error", "Duplicate scan failed. See Activity for details.")
        self.duplicates.set_progress_text(f"Scan error: {err_msg}")
        self.log("ERROR", f"Duplicate scan failed: {err_msg}")

    def _on_duplicate_scan_progress(self, progress: ScanProgress, gen: int):
        if self._is_closing or not self.winfo_exists():
            return
        if gen != self._scan_generation:
            return
        self.duplicates.show_progress(progress)

    def _on_duplicate_scan_complete(self, groups: list[DuplicateGroup], target_dir: Path, gen: int):
        if self._is_closing or not self.winfo_exists():
            return

        if gen != self._scan_generation or target_dir.resolve() != self.current_path.resolve():
            # Discard results from a stale scan generation or directory switch
            return

        self._is_scanning = False
        self.duplicate_scan_dir = target_dir
        self.duplicates.set_scanning(False)

        if self._cancel_scan.is_set():
            self.set_status("warning", "Duplicate scan cancelled.")
            self.duplicates.set_progress_text("Scan cancelled by user.")
            return

        self.duplicate_groups = groups
        total_reclaimable = format_size(sum(g.reclaimable_bytes for g in groups))
        total_dup_files = sum(len(g.duplicates) for g in groups)

        if not groups:
            self.set_status("success", "Scan finished: no duplicates found.")
            self.duplicates.set_progress_text("Scan complete: No duplicates found.")
            self.log("INFO", "Duplicate scan completed: 0 duplicates detected.")
        else:
            self.set_status(
                "success",
                f"Scan finished: {len(groups)} groups, {total_dup_files} extra copies, {total_reclaimable} reclaimable.",
            )
            self.duplicates.set_progress_text(
                f"Found {len(groups)} group(s) — {total_dup_files} duplicate files ({total_reclaimable} reclaimable)"
            )
            self.log(
                "SUCCESS",
                f"Found {len(groups)} duplicate group(s), {total_dup_files} redundant copies ({total_reclaimable} reclaimable).",
            )

        self.duplicates.render_groups()

    # ------------------------------------------------------------------
    # Duplicate actions (move / trash)
    # ------------------------------------------------------------------

    def _get_selected_duplicate_paths(self) -> list[Path]:
        return [f.path for group in self.duplicate_groups for f in group.files if f.selected]

    def _refuse_if_no_kept_copy(self) -> bool:
        """Show an error and return True when some group would lose every copy."""
        unkept = groups_without_kept_copy(self.duplicate_groups)
        if not unkept:
            return False
        # Number groups the way the results list does ("Group N").
        names = "\n".join(
            f"• Group {idx}: {g.files[0].path.name}"
            for idx, g in enumerate(self.duplicate_groups, 1)
            if g in unkept
        )
        messagebox.showerror(
            "Every Copy Selected",
            f"Every copy is selected in these group(s):\n{names}\n\n"
            "Leave at least one copy unselected in each group to keep it.",
        )
        return True

    def _unchanged_selection(self) -> list[Path]:
        """Re-check selected files against the scan and log every skipped file."""
        safe, skips = filter_unchanged_duplicates(self.duplicate_groups)
        for reason in skips:
            self.log("WARN", f"Skipped {reason}")
        return safe

    def _scan_dir_mismatch(self, verb: str) -> bool:
        """Refuse (and say so) when the scan was made for another folder."""
        if (
            self.duplicate_scan_dir is not None
            and self.duplicate_scan_dir.resolve() == self.current_path.resolve()
        ):
            return False
        messagebox.showerror(
            "Mismatched Directory",
            "Target folder has changed since the duplicate scan was performed. "
            f"Please re-scan the current folder before {verb} duplicates.",
        )
        return True

    def move_selected_duplicates(self):
        if self._is_executing:
            return
        if self._scan_dir_mismatch("isolating"):
            return

        selected = self._get_selected_duplicate_paths()
        if not selected:
            messagebox.showinfo("No Files Selected", "Please select at least one duplicate file to isolate.")
            return
        if self._refuse_if_no_kept_copy():
            return

        if not messagebox.askyesno(
            "Confirm Isolation",
            f"Move {len(selected)} selected duplicate file(s) into 'Duplicates/' folder?\n(You can undo this operation afterward).",
        ):
            return

        self._is_executing = True
        try:
            selected = self._unchanged_selection()
            ok, plan, err = build_duplicate_move_plan(selected, self.current_path, "Duplicates")
            if not ok:
                messagebox.showerror("Error", err or "Failed to build move plan")
                return
            if plan.skipped_count:
                self.log("WARN", f"Skipped {plan.skipped_count} selected file(s):")
                for item in plan.items:
                    if item.status == OperationStatus.SKIPPED:
                        self.log("WARN", f"  {item.source.name} — {item.skip_reason}")

            result = execute_operation_plan(plan)
            result.description = "Duplicates moved"  # label for the Undo button
            self.last_execution_result = result
            self.update_undo_state()

            if result.success_count > 0:
                self.log(
                    "SUCCESS",
                    f"Moved {result.success_count} duplicate file(s) into 'Duplicates/' folder (Undo supported).",
                )

            if result.failure_count > 0:
                self.log("ERROR", f"{result.failure_count} duplicate file(s) could not be moved.")
                for src, _, err_msg in result.failed_moves:
                    self.log("ERROR", f"  Failed: {src.name} — {err_msg}")
                messagebox.showwarning(
                    "Partial Duplicate Isolation",
                    f"What happened:\n{result.success_count} file(s) moved, but {result.failure_count} failed.\n\n"
                    "Why:\nOne or more files were modified, locked, or removed externally.\n\n"
                    "Next steps:\nCheck the Activity view for detailed diagnostics.",
                )

            status_msg = f"Isolated {result.success_count} duplicate(s)."
            if result.failure_count > 0:
                status_msg += f" ({result.failure_count} failed)"
            self.set_status("success" if result.failure_count == 0 else "warning", status_msg)

            # Update duplicate model preserving unaffected groups
            successful_paths = {r.source for r in result.successful_moves}
            self.duplicate_groups = update_duplicate_groups_after_removal(
                self.duplicate_groups, successful_paths
            )
            self.duplicates.render_groups()
        finally:
            self._is_executing = False

    def trash_selected_duplicates(self):
        if self._is_executing:
            return
        if self._scan_dir_mismatch("trashing"):
            return

        selected = self._get_selected_duplicate_paths()
        if not selected:
            messagebox.showinfo("No Files Selected", "Please select at least one duplicate file to trash.")
            return
        if self._refuse_if_no_kept_copy():
            return

        # The scan is non-recursive, so every selected file is on this folder's drive.
        may_be_permanent = trash_may_be_permanent(self.duplicate_scan_dir)
        confirm_text = f"Send {len(selected)} selected duplicate file(s) to the {trash_label()}?\n\nNote: Undo from application is unavailable for trashed files."
        if may_be_permanent:
            confirm_text += f"\n\nFiles on this drive may be deleted permanently instead of being sent to the {trash_label()}."
        if not messagebox.askyesno(f"Confirm {trash_label().title()}", confirm_text):
            return

        self._is_executing = True
        try:
            successful_paths: set[Path] = set()
            failed_count = 0

            for f in self._unchanged_selection():
                ok, err = move_to_system_trash(f)
                if ok:
                    successful_paths.add(f)
                    self.log("INFO", f"Trashed duplicate: {f.name}")
                else:
                    failed_count += 1
                    self.log("ERROR", f"Could not trash {f.name}: {err}")

            success_count = len(successful_paths)

            if may_be_permanent:
                self.log("WARN", f"Removed {success_count} file(s) ({failed_count} failed). Files on this drive may have been deleted permanently instead of being sent to the {trash_label()}.")
            else:
                self.log("SUCCESS", f"Sent {success_count} file(s) to {trash_label()} ({failed_count} failed).")
            status_msg = f"Trashed {success_count} file(s)."
            if failed_count > 0:
                status_msg += f" ({failed_count} failed)"
            self.set_status("success" if failed_count == 0 else "warning", status_msg)

            if failed_count > 0:
                messagebox.showwarning(
                    "Trash Finished with Errors",
                    f"What happened:\n{success_count} file(s) moved to trash, but {failed_count} encountered errors.\n\n"
                    "Why:\nSome files may be locked, symbolic links, or removed externally.\n\n"
                    "Next steps:\nReview the Activity view for details.",
                )

            # Update duplicate model preserving unaffected groups
            self.duplicate_groups = update_duplicate_groups_after_removal(
                self.duplicate_groups, successful_paths
            )
            self.duplicates.render_groups()
        finally:
            self._is_executing = False

    # ------------------------------------------------------------------
    # Native Directory Selection
    # ------------------------------------------------------------------

    def _ask_directory_native(self, initial_dir: Path) -> str:
        initial_str = str(initial_dir)

        is_linux = sys.platform.startswith("linux")

        if is_linux and shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", "--directory", f"--filename={initial_str}/"]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return res.stdout.strip()
                if res.returncode == 1:
                    return ""
            except (subprocess.SubprocessError, OSError):
                self.log("WARN", "Zenity dialog failed, attempting fallback.")

        if is_linux and shutil.which("kdialog"):
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

    def _invalidate_target_dependent_state(self, new_path: Path):
        """
        Invalidate all cached plans, scan results, and UI elements tied to the target directory.
        Cancels any ongoing scan and increments generation token to discard stale async worker results.
        """
        self.current_path = new_path
        self._scan_generation += 1
        if self._is_scanning:
            self._cancel_scan.set()
            # The stale worker's callbacks are ignored, so reset the scan UI here
            self._is_scanning = False
            self.duplicates.set_scanning(False)
        self.duplicate_groups.clear()
        self.duplicate_scan_dir = None

        self.organize.clear_preview("Folder changed", "Preview to see what will move in this folder.")
        self.duplicates.render_groups()
        self.duplicates.set_progress_text("Ready to scan root folder for byte-identical duplicates.")

    def select_folder(self):
        initial_dir = self.current_path if self.current_path.exists() else Path.home()
        chosen = self._ask_directory_native(initial_dir)
        if not chosen:
            return

        new_dir = Path(chosen)
        try:
            if new_dir.resolve() == self.current_path.resolve():
                return
        except OSError:
            pass

        self._invalidate_target_dependent_state(new_dir)
        self._show_folder()

        self.set_status("info", f"Folder changed to {self.current_path.name}. Nothing has changed yet.")
        self.log("INFO", f"Active folder changed to: {self.current_path}")

