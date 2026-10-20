"""Duplicates view: scan controls, results tree with tick boxes, and actions."""

from __future__ import annotations

from datetime import datetime
from tkinter import ttk

import customtkinter as ctk

from models import (
    DuplicateFile,
    DuplicateGroup,
    ExecutionResult,
    ScanProgress,
    clear_duplicate_selection,
    select_all_duplicates,
)
from platform_utils import trash_label
from ui import theme as t
from ui.formatting import format_size, plural, selection_summary
from ui.widgets import (
    Banner,
    Card,
    EmptyState,
    danger_button,
    primary_button,
    scrollbar,
    secondary_button,
    set_default,
    set_enabled,
    tooltip,
)

_COLUMNS = (
    # id, heading, width, stretch, anchor. Widths fit the 880 px minimum window;
    # ttk only stretches columns when there is extra room, never shrinks them.
    ("name", "Name", 144, True, "w"),  # the only stretching column: gets all spare width
    ("size", "Size", 66, False, "e"),
    ("modified", "Modified", 118, False, "w"),
    ("role", "Role", 112, False, "w"),
    ("hash", "SHA-256", 72, False, "w"),
)


def group_label(group: DuplicateGroup) -> str:
    """Parent-row text, also used by the app's "every copy selected" refusal."""
    return f"{group.files[0].path.name} — {plural(len(group.files), 'copy', 'copies')} · {format_size(group.size)} each"


class DuplicatesView(ctk.CTkFrame):
    TITLE = "Duplicates"
    SUBTITLE = "Byte-identical files directly in this folder. Subfolders are not scanned."

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        # Tree row id -> model object, rebuilt with the tree
        self._file_rows: dict[str, tuple[DuplicateFile, str]] = {}  # iid -> (file, parent iid)
        self._group_rows: dict[str, DuplicateGroup] = {}
        self._scanned = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.banner = Banner(self)
        self.banner.grid(row=1, column=0, sticky="ew", pady=(0, 2 * t.SPACE))
        self.banner.hide()

        self._build_scan_bar().grid(row=2, column=0, sticky="ew", pady=(0, 2 * t.SPACE))
        self._build_results().grid(row=3, column=0, sticky="nsew")
        self._build_footer().grid(row=4, column=0, sticky="ew", pady=(2 * t.SPACE, 0))
        self.render_groups()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_scan_bar(self) -> ctk.CTkFrame:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid_columnconfigure(2, weight=1)
        self.scan_button = primary_button(bar, "Scan Folder", self.app.start_duplicate_scan, width=112)
        self.scan_button.grid(row=0, column=0, rowspan=2)
        tooltip(self.scan_button, "Compare every file directly in this folder. Nothing changes.  (Ctrl+Enter)")
        self.cancel_button = secondary_button(bar, "Cancel", self.app.cancel_duplicate_scan, width=80)
        self.cancel_button.grid(row=0, column=1, rowspan=2, padx=(t.SPACE, 0))
        self.cancel_button.grid_remove()
        self.progress_label = ctk.CTkLabel(
            bar, text="", font=t.font("caption"), text_color=t.TEXT_MUTED, anchor="w"
        )
        self.progress_label.grid(row=0, column=2, rowspan=2, padx=2 * t.SPACE, sticky="ew")
        self.progress_bar = ctk.CTkProgressBar(
            bar, height=4, corner_radius=2, progress_color=t.ACCENT, fg_color=t.NEUTRAL
        )
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=2, padx=2 * t.SPACE, sticky="ew")
        self.progress_bar.grid_remove()
        return bar

    def _build_results(self) -> Card:
        card = Card(self)
        body = card.body
        body.grid_rowconfigure(3, weight=1)

        self.summary_label = ctk.CTkLabel(body, text="", font=t.font("headline"), text_color=t.TEXT, anchor="w")
        self.summary_label.grid(row=0, column=0, sticky="w")
        self.selected_label = ctk.CTkLabel(body, text="", font=t.font("body"), text_color=t.TEXT_MUTED, anchor="e")
        self.selected_label.grid(row=0, column=1, sticky="e")
        self.unkept_label = ctk.CTkLabel(body, text="", font=t.font("caption"), text_color=t.DANGER, anchor="e")
        self.unkept_label.grid(row=1, column=0, columnspan=2, sticky="e")

        self.toolbar = ctk.CTkFrame(body, fg_color="transparent")
        self.toolbar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(t.SPACE, t.SPACE))
        for text, command, tip in (
            ("Select Extra Copies", self._select_all, "Tick every copy except the original of each group"),
            ("Clear Selection", self._clear_selection, "Untick everything"),
            ("Expand All", lambda: self._set_open(True), None),
            ("Collapse All", lambda: self._set_open(False), None),
        ):
            button = secondary_button(self.toolbar, text, command, small=True)
            button.pack(side="left", padx=(0, 6))
            if tip:
                tooltip(button, tip)

        self._tree_frame = ctk.CTkFrame(body, fg_color="transparent")
        self._tree_frame.grid(row=3, column=0, columnspan=2, sticky="nsew")
        self._tree_frame.grid_columnconfigure(0, weight=1)
        self._tree_frame.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(self._tree_frame, columns=[c[0] for c in _COLUMNS], show="tree headings")
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=round(52 * scale), minwidth=round(52 * scale), stretch=False, anchor="w")
        for col, heading, width, stretch, anchor in _COLUMNS:
            self.tree.heading(col, text=heading, anchor=anchor)
            self.tree.column(col, width=round(width * scale), minwidth=round(48 * scale), stretch=stretch, anchor=anchor)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar(self._tree_frame, self.tree).grid(row=0, column=1, sticky="ns")
        t.register_tree_tags(
            self.tree,
            {
                "group": {"font": t.tree_font("headline"), "background": t.GROUP_ROW},
                "unkept": {"foreground": t.DANGER, "background": t.DANGER_TINT},
            },
        )
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<space>", self._on_space)
        self.tree.bind("<Delete>", lambda _e: self.app.trash_selected_duplicates())

        self.empty = EmptyState(body, "Scan Folder", self.app.start_duplicate_scan)
        self.empty.grid(row=0, column=0, rowspan=4, columnspan=2, sticky="nsew")
        return card

    def _build_footer(self) -> ctk.CTkFrame:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid_columnconfigure(0, weight=1)
        hint = ctk.CTkLabel(
            footer, text="Click a tick box or press Space to tick a copy.", font=t.font("caption"), text_color=t.TEXT_MUTED
        )
        hint.grid(row=0, column=0, sticky="w")

        def fit_hint(event):
            # The hint only shows when it fits beside the buttons (not in narrow windows).
            room = event.width - self.trash_button.winfo_reqwidth() - self.move_button.winfo_reqwidth()
            if room > hint.winfo_reqwidth() + 2 * t.MARGIN:
                hint.grid()
            else:
                hint.grid_remove()

        footer.bind("<Configure>", fit_hint, add="+")
        self.trash_button = danger_button(footer, "", self.app.trash_selected_duplicates)
        self.trash_button.grid(row=0, column=1, padx=(0, t.SPACE))
        tooltip(
            self.trash_button,
            f"Send the ticked copies to the {trash_label()}. This can't be undone from File Suite.  (Delete)",
        )
        self.move_button = primary_button(footer, "", self.app.move_selected_duplicates)
        self.move_button.grid(row=0, column=2)
        tooltip(self.move_button, "Move the ticked copies into a “Duplicates” folder here. You can undo this.  (Ctrl+M)")
        return footer

    # ------------------------------------------------------------------
    # Scan state (driven by the app)
    # ------------------------------------------------------------------

    def set_scanning(self, scanning: bool):
        set_enabled(self.scan_button, not scanning)
        if scanning:
            self.banner.hide()
            self.cancel_button.grid()
            self.progress_bar.set(0)
            self.progress_bar.grid()
            self.progress_label.grid_configure(rowspan=1)
            if not self.app.duplicate_groups:
                self.empty.set("Scanning…", "Comparing file sizes, then contents.", button_text="")
        else:
            self.cancel_button.grid_remove()
            self.progress_bar.grid_remove()
            self.progress_label.grid_configure(rowspan=2)

    def set_progress_text(self, text: str):
        self.progress_label.configure(text=text)

    def show_progress(self, progress: ScanProgress):
        if progress.total > 0:
            self.progress_bar.set(progress.current / progress.total)
        self.set_progress_text(
            f"{progress.step} — {progress.files_processed} of {progress.total} files · "
            f"{plural(progress.groups_found, 'group')} so far"
        )

    def scan_finished(self):
        self._scanned = True
        self.render_groups()
        # Keyboard users can tick (Space), trash (Delete) and navigate (arrows) right away.
        first_file = next(iter(self._file_rows), None)
        if first_file and self.winfo_ismapped():
            self.tree.focus_set()
            self.tree.focus(first_file)
            self.tree.selection_set(first_file)

    def reset(self):
        """Folder changed: back to the "no scan yet" state."""
        self._scanned = False
        self.banner.hide()
        self.set_progress_text("")
        self.render_groups()

    def mark_stale(self):
        """Files moved since the scan (organize run or undo); results may no longer match."""
        if self._scanned:
            self.banner.show(
                "warning",
                "Results may be out of date",
                "Files in this folder were moved after the scan. Moving or trashing still "
                "re-checks every file first.",
                ("Rescan", self.app.start_duplicate_scan),
            )

    # ------------------------------------------------------------------
    # Results tree
    # ------------------------------------------------------------------

    def render_groups(self):
        """Rebuild the tree; only after a scan or after files were removed."""
        groups = self.app.duplicate_groups
        self.tree.delete(*self.tree.get_children())
        self._file_rows.clear()
        self._group_rows.clear()

        if not groups:
            if self._scanned:
                self.empty.set(
                    "No duplicates found",
                    "No two files directly in this folder have identical content.",
                    button_text="Scan Again",
                )
            else:
                self.empty.set(
                    "No scan yet",
                    "Scan this folder to find files with identical content. Scanning changes nothing.",
                    button_text="Scan Folder",
                )
            self.empty.grid()
            self._update_summary()
            return

        self.empty.grid_remove()
        for group in groups:
            gid = self.tree.insert("", "end", text="", open=True, values=("", "", "", "", group.sha256[:12]))
            self._group_rows[gid] = group
            for f in group.files:
                fid = self.tree.insert(gid, "end")
                self._file_rows[fid] = (f, gid)
                self._refresh_file_row(fid)
            self._refresh_group_row(gid)
        self._update_summary()

    def _refresh_file_row(self, fid: str):
        f, _ = self._file_rows[fid]
        if f.selected:
            role = "Remove"
        elif f.is_original:
            role = "Keep (original)"
        else:
            role = "Keep"
        modified = (
            datetime.fromtimestamp(f.mtime_ns / 1e9).strftime("%Y-%m-%d %H:%M") if f.mtime_ns else "—"
        )
        self.tree.item(
            fid,
            text="",
            image=t.checkbox_image(self, f.selected),
            values=(f.path.name, format_size(f.size), modified, role, ""),
        )

    def _refresh_group_row(self, gid: str):
        group = self._group_rows[gid]
        unkept = all(f.selected for f in group.files)
        label = group_label(group)
        self.tree.item(
            gid,
            values=(
                f"{label} — Every copy selected, one must stay" if unkept else label,
                "",
                "",
                "Keep one" if unkept else "",
                group.sha256[:12],
            ),
            tags=("group", "unkept") if unkept else ("group",),
        )

    def _update_summary(self):
        s = selection_summary(self.app.duplicate_groups)
        widgets = (self.summary_label, self.selected_label, self.toolbar, self._tree_frame)
        for widget in widgets:
            if s.groups:
                widget.grid()
            else:
                widget.grid_remove()
        self.summary_label.configure(
            text=f"{plural(s.groups, 'group')} · {plural(s.extra_copies, 'extra copy', 'extra copies')} · "
            f"{format_size(s.reclaimable_bytes)} reclaimable"
        )
        self.selected_label.configure(
            text=f"Selected: {plural(s.selected_files, 'file')} · {format_size(s.selected_bytes)}"
        )
        if s.groups_without_kept_copy:
            self.unkept_label.configure(
                text=f"{plural(s.groups_without_kept_copy, 'group')} with every copy selected: "
                "leave one copy unticked in each"
            )
            self.unkept_label.grid()
        else:
            self.unkept_label.grid_remove()
        count = s.selected_files
        set_enabled(self.move_button, count > 0)
        set_enabled(self.trash_button, count > 0)
        files = f"{plural(count, 'File', 'Files')} " if count else ""
        self.move_button.configure(text=f"Move {files}to “Duplicates”")
        self.trash_button.configure(text=f"Move {files}to {trash_label().title()}")
        # One default action: Scan until there are results, then Move.
        set_default(self.scan_button, s.groups == 0)

    # ------------------------------------------------------------------
    # Ticking
    # ------------------------------------------------------------------

    def _toggle(self, iids):
        rows = [iid for iid in iids if iid in self._file_rows]
        if not rows:
            return
        new_state = not all(self._file_rows[iid][0].selected for iid in rows)
        parents = set()
        for iid in rows:
            f, gid = self._file_rows[iid]
            f.selected = new_state
            self._refresh_file_row(iid)
            parents.add(gid)
        for gid in parents:
            self._refresh_group_row(gid)
        self._update_summary()

    def _on_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid not in self._file_rows or self.tree.identify_column(event.x) != "#0":
            return None
        selection = self.tree.selection()
        if iid in selection and len(selection) > 1:
            self._toggle(selection)
            return "break"  # keep the multi-selection
        self._toggle([iid])
        return None

    def _on_space(self, _event):
        self._toggle(self.tree.selection() or [self.tree.focus()])
        return "break"

    def _select_all(self):
        select_all_duplicates(self.app.duplicate_groups)
        self._refresh_all_rows()

    def _clear_selection(self):
        clear_duplicate_selection(self.app.duplicate_groups)
        self._refresh_all_rows()

    def _refresh_all_rows(self):
        # Updates row text in place, so scroll position and open state are kept.
        for fid in self._file_rows:
            self._refresh_file_row(fid)
        for gid in self._group_rows:
            self._refresh_group_row(gid)
        self._update_summary()

    def _set_open(self, is_open: bool):
        for gid in self._group_rows:
            self.tree.item(gid, open=is_open)

    # ------------------------------------------------------------------
    # Results of actions (reported by the app)
    # ------------------------------------------------------------------

    def report_move(self, result: ExecutionResult, skipped: int):
        moved, failed = result.success_count, result.failure_count
        if failed == 0 and skipped == 0:
            self.banner.show(
                "success",
                f"Moved {plural(moved, 'file')} to “Duplicates”",
                "Use Undo in the toolbar to put them back.",
                ("Undo", self.app.execute_undo),
            )
            return
        self.banner.show(
            "warning" if moved else "error",
            f"Moved {moved} of {plural(moved + failed + skipped, 'selected file')}",
            f"What happened: {plural(failed, 'file')} failed and {skipped} were skipped.  "
            "Why: they were changed, locked or removed after the scan.  "
            "Next steps: open Activity for the reason per file.",
            ("Open Activity", lambda: self.app.show_view("activity")),
        )

    def report_trash(self, removed: int, failed: int, skipped: int, may_be_permanent: bool):
        where = f"to the {trash_label()}"
        if may_be_permanent:
            text = f"Files on this drive may have been deleted permanently instead of going {where}."
        else:
            text = f"Restore them from the {trash_label()} in your file manager if needed."
        if failed == 0 and skipped == 0:
            self.banner.show("warning" if may_be_permanent else "success", f"Removed {plural(removed, 'file')}", text)
            return
        self.banner.show(
            "warning" if removed else "error",
            f"Removed {removed} of {plural(removed + failed + skipped, 'selected file')}",
            f"What happened: {plural(failed, 'file')} failed and {skipped} were skipped.  "
            "Why: they were locked, links, or changed or removed after the scan.  "
            "Next steps: open Activity for details.  " + text,
            ("Open Activity", lambda: self.app.show_view("activity")),
        )
