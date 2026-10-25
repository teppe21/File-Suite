# PyInstaller spec for the macOS FileSuite.app (one-dir inside a bundle). Build with build.sh.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH).resolve().parents[1]  # noqa: F821 (SPECPATH is set by PyInstaller)
sys.path.insert(0, str(root))
from version import __version__  # noqa: E402

datas = [
    (str(root / "organizer.jpg"), "."),
    (str(root / "organizer-small.png"), "."),
] + collect_data_files("customtkinter")
# pyobjc is imported inside a function (Finder Trash), so name it explicitly.
hiddenimports = collect_submodules("customtkinter") + ["objc", "Foundation", "CoreFoundation"]

folder_usage = "File Suite only reads and moves files in the folder you choose."

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
)
coll = COLLECT(exe, a.binaries, a.datas, name="FileSuite", upx=False)
app = BUNDLE(
    coll,
    name="FileSuite.app",
    icon=str(Path(SPECPATH) / "organizer.icns"),  # noqa: F821
    bundle_identifier="io.github.teppe21.filesuite",
    info_plist={
        "CFBundleName": "File Suite",
        "CFBundleDisplayName": "File Suite",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "LSMinimumSystemVersion": "15.0",
        "NSHighResolutionCapable": True,
        # Without this, Dark Mode may be ignored by the Tk window.
        "NSRequiresAquaSystemAppearance": False,
        "LSApplicationCategoryType": "public.app-category.utilities",
        "NSHumanReadableCopyright": "Copyright © 2026 Levente Lámfalusi",
        "NSDesktopFolderUsageDescription": folder_usage,
        "NSDocumentsFolderUsageDescription": folder_usage,
        "NSDownloadsFolderUsageDescription": folder_usage,
        "NSRemovableVolumesUsageDescription": folder_usage,
        "NSNetworkVolumesUsageDescription": folder_usage,
    },
)
