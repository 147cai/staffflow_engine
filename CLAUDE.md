# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

- Python 3.11.15 in conda env `staffflow_engine`
- Python path: `C:\Users\nantian\miniforge3\envs\staffflow_engine\python.exe`
- **Must activate conda env before running** — direct Python calls fail with DLL errors

## Commands

**Run the tool:**
```
cmd /c "chcp 65001 & call C:\Users\nantian\miniforge3\Scripts\activate.bat staffflow_engine & python main.py --input <Excel路径>"
```
Or using `run_config.yaml` for start_date:
```
cmd /c "chcp 65001 & call C:\Users\nantian\miniforge3\Scripts\activate.bat staffflow_engine & python main.py --input <Excel路径> --start-date 2026.5.12"
```

**Run all tests:**
```powershell
Set-Location "C:\01_NanTian\项目\排班\staffflow_engine"
& cmd /c "chcp 65001 & call C:\Users\nantian\miniforge3\Scripts\activate.bat staffflow_engine & python -m pytest tests/ -v --tb=short 2>&1"
```

**Run a single test:**
```
... & python -m pytest tests/test_engine.py::TestSchedulerIntegration::test_basic_schedule_no_transfer -v
```

## Architecture

### Data flow
```
Excel (6 sheets)  →  loader.py  →  [Order, Staff, BorrowConfig, WorkCalendar]
                                          ↓
                              scheduler.py (month loop)
                              ├── borrow_handler.py   (apply borrows first)
                              └── _schedule_staff_month()
                                  ├── downgrade loop in current order
                                  ├── transfer_finder.py  (find next order)
                                  └── record Assignment / TransferRecord
                                          ↓
                              exporter.py  →  4-sheet Excel output
```

### Key models (`src/models/`)
- **`Order`** — budget per level (`initial_budget`, `remaining`, `consumed_before`), `monthly_consumption` accumulates as scheduling runs. `is_active()` checks date range AND any remaining > threshold.
- **`Staff`** — tracks `current_order_no`, `current_level`, `assignments[]`, `transfers[]`, `idle_months[]`. `entry_date`/`exit_date` control availability.
- **`WorkCalendar`** — `get_working_days(month)` from `work_days` dict; `get_working_days_in_range(start, end)` does exact day-by-day counting using `holidays` and `makeup_days` sets (falls back to proportional if both sets are empty).
- **`Assignment`** — one record per (staff, order, month); `is_borrow=True` for cross-domain borrow rows.
- **`TransferRecord`** — written when staff changes order or goes idle.

### Core scheduling logic (`src/engine/scheduler.py`)
Each month, for each active staff member:
1. `apply_borrows` runs first — locks borrow days, deducts from target order budget.
2. Current order: loop through the full downgrade path (`高级→中级→初级`) starting at the staff's effective level. Only moves to transfer after ALL reachable levels in the current order are exhausted (threshold = 0.05 人月).
3. Transfer: `transfer_finder.find_target()` scores candidate orders by continuity bonus + urgency + duration. Domain must match; whitelist respected.
4. If no target: staff goes idle.

### Rules (`config/rules.yaml` → `src/engine/rules.py`)
- `exhaustion_threshold: 0.05` — remaining ≤ 0.05 人月 is treated as exhausted
- `work_days_per_month: 22` — used for 人月↔天 conversion (1 人月 = 22 天)
- `downgrade.path: [高级, 中级, 初级]` — senior can use mid/junior budget; mid can use junior budget
- `domain.strict: true` — cross-domain transfers blocked (except explicit borrow configs)
- `scoring.continuity_bonus: 1000` — strongly prefers keeping staff on current order

### Configuration files (`config/`)
| File | Purpose | Who updates |
|------|---------|------------|
| `run_config.yaml` | `start_date` / `end_date` for each run | HR every Monday |
| `calendar.yaml` | Monthly work days + holidays + makeup days | HR annually |
| `input_schema.yaml` | Excel sheet names and column name mappings | Dev when Excel format changes |
| `rules.yaml` | Business rule parameters | Dev |

### Input Excel sheets (mapped in `input_schema.yaml`)
1. **订单清单** — orders with budget (高/中/初 人月) and domain
2. **订单当前工作量** — already-consumed 人月 per order per level
3. **当前在岗人员清单** — all staff with domain
4. **当前订单人员清单** — staff↔order assignments with entry/exit dates
5. **遴选清单\_\<订单号\>** — whitelist sheets (auto-detected by prefix); whitelist overrides staff level
6. **跨领域借还配置** — optional; specifies cross-domain borrow (name, to_order, month, days)

### Output Excel sheets
1. **各订单排班后的情况表** — budget consumed vs predicted per order per level; column header shows `data_date` (e.g. "5.12日数据")
2. **最新排班表** — month columns with work-day count (e.g. "5月（19）"); sorted 高级→中级→初级 within each order; borrow rows in yellow font
3. **人员转场日期表** — when each person transfers and to which order
4. **预警说明** — budget warnings + idle staff + loader errors

### Reporter modules (`src/reporter/`)
- `order_summary.build_rows()` — always emits all 3 level rows per order (even if budget=0), filters only if the entire order has zero budget and zero consumed
- `schedule_table.build_rows()` — `BORROW_MARKER` prefix on staff_name signals exporter to apply yellow font
- `transfer_table.build_rows()` — straightforward flattening of `staff.transfers`

### Adding a new order
Add a row to the **订单清单** sheet with status "进行中" — no code changes needed.

### Adding borrow config
Add rows to the **跨领域借还配置** sheet. If total days exceed one month's work days, `loader.py` automatically splits across consecutive months.

## Testing

Tests use `conftest.make_order()` and `conftest.make_staff()` helpers. When testing transfer scenarios, explicitly set both `initial_budget` and `remaining` on the order — `model_post_init` sets `remaining` from budget minus consumed, but tests that call `run_scheduler` need explicit exhaustion states.

The `conftest.calendar` fixture uses simple static work_days dict (no holidays/makeup_days), so `get_working_days_in_range` uses proportional calculation in tests — this is intentional for test simplicity.
