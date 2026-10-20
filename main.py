"""
File Suite — Desktop File Organizer & Deduplication Utility.

A polished, secure, and deterministic utility for organizing files and finding
duplicates inside a selected directory. Linux is the primary platform;
Windows support is experimental.

Entry point only; the UI lives in the ``ui`` package.
"""

from ui.app import FileOrganizerApp

if __name__ == "__main__":
    app = FileOrganizerApp()
    app.mainloop()
