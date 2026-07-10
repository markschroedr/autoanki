@echo off
setlocal
cd /d "%~dp0"

where uv >NUL 2>NUL
if errorlevel 1 (
  echo Error: uv is not installed or not in PATH.
  echo Install uv first: https://docs.astral.sh/uv/
  exit /b 1
)

uv sync --frozen
if errorlevel 1 exit /b %errorlevel%

uv run python main.py %*
exit /b %errorlevel%
