import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

from paths import get_app_root, resolve_path

class TestPaths(unittest.TestCase):
    def test_get_app_root_normal(self):
        with patch('paths.sys') as mock_sys:
            mock_sys.frozen = False
            root = get_app_root()
            self.assertTrue(root.is_absolute())
            self.assertEqual(root.name, "AutoEverGreen")

    def test_get_app_root_frozen(self):
        with patch('paths.sys') as mock_sys:
            mock_sys.frozen = True
            mock_sys.executable = str(Path("C:/dummy/AutoEverGreen.exe").resolve())
            root = get_app_root()
            self.assertTrue(root.is_absolute())
            self.assertEqual(str(root), str(Path("C:/dummy").resolve()))

    def test_resolve_path_absolute(self):
        abs_path = str(Path("C:/test/file.txt").resolve())
        resolved = resolve_path(abs_path)
        self.assertEqual(str(resolved), abs_path)

    def test_resolve_path_relative(self):
        with patch('paths.get_app_root', return_value=Path("C:/app_root").resolve()):
            resolved = resolve_path("logs/autoevergreen.log")
            self.assertTrue(resolved.is_absolute())
            self.assertEqual(str(resolved), str(Path("C:/app_root/logs/autoevergreen.log").resolve()))

if __name__ == "__main__":
    unittest.main()
