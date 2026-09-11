import datetime
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.parse

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

from core import (
    CATEGORIES,
    build_collision_safe_path,
    classify_extension,
    collect_selected_extensions,
    group_by_size,
    resolve_destination,
)


# ---------------------------------------------------------------------------
# Path helpers (works both from source and from a PyInstaller bundle)
# ---------------------------------------------------------------------------

def _resource_path(name: str) -> Path:
    """Return the on-disk path of a bundled resource."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent
    return base / name


# ---------------------------------------------------------------------------
# Appearance
# ---------------------------------------------------------------------------

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


# ---------------------------------------------------------------------------
# Duplicate action dialog
# ---------------------------------------------------------------------------

class DuplicateActionDialog(ctk.CTkToplevel):
    """Modal dialog offering options for duplicate handling."""

    def __init__(self, parent, count: int):
        super().__init__(parent)
        self.title("Duplicates Found")
        self.geometry("420x240")
        self.resizable(False, False)
        self.action: str | None = None

        self.transient(parent)

        # Delay UI construction until the window is mapped. This avoids a
        # known CustomTkinter issue on Linux (especially under Wayland)
        # where the children of a CTkToplevel are not rendered when
        # grab_set() is called too early during __init__.
        self.after(100, lambda: self._build_ui(parent, count))

    def _build_ui(self, parent, count: int):
        label = ctk.CTkLabel(
            self,
            text=f"Found {count} duplicate file(s).",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        label.pack(pady=(20, 5))

        sublabel = ctk.CTkLabel(
            self,
            text="Choose how you would like to handle these duplicates:",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
        )
        sublabel.pack(pady=(0, 20))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20)

        ctk.CTkButton(
            btn_frame,
            text="📁 Move to 'Duplicates' Folder",
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            command=self._on_folder,
        ).pack(fill="x", pady=4)

        ctk.CTkButton(
            btn_frame,
            text="🗑️ Move to System Trash",
            fg_color="#DC2626",
            hover_color="#B91C1C",
            command=self._on_trash,
        ).pack(fill="x", pady=4)

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            fg_color="transparent",
            border_width=1,
            text_color="gray80",
            command=self.destroy,
        ).pack(fill="x", pady=4)

        # Now that the UI exists, make the dialog modal and bring it forward.
        self.lift()
        self.focus_force()
        self.grab_set()

    def _on_folder(self):
        self.action = "folder"
        self.destroy()

    def _on_trash(self):
        self.action = "trash"
        self.destroy()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class FileOrganizerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("File Suite — Modern Desktop Organizer & Duplicate Cleaner")
        self.geometry("860x720")
        self.minsize(780, 600)

        self._set_window_icon()

        default_downloads = Path.home() / "Downloads"
        self.current_path = default_downloads if default_downloads.exists() else Path.home()

        self.cat_vars = {cat: ctk.BooleanVar(value=True) for cat in CATEGORIES}

        self._build_ui()

    # ------------------------------------------------------------------
    # Window icon
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

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=24, pady=(16, 4), sticky="ew")

        ctk.CTkLabel(
            header_frame, text="File Suite",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(side="left")

        ctk.CTkLabel(
            header_frame,
            text="Custom Folder Grouping & Duplicate Cleaner",
            font=ctk.CTkFont(size=12),
            text_color="gray60",
        ).pack(side="left", padx=(12, 0), pady=(4, 0))

        # Directory picker
        picker_card = ctk.CTkFrame(self, corner_radius=12)
        picker_card.grid(row=1, column=0, padx=24, pady=6, sticky="ew")
        picker_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            picker_card, text="Target Folder:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, padx=(16, 10), pady=12, sticky="w")

        self.path_entry = ctk.CTkEntry(
            picker_card, height=36, corner_radius=8, border_width=1,
            placeholder_text="Select a directory...",
        )
        self.path_entry.insert(0, str(self.current_path))
        self.path_entry.configure(state="disabled")
        self.path_entry.grid(row=0, column=1, padx=5, pady=12, sticky="ew")

        ctk.CTkButton(
            picker_card, text="Browse...", height=36, corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.select_folder, width=100,
        ).grid(row=0, column=2, padx=(5, 16), pady=12)

        # Organization panel
        organize_card = ctk.CTkFrame(self, corner_radius=12)
        organize_card.grid(row=2, column=0, padx=24, pady=6, sticky="ew")
        organize_card.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(
            organize_card, text="File Organization & Grouping Rules",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="gray80",
        ).grid(row=0, column=0, columnspan=2, padx=16, pady=(12, 6), sticky="w")

        cb_frame = ctk.CTkFrame(organize_card, fg_color="transparent")
        cb_frame.grid(row=1, column=0, columnspan=2, padx=16, pady=4, sticky="ew")

        for col, (cat_name, var) in enumerate(self.cat_vars.items()):
            ctk.CTkCheckBox(
                cb_frame, text=cat_name, variable=var,
                font=ctk.CTkFont(size=12),
            ).grid(row=0, column=col, padx=(0, 14), pady=4, sticky="w")

        ctk.CTkLabel(
            organize_card,
            text="Additional Extensions (comma-separated, e.g. .iso, .blend):",
            font=ctk.CTkFont(size=11), text_color="gray70",
        ).grid(row=2, column=0, columnspan=2, padx=16, pady=(8, 2), sticky="w")

        self.custom_ext_entry = ctk.CTkEntry(
            organize_card, height=32, corner_radius=6,
            placeholder_text="Optional custom extensions...",
        )
        self.custom_ext_entry.grid(row=3, column=0, columnspan=2, padx=16, pady=(0, 8), sticky="ew")

        ctk.CTkLabel(
            organize_card,
            text="Destination Subfolder Name (for grouped items):",
            font=ctk.CTkFont(size=11), text_color="gray70",
        ).grid(row=4, column=0, padx=16, pady=(4, 2), sticky="w")

        self.custom_folder_entry = ctk.CTkEntry(
            organize_card, height=32, corner_radius=6,
            placeholder_text="e.g. Custom_Group (Leave blank to use default categories)",
        )
        self.custom_folder_entry.grid(row=5, column=0, padx=16, pady=(0, 14), sticky="ew")

        ctk.CTkButton(
            organize_card, text="⚡ Group Selected Types",
            height=36, corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.organize_selected,
            fg_color="#2563EB", hover_color="#1D4ED8",
        ).grid(row=5, column=1, padx=(10, 16), pady=(0, 14), sticky="ew")

        # Duplicate section
        dup_card = ctk.CTkFrame(self, corner_radius=12)
        dup_card.grid(row=3, column=0, padx=24, pady=6, sticky="ew")
        dup_card.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            dup_card, text="🔍 Find Duplicates in Root Directory",
            height=38, corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.find_duplicates,
            fg_color="#059669", hover_color="#047857",
        ).grid(row=0, column=0, padx=16, pady=10, sticky="ew")

        # Log
        log_card = ctk.CTkFrame(self, corner_radius=12)
        log_card.grid(row=4, column=0, padx=24, pady=(6, 16), sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            log_card, text="Activity Console",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="gray70",
        ).grid(row=0, column=0, padx=16, pady=(10, 2), sticky="w")

        self.log_box = ctk.CTkTextbox(
            log_card, font=("Monospace", 12),
            corner_radius=8, activate_scrollbars=True,
        )
        self.log_box.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="nsew")

        self.log("System initialized. Configure options and select an operation.\n")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, message: str):
        try:
            self.log_box.insert("end", f"{message}\n")
            self.log_box.see("end")
        except Exception:
            print(message)

    # ------------------------------------------------------------------
    # Directory picker
    # ------------------------------------------------------------------

    def _ask_directory_native(self, initial_dir: Path) -> str:
        initial_str = str(initial_dir)

        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", "--directory",
                       f"--filename={initial_str}/"]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return res.stdout.strip()
                if res.returncode == 1:
                    return ""
            except Exception:
                pass

        if shutil.which("kdialog"):
            try:
                cmd = ["kdialog", "--getexistingdirectory", initial_str]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return res.stdout.strip()
                if res.returncode == 1:
                    return ""
            except Exception:
                pass

        try:
            return filedialog.askdirectory(initialdir=initial_str)
        except Exception as exc:
            self.log(f"[WARNING] Directory dialog failed: {exc}")
            return ""

    def select_folder(self):
        initial_dir = self.current_path if self.current_path.exists() else Path.home()
        chosen_dir = self._ask_directory_native(initial_dir)
        if not chosen_dir:
            return
        self.current_path = Path(chosen_dir)
        self.path_entry.configure(state="normal")
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, str(self.current_path))
        self.path_entry.configure(state="disabled")
        self.log(f"[SELECTED] Active folder: {self.current_path}")

    # ------------------------------------------------------------------
    # Organization
    # ------------------------------------------------------------------

    def organize_selected(self):
        target_dir = self.current_path

        if not target_dir.exists() or not target_dir.is_dir():
            self.log("[ERROR] The selected target directory does not exist!")
            return

        selected_exts = collect_selected_extensions(
            {cat: var.get() for cat, var in self.cat_vars.items()},
            self.custom_ext_entry.get(),
        )
        if not selected_exts:
            messagebox.showwarning(
                "No Extensions Selected",
                "Please select at least one file category or enter custom extensions.",
            )
            return

        custom_folder_name = self.custom_folder_entry.get().strip()

        # If the user supplied a custom destination, validate it *before*
        # touching any file.
        validated_destination: Path | None = None
        if custom_folder_name:
            ok, result = resolve_destination(target_dir, custom_folder_name)
            if not ok:
                messagebox.showerror("Invalid destination folder name", str(result))
                self.log(f"[ERROR] Invalid destination folder name: {result}")
                return
            validated_destination = result  # type: ignore[assignment]

        self.log(f"\n--- ORGANIZING ROOT FILES: {target_dir} ---")
        moved_count = 0

        for item in target_dir.iterdir():
            if item.is_dir() or item.name.startswith("."):
                continue

            try:
                ext = item.suffix.lower()
                full_ext = "".join(item.suffixes).lower()
            except Exception:
                continue

            if ext not in selected_exts and full_ext not in selected_exts:
                continue

            if validated_destination is not None:
                cat_dir = validated_destination
                dest_category_label = validated_destination.name
            else:
                dest_category_label = classify_extension(ext, full_ext) or "Misc"
                cat_dir = target_dir / dest_category_label

            try:
                cat_dir.mkdir(exist_ok=True)
            except OSError as exc:
                self.log(f"[ERROR] Could not create '{cat_dir.name}': {exc}")
                continue

            dest_path = build_collision_safe_path(cat_dir, item.name)

            try:
                shutil.move(str(item), str(dest_path))
            except OSError as exc:
                self.log(f"[ERROR] Could not move {item.name}: {exc}")
                continue

            self.log(f"[MOVED] {item.name} ➔ {dest_category_label}/{dest_path.name}")
            moved_count += 1

        self.log(f"--- Task Complete: {moved_count} file(s) organized. ---\n")

    # ------------------------------------------------------------------
    # Hashing / trash
    # ------------------------------------------------------------------

    def _calculate_sha256(self, file_path: Path) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as fh:
            while chunk := fh.read(64 * 1024):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _move_to_system_trash(self, file_path: Path):
        trash_files_dir = Path.home() / ".local/share/Trash/files"
        trash_info_dir = Path.home() / ".local/share/Trash/info"

        try:
            trash_files_dir.mkdir(parents=True, exist_ok=True)
            trash_info_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OSError(f"Could not access trash directory: {exc}") from exc

        dest_path = build_collision_safe_path(trash_files_dir, file_path.name)

        info_path = trash_info_dir / f"{dest_path.name}.trashinfo"
        deletion_date = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        escaped_path = urllib.parse.quote(str(file_path.absolute()))
        info_content = (
            f"[Trash Info]\nPath={escaped_path}\nDeletionDate={deletion_date}\n"
        )

        with open(info_path, "w", encoding="utf-8") as fh:
            fh.write(info_content)

        shutil.move(str(file_path), str(dest_path))

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    def find_duplicates(self):
        target_dir = self.current_path

        if not target_dir.exists() or not target_dir.is_dir():
            self.log("[ERROR] The selected target directory does not exist!")
            return

        self.log(f"\n--- SCANNING FOR DUPLICATES: {target_dir} ---")

        files = [
            f for f in target_dir.iterdir()
            if f.is_file() and not f.name.startswith(".")
        ]

        if not files:
            self.log("No valid files found in the root folder to process.")
            return

        # Stage 1: group by size. Only groups with >= 2 members need hashing.
        size_groups = group_by_size(files)
        candidate_files = [f for group in size_groups.values() if len(group) >= 2 for f in group]

        if not candidate_files:
            self.log("No duplicate files detected.")
            return

        # Stage 2: hash candidates.
        hashes: dict[str, Path] = {}
        duplicates: list[tuple[Path, Path]] = []

        for file in candidate_files:
            try:
                file_hash = self._calculate_sha256(file)
            except OSError as exc:
                self.log(f"[ERROR] Could not read {file.name}: {exc}")
                continue

            if file_hash in hashes:
                duplicates.append((file, hashes[file_hash]))
            else:
                hashes[file_hash] = file

        if not duplicates:
            self.log("No duplicate files detected.")
            return

        self.log(f"Found {len(duplicates)} duplicate file(s):")
        for dup_file, orig_file in duplicates:
            try:
                size_mb = dup_file.stat().st_size / (1024 * 1024)
            except OSError:
                size_mb = 0.0
            self.log(f"[DUPLICATE] {dup_file.name} ({size_mb:.2f} MB)")
            self.log(f"  └── Original: {orig_file.name}")

        dialog = DuplicateActionDialog(self, len(duplicates))
        self.wait_window(dialog)

        if dialog.action == "folder":
            dup_folder = target_dir / "Duplicates"
            try:
                dup_folder.mkdir(exist_ok=True)
            except OSError as exc:
                self.log(f"[ERROR] Could not create 'Duplicates': {exc}")
                return

            for dup_file, _ in duplicates:
                dest_path = build_collision_safe_path(dup_folder, dup_file.name)
                try:
                    shutil.move(str(dup_file), str(dest_path))
                except OSError as exc:
                    self.log(f"[ERROR] Could not move {dup_file.name}: {exc}")
                    continue
                self.log(f"[ISOLATED] {dup_file.name} ➔ Duplicates/{dest_path.name}")

            self.log("--- Duplicates moved to 'Duplicates' folder successfully. ---\n")

        elif dialog.action == "trash":
            for dup_file, _ in duplicates:
                try:
                    self._move_to_system_trash(dup_file)
                except OSError as exc:
                    self.log(f"[ERROR] Could not trash {dup_file.name}: {exc}")
                    continue
                self.log(f"[TRASHED] {dup_file.name} ➔ System Trash")

            self.log("--- Duplicates moved to System Trash successfully. ---\n")


if __name__ == "__main__":
    app = FileOrganizerApp()
    app.mainloop()