from __future__ import annotations
from datetime import date
from typing import Optional
from pydantic import BaseModel

# Month convention: date with day=1
Month = date


class Assignment(BaseModel):
    model_config = {"frozen": False}

    staff_name: str
    order_no: str
    level: str          # 高级 / 中级 / 初级
    month: Month
    days: int
    is_borrow: bool = False
    note: Optional[str] = None


class TransferRecord(BaseModel):
    model_config = {"frozen": False}

    staff_name: str
    from_order: str
    to_order: Optional[str]         # None → 无单可排（闲置）
    transfer_date: date             # 精确到天
    remaining_days_in_month: int    # 转场当月剩余工作日
    domain: str
    reason: str
