import sys
from pathlib import Path

def get_app_root() -> Path:
    """Returns the absolute path to the application root directory."""
    if getattr(sys, 'frozen', False):
        # We are running as a PyInstaller bundle
        return Path(sys.executable).parent.resolve()
    else:
        # We are running in a normal Python environment
        return Path(__file__).parent.resolve()

def resolve_path(path_str: str) -> Path:
    """Resolves a given path string against the application root if it's not absolute."""
    path = Path(path_str)
    if path.is_absolute():
        return path
    return (get_app_root() / path).resolve()
