# File Suite — Linux File Organizer & Duplicate Cleaner

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge\&logo=python\&logoColor=white)
![CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-blue?style=for-the-badge)
![Linux](https://img.shields.io/badge/Platform-Linux-FCC624?style=for-the-badge\&logo=linux\&logoColor=black)

File Suite is a desktop utility for Linux systems designed to organize loose files and locate duplicate content within a chosen directory.

The application operates only on files located directly in the selected directory. It ignores subdirectories and hidden dotfiles to prevent unintended changes to existing folder structures.


<img width="855" height="743" alt="file_suite_gui_1" src="https://github.com/user-attachments/assets/024ccb96-71d3-4f6b-9d04-d0d905e0658a" />



---

## Features

* **Multi-Category & Custom Extension Grouping**
  Allows selecting multiple preset file categories at once or specifying custom extensions to group files into user-defined target subfolders.

* **Flexible Duplicate Action Handling**
  When duplicates are found, the user can choose to either move them into a dedicated `Duplicates/` folder or send them directly to the Linux System Trash (`~/.local/share/Trash/`).

* **Native Desktop Directory Picker**
  Uses system-native GTK (`zenity`) or KDE (`kdialog`) folder choosers when available.

* **SHA-256 Duplicate Detection**
  Identifies identical files by computing SHA-256 hashes in 64 KB chunks, allowing large files to be processed without high memory usage.

* **Non-Recursive Execution**
  Processes only files directly inside the selected directory while leaving existing subfolders untouched.

* **Ignores Hidden Files**
  System files and dotfiles, such as `.git` or `.bashrc`, are skipped and remain unmodified.

* **Dark Mode GUI**
  Built with CustomTkinter, providing a simple interface with an integrated activity log.

* **Collision Protection**
  Automatically renames destination files if a file with the same name already exists, preventing accidental overwrites.

---

## Technical Stack

* **CustomTkinter** — Graphical interface components.

* **Pillow** — Image processing and application window icon integration.

* **System Utilities (Zenity/Kdialog)** — Native Linux directory chooser integration.

* **Python Standard Library**

  * `pathlib` — Path operations and directory traversal
  * `hashlib` — SHA-256 hashing
  * `shutil` — File moving operations

---

## Installation

### Requirements

* Linux OS
* Python 3.10 or newer

### Setup

Clone the repository and run the installation script:

```bash
git clone https://github.com/teppe21/File-Suite.git
cd File-Suite
chmod +x install.sh
./install.sh
```

After running the script, File Suite will be available in your desktop environment's application menu.

---

## Safety & Non-Recursive Rules

File Suite follows a non-recursive approach when processing directories:

* Only files located directly in the selected directory are scanned.
* Existing subfolders are completely skipped.
* Hidden files starting with `.` are ignored.
* Sorting a directory will not affect existing folders such as `Documents/`, `Projects/`, or version control directories like `.git/`.
* Destination conflicts are handled by adding sequential suffixes instead of replacing existing files.

---

## Project Structure

```text
File-Suite/
├── install.sh      # Shell script for desktop shortcut setup
├── main.py         # Application logic and CustomTkinter interface
├── organizer.jpg   # Application icon
├── README.md       # Documentation
└── .gitignore      # Tracked file exclusions
```

---

## License

Distributed under the MIT License. See `LICENSE` for details.
