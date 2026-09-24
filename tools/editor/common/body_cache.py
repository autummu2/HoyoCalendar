"""公告正文的本机缓存：同一篇公告在 TTL 内只抓一次。

请求数正是米游社风控的主因（`retcode 1034`，见 extractor.fetch_post 的说明），而管线里
有一批公告是**每轮都要读**的：版本更新说明（版本周期、高难期名、下版本日期都在里面）、
卡池（5 星名只写在正文里）、以及正文里挂着多条活动的活动公告（已落盘的按 audited 的
`waiting` 再审，见下）。这些正文发布之后基本不变，所以按 post_id 存在本机、TTL 内直接
复用——请求数由「每篇每轮一次」降到「稳态 0」（命中缓存的那几篇不计请求）。

为什么是 TTL 而不是永久（2026-09-22 定）：公告会被**事后编辑**——补录活动、订正日期，
本仓库的订正机制（calibrate.correct_from_candidates）就是为这种编辑准备的。14 天既挡住
绝大部分重复请求，又让编辑后的版本最多两周内被读回来。缓存目录不进仓库。

audited.json 记「哪几篇正文审过了、审出什么」，只给**已落盘**的公告用：那批公告的正文本来
会被预筛跳过，而「一帖多活动」的公告恰恰要在正文里才能发现被埋的活动（见 starrail.parse.
parse_activity_bodies）。每篇两个字段：

- `date`：上次审读日。记的是**尝试**而不是成功——抓失败时也记下来，否则风控期间每轮都会
  重试同一批公告，把风控加码（正文抓不到的后果见 keys.likely_recorded 的说明）。
- `waiting`：这篇里**还有块的日期解不出来**（多半在等版本周期表，如「命运契约•再启」等
  4.6；一条都没解析出来的残页也算）。只有为真才值得再读一次；全部块都落盘了就按原神那样
  跳过，连 TTL 都不用等（2026-09-22 定）。判据是派生的——「这篇还有没啃下来的块」，
  不需要任何名单。
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
BODIES_DIR = CACHE_DIR / "bodies"
AUDITED_FILE = CACHE_DIR / "audited.json"

# 正文复用天数。与 audited 的 `date` 共用：都是「多久之后值得再花一次请求」。
TTL_DAYS = 14


def _today() -> datetime.date:
    return datetime.date.today()


def _stale(fetched_at: str | None) -> bool:
    try:
        when = datetime.date.fromisoformat(str(fetched_at))
    except (TypeError, ValueError):
        return True
    return (_today() - when).days >= TTL_DAYS


def _path(post_id) -> Path:
    return BODIES_DIR / f"{post_id}.json"


def get(post_id) -> dict | None:
    """取缓存 → {text, images, …}；没有或已过期返回 None。

    字段随游戏而异（绝区零还要 content——网页活动的判据是正文里的原始外链），
    所以这里整份存整份还，不去规定有哪几个键。
    """
    if not post_id:
        return None
    try:
        with open(_path(post_id), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if _stale(d.get("fetched_at")):
        return None
    return d


def put(post_id, **fields) -> None:
    """存一篇正文。写失败不影响本次运行（缓存只是省请求，不是数据源）。"""
    if not post_id:
        return
    _path(post_id).parent.mkdir(parents=True, exist_ok=True)
    with open(_path(post_id), "w", encoding="utf-8") as f:
        json.dump({"post_id": str(post_id), **fields,
                   "fetched_at": _today().isoformat()}, f, ensure_ascii=False)


def _load_audited() -> dict:
    try:
        with open(AUDITED_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def audit_state(post_id) -> dict | None:
    """这篇公告的上次审读记录 → {"date": …, "waiting": bool}；没审过或已过期返回 None。

    旧格式（只存一个日期字符串）当作 waiting=True：多读一次自纠，不会把「还有块在等版本
    周期表」的那篇误判成已经啃干净。
    """
    if not post_id:
        return None
    rec = _load_audited().get(str(post_id))
    if isinstance(rec, str):
        rec = {"date": rec, "waiting": True}
    if not isinstance(rec, dict) or _stale(rec.get("date")):
        return None
    return rec


def mark_audited(post_id, waiting: bool) -> None:
    """记下「本轮审过这篇公告」，以及**还有没有块的日期解不出来**（`waiting`）。

    调用方在抓之前先记 waiting=False：抓失败的也要算审过，否则风控期间每轮都重试同一批
    （见模块说明）；解析成功后再按实际结果改写。
    """
    if not post_id:
        return
    d = _load_audited()
    d[str(post_id)] = {"date": _today().isoformat(), "waiting": bool(waiting)}
    AUDITED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDITED_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
