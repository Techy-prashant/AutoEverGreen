import logging
import sys
import json
import re
from pathlib import Path
from paths import resolve_path

# Scrubber to catch tokens in URLs (e.g. https://token@github.com or https://user:pass@github.com)
URL_CREDENTIAL_PATTERN = re.compile(r'(https?://)[^@\s]+(:[^@\s]+)?@')

class ScrubbingFormatter(logging.Formatter):
    """Formats logs for human reading while scrubbing secrets."""
    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return URL_CREDENTIAL_PATTERN.sub(r'\1***@', original)

class JsonFormatter(logging.Formatter):
    """Formats logs as structured JSON while scrubbing secrets."""
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        message = URL_CREDENTIAL_PATTERN.sub(r'\1***@', message)
        
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_record)

def setup_logger(name: str = "AutoEverGreen", log_dir: str = "logs") -> logging.Logger:
    """
    Sets up and configures the logger for the application.
    Supports console, plain text log, and structured JSON log.
    """
    logger = logging.getLogger(name)
    
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.INFO)
    logger.propagate = False
    
    resolved_log_dir = resolve_path(log_dir)
    resolved_log_dir.mkdir(exist_ok=True, parents=True)
    
    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ScrubbingFormatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    # 2. Text File Handler
    file_handler = logging.FileHandler(resolved_log_dir / "autoevergreen.log", encoding='utf-8')
    file_handler.setFormatter(ScrubbingFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    # 3. JSON File Handler
    json_handler = logging.FileHandler(resolved_log_dir / "execution.json", encoding='utf-8')
    json_handler.setFormatter(JsonFormatter())
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(json_handler)
    
    return logger
