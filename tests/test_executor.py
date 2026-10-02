import unittest
import tempfile
from unittest.mock import patch, MagicMock
from pathlib import Path
from executor import AutoEverGreenExecutor, FileOperator
from config import ConfigManager, AppConfig, RepositoryConfig, CommitConfig, SettingsConfig
from git import GitError

class TestExecutor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = str(Path(self.temp_dir.name) / "state.json")
        self.work_dir = str(Path(self.temp_dir.name) / "repos")
        Path(self.work_dir, "test_repo").mkdir(parents=True, exist_ok=True)
        
        self.config_manager = MagicMock(spec=ConfigManager)
        
        self.commit1 = CommitConfig("test.txt", "append", "data", "msg {date}")
        self.commit2 = CommitConfig("test2.txt", "append", "data2", "msg2 {date}")
        self.repo = RepositoryConfig("test_repo", "http://test", [self.commit1, self.commit2])
        self.settings = SettingsConfig(max_commits_per_run=2)
        self.app_config = AppConfig([self.repo], self.settings)
        
        self.config_manager.config = self.app_config

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch('executor.GitManager')
    @patch('executor.FileOperator.apply')
    def test_successful_execution(self, mock_file_op, MockGitManager):
        mock_git = MockGitManager.return_value
        mock_git._run.side_effect = lambda args: "M test.txt" if "status" in args else "new_head"
        mock_git.rev_parse.side_effect = ["old_head", "new_head", "old_head2", "new_head2"]
        
        executor = AutoEverGreenExecutor(self.config_manager, work_dir=self.work_dir, state_file=self.state_file)
        result = executor.run()
        
        self.assertTrue(result.repo_results[0].success)
        self.assertEqual(len(result.repo_results[0].jobs), 2)
        self.assertTrue(result.repo_results[0].jobs[0].success)
        mock_git.push.assert_called_once()
        self.assertEqual(mock_git.commit.call_count, 2)
        
        # Verify state is saved
        tracker = executor.state_tracker
        self.assertTrue(tracker.batch_states[tracker.current_batch_id].is_completed)
        self.assertTrue(tracker.is_job_completed("test_repo", "main", 0))

    @patch('executor.GitManager')
    @patch('executor.FileOperator.apply')
    def test_failed_file_operation(self, mock_file_op, MockGitManager):
        mock_file_op.side_effect = IOError("File error")
        
        executor = AutoEverGreenExecutor(self.config_manager, work_dir=self.work_dir, state_file=self.state_file)
        result = executor.run()
        
        self.assertFalse(result.repo_results[0].success)
        self.assertFalse(result.repo_results[0].jobs[0].success)
        self.assertEqual(result.repo_results[0].jobs[0].error, "File error")
        
        # Ensure failure is recorded in state
        tracker = executor.state_tracker
        self.assertFalse(tracker.is_job_completed("test_repo", "main", 0))
        self.assertEqual(tracker.batch_states[tracker.current_batch_id].jobs[0].status, "error")

    @patch('executor.GitManager')
    @patch('executor.FileOperator.apply')
    def test_interrupted_execution_and_recovery(self, mock_file_op, MockGitManager):
        mock_git = MockGitManager.return_value
        mock_git._run.side_effect = lambda args: "M test.txt" if "status" in args else "new_head"
        
        # First commit works, second throws error simulating interruption
        mock_git.rev_parse.side_effect = ["old", "new1", GitError("Network interrupt")]
        
        executor = AutoEverGreenExecutor(self.config_manager, work_dir=self.work_dir, state_file=self.state_file)
        result = executor.run()
        
        self.assertFalse(result.repo_results[0].success)
        self.assertTrue(result.repo_results[0].jobs[0].success)
        self.assertFalse(result.repo_results[0].jobs[1].success)
        
        tracker = executor.state_tracker
        batch_id_1 = tracker.current_batch_id
        
        # RECOVERY: Create new executor with SAME state file. 
        # It should skip job 0 and only do job 1.
        mock_git.rev_parse.side_effect = ["old2", "new2"] # Succeed on job 1 now
        
        executor2 = AutoEverGreenExecutor(self.config_manager, work_dir=self.work_dir, state_file=self.state_file)
        result2 = executor2.run()
        
        self.assertTrue(result2.repo_results[0].success)
        # Should only have processed the remaining job
        self.assertEqual(len(result2.repo_results[0].jobs), 1)
        self.assertEqual(result2.repo_results[0].jobs[0].commit_id, "test_repo:main:1")
        self.assertTrue(result2.repo_results[0].jobs[0].success)
        
        tracker2 = executor2.state_tracker
        self.assertEqual(tracker2.current_batch_id, batch_id_1) # Batch is resumed
        self.assertTrue(tracker2.batch_states[batch_id_1].is_completed)

    def test_dry_run_mode(self):
        executor = AutoEverGreenExecutor(self.config_manager, work_dir=self.work_dir, dry_run=True, state_file=self.state_file)
        result = executor.run()
        
        # Validation checks
        self.assertTrue(result.repo_results[0].success)
        self.assertTrue(result.repo_results[0].jobs[0].success)
        self.assertTrue(result.repo_results[0].jobs[0].dry_run)
        
        # Verify ZERO write operations happened physically
        test_file = Path(self.work_dir) / "test_repo" / "test.txt"
        self.assertFalse(test_file.exists())
        
        # Verify state was not updated physically
        self.assertFalse(Path(self.state_file).exists())

    @patch('executor.GitManager')
    @patch('executor.FileOperator.apply')
    def test_execution_goal_1(self, mock_file_op, MockGitManager):
        mock_git = MockGitManager.return_value
        mock_git._run.side_effect = lambda args: "M test.txt" if "status" in args else "new_head"
        mock_git.rev_parse.side_effect = ["old_head", "new_head", "old_head2", "new_head2"]
        
        self.app_config.settings.max_commits_per_run = 1
        
        executor = AutoEverGreenExecutor(self.config_manager, work_dir=self.work_dir, state_file=self.state_file)
        result = executor.run()
        
        self.assertTrue(result.repo_results[0].success)
        self.assertEqual(len(result.repo_results[0].jobs), 1)
        self.assertEqual(mock_git.commit.call_count, 1)

    @patch('executor.GitManager')
    @patch('executor.FileOperator.apply')
    def test_execution_goal_failed_job_not_counted(self, mock_file_op, MockGitManager):
        mock_git = MockGitManager.return_value
        mock_git._run.side_effect = lambda args: "M test.txt" if "status" in args else "new_head"
        
        # First commit fails (HEAD did not move)
        mock_git.rev_parse.side_effect = ["old_head", "old_head", "old_head", "new_head"]
        
        self.app_config.settings.max_commits_per_run = 1
        
        executor = AutoEverGreenExecutor(self.config_manager, work_dir=self.work_dir, state_file=self.state_file)
        result = executor.run()
        
        # Job 0 failed, but does it process Job 1?
        # In our current code, a failed job stops processing the rest of the repository.
        # "if not job_res.success: break"
        # So it processes 1 job which fails, and then breaks.
        self.assertFalse(result.repo_results[0].success)
        self.assertEqual(len(result.repo_results[0].jobs), 1)
        self.assertFalse(result.repo_results[0].jobs[0].success)

    @patch('executor.GitManager')
    @patch('executor.FileOperator.apply')
    def test_execution_goal_cross_repo(self, mock_file_op, MockGitManager):
        # Create a second repo
        commit3 = CommitConfig("test3.txt", "append", "data", "msg3")
        commit4 = CommitConfig("test4.txt", "append", "data", "msg4")
        repo2 = RepositoryConfig("test_repo2", "http://test2", [commit3, commit4])
        self.app_config.repositories.append(repo2)
        
        self.app_config.settings.max_commits_per_run = 3
        
        mock_git = MockGitManager.return_value
        mock_git._run.side_effect = lambda args: "M test.txt" if "status" in args else "new_head"
        
        # 3 commits will be made
        mock_git.rev_parse.side_effect = [
            "old", "new1", # repo1 job0
            "new1", "new2", # repo1 job1
            "old", "new3"  # repo2 job0
        ]
        
        executor = AutoEverGreenExecutor(self.config_manager, work_dir=self.work_dir, state_file=self.state_file)
        result = executor.run()
        
        self.assertTrue(result.repo_results[0].success)
        self.assertEqual(len(result.repo_results[0].jobs), 2)
        
        self.assertTrue(result.repo_results[1].success)
        self.assertEqual(len(result.repo_results[1].jobs), 1)
        
        self.assertEqual(mock_git.commit.call_count, 3)

if __name__ == '__main__':
    unittest.main()
