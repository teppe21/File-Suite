# File Suite

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-blue?style=for-the-badge)
![Linux](https://img.shields.io/badge/Platform-Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black)

A small Linux desktop utility for organizing loose files and finding
duplicates inside a selected directory.

File Suite operates only on the files directly inside the chosen folder.
Existing subdirectories, hidden dotfiles, and any other nested content are
left untouched.

<img width="855" height="743" alt="file_suite_gui_1" src="https://github.com/user-attachments/assets/d383ca1b-449c-4f55-8dc8-a02f7e3ad7b8" />
<img width="421" height="272" alt="filesuiteduplicateshowcase" src="https://github.com/user-attachments/assets/a6ff52e4-3be8-465d-a695-6e43c4d8e78e" />



## Features

- Organize files into preset categories (Images, Documents, Archives,
  Media, Installers & Code) or a single user-defined subfolder.
- Find byte-identical files using SHA-256 hashing (64 KB chunks, memory
  friendly). Files whose sizes differ are skipped before hashing.
- Choose what happens to duplicates: move them into a `Duplicates/`
  subfolder, or send them to the freedesktop trash
  (`~/.local/share/Trash/`).
- Native directory picker via `zenity` (GTK) or `kdialog` (KDE) when
  available, with a Tkinter fallback.
- Non-recursive: only files directly in the selected directory are
  processed.
- Hidden files (names starting with `.`) are skipped.
- Collision-safe: existing destination files are never overwritten.
  Renamed files keep their full extension (`backup.tar.gz` →
  `backup_1.tar.gz`).
- User-supplied destination folder names are validated to prevent them
  from escaping the selected directory.
- Dark-mode GUI built with CustomTkinter, with an in-app activity log.

## Requirements

- Linux
- Python 3.10 or newer (for running from source or building)
- A working Tk installation (usually shipped with Python on Linux)

Optional, for a native folder picker:

- `zenity` (GNOME / GTK desktops)
- `kdialog` (KDE desktops)

If neither is installed, the app falls back to a standard Tk folder
dialog.

## Running from source (development)

```bash
git clone https://github.com/teppe21/File-Suite.git
cd File-Suite

python3 -m venv .venv
source .venv/bin/activate

python3 -m pip install -r requirements.txt

python3 main.py
