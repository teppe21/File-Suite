# File Suite

![Python](https://img.shields.io/badge/Python-3.10%20--%203.13-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20(experimental)-FCC624?style=for-the-badge&logo=linux&logoColor=black)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)
[![Tests and Lint](https://github.com/teppe21/File-Suite/actions/workflows/tests.yml/badge.svg)](https://github.com/teppe21/File-Suite/actions/workflows/tests.yml)
[![Windows Tests](https://github.com/teppe21/File-Suite/actions/workflows/windows.yml/badge.svg)](https://github.com/teppe21/File-Suite/actions/workflows/windows.yml)

File Suite is a desktop app that sorts the loose files in a folder into category subfolders and finds byte-identical duplicates by SHA-256. Every change is shown as a preview first, nothing happens until you confirm, existing files are never overwritten, and the last operation can be undone. It works only on files directly inside the chosen folder; subfolders, hidden files and symlinks are skipped.

<p align="center">
  <img width="901" height="749" alt="Organize Files View" src="https://github.com/user-attachments/assets/628b7b11-3fe2-494d-a28a-b51b5ac00b03" />
  <br/>
  <img width="901" height="749" alt="Duplicate Finder View" src="https://github.com/user-attachments/assets/fb87ef58-e735-4b3f-9b5e-d8e6e058ff35" />
  <br/>
  <img width="901" height="749" alt="Activity Log View" src="https://github.com/user-attachments/assets/7fb8afcd-5b4a-45a9-9aa2-607acfadbb81" />
</p>

## What it does

- **Organize Files**: previews which files move into which category folder, with file counts, total size and any renames, then moves them on confirmation.
- **Duplicate Finder**: groups byte-identical files, lets you select the copies to remove (one original per group stays unselected by default), and moves them into a `Duplicates/` folder or to the system trash.
- **Activity Log**: shows a timestamped record of every operation, skip and error.

### Safety at a glance

- Every operation is previewed and needs confirmation; undo restores the last organize or duplicate move for the current session.
- Files are never overwritten; name collisions get a suffix such as `file_1.pdf`.
- Symlinks are skipped, and destination paths are checked again right before each move.
- At least one copy of each duplicate group is always kept.
- Files that changed since the duplicate scan are skipped.

Details: [docs/SAFETY.md](docs/SAFETY.md).

## Install and run

**Requirements**: Python 3.10 to 3.13 with Tk (on Linux, the `python3-tk` package). On Linux, `zenity` or `kdialog` is used for the folder picker if installed. Windows needs Windows 10 22H2 or newer, x64.

### Run from source

Linux:

```bash
git clone https://github.com/teppe21/File-Suite.git
cd File-Suite
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Windows (PowerShell):

```powershell
git clone https://github.com/teppe21/File-Suite.git
cd File-Suite
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

### Standalone build

Linux: `./build.sh` creates the single-file executable `dist/FileSuite`. `./install.sh` then copies it to `~/.local/bin` and adds a desktop launcher (category Utility/System); with `~/.local/bin` on your `PATH` it also starts with `FileSuite`.

```bash
./build.sh
./install.sh
```

Windows: `packaging\windows\build.ps1` creates `dist\FileSuite-windows-x64-v<version>.zip` and a `.sha256` file.

## Platform notes

Linux (X11 and Wayland) is the primary platform. Windows support is experimental and has been tested mainly through CI. Main Windows caveats:

- The executable is not code-signed, so SmartScreen may warn when you start it.
- On USB sticks and network shares, deleted duplicates may be deleted permanently instead of going to the Recycle Bin; the app warns before this.
- OneDrive online-only files are skipped.
- The native folder pickers are not used; the standard Tkinter dialog is shown.

Full list: [docs/SAFETY.md](docs/SAFETY.md#windows-specific-limitations).

## Development

File Suite is developed with AI assistance. The author reviews every change before it is merged, and CI runs the unit tests, Ruff, Bandit and pip-audit on every pull request.
See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for architecture, tests and releases, and [CHANGELOG.md](CHANGELOG.md) for the release history.

## License

MIT. See [LICENSE](LICENSE).
