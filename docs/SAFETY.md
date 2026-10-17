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
8. **No-clobber moves**: On Linux a move hard-links the file to its destination and then removes the source, which fails instead of replacing a file that appeared at the destination after the checks. Where hard links are unavailable (another drive, FAT/exFAT) the file is copied into an exclusively created destination and any partial copy is removed on error. On Windows a plain rename already refuses to overwrite.
9. **FreeDesktop trash**: On Linux, files sent to trash are moved into `$XDG_DATA_HOME/Trash/files` (default `~/.local/share/Trash/files`) with conforming `.trashinfo` metadata. The metadata file is created exclusively, so another application's trash entry is never overwritten; a taken name moves on to the next free one. If the move fails, the metadata file is removed so no orphaned trash entry is left.
10. **A kept copy is always left**: Moving or trashing duplicates is refused while every copy of a group is selected. Any copy can be the one kept.
11. **Stale scan protection**: Duplicate scans check file metadata before and after hashing. Right before moving or trashing duplicates, each selected file and the group's kept copies are checked again. A selected file whose size, modification time or inode changed since the scan is skipped, and a group with no unchanged kept copy left is skipped entirely. Every skip is written to the Activity Log.
12. **Session undo**: A single-level, in-memory undo moves organized or isolated files back to their original locations in reverse order. If a file now exists at the original location, that file is not overwritten.

## Limitations

- **Platforms**: Linux desktop environments (X11 and Wayland) are the primary target and follow XDG and FreeDesktop standards. Windows support is experimental; see [Windows-specific limitations](#windows-specific-limitations).
- **Race conditions**: Despite the revalidation above, standard OS filesystem interfaces cannot guarantee immunity against concurrent malicious processes working in the same directory.
- **Hard links**: Reclaimable-space figures count shared inodes once, so disk blocks are not overcounted. Removing a hard-linked duplicate removes that directory entry and decrements the link count, but disk blocks are only freed when the last link is removed.
- **Undo scope**: Undo lasts only for the current application session. Files sent to the trash or Recycle Bin must be restored from your file manager (Explorer on Windows), not from the app.

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

## Verifying a Windows zip

`packaging\windows\build.ps1` writes a `.sha256` file next to the zip that contains the hash and the zip file name. Compare it with the hash of the zip:

```powershell
$expected = (Get-Content .\FileSuite-windows-x64-v<version>.zip.sha256).Split(" ")[0]
$actual = (Get-FileHash -Algorithm SHA256 .\FileSuite-windows-x64-v<version>.zip).Hash
$actual -eq $expected   # case-insensitive comparison; should print True
```

For the Linux binary, run `sha256sum -c FileSuite.sha256` in `dist/`.
