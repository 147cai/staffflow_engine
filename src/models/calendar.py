from __future__ import annotations
import calendar as _cal
from datetime import date, timedelta
from typing import Dict, Set
from pydantic import BaseModel, Field
from .assignment import Month


class WorkCalendar(BaseModel):
    work_days: Dict[Month, int]
    # 法定节假日（非工作日）：配置后启用精确逐日计算
    holidays: Set[date] = Field(default_factory=set)
    # 补班日（周末需要上班的日子）
    makeup_days: Set[date] = Field(default_factory=set)

    def get_working_days(self, month: Month) -> int:
        return self.work_days.get(month, 0)

    def get_working_days_in_range(self, start: date, end: date) -> int:
        """计算日期区间内的工作日数。
        若配置了 holidays/makeup_days，使用精确逐日计算；否则按比例估算。
        """
        if start > end:
            return 0
        if self.holidays or self.makeup_days:
            return self._count_exact(start, end)
        return self._count_proportional(start, end)

    def _count_exact(self, start: date, end: date) -> int:
        """逐日精确计算工作日：跳过周末和节假日，补班日计入。"""
        count = 0
        cur = start
        while cur <= end:
            if cur in self.makeup_days:
                count += 1          # 补班日（周末上班）
            elif cur.weekday() < 5 and cur not in self.holidays:
                count += 1          # 普通工作日（非节假日）
            cur += timedelta(days=1)
        return count

    def _count_proportional(self, start: date, end: date) -> int:
        """按月总工作日比例估算（不需要节假日配置时的后备方案）。"""
        total = 0
        cur = date(start.year, start.month, 1)
        while cur <= date(end.year, end.month, 1):
            _, days_in_month = _cal.monthrange(cur.year, cur.month)
            m_start = cur
            m_end = date(cur.year, cur.month, days_in_month)
            eff_start = max(start, m_start)
            eff_end = min(end, m_end)
            if eff_start <= eff_end:
                span = (eff_end - eff_start).days + 1
                work = self.work_days.get(cur, 0)
                total += round(work * span / days_in_month)
            cur = (m_end + timedelta(days=1))
            cur = date(cur.year, cur.month, 1)
        return total

    def month_end(self, month: Month) -> date:
        _, d = _cal.monthrange(month.year, month.month)
        return date(month.year, month.month, d)
