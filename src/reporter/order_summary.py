"""各订单排班后的情况表数据组装。"""
from __future__ import annotations
from datetime import date
from typing import Dict, List, Optional, Tuple

from ..models import Month, Order

# (order_no, first_data_row_1based, last_data_row_1based)
OrderGroup = Tuple[str, int, int]


def build_rows(
    orders: Dict[str, Order],
    months: List[Month],
    work_days_per_month: int = 22,
    data_date: Optional[date] = None,
) -> Tuple[List[str], List[list], List[OrderGroup]]:
    """返回 (header, rows, order_groups)。

    order_groups 描述每个订单在工作表中的行范围（1-based，header占第1行）。
    data_date: 输入数据的基准日期，用于列标题（如"4.10日数据"）；None时用今天。
    """
    label_date = data_date if data_date is not None else date.today()
    data_date_label = f"{label_date.month}.{label_date.day}日数据"
    header = [
        "合同编号",
        "项目编号",
        "合同名称",
        "资质级别",
        "合同工作量",
        data_date_label,
        "当前考勤缺口（负值代表超）",
        "预测人月",
        "合同计划考勤完成人月",
    ]

    rows: List[list] = []
    order_groups: List[OrderGroup] = []
    next_row = 2  # header 在第1行，数据从第2行开始

    for no in sorted(orders):
        order = orders[no]
        # 始终显示全部三个级别，即使预算为0（高级可能以中级/初级身份出现在此订单）
        levels = ["高级", "中级", "初级"]
        if not any(order.initial_budget.get(lvl, 0) > 0 or
                   order.consumed_before.get(lvl, 0) > 0
                   for lvl in levels):
            continue

        group_start = next_row
        first = True
        for level in levels:
            budget = round(order.initial_budget.get(level, 0), 2)
            consumed_hist = round(order.consumed_before.get(level, 0), 2)
            current_gap = round(budget - consumed_hist, 2)
            predicted = round(
                sum(order.monthly_consumption.get(m, {}).get(level, 0) for m in months), 2
            )
            final_completion = round(current_gap - predicted, 2)

            rows.append([
                "",                          # 合同编号（留空）
                no,                          # 项目编号
                order.name if first else "", # 合同名称（仅首行）
                level,                       # 资质级别
                budget,                      # 合同工作量
                consumed_hist,               # [date]日数据
                current_gap,                 # 当前考勤缺口
                predicted,                   # 预测人月
                final_completion,            # 合同计划考勤完成人月
            ])
            next_row += 1
            first = False

        order_groups.append((no, group_start, next_row - 1))

    return header, rows, order_groups
