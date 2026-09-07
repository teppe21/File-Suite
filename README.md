# File Suite — Linux File Organizer & Duplicate Cleaner

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-blue?style=for-the-badge)
![Linux](https://img.shields.io/badge/Platform-Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black)

File Suite is a desktop utility for Linux systems designed to organize loose files and locate duplicate content within a chosen directory.

The application strictly operates on files located directly in the root of the selected directory. It deliberately ignores subdirectories and hidden dotfiles to prevent unintended modifications to existing folder hierarchies.

---

## Features

* **Automatic File Categorization:** Groups files into subfolders (*Images, Documents, Archives, Installers & Code, Media, Misc*) according to their extensions.
* **SHA-256 Duplicate Detection:** Identifies identical files by computing hashes in 64 KB chunks, allowing efficient processing of large files without high memory consumption.
* **Non-Recursive Execution:** Processes only top-level files in the selected directory while keeping existing subfolders untouched.
* **Ignores Hidden Files:** System files and dotfiles (such as `.git` or `.bashrc`) remain unmodified.
* **Dark Mode GUI:** Built with CustomTkinter, offering a simple interface with an integrated activity log.
* **Collision Protection:** Automatically renames destination files if a file with the same name already exists to prevent accidental overwrites.

---

## Technical Stack

* **CustomTkinter:** Graphical interface components.
* **Pillow:** Image processing and application window icon integration.
* **Python Standard Library:**
  * `pathlib` — Path operations and directory traversal
  * `hashlib` — SHA-256 hashing stream
  * `shutil` — File moving operations

---

## Installation

### Requirements
* Linux OS
* Python 3.10 or newer

### Setup
Clone the repository and run the installation script:

```bash
git clone [https://github.com/teppe21/File-Suite.git](https://github.com/teppe21/File-Suite.git)
cd File-Suite
chmod +x install.sh
./install.sh