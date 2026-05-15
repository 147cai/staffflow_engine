"""StaffFlow 桌面 GUI — pywebview 入口"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path

import yaml
import webview

# ── 路径（gui.py 与 main.py 同目录）────────────────────
BASE_DIR      = Path(__file__).parent          # staffflow_engine/
CONFIG_DIR    = BASE_DIR / "config"
RUN_CONFIG    = CONFIG_DIR / "run_config.yaml"
CAL_CONFIG    = CONFIG_DIR / "calendar.yaml"
OUTPUT_DIR    = BASE_DIR / "data" / "output"
HTML_FILE     = BASE_DIR / "staffflow_ui_mockup.html"
PYTHON_EXE    = Path(r"C:\Users\nantian\miniforge3\envs\staffflow_engine\python.exe")
ACTIVATE_BAT  = Path(r"C:\Users\nantian\miniforge3\Scripts\activate.bat")
MAIN_PY       = BASE_DIR / "main.py"


class API:
    """暴露给页面 JS 的 Python 方法（通过 window.pywebview.api 调用）。"""

    def __init__(self) -> None:
        self._win: webview.Window | None = None

    def _js(self, expr: str) -> None:
        if self._win:
            self._win.evaluate_js(expr)

    # ── 文件 / 目录选择 ─────────────────────────────────
    def browse_file(self) -> str | None:
        result = self._win.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=("Excel 文件 (*.xlsx)", "所有文件 (*.*)"),
        )
        return result[0] if result else None

    def browse_folder(self) -> str | None:
        result = self._win.create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result else None

    # ── 运行配置 ────────────────────────────────────────
    def get_run_config(self) -> dict:
        with open(RUN_CONFIG, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {
            "start_date": str(data.get("start_date") or ""),
            "end_date":   str(data.get("end_date")   or ""),
        }

    def save_run_config(self, start_date: str, end_date: str) -> bool:
        data = {
            "start_date": start_date.strip() or None,
            "end_date":   end_date.strip()   or None,
        }
        with open(RUN_CONFIG, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return True

    # ── 工作日历 ────────────────────────────────────────
    def get_calendar(self) -> str:
        with open(CAL_CONFIG, encoding="utf-8") as f:
            return f.read()

    def save_calendar(self, content: str) -> bool:
        yaml.safe_load(content)  # 格式校验，非法 YAML 会抛异常
        with open(CAL_CONFIG, "w", encoding="utf-8") as f:
            f.write(content)
        return True

    # ── 生成排班 ────────────────────────────────────────
    def generate(self, input_path: str, output_dir: str) -> bool:
        """后台线程运行引擎，通过 JS 回调推送进度。立即返回 True。"""

        def run() -> None:
            try:
                out_dir = (
                    output_dir.strip()
                    if output_dir and output_dir.strip()
                    else str(OUTPUT_DIR)
                )
                # shell=True 让 Python 直接把字符串交给 cmd.exe /c，
                # 避免 list2cmdline 对含引号路径做双重转义导致命令损坏。
                # chcp 65001 确保 activate.bat 的输出也是 UTF-8。
                cmd_str = (
                    f'chcp 65001 > nul'
                    f' & call "{ACTIVATE_BAT}" staffflow_engine'
                    f' & "{PYTHON_EXE}" -u "{MAIN_PY}"'
                    f' --input "{input_path}"'
                    f' --output-dir "{out_dir}"'
                    f' --config-dir "{CONFIG_DIR}"'
                )
                proc = subprocess.Popen(
                    cmd_str,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(BASE_DIR),
                )

                out_file: str | None = None
                tail: list[str] = []          # 保留最后几行，报错时显示
                for raw in proc.stdout:
                    line = raw.rstrip()
                    if not line:
                        continue
                    tail = (tail + [line])[-6:]   # 滚动保留最近 6 行
                    if line.startswith("输出文件："):
                        out_file = line.split("：", 1)[1].strip()
                    msg = line.split(": ", 1)[-1] if ": " in line else line
                    self._js(f"onProgressLog({json.dumps(msg)})")

                proc.wait()
                if proc.returncode == 0:
                    fname = Path(out_file).name if out_file else "排班预测.xlsx"
                    self._js(
                        f"onGenerateSuccess({json.dumps(fname)}, {json.dumps(out_file or '')})"
                    )
                else:
                    detail = " | ".join(tail) if tail else "（无输出，可能是启动失败）"
                    self._js(f"onGenerateError({json.dumps(f'code={proc.returncode}: {detail}')})")

            except Exception as exc:
                self._js(f"onGenerateError({json.dumps(str(exc))})")

        threading.Thread(target=run, daemon=True).start()
        return True


def main() -> None:
    api = API()
    win = webview.create_window(
        title="StaffFlow 排班工具",
        url=HTML_FILE.as_uri(),
        js_api=api,
        width=1000,
        height=700,
        resizable=False,
        min_size=(1000, 700),
    )
    api._win = win
    webview.start()


if __name__ == "__main__":
    main()
