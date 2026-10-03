import unittest
import tempfile
import subprocess
import json
import os
import shutil
import sys
from pathlib import Path

class AutoEverGreenIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        
        # Paths
        self.remote_repo_path = self.base_path / "remote.git"
        self.app_root = self.base_path / "app"
        self.config_dir = self.app_root / "config"
        self.config_file = self.config_dir / "config.json"
        self.state_file = self.app_root / "state.json"
        self.logs_dir = self.app_root / "logs"
        
        # Source paths
        self.source_root = Path(__file__).resolve().parent.parent.parent
        
        self.app_root.mkdir()
        self.config_dir.mkdir()
        
        # Copy source files to isolated app root
        for f in self.source_root.glob("*.py"):
            shutil.copy(f, self.app_root)
            
        # Setup Bare Remote
        self.remote_repo_path.mkdir()
        subprocess.run(["git", "init", "--bare"], cwd=str(self.remote_repo_path), check=True, capture_output=True)
        
        # Initial clone to create first commit
        init_clone_path = self.base_path / "init_clone"
        subprocess.run(["git", "clone", str(self.remote_repo_path), str(init_clone_path)], check=True, capture_output=True)
        
        # Create README
        (init_clone_path / "README.md").write_text("# Test Repo")
        subprocess.run(["git", "add", "README.md"], cwd=str(init_clone_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(init_clone_path), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(init_clone_path), check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(init_clone_path), check=True, capture_output=True)
        subprocess.run(["git", "push", "-u", "origin", "HEAD:main"], cwd=str(init_clone_path), check=True, capture_output=True)
        
        # Verify remote format
        self.remote_url = self.remote_repo_path.as_uri() # e.g., file:///...

    def tearDown(self):
        # On windows, temp directory deletion can sometimes fail with git permissions. We can just ignore errors.
        try:
            self.temp_dir.cleanup()
        except:
            pass

    def write_config(self, jobs, max_commits):
        config_data = {
            "settings": {
                "max_commits_per_run": max_commits
            },
            "repositories": [
                {
                    "name": "integration_test_repo",
                    "url": self.remote_url,
                    "branch": "main",
                    "commits": jobs
                }
            ]
        }
        self.config_file.write_text(json.dumps(config_data))

    def run_app(self, *args):
        # We run the copied main.py in app_root, which guarantees APP_ROOT is isolated.
        cmd = [sys.executable, "main.py"] + list(args)
        # Pass a minimal env with system paths
        env = os.environ.copy()
        result = subprocess.run(cmd, cwd=str(self.app_root), capture_output=True, text=True, env=env)
        return result

    def get_state(self):
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return None

    def get_remote_commits(self):
        # List commits on remote main branch
        result = subprocess.run(["git", "log", "--oneline", "main"], cwd=str(self.remote_repo_path), capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip().split("\n")
        return []

    def get_cloned_working_tree(self):
        return self.app_root / "repos" / "integration_test_repo"

    def test_successful_end_to_end_execution(self):
        jobs = [
            {"file_path": "logs/test1.md", "operation": "append", "content": "data", "message_template": "job 1"},
            {"file_path": "logs/test2.md", "operation": "append", "content": "data", "message_template": "job 2"},
            {"file_path": "logs/test3.md", "operation": "append", "content": "data", "message_template": "job 3"}
        ]
        self.write_config(jobs, max_commits=2)
        
        # Run 1: Should complete 2 jobs
        res = self.run_app()
        self.assertEqual(res.returncode, 0, f"stdout: {res.stdout}\nstderr: {res.stderr}")
        self.assertIn("GOAL_REACHED", res.stdout)
        
        state = self.get_state()
        self.assertIsNotNone(state)
        current_batch = state["batches"][state["current_batch_id"]]
        completed_jobs = [f"{j['repository']}:{j['branch']}:{j['job_index']}" for j in current_batch["jobs"] if j["status"] == "success"]
        self.assertEqual(len(completed_jobs), 2)
        self.assertIn("integration_test_repo:main:0", completed_jobs)
        self.assertIn("integration_test_repo:main:1", completed_jobs)
        
        commits = self.get_remote_commits()
        # Initial commit + 2 autoevergreen commits
        self.assertEqual(len(commits), 3)
        self.assertIn("job 2", commits[0])
        self.assertIn("job 1", commits[1])
        self.assertIn("Initial commit", commits[2])
        
        # Working tree must be clean
        wt = self.get_cloned_working_tree()
        status = subprocess.run(["git", "status", "--porcelain"], cwd=str(wt), capture_output=True, text=True)
        self.assertEqual(status.stdout.strip(), "")
        
        # Run 2: Should complete 1 job
        res2 = self.run_app()
        self.assertEqual(res2.returncode, 0, f"stdout: {res2.stdout}\nstderr: {res2.stderr}")
        self.assertIn("BATCH_COMPLETED", res2.stdout)
        
        state = self.get_state()
        current_batch = state["batches"][state["current_batch_id"]]
        completed_jobs = [f"{j['repository']}:{j['branch']}:{j['job_index']}" for j in current_batch["jobs"] if j["status"] == "success"]
        self.assertEqual(len(completed_jobs), 3)
        self.assertIn("integration_test_repo:main:2", completed_jobs)
        
        commits2 = self.get_remote_commits()
        self.assertEqual(len(commits2), 4)
        self.assertIn("job 3", commits2[0])
        
        # Run 3: Should report NO_WORK
        res3 = self.run_app()
        self.assertEqual(res3.returncode, 0)
        self.assertIn("NO_WORK", res3.stdout)
        
        commits3 = self.get_remote_commits()
        self.assertEqual(len(commits3), 4)

    def test_failed_job_recovery(self):
        jobs = [
            {"file_path": "logs/test1.md", "operation": "append", "content": "data", "message_template": "job 1"},
            {"file_path": "../../logs/fail/dir/test.md", "operation": "append", "content": "data", "message_template": "job 2"}, # Fails
            {"file_path": "logs/test3.md", "operation": "append", "content": "data", "message_template": "job 3"}
        ]
        self.write_config(jobs, max_commits=3)
        
        res = self.run_app()
        self.assertEqual(res.returncode, 0, f"stdout: {res.stdout}\nstderr: {res.stderr}")
        
        # Should process 1, fail on 2, and skip 3 for this repo.
        state = self.get_state()
        current_batch = state["batches"][state["current_batch_id"]]
        completed_jobs = [f"{j['repository']}:{j['branch']}:{j['job_index']}" for j in current_batch["jobs"] if j["status"] == "success"]
        self.assertEqual(len(completed_jobs), 1)
        self.assertIn("integration_test_repo:main:0", completed_jobs)
        
        # Now fix the bad job config
        jobs[1]["file_path"] = "logs/test2_fixed.md"
        self.write_config(jobs, max_commits=3)
        
        # Run again to recover
        res2 = self.run_app()
        self.assertEqual(res2.returncode, 0, f"stdout: {res2.stdout}\nstderr: {res2.stderr}")
        
        state2 = self.get_state()
        current_batch2 = state2["batches"][state2["current_batch_id"]]
        completed_jobs2 = [f"{j['repository']}:{j['branch']}:{j['job_index']}" for j in current_batch2["jobs"] if j["status"] == "success"]
        
        # Now it should have processed 1 (already done), 2 (fixed), and 3.
        self.assertEqual(len(completed_jobs2), 3)
        self.assertIn("integration_test_repo:main:0", completed_jobs2)
        self.assertIn("integration_test_repo:main:1", completed_jobs2)
        self.assertIn("integration_test_repo:main:2", completed_jobs2)
        
        commits = self.get_remote_commits()
        self.assertEqual(len(commits), 4) # initial + job 1 + job 2 + job 3

    def test_dry_run(self):
        jobs = [
            {"file_path": "logs/test1.md", "operation": "append", "content": "data", "message_template": "job 1"},
        ]
        self.write_config(jobs, max_commits=1)
        
        res = self.run_app("--dry-run")
        self.assertEqual(res.returncode, 0, f"stdout: {res.stdout}\nstderr: {res.stderr}")
        
        self.assertIn("DRY RUN", res.stdout)
        self.assertIsNone(self.get_state())
        
        commits = self.get_remote_commits()
        self.assertEqual(len(commits), 1) # Only initial commit
        
    def test_packaged_executable(self):
        dist_dir = self.source_root / "dist" / "AutoEverGreen"
        exe_path = dist_dir / "AutoEverGreen.exe"
        if not exe_path.exists():
            self.skipTest("Packaged executable not found, skipping integration test.")
            
        # Copy the entire dist directory contents into app_root to act as the app root
        for item in dist_dir.iterdir():
            if item.is_dir():
                shutil.copytree(item, self.app_root / item.name, dirs_exist_ok=True)
            else:
                shutil.copy2(item, self.app_root)
        
        target_exe = self.app_root / "AutoEverGreen.exe"
        
        jobs = [
            {"file_path": "logs/test1.md", "operation": "append", "content": "data", "message_template": "job 1"}
        ]
        self.write_config(jobs, max_commits=1)
        
        # Run executable
        cmd = [str(target_exe)]
        env = os.environ.copy()
        res = subprocess.run(cmd, cwd=str(self.app_root), capture_output=True, text=True, env=env)
        
        self.assertEqual(res.returncode, 0, f"stdout: {res.stdout}\nstderr: {res.stderr}")
        self.assertIn("GOAL_REACHED", res.stdout)
        
        state = self.get_state()
        self.assertIsNotNone(state)
        current_batch = state["batches"][state["current_batch_id"]]
        completed_jobs = [f"{j['repository']}:{j['branch']}:{j['job_index']}" for j in current_batch["jobs"] if j["status"] == "success"]
        self.assertEqual(len(completed_jobs), 1)
        
        commits = self.get_remote_commits()
        self.assertEqual(len(commits), 2)

