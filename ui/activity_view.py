"""Activity view: the in-app log."""

from __future__ import annotations

import customtkinter as ctk

from platform_utils import mono_font
from ui.formatting import format_log_line
from ui.theme import THEME


class ActivityView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, pady=(0, 8), sticky="ew")

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
            command=app.clear_log,
        ).pack(side="right")

        self.log_box = ctk.CTkTextbox(
            self,
            font=(mono_font(), 11),
            corner_radius=8,
            fg_color=THEME["surface"],
            border_width=1,
            border_color=THEME["border"],
            text_color=THEME["text_primary"],
            activate_scrollbars=True,
        )
        self.log_box.grid(row=1, column=0, sticky="nsew")

    def append(self, entry: tuple[str, str, str]):
        self.log_box.insert("end", format_log_line(entry))
        self.log_box.see("end")

    def reload(self):
        self.log_box.delete("1.0", "end")
        for entry in self.app.log_entries:
            self.log_box.insert("end", format_log_line(entry))
        self.log_box.see("end")
