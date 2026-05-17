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
  "analytics_insights.py",
  "controllers",
  "frontend",
  "routes",
  "utils",
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
3. Double-click run-datalens.bat.
4. Open http://localhost:3000 if the browser does not open automatically.

DataLens runs locally on your desktop.
"@ | Set-Content -Path (Join-Path $staging "START_HERE.txt") -Encoding UTF8

if (Test-Path $zipPath) {
  Remove-Item -LiteralPath $zipPath -Force
}

Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -Force
Write-Host "Created $zipPath"

