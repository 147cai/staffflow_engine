"""最新排班表数据组装：按订单编号排序，借还行标记，订单间插空行。"""
from __future__ import annotations
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from ..models import Assignment, Month, Order, Staff

# 标记借还行的哨兵值（exporter 据此设黄色字体）
BORROW_MARKER = "__BORROW__"

# 级别排序权重：高级→中级→初级，未知级别排最后
_LEVEL_ORDER = {"高级": 0, "中级": 1, "初级": 2}


def _level_priority(level_str: str) -> int:
    """从级别字符串中提取排序优先级（高级=0, 中级=1, 初级=2）。
    借还行如"高级（借信贷）"也能正确匹配。
    """
    for lvl, pri in _LEVEL_ORDER.items():
        if level_str.startswith(lvl):
            return pri
    return 99


def build_rows(
    staff_pool: Dict[str, Staff],
    orders: Dict[str, Order],
    months: List[Month],
    calendar=None,
) -> Tuple[List[str], List[list]]:
    """
    返回 (header, rows)。
    借还行的 staff_name 列以 BORROW_MARKER 为前缀，供 exporter 识别并设黄色字体。
    每两个订单组之间插入一行 None（空行）。
    calendar: 若传入，月份标题显示工作日数，如"4月（21）"。
    """
    if calendar is not None:
        month_headers = [f"{m.month}月（{calendar.get_working_days(m)}）" for m in months]
    else:
        month_headers = [f"{m.month}月" for m in months]
    header = ["订单编号", "姓名", "级别"] + month_headers

    # {order_no: [(staff_name, level, {month: days}, is_borrow, effective_level), ...]}
    grouped: Dict[str, List[tuple]] = defaultdict(list)

    for staff in staff_pool.values():
        # 按 (order_no, level, is_borrow) 聚合 assignments
        agg: Dict[Tuple[str, str, bool], Dict[Month, int]] = defaultdict(dict)
        for a in staff.assignments:
            key = (a.order_no, a.level, a.is_borrow)
            agg[key][a.month] = agg[key].get(a.month, 0) + a.days

        for (order_no, level, is_borrow), monthly in agg.items():
            # 该人员在此订单的"本职级别"：遴选清单优先，否则用 base_level
            order = orders.get(order_no)
            wl_level = order.get_whitelist_level(staff.name) if order else None
            effective_level = wl_level or staff.base_level or level
            grouped[order_no].append((staff.name, level, monthly, is_borrow, effective_level))

    rows: List[list] = []
    sorted_orders = sorted(grouped.keys())

    for i, order_no in enumerate(sorted_orders):
        if i > 0:
            rows.append([None] * len(header))   # 订单间空行

        entries = grouped[order_no]
        # 按本职级别排序（高→中→初），同一人的多行不被打散；
        # 同名同本职级别内再按实际消耗级别排（中级行在中级→初级行前面）
        entries.sort(key=lambda x: (_level_priority(x[4]), x[0], _level_priority(x[1]), x[3]))

        for staff_name, level, monthly, is_borrow, effective_level in entries:
            display_name = f"{BORROW_MARKER}{staff_name}" if is_borrow else staff_name
            # 降级消耗时显示"中级→初级"，让HR清楚此人本职级别
            display_level = level if level == effective_level else f"{effective_level}→{level}"
            row = [order_no, display_name, display_level]
            row += [monthly.get(m) for m in months]
            rows.append(row)

    return header, rows
