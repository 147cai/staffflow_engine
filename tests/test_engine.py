"""引擎核心逻辑测试：转场评分、借还处理、整月排班。"""
from __future__ import annotations
from datetime import date
import pytest

from src.engine import borrow_handler, transfer_finder
from src.engine.budget import compute_transfer_date, max_schedulable_days
from src.engine.scheduler import run as run_scheduler
from src.models import BorrowConfig, WorkCalendar
from tests.conftest import make_order, make_staff, make_window, _DEFAULT_RULES
from src.engine.rules import RulesConfig


@pytest.fixture
def rules():
    return RulesConfig(_DEFAULT_RULES)


@pytest.fixture
def calendar():
    return WorkCalendar(work_days={
        date(2026, 5, 1): 19,
        date(2026, 6, 1): 21,
        date(2026, 7, 1): 23,
    })


class TestTransferFinder:
    def test_finds_same_domain_order(self, rules):
        # 排除当前订单 F001（模拟预算耗尽），验证能找到 F002
        orders = {
            "F001": make_order("F001", domain="信贷", mid=10.0),
            "F002": make_order("F002", domain="信贷", mid=10.0),
        }
        staff = make_staff("甲", domain="信贷", order_no="F001")
        result = transfer_finder.find_target(staff, date(2026, 5, 1), orders, rules,
                                             exclude_order="F001")
        assert result is not None
        assert result[0] == "F002"

    def test_respects_domain_barrier(self, rules):
        orders = {
            "F001": make_order("F001", domain="房改", mid=10.0),
        }
        staff = make_staff("甲", domain="信贷", order_no="X999")
        result = transfer_finder.find_target(staff, date(2026, 5, 1), orders, rules)
        assert result is None

    def test_continuity_bonus_prefers_current_order(self, rules):
        orders = {
            "F001": make_order("F001", domain="信贷", mid=10.0),
            "F002": make_order("F002", domain="信贷", mid=10.0),
        }
        staff = make_staff("甲", domain="信贷", order_no="F001")
        result = transfer_finder.find_target(staff, date(2026, 5, 1), orders, rules)
        # F001 has continuity bonus, should be preferred
        assert result[0] == "F001"

    def test_excludes_exhausted_order(self, rules):
        exhausted = make_order("F001", domain="信贷", mid=0.0)
        exhausted.remaining = {"高级": 0.0, "中级": 0.0, "初级": 0.0}
        orders = {
            "F001": exhausted,
            "F002": make_order("F002", domain="信贷", mid=10.0),
        }
        staff = make_staff("甲", domain="信贷", order_no="F001")
        result = transfer_finder.find_target(staff, date(2026, 5, 1), orders, rules,
                                             exclude_order="F001")
        assert result is not None
        assert result[0] == "F002"

    def test_whitelist_filter(self, rules):
        wl_order = make_order("F002", domain="信贷", mid=10.0, whitelist={"乙": "中级"})
        orders = {"F002": wl_order}
        staff_ok = make_staff("乙", domain="信贷", order_no="X")
        staff_no = make_staff("丙", domain="信贷", order_no="X")
        assert transfer_finder.find_target(staff_ok, date(2026, 5, 1), orders, rules) is not None
        assert transfer_finder.find_target(staff_no, date(2026, 5, 1), orders, rules) is None


class TestBorrowHandler:
    def test_borrow_deducts_target_budget(self, rules, calendar):
        orders = {"F001": make_order("F001", domain="信贷", mid=5.0)}
        staff_pool = {"房改甲": make_staff("房改甲", domain="房改", order_no="F999")}
        month = date(2026, 5, 1)
        window = make_window(calendar, month)
        borrows = [BorrowConfig(staff_name="房改甲", from_domain="房改",
                                to_order_no="F001", month=month, days=11)]
        warnings = []
        borrow_handler.apply_borrows(window, borrows, staff_pool, orders, rules, warnings)

        assert orders["F001"].remaining["中级"] == pytest.approx(4.5)
        assert staff_pool["房改甲"].get_borrowed_days(month) == 11
        assert len(staff_pool["房改甲"].assignments) == 1
        a = staff_pool["房改甲"].assignments[0]
        assert a.is_borrow is True
        assert a.days == 11

    def test_borrow_warns_on_no_budget(self, rules, calendar):
        orders = {"F001": make_order("F001", domain="信贷", mid=0.0)}
        orders["F001"].remaining = {"高级": 0.0, "中级": 0.0, "初级": 0.0}
        staff_pool = {"房改甲": make_staff("房改甲", domain="房改", order_no="F999")}
        month = date(2026, 5, 1)
        window = make_window(calendar, month)
        borrows = [BorrowConfig(staff_name="房改甲", from_domain="房改",
                                to_order_no="F001", month=month, days=5)]
        warnings = []
        borrow_handler.apply_borrows(window, borrows, staff_pool, orders, rules, warnings)
        assert len(warnings) == 1
        assert len(staff_pool["房改甲"].assignments) == 0


class TestBudgetUtils:
    def test_transfer_date_midmonth(self, calendar):
        w = make_window(calendar, date(2026, 5, 1))
        d = compute_transfer_date(w, 10, 20)   # 50% of 31 days = day 16
        assert d == date(2026, 5, 16)

    def test_transfer_date_full_month(self, calendar):
        w = make_window(calendar, date(2026, 5, 1))
        d = compute_transfer_date(w, 19, 19)   # 100% → last day
        assert d.month == 5
        assert d.day == 31

    def test_transfer_date_start_of_month(self, calendar):
        w = make_window(calendar, date(2026, 5, 1))
        d = compute_transfer_date(w, 0, 19)    # 0% → day 1
        assert d == date(2026, 5, 1)

    def test_max_days_basic(self):
        o = make_order("F001", mid=2.0)
        # (2.0 - 0.05) * 22 = 42.9 → 42
        assert max_schedulable_days(o, "中级", 22) == 42

    def test_max_days_zero_when_exhausted(self):
        o = make_order("F001", mid=0.0)
        o.remaining["中级"] = 0.0
        assert max_schedulable_days(o, "中级", 22) == 0


class TestSchedulerIntegration:
    """小规模端到端测试：2人2订单，验证排班和转场逻辑。"""

    def test_basic_schedule_no_transfer(self, rules, calendar):
        orders = {"F001": make_order("F001", domain="信贷", mid=50.0)}
        staff_pool = {"甲": make_staff("甲", domain="信贷", level="中级", order_no="F001")}
        result = run_scheduler(
            orders=orders, staff_pool=staff_pool, calendar=calendar,
            borrow_configs=[], rules=rules,
            start_month=date(2026, 5, 1), end_month=date(2026, 6, 1),
            loader_warnings=[],
        )
        assignments = [a for a in result.all_assignments if a.staff_name == "甲"]
        assert len(assignments) == 2    # May + June
        assert assignments[0].days == 19
        assert assignments[1].days == 21
        assert len(result.all_transfers) == 0

    def test_transfer_when_all_levels_exhausted(self, rules, calendar):
        # F001 所有级别预算耗尽（高=0, 中=0.5人月≈9天, 初=0）→ 排完后转场到 F002
        # 注意：必须所有级别都耗尽才转场（业务规则）
        f001 = make_order("F001", domain="信贷", senior=0.0, mid=0.5, junior=0.0)
        f001.remaining = {"高级": 0.0, "中级": 0.5, "初级": 0.0}
        f002 = make_order("F002", domain="信贷", mid=50.0)
        orders = {"F001": f001, "F002": f002}
        staff_pool = {"甲": make_staff("甲", domain="信贷", level="中级", order_no="F001")}

        result = run_scheduler(
            orders=orders, staff_pool=staff_pool, calendar=calendar,
            borrow_configs=[], rules=rules,
            start_month=date(2026, 5, 1), end_month=date(2026, 5, 1),
            loader_warnings=[],
        )
        # 5月：先在 F001 排约9天（中级0.5人月），中级/初级全部耗尽后转场到 F002
        assignments = result.all_assignments
        f001_days = sum(a.days for a in assignments if a.order_no == "F001")
        f002_days = sum(a.days for a in assignments if a.order_no == "F002")
        assert f001_days + f002_days == 19
        assert len(result.all_transfers) == 1
        t = result.all_transfers[0]
        assert t.from_order == "F001"
        assert t.to_order == "F002"

    def test_senior_uses_lower_level_budget_before_transfer(self, rules, calendar):
        # 高级工程师：高级预算耗尽后，继续用中级预算，全部耗尽才转场
        f001 = make_order("F001", domain="信贷", senior=0.0, mid=0.5, junior=0.0)
        f001.remaining = {"高级": 0.0, "中级": 0.5, "初级": 0.0}
        f002 = make_order("F002", domain="信贷", mid=50.0)
        orders = {"F001": f001, "F002": f002}
        staff_pool = {"甲": make_staff("甲", domain="信贷", level="高级", order_no="F001")}

        result = run_scheduler(
            orders=orders, staff_pool=staff_pool, calendar=calendar,
            borrow_configs=[], rules=rules,
            start_month=date(2026, 5, 1), end_month=date(2026, 5, 1),
            loader_warnings=[],
        )
        assignments = result.all_assignments
        # 高级工程师应当降级使用中级预算在 F001，耗尽后转 F002
        f001_a = [a for a in assignments if a.order_no == "F001"]
        assert len(f001_a) > 0, "高级工程师应在F001排班（降级用中级预算）"
        assert any(a.level == "中级" for a in f001_a), "应消耗中级预算"
        assert len(result.all_transfers) == 1

    def test_idle_when_no_target(self, rules, calendar):
        # 唯一订单预算耗尽
        o = make_order("F001", domain="信贷", mid=0.0)
        o.remaining = {"高级": 0.0, "中级": 0.0, "初级": 0.0}
        staff_pool = {"甲": make_staff("甲", domain="信贷", level="中级", order_no="F001")}
        result = run_scheduler(
            orders={"F001": o}, staff_pool=staff_pool, calendar=calendar,
            borrow_configs=[], rules=rules,
            start_month=date(2026, 5, 1), end_month=date(2026, 5, 1),
            loader_warnings=[],
        )
        assert date(2026, 5, 1) in staff_pool["甲"].idle_months
        idle_transfers = [t for t in result.all_transfers if t.to_order is None]
        assert len(idle_transfers) == 1

    def test_domain_barrier_prevents_cross_domain(self, rules, calendar):
        orders = {
            "F001": make_order("F001", domain="信贷", mid=0.0),
            "F002": make_order("F002", domain="房改", mid=50.0),  # 房改域
        }
        orders["F001"].remaining = {"高级": 0.0, "中级": 0.0, "初级": 0.0}
        staff_pool = {"甲": make_staff("甲", domain="信贷", level="中级", order_no="F001")}
        result = run_scheduler(
            orders=orders, staff_pool=staff_pool, calendar=calendar,
            borrow_configs=[], rules=rules,
            start_month=date(2026, 5, 1), end_month=date(2026, 5, 1),
            loader_warnings=[],
        )
        # 甲是信贷域，F002是房改，不能转场
        assert date(2026, 5, 1) in staff_pool["甲"].idle_months

    def test_borrow_splits_month(self, rules, calendar):
        orders = {
            "F001": make_order("F001", domain="信贷", mid=50.0),  # 借入订单
            "F002": make_order("F002", domain="房改", mid=50.0),  # 原领域订单
        }
        staff_pool = {"房改甲": make_staff("房改甲", domain="房改", level="中级", order_no="F002")}
        month = date(2026, 5, 1)
        borrows = [BorrowConfig(staff_name="房改甲", from_domain="房改",
                                to_order_no="F001", month=month, days=9)]

        result = run_scheduler(
            orders=orders, staff_pool=staff_pool, calendar=calendar,
            borrow_configs=borrows, rules=rules,
            start_month=month, end_month=month,
            loader_warnings=[],
        )
        a_list = staff_pool["房改甲"].assignments
        borrow_days = sum(a.days for a in a_list if a.is_borrow)
        regular_days = sum(a.days for a in a_list if not a.is_borrow)
        assert borrow_days == 9
        assert regular_days == 19 - 9   # 10天在原领域
        assert len(result.all_transfers) == 0

    def test_data_date_truncates_first_month(self, rules, calendar):
        """起排日截断首月：5.12 起排，5 月只排约 12 天（按 proportional 估算）。"""
        orders = {"F001": make_order("F001", domain="信贷", mid=50.0)}
        staff_pool = {"甲": make_staff("甲", domain="信贷", level="中级", order_no="F001")}
        result = run_scheduler(
            orders=orders, staff_pool=staff_pool, calendar=calendar,
            borrow_configs=[], rules=rules,
            start_month=date(2026, 5, 1), end_month=date(2026, 5, 1),
            loader_warnings=[],
            data_date=date(2026, 5, 12),
        )
        may_days = sum(a.days for a in result.all_assignments if a.month == date(2026, 5, 1))
        assert may_days < 19   # 必小于整月19
        assert may_days > 0
        # 验证 windows 已正确生成且首月是 partial
        assert result.windows[0].is_partial
        assert result.windows[0].start == date(2026, 5, 12)

    def test_end_date_truncates_last_month(self, rules, calendar):
        """结束日截断末月：end_date 5.15 时，5 月只排约前半月。"""
        orders = {"F001": make_order("F001", domain="信贷", mid=50.0)}
        staff_pool = {"甲": make_staff("甲", domain="信贷", level="中级", order_no="F001")}
        result = run_scheduler(
            orders=orders, staff_pool=staff_pool, calendar=calendar,
            borrow_configs=[], rules=rules,
            start_month=date(2026, 5, 1), end_month=date(2026, 5, 1),
            loader_warnings=[],
            end_date=date(2026, 5, 15),
        )
        may_days = sum(a.days for a in result.all_assignments if a.month == date(2026, 5, 1))
        assert may_days < 19
        assert result.windows[0].end == date(2026, 5, 15)
