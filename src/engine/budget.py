"""预算计算工具函数。"""
from __future__ import annotations
from datetime import date, timedelta

from ..models import MonthWindow, Order


def compute_transfer_date(window: MonthWindow, days_worked_before: int,
                          available_days: int) -> date:
    """估算转场发生的日历日期。
    按比例将"第 days_worked_before 个工作日"映射到窗口的自然日范围。
    """
    if available_days <= 0:
        return window.start
    span = window.natural_span
    fraction = min(days_worked_before / available_days, 1.0)
    day_offset = max(round(fraction * span), 1)
    day_offset = min(day_offset, span)
    return window.start + timedelta(days=day_offset - 1)


def max_schedulable_days(order: Order, level: str,
                         work_days_per_month: int = 22,
                         threshold: float = 0.05) -> int:
    """该订单该级别剩余预算最多可排多少工作日。"""
    budget = max(order.remaining.get(level, 0) - threshold, 0)
    return int(budget * work_days_per_month)
