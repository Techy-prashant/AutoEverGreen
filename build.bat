@echo off
echo Cleaning old build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Building AutoEverGreen...
python -m PyInstaller --name AutoEverGreen --onedir --clean --noconfirm main.py

echo Build complete! Executable is located at dist\AutoEverGreen\AutoEverGreen.exe
