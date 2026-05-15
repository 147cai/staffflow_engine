"""输入数据校验：致命错误终止运行，数据警告写入预警列表。"""
from __future__ import annotations
from datetime import date
from typing import Dict, List

from ..models import BorrowConfig, Order, Staff, WorkCalendar


class ValidationError(Exception):
    pass


def validate_all(orders: Dict[str, Order], staff_pool: Dict[str, Staff],
                 calendar: WorkCalendar, borrows: List[BorrowConfig],
                 warnings: List[str]) -> None:
    _validate_orders(orders)
    _validate_staff(staff_pool, orders, warnings)
    _validate_borrows(borrows, orders, staff_pool, calendar, warnings)
    _validate_whitelists(orders, staff_pool, warnings)


def _validate_orders(orders: Dict[str, Order]) -> None:
    for no, o in orders.items():
        if not o.domain:
            raise ValidationError(f"订单 {no} 领域为空")
        if o.start_date > o.end_date:
            raise ValidationError(f"订单 {no} 开始日期 {o.start_date} > 结束日期 {o.end_date}")
        for lvl, budget in o.initial_budget.items():
            if budget < 0:
                raise ValidationError(f"订单 {no} {lvl}预算为负值 {budget}")
        for lvl, rem in o.remaining.items():
            if rem < -0.1:
                raise ValidationError(f"订单 {no} {lvl}剩余预算 {rem} 异常（已超支）")


def _validate_staff(staff_pool: Dict[str, Staff], orders: Dict[str, Order],
                    warnings: List[str]) -> None:
    for name, s in staff_pool.items():
        if not s.domain:
            raise ValidationError(f"人员 {name} 领域为空")
        if not s.base_level:
            warnings.append(f"[校验] {name} 资质为空，将按初级处理")
            s.base_level = "初级"
        if s.initial_order_no and s.initial_order_no not in orders:
            warnings.append(f"[校验] {name} 当前订单 {s.initial_order_no} 不在进行中订单列表，将视为无单在岗")
            s.current_order_no = None


def _validate_borrows(borrows: List[BorrowConfig], orders: Dict[str, Order],
                      staff_pool: Dict[str, Staff], calendar: WorkCalendar,
                      warnings: List[str]) -> None:
    for b in borrows:
        if b.to_order_no not in orders:
            raise ValidationError(f"借还配置：{b.staff_name} 借入订单 {b.to_order_no} 不存在")
        if b.days <= 0:
            raise ValidationError(f"借还配置：{b.staff_name} {b.month} 借用天数 {b.days} 无效")
        month_days = calendar.get_working_days(b.month)
        if month_days > 0 and b.days > month_days:
            raise ValidationError(
                f"借还配置：{b.staff_name} {b.month} 借用天数 {b.days} 超过当月工作日 {month_days}")
        staff = staff_pool.get(b.staff_name)
        if staff and staff.domain != b.from_domain:
            warnings.append(
                f"[借还配置] {b.staff_name} 领域 '{staff.domain}' 与配置借出方领域 '{b.from_domain}' 不一致，请核查")


def _validate_whitelists(orders: Dict[str, Order], staff_pool: Dict[str, Staff],
                         warnings: List[str]) -> None:
    for no, o in orders.items():
        if not o.whitelist:
            continue
        for name, wl_level in o.whitelist.items():
            staff = staff_pool.get(name)
            if staff and staff.domain != o.domain:
                warnings.append(
                    f"[遴选清单] {name}（{staff.domain}）出现在{o.domain}订单 {no} 白名单中，"
                    f"疑似跨领域——如需跨领域排班请改用借还配置")
