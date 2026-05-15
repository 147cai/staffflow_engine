"""加载器集成测试：用真实模板文件验证解析正确性。"""
from __future__ import annotations
from datetime import date
import pytest

from src.io.loader import load_all
from src.io.validator import validate_all, ValidationError

_EXCEL = r"C:\01_NanTian\项目\排班\相关文件\深开排班表生成模板v0.2.xlsx"
_BASE = r"C:\01_NanTian\项目\排班\staffflow_engine"
_SCHEMA = f"{_BASE}/config/input_schema.yaml"
_CALENDAR = f"{_BASE}/config/calendar.yaml"


@pytest.fixture(scope="module")
def loaded():
    return load_all(_EXCEL, _SCHEMA, _CALENDAR)


class TestLoaderBasics:
    def test_loads_five_active_orders(self, loaded):
        assert len(loaded.orders) == 5

    def test_order_numbers_correct(self, loaded):
        nos = set(loaded.orders.keys())
        assert "FTZB250108/01-F150053" in nos
        assert "FTZB250108/01-F150159" in nos

    def test_orders_have_domain(self, loaded):
        for no, o in loaded.orders.items():
            assert o.domain, f"订单 {no} 领域为空"

    def test_order_budgets_positive(self, loaded):
        for no, o in loaded.orders.items():
            total = sum(o.initial_budget.values())
            assert total > 0, f"订单 {no} 预算全为0"

    def test_loads_staff_pool(self, loaded):
        assert len(loaded.staff_pool) == 96

    def test_staff_have_domain(self, loaded):
        for name, s in loaded.staff_pool.items():
            assert s.domain, f"人员 {name} 领域为空"

    def test_whitelist_loaded_for_f150159(self, loaded):
        f159 = next(
            (o for no, o in loaded.orders.items() if "F150159" in no), None)
        assert f159 is not None
        assert f159.whitelist is not None
        assert len(f159.whitelist) > 0

    def test_borrow_config_loaded(self, loaded):
        # 模板中有部分借还配置（非全部有效）
        assert isinstance(loaded.borrow_configs, list)

    def test_calendar_has_required_months(self, loaded):
        required = [date(2026, m, 1) for m in range(5, 13)]
        required += [date(2027, m, 1) for m in range(1, 4)]
        for m in required:
            assert m in loaded.calendar.work_days, f"缺少月份 {m}"

    def test_remaining_budget_is_initial_minus_consumed(self, loaded):
        for no, o in loaded.orders.items():
            for lvl in o.initial_budget:
                expected = round(
                    o.initial_budget.get(lvl, 0) - o.consumed_before.get(lvl, 0), 2)
                assert o.remaining.get(lvl, 0) == pytest.approx(expected), \
                    f"{no} {lvl} remaining 计算有误"


class TestLoaderEdgeCases:
    def test_strip_whitespace_in_names(self, loaded):
        for name in loaded.staff_pool:
            assert name == name.strip(), f"人员名称有前后空格: '{name}'"

    def test_no_duplicate_staff(self, loaded):
        assert len(loaded.staff_pool) == len(set(loaded.staff_pool.keys()))

    def test_borrow_days_not_exceed_month(self, loaded):
        for b in loaded.borrow_configs:
            month_days = loaded.calendar.get_working_days(b.month)
            if month_days > 0:
                assert b.days <= month_days, \
                    f"{b.staff_name} {b.month} 借用天数 {b.days} > 月工作日 {month_days}"

    def test_validation_passes(self, loaded):
        warnings = list(loaded.warnings)
        try:
            validate_all(loaded.orders, loaded.staff_pool, loaded.calendar,
                         loaded.borrow_configs, warnings)
        except ValidationError as e:
            pytest.fail(f"Validation failed: {e}")
