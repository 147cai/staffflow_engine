from __future__ import annotations
from pydantic import BaseModel
from .assignment import Month


class BorrowConfig(BaseModel):
    staff_name: str
    from_domain: str
    to_order_no: str    # 完整订单号
    month: Month        # 发生月份（day=1）
    days: int           # 借用工作日天数
