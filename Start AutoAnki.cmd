@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if %errorlevel% equ 0 (
  uv run autoanki-web
) else (
  echo uv was not found on PATH.
  echo Install uv, then run this launcher again.
)

echo.
echo AutoAnki closed. Press any key to exit.
pause >nul
