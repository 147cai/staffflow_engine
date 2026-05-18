"""主排班循环：按月推进，处理借还 → 常规排班 → 转场。"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from ..models import (Assignment, BorrowConfig, Month, MonthWindow, Order,
                      Staff, TransferRecord, WorkCalendar)
from ..utils import window_range
from .borrow_handler import apply_borrows
from .budget import compute_transfer_date, max_schedulable_days
from .rules import RulesConfig
from .transfer_finder import find_target

log = logging.getLogger(__name__)


@dataclass
class ScheduleResult:
    orders: Dict[str, Order]
    staff_pool: Dict[str, Staff]
    warnings: List[str] = field(default_factory=list)
    windows: List[MonthWindow] = field(default_factory=list)

    @property
    def all_assignments(self) -> List[Assignment]:
        return [a for s in self.staff_pool.values() for a in s.assignments]

    @property
    def all_transfers(self) -> List[TransferRecord]:
        return [t for s in self.staff_pool.values() for t in s.transfers]


def run(
    orders: Dict[str, Order],
    staff_pool: Dict[str, Staff],
    calendar: WorkCalendar,
    borrow_configs: List[BorrowConfig],
    rules: RulesConfig,
    start_month: Month,
    end_month: Month,
    loader_warnings: List[str],
    data_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> ScheduleResult:
    windows = window_range(calendar, start_month, end_month, data_date, end_date)
    result = ScheduleResult(orders=orders, staff_pool=staff_pool,
                            warnings=list(loader_warnings), windows=windows)

    for window in windows:
        log.info("Scheduling month %s window %s~%s (%d work days, total %d)",
                 window.month, window.start, window.end,
                 window.work_days, window.total_month_days)

        apply_borrows(window, borrow_configs, staff_pool, orders, rules, result.warnings)

        for staff in sorted(staff_pool.values(), key=lambda s: s.name):
            if not staff.is_active(window.month):
                continue
            _schedule_staff_month(staff, window, orders, calendar, rules, result.warnings)

    _collect_idle_warnings(staff_pool, result.warnings)
    return result


def _schedule_staff_month(
    staff: Staff, window: MonthWindow,
    orders: Dict[str, Order], calendar: WorkCalendar,
    rules: RulesConfig, warnings: List[str],
) -> None:
    month = window.month
    available = staff.get_available_days(window, calendar)
    available -= staff.get_borrowed_days(month)
    if available <= 0:
        return

    days_left = available
    days_placed = 0   # 用于计算转场日期

    current_no = staff.current_order_no
    current_order = orders.get(current_no) if current_no else None

    # 当前订单：遍历完整降级路径（高级→中级→初级），直到天数排满或全部级别耗尽才转场
    # 业务规则：必须等该订单所有可用级别预算耗尽，人员才能转场
    if current_order and current_order.is_active(month, rules.threshold):
        intended = rules.effective_level(staff, current_order)
        path_start = (rules.downgrade_path.index(intended)
                      if intended in rules.downgrade_path else 0)
        for lvl in rules.downgrade_path[path_start:]:
            if days_left <= 0:
                break
            if current_order.remaining.get(lvl, 0) <= rules.threshold:
                continue  # 该级别已耗尽（含阈值保护），尝试下一级
            placeable = max_schedulable_days(current_order, lvl,
                                             rules.work_days_per_month, rules.threshold)
            if placeable <= 0:
                continue  # 阈值保护导致可排天数为0，尝试下一级
            actual = min(days_left, placeable)
            _add_assignment(staff, current_no, lvl, month, actual, current_order, rules)
            days_placed += actual
            days_left -= actual

    if days_left <= 0:
        return

    # 当前订单预算耗尽或无订单，需转场
    transfer_date = compute_transfer_date(window, days_placed, available)
    exclude = current_no
    target = find_target(staff, month, orders, rules, exclude_order=exclude)

    if target:
        new_no, new_level = target
        _record_transfer(staff, current_no, new_no, transfer_date, days_left,
                         orders[new_no].domain, warnings)
        new_order = orders[new_no]
        placeable = max_schedulable_days(new_order, new_level,
                                        rules.work_days_per_month, rules.threshold)
        actual = min(days_left, placeable)
        _add_assignment(staff, new_no, new_level, month, actual, new_order, rules)
        staff.current_order_no = new_no
        staff.current_level = new_level
        days_left -= actual
    else:
        # 仅在第一次进入闲置（或从有订单到无订单）时写入转场表，连续闲置不重复写
        if _is_new_idle(staff):
            _record_transfer(staff, current_no, None, transfer_date, days_left,
                             staff.domain, warnings)
        staff.idle_months.append(month)
        log.warning("Idle: %s in %s (%d days)", staff.name, month, days_left)
        days_left = 0


def _add_assignment(staff: Staff, order_no: str, level: str, month: Month,
                    days: int, order: Order, rules: RulesConfig) -> None:
    if days <= 0:
        return
    order.deduct(level, days, month, rules.work_days_per_month, rules.decimals)
    staff.assignments.append(Assignment(
        staff_name=staff.name, order_no=order_no, level=level,
        month=month, days=days,
    ))


def _is_new_idle(staff: Staff) -> bool:
    """True 当且仅当本次是第一次闲置，或上次有有效订单（非连续闲置）。"""
    if not staff.transfers:
        return True
    return staff.transfers[-1].to_order is not None


def _record_transfer(staff: Staff, from_order: Optional[str], to_order: Optional[str],
                     transfer_date: date, remaining_days: int,
                     domain: str, warnings: List[str]) -> None:
    reason = "原订单预算耗尽" if from_order else "订单到期"
    rec = TransferRecord(
        staff_name=staff.name,
        from_order=from_order or "（无）",
        to_order=to_order,
        transfer_date=transfer_date,
        remaining_days_in_month=remaining_days,
        domain=domain,
        reason=reason,
    )
    staff.transfers.append(rec)
    if to_order is None:
        warnings.append(
            f"[人员闲置] {staff.name} 于 {transfer_date} 后无单可排（{remaining_days}天），等待新订单")


def _collect_idle_warnings(staff_pool: Dict[str, Staff], warnings: List[str]) -> None:
    idle_staff = [s.name for s in staff_pool.values() if s.idle_months]
    if idle_staff:
        warnings.append(f"[人员闲置汇总] 以下人员存在闲置月份：{', '.join(idle_staff)}")


