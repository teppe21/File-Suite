"""Activity view: the in-app log with level colours, a filter, copy and save."""

from __future__ import annotations

from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk

from platform_utils import mono_font
from ui import theme as t
from ui.formatting import format_log_line
from ui.widgets import secondary_button, segmented, tooltip

_LEVEL_COLORS = {"INFO": t.TEXT, "SUCCESS": t.SUCCESS, "WARN": t.WARNING, "ERROR": t.DANGER}
_FILTERS = {"All": None, "Warnings": {"WARN"}, "Errors": {"ERROR"}}


class ActivityView(ctk.CTkFrame):
    TITLE = "Activity"
    SUBTITLE = "Everything File Suite did in this session, including skipped files and errors."

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._levels: set[str] | None = None  # None = show every level

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.filter = segmented(bar, list(_FILTERS), self._on_filter)
        self.filter.set("All")
        self.filter.pack(side="left")
        for text, command, tip in (
            ("Clear", app.clear_log, "Empty the log for this session"),
            ("Save As…", self._save, "Save the whole log as a text file"),
            ("Copy All", self._copy, "Copy the whole log to the clipboard"),
        ):
            button = secondary_button(bar, text, command, small=True)
            button.pack(side="right", padx=(6, 0))
            tooltip(button, tip)

        self.log_box = ctk.CTkTextbox(
            self,
            font=(mono_font(), 12),
            corner_radius=t.CARD_RADIUS,
            fg_color=t.SURFACE,
            border_width=1,
            border_color=t.SEPARATOR,
            text_color=t.TEXT,
            scrollbar_button_color=t.FIELD_BORDER,
            scrollbar_button_hover_color=t.TEXT_MUTED,
            wrap="none",
            state="disabled",
        )
        self.log_box.grid(row=1, column=0, sticky="nsew")
        self.apply_colors()

    def apply_colors(self):
        """tk.Text tags take one colour, so re-apply on every appearance change."""
        for level, token in _LEVEL_COLORS.items():
            self.log_box.tag_config(level, foreground=t.pick(token))

    def _insert(self, entry: tuple[str, str, str]):
        self.log_box.insert("end", format_log_line(entry), entry[1])

    def append(self, entry: tuple[str, str, str]):
        if self._levels is not None and entry[1] not in self._levels:
            return
        self.log_box.configure(state="normal")
        self._insert(entry)
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def reload(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        for entry in self.app.log_entries:
            if self._levels is None or entry[1] in self._levels:
                self._insert(entry)
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def _on_filter(self, value: str):
        self._levels = _FILTERS[value]
        self.reload()

    def _all_text(self) -> str:
        return "".join(format_log_line(e) for e in self.app.log_entries)

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self._all_text())
        self.app.set_status("success", f"Copied {len(self.app.log_entries)} log lines to the clipboard.")

    def _save(self):
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save activity log",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"file-suite-activity-{datetime.now():%Y%m%d-%H%M}.txt",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._all_text())
        except OSError as exc:
            self.app.log("ERROR", f"Could not save the activity log: {exc}")
            self.app.set_status("error", "Could not save the activity log. See the last line.")
            return
        self.app.set_status("success", f"Activity log saved to {path}.")
