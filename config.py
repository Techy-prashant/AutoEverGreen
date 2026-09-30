import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from paths import resolve_path

@dataclass
class CommitConfig:
    file_path: str
    operation: str
    message_template: str
    content: Optional[str] = None
    source_path: Optional[str] = None
    id: Optional[str] = None
    enabled: bool = True
    phase: Optional[str] = None

@dataclass
class RepositoryConfig:
    name: str
    url: str
    commits: List[CommitConfig]
    branch: str = "main"

@dataclass
class SettingsConfig:
    max_commits_per_run: int = 1
    dry_run: bool = False

@dataclass
class AppConfig:
    repositories: List[RepositoryConfig]
    settings: SettingsConfig

class ConfigManager:
    """Manages the application configuration."""
    def __init__(self, config_path: str = "config/publish_config.json"):
        self.config_path = resolve_path(config_path)
        self.config: Optional[AppConfig] = None
        self.raw_data: Dict[str, Any] = {}

    def load_config(self) -> None:
        """Loads and parses the configuration from JSON."""
        from validator import ConfigValidator
        
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found at {self.config_path}")
            
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.raw_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed JSON in configuration file: {e}")
            
        self.config = ConfigValidator.validate_and_parse(self.raw_data)
