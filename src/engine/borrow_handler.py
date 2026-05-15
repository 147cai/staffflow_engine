"""跨领域借还：月内先扣借入订单天数，再处理原领域剩余天数。"""
from __future__ import annotations
import logging
from typing import Dict, List

from ..models import Assignment, BorrowConfig, Month, Order, Staff
from .rules import RulesConfig

log = logging.getLogger(__name__)


def apply_borrows(
    month: Month,
    borrows: List[BorrowConfig],
    staff_pool: Dict[str, Staff],
    orders: Dict[str, Order],
    rules: RulesConfig,
    warnings: List[str],
) -> None:
    """处理该月所有借还配置，扣减借入订单预算，记录借出天数。"""
    for b in borrows:
        if b.month != month:
            continue
        staff = staff_pool.get(b.staff_name)
        order = orders.get(b.to_order_no)
        if staff is None or order is None:
            continue
        _process_single_borrow(b, staff, order, rules, warnings)


def _process_single_borrow(
    b: BorrowConfig, staff: Staff, order: Order,
    rules: RulesConfig, warnings: List[str],
) -> None:
    intended = order.get_whitelist_level(staff.name) or staff.base_level
    level = order.find_usable_level(intended, rules.downgrade_path, rules.threshold)

    if level is None:
        warnings.append(
            f"[借还] {staff.name} {b.month} 借入订单 {order.no} 无可用预算，本次借还跳过")
        log.warning("Borrow skipped: %s %s -> %s no budget", staff.name, b.month, order.no)
        return

    order.deduct(level, b.days, b.month, rules.work_days_per_month, rules.decimals)
    staff.set_borrowed_days(b.month, b.days)

    note = f"跨领域借入（{b.from_domain}→{order.domain}）"
    staff.assignments.append(Assignment(
        staff_name=staff.name,
        order_no=order.no,
        level=level,
        month=b.month,
        days=b.days,
        is_borrow=True,
        note=note,
    ))
    log.debug("Borrow applied: %s %s -> %s %s %dd", staff.name, b.month, order.no, level, b.days)
