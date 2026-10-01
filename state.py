import json
import uuid
import tempfile
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import datetime

@dataclass
class JobState:
    batch_id: str
    repository: str
    branch: str
    job_index: int
    commit_sha: Optional[str]
    timestamp: str
    status: str
    error: Optional[str] = None

@dataclass
class BatchState:
    batch_id: str
    is_completed: bool
    jobs: List[JobState]

class StateTracker:
    def __init__(self, state_file: Path):
        self.state_file = Path(state_file)
        self.batch_states: Dict[str, BatchState] = {}
        self.current_batch_id: Optional[str] = None
        self._load()

    def _load(self) -> None:
        if self.state_file.exists():
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.current_batch_id = data.get("current_batch_id")
                for b_id, b_data in data.get("batches", {}).items():
                    jobs = [JobState(**j) for j in b_data.get("jobs", [])]
                    self.batch_states[b_id] = BatchState(
                        batch_id=b_id,
                        is_completed=b_data.get("is_completed", False),
                        jobs=jobs
                    )

    def start_new_batch(self) -> str:
        new_id = str(uuid.uuid4())
        self.current_batch_id = new_id
        self.batch_states[new_id] = BatchState(batch_id=new_id, is_completed=False, jobs=[])
        self.save()
        return new_id

    def _atomic_write(self, data: dict) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=self.state_file.parent, prefix="state_tmp_", suffix=".json")
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self.state_file)
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise e

    def save(self) -> None:
        data = {
            "current_batch_id": self.current_batch_id,
            "batches": {
                b_id: {
                    "is_completed": b.is_completed,
                    "jobs": [asdict(j) for j in b.jobs]
                }
                for b_id, b in self.batch_states.items()
            }
        }
        self._atomic_write(data)

    def mark_batch_completed(self) -> None:
        if self.current_batch_id and self.current_batch_id in self.batch_states:
            self.batch_states[self.current_batch_id].is_completed = True
            self.save()

    def record_job(self, repository: str, branch: str, job_index: int, status: str, commit_sha: Optional[str] = None, error: Optional[str] = None) -> None:
        if not self.current_batch_id:
            self.start_new_batch()
            
        job = JobState(
            batch_id=self.current_batch_id,
            repository=repository,
            branch=branch,
            job_index=job_index,
            commit_sha=commit_sha,
            timestamp=datetime.datetime.now().isoformat(),
            status=status,
            error=error
        )
        self.batch_states[self.current_batch_id].jobs.append(job)
        self.save()

    def is_job_completed(self, repository: str, branch: str, job_index: int) -> bool:
        if not self.current_batch_id:
            return False
            
        batch = self.batch_states.get(self.current_batch_id)
        if not batch:
            return False
            
        for job in batch.jobs:
            if job.repository == repository and job.branch == branch and job.job_index == job_index and job.status == "success":
                return True
        return False
        
    def reset(self) -> None:
        self.current_batch_id = None
        self.batch_states = {}
        if self.state_file.exists():
            self.state_file.unlink()
