# File Suite — Modern Linux Desktop Organizer & Duplicate Cleaner

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-blue?style=for-the-badge)
![Linux](https://img.shields.io/badge/Platform-Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black)

**File Suite** is a sleek, modern, dark-themed GUI desktop application built for Linux users to automatically organize cluttered directories and safely isolate duplicate files. 

Engineered with a **strict non-recursive safety principle**, it operates exclusively on the immediate root of the target directory—leaving subdirectories and hidden dotfiles completely untouched.

---

## ✨ Key Features

* **⚡ Smart Root Categorization:** Automatically sorts top-level files into logical subfolders (*Images, Documents, Archives, Installers & Code, Media, Misc*) based on file extensions.
* **🔍 RAM-Efficient Duplicate Detection:** Streams files using 64KB block hashing (`hashlib.sha256`) to locate exact content duplicates without memory spikes on large files.
* **🔒 Strict Directory Safety:** Uses `pathlib` checks to completely ignore existing subfolders and hidden system files (`.git`, `.bashrc`, etc.).
* **🎨 Modern Minimalist Dark UI:** CustomTkinter interface built with a clean card layout and real-time console logging.
* **🛡️ Collision Prevention:** Auto-renames files if destination collisions occur during sorting or isolation.

---

## 🛠️ Built With

* **[CustomTkinter](https://github.com/TomSchimansky/CustomTkinter):** Modern UI widget wrapper over Tkinter.
* **[Pillow (PIL)](https://python-pillow.org/):** Cross-platform image handling for X11 application window icons.
* **Python Standard Library:** `pathlib`, `hashlib`, `shutil`.

---

## 🚀 Quick Installation (Linux)

You can install File Suite directly from source with a single terminal command:

```bash
git clone [https://github.com/YOUR_USERNAME/linux-file-organizer.git](https://github.com/YOUR_USERNAME/linux-file-organizer.git)
cd linux-file-organizer
chmod +x install.sh
./install.sh