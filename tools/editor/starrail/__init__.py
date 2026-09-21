"""崩坏：星穹铁道（honkai-star-rail）的自动化维护。

与原神侧（genshin/）并列的一套实现，因为两边的公告格式与版本规律都不同
（见 rules.py）。共用的底层在 common/：yaml_io / keys / calibrate / extractor /
bilibili / colors。

- rules.py    常量：抓取参数、段落名、标题格式、颜色。差异都集中在这里
- parse.py    纯函数解析层，不联网不读写文件，由 selftest.py 用真实公告 fixtures 断言
- pipeline.py 编排：抓取 → 解析 → 校准 → 写 extracted_hsr.json
- selftest.py 离线自检（python starrail/selftest.py）

包内模块之间一律写 `from starrail import parse`，不靠 sys.path 的副作用。
"""

from starrail import parse, rules  # noqa: F401
from starrail.pipeline import OUT_FILE, run  # noqa: F401

__all__ = ["run", "parse", "rules", "OUT_FILE"]
