import argparse
import sys
import enum
import os
import msvcrt
from pathlib import Path
from executor import AutoEverGreenExecutor
from config import ConfigManager
from logger import setup_logger
from git import GitExecutableNotFoundError, GitAuthenticationError, GitRepositoryNotFoundError

logger = setup_logger()
_lock_fd = None

class ExitCode(enum.IntEnum):
    SUCCESS = 0
    CONFIG_ERROR = 1
    GIT_NOT_FOUND = 2
    AUTH_FAILURE = 3
    REPO_ACCESS_FAILURE = 4
    ALREADY_RUNNING = 5
    UNEXPECTED_ERROR = 99

def acquire_lock() -> bool:
    global _lock_fd
    lock_file = Path(os.environ.get("TEMP", ".")) / "autoevergreen.lock"
    try:
        _lock_fd = open(lock_file, "w")
        msvcrt.locking(_lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AutoEverGreen - Automated GitHub Activity")
    parser.add_argument("--config", type=str, default=None, help="Path to config file")
    parser.add_argument("--dry-run", action="store_true", help="Run without making any actual changes")
    parser.add_argument("--startup", choices=["enable", "disable", "status"], help="Manage Windows Startup entry")
    parser.add_argument("--gui", action="store_true", help="Launch the graphical dashboard (default when no flags given)")
    parser.add_argument("--background", action="store_true", help="Run in headless background mode (no GUI)")
    return parser.parse_args()

def handle_startup_commands(action: str) -> None:
    from startup import enable_startup, disable_startup, is_startup_enabled
    if action == "enable":
        enable_startup()
    elif action == "disable":
        disable_startup()
    elif action == "status":
        if is_startup_enabled():
            logger.info("Startup is ENABLED")
        else:
            logger.info("Startup is DISABLED")
    sys.exit(ExitCode.SUCCESS.value)

def run_background(config_path: str, force_dry_run: bool) -> None:
    """Headless execution — existing behavior, now callable from GUI and CLI."""
    logger.info("APPLICATION STARTUP")
    
    if not acquire_lock():
        logger.error("AutoEverGreen is already running. Exiting.")
        logger.info("APPLICATION SHUTDOWN")
        sys.exit(ExitCode.ALREADY_RUNNING.value)
        
    config_manager = ConfigManager(config_path)
    
    try:
        config_manager.load_config()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        logger.info("APPLICATION SHUTDOWN")
        sys.exit(ExitCode.CONFIG_ERROR.value)
        
    dry_run = force_dry_run or config_manager.config.settings.dry_run
    
    try:
        executor = AutoEverGreenExecutor(config_manager, dry_run=dry_run)
        
        if not executor.has_pending_work():
            logger.info("No pending work detected")
            logger.info("EXECUTION SUMMARY: NO_WORK")
            logger.info("APPLICATION SHUTDOWN")
            sys.exit(ExitCode.SUCCESS.value)
            
        executor.run()
        
    except GitExecutableNotFoundError as e:
        logger.error(str(e))
        logger.info("APPLICATION SHUTDOWN")
        sys.exit(ExitCode.GIT_NOT_FOUND.value)
    except GitAuthenticationError as e:
        logger.error(str(e))
        logger.info("APPLICATION SHUTDOWN")
        sys.exit(ExitCode.AUTH_FAILURE.value)
    except GitRepositoryNotFoundError as e:
        logger.error(str(e))
        logger.info("APPLICATION SHUTDOWN")
        sys.exit(ExitCode.REPO_ACCESS_FAILURE.value)
    except Exception as e:
        logger.exception(f"Unexpected application error: {e}")
        logger.info("APPLICATION SHUTDOWN")
        sys.exit(ExitCode.UNEXPECTED_ERROR.value)
        
    logger.info("APPLICATION SHUTDOWN")
    sys.exit(ExitCode.SUCCESS.value)

def run_gui(config_path: str | None) -> None:
    """Launch the graphical dashboard."""
    try:
        from gui.service import AppService
        from gui.app import AutoEverGreenApp
        svc = AppService(config_path)
        app = AutoEverGreenApp(svc)
        app.mainloop()
    except Exception as e:
        logger.exception(f"GUI startup error: {e}")
        sys.exit(ExitCode.UNEXPECTED_ERROR.value)

def main() -> None:
    args = parse_args()
    
    if args.startup:
        handle_startup_commands(args.startup)

    # Determine mode:
    # 1. Explicit --background → headless (backwards compatible with old --config usage)
    # 2. Explicit --gui        → GUI
    # 3. --config but no --gui → headless (preserves: AutoEverGreen.exe --config foo.json)
    # 4. No flags at all       → GUI (double-click friendly)

    config_path = args.config or "config/publish_config.json"

    if args.background or (args.config and not args.gui):
        run_background(config_path, args.dry_run)
    else:
        run_gui(args.config)

if __name__ == "__main__":
    main()
