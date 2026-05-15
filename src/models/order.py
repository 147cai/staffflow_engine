from __future__ import annotations
from datetime import date
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from .assignment import Month


class Order(BaseModel):
    model_config = {"frozen": False, "arbitrary_types_allowed": True}

    no: str
    name: str
    domain: str
    start_date: date
    end_date: date
    status: str

    initial_budget: Dict[str, float]
    consumed_before: Dict[str, float] = Field(default_factory=dict)
    whitelist: Optional[Dict[str, str]] = None      # {姓名: 级别}

    remaining: Dict[str, float] = Field(default_factory=dict)
    monthly_consumption: Dict[Month, Dict[str, float]] = Field(default_factory=dict)

    def model_post_init(self, __context) -> None:
        if not self.remaining:
            self.remaining = {
                lvl: round(self.initial_budget.get(lvl, 0) - self.consumed_before.get(lvl, 0), 2)
                for lvl in self.initial_budget
            }

    def is_active(self, month: Month, threshold: float = 0.05) -> bool:
        if self.status != "进行中":
            return False
        month_end = date(month.year, month.month, _month_last_day(month))
        if self.end_date < month or self.start_date > month_end:
            return False
        return any(v > threshold for v in self.remaining.values())

    def find_usable_level(self, intended: str, path: List[str], threshold: float = 0.05) -> Optional[str]:
        start = path.index(intended) if intended in path else 0
        for lvl in path[start:]:
            if self.remaining.get(lvl, 0) > threshold:
                return lvl
        return None

    def max_days_for_level(self, level: str, work_days_per_month: int, threshold: float = 0.05) -> int:
        budget = max(self.remaining.get(level, 0) - threshold, 0)
        return int(budget * work_days_per_month)

    def deduct(self, level: str, days: int, month: Month,
               work_days_per_month: int = 22, decimals: int = 2) -> float:
        consumed = round(days / work_days_per_month, decimals)
        self.remaining[level] = round(self.remaining.get(level, 0) - consumed, decimals)
        bucket = self.monthly_consumption.setdefault(month, {})
        bucket[level] = round(bucket.get(level, 0.0) + consumed, decimals)
        return consumed

    def staff_allowed(self, name: str) -> bool:
        return self.whitelist is None or name in self.whitelist

    def get_whitelist_level(self, name: str) -> Optional[str]:
        return self.whitelist.get(name) if self.whitelist else None


def _month_last_day(month: Month) -> int:
    import calendar as _cal
    _, d = _cal.monthrange(month.year, month.month)
    return d
