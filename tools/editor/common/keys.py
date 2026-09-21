"""活动条目的去重主键（唯一身份）。

「两个条目是不是同一个活动」只由主键决定，与日期无关——日期是**值**，会被校准修改；
主键是**身份**，一旦确定就不再变。混用两者会导致：日期一改，旧条目认不出来 → 重复插入。

主键只取不含解析假设的字段。标题格式会随版本变（武器池 7.0 是
`祈愿：「长柄武器·血染荒城」…`，7.1 变成 `「神铸赋形」祈愿：…`），所以能不用
括号解析就不用：

  卡池 / 常规活动 / 版本大活动 / 大月卡 / 网页活动 → 完整标题
  幽境危战                                        → 米游社公告 post_id（标题每期一字不变）
  版本更新 / 前瞻直播                              → (类型, 版本号)
  深境螺旋 / 幻想真境剧诗                          → (标题, 开始日期)（无公告，标题自带 MMDD，带年份防跨年撞）

版本类事件另加「±7 天内同类型即同一事件」的日期兜底：inference 的版本号是朴素
+0.1 预测（`_version_number`），且标题一旦生成就不再改号，所以版本号可能预测错；
此时主键失配，靠日期兜底仍能认出是同一事件而不是插一条重复。
"""

from __future__ import annotations

import datetime
import re

# 标题完全不变、只能靠公告 id 区分的事件
POST_ID_KEYED_TITLES = {"「幽境危战」"}

# 标题自带 MMDD、无公告的周期性事件（主键需带日期）
DATED_KEYED_PREFIXES = ("深境螺旋", "幻想真境剧诗")

# 版本类事件：主键用版本号
VERSION_KEYED_TYPES = {"版本更新", "前瞻直播"}

# 版本号预测错时，同类型日期相差不超过这个天数视为同一事件
VERSION_TOLERANCE_DAYS = 7


def version_of(title: str) -> str | None:
    """取标题里的版本号：「《原神》7.1 版本「往冥府的安魂歌」停服更新」→ '7.1'。

    兼容带空格（7.1 版本）与不带空格（7.0版本）两种写法。
    """
    m = re.search(r"(\d+)\.(\d+)\s*版本", title or "")
    return f"{m.group(1)}.{m.group(2)}" if m else None


def post_id_of(event: dict) -> str | None:
    """取米游社公告 id：优先 post_id 字段，否则从 source_url 里解析。"""
    pid = event.get("post_id")
    if pid:
        return str(pid)
    m = re.search(r"/article/(\d+)", event.get("source_url") or "")
    return m.group(1) if m else None


def event_key(event: dict) -> tuple | None:
    """返回条目的去重主键；身份判不出来时返回 None（调用方需容错）。"""
    etype = event.get("type", "")
    title = event.get("title", "")

    if etype in VERSION_KEYED_TYPES:
        ver = version_of(title)
        return (etype, "v", ver) if ver else None

    if title in POST_ID_KEYED_TITLES:
        pid = post_id_of(event)
        return (etype, "post", pid) if pid else None

    if title.startswith(DATED_KEYED_PREFIXES):
        return (etype, title, event.get("start_date") or "")

    return (etype, title)


def _date(value) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def find_duplicate(candidate: dict, existing: list[dict]) -> dict | None:
    """在 existing 里找与 candidate 同身份的条目，没有则返回 None。

    先按主键精确匹配；版本类事件主键失配时，再看同类型 7 天内有无既有条目。
    """
    key = event_key(candidate)
    if key is not None:
        for e in existing:
            if event_key(e) == key:
                return e

    if candidate.get("type") in VERSION_KEYED_TYPES:
        d = _date(candidate.get("start_date"))
        if d:
            for e in existing:
                if e.get("type") != candidate.get("type"):
                    continue
                ed = _date(e.get("start_date"))
                if ed and abs((ed - d).days) <= VERSION_TOLERANCE_DAYS:
                    return e
    return None
