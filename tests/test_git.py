import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from git import (
    GitManager, GitError, GitCommandError,
    GitExecutableNotFoundError, GitAuthenticationError, 
    GitRepositoryNotFoundError, GitNetworkError
)

class TestGitManager(unittest.TestCase):
    def setUp(self):
        self.repo_path = Path("dummy_path")
        self.git = GitManager(str(self.repo_path))

    @patch('subprocess.run')
    def test_version(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "git version 2.30.0\n"
        mock_run.return_value = mock_result

        version = self.git.version()
        self.assertEqual(version, "git version 2.30.0")
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_git_error_scrubbing(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        mock_result.stderr = "fatal: repository 'https://secret_token@github.com/repo.git' not found"
        mock_run.return_value = mock_result

        with self.assertRaises(GitRepositoryNotFoundError) as context:
             # cwd=None will fall back to script's dir for tests just to pass the exists check if we use Path(".")
             self.git._run(["clone", "https://secret_token@github.com/repo.git", "."], cwd=Path("."))
             
        # Check that secret_token is not in the error message
        self.assertNotIn("secret_token", str(context.exception))
        self.assertIn("***@", str(context.exception))

    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.iterdir')
    def test_clone_non_empty(self, mock_iterdir, mock_exists):
        mock_exists.return_value = True
        mock_iterdir.return_value = [Path("some_file")]
        
        with self.assertRaisesRegex(GitError, "not empty"):
            self.git.clone("http://repo")

    @patch('git.GitManager.is_repository')
    @patch('subprocess.run')
    @patch('pathlib.Path.exists')
    def test_status(self, mock_exists, mock_run, mock_is_repo):
        mock_exists.return_value = True
        mock_is_repo.return_value = True
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "M file.txt\n"
        mock_run.return_value = mock_result
        
        status = self.git.status()
        self.assertEqual(status, "M file.txt")

    @patch('git.GitManager.is_repository')
    def test_verify_branch_exists(self, mock_is_repo):
        mock_is_repo.return_value = True
        
        with patch.object(self.git, '_run') as mock_run:
            # First rev-parse fails, second fails
            mock_run.side_effect = GitCommandError("cmd", 1, "", "")
            self.assertFalse(self.git.branch_exists("nonexistent"))
            
            # Reset
            mock_run.side_effect = None
            self.assertTrue(self.git.branch_exists("main"))

    @patch('subprocess.run')
    def test_authentication_error(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: Authentication failed for 'https://github.com/repo.git'"
        mock_run.return_value = mock_result
        
        with self.assertRaises(GitAuthenticationError) as context:
            self.git._run(["ls-remote", "https://github.com/repo.git"], cwd=Path("."))
        self.assertIn("authentication failed", str(context.exception).lower())

    @patch('subprocess.run')
    def test_repository_not_found_error(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "remote: Repository not found.\nfatal: repository 'x' not found"
        mock_run.return_value = mock_result
        
        with self.assertRaises(GitRepositoryNotFoundError):
            self.git._run(["ls-remote", "https://github.com/repo.git"], cwd=Path("."))

    @patch('subprocess.run')
    def test_network_error(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: unable to access 'url': Could not resolve host: github.com"
        mock_run.return_value = mock_result
        
        with self.assertRaises(GitNetworkError):
            self.git._run(["ls-remote", "https://github.com/repo.git"], cwd=Path("."))

    @patch('subprocess.run')
    def test_executable_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        
        with self.assertRaises(GitExecutableNotFoundError):
            self.git._run(["--version"], cwd=Path("."))

    @patch('subprocess.run')
    def test_check_remote_access(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc123ref refs/heads/main"
        mock_run.return_value = mock_result
        
        # Should not raise exception
        self.assertTrue(self.git.check_remote_access("https://github.com/repo.git"))

if __name__ == '__main__':
    unittest.main()
