Param(
    [string]$Entry = "server.py",
    [switch]$OneFile
)

if ($env:OS -notlike "*Windows*") {
    Write-Error "This script must be run on Windows."
    exit 1
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python executable not found in PATH. Install Python and try again."
    exit 1
}

Write-Output "Installing dependencies (this may take a minute)..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

# Prepare --add-data arguments for PyInstaller (format: src;dest)
$dataPairs = @(
    "frontend;frontend",
    "routes;routes",
    "controllers;controllers",
    "assets;assets",
    "utils;utils"
)

# Build PyInstaller-style args safely (use python -m PyInstaller to avoid PATH issues)
$addDataArgs = @()
foreach ($pair in $dataPairs) {
    $src = $pair.Split(';')[0]
    if (Test-Path $src) {
        $addDataArgs += '--add-data'
        $addDataArgs += $pair
    }
}

$oneFileArg = if ($OneFile.IsPresent) { '--onefile' } else { '--onedir' }

Write-Output "Running PyInstaller (entry: $Entry, mode: $oneFileArg)"

# Use temporary directories for spec/work/dist on the same drive as the repo to avoid cross-drive relpath errors
# Use the system temp folder for the PyInstaller workspace to avoid permission issues on the repo drive.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$tmpBase = Join-Path $env:TEMP 'DataLens_pyinstaller'
# create/clean the workspace
if (Test-Path $tmpBase) {
    Get-ChildItem -Path $tmpBase -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
} else {
    New-Item -ItemType Directory -Path $tmpBase -Force | Out-Null
}

# copy entry script into the temp workspace
$entrySrc = Join-Path $scriptDir $Entry
if (Test-Path $entrySrc) { Copy-Item -Path $entrySrc -Destination (Join-Path $tmpBase (Split-Path $Entry -Leaf)) -Force }

# copy data folders (use destination names from dataPairs)
foreach ($pair in $dataPairs) {
    $srcFolder = $pair.Split(';')[0]
    $destFolder = $pair.Split(';')[1]
    if (Test-Path (Join-Path $scriptDir $srcFolder)) {
        $destPath = Join-Path $tmpBase $destFolder
        Copy-Item -Path (Join-Path $scriptDir $srcFolder) -Destination $destPath -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$specPath = $tmpBase
$distPath = Join-Path $tmpBase 'dist'
$workPath = Join-Path $tmpBase 'build'
if (-Not (Test-Path $distPath)) { New-Item -ItemType Directory -Path $distPath -Force | Out-Null }
if (-Not (Test-Path $workPath)) { New-Item -ItemType Directory -Path $workPath -Force | Out-Null }

# Update entry path to the copied script inside the temp workspace
$Entry = Join-Path $tmpBase (Split-Path $Entry -Leaf)

# If an .ico file exists under assets, instruct PyInstaller to use it as the exe icon
$iconPathCandidates = @("assets\\DataLens.ico","assets\\datalens.ico","assets\\datalens-icon.ico")
$iconArg = @()
foreach ($p in $iconPathCandidates) {
    $full = Join-Path $scriptDir $p
    if (Test-Path $full) {
        $iconArg = @('--icon',(Resolve-Path $full).Path)
        break
    }
}

$pyArgs = @('--noconfirm','--clean',$oneFileArg,'--name','DataLens') + $addDataArgs + $iconArg + @('--specpath',$specPath,'--distpath',$distPath,'--workpath',$workPath,$Entry)
& python -m PyInstaller @pyArgs

# Copy outputs to release/build for packaging
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$releaseDir = Join-Path $scriptDir "release\build"

# Try to create the release dir; if permission denied, fallback to temp directory
try {
    if (-Not (Test-Path $releaseDir)) { New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null }
} catch {
    $msg = "Cannot create " + $releaseDir + ": " + ($_.ToString()) + " Attempting fallback to TEMP directory."
    Write-Warning $msg
    $releaseDir = Join-Path $env:TEMP 'DataLens_build'
    if (-Not (Test-Path $releaseDir)) { New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null }
}

if ($OneFile.IsPresent) {
    $exeSrc = Join-Path $scriptDir "dist\DataLens.exe"
    if (Test-Path $exeSrc) { Copy-Item -Path $exeSrc -Destination $releaseDir -Force }
} else {
    $dirSrc = Join-Path $scriptDir "dist\DataLens"
    if (Test-Path $dirSrc) {
        $dest = Join-Path $releaseDir "DataLens"
        if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
        Copy-Item -Path $dirSrc -Destination $dest -Recurse -Force
    }
}

Write-Output "Build finished. Artifacts placed in: $releaseDir"
Write-Output "Next: open the Inno Setup script at release\DataLensInstaller.iss with Inno Setup Compiler (ISCC) to create the installer."
