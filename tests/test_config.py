import json
import tempfile
import unittest
from pathlib import Path
from config import ConfigManager
from validator import ConfigValidator

class TestConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "test_config.json"
        
        self.valid_config = {
            "settings": {
                "max_commits_per_run": 2
            },
            "repositories": [
                {
                    "name": "test-repo",
                    "url": "https://github.com/user/test-repo.git",
                    "commits": [
                        {
                            "file_path": "log.txt",
                            "operation": "append",
                            "content": "log\n",
                            "message_template": "update {date}"
                        }
                    ]
                }
            ]
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_config(self, data):
        with open(self.config_path, 'w', encoding='utf-8') as f:
             json.dump(data, f)

    def test_valid_config(self):
        self.write_config(self.valid_config)
        manager = ConfigManager(str(self.config_path))
        manager.load_config()
        
        self.assertIsNotNone(manager.config)
        self.assertEqual(len(manager.config.repositories), 1)
        self.assertEqual(manager.config.settings.max_commits_per_run, 2)
        self.assertEqual(manager.config.settings.dry_run, False)

    def test_dry_run_config(self):
        config = dict(self.valid_config)
        config["settings"]["dry_run"] = True
        self.write_config(config)
        manager = ConfigManager(str(self.config_path))
        manager.load_config()
        
        self.assertEqual(manager.config.settings.dry_run, True)
        
    def test_malformed_json(self):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            f.write("{ invalid json ")
            
        manager = ConfigManager(str(self.config_path))
        with self.assertRaisesRegex(ValueError, "Malformed JSON"):
            manager.load_config()
            
    def test_missing_repositories(self):
        invalid = {"settings": {}}
        self.write_config(invalid)
        manager = ConfigManager(str(self.config_path))
        with self.assertRaisesRegex(ValueError, "Missing required field: 'repositories'"):
            manager.load_config()
            
    def test_invalid_git_url(self):
        config = dict(self.valid_config)
        config["repositories"][0]["url"] = "not_a_url"
        self.write_config(config)
        
        manager = ConfigManager(str(self.config_path))
        with self.assertRaisesRegex(ValueError, "invalid Git URL format"):
            manager.load_config()
            
    def test_invalid_operation(self):
        config = dict(self.valid_config)
        config["repositories"][0]["commits"][0]["operation"] = "delete"
        self.write_config(config)
        
        manager = ConfigManager(str(self.config_path))
        with self.assertRaisesRegex(ValueError, "invalid operation"):
            manager.load_config()

    def test_invalid_max_commits_boolean(self):
        config = dict(self.valid_config)
        config["settings"]["max_commits_per_run"] = True
        self.write_config(config)
        manager = ConfigManager(str(self.config_path))
        with self.assertRaisesRegex(ValueError, "positive integer greater than zero"):
            manager.load_config()

    def test_invalid_max_commits_zero(self):
        config = dict(self.valid_config)
        config["settings"]["max_commits_per_run"] = 0
        self.write_config(config)
        manager = ConfigManager(str(self.config_path))
        with self.assertRaisesRegex(ValueError, "positive integer greater than zero"):
            manager.load_config()

    def test_invalid_max_commits_string(self):
        config = dict(self.valid_config)
        config["settings"]["max_commits_per_run"] = "5"
        self.write_config(config)
        manager = ConfigManager(str(self.config_path))
        with self.assertRaisesRegex(ValueError, "positive integer greater than zero"):
            manager.load_config()

    def test_valid_copy_operation(self):
        config = dict(self.valid_config)
        config["repositories"][0]["commits"].append({
            "file_path": "dest.txt",
            "operation": "copy",
            "source_path": "README.md",
            "message_template": "update"
        })
        self.write_config(config)
        manager = ConfigManager(str(self.config_path))
        manager.load_config()
        self.assertEqual(manager.config.repositories[0].commits[1].operation, "copy")
        self.assertEqual(manager.config.repositories[0].commits[1].source_path, "README.md")
        self.assertIsNone(manager.config.repositories[0].commits[1].content)

    def test_copy_without_source_path(self):
        config = dict(self.valid_config)
        config["repositories"][0]["commits"].append({
            "file_path": "dest.txt",
            "operation": "copy",
            "message_template": "update"
        })
        self.write_config(config)
        manager = ConfigManager(str(self.config_path))
        with self.assertRaisesRegex(ValueError, "missing required 'source_path'"):
            manager.load_config()

    def test_copy_with_content(self):
        config = dict(self.valid_config)
        config["repositories"][0]["commits"].append({
            "file_path": "dest.txt",
            "operation": "copy",
            "source_path": "README.md",
            "content": "some content",
            "message_template": "update"
        })
        self.write_config(config)
        manager = ConfigManager(str(self.config_path))
        with self.assertRaisesRegex(ValueError, "specifies 'content' which is invalid for 'copy'"):
            manager.load_config()

    def test_append_with_source_path(self):
        config = dict(self.valid_config)
        config["repositories"][0]["commits"][0]["source_path"] = "README.md"
        self.write_config(config)
        manager = ConfigManager(str(self.config_path))
        with self.assertRaisesRegex(ValueError, "specifies 'source_path' which is only valid for 'copy'"):
            manager.load_config()

if __name__ == '__main__':
    unittest.main()
