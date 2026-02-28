import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from kagent.interaction.scheduler.model import ScheduledTask


class TaskStore:
    DEFAULT_DIR = ".agent/schedule"
    TASK_FILE = "tasks.json"

    def __init__(self, store_dir: Optional[str] = None):
        self.store_dir = Path(store_dir or self.DEFAULT_DIR)
        self.task_file = self.store_dir / self.TASK_FILE
        self._ensure_dir()

    def _ensure_dir(self):
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def _load_tasks(self) -> List[Dict[str, Any]]:
        if not self.task_file.exists():
            return []
        try:
            with open(self.task_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load tasks: {e}")
            return []

    def _save_tasks(self, tasks: List[Dict[str, Any]]):
        try:
            with open(self.task_file, "w", encoding="utf-8") as f:
                json.dump(tasks, f, ensure_ascii=False, indent=2)
        except IOError as e:
            raise Exception(f"Failed to save tasks: {e}")

    def save(self, task: ScheduledTask) -> ScheduledTask:
        tasks = self._load_tasks()
        tasks.append(task.to_dict())
        self._save_tasks(tasks)
        return task

    def update(self, task: ScheduledTask) -> ScheduledTask:
        tasks = self._load_tasks()
        for i, t in enumerate(tasks):
            if t.get("task_id") == task.task_id:
                tasks[i] = task.to_dict()
                self._save_tasks(tasks)
                return task
        raise Exception(f"Task not found: {task.task_id}")

    def delete(self, task_id: str) -> bool:
        tasks = self._load_tasks()
        original_len = len(tasks)
        tasks = [t for t in tasks if t.get("task_id") != task_id]
        if len(tasks) < original_len:
            self._save_tasks(tasks)
            return True
        return False

    def get(self, task_id: str) -> Optional[ScheduledTask]:
        tasks = self._load_tasks()
        for t in tasks:
            if t.get("task_id") == task_id:
                return ScheduledTask.from_dict(t)
        return None

    def get_all(self) -> List[ScheduledTask]:
        tasks = self._load_tasks()
        return [ScheduledTask.from_dict(t) for t in tasks]

    def get_by_status(self, status: str) -> List[ScheduledTask]:
        tasks = self._load_tasks()
        return [ScheduledTask.from_dict(t) for t in tasks if t.get("status") == status]

    def get_pending(self) -> List[ScheduledTask]:
        return self.get_by_status("pending")
