@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3.12 generate_icon.py
    py -3.12 -m PyInstaller --onefile --windowed --icon app_icon.ico --name "MiniMaxPromptStudio" main.py
) else (
    python generate_icon.py
    python -m PyInstaller --onefile --windowed --icon app_icon.ico --name "MiniMaxPromptStudio" main.py
)
