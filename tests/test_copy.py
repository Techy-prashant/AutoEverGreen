import unittest
import tempfile
import os
from pathlib import Path
from executor import FileOperator, DryRunFileOperator
from paths import get_app_root
from logger import setup_logger

class TestCopyOperation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self.temp_dir.name) / "repo"
        self.repo_path.mkdir()
        
        # We need a source file inside the app root for copy to work
        # To test safely, we will create a dummy file in a non-protected dir of app root
        self.app_root = get_app_root()
        self.dummy_src_rel = "tests/dummy_test_src.txt"
        self.dummy_src_abs = self.app_root / self.dummy_src_rel
        self.dummy_src_abs.parent.mkdir(exist_ok=True, parents=True)
        with open(self.dummy_src_abs, 'wb') as f:
            f.write(b"binary data \x00\x01\x02 test")
            
        self.operator = FileOperator()

    def tearDown(self):
        if self.dummy_src_abs.exists():
            self.dummy_src_abs.unlink()
        self.temp_dir.cleanup()

    def test_successful_copy(self):
        self.operator.apply(self.repo_path, "copied.txt", "copy", source_path=self.dummy_src_rel)
        target = self.repo_path / "copied.txt"
        self.assertTrue(target.exists())
        with open(target, 'rb') as f:
            self.assertEqual(f.read(), b"binary data \x00\x01\x02 test")

    def test_missing_source(self):
        with self.assertRaises(FileNotFoundError):
            self.operator.apply(self.repo_path, "dest.txt", "copy", source_path="tests/does_not_exist.txt")

    def test_source_is_directory(self):
        with self.assertRaises(IsADirectoryError):
            self.operator.apply(self.repo_path, "dest.txt", "copy", source_path="tests")

    def test_source_outside_project(self):
        # Escaping
        with self.assertRaises(ValueError):
            self.operator.apply(self.repo_path, "dest.txt", "copy", source_path="../outside.txt")

    def test_destination_outside_clone(self):
        with self.assertRaises(ValueError):
            self.operator.apply(self.repo_path, "../outside.txt", "copy", source_path=self.dummy_src_rel)

    def test_protected_source_paths_actual(self):
        # Create a dummy protected file
        protected_file = self.app_root / "logs" / "dummy_log.txt"
        protected_file.parent.mkdir(exist_ok=True)
        protected_file.touch()
        try:
            with self.assertRaisesRegex(ValueError, "protected directory"):
                self.operator.apply(self.repo_path, "dest.txt", "copy", source_path="logs/dummy_log.txt")
        finally:
            protected_file.unlink()

        # Create dummy state.json
        state_file = self.app_root / "state.json"
        created_state = False
        if not state_file.exists():
            state_file.touch()
            created_state = True
        try:
            with self.assertRaisesRegex(ValueError, "protected file type"):
                self.operator.apply(self.repo_path, "dest.txt", "copy", source_path="state.json")
        finally:
            if created_state:
                state_file.unlink()

    def test_dry_run_does_not_copy(self):
        logger = setup_logger("test_dry_run")
        dry_operator = DryRunFileOperator(logger)
        
        dry_operator.apply(self.repo_path, "copied.txt", "copy", source_path=self.dummy_src_rel)
        target = self.repo_path / "copied.txt"
        self.assertFalse(target.exists())
        
    def test_append_create_update_still_work(self):
        self.operator.apply(self.repo_path, "create.txt", "create", content="hello")
        with open(self.repo_path / "create.txt", "r") as f:
            self.assertEqual(f.read(), "hello")
            
        self.operator.apply(self.repo_path, "create.txt", "append", content=" world")
        with open(self.repo_path / "create.txt", "r") as f:
            self.assertEqual(f.read(), "hello world")
            
        self.operator.apply(self.repo_path, "create.txt", "update", content="new")
        with open(self.repo_path / "create.txt", "r") as f:
            self.assertEqual(f.read(), "new")

if __name__ == '__main__':
    unittest.main()
