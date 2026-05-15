"""命令行参数解析与全流程调度。"""
from __future__ import annotations
import argparse
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

from .engine.rules import RulesConfig
from .engine.scheduler import run as run_scheduler
from .io.exporter import export
from .io.loader import load_all
from .io.validator import validate_all, ValidationError
from .utils import month_range


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="StaffFlow 排班预测工具")
    p.add_argument("--input", required=True, help="输入Excel路径")
    p.add_argument("--output-dir", default="data/output", help="输出目录")
    p.add_argument("--config-dir", default="config", help="配置文件目录")
    p.add_argument("--start-date", default=None,
                   help="排班起始日期 YYYY.M.D（优先于 run_config.yaml）")
    p.add_argument("--end-date", default=None,
                   help="排班结束月份 YYYY.M.D（留空则自动推断）")
    p.add_argument("--debug", action="store_true", help="开启 DEBUG 日志")
    return p.parse_args(argv)


def setup_logging(debug: bool, log_dir: str) -> None:
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"run_{ts}.log")
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
    )


def _parse_date_str(s: str) -> date:
    """解析 YYYY.M.D 或 YYYY-MM-DD 或 YYYY.M 格式，保留完整日期（精确到天）。
    若未指定日则默认为1日。
    """
    s = s.strip()
    sep = "." if "." in s else "-"
    parts = s.split(sep)
    year, month = int(parts[0]), int(parts[1])
    day = int(parts[2]) if len(parts) >= 3 else 1
    return date(year, month, day)


def _load_run_config(cfg_dir: Path) -> dict:
    path = cfg_dir / "run_config.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _infer_end_month(orders: dict) -> date:
    ends = [o.end_date for o in orders.values()]
    if not ends:
        today = date.today()
        return date(today.year + 1, today.month, 1)
    latest = max(ends)
    return date(latest.year, latest.month, 1)


def main(argv=None) -> int:
    args = parse_args(argv)
    setup_logging(args.debug, "logs")
    log = logging.getLogger(__name__)

    cfg_dir = Path(args.config_dir)
    run_cfg = _load_run_config(cfg_dir)

    schema_path = str(cfg_dir / "input_schema.yaml")
    calendar_path = str(cfg_dir / "calendar.yaml")
    rules_path = str(cfg_dir / "rules.yaml")

    with open(rules_path, encoding="utf-8") as f:
        rules_cfg = yaml.safe_load(f)
    rules = RulesConfig(rules_cfg)

    log.info("Loading input: %s", args.input)
    try:
        loaded = load_all(args.input, schema_path, calendar_path)
    except Exception as e:
        log.error("加载输入文件失败: %s", e)
        return 1

    try:
        validate_all(loaded.orders, loaded.staff_pool, loaded.calendar,
                     loaded.borrow_configs, loaded.warnings)
    except ValidationError as e:
        log.error("数据校验失败: %s", e)
        return 1

    # 起始日期：命令行 > run_config.yaml > 报错提示
    raw_start = args.start_date or str(run_cfg.get("start_date") or "")
    if not raw_start:
        log.error(
            "未指定排班起始日期。请在 config/run_config.yaml 中设置 start_date（格式 YYYY.M.D），"
            "或通过 --start-date 参数传入。"
        )
        return 1
    # data_date 保留完整日期（含日），用于输出表格的列标题
    # start_month 始终取当月1日，用于月度排班循环
    data_date = _parse_date_str(raw_start)
    start_month = date(data_date.year, data_date.month, 1)

    raw_end = args.end_date or str(run_cfg.get("end_date") or "")
    end_month = _parse_date_str(raw_end) if raw_end else _infer_end_month(loaded.orders)
    end_month = date(end_month.year, end_month.month, 1)

    log.info("排班区间：%s ~ %s（数据基准日：%s）", start_month, end_month, data_date)
    result = run_scheduler(
        orders=loaded.orders,
        staff_pool=loaded.staff_pool,
        calendar=loaded.calendar,
        borrow_configs=loaded.borrow_configs,
        rules=rules,
        start_month=start_month,
        end_month=end_month,
        loader_warnings=loaded.warnings,
    )

    os.makedirs(args.output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(args.output_dir, f"排班预测_{ts}.xlsx")

    export(result, rules, start_month, end_month, out_path, loaded.warnings,
           loaded.calendar, data_date)
    log.info("Done. Output: %s", out_path)
    print(f"输出文件：{out_path}")
    return 0
