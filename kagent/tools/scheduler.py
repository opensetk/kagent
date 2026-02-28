import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable, TYPE_CHECKING
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from kagent.core.tool import tool
from kagent.interaction.scheduler import (
    ScheduledTask,
    TaskStore,
    TimeParser,
    TimeParseError,
)

if TYPE_CHECKING:
    from kagent.interaction.manager import InteractionManager
    from kagent.channel.base import BaseChannel


_global_scheduler: Optional["TaskScheduler"] = None
_store: Optional[TaskStore] = None
_interaction_manager: Optional["InteractionManager"] = None
_active_channel: Optional["BaseChannel"] = None
_current_session_id: Optional[str] = None


def get_scheduler() -> "TaskScheduler":
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = TaskScheduler()
        _global_scheduler.set_executor_callback(_execute_scheduled_task)
    return _global_scheduler


def get_store() -> TaskStore:
    global _store
    if _store is None:
        _store = TaskStore()
    return _store


def set_interaction_manager(manager: "InteractionManager"):
    global _interaction_manager
    _interaction_manager = manager


def set_active_channel(channel: "BaseChannel"):
    global _active_channel
    _active_channel = channel


def set_current_session_id(session_id: str):
    global _current_session_id
    _current_session_id = session_id


def get_current_session_id() -> Optional[str]:
    global _current_session_id
    return _current_session_id


_target_id_storage: Dict[str, str] = {}


def set_target_id(target_id: str, target_id_type: str = "open_id"):
    """Set target_id for channel pushback (called by channel when handling message)."""
    global _target_id_storage
    session_id = _current_session_id or "default"
    _target_id_storage[session_id] = target_id
    _target_id_storage[f"{session_id}_type"] = target_id_type


def _get_target_id() -> Optional[str]:
    """Get target_id for current session."""
    global _target_id_storage
    session_id = _current_session_id or "default"
    return _target_id_storage.get(session_id)


def _get_target_id_type() -> str:
    """Get target_id_type for current session."""
    global _target_id_storage
    session_id = _current_session_id or "default"
    return _target_id_storage.get(f"{session_id}_type", "open_id")


async def _execute_scheduled_task(task: ScheduledTask):
    """Execute a scheduled task."""
    global _interaction_manager, _active_channel

    if _interaction_manager is None:
        print(f"Error: InteractionManager not set for scheduled task {task.task_id}")
        return

    store = get_store()
    task_data = store.get(task.task_id)
    if not task_data:
        print(f"Error: Task {task.task_id} not found")
        return

    task = task_data

    if task.status == "cancelled":
        print(f"Task {task.task_id} was cancelled, skipping")
        return

    trigger_info = ""
    if task.trigger_type == "once" and task.trigger_time:
        trigger_info = f"原计划执行时间: {task.trigger_time}"
    elif task.trigger_type == "delay":
        trigger_info = f"延迟任务"
    elif task.trigger_type == "cron":
        trigger_info = f"周期任务: {task.trigger_spec}"

    session_id = task.session_id if task.session_id else "scheduled-task"

    # Use task's target_id for pushback, fallback to session_id
    push_target_id = task.target_id if task.target_id else session_id
    push_target_id_type = task.target_id_type if task.target_id_type else "open_id"

    try:
        result = await _interaction_manager.handle_scheduled_task(
            instruction=task.instruction,
            session_id=session_id,
            trigger_info=trigger_info,
        )

        task.mark_completed()
        store.update(task)

        if _active_channel:
            await _active_channel.send_message(
                target_id=push_target_id,
                content=f"⏰ 定时任务执行结果：\n\n{result.message}",
                target_id_type=push_target_id_type,
            )
    except Exception as e:
        task.mark_failed(str(e))
        store.update(task)
        print(f"Error executing scheduled task {task.task_id}: {e}")


class TaskScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._executor_callback: Optional[Callable[[ScheduledTask], Any]] = None

    def set_executor_callback(self, callback: Callable[[ScheduledTask], Any]):
        self._executor_callback = callback

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()

    def add_task(self, task: ScheduledTask, run_time):
        if task.trigger_type == "delay":
            trigger = DateTrigger(run_date=run_time)
        elif task.trigger_type == "once":
            trigger = DateTrigger(run_date=run_time)
        elif task.trigger_type == "cron":
            trigger = CronTrigger.from_crontab(task.trigger_spec)
        else:
            raise ValueError(f"Unknown trigger type: {task.trigger_type}")

        job_id = task.task_id
        self.scheduler.add_job(
            self._execute_task,
            trigger=trigger,
            id=job_id,
            args=[task],
            replace_existing=True,
        )

    async def _execute_task(self, task: ScheduledTask):
        if self._executor_callback:
            await self._executor_callback(task)

    def remove_job(self, task_id: str):
        try:
            self.scheduler.remove_job(task_id)
        except Exception:
            pass

    def get_job(self, task_id: str):
        return self.scheduler.get_job(task_id)

    def list_jobs(self) -> List[Dict[str, Any]]:
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "next_run_time": str(job.next_run_time)
                    if job.next_run_time
                    else None,
                }
            )
        return jobs


@tool(
    name="schedule_task",
    description="创建定时任务。支持延迟执行(delay)、指定时间执行(once)和周期执行(cron)。",
    param_descriptions={
        "instruction": "任务的具体内容描述，即到达时间后要执行的指令",
        "trigger_type": "触发类型：delay(延迟执行)、once(指定时间执行)、cron(周期执行)",
        "trigger_spec": "触发规格。delay格式：5m(5分钟)、2h30m(2小时30分钟)、30s(30秒)、1d(1天)；once格式：2025-01-01 09:00、明天下午3点、下周一早上8点；cron格式：每天9点、每小时、0 9 * * *",
    },
)
async def schedule_task(
    instruction: str,
    trigger_type: str,
    trigger_spec: str,
) -> str:
    """
    创建定时任务。
    """
    if trigger_type not in ["delay", "once", "cron"]:
        return f"错误：无效的触发类型 {trigger_type}，必须是 delay、once 或 cron"

    try:
        parsed_time, _ = TimeParser.parse(trigger_spec, trigger_type)
    except TimeParseError as e:
        return f"错误：无法解析时间表达式 {trigger_spec}，{str(e)}"

    task_id = ScheduledTask.generate_task_id()
    store = get_store()
    session_id = get_current_session_id() or "default"

    # Get target_id from global for channel pushback
    target_id = _get_target_id() or session_id

    if trigger_type in ["delay", "once"]:
        if isinstance(parsed_time, timedelta):
            run_time = datetime.now() + parsed_time
            trigger_time = run_time.isoformat()
        elif isinstance(parsed_time, datetime):
            run_time = parsed_time
            trigger_time = run_time.isoformat()
        else:
            return f"错误：无法处理的时间类型"
    else:
        run_time = None
        trigger_time = None

    task = ScheduledTask(
        task_id=task_id,
        instruction=instruction,
        trigger_type=trigger_type,
        trigger_spec=trigger_spec,
        session_id=session_id,
        trigger_time=trigger_time,
        target_id=target_id,
        target_id_type=_get_target_id_type(),
    )

    store.save(task)

    scheduler = get_scheduler()
    scheduler.start()
    if run_time:
        scheduler.add_task(task, run_time)

    trigger_desc = ""
    if trigger_type == "delay":
        if isinstance(parsed_time, timedelta):
            total_seconds = int(parsed_time.total_seconds())
            if total_seconds >= 86400:
                days = total_seconds // 86400
                hours = (total_seconds % 86400) // 3600
                trigger_desc = f"{days}天{hours}小时后"
            elif total_seconds >= 3600:
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                trigger_desc = f"{hours}小时{minutes}分钟后"
            else:
                trigger_desc = f"{total_seconds}秒后"
    elif trigger_type == "once":
        trigger_desc = f"于 {trigger_spec}"
    elif trigger_type == "cron":
        trigger_desc = f"按计划 {trigger_spec} 循环执行"

    return f"✅ 任务已创建！\n任务ID: {task_id}\n执行时间: {trigger_desc}\n任务内容: {instruction}"


@tool(
    name="list_tasks",
    description="列出所有定时任务",
    param_descriptions={},
)
async def list_tasks() -> str:
    """
    列出所有定时任务。
    """
    store = get_store()
    tasks = store.get_all()

    if not tasks:
        return "暂无定时任务。使用 schedule_task 创建新任务。"

    lines = ["📋 定时任务列表：\n"]
    for task in tasks:
        status_emoji = {
            "pending": "⏳",
            "completed": "✅",
            "cancelled": "❌",
            "failed": "⚠️",
        }.get(task.status, "❓")

        trigger_info = ""
        if task.trigger_type == "delay":
            trigger_info = f"延迟: {task.trigger_spec}"
        elif task.trigger_type == "once":
            trigger_info = f"时间: {task.trigger_time or task.trigger_spec}"
        elif task.trigger_type == "cron":
            trigger_info = f"Cron: {task.trigger_spec}"

        lines.append(f"{status_emoji} [{task.task_id}]")
        lines.append(f"   任务: {task.instruction}")
        lines.append(f"   类型: {task.trigger_type} - {trigger_info}")
        lines.append(f"   状态: {task.status}")
        if task.last_run:
            lines.append(f"   上次执行: {task.last_run}")
        lines.append("")

    return "\n".join(lines)


@tool(
    name="cancel_task",
    description="取消指定的定时任务",
    param_descriptions={
        "task_id": "要取消的任务ID",
    },
)
async def cancel_task(task_id: str) -> str:
    """
    取消指定的定时任务。
    """
    store = get_store()
    task = store.get(task_id)

    if not task:
        return f"错误：未找到任务 {task_id}"

    if task.status == "cancelled":
        return f"任务 {task_id} 已经是取消状态"

    if task.status == "completed":
        return f"任务 {task_id} 已经执行完成，无法取消"

    task.mark_cancelled()
    store.update(task)

    scheduler = get_scheduler()
    scheduler.remove_job(task_id)

    return f"✅ 任务 {task_id} 已取消\n任务内容: {task.instruction}"


@tool(
    name="show_task",
    description="查看指定定时任务的详细信息",
    param_descriptions={
        "task_id": "要查看的任务ID",
    },
)
async def show_task(task_id: str) -> str:
    """
    查看指定定时任务的详细信息。
    """
    store = get_store()
    task = store.get(task_id)

    if not task:
        return f"错误：未找到任务 {task_id}"

    lines = [
        f"📌 任务详情",
        f"",
        f"ID: {task.task_id}",
        f"任务: {task.instruction}",
        f"类型: {task.trigger_type}",
        f"规格: {task.trigger_spec}",
        f"状态: {task.status}",
        f"创建时间: {task.created_at}",
    ]

    if task.trigger_time:
        lines.append(f"触发时间: {task.trigger_time}")

    if task.last_run:
        lines.append(f"上次执行: {task.last_run}")

    if task.run_count > 0:
        lines.append(f"执行次数: {task.run_count}")

    if task.error:
        lines.append(f"错误信息: {task.error}")

    return "\n".join(lines)
