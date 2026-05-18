"""pytest 共用 fixtures。"""
from __future__ import annotations
from datetime import date
import pytest
import yaml

from src.engine.rules import RulesConfig
from src.models import BorrowConfig, MonthWindow, Order, Staff, WorkCalendar
from src.utils import month_range

_DEFAULT_RULES = {
    "budget": {"work_days_per_month": 22, "exhaustion_threshold": 0.05, "rounding_decimals": 2},
    "downgrade": {"enabled": True, "path": ["高级", "中级", "初级"], "consume_target_level": True},
    "domain": {"strict": True, "overrides": {}},
    "scoring": {"continuity_bonus": 1000, "urgency_bonus": 500,
                "urgency_months": 3, "duration_weight": 10},
    "warnings": {"order_budget_months": 2, "domain_warning_months": 2},
}


@pytest.fixture
def rules():
    return RulesConfig(_DEFAULT_RULES)


@pytest.fixture
def calendar():
    return WorkCalendar(work_days={
        date(2026, 5, 1): 19,
        date(2026, 6, 1): 21,
        date(2026, 7, 1): 23,
        date(2026, 8, 1): 21,
        date(2026, 9, 1): 21,
    })


def make_order(no: str, domain: str = "信贷", senior: float = 10.0,
               mid: float = 20.0, junior: float = 10.0,
               start: date = date(2026, 1, 1), end: date = date(2027, 3, 31),
               whitelist=None) -> Order:
    budget = {"高级": senior, "中级": mid, "初级": junior}
    o = Order(no=no, name=no, domain=domain, start_date=start, end_date=end,
              status="进行中", initial_budget=budget, whitelist=whitelist)
    return o


def make_staff(name: str, domain: str = "信贷", level: str = "中级",
               order_no: str = "F001", entry: date = date(2026, 1, 1),
               exit_: date = None) -> Staff:
    s = Staff(name=name, domain=domain, base_level=level,
              initial_order_no=order_no, current_order_no=order_no,
              initial_level=level, current_level=level,
              entry_date=entry, exit_date=exit_)
    return s


def make_window(calendar: WorkCalendar, month: date,
                data_date: date = None, end_date: date = None) -> MonthWindow:
    """便捷生成 MonthWindow（测试用）。"""
    return calendar.window_for(month, data_date, end_date)
