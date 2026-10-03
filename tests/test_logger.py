import unittest
import json
import logging
import tempfile
import sys
from pathlib import Path
from logger import setup_logger, ScrubbingFormatter, JsonFormatter

class TestLogger(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = self.temp_dir.name
        
        # We need a new logger per test so they don't share handlers
        self.logger_name = f"TestLogger_{id(self)}"
        self.logger = setup_logger(self.logger_name, log_dir=self.log_dir)

    def tearDown(self):
        # Close file handlers to release Windows locks
        for handler in self.logger.handlers:
            handler.close()
        self.temp_dir.cleanup()

    def test_scrubbing_formatter_removes_tokens(self):
        formatter = ScrubbingFormatter('%(message)s')
        
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Cloning https://ghp_token123@github.com/user/repo.git", args=(), exc_info=None
        )
        self.assertEqual(formatter.format(record), "Cloning https://***@github.com/user/repo.git")
        
        record2 = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Push to http://user:password@gitlab.com/test", args=(), exc_info=None
        )
        self.assertEqual(formatter.format(record2), "Push to http://***@gitlab.com/test")

    def test_json_formatter_structure_and_scrubbing(self):
        formatter = JsonFormatter()
        
        record = logging.LogRecord(
            name="test_json", level=logging.ERROR, pathname="", lineno=0,
            msg="Failed at https://secret@github.com", args=(), exc_info=None
        )
        
        output = formatter.format(record)
        data = json.loads(output)
        
        self.assertEqual(data["level"], "ERROR")
        self.assertEqual(data["logger"], "test_json")
        self.assertEqual(data["message"], "Failed at https://***@github.com")
        self.assertIn("timestamp", data)

    def test_logger_files_created_and_levels(self):
        self.logger.info("Test info message")
        self.logger.warning("Test warning message")
        self.logger.error("Test error message")
        
        # Verify text log exists and was written to
        text_log = Path(self.log_dir) / "autoevergreen.log"
        self.assertTrue(text_log.exists())
        with open(text_log, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("INFO - Test info message", content)
            self.assertIn("WARNING - Test warning message", content)
            self.assertIn("ERROR - Test error message", content)
            
        # Verify json log exists and was written to
        json_log = Path(self.log_dir) / "execution.json"
        self.assertTrue(json_log.exists())
        with open(json_log, "r", encoding="utf-8") as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 3)
            
            # Check JSON parsing and levels
            data_info = json.loads(lines[0])
            self.assertEqual(data_info["level"], "INFO")
            self.assertEqual(data_info["message"], "Test info message")
            
            data_warn = json.loads(lines[1])
            self.assertEqual(data_warn["level"], "WARNING")
            self.assertEqual(data_warn["message"], "Test warning message")
            
            data_err = json.loads(lines[2])
            self.assertEqual(data_err["level"], "ERROR")
            self.assertEqual(data_err["message"], "Test error message")

if __name__ == '__main__':
    unittest.main()
