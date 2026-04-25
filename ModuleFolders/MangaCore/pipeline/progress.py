from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(slots=True)
class PipelineJob:
    job_id: str
    stage: str
    status: str
    progress: int = 0
    message: str = ""
    page_id: str = ""
    project_id: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        return payload


class JobRegistry:
    _lock = threading.Lock()
    _jobs: dict[str, PipelineJob] = {}
    _counter: int = 1

    @classmethod
    def create(cls, *, stage: str, status: str, project_id: str = "", page_id: str = "", message: str = "", progress: int = 0) -> PipelineJob:
        with cls._lock:
            job_id = f"mjob_{cls._counter:05d}"
            cls._counter += 1
            job = PipelineJob(
                job_id=job_id,
                stage=stage,
                status=status,
                project_id=project_id,
                page_id=page_id,
                message=message,
                progress=progress,
            )
            cls._jobs[job_id] = job
            return job

    @classmethod
    def get(cls, job_id: str) -> PipelineJob | None:
        with cls._lock:
            return cls._jobs.get(job_id)

    @classmethod
    def update(cls, job_id: str, **changes) -> PipelineJob | None:
        with cls._lock:
            job = cls._jobs.get(job_id)
            if job is None:
                return None
            for key, value in changes.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            return job
