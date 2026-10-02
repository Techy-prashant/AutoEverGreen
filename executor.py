import os
import shutil
import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

from config import ConfigManager, RepositoryConfig
from git import GitManager, GitError, GitAuthenticationError, GitRepositoryNotFoundError, GitExecutableNotFoundError
from logger import setup_logger
from state import StateTracker
from paths import resolve_path, get_app_root, get_project_root

@dataclass
class JobResult:
    commit_id: str
    success: bool
    error: Optional[str] = None
    dry_run: bool = False

@dataclass
class RepoExecutionResult:
    repo_name: str
    success: bool
    jobs: List[JobResult] = field(default_factory=list)
    error: Optional[str] = None

@dataclass
class ExecutionResult:
    total_repos: int = 0
    repo_results: List[RepoExecutionResult] = field(default_factory=list)

class FileOperator:
    """Applies required file operations securely."""
    def apply(self, repo_path: Path, file_path: str, operation: str, content: Optional[str] = None, source_path: Optional[str] = None) -> None:
        target = (repo_path / file_path).resolve()
        
        # Prevent path traversal outside repo
        if not target.is_relative_to(repo_path.resolve()):
            raise ValueError(f"File path {file_path} escapes repository boundaries.")
            
        target.parent.mkdir(parents=True, exist_ok=True)
        
        if operation == "copy":
            if not source_path:
                raise ValueError("source_path is required for copy operation")
            
            src = (get_project_root() / source_path).resolve()
            
            # Validate source path
            if not src.is_relative_to(get_project_root()):
                raise ValueError(f"Source path {source_path} escapes project root.")
                
            if not src.exists():
                raise FileNotFoundError(f"Source path {source_path} does not exist.")
                
            if src.is_dir():
                raise IsADirectoryError(f"Source path {source_path} is a directory.")
                
            # Check protected paths
            rel_src = src.relative_to(get_project_root())
            parts = rel_src.parts
            if parts:
                first_part = parts[0]
                protected_dirs = {".git", "dist", "build", "logs", "repos", "__pycache__"}
                if first_part in protected_dirs:
                    raise ValueError(f"Source path {source_path} is in a protected directory.")
            
            if rel_src.name in {"state.json", "config.json"} or rel_src.suffix == ".pyc":
                raise ValueError(f"Source path {source_path} is a protected file type.")
                
            shutil.copy2(src, target)
        elif operation == "append":
            with open(target, 'a', encoding='utf-8') as f:
                f.write(content)
        elif operation in ("create", "update"):
            with open(target, 'w', encoding='utf-8') as f:
                f.write(content)
        else:
            raise ValueError(f"Unsupported operation: {operation}")

class DryRunFileOperator(FileOperator):
    def __init__(self, logger):
        self.logger = logger
        
    def apply(self, repo_path: Path, file_path: str, operation: str, content: Optional[str] = None, source_path: Optional[str] = None) -> None:
        if operation == "copy":
            if not source_path:
                raise ValueError("source_path is required for copy operation")
            
            target = (repo_path / file_path).resolve()
            if not target.is_relative_to(repo_path.resolve()):
                raise ValueError(f"File path {file_path} escapes repository boundaries.")
                
            src = (get_project_root() / source_path).resolve()
            if not src.is_relative_to(get_project_root()):
                raise ValueError(f"Source path {source_path} escapes project root.")
            if not src.exists():
                raise FileNotFoundError(f"Source path {source_path} does not exist.")
            if src.is_dir():
                raise IsADirectoryError(f"Source path {source_path} is a directory.")
                
            rel_src = src.relative_to(get_project_root())
            parts = rel_src.parts
            if parts:
                if parts[0] in {".git", "dist", "build", "logs", "repos", "__pycache__"}:
                    raise ValueError(f"Source path {source_path} is in a protected directory.")
            if rel_src.name in {"state.json", "config.json"} or rel_src.suffix == ".pyc":
                raise ValueError(f"Source path {source_path} is a protected file type.")
                
            self.logger.info(f"DRY RUN: would copy file {source_path} to {file_path}")
        else:
            self.logger.info(f"DRY RUN: would modify file {file_path} with {operation}")

class DryRunGitManager(GitManager):
    def __init__(self, path: str, logger):
        # Bypass checking if it's a real git repo during init
        self.repo_dir = path
        self.logger = logger
        self._sha_counter = 0

    def clone(self, url: str) -> None:
        self.logger.info(f"DRY RUN: would clone repository {url}")

    def checkout(self, branch: str) -> None:
        self.logger.info(f"DRY RUN: would checkout branch {branch}")

    def pull(self) -> None:
        self.logger.info("DRY RUN: would pull from remote")

    def add(self, path: str) -> None:
        self.logger.info(f"DRY RUN: would stage {path}")

    def commit(self, message: str) -> None:
        self.logger.info(f"DRY RUN: would create commit with message '{message}'")
        self._sha_counter += 1

    def push(self) -> None:
        self.logger.info("DRY RUN: would push changes")

    def check_remote_access(self, url: str) -> bool:
        self.logger.info(f"DRY RUN: would verify remote access using ls-remote for {url}")
        return True

    def rev_parse(self, rev: str) -> str:
        if rev == "HEAD":
            return f"dry-run-sha-{self._sha_counter}"
        return f"dry-run-sha-{self._sha_counter-1}"

    def _run(self, args: List[str]) -> str:
        if args[0] == "fetch":
            self.logger.info("DRY RUN: would fetch from origin")
            return ""
        if args[0] == "status":
            self.logger.info(f"DRY RUN: would check status for {args[-1]}")
            return "M dummy"
        return ""

class DryRunStateTracker:
    def __init__(self, real_tracker: StateTracker, logger):
        self.real = real_tracker
        self.logger = logger
        self.current_batch_id = self.real.current_batch_id
        self.batch_states = self.real.batch_states

    def record_job(self, repository: str, branch: str, job_index: int, status: str, commit_sha: Optional[str] = None, error: Optional[str] = None) -> None:
        self.logger.info(f"DRY RUN: would record job {job_index} for {repository}:{branch} with status {status}")

    def mark_batch_completed(self) -> None:
        self.logger.info("DRY RUN: would mark batch as completed")

    def start_new_batch(self) -> str:
        self.logger.info("DRY RUN: would start new batch")
        self.current_batch_id = "dry-run-batch"
        return self.current_batch_id
        
    def is_job_completed(self, *args, **kwargs) -> bool:
        return self.real.is_job_completed(*args, **kwargs)

class AutoEverGreenExecutor:
    """The central execution engine orchestrating Git and file operations."""
    def __init__(self, config_manager: ConfigManager, work_dir: str = "repos", state_file: str = "state.json", dry_run: bool = False):
        self.config_manager = config_manager
        self.work_dir = resolve_path(work_dir)
        self.logger = setup_logger("AutoEverGreen.Executor")
        self.dry_run = dry_run
        
        real_tracker = StateTracker(resolve_path(state_file))
        if self.dry_run:
            self.state_tracker = DryRunStateTracker(real_tracker, self.logger)
            self.file_operator = DryRunFileOperator(self.logger)
        else:
            self.state_tracker = real_tracker
            self.file_operator = FileOperator()
            
    def has_pending_work(self) -> bool:
        if not self.config_manager.config:
            return False
            
        if len(self.config_manager.config.repositories) == 0:
            return False
            
        for repo_config in self.config_manager.config.repositories:
            for idx in range(len(repo_config.commits)):
                if repo_config.commits[idx].enabled and not self.state_tracker.is_job_completed(repo_config.name, repo_config.branch, idx):
                    return True
        return False
        
    def run(self) -> ExecutionResult:
        if not self.config_manager.config:
            self.logger.error("Configuration not loaded.")
            return ExecutionResult()
            
        app_config = self.config_manager.config
        result = ExecutionResult(total_repos=len(app_config.repositories))
        
        goal = app_config.settings.max_commits_per_run
        self.logger.info(f"GOAL: {goal}")
        self.logger.info("EXECUTION STARTED")
        
        if not self.state_tracker.current_batch_id or (
            self.state_tracker.current_batch_id in self.state_tracker.batch_states and 
            self.state_tracker.batch_states[self.state_tracker.current_batch_id].is_completed
        ):
            self.state_tracker.start_new_batch()
        
        global_commits_processed = 0
        total_failed_jobs = 0
        total_skipped_jobs = 0
        total_remaining_jobs = 0
        
        for repo_config in app_config.repositories:
            if global_commits_processed >= goal:
                break
                
            remaining_goal = goal - global_commits_processed
            repo_res, repo_commits, repo_fails, repo_skips, repo_remain = self._process_repository(repo_config, remaining_goal, global_commits_processed, goal)
            global_commits_processed += repo_commits
            total_failed_jobs += repo_fails
            total_skipped_jobs += repo_skips
            total_remaining_jobs += repo_remain
            result.repo_results.append(repo_res)
            
        all_success = all(r.success for r in result.repo_results)
        
        # We also need to count remaining jobs across unprocessed repos
        unprocessed_repos = [r for r in app_config.repositories if not any(rr.repo_name == r.name for rr in result.repo_results)]
        for r in unprocessed_repos:
            total_remaining_jobs += sum(1 for idx in range(len(r.commits)) if r.commits[idx].enabled and not self.state_tracker.is_job_completed(r.name, r.branch, idx))

        if global_commits_processed >= goal:
            self.logger.info("EXECUTION GOAL REACHED")
        
        if all_success and total_remaining_jobs == 0:
            self.state_tracker.mark_batch_completed()
            
        self.logger.info("--- EXECUTION SUMMARY ---")
        self.logger.info(f"Requested: {goal}")
        self.logger.info(f"Successful commits: {global_commits_processed}")
        self.logger.info(f"Failed jobs: {total_failed_jobs}")
        self.logger.info(f"Skipped jobs: {total_skipped_jobs}")
        self.logger.info(f"Remaining jobs: {total_remaining_jobs}")
        
        if global_commits_processed >= goal:
            self.logger.info("Status: GOAL_REACHED")
        elif total_remaining_jobs == 0:
            self.logger.info("Status: BATCH_COMPLETED")
        else:
            self.logger.info("Status: INCOMPLETE")
            
        return result
        
    def _process_repository(self, repo_config: RepositoryConfig, allowed_commits: int, current_global_count: int, total_goal: int):
        self.logger.info(f"Repository selected: {repo_config.name}")
        repo_result = RepoExecutionResult(repo_name=repo_config.name, success=True)
        repo_path = self.work_dir / repo_config.name
        
        failed_jobs = 0
        skipped_jobs = 0
        remaining_jobs = 0
        
        if self.dry_run:
            git = DryRunGitManager(str(repo_path), self.logger)
        else:
            git = GitManager(str(repo_path))
        
        try:
            self.logger.info(f"Verifying remote access for {repo_config.url}")
            git.check_remote_access(repo_config.url)
            
            if not repo_path.exists():
                self.logger.info(f"Cloning repository {repo_config.url}")
                git.clone(repo_config.url)
            
            git._run(["fetch", "origin"])
            git.checkout(repo_config.branch)
            self.logger.info(f"Branch selected: {repo_config.branch}")
            git.pull()
                
        except (GitAuthenticationError, GitRepositoryNotFoundError, GitExecutableNotFoundError) as e:
            # Fatal startup / auth errors must propagate to the top-level boundary
            raise
        except GitError as e:
            self.logger.error(f"Critical Git failure on repo {repo_config.name}: {e}")
            repo_result.success = False
            repo_result.error = str(e)
            
            # Count remaining pending jobs for this repo
            for idx in range(len(repo_config.commits)):
                 if repo_config.commits[idx].enabled and not self.state_tracker.is_job_completed(repo_config.name, repo_config.branch, idx):
                     remaining_jobs += 1
            return repo_result, 0, 0, 0, remaining_jobs

        commits_processed = 0
        pushed_needed = False
        
        for idx, commit_cfg in enumerate(repo_config.commits):
            if commits_processed >= allowed_commits:
                if commit_cfg.enabled and not self.state_tracker.is_job_completed(repo_config.name, repo_config.branch, idx):
                    remaining_jobs += 1
                continue
                
            job_id = f"{repo_config.name}:{repo_config.branch}:{idx}"
            
            if not commit_cfg.enabled or self.state_tracker.is_job_completed(repo_config.name, repo_config.branch, idx):
                skipped_jobs += 1
                continue
                
            self.logger.info(f"Job started: {job_id}")
            job_res = JobResult(commit_id=job_id, success=False, dry_run=self.dry_run)
            
            try:
                self.file_operator.apply(repo_path, commit_cfg.file_path, commit_cfg.operation, content=commit_cfg.content, source_path=commit_cfg.source_path)
                self.logger.info(f"File operation applied: {commit_cfg.operation} on {commit_cfg.file_path}")
                
                git.add(commit_cfg.file_path)
                self.logger.info(f"Git add result: staged {commit_cfg.file_path}")
                
                status_out = git._run(["status", "--porcelain", commit_cfg.file_path])
                if not status_out.strip():
                     raise ValueError("No changes detected. Skipping empty commit.")
                
                date_str = datetime.datetime.now().strftime("%Y-%m-%d")
                msg = commit_cfg.message_template.replace("{date}", date_str)
                
                head_before = git.rev_parse("HEAD")
                git.commit(msg)
                self.logger.info(f"Commit result: successfully created commit with message '{msg}'")
                
                head_after = git.rev_parse("HEAD")
                if head_before == head_after:
                     raise ValueError("Commit verification failed: HEAD did not move.")
                
                self.logger.info(f"Commit SHA: {head_after}")
                     
                job_res.success = True
                self.state_tracker.record_job(repo_config.name, repo_config.branch, idx, status="success", commit_sha=head_after)
                commits_processed += 1
                current_global_count += 1
                pushed_needed = True
                
                self.logger.info(f"COMMIT SUCCESS: {current_global_count}/{total_goal}")
                self.logger.info(f"Job {job_id} succeeded.")
                
            except Exception as e:
                self.logger.error(f"Error executing job {job_id}: {e}")
                job_res.error = str(e)
                repo_result.success = False
                self.state_tracker.record_job(repo_config.name, repo_config.branch, idx, status="error", error=str(e))
                failed_jobs += 1
                remaining_jobs += 1
                
            repo_result.jobs.append(job_res)
            
            if not job_res.success:
                # Count remaining unprocessed jobs
                for rem_idx in range(idx + 1, len(repo_config.commits)):
                     if repo_config.commits[rem_idx].enabled and not self.state_tracker.is_job_completed(repo_config.name, repo_config.branch, rem_idx):
                         remaining_jobs += 1
                break

        if pushed_needed:
            try:
                git.push()
                self.logger.info(f"Push result: Successfully pushed changes for {repo_config.name}")
            except GitError as e:
                self.logger.error(f"Error pushing {repo_config.name}: {e}")
                repo_result.success = False
                repo_result.error = f"Push failed: {e}"
                
        return repo_result, commits_processed, failed_jobs, skipped_jobs, remaining_jobs
