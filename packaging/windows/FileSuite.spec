# PyInstaller spec for the Windows one-dir bundle. Build with build.ps1.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH).resolve().parents[1]  # noqa: F821 (SPECPATH is set by PyInstaller)

datas = [
    (str(root / "organizer.jpg"), "."),
    (str(root / "organizer.ico"), "."),
] + collect_data_files("customtkinter")
hiddenimports = collect_submodules("customtkinter")

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    datas=datas,
    hiddenimports=hiddenimports,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="FileSuite",
    console=False,
    upx=False,
    icon=str(root / "organizer.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="FileSuite", upx=False)
