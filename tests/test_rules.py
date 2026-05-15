"""规则约束测试：领域壁垒、白名单、降级。"""
from __future__ import annotations
from datetime import date
import pytest

from src.engine.rules import RulesConfig
from tests.conftest import make_order, make_staff, _DEFAULT_RULES


@pytest.fixture
def rules():
    return RulesConfig(_DEFAULT_RULES)


class TestDomainBarrier:
    def test_same_domain_allowed(self, rules):
        order = make_order("F001", domain="信贷")
        staff = make_staff("甲", domain="信贷")
        assert rules.can_enter_order(staff, order)

    def test_cross_domain_blocked(self, rules):
        order = make_order("F001", domain="房改")
        staff = make_staff("甲", domain="信贷")
        assert not rules.can_enter_order(staff, order)

    def test_dynamic_domain_name(self, rules):
        order = make_order("F001", domain="新零售")
        staff = make_staff("甲", domain="新零售")
        assert rules.can_enter_order(staff, order)


class TestWhitelist:
    def test_whitelist_blocks_unlisted_staff(self, rules):
        order = make_order("F001", domain="信贷", whitelist={"张三": "高级"})
        staff = make_staff("李四", domain="信贷")
        assert not rules.can_enter_order(staff, order)

    def test_whitelist_allows_listed_staff(self, rules):
        order = make_order("F001", domain="信贷", whitelist={"张三": "高级"})
        staff = make_staff("张三", domain="信贷")
        assert rules.can_enter_order(staff, order)

    def test_whitelist_overrides_level(self, rules):
        order = make_order("F001", domain="信贷", whitelist={"张三": "高级"})
        staff = make_staff("张三", domain="信贷", level="中级")
        lvl = rules.effective_level(staff, order)
        assert lvl == "高级"    # 白名单覆盖原始级别

    def test_no_whitelist_uses_base_level(self, rules):
        order = make_order("F001", domain="信贷")
        staff = make_staff("张三", domain="信贷", level="初级")
        lvl = rules.effective_level(staff, order)
        assert lvl == "初级"


class TestDowngrade:
    def test_downgrade_finds_next_level(self, rules):
        order = make_order("F001", domain="信贷", senior=0.0, mid=5.0)
        order.remaining["高级"] = 0.0
        staff = make_staff("甲", domain="信贷", level="高级")
        lvl = rules.find_usable_level(staff, order, date(2026, 5, 1))
        assert lvl == "中级"

    def test_no_downgrade_when_disabled(self):
        cfg = {**_DEFAULT_RULES, "downgrade": {"enabled": False, "path": ["高级", "中级", "初级"]}}
        rules_no_dg = RulesConfig(cfg)
        order = make_order("F001", domain="信贷", senior=0.0, mid=5.0)
        order.remaining["高级"] = 0.0
        staff = make_staff("甲", domain="信贷", level="高级")
        lvl = rules_no_dg.find_usable_level(staff, order, date(2026, 5, 1))
        assert lvl is None

    def test_returns_none_when_all_exhausted(self, rules):
        order = make_order("F001", domain="信贷", senior=0.0, mid=0.0, junior=0.0)
        order.remaining = {"高级": 0.0, "中级": 0.0, "初级": 0.0}
        staff = make_staff("甲", domain="信贷", level="高级")
        assert rules.find_usable_level(staff, order, date(2026, 5, 1)) is None
