import hashlib
from pathlib import Path
import shutil
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

# Appearance & Theme Settings
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Category rules mapped by file extensions
CATEGORIES = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"},
    "Documents": {".pdf", ".docx", ".txt", ".xlsx", ".csv"},
    "Archives": {".zip", ".tar.gz", ".7z", ".rar", ".gz", ".tar"},
    "Installers & Code": {".deb", ".sh", ".py", ".js", ".json"},
    "Media": {".mp4", ".mkv", ".mp3", ".flac"},
}


class FileOrganizerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Main Window Configuration
        self.title("File Suite — Modern Linux Desktop Organizer & Duplicate Cleaner")
        self.geometry("820x620")
        self.minsize(740, 520)

        # Set Application Icon (safely resized for Linux / X11)
        self._set_window_icon()

        # Default Directory: ~/Downloads (fallback to Home if missing)
        default_downloads = Path.home() / "Downloads"
        self.current_path = default_downloads if default_downloads.exists() else Path.home()

        self._build_ui()

    def _set_window_icon(self):
        """Loads, resizes, and sets the window icon from organizer.jpg to avoid X11 buffer errors."""
        icon_path = Path(__file__).parent / "organizer.jpg"
        if icon_path.exists():
            try:
                # Resize image to standard icon size to prevent X11 BadLength error
                pil_img = Image.open(icon_path).convert("RGBA")
                pil_img = pil_img.resize((64, 64), Image.Resampling.LANCZOS)
                
                self.icon_image = ImageTk.PhotoImage(pil_img)
                self.iconphoto(True, self.icon_image)
            except Exception as e:
                print(f"[WARNING] Could not load window icon: {e}")

    def _build_ui(self):
        """Builds the modern minimalist CustomTkinter interface."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # --- Header Bar ---
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=24, pady=(20, 8), sticky="ew")

        title_label = ctk.CTkLabel(
            header_frame, 
            text="File Suite", 
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack(side="left")

        subtitle_label = ctk.CTkLabel(
            header_frame, 
            text="Clean & Organize Your Root Folders Effortlessly", 
            font=ctk.CTkFont(size=12),
            text_color="gray60"
        )
        subtitle_label.pack(side="left", padx=(12, 0), pady=(4, 0))

        # --- Directory Picker Card ---
        picker_card = ctk.CTkFrame(self, corner_radius=12)
        picker_card.grid(row=1, column=0, padx=24, pady=8, sticky="ew")
        picker_card.grid_columnconfigure(1, weight=1)

        picker_label = ctk.CTkLabel(
            picker_card, 
            text="Target Folder:", 
            font=ctk.CTkFont(size=12, weight="bold")
        )
        picker_label.grid(row=0, column=0, padx=(16, 10), pady=16, sticky="w")

        self.path_entry = ctk.CTkEntry(
            picker_card, 
            height=38,
            corner_radius=8,
            border_width=1,
            placeholder_text="Select a directory..."
        )
        self.path_entry.insert(0, str(self.current_path))
        self.path_entry.configure(state="disabled")
        self.path_entry.grid(row=0, column=1, padx=5, pady=16, sticky="ew")

        browse_btn = ctk.CTkButton(
            picker_card, 
            text="Browse...", 
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.select_folder,
            width=110
        )
        browse_btn.grid(row=0, column=2, padx=(5, 16), pady=16)

        # --- Action Buttons ---
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.grid(row=2, column=0, padx=24, pady=8, sticky="ew")
        action_frame.grid_columnconfigure((0, 1), weight=1)

        organize_btn = ctk.CTkButton(
            action_frame, 
            text="⚡ Organize Files", 
            height=44,
            corner_radius=8,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.organize_files,
            fg_color="#2563EB", 
            hover_color="#1D4ED8"
        )
        organize_btn.grid(row=0, column=0, padx=(0, 6), pady=0, sticky="ew")

        dup_btn = ctk.CTkButton(
            action_frame, 
            text="🔍 Find Duplicates", 
            height=44,
            corner_radius=8,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.find_duplicates,
            fg_color="#059669", 
            hover_color="#047857"
        )
        dup_btn.grid(row=0, column=1, padx=(6, 0), pady=0, sticky="ew")

        # --- Console / Output Log Card ---
        log_card = ctk.CTkFrame(self, corner_radius=12)
        log_card.grid(row=3, column=0, padx=24, pady=(8, 20), sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        log_header = ctk.CTkLabel(
            log_card, 
            text="Activity Console", 
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="gray70"
        )
        log_header.grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        self.log_box = ctk.CTkTextbox(
            log_card, 
            font=("Monospace", 12),
            corner_radius=8,
            activate_scrollbars=True
        )
        self.log_box.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")

        self.log("System initialized. Select a directory and start an operation.\n")

    def log(self, message: str):
        """Appends output messages to the GUI console."""
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")

    def select_folder(self):
        """Opens directory picker dialog and updates the target path."""
        initial_dir = str(self.current_path) if self.current_path.exists() else str(Path.home())
        chosen_dir = filedialog.askdirectory(initialdir=initial_dir)

        if chosen_dir:
            self.current_path = Path(chosen_dir)
            self.path_entry.configure(state="normal")
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, str(self.current_path))
            self.path_entry.configure(state="disabled")
            self.log(f"[SELECTED] Active folder: {self.current_path}")

    def organize_files(self):
        """Organizes direct root files into categorized subfolders."""
        target_dir = self.current_path

        if not target_dir.exists() or not target_dir.is_dir():
            self.log("[ERROR] The selected target directory does not exist!")
            return

        self.log(f"\n--- ORGANIZING ROOT FILES: {target_dir} ---")
        moved_count = 0

        for item in target_dir.iterdir():
            if item.is_dir() or item.name.startswith("."):
                continue

            category = "Misc"
            ext = item.suffix.lower()
            full_ext = "".join(item.suffixes).lower()

            for cat_name, extensions in CATEGORIES.items():
                if ext in extensions or full_ext in extensions:
                    category = cat_name
                    break

            cat_dir = target_dir / category
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
            self.log(f"[MOVED] {item.name} ➔ {category}/")
            moved_count += 1

        self.log(f"--- Task Complete: {moved_count} file(s) organized. ---\n")

    def _calculate_sha256(self, file_path: Path) -> str:
        """Computes SHA-256 hash using 64KB streaming blocks (memory-efficient)."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(64 * 1024):
                sha256.update(chunk)
        return sha256.hexdigest()

    def find_duplicates(self):
        """Identifies duplicate files strictly located in the root directory."""
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

        should_move = messagebox.askyesno(
            "Isolate Duplicates",
            f"Found {len(duplicates)} duplicate file(s).\n\nDo you want to move them to a dedicated 'Duplicates' folder?"
        )

        if should_move:
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

            self.log("--- Duplicates moved successfully. ---\n")


if __name__ == "__main__":
    app = FileOrganizerApp()
    app.mainloop()