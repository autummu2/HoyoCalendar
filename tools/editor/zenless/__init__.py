"""绝区零（zenless-zone-zero）活动维护管线。

与 genshin/、starrail/、themis/ 并列的一条线：同一套 common/（yaml_io / keys / calibrate /
colors / bilibili），各自的 rules.py + parse.py + pipeline.py。

    from zenless import run          # 抓取 → 解析 → 校准 → extracted_zzz.json
    python zenless/selftest.py       # 离线自检，不联网
"""

from zenless import inference, parse, rules  # noqa: F401
from zenless.pipeline import OUT_FILE, run  # noqa: F401

__all__ = ["run", "parse", "rules", "inference", "OUT_FILE"]
