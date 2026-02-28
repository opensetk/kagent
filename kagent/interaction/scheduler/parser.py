import re
from datetime import datetime, timedelta
from typing import Optional, Tuple, Union
from croniter import croniter


class TimeParseError(Exception):
    pass


class TimeParser:
    DELAY_PATTERN = re.compile(
        r"^(\d+)(s|m|h|d)$|"
        r"^(\d+)秒$|"
        r"^(\d+)分(钟)?$|"
        r"^(\d+)小?时$|"
        r"^(\d+)天$",
        re.IGNORECASE,
    )

    @classmethod
    def parse(
        cls, spec: str, trigger_type: str
    ) -> Tuple[Union[datetime, timedelta, str], Optional[str]]:
        spec = spec.strip()

        if trigger_type == "delay":
            return cls._parse_delay(spec)
        elif trigger_type == "once":
            return cls._parse_datetime(spec), None
        elif trigger_type == "cron":
            return cls._parse_cron(spec)
        else:
            raise TimeParseError(f"Unknown trigger type: {trigger_type}")

    @classmethod
    def _parse_delay(cls, spec: str) -> Tuple[timedelta, None]:
        spec = spec.lower().strip()

        match = re.match(r"^(\d+)(s|m|h|d)$", spec)
        if match:
            value, unit = int(match.group(1)), match.group(2)
            if unit == "s":
                return timedelta(seconds=value), None
            elif unit == "m":
                return timedelta(minutes=value), None
            elif unit == "h":
                return timedelta(hours=value), None
            elif unit == "d":
                return timedelta(days=value), None

        if "秒" in spec:
            m = re.search(r"(\d+)", spec)
            if m:
                value = int(m.group(1))
                return timedelta(seconds=value), None

        if "分" in spec:
            m = re.search(r"(\d+)", spec)
            if m:
                value = int(m.group(1))
                return timedelta(minutes=value), None

        if "时" in spec:
            m = re.search(r"(\d+)", spec)
            if m:
                value = int(m.group(1))
                return timedelta(hours=value), None

        if "天" in spec:
            m = re.search(r"(\d+)", spec)
            if m:
                value = int(m.group(1))
                return timedelta(days=value), None

        raise TimeParseError(f"Cannot parse delay spec: {spec}")

    @classmethod
    def _parse_datetime(cls, spec: str) -> datetime:
        spec = spec.strip()
        now = datetime.now()

        if re.match(r"^\d{4}-\d{2}-\d{2}", spec):
            try:
                return datetime.strptime(spec, "%Y-%m-%d %H:%M")
            except ValueError:
                try:
                    return datetime.strptime(spec, "%Y-%m-%d")
                except ValueError:
                    pass

        cn_time_map = {
            "今天": 0,
            "明天": 1,
            "后天": 2,
        }
        for cn, days in cn_time_map.items():
            if cn in spec:
                target_date = now + timedelta(days=days)
                time_match = re.search(r"(\d{1,2})[点时](?:(\d{1,2})(?:分)?)?", spec)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2) or 0)
                    return target_date.replace(hour=hour, minute=minute, second=0)
                return target_date.replace(hour=9, minute=0, second=0)

        if "明天下午" in spec or "下午" in spec:
            time_match = re.search(r"下午(\d{1,2})[点时]?", spec)
            if time_match:
                hour = int(time_match.group(1)) + 12
                target_date = now + timedelta(days=1)
                return target_date.replace(hour=hour, minute=0, second=0)

        if "早上" in spec or "上午" in spec:
            m = re.search(r"(\d{1,2})", spec)
            if m:
                hour = int(m.group(1))
                if "明" in spec:
                    target_date = now + timedelta(days=1)
                else:
                    target_date = now
                return target_date.replace(hour=hour, minute=0, second=0)

        time_match = re.search(r"(\d{1,2})[点时](?:(\d{1,2})(?:分)?)?", spec)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            if "明" in spec:
                target_date = now + timedelta(days=1)
            else:
                target_date = now
            if hour < 12 and ("下午" in spec or "晚" in spec):
                hour += 12
            return target_date.replace(hour=hour, minute=minute, second=0)

        cn_weekday_map = {
            "周一": 0,
            "周二": 1,
            "周三": 2,
            "周四": 3,
            "周五": 4,
            "周六": 5,
            "周日": 6,
            "星期一": 0,
            "星期二": 1,
            "星期三": 2,
            "星期四": 3,
            "星期五": 4,
            "星期六": 5,
            "星期天": 6,
        }
        for cn_day, offset in cn_weekday_map.items():
            if cn_day in spec:
                current_weekday = now.weekday()
                days_ahead = (offset - current_weekday + 7) % 7
                if days_ahead == 0:
                    days_ahead = 7
                target_date = now + timedelta(days=days_ahead)
                time_match = re.search(r"(\d{1,2})[点时]", spec)
                if time_match:
                    hour = int(time_match.group(1))
                    return target_date.replace(hour=hour, minute=0, second=0)
                return target_date.replace(hour=9, minute=0, second=0)

        raise TimeParseError(f"Cannot parse datetime spec: {spec}")

    @classmethod
    def _parse_cron(cls, spec: str) -> Tuple[str, str]:
        spec = spec.strip()

        cn_cron_map = {
            "每天": "0 9 * * *",
            "每天早上": "0 9 * * *",
            "每天下午": "0 17 * * *",
            "每天晚上": "0 20 * * *",
            "每小时": "0 * * * *",
            "每半小时": "0,30 * * * *",
            "每分钟": "* * * * *",
            "每周一": "0 9 * * 1",
            "每周一早上": "0 9 * * 1",
            "每月1号": "0 0 1 * *",
            "每月一号": "0 0 1 * *",
        }

        for cn_expr, cron_expr in cn_cron_map.items():
            if cn_expr in spec:
                hour_match = re.search(r"(\d{1,2})[点时]", spec)
                if hour_match and "每天" in cn_expr:
                    hour = int(hour_match.group(1))
                    cron_expr = f"0 {hour} * * *"
                return cron_expr, cron_expr

        if re.match(r"^\d+ \d+ \* \* \*$", spec):
            return spec, spec

        if re.match(r"^\d+ \d+ \d+ \* \*$", spec):
            return spec, spec

        raise TimeParseError(f"Cannot parse cron spec: {spec}")
