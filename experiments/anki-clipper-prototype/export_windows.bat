@echo off
setlocal
cd /d "%~dp0"

set ZIP_NAME=anki-clipper-windows.zip

powershell -NoProfile -Command ^
  "$exclude = @('.git', '.venv', '__pycache__', '.DS_Store', 'anki-clipper.log', 'cards\\media');" ^
  "$items = Get-ChildItem -Force | Where-Object { $exclude -notcontains $_.Name };" ^
  "if (Test-Path '%ZIP_NAME%') { Remove-Item '%ZIP_NAME%' -Force };" ^
  "Compress-Archive -Path $items -DestinationPath '%ZIP_NAME%' -Force"

if errorlevel 1 (
  echo Export failed.
  exit /b 1
)

echo Export created: %ZIP_NAME%
