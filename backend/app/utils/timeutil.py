"""时间工具：全站统一东八区（Asia/Shanghai）。

库里用 DATETIME 存"本地墙上时间"（naive），序列化时统一补 +08:00 后缀，
这样前端拿到的永远是 `2026-10-17T12:00:00+08:00` 这种带时区的 ISO8601。
"""
from datetime import date, datetime, timedelta, timezone

CN_TZ = timezone(timedelta(hours=8))


def now_cn() -> datetime:
    """当前东八区时间（去掉 tzinfo，直接写库）。"""
    return datetime.now(CN_TZ).replace(tzinfo=None)


def today_cn() -> date:
    return datetime.now(CN_TZ).date()


def to_iso(dt: datetime | None) -> str | None:
    """naive datetime 视为东八区时间，输出带偏移的 ISO8601 字符串。"""
    if dt is None:
        return None
    return dt.replace(tzinfo=CN_TZ).isoformat()


def to_date_str(d: date | None) -> str | None:
    return d.isoformat() if d else None


def next_midnight_cn() -> datetime:
    """次日 0 点（东八区），额度重置时间。"""
    return datetime.combine(today_cn() + timedelta(days=1), datetime.min.time()).replace(tzinfo=CN_TZ)
