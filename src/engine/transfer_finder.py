"""转场目标订单评分与筛选。"""
from __future__ import annotations
import calendar as _cal
from datetime import date
from typing import Dict, List, Optional, Tuple

from ..models import Month, Order, Staff
from .rules import RulesConfig


def find_target(
    staff: Staff,
    month: Month,
    orders: Dict[str, Order],
    rules: RulesConfig,
    exclude_order: Optional[str] = None,
) -> Optional[Tuple[str, str]]:
    """
    返回 (order_no, usable_level) 或 None（无可用订单）。
    exclude_order: 当前已耗尽的订单，不再考虑。
    """
    candidates = _collect_candidates(staff, month, orders, rules, exclude_order)
    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[2], x[0]))   # 高分优先，同分按编号字典序
    order_no, level, _ = candidates[0]
    return order_no, level


def _collect_candidates(
    staff: Staff, month: Month, orders: Dict[str, Order],
    rules: RulesConfig, exclude_order: Optional[str],
) -> List[Tuple[str, str, int]]:
    from .budget import max_schedulable_days
    results = []
    for no, order in orders.items():
        if no == exclude_order:
            continue
        if not order.is_active(month, rules.threshold):
            continue
        if not rules.can_enter_order(staff, order):
            continue
        level = rules.find_usable_level(staff, order, month)
        if level is None:
            continue
        if max_schedulable_days(order, level, rules.work_days_per_month, rules.threshold) == 0:
            continue
        score = _score(staff, order, month, rules, level)
        results.append((no, level, score))
    return results


def _score(staff: Staff, order: Order, month: Month, rules: RulesConfig,
           level: Optional[str] = None) -> int:
    score = 0
    if staff.current_order_no == order.no:
        score += rules.continuity_bonus
    months_to_end = _months_between(month, order.end_date)
    if months_to_end <= rules.urgency_months:
        score += rules.urgency_bonus
    score += rules.duration_weight * months_to_end
    # Tiebreaker: prefer orders with more remaining budget to avoid low-capacity traps
    if level:
        remaining = order.remaining.get(level, 0)
        score += min(int(remaining * 10), 100)  # up to 100 pts for 10+ 人月 remaining
    return score


def _months_between(month: Month, end: date) -> int:
    end_month = date(end.year, end.month, 1)
    return max(0, (end_month.year - month.year) * 12 + (end_month.month - month.month))
