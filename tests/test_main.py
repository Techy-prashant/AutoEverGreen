import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

from main import main, ExitCode
from git import GitExecutableNotFoundError, GitAuthenticationError, GitRepositoryNotFoundError

class TestMain(unittest.TestCase):
    def setUp(self):
        self.mock_exit = patch('sys.exit').start()
        self.mock_exit.side_effect = SystemExit
        
        self.mock_logger_info = patch('main.logger.info').start()
        self.mock_logger_error = patch('main.logger.error').start()
        self.mock_logger_exception = patch('main.logger.exception').start()
        
        # Always allow lock by default in tests
        self.mock_acquire_lock = patch('main.acquire_lock').start()
        self.mock_acquire_lock.return_value = True
        
        self.mock_parse_args = patch('main.parse_args').start()
        args = MagicMock()
        args.config = "dummy_config.json"
        args.dry_run = True
        args.startup = None
        self.mock_parse_args.return_value = args
        
        self.mock_config_manager = patch('main.ConfigManager').start()
        self.mock_config_manager.return_value.config.settings.dry_run = True
        
        self.mock_executor_cls = patch('main.AutoEverGreenExecutor').start()
        self.mock_executor = self.mock_executor_cls.return_value
        self.mock_executor.has_pending_work.return_value = True

    def tearDown(self):
        patch.stopall()

    def test_missing_config(self):
        self.mock_config_manager.return_value.load_config.side_effect = FileNotFoundError("Not found")
        
        with self.assertRaises(SystemExit):
            main()
            
        self.mock_exit.assert_called_once_with(ExitCode.CONFIG_ERROR.value)
        self.mock_logger_info.assert_any_call("APPLICATION SHUTDOWN")

    def test_invalid_config(self):
        self.mock_config_manager.return_value.load_config.side_effect = ValueError("Bad config")
        
        with self.assertRaises(SystemExit):
            main()
        
        self.mock_exit.assert_called_once_with(ExitCode.CONFIG_ERROR.value)
        self.mock_logger_info.assert_any_call("APPLICATION SHUTDOWN")

    def test_no_pending_work(self):
        self.mock_executor.has_pending_work.return_value = False
        
        with self.assertRaises(SystemExit):
            main()
        
        self.mock_logger_info.assert_any_call("No pending work detected")
        self.mock_logger_info.assert_any_call("EXECUTION SUMMARY: NO_WORK")
        self.mock_exit.assert_called_once_with(ExitCode.SUCCESS.value)
        self.mock_executor.run.assert_not_called()

    def test_successful_execution(self):
        with self.assertRaises(SystemExit):
            main()
        
        self.mock_executor.run.assert_called_once()
        self.mock_exit.assert_called_once_with(ExitCode.SUCCESS.value)
        self.mock_logger_info.assert_any_call("APPLICATION SHUTDOWN")

    def test_git_not_found(self):
        self.mock_executor.run.side_effect = GitExecutableNotFoundError("git not found")
        with self.assertRaises(SystemExit):
            main()
        self.mock_exit.assert_called_once_with(ExitCode.GIT_NOT_FOUND.value)

    def test_auth_failure(self):
        self.mock_executor.run.side_effect = GitAuthenticationError("auth failed")
        with self.assertRaises(SystemExit):
            main()
        self.mock_exit.assert_called_once_with(ExitCode.AUTH_FAILURE.value)

    def test_repo_access_failure(self):
        self.mock_executor.run.side_effect = GitRepositoryNotFoundError("repo missing")
        with self.assertRaises(SystemExit):
            main()
        self.mock_exit.assert_called_once_with(ExitCode.REPO_ACCESS_FAILURE.value)

    def test_unexpected_error(self):
        self.mock_executor.run.side_effect = RuntimeError("Something terrible")
        with self.assertRaises(SystemExit):
            main()
        self.mock_logger_exception.assert_called_once()
        self.mock_exit.assert_called_once_with(ExitCode.UNEXPECTED_ERROR.value)

    def test_already_running(self):
        self.mock_acquire_lock.return_value = False
        with self.assertRaises(SystemExit):
            main()
        self.mock_exit.assert_called_once_with(ExitCode.ALREADY_RUNNING.value)

    @patch('main.handle_startup_commands')
    def test_startup_command_dispatches(self, mock_handle):
        self.mock_parse_args.return_value.startup = "enable"
        
        with self.assertRaises(SystemExit):
            main()
        
        mock_handle.assert_called_once_with("enable")
        
        # When startup is passed, handle_startup_commands exits, so the rest is not run
        # Wait, handle_startup_commands calls sys.exit, but we patched handle_startup_commands so it returns normally.
        # So we just verify it was called.

if __name__ == "__main__":
    unittest.main()
