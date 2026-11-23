@echo off
rem Start Bellwether on Windows as an independent background process and return at once (scripts/start.sh on
rem Linux and macOS). The pythonw of the checkout runs scripts\start_windows.py, which starts the widget with no
rem console and its output in %%LOCALAPPDATA%%\bellwether\Logs\bellwether\start.log.
setlocal
for %%I in ("%~dp0..") do set "root=%%~fI"
if not exist "%root%\.venv\Scripts\pythonw.exe" (
  echo bellwether: %root%\.venv\Scripts\pythonw.exe not found, run uv sync in %root% 1>&2
  exit /b 1
)
"%root%\.venv\Scripts\pythonw.exe" "%root%\scripts\start_windows.py"
exit /b %errorlevel%
