import datetime
import hashlib
from pathlib import Path
import shutil
import subprocess
import urllib.parse
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

# Appearance & Theme Settings
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Pre-defined category rules mapped by file extensions
CATEGORIES = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"},
    "Documents": {".pdf", ".docx", ".txt", ".xlsx", ".csv"},
    "Archives": {".zip", ".tar.gz", ".7z", ".rar", ".gz", ".tar"},
    "Installers & Code": {".deb", ".sh", ".py", ".js", ".json"},
    "Media": {".mp4", ".mkv", ".mp3", ".flac"},
}


class DuplicateActionDialog(ctk.CTkToplevel):
    """Custom modal dialog offering options for duplicate handling."""
    def __init__(self, parent, count: int):
        super().__init__(parent)
        self.title("Duplicates Found")
        self.geometry("420x220")
        self.resizable(False, False)
        self.action = None  # Will be 'folder', 'trash', or None

        self.transient(parent)
        self.grab_set()

        # UI Layout
        label = ctk.CTkLabel(
            self, 
            text=f"Found {count} duplicate file(s).",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        label.pack(pady=(20, 5))

        sublabel = ctk.CTkLabel(
            self,
            text="Choose how you would like to handle these duplicates:",
            font=ctk.CTkFont(size=12),
            text_color="gray70"
        )
        sublabel.pack(pady=(0, 20))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20)

        folder_btn = ctk.CTkButton(
            btn_frame,
            text="📁 Move to 'Duplicates' Folder",
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            command=self._on_folder
        )
        folder_btn.pack(fill="x", pady=4)

        trash_btn = ctk.CTkButton(
            btn_frame,
            text="🗑️ Move to System Trash",
            fg_color="#DC2626",
            hover_color="#B91C1C",
            command=self._on_trash
        )
        trash_btn.pack(fill="x", pady=4)

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            fg_color="transparent",
            border_width=1,
            text_color="gray80",
            command=self.destroy
        )
        cancel_btn.pack(fill="x", pady=4)

    def _on_folder(self):
        self.action = "folder"
        self.destroy()

    def _on_trash(self):
        self.action = "trash"
        self.destroy()


class FileOrganizerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Main Window Configuration
        self.title("File Suite — Modern Desktop Organizer & Duplicate Cleaner")
        self.geometry("860x720")
        self.minsize(780, 600)

        # Set Application Icon (safely resized for X11/Linux buffer limits)
        self._set_window_icon()

        # Default Directory: ~/Downloads (fallback to Home)
        default_downloads = Path.home() / "Downloads"
        self.current_path = default_downloads if default_downloads.exists() else Path.home()

        # Category checkboxes state dictionary
        self.cat_vars = {cat: ctk.BooleanVar(value=True) for cat in CATEGORIES.keys()}

        self._build_ui()

    def _set_window_icon(self):
        """Loads and resizes window icon to prevent X11 buffer length errors."""
        icon_path = Path(__file__).parent / "organizer.jpg"
        if icon_path.exists():
            try:
                pil_img = Image.open(icon_path).convert("RGBA")
                pil_img = pil_img.resize((64, 64), Image.Resampling.LANCZOS)
                self.icon_image = ImageTk.PhotoImage(pil_img)
                self.iconphoto(True, self.icon_image)
            except Exception as e:
                print(f"[WARNING] Could not load window icon: {e}")

    def _build_ui(self):
        """Builds the GUI layout."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        # --- 1. Header Bar ---
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=24, pady=(16, 4), sticky="ew")

        title_label = ctk.CTkLabel(
            header_frame, 
            text="File Suite", 
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack(side="left")

        subtitle_label = ctk.CTkLabel(
            header_frame, 
            text="Custom Folder Grouping & Duplicate Cleaner", 
            font=ctk.CTkFont(size=12),
            text_color="gray60"
        )
        subtitle_label.pack(side="left", padx=(12, 0), pady=(4, 0))

        # --- 2. Directory Picker Card ---
        picker_card = ctk.CTkFrame(self, corner_radius=12)
        picker_card.grid(row=1, column=0, padx=24, pady=6, sticky="ew")
        picker_card.grid_columnconfigure(1, weight=1)

        picker_label = ctk.CTkLabel(
            picker_card, 
            text="Target Folder:", 
            font=ctk.CTkFont(size=12, weight="bold")
        )
        picker_label.grid(row=0, column=0, padx=(16, 10), pady=12, sticky="w")

        self.path_entry = ctk.CTkEntry(
            picker_card, 
            height=36,
            corner_radius=8,
            border_width=1,
            placeholder_text="Select a directory..."
        )
        self.path_entry.insert(0, str(self.current_path))
        self.path_entry.configure(state="disabled")
        self.path_entry.grid(row=0, column=1, padx=5, pady=12, sticky="ew")

        browse_btn = ctk.CTkButton(
            picker_card, 
            text="Browse...", 
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.select_folder,
            width=100
        )
        browse_btn.grid(row=0, column=2, padx=(5, 16), pady=12)

        # --- 3. Custom Grouping & Organization Panel ---
        organize_card = ctk.CTkFrame(self, corner_radius=12)
        organize_card.grid(row=2, column=0, padx=24, pady=6, sticky="ew")
        organize_card.grid_columnconfigure((0, 1), weight=1)

        org_title = ctk.CTkLabel(
            organize_card, 
            text="File Organization & Grouping Rules", 
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="gray80"
        )
        org_title.grid(row=0, column=0, columnspan=2, padx=16, pady=(12, 6), sticky="w")

        # Category Checkboxes Frame
        cb_frame = ctk.CTkFrame(organize_card, fg_color="transparent")
        cb_frame.grid(row=1, column=0, columnspan=2, padx=16, pady=4, sticky="ew")

        col = 0
        for cat_name, var in self.cat_vars.items():
            cb = ctk.CTkCheckBox(cb_frame, text=cat_name, variable=var, font=ctk.CTkFont(size=12))
            cb.grid(row=0, column=col, padx=(0, 14), pady=4, sticky="w")
            col += 1

        # Additional Extensions Input
        ext_label = ctk.CTkLabel(
            organize_card, 
            text="Additional Extensions (comma-separated, e.g. .iso, .blend):", 
            font=ctk.CTkFont(size=11),
            text_color="gray70"
        )
        ext_label.grid(row=2, column=0, columnspan=2, padx=16, pady=(8, 2), sticky="w")

        self.custom_ext_entry = ctk.CTkEntry(
            organize_card,
            height=32,
            corner_radius=6,
            placeholder_text="Optional custom extensions..."
        )
        self.custom_ext_entry.grid(row=3, column=0, columnspan=2, padx=16, pady=(0, 8), sticky="ew")

        # Target Subfolder Name Input
        folder_name_label = ctk.CTkLabel(
            organize_card, 
            text="Destination Subfolder Name (for grouped items):", 
            font=ctk.CTkFont(size=11),
            text_color="gray70"
        )
        folder_name_label.grid(row=4, column=0, padx=16, pady=(4, 2), sticky="w")

        self.custom_folder_entry = ctk.CTkEntry(
            organize_card,
            height=32,
            corner_radius=6,
            placeholder_text="e.g. Custom_Group (Leave blank to use default categories)"
        )
        self.custom_folder_entry.grid(row=5, column=0, padx=16, pady=(0, 14), sticky="ew")

        # Action Buttons for Organization
        group_btn = ctk.CTkButton(
            organize_card,
            text="⚡ Group Selected Types",
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.organize_selected,
            fg_color="#2563EB",
            hover_color="#1D4ED8"
        )
        group_btn.grid(row=5, column=1, padx=(10, 16), pady=(0, 14), sticky="ew")

        # --- 4. Duplicates Section ---
        dup_card = ctk.CTkFrame(self, corner_radius=12)
        dup_card.grid(row=3, column=0, padx=24, pady=6, sticky="ew")
        dup_card.grid_columnconfigure(0, weight=1)

        dup_btn = ctk.CTkButton(
            dup_card,
            text="🔍 Find Duplicates in Root Directory",
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.find_duplicates,
            fg_color="#059669",
            hover_color="#047857"
        )
        dup_btn.grid(row=0, column=0, padx=16, pady=10, sticky="ew")

        # --- 5. Output Console Log ---
        log_card = ctk.CTkFrame(self, corner_radius=12)
        log_card.grid(row=4, column=0, padx=24, pady=(6, 16), sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        log_header = ctk.CTkLabel(
            log_card, 
            text="Activity Console", 
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="gray70"
        )
        log_header.grid(row=0, column=0, padx=16, pady=(10, 2), sticky="w")

        self.log_box = ctk.CTkTextbox(
            log_card, 
            font=("Monospace", 12),
            corner_radius=8,
            activate_scrollbars=True
        )
        self.log_box.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="nsew")

        self.log("System initialized. Configure options and select an operation.\n")

    def log(self, message: str):
        """Appends output messages to the console log."""
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")

    def _ask_directory_native(self, initial_dir: Path) -> str:
        """Opens native GTK/KDE file picker if available, falling back to Tkinter."""
        initial_str = str(initial_dir)

        # 1. Try Zenity (GNOME / GTK native picker)
        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", "--directory", f"--filename={initial_str}/"]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return res.stdout.strip()
                elif res.returncode == 1:  # User clicked Cancel
                    return ""
            except Exception:
                pass

        # 2. Try Kdialog (KDE native picker)
        if shutil.which("kdialog"):
            try:
                cmd = ["kdialog", "--getexistingdirectory", initial_str]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return res.stdout.strip()
                elif res.returncode == 1:  # User clicked Cancel
                    return ""
            except Exception:
                pass

        # 3. Fallback to standard Tkinter dialog
        return filedialog.askdirectory(initialdir=initial_str)

    def select_folder(self):
        """Opens native directory picker dialog."""
        initial_dir = self.current_path if self.current_path.exists() else Path.home()
        chosen_dir = self._ask_directory_native(initial_dir)

        if chosen_dir:
            self.current_path = Path(chosen_dir)
            self.path_entry.configure(state="normal")
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, str(self.current_path))
            self.path_entry.configure(state="disabled")
            self.log(f"[SELECTED] Active folder: {self.current_path}")

    def _get_selected_extensions(self) -> set:
        """Collects extensions from active checkboxes and custom input field."""
        extensions = set()
        
        # Collect checked preset categories
        for cat_name, is_checked in self.cat_vars.items():
            if is_checked.get():
                extensions.update(CATEGORIES[cat_name])

        # Parse custom extensions input
        custom_input = self.custom_ext_entry.get().strip()
        if custom_input:
            raw_exts = [e.strip().lower() for e in custom_input.split(",") if e.strip()]
            for ext in raw_exts:
                if not ext.startswith("."):
                    ext = f".{ext}"
                extensions.add(ext)

        return extensions

    def organize_selected(self):
        """Organizes root files matching selected categories/extensions into target folder(s)."""
        target_dir = self.current_path

        if not target_dir.exists() or not target_dir.is_dir():
            self.log("[ERROR] The selected target directory does not exist!")
            return

        selected_exts = self._get_selected_extensions()
        if not selected_exts:
            messagebox.showwarning("No Extensions Selected", "Please select at least one file category or enter custom extensions.")
            return

        custom_folder_name = self.custom_folder_entry.get().strip()
        
        self.log(f"\n--- ORGANIZING ROOT FILES: {target_dir} ---")
        moved_count = 0

        # Inspect top-level files only
        for item in target_dir.iterdir():
            if item.is_dir() or item.name.startswith("."):
                continue

            ext = item.suffix.lower()
            full_ext = "".join(item.suffixes).lower()

            if ext in selected_exts or full_ext in selected_exts:
                if custom_folder_name:
                    dest_category = custom_folder_name
                else:
                    dest_category = "Misc"
                    for cat_name, cat_extensions in CATEGORIES.items():
                        if ext in cat_extensions or full_ext in cat_extensions:
                            dest_category = cat_name
                            break

                cat_dir = target_dir / dest_category
                cat_dir.mkdir(exist_ok=True)

                dest_path = cat_dir / item.name
                if dest_path.exists():
                    stem = item.stem
                    suffix = item.suffix
                    counter = 1
                    while dest_path.exists():
                        dest_path = cat_dir / f"{stem}_{counter}{suffix}"
                        counter += 1

                shutil.move(str(item), str(dest_path))
                self.log(f"[MOVED] {item.name} ➔ {dest_category}/")
                moved_count += 1

        self.log(f"--- Task Complete: {moved_count} file(s) organized. ---\n")

    def _calculate_sha256(self, file_path: Path) -> str:
        """Computes SHA-256 hash using 64KB streaming blocks."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(64 * 1024):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _move_to_system_trash(self, file_path: Path):
        """Moves file to Linux Freedesktop System Trash (~/.local/share/Trash/)."""
        trash_files_dir = Path.home() / ".local/share/Trash/files"
        trash_info_dir = Path.home() / ".local/share/Trash/info"
        trash_files_dir.mkdir(parents=True, exist_ok=True)
        trash_info_dir.mkdir(parents=True, exist_ok=True)

        dest_path = trash_files_dir / file_path.name
        counter = 1
        stem = file_path.stem
        suffix = file_path.suffix

        while dest_path.exists():
            dest_path = trash_files_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        info_path = trash_info_dir / f"{dest_path.name}.trashinfo"
        deletion_date = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        escaped_path = urllib.parse.quote(str(file_path.absolute()))
        
        info_content = f"[Trash Info]\nPath={escaped_path}\nDeletionDate={deletion_date}\n"
        
        with open(info_path, "w", encoding="utf-8") as f:
            f.write(info_content)

        shutil.move(str(file_path), str(dest_path))

    def find_duplicates(self):
        """Identifies duplicate root files and prompts for isolation or system trash."""
        target_dir = self.current_path

        if not target_dir.exists() or not target_dir.is_dir():
            self.log("[ERROR] The selected target directory does not exist!")
            return

        self.log(f"\n--- SCANNING FOR DUPLICATES: {target_dir} ---")

        files = [f for f in target_dir.iterdir() if f.is_file() and not f.name.startswith(".")]

        if not files:
            self.log("No valid files found in the root folder to process.")
            return

        hashes = {}
        duplicates = []

        for file in files:
            try:
                file_hash = self._calculate_sha256(file)
                if file_hash in hashes:
                    duplicates.append((file, hashes[file_hash]))
                else:
                    hashes[file_hash] = file
            except Exception as e:
                self.log(f"[ERROR] Could not process file ({file.name}): {e}")

        if not duplicates:
            self.log("No duplicate files detected.")
            return

        self.log(f"Found {len(duplicates)} duplicate file(s):")
        for dup_file, orig_file in duplicates:
            size_mb = dup_file.stat().st_size / (1024 * 1024)
            self.log(f"[DUPLICATE] {dup_file.name} ({size_mb:.2f} MB)")
            self.log(f"  └── Original: {orig_file.name}")

        dialog = DuplicateActionDialog(self, len(duplicates))
        self.wait_window(dialog)

        if dialog.action == "folder":
            dup_folder = target_dir / "Duplicates"
            dup_folder.mkdir(exist_ok=True)

            for dup_file, _ in duplicates:
                dest_path = dup_folder / dup_file.name
                if dest_path.exists():
                    stem = dup_file.stem
                    suffix = dup_file.suffix
                    counter = 1
                    while dest_path.exists():
                        dest_path = dup_folder / f"{stem}_{counter}{suffix}"
                        counter += 1
                shutil.move(str(dup_file), str(dest_path))
                self.log(f"[ISOLATED] {dup_file.name} ➔ Duplicates/")

            self.log("--- Duplicates moved to 'Duplicates' folder successfully. ---\n")

        elif dialog.action == "trash":
            for dup_file, _ in duplicates:
                self._move_to_system_trash(dup_file)
                self.log(f"[TRASHED] {dup_file.name} ➔ System Trash")

            self.log("--- Duplicates moved to System Trash successfully. ---\n")


if __name__ == "__main__":
    app = FileOrganizerApp()
    app.mainloop()