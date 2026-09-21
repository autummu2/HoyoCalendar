"""自动化维护入口：提取新活动 + 校准已有条目 + 应用落盘。

供外部调用，三种方式等价：
- python maintain.py
- maintain.bat（Windows 双击 / 任务计划）
- 编辑器 main.py 的「自动化维护」按键

先 chdir 到本脚本目录（run_pipeline / apply_events 用相对路径读写 extracted_full.json），
再依次执行 run_pipeline.run（提取 + 推理 + 校准，写 extracted_full.json）
与 apply_events.main（把新活动写进 data/events/genshin-impact.yaml）。

全程 stdout 追加写入 logs/YYYY-MM-DD.log（UTF-8）。自动化运行无人值守，
日志是事后核查「那天到底干了什么」的唯一依据——尤其是正文接口被风控时，
本轮结果会静默变少，只有看日志里的「正文抓取」与「跳过（日期不完整）」才能分辨。
"""
import datetime
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import run_pipeline
import apply_events


class _Tee:
    """把标准输出同时写到日志文件。isatty/encoding 转发给原流，避免影响 rich 的终端判定。"""

    def __init__(self, stream, log):
        self._stream = stream
        self._log = log

    def write(self, text):
        self._stream.write(text)
        self._log.write(text)
        return len(text)

    def flush(self):
        self._stream.flush()
        self._log.flush()

    def isatty(self):
        return self._stream.isatty()

    @property
    def encoding(self):
        return self._stream.encoding


def main():
    os.makedirs("logs", exist_ok=True)
    path = os.path.join("logs", f"{datetime.date.today():%Y-%m-%d}.log")
    with open(path, "a", encoding="utf-8") as log:
        log.write(f"\n=== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} 运行 ===\n")
        log.flush()
        real_stdout = sys.stdout
        sys.stdout = _Tee(real_stdout, log)
        try:
            run_pipeline.run()
            apply_events.main()
        finally:
            sys.stdout = real_stdout


if __name__ == "__main__":
    main()
