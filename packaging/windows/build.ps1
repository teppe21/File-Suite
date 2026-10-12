# Builds the Windows one-dir bundle and packs it into dist\FileSuite-windows-x64-v<version>.zip.
$ErrorActionPreference = "Stop"

function Invoke-Native {
    # Windows PowerShell 5.1 turns native stderr output into errors; judge by exit code instead.
    $ErrorActionPreference = "Continue"
    & $args[0] $args[1..($args.Length - 1)]
    if ($LASTEXITCODE -ne 0) { throw "'$($args -join ' ')' failed with exit code $LASTEXITCODE" }
}

Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..\.."))

$version = (& python -c "import version; print(version.__version__)").Trim()
if (-not $version) { throw "Could not read the version from version.py" }
Write-Host "Building File Suite v$version"

if (-not (Test-Path ".venv")) {
    Invoke-Native python -m venv .venv
}
$py = Join-Path (Get-Location) ".venv\Scripts\python.exe"

Invoke-Native $py -m pip install --upgrade pip
Invoke-Native $py -m pip install -r requirements.txt
Invoke-Native $py -m pip install "pyinstaller>=6,<7"

Invoke-Native $py -m PyInstaller --noconfirm --clean packaging\windows\FileSuite.spec
if (-not (Test-Path "dist\FileSuite\FileSuite.exe")) { throw "Build did not produce dist\FileSuite\FileSuite.exe" }

$zip = "FileSuite-windows-x64-v$version.zip"
$pack = @'
import hashlib, os, shutil, sys
zip_name = sys.argv[1]
if os.path.exists("dist/" + zip_name):
    os.remove("dist/" + zip_name)
shutil.make_archive("dist/" + zip_name[:-4], "zip", "dist", "FileSuite")
digest = hashlib.sha256(open("dist/" + zip_name, "rb").read()).hexdigest()
with open("dist/" + zip_name + ".sha256", "w", newline="\n") as f:
    f.write(digest + "  " + zip_name + "\n")
'@
$pack | & $py - $zip
if ($LASTEXITCODE -ne 0) { throw "Packaging failed" }
Write-Host "Wrote dist\$zip and dist\$zip.sha256"
