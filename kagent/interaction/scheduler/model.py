from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from datetime import datetime
import uuid
import json
from pathlib import Path


TRIGGER_TYPES = ["delay", "once", "cron"]
TASK_STATUS = ["pending", "completed", "cancelled", "failed"]


@dataclass
class ScheduledTask:
    task_id: str
    instruction: str
    trigger_type: str
    trigger_spec: str
    session_id: str
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    trigger_time: Optional[str] = None
    last_run: Optional[str] = None
    run_count: int = 0
    error: Optional[str] = None
    target_id: Optional[str] = None  # For channel pushback (e.g., user's open_id)
    target_id_type: Optional[str] = "open_id"  # open_id, user_id, chat_id

    def __post_init__(self):
        if self.trigger_type not in TRIGGER_TYPES:
            raise ValueError(
                f"Invalid trigger_type: {self.trigger_type}. Must be one of {TRIGGER_TYPES}"
            )
        if self.status not in TASK_STATUS:
            raise ValueError(
                f"Invalid status: {self.status}. Must be one of {TASK_STATUS}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledTask":
        return cls(**data)

    def mark_completed(self):
        self.status = "completed"
        self.last_run = datetime.now().isoformat()
        self.run_count += 1

    def mark_cancelled(self):
        self.status = "cancelled"

    def mark_failed(self, error: str):
        self.status = "failed"
        self.error = error
        self.last_run = datetime.now().isoformat()

    @staticmethod
    def generate_task_id() -> str:
        return f"task_{uuid.uuid4().hex[:12]}"
