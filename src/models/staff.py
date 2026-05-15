from __future__ import annotations
from datetime import date
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from .assignment import Assignment, Month, TransferRecord


class Staff(BaseModel):
    model_config = {"frozen": False, "arbitrary_types_allowed": True}

    name: str
    domain: str
    base_level: str

    initial_order_no: Optional[str] = None
    initial_level: Optional[str] = None
    entry_date: Optional[date] = None
    exit_date: Optional[date] = None

    # simulation state (mutated by engine)
    current_order_no: Optional[str] = None
    current_level: Optional[str] = None

    assignments: List[Assignment] = Field(default_factory=list)
    transfers: List[TransferRecord] = Field(default_factory=list)
    idle_months: List[Month] = Field(default_factory=list)
    borrowed_days: Dict[Month, int] = Field(default_factory=dict)

    def is_active(self, month: Month) -> bool:
        month_end = date(month.year, month.month, _last_day(month))
        if self.entry_date and self.entry_date > month_end:
            return False
        if self.exit_date and self.exit_date < month:
            return False
        return True

    def get_available_days(self, month: Month, total_work_days: int, calendar) -> int:
        month_start = month
        month_end = date(month.year, month.month, _last_day(month))
        eff_start = month_start
        eff_end = month_end
        if self.entry_date and self.entry_date > month_start:
            eff_start = self.entry_date
        if self.exit_date and self.exit_date < month_end:
            eff_end = self.exit_date
        if eff_start > eff_end:
            return 0
        if eff_start == month_start and eff_end == month_end:
            return total_work_days
        return calendar.get_working_days_in_range(eff_start, eff_end)

    def get_borrowed_days(self, month: Month) -> int:
        return self.borrowed_days.get(month, 0)

    def set_borrowed_days(self, month: Month, days: int) -> None:
        self.borrowed_days[month] = self.borrowed_days.get(month, 0) + days

    def level_for_order(self, order_no: str, whitelist_level: Optional[str]) -> str:
        if whitelist_level:
            return whitelist_level
        if order_no == self.current_order_no and self.current_level:
            return self.current_level
        return self.base_level


def _last_day(month: Month) -> int:
    import calendar as _cal
    _, d = _cal.monthrange(month.year, month.month)
    return d
