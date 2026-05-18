"""Order / Staff 模型方法单元测试。"""
from __future__ import annotations
from datetime import date
import pytest

from src.models import Order, Staff, WorkCalendar
from tests.conftest import make_order, make_staff, make_window


class TestOrderBudget:
    def test_remaining_after_init(self):
        o = make_order("F001", senior=10.0, mid=20.0, junior=5.0)
        assert o.remaining == {"高级": 10.0, "中级": 20.0, "初级": 5.0}

    def test_remaining_subtracts_consumed(self):
        o = make_order("F001", senior=10.0, mid=20.0, junior=5.0)
        o.consumed_before = {"高级": 2.0, "中级": 5.0, "初级": 0.0}
        # 直接重算 remaining（loader 中也是这样做的）
        o.remaining = {
            lvl: round(o.initial_budget.get(lvl, 0) - o.consumed_before.get(lvl, 0), 2)
            for lvl in o.initial_budget
        }
        assert o.remaining["高级"] == 8.0
        assert o.remaining["中级"] == 15.0

    def test_deduct_updates_remaining_and_monthly(self):
        o = make_order("F001", mid=10.0)
        month = date(2026, 5, 1)
        consumed = o.deduct("中级", 22, month, work_days_per_month=22)
        assert consumed == 1.0
        assert o.remaining["中级"] == pytest.approx(9.0)
        assert o.monthly_consumption[month]["中级"] == pytest.approx(1.0)

    def test_deduct_partial_days(self):
        o = make_order("F001", mid=10.0)
        month = date(2026, 5, 1)
        o.deduct("中级", 11, month, work_days_per_month=22)
        assert o.remaining["中级"] == pytest.approx(9.5)

    def test_find_usable_level_direct(self):
        o = make_order("F001", senior=5.0, mid=5.0)
        lvl = o.find_usable_level("高级", ["高级", "中级", "初级"])
        assert lvl == "高级"

    def test_find_usable_level_downgrade(self):
        o = make_order("F001", senior=0.0, mid=5.0, junior=0.0)
        # 高级预算耗尽，应降为中级
        o.remaining["高级"] = 0.0
        lvl = o.find_usable_level("高级", ["高级", "中级", "初级"])
        assert lvl == "中级"

    def test_find_usable_level_none_when_exhausted(self):
        o = make_order("F001", senior=0.0, mid=0.0, junior=0.0)
        o.remaining = {"高级": 0.0, "中级": 0.0, "初级": 0.0}
        lvl = o.find_usable_level("高级", ["高级", "中级", "初级"])
        assert lvl is None

    def test_is_active_normal(self):
        o = make_order("F001")
        assert o.is_active(date(2026, 5, 1))

    def test_is_active_ended(self):
        o = make_order("F001", end=date(2026, 4, 30))
        assert not o.is_active(date(2026, 5, 1))

    def test_is_active_exhausted(self):
        o = make_order("F001", senior=0.0, mid=0.0, junior=0.0)
        o.remaining = {"高级": 0.0, "中级": 0.0, "初级": 0.0}
        assert not o.is_active(date(2026, 5, 1))

    def test_whitelist_allowed(self):
        o = make_order("F001", whitelist={"张三": "高级", "李四": "中级"})
        assert o.staff_allowed("张三")
        assert not o.staff_allowed("王五")

    def test_no_whitelist_allows_all(self):
        o = make_order("F001")
        assert o.staff_allowed("任何人")

    def test_max_days_for_level(self):
        o = make_order("F001", mid=2.0)
        days = o.max_days_for_level("中级", 22)
        # (2.0 - 0.05) * 22 = 42.9 → int() = 42
        assert days == 42


class TestStaffAvailability:
    def test_is_active_normal(self):
        s = make_staff("甲", entry=date(2026, 1, 1))
        assert s.is_active(date(2026, 5, 1))

    def test_is_active_before_entry(self):
        s = make_staff("甲", entry=date(2026, 6, 1))
        assert not s.is_active(date(2026, 5, 1))

    def test_is_active_after_exit(self):
        s = make_staff("甲", entry=date(2026, 1, 1), exit_=date(2026, 4, 30))
        assert not s.is_active(date(2026, 5, 1))

    def test_get_available_days_full_month(self, calendar):
        s = make_staff("甲", entry=date(2026, 1, 1))
        w = make_window(calendar, date(2026, 5, 1))
        days = s.get_available_days(w, calendar)
        assert days == 19

    def test_get_available_days_partial_entry(self, calendar):
        # 5月17日进场，5月有19个工作日，共31天，后15天
        s = make_staff("甲", entry=date(2026, 5, 17))
        w = make_window(calendar, date(2026, 5, 1))
        days = s.get_available_days(w, calendar)
        assert days > 0
        assert days < 19

    def test_get_available_days_partial_exit(self, calendar):
        s = make_staff("甲", entry=date(2026, 1, 1), exit_=date(2026, 5, 10))
        w = make_window(calendar, date(2026, 5, 1))
        days = s.get_available_days(w, calendar)
        assert 0 < days < 19

    def test_borrowed_days_tracking(self):
        s = make_staff("甲")
        month = date(2026, 5, 1)
        assert s.get_borrowed_days(month) == 0
        s.set_borrowed_days(month, 5)
        assert s.get_borrowed_days(month) == 5
        s.set_borrowed_days(month, 3)
        assert s.get_borrowed_days(month) == 8   # 累加


class TestMonthWindow:
    """MonthWindow 与 window_for 截断逻辑测试。"""

    def test_full_month_window(self, calendar):
        w = calendar.window_for(date(2026, 5, 1))
        assert w.start == date(2026, 5, 1)
        assert w.end == date(2026, 5, 31)
        assert w.work_days == 19
        assert w.total_month_days == 19
        assert not w.is_partial

    def test_start_truncated_by_data_date(self, calendar):
        # 5.12 起排，按 proportional 估算（conftest calendar 无 holidays）
        w = calendar.window_for(date(2026, 5, 1), data_date=date(2026, 5, 12))
        assert w.start == date(2026, 5, 12)
        assert w.end == date(2026, 5, 31)
        assert w.work_days < 19
        assert w.total_month_days == 19
        assert w.is_partial

    def test_end_truncated_by_end_date(self, calendar):
        w = calendar.window_for(date(2026, 5, 1), end_date=date(2026, 5, 15))
        assert w.start == date(2026, 5, 1)
        assert w.end == date(2026, 5, 15)
        assert w.work_days < 19
        assert w.is_partial

    def test_data_date_in_other_month_no_truncation(self, calendar):
        # data_date 在 4 月，对 5 月窗口无影响
        w = calendar.window_for(date(2026, 5, 1), data_date=date(2026, 4, 20))
        assert w.start == date(2026, 5, 1)
        assert w.work_days == 19
        assert not w.is_partial

    def test_window_for_exact_calendar(self):
        # 用真实节假日配置验证 5.12 起排首月 = 14 个工作日
        cal = WorkCalendar(
            work_days={date(2026, 5, 1): 19},
            holidays={date(2026, 5, 1), date(2026, 5, 4), date(2026, 5, 5)},
        )
        w = cal.window_for(date(2026, 5, 1), data_date=date(2026, 5, 12))
        assert w.work_days == 14   # 5.12 周二起：5.12-15 + 5.18-22 + 5.25-29 = 14
        assert w.total_month_days == 19
