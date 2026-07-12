$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$ReleaseDir = Join-Path $Root "release"
$StageDir = Join-Path $ReleaseDir "AutoAnki-Portable-Windows-x64"
$ZipPath = "$StageDir.zip"

Push-Location $Root
try {
    uv sync --group release
    uv run pyinstaller autoanki.spec --noconfirm --clean

    if (Test-Path $StageDir) { Remove-Item $StageDir -Recurse -Force }
    if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
    New-Item $StageDir -ItemType Directory | Out-Null

    Copy-Item "dist/AutoAnki/*" $StageDir -Recurse
    Copy-Item ".env.example" (Join-Path $StageDir ".env.example")
    Copy-Item "docs/PORTABLE_README.txt" (Join-Path $StageDir "README.txt")
    New-Item (Join-Path $StageDir "data") -ItemType Directory | Out-Null
    New-Item (Join-Path $StageDir "exports") -ItemType Directory | Out-Null
    Copy-Item "docs/PORTABLE_DATA_README.txt" (Join-Path $StageDir "data/README.txt")
    Copy-Item "docs/PORTABLE_EXPORTS_README.txt" (Join-Path $StageDir "exports/README.txt")

    Compress-Archive -Path "$StageDir/*" -DestinationPath $ZipPath -CompressionLevel Optimal
    Write-Host "Portable release created: $ZipPath"
}
finally {
    Pop-Location
}
