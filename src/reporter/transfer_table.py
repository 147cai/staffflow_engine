"""人员转场日期表数据组装。"""
from __future__ import annotations
from typing import Dict, List, Tuple

from ..models import Staff, TransferRecord


def build_rows(staff_pool: Dict[str, Staff]) -> Tuple[List[str], List[list]]:
    header = ["姓名", "所在领域", "当前/原订单", "转场目标订单", "预测转场日期", "转场后当月剩余工作日", "原因"]
    rows = []
    for staff in sorted(staff_pool.values(), key=lambda s: s.name):
        for t in staff.transfers:
            to_order = t.to_order if t.to_order else "待定（无单可排）"
            rows.append([
                t.staff_name,
                t.domain,
                t.from_order,
                to_order,
                t.transfer_date,        # date 对象，exporter 负责格式化
                t.remaining_days_in_month,
                t.reason,
            ])
    return header, rows
