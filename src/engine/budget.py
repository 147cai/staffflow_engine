"""预算计算工具函数。"""
from __future__ import annotations
import calendar as _cal
from datetime import date, timedelta
from typing import Optional

from ..models import Month, Order


def compute_transfer_date(month: Month, days_worked_before: int,
                          total_work_days: int) -> date:
    """
    估算转场发生的日历日期。
    按比例将"第 days_worked_before 个工作日"映射到该月的日历天。
    """
    if total_work_days <= 0:
        return month
    _, days_in_month = _cal.monthrange(month.year, month.month)
    fraction = min(days_worked_before / total_work_days, 1.0)
    day_offset = max(round(fraction * days_in_month), 1)
    day_offset = min(day_offset, days_in_month)
    return date(month.year, month.month, day_offset)


def max_schedulable_days(order: Order, level: str,
                         work_days_per_month: int = 22,
                         threshold: float = 0.05) -> int:
    """该订单该级别剩余预算最多可排多少工作日。"""
    budget = max(order.remaining.get(level, 0) - threshold, 0)
    return int(budget * work_days_per_month)
