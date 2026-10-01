import re
from typing import Dict, Any, List
from config import AppConfig, RepositoryConfig, CommitConfig, SettingsConfig

class ConfigValidator:
    """Validates application configuration and parses it into models."""
    
    VALID_OPERATIONS = {"append", "create", "update", "copy"}
    
    @staticmethod
    def validate_and_parse(data: Dict[str, Any]) -> AppConfig:
        if not isinstance(data, dict):
            raise ValueError("Configuration root must be a JSON object.")
            
        settings_data = data.get("settings", {})
        if not isinstance(settings_data, dict):
             raise ValueError("'settings' must be an object.")
             
        max_commits_per_run = settings_data.get("max_commits_per_run", 1)
        if type(max_commits_per_run) is not int or max_commits_per_run < 1:
            raise ValueError("'max_commits_per_run' must be a positive integer greater than zero.")
            
        dry_run = settings_data.get("dry_run", False)
        if not isinstance(dry_run, bool):
             raise ValueError("'dry_run' must be a boolean.")
             
        settings = SettingsConfig(max_commits_per_run=max_commits_per_run, dry_run=dry_run)
        
        repos_data = data.get("repositories")
        if repos_data is None:
            raise ValueError("Missing required field: 'repositories'.")
        if not isinstance(repos_data, list):
            raise ValueError("'repositories' must be a list.")
            
        repos = []
        for i, repo_data in enumerate(repos_data):
            if not isinstance(repo_data, dict):
                raise ValueError(f"Repository at index {i} must be an object.")
                
            name = repo_data.get("name")
            if not name or not isinstance(name, str):
                raise ValueError(f"Repository at index {i} is missing or has invalid 'name'.")
                
            url = repo_data.get("url")
            if not url or not isinstance(url, str):
                raise ValueError(f"Repository '{name}' is missing or has invalid 'url'.")
            if not ConfigValidator._is_valid_git_url(url):
                raise ValueError(f"Repository '{name}' has an invalid Git URL format.")
                
            branch = repo_data.get("branch", "main")
            
            commits_data = repo_data.get("commits")
            if commits_data is None:
                raise ValueError(f"Repository '{name}' is missing 'commits' list.")
            if not isinstance(commits_data, list):
                raise ValueError(f"Repository '{name}' 'commits' must be a list.")
                
            commits = []
            for j, commit_data in enumerate(commits_data):
                if not isinstance(commit_data, dict):
                    raise ValueError(f"Commit at index {j} in repo '{name}' must be an object.")
                    
                file_path = commit_data.get("file_path")
                operation = commit_data.get("operation")
                content = commit_data.get("content")
                source_path = commit_data.get("source_path")
                message_template = commit_data.get("message_template")
                job_id = commit_data.get("id")
                enabled = commit_data.get("enabled", True)
                phase = commit_data.get("phase")
                
                if not all(isinstance(x, str) for x in (file_path, operation, message_template)):
                    raise ValueError(f"Commit at index {j} in repo '{name}' has missing or non-string required fields.")
                
                if operation == "copy":
                    if not isinstance(source_path, str):
                        raise ValueError(f"Commit at index {j} in repo '{name}' is missing required 'source_path' for 'copy' operation.")
                    if content is not None:
                        raise ValueError(f"Commit at index {j} in repo '{name}' specifies 'content' which is invalid for 'copy' operation.")
                else:
                    if not isinstance(content, str):
                        raise ValueError(f"Commit at index {j} in repo '{name}' is missing required 'content' for '{operation}' operation.")
                    if source_path is not None:
                        raise ValueError(f"Commit at index {j} in repo '{name}' specifies 'source_path' which is only valid for 'copy' operation.")
                      
                if operation not in ConfigValidator.VALID_OPERATIONS:
                    raise ValueError(f"Commit at index {j} in repo '{name}' has invalid operation '{operation}'. Valid: {ConfigValidator.VALID_OPERATIONS}")
                    
                if job_id is not None and not isinstance(job_id, str):
                    raise ValueError(f"Commit at index {j} in repo '{name}' has invalid 'id'.")
                if not isinstance(enabled, bool):
                    raise ValueError(f"Commit at index {j} in repo '{name}' has invalid 'enabled'.")
                if phase is not None and not isinstance(phase, str):
                    raise ValueError(f"Commit at index {j} in repo '{name}' has invalid 'phase'.")
                    
                commits.append(CommitConfig(
                    file_path=file_path,
                    operation=operation,
                    content=content,
                    source_path=source_path,
                    message_template=message_template,
                    id=job_id,
                    enabled=enabled,
                    phase=phase
                ))
                
            repos.append(RepositoryConfig(name=name, url=url, branch=branch, commits=commits))
            
        return AppConfig(repositories=repos, settings=settings)

    @staticmethod
    def _is_valid_git_url(url: str) -> bool:
        # A simple regex for http(s):// or git@ formats
        http_pattern = re.compile(r'^https?://.*\.git$')
        ssh_pattern = re.compile(r'^git@.*:.*\.git$')
        file_pattern = re.compile(r'^file://.*')
        return bool(http_pattern.match(url) or ssh_pattern.match(url) or file_pattern.match(url))
