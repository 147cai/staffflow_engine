"""规则约束：领域壁垒、白名单过滤、降级路径。"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple

from ..models import Month, Order, Staff


class RulesConfig:
    def __init__(self, cfg: dict):
        budget = cfg.get("budget", {})
        self.work_days_per_month: int = budget.get("work_days_per_month", 22)
        self.threshold: float = budget.get("exhaustion_threshold", 0.05)
        self.decimals: int = budget.get("rounding_decimals", 2)

        downgrade = cfg.get("downgrade", {})
        self.downgrade_enabled: bool = downgrade.get("enabled", True)
        self.downgrade_path: List[str] = downgrade.get("path", ["高级", "中级", "初级"])

        scoring = cfg.get("scoring", {})
        self.continuity_bonus: int = scoring.get("continuity_bonus", 1000)
        self.urgency_bonus: int = scoring.get("urgency_bonus", 500)
        self.urgency_months: int = scoring.get("urgency_months", 3)
        self.duration_weight: int = scoring.get("duration_weight", 10)

        warn = cfg.get("warnings", {})
        self.order_budget_months: int = warn.get("order_budget_months", 2)
        self.domain_warning_months: int = warn.get("domain_warning_months", 2)

    def can_enter_order(self, staff: Staff, order: Order) -> bool:
        if staff.domain != order.domain:
            return False
        if not order.staff_allowed(staff.name):
            return False
        return True

    def effective_level(self, staff: Staff, order: Order) -> str:
        wl = order.get_whitelist_level(staff.name)
        if wl:
            return wl
        return staff.base_level

    def find_usable_level(self, staff: Staff, order: Order, month: Month) -> Optional[str]:
        intended = self.effective_level(staff, order)
        if not self.downgrade_enabled:
            return intended if order.remaining.get(intended, 0) > self.threshold else None
        return order.find_usable_level(intended, self.downgrade_path, self.threshold)
