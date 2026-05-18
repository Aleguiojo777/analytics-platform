param(
  [string]$Version = "dev",
  [string]$OutputDir = "release"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$distRoot = Join-Path $root $OutputDir
$packageName = "DataLens-$Version"
$staging = Join-Path $distRoot $packageName
$zipPath = Join-Path $distRoot "$packageName.zip"

if (Test-Path $staging) {
  Remove-Item -LiteralPath $staging -Recurse -Force
}

New-Item -ItemType Directory -Path $staging | Out-Null

$include = @(
  "services",
  "controllers",
  "frontend",
  "routes",
  "utils",
  "assets",
  "requirements.txt",
  "server.py",
  "README.md",
  "PYTHON_SETUP.md",
  "run-datalens.bat",
  ".env.example"
)

foreach ($item in $include) {
  $source = Join-Path $root $item
  if (Test-Path $source) {
    Copy-Item -LiteralPath $source -Destination $staging -Recurse -Force
  }
}

$launcherSource = Join-Path $root "scripts\DataLensLauncher.cs"
$launcherIcon = Join-Path $root "assets\datalens.ico"
$launcherExe = Join-Path $staging "DataLens.exe"
$cscCandidates = @(
  "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
  "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe"
)
$csc = $cscCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($csc -and (Test-Path $launcherSource) -and (Test-Path $launcherIcon)) {
  & $csc /nologo /target:winexe /platform:anycpu /win32icon:"$launcherIcon" /reference:System.Windows.Forms.dll /out:"$launcherExe" "$launcherSource"
} else {
  Write-Warning "Could not compile DataLens.exe launcher. Falling back to run-datalens.bat only."
}

Get-ChildItem -LiteralPath $staging -Directory -Recurse -Force -Filter "__pycache__" |
  Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $staging -File -Recurse -Force |
  Where-Object { $_.Extension -in '.pyc', '.pyo' } |
  Remove-Item -Force

@"
DataLens $Version

Quick start:
1. Install Python 3.9+.
2. Install Microsoft ODBC Driver 18 for SQL Server.
3. Double-click DataLens.exe.
4. Open http://localhost:3000 if the browser does not open automatically.

DataLens runs locally on your desktop.
If DataLens.exe is blocked by Windows SmartScreen, use run-datalens.bat as the fallback launcher.
"@ | Set-Content -Path (Join-Path $staging "START_HERE.txt") -Encoding UTF8

if (Test-Path $zipPath) {
  Remove-Item -LiteralPath $zipPath -Force
}

Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -Force
Write-Host "Created $zipPath"
