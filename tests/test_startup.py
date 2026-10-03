import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from startup import enable_startup, disable_startup, is_startup_enabled

class TestStartup(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_get_startup_folder = patch('startup.get_startup_folder').start()
        self.mock_get_startup_folder.return_value = Path(self.temp_dir.name)
        
        self.mock_subprocess = patch('startup.subprocess.run').start()

    def tearDown(self):
        patch.stopall()
        self.temp_dir.cleanup()

    def test_enable_startup(self):
        self.assertFalse(is_startup_enabled())
        
        # We need to simulate the file creation because subprocess is mocked
        def mock_run(*args, **kwargs):
            (Path(self.temp_dir.name) / "AutoEverGreen.lnk").touch()
            
        self.mock_subprocess.side_effect = mock_run
        
        result = enable_startup()
        self.assertTrue(result)
        self.assertTrue(is_startup_enabled())
        self.mock_subprocess.assert_called_once()

    def test_enable_startup_twice_idempotent(self):
        def mock_run(*args, **kwargs):
            (Path(self.temp_dir.name) / "AutoEverGreen.lnk").touch()
            
        self.mock_subprocess.side_effect = mock_run
        
        enable_startup()
        self.mock_subprocess.reset_mock()
        
        # Second time should just return True and do nothing
        result = enable_startup()
        self.assertTrue(result)
        self.mock_subprocess.assert_not_called()

    def test_disable_startup(self):
        def mock_run(*args, **kwargs):
            (Path(self.temp_dir.name) / "AutoEverGreen.lnk").touch()
        self.mock_subprocess.side_effect = mock_run
        enable_startup()
        self.assertTrue(is_startup_enabled())
        
        result = disable_startup()
        self.assertTrue(result)
        self.assertFalse(is_startup_enabled())

    def test_disable_startup_already_disabled(self):
        self.assertFalse(is_startup_enabled())
        result = disable_startup()
        self.assertTrue(result)

if __name__ == "__main__":
    unittest.main()
