# Safety Model and Limitations

[Back to README](../README.md)

## Safety model

File Suite checks the following before and during every operation:

1. **Preview before changes**: Organizing shows a dry-run preview with affected file counts, total size in MB, destination subfolders and any collision renames. Nothing is moved until you confirm.
2. **Non-recursive boundary**: Operations apply only to loose files directly inside the active directory. Subdirectories are never descended into, altered or deleted. Hidden files are skipped.
3. **Symlinks skipped**: Symlinks are skipped so that no link target outside the folder is changed.
4. **Pre-execution revalidation**: The preview and the execution are separate trust boundaries. Immediately before each move, the source is checked again: it must still exist, be a regular file and not be a symlink.
5. **Destination path containment**: Every target path and its intermediate components are re-resolved against the active root directory right before execution. If an intermediate directory was replaced by a symlink between preview and execution, the operation is aborted for that item.
6. **Collision avoidance**: Target names that collide with existing files, symlinks (including broken symlinks) or other files in the same batch are suffixed without overwriting existing data. Multi-part extensions are kept intact (`file_1.pdf`, `archive_1.tar.gz`, `data_1.tar.zst`).
7. **Path traversal defense**: User-supplied folder names cannot escape the root directory: `/`, `\`, `..`, a leading `~` and control characters are rejected.
8. **No-clobber moves**: On Linux a move hard-links the file to its destination and then removes the source, which fails instead of replacing a file that appeared at the destination after the checks. Where hard links are unavailable (another drive, FAT/exFAT) the file is copied into an exclusively created destination and any partial copy is removed on error. On Windows a plain rename already refuses to overwrite. macOS uses the same hard-link move as Linux.
9. **FreeDesktop trash**: On Linux, files sent to trash are moved into `$XDG_DATA_HOME/Trash/files` (default `~/.local/share/Trash/files`) with conforming `.trashinfo` metadata. The metadata file is created exclusively, so another application's trash entry is never overwritten; a taken name moves on to the next free one. If the move fails, the metadata file is removed so no orphaned trash entry is left.
10. **A kept copy is always left**: Moving or trashing duplicates is refused while every copy of a group is selected. Any copy can be the one kept.
11. **Stale scan protection**: Duplicate scans check file metadata before and after hashing. Right before moving or trashing duplicates, each selected file and the group's kept copies are checked again. A selected file whose size, modification time or inode changed since the scan is skipped, and a group with no unchanged kept copy left is skipped entirely. Every skip is written to the Activity Log.
12. **Session undo**: A single-level, in-memory undo moves organized or isolated files back to their original locations in reverse order. If a file now exists at the original location, that file is not overwritten.

## Limitations

- **Platforms**: Linux desktop environments (X11 and Wayland) are the primary target and follow XDG and FreeDesktop standards. Windows support is experimental; see [Windows-specific limitations](#windows-specific-limitations). macOS support is experimental too; see [macOS-specific limitations](#macos-specific-limitations).
- **Race conditions**: Despite the revalidation above, standard OS filesystem interfaces cannot guarantee immunity against concurrent malicious processes working in the same directory.
- **Hard links**: Reclaimable-space figures count shared inodes once, so disk blocks are not overcounted. Removing a hard-linked duplicate removes that directory entry and decrements the link count, but disk blocks are only freed when the last link is removed.
- **Undo scope**: Undo lasts only for the current application session. Files sent to the trash or Recycle Bin must be restored from your file manager (Explorer on Windows, Finder on macOS), not from the app.

## Windows-specific limitations

Windows support is new and has been tested mainly through CI. On Windows, `requirements.txt` also installs `send2trash`, which moves deleted duplicates to the Recycle Bin.

- The executable is not code-signed, so Windows SmartScreen may warn when you start it.
- Paths longer than 260 characters are not specially handled.
- Files that exist only in the cloud (OneDrive "online-only" placeholders) are skipped, because touching them would trigger a download.
- Files with the Windows hidden or system attribute are skipped, in addition to dot-files.
- Folder names that Windows does not allow are rejected (reserved device names such as `CON` or `NUL`, characters like `: ? * " < > |`, trailing dots or spaces, names over 255 characters).
- Symlinks, junctions and mount points are treated as links and rejected.
- A file that is open in another program is reported as failed and left in place.
- On drives that may have no Recycle Bin (anything other than a fixed local disk, for example USB sticks and network shares), deleted duplicates may be deleted permanently instead. The app warns about this before you confirm and in the log.
- The native folder pickers (`zenity`, `kdialog`) are not used; the standard Tkinter dialog is shown instead.

## macOS-specific limitations

macOS support is new and has been tested through CI on macOS 15 and 26. Not yet tried on a real Mac: the first-launch steps below, the privacy prompts, iCloud placeholder files, Finder's Put Back and the Intel build. The tests run on macOS 15 and 26, but the app bundle has only been started on macOS 26. On macOS, `requirements.txt` also installs `pyobjc-framework-Cocoa`, which sends deleted duplicates to the Finder Trash.

- The app is not notarized, so Gatekeeper blocks the first launch; see [Opening the macOS app for the first time](#opening-the-macos-app-for-the-first-time).
- Deleted duplicates go to the Finder Trash through the system's trash call and are never deleted permanently. If that call fails, for example on a volume that has no Trash, the file stays where it is and the failure is reported. Whether Put Back works for these files, and how network shares without a Trash behave, is unverified on a real Mac.
- Files with the Finder "hidden" flag are skipped, in addition to dot-files. A file whose flags cannot be read counts as hidden.
- Files that iCloud Drive keeps only in the cloud (dataless placeholders) are skipped, because touching them would trigger a download. This relies on the file's `SF_DATALESS` flag and has not been tried with real iCloud files.
- Names are compared the way APFS compares them: `Report.pdf` and `report.pdf`, or the same name with composed and decomposed accents, count as one name, so a colliding file gets a suffix instead of replacing the other. This also applies on case-sensitive volumes, where a file may get a suffix it did not strictly need.
- "Operation not permitted" (`EPERM`) has two causes, and the error message names both: the file is locked in Finder (Get Info › Locked), or macOS privacy settings block File Suite (or the terminal it runs from). A locked file is reported as failed and left in place; it is not copied.
- If privacy settings block a whole folder, the Organize preview shows the error, but the duplicate scan reports no duplicates instead of an error.
- A move inside one volume keeps extended attributes and Finder tags, because the file itself is not copied. When the copy fallback is used (another volume, FAT/exFAT), the new copy gets the contents, permissions and timestamps, but not extended attributes or Finder tags.
- Folder names containing `:` are rejected, because Finder shows `:` as `/`.
- App menu items such as About and Preferences (⌘,) are Tk's defaults. When File Suite is started from source, the menu bar says "Python".

## Verifying a Windows zip

`packaging\windows\build.ps1` writes a `.sha256` file next to the zip that contains the hash and the zip file name. Compare it with the hash of the zip:

```powershell
$expected = (Get-Content .\FileSuite-windows-x64-v<version>.zip.sha256).Split(" ")[0]
$actual = (Get-FileHash -Algorithm SHA256 .\FileSuite-windows-x64-v<version>.zip).Hash
$actual -eq $expected   # case-insensitive comparison; should print True
```

For the Linux binary, run `sha256sum -c FileSuite.sha256` in `dist/`.

## Opening the macOS app for the first time

The DMG is not notarized, because the project has no paid Apple Developer account. The app inside is signed ad hoc only, so macOS blocks it the first time you open it. The steps follow Apple's documentation ([Safely open apps on your Mac](https://support.apple.com/en-us/102445), [Open a Mac app from an unknown developer](https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unknown-developer-mh40616/mac)); nobody has gone through them with File Suite on a real Mac yet, so the dialog wording may differ.

1. **Check the download.** `packaging/macos/build.sh` writes a `.sha256` file next to the DMG that contains the hash and the DMG file name. With both files in one folder (`<arch>` is `arm64` for Apple silicon and `x86_64` for Intel Macs):

   ```bash
   shasum -a 256 -c FileSuite-macos-<arch>-v<version>.dmg.sha256
   ```

   It should print `FileSuite-macos-<arch>-v<version>.dmg: OK`.
2. Open the DMG and drag **File Suite** to **Applications**.
3. Open File Suite from Applications. macOS says it cannot verify the app and offers **Done** and **Move to Trash**. Click **Done**, not Move to Trash.
4. Open **System Settings › Privacy & Security**, scroll to **Security**, click **Open Anyway** next to File Suite, confirm in the next dialog and sign in with your password or Touch ID. The button appears only after a blocked attempt, for about an hour. Afterwards File Suite opens with a double-click.

**Terminal alternative**, only for a download you trust: this removes the quarantine flag, so macOS skips its first-launch check for this app for good, with no prompt and no malware check.

```bash
xattr -dr com.apple.quarantine /Applications/FileSuite.app
```

**Privacy permissions**: the first time File Suite reads Downloads, Desktop, Documents, an external drive or a network volume, macOS asks whether to allow it, once per location. The answer is remembered and can be changed under System Settings › Privacy & Security › Files & Folders ([Apple's guide](https://support.apple.com/guide/mac-help/control-access-to-files-and-folders-on-mac-mchld5a35146/mac)). File Suite opens with Downloads preselected, so expect a question on the first scan; whether the folder dialog counts as permission is unverified. Because the app is signed ad hoc, macOS may ask again after an update; this follows from Apple's documentation and has not been tried.
