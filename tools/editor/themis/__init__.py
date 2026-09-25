"""未定事件簿（tears-of-themis）活动维护管线。

与 genshin/、starrail/、zenless/ 并列的第四条线：同一套 common/（yaml_io / keys /
colors / body_cache），各自的 rules.py + parse.py + pipeline.py。

    from themis import run            # 抓取 → 解析 → extracted_tea.json
    python themis/selftest.py         # 离线自检，不联网
    python themis/pipeline.py --dry-run   # 联网抓取，只打印判定表不落盘

**没有 calibrate**（裁定 19）：未定只增不改，落盘的日期不再被自动流程改写。
"""

from themis import parse, rules  # noqa: F401
from themis.pipeline import OUT_FILE, run  # noqa: F401

__all__ = ["run", "parse", "rules", "OUT_FILE"]
