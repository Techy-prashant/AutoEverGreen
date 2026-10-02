import os
import sys
import subprocess
from pathlib import Path
from paths import get_app_root
from logger import setup_logger

logger = setup_logger()

def get_startup_folder() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA environment variable not found.")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

def get_shortcut_path() -> Path:
    return get_startup_folder() / "AutoEverGreen.lnk"

def is_startup_enabled() -> bool:
    return get_shortcut_path().exists()

def enable_startup() -> bool:
    if is_startup_enabled():
        logger.info("Startup is already enabled.")
        return True

    shortcut_path = get_shortcut_path()
    
    # We want to run main.py using the current python executable.
    # If packaged via PyInstaller in future, sys.executable is the .exe itself.
    is_frozen = getattr(sys, 'frozen', False)
    
    if is_frozen:
        target_path = sys.executable
        arguments = "--background"
    else:
        target_path = sys.executable
        main_py = str(get_app_root() / "main.py")
        arguments = f'"{main_py}" --background'
        
    working_dir = str(get_app_root())

    ps_script = f"""
    $wshell = New-Object -ComObject WScript.Shell
    $shortcut = $wshell.CreateShortcut("{shortcut_path}")
    $shortcut.TargetPath = "{target_path}"
    $shortcut.Arguments = '{arguments}'
    $shortcut.WorkingDirectory = "{working_dir}"
    $shortcut.Save()
    """
    
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info(f"Startup enabled. Shortcut created at {shortcut_path}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to enable startup: {e.stderr.decode()}")
        return False

def disable_startup() -> bool:
    if not is_startup_enabled():
        logger.info("Startup is already disabled.")
        return True
        
    try:
        get_shortcut_path().unlink()
        logger.info("Startup disabled. Shortcut removed.")
        return True
    except Exception as e:
        logger.error(f"Failed to disable startup: {e}")
        return False
