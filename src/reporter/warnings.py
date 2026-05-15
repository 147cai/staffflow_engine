"""预警检测：订单预算、领域停排、人员闲置、数据异常。"""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from typing import Dict, List, Tuple

from ..models import Month, Order, Staff
from ..engine.rules import RulesConfig


def build_rows(
    orders: Dict[str, Order],
    staff_pool: Dict[str, Staff],
    rules: RulesConfig,
    months: List[Month],
    loader_warnings: List[str],
    engine_warnings: List[str],
) -> Tuple[List[str], List[list]]:
    header = ["预警类型", "严重程度", "涉及对象", "描述", "建议行动"]
    rows = []

    rows += _order_budget_warnings(orders, months, rules)
    rows += _domain_idle_warnings(orders, staff_pool, months, rules)
    rows += _staff_idle_warnings(staff_pool)

    for w in loader_warnings + engine_warnings:
        level = "ERROR" if w.startswith("[校验]") or "致命" in w else "WARN"
        rows.append(["数据异常", level, "—", w, "请检查输入数据"])

    return header, rows


def _order_budget_warnings(orders: Dict[str, Order], months: List[Month],
                           rules: RulesConfig) -> List[list]:
    rows = []
    threshold_months = rules.order_budget_months
    for no, order in sorted(orders.items()):
        for level, remaining in order.remaining.items():
            recent = [order.monthly_consumption.get(m, {}).get(level, 0) for m in months[-2:]]
            avg = sum(recent) / len(recent) if recent else 0
            if avg <= 0:
                continue
            months_left = remaining / avg
            if months_left <= threshold_months:
                rows.append([
                    "订单预算预警", "WARN", f"{no} {level}",
                    f"剩余 {round(remaining, 2)} 人月，按当前节奏约 {round(months_left, 1)} 个月耗尽",
                    "建议向客户申请续期或补充新订单",
                ])
    return rows


def _domain_idle_warnings(orders: Dict[str, Order], staff_pool: Dict[str, Staff],
                          months: List[Month], rules: RulesConfig) -> List[list]:
    rows = []
    domains = {s.domain for s in staff_pool.values()}
    for domain in sorted(domains):
        domain_orders = [o for o in orders.values() if o.domain == domain]
        staff_count = sum(1 for s in staff_pool.values() if s.domain == domain)
        still_active = [o for o in domain_orders if any(
            o.is_active(m, rules.threshold) for m in months[-rules.domain_warning_months:])]
        if not still_active and staff_count > 0:
            rows.append([
                "领域停排预警", "ERROR", domain,
                f"{domain}领域所有订单预算即将耗尽，当前 {staff_count} 名人员将无单可排",
                "尽快向客户申请新订单",
            ])
    return rows


def _staff_idle_warnings(staff_pool: Dict[str, Staff]) -> List[list]:
    rows = []
    for staff in sorted(staff_pool.values(), key=lambda s: s.name):
        if staff.idle_months:
            months_str = "、".join(f"{m.year}年{m.month}月" for m in staff.idle_months)
            rows.append([
                "人员闲置预警", "WARN", staff.name,
                f"{staff.name}（{staff.domain}）在以下月份无单可排：{months_str}",
                "等待新订单下发，或调整借还配置",
            ])
    return rows
