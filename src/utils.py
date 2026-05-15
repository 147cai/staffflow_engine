"""共用工具函数（日期、月份列表等）。"""
from __future__ import annotations
import calendar as _cal
from datetime import date, timedelta
from typing import List

from .models.assignment import Month


def month_range(start: Month, end: Month) -> List[Month]:
    """生成从 start 到 end（含）的月份列表，每个月用 day=1 的 date 表示。"""
    months: List[Month] = []
    cur = start
    while cur <= end:
        months.append(cur)
        _, last = _cal.monthrange(cur.year, cur.month)
        nxt = date(cur.year, cur.month, last) + timedelta(days=1)
        cur = date(nxt.year, nxt.month, 1)
    return months


def month_label(month: Month) -> str:
    """返回 '5月' 形式的短标签，用于表头。"""
    return f"{month.month}月"


def month_end(month: Month) -> date:
    """返回该月最后一天。"""
    _, d = _cal.monthrange(month.year, month.month)
    return date(month.year, month.month, d)
