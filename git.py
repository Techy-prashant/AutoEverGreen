import subprocess
from pathlib import Path
from typing import List, Optional
import logging
import re
from paths import get_app_root

class GitError(Exception):
    """Base exception for Git operations."""
    pass

class GitCommandError(GitError):
    """Raised when a Git command returns a non-zero exit code."""
    def __init__(self, command: str, exit_code: int, stdout: str, stderr: str):
        scrubbed_cmd = self._scrub(command)
        scrubbed_stderr = self._scrub(stderr)
        super().__init__(f"Command '{scrubbed_cmd}' failed with exit code {exit_code}.\nStderr: {scrubbed_stderr}")
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    @staticmethod
    def _scrub(text: str) -> str:
        """Removes potential secrets from strings like URLs."""
        if not text:
            return ""
        # Matches https://token@github.com and scrubs the token
        return re.sub(r'(https?://)[^@\s]+(:[^@\s]+)?@', r'\1***@', text)

class GitExecutableNotFoundError(GitError):
    """Raised when Git is not installed or not in PATH."""
    pass

class GitAuthenticationError(GitError):
    """Raised when Git authentication fails."""
    pass

class GitRepositoryNotFoundError(GitError):
    """Raised when the repository does not exist or access is denied."""
    pass

class GitNetworkError(GitError):
    """Raised when there is a network failure communicating with the remote."""
    pass

class GitManager:
    """Handles interactions with Git repositories using the git CLI."""
    
    def __init__(self, repo_path: str = ".", timeout: int = 60):
        self.repo_path = Path(repo_path)
        self.timeout = timeout
        self.logger = logging.getLogger("AutoEverGreen.Git")

    def _run(self, args: List[str], cwd: Optional[Path] = None) -> str:
        import os
        exec_cwd = cwd if cwd is not None else self.repo_path
        
        safe_commands = {"clone", "--version", "ls-remote"}
        if not exec_cwd.exists() and args[0] not in safe_commands:
            raise GitError(f"Directory {exec_cwd} does not exist.")

        # Prevent GUI credential popups so background runs fail fast instead of hanging
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GCM_INTERACTIVE"] = "never"

        cmd = ["git"] + args
        try:
            kwargs = {
                "cwd": str(exec_cwd) if exec_cwd.exists() else None,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "env": env,
                "timeout": self.timeout
            }
            if os.name == 'nt':
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                
            result = subprocess.run(cmd, **kwargs)
        except subprocess.TimeoutExpired as e:
            raise GitNetworkError(f"Git command timed out after {self.timeout}s.") from e
        except FileNotFoundError:
            raise GitExecutableNotFoundError("Git executable not found in PATH.")
            
        if result.returncode != 0:
            cmd_str = " ".join(cmd)
            stderr_lower = result.stderr.lower()
            scrubbed_stderr = GitCommandError._scrub(result.stderr)
            
            if any(err in stderr_lower for err in ["authentication failed", "could not read username", "logon failed"]):
                raise GitAuthenticationError(f"GitHub authentication failed. Please verify your Git credentials. Details: {scrubbed_stderr}")
            elif any(err in stderr_lower for err in ["not found", "does not exist", "repository not exported"]):
                raise GitRepositoryNotFoundError(f"Repository not found or access denied. Details: {scrubbed_stderr}")
            elif any(err in stderr_lower for err in ["could not resolve host", "timed out", "connection refused", "network is unreachable"]):
                raise GitNetworkError(f"Network failure communicating with remote. Details: {scrubbed_stderr}")
                
            raise GitCommandError(cmd_str, result.returncode, result.stdout, result.stderr)
            
        return result.stdout.strip()

    def version(self) -> str:
        return self._run(["--version"], cwd=get_app_root())

    def clone(self, url: str) -> None:
        if self.repo_path.exists() and any(self.repo_path.iterdir()):
            raise GitError(f"Cannot clone into {self.repo_path}: directory is not empty.")
        self.repo_path.parent.mkdir(parents=True, exist_ok=True)
        self._run(["clone", url, str(self.repo_path)], cwd=self.repo_path.parent)

    def is_repository(self) -> bool:
        if not self.repo_path.exists():
            return False
        try:
            output = self._run(["rev-parse", "--is-inside-work-tree"])
            return output == "true"
        except (GitError, FileNotFoundError):
            return False

    def _verify_repo(self) -> None:
        if not self.is_repository():
            raise GitError(f"Directory '{self.repo_path}' is not a valid Git repository.")

    def status(self) -> str:
        self._verify_repo()
        return self._run(["status", "--porcelain"])

    def check_status(self) -> bool:
        return len(self.status()) == 0

    def branch_exists(self, branch_name: str) -> bool:
        self._verify_repo()
        try:
            self._run(["rev-parse", "--verify", branch_name])
            return True
        except GitError:
            try:
                self._run(["rev-parse", "--verify", f"origin/{branch_name}"])
                return True
            except GitError:
                return False

    def checkout(self, branch: str) -> None:
        self._verify_repo()
        if not self.branch_exists(branch):
            raise GitError(f"Branch '{branch}' does not exist.")
        self._run(["checkout", branch])

    def pull(self) -> None:
        self._verify_repo()
        self._run(["pull"])

    def add(self, filepath: str) -> None:
        self._verify_repo()
        self._run(["add", filepath])

    def commit(self, message: str) -> None:
        self._verify_repo()
        self._run(["commit", "-m", message])
        
    def commit_changes(self, message: str) -> None:
        self.commit(message)

    def push(self) -> None:
        self._verify_repo()
        self._run(["push"])
        
    def push_changes(self) -> None:
        self.push()

    def rev_parse(self, target: str = "HEAD") -> str:
        self._verify_repo()
        return self._run(["rev-parse", target])

    def remote(self) -> str:
        self._verify_repo()
        return self._run(["remote", "-v"])

    def check_remote_access(self, url: str) -> bool:
        """Verifies read access to the remote repository without modifying anything."""
        try:
            self._run(["ls-remote", url], cwd=get_app_root())
            return True
        except GitError:
            raise
