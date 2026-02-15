"""TodoList tool - Manage task lists for tracking progress."""

import json
import os
from datetime import datetime
from typing import Optional, List
from pathlib import Path
from kagent.core.tool import tool


TODO_DIR = Path(".agent/todos")


def _get_todo_file(session_id: str) -> Path:
    """Get the todo file path for a session."""
    TODO_DIR.mkdir(parents=True, exist_ok=True)
    return TODO_DIR / f"{session_id}.json"


def _load_todos(session_id: str) -> List[dict]:
    """Load todos from file."""
    todo_file = _get_todo_file(session_id)
    if not todo_file.exists():
        return []
    try:
        with open(todo_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_todos(session_id: str, todos: List[dict]) -> None:
    """Save todos to file."""
    todo_file = _get_todo_file(session_id)
    with open(todo_file, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)


def _format_todo(todo: dict, index: int) -> str:
    """Format a single todo item for display."""
    status_icon = "✅" if todo["status"] == "completed" else "⬜"
    priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(todo.get("priority", "medium"), "🟡")
    return f"{index + 1}. {status_icon} {priority_icon} {todo['content']}"


@tool(
    param_descriptions={
        "action": "Action to perform: add, list, complete, remove, update, clear",
        "content": "Task content (required for 'add' action)",
        "task_id": "Task number (1-based index, required for 'complete', 'remove', 'update' actions)",
        "priority": "Task priority: high, medium, low (default: medium)",
        "session_id": "Session identifier for isolated todo lists (default: 'default')",
    }
)
async def todo_list(
    action: str,
    content: Optional[str] = None,
    task_id: Optional[int] = None,
    priority: str = "medium",
    session_id: str = "default",
) -> str:
    """
    Manage a todo list for tracking tasks.
    
    Actions:
    - add: Add a new task
    - list: List all tasks
    - complete: Mark a task as completed
    - remove: Remove a task
    - update: Update task content or priority
    - clear: Clear all tasks
    """
    action = action.lower().strip()
    
    if action == "add":
        if not content:
            return "Error: 'content' is required for 'add' action"
        
        todos = _load_todos(session_id)
        new_todo = {
            "content": content,
            "status": "pending",
            "priority": priority.lower() if priority.lower() in ["high", "medium", "low"] else "medium",
            "created_at": datetime.now().isoformat(),
        }
        todos.append(new_todo)
        _save_todos(session_id, todos)
        
        return f"✅ Added task: {content}\nTotal tasks: {len(todos)}"
    
    elif action == "list":
        todos = _load_todos(session_id)
        if not todos:
            return "📋 No tasks in the list"
        
        lines = [f"📋 Todo List ({session_id}):", ""]
        for i, todo in enumerate(todos):
            lines.append(_format_todo(todo, i))
        
        pending = sum(1 for t in todos if t["status"] == "pending")
        completed = sum(1 for t in todos if t["status"] == "completed")
        lines.append("")
        lines.append(f"📊 Summary: {pending} pending, {completed} completed, {len(todos)} total")
        
        return "\n".join(lines)
    
    elif action == "complete":
        if task_id is None:
            return "Error: 'task_id' is required for 'complete' action"
        
        todos = _load_todos(session_id)
        if task_id < 1 or task_id > len(todos):
            return f"Error: Invalid task_id {task_id}. Valid range: 1-{len(todos)}"
        
        todos[task_id - 1]["status"] = "completed"
        todos[task_id - 1]["completed_at"] = datetime.now().isoformat()
        _save_todos(session_id, todos)
        
        return f"✅ Completed: {todos[task_id - 1]['content']}"
    
    elif action == "remove":
        if task_id is None:
            return "Error: 'task_id' is required for 'remove' action"
        
        todos = _load_todos(session_id)
        if task_id < 1 or task_id > len(todos):
            return f"Error: Invalid task_id {task_id}. Valid range: 1-{len(todos)}"
        
        removed = todos.pop(task_id - 1)
        _save_todos(session_id, todos)
        
        return f"🗑️ Removed: {removed['content']}\nRemaining tasks: {len(todos)}"
    
    elif action == "update":
        if task_id is None:
            return "Error: 'task_id' is required for 'update' action"
        
        todos = _load_todos(session_id)
        if task_id < 1 or task_id > len(todos):
            return f"Error: Invalid task_id {task_id}. Valid range: 1-{len(todos)}"
        
        todo = todos[task_id - 1]
        if content:
            todo["content"] = content
        if priority.lower() in ["high", "medium", "low"]:
            todo["priority"] = priority.lower()
        todo["updated_at"] = datetime.now().isoformat()
        
        _save_todos(session_id, todos)
        return f"📝 Updated task {task_id}: {todo['content']}"
    
    elif action == "clear":
        _save_todos(session_id, [])
        return "🗑️ All tasks cleared"
    
    else:
        return f"Error: Unknown action '{action}'. Valid actions: add, list, complete, remove, update, clear"
