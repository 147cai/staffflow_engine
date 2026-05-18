"""共用工具函数（日期、月份列表等）。"""
from __future__ import annotations
import calendar as _cal
from datetime import date, timedelta
from typing import List, Optional

from .models.assignment import Month
from .models.calendar import MonthWindow, WorkCalendar


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


def window_range(calendar: WorkCalendar,
                 start_month: Month,
                 end_month: Month,
                 data_date: Optional[date] = None,
                 end_date: Optional[date] = None) -> List[MonthWindow]:
    """生成 start_month..end_month（含）的 MonthWindow 列表。
    首月若被 data_date 截断、末月若被 end_date 截断，会在 window_for 中体现。
    """
    return [calendar.window_for(m, data_date, end_date)
            for m in month_range(start_month, end_month)]


def month_label(month: Month) -> str:
    """返回 '5月' 形式的短标签，用于表头。"""
    return f"{month.month}月"


def month_end(month: Month) -> date:
    """返回该月最后一天。"""
    _, d = _cal.monthrange(month.year, month.month)
    return date(month.year, month.month, d)
