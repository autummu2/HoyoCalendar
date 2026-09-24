"""原神周期性活动推理。

依据 tools/editor/genshin/RULES.md 的规则，纯日期推算未来 N 天内的周期性活动：
- 深境螺旋：每月 16 号刷新，一期 16号 ~ 次月15号
- 幻想真境剧诗：每月 1 号刷新，一期 1号 ~ 月末
- 版本更新：每周三，42 天一个版本
- 前瞻直播：版本更新前约 11 天（近似，实际周五/周六，B站可确认）
- 卡池：上下半各 3 周，上半 = [更新日, 更新日+20]，下半 = [更新日+20, 更新日+41]（infer_banner_dates，就近匹配最近版本更新日，版本更新日从数据文件读出）

生成的活动带 `自动推理` 标签；版本更新与前瞻再带 `待确认版本`（版本号与版本名均为预测/占位，公告后回填）。
本模块为纯函数，不读写数据文件，便于测试与后续接入编辑器或定时任务。
"""

from __future__ import annotations

import datetime

from common import keys

GAME = "genshin-impact"

# ── 版本更新锚点 ──────────────────────────────────────────
# 锚点不再硬编码：由 extract_version_anchor 从数据文件里取最新一条「版本更新」
# （日期 + 标题里的版本号），后续版本 = 锚点 + 42 天 × n。
# 版本延期、版本号跳号都只需人工改数据文件里那一条，推理自动跟着走。
VERSION_CYCLE_DAYS = 42
LIVESTREAM_LEAD_DAYS = 11  # 前瞻约在版本更新前 11 天（周五/周六，近似值）

# ── 卡池节奏（版本更新固定周三，上下半各 3 周）────────────
BANNER_PHASE1_END = 20   # 上半结束日 = 更新日 + 20 天
BANNER_PHASE2_END = 41   # 下半结束日 = 更新日 + 41 天

# ── 颜色（与现有数据一致） ───────────────────────────────
COLOR_ABYSS = "#8779d2"       # 深境螺旋
COLOR_THEATER = "#7ba6f4"     # 幻想真境剧诗
COLOR_VERSION = "#ffffff"     # 版本更新
COLOR_LIVESTREAM = "#7dc4ea"  # 前瞻直播

TAG_INFER = "自动推理"
# 版本号与版本名均为预测/占位，待公告后回填。值只在 common/keys.py 定义一处：
# 它由 calibrate 在校准到权威来源时摘掉，产出侧与清除侧必须是同一个字符串
# （原神的 `待确认` 曾经就是因为各写一份字面量而永远摘不掉）。
TAG_PENDING_VERSION = keys.TAG_PENDING_VERSION


def _iso(d: datetime.date) -> str:
    return d.isoformat()


def _mmdd(d: datetime.date) -> str:
    return f"{d.month:02d}{d.day:02d}"


def _add_months(d: datetime.date, months: int) -> datetime.date:
    """d 的月份加 months，返回该月 1 号。"""
    m = d.month - 1 + months
    return datetime.date(d.year + m // 12, m % 12 + 1, 1)


def _next_same_day(today: datetime.date, day: int) -> datetime.date:
    """返回 >= today 的下一个 day 号日期（本月或之后月份）。"""
    candidate = datetime.date(today.year, today.month, day)
    if candidate < today:
        candidate = _add_months(today, 1).replace(day=day)
    return candidate


def _next_version_date(today: datetime.date, anchor_date: datetime.date) -> datetime.date:
    """返回 >= today 的下一个版本更新日（周三）。"""
    delta = (today - anchor_date).days
    k = -(-delta // VERSION_CYCLE_DAYS)  # ceil(delta/42)，负数向上取整为 0
    return anchor_date + datetime.timedelta(days=k * VERSION_CYCLE_DAYS)


def _version_number(anchor_num: tuple[int, int], k: int) -> str:
    """锚点版本号 + k 个周期的预测版本号，简单按 0.1 递增。

    每个大版本的小版本数不固定（1.x 有 7 个，2.x~5.x 有 9 个），
    无法硬编码进位规则，故只做朴素 +0.1 预测；实际版本号待公告确认后校正。
    """
    major, minor = anchor_num
    total = major * 10 + minor + k
    return f"{total // 10}.{total % 10}"


def extract_version_anchor(events: list[dict]) -> tuple[datetime.date, tuple[int, int]] | None:
    """从事件列表里取最新一条「版本更新」作为版本节奏锚点。

    返回 (更新日, (大版本, 小版本))；没有可解析的「版本更新」时返回 None（则不推理版本事件）。
    取日期最晚的一条（可能是推理出的未来版本）；标题里解析不出版本号的条目跳过。
    """
    best: tuple[datetime.date, tuple[int, int]] | None = None
    for e in events:
        if e.get("type") != "版本更新":
            continue
        try:
            d = datetime.date.fromisoformat(str(e.get("start_date")))
        except (TypeError, ValueError):
            continue
        v = keys.version_of(e.get("title", ""))
        if not v:
            continue
        major, minor = v.split(".")
        if best is None or d > best[0]:
            best = (d, (int(major), int(minor)))
    return best


def _mk(start: datetime.date, end: datetime.date, type_: str, title: str, color: str,
        tags: list[str], suffix: str = "") -> dict:
    ev = {
        "id": f"gi-{(suffix or type_).rstrip('-')}-{title}",
        "game": GAME,
        "title": title,
        "type": type_,
        "start_date": _iso(start),
        "end_date": _iso(end),
        "color": color,
    }
    if tags:
        ev["tags"] = tags
    return ev


def infer_events(today: datetime.date, version_anchor=None, days: int = 30) -> list[dict]:
    """返回 start_date 落在 [today, today+days] 内的推理活动。

    version_anchor：extract_version_anchor 的结果 (更新日, (大版本, 小版本))。
    为 None 时不推理「版本更新 / 前瞻直播」（无锚点无法定位版本节奏），
    深境螺旋 / 幻想真境剧诗与版本节奏无关，照常推理。
    """
    horizon = today + datetime.timedelta(days=days)
    events: list[dict] = []

    # 深境螺旋：每月 16 号 ~ 次月 15 号
    abyss_start = _next_same_day(today, 16)
    abyss_end = _add_months(abyss_start, 1).replace(day=15)
    if abyss_start <= horizon:
        mmdd = _mmdd(abyss_start)
        events.append(_mk(abyss_start, abyss_end, "高难挑战", f"深境螺旋{mmdd}",
                          COLOR_ABYSS, [TAG_INFER], suffix="深境螺旋-"))

    # 幻想真境剧诗：每月 1 号 ~ 月末
    theater_start = _next_same_day(today, 1)
    theater_end = _add_months(theater_start, 1) - datetime.timedelta(days=1)
    if theater_start <= horizon:
        mmdd = _mmdd(theater_start)
        events.append(_mk(theater_start, theater_end, "高难挑战", f"幻想真境剧诗{mmdd}",
                          COLOR_THEATER, [TAG_INFER], suffix="幻想真境剧诗-"))

    # 版本更新 + 前瞻直播
    if version_anchor is not None:
        anchor_date, anchor_num = version_anchor
        ver_date = _next_version_date(today, anchor_date)
        if ver_date <= horizon:
            k = (ver_date - anchor_date).days // VERSION_CYCLE_DAYS
            ver_num = _version_number(anchor_num, k)
            events.append(_mk(ver_date, ver_date, "版本更新", f"《原神》{ver_num} 版本停服更新",
                              COLOR_VERSION, [TAG_INFER, TAG_PENDING_VERSION], suffix="版本更新-"))
            live_date = ver_date - datetime.timedelta(days=LIVESTREAM_LEAD_DAYS)
            if today <= live_date <= horizon:
                events.append(_mk(live_date, live_date, "前瞻直播",
                                  f"《原神》{ver_num} 版本前瞻特别节目",
                                  COLOR_LIVESTREAM, [TAG_INFER, TAG_PENDING_VERSION], suffix="前瞻直播-"))

    return events


def extract_version_dates(events: list[dict]) -> list[str]:
    """从事件列表里提取「版本更新」事件的 start_date（去重、升序）。

    供 infer_banner_dates 就近匹配卡池所属版本。事件来自 yaml_io.load_events，
    已含过去确认的版本更新与推理出的未来版本更新。
    """
    return sorted({e["start_date"] for e in events
                   if e.get("type") == "版本更新" and e.get("start_date")})


def _nearest_version_date(created_at: int, updates: list[datetime.date]) -> datetime.date | None:
    """返回距发布日最近的版本更新日（即活动所属版本）。

    「版本更新后 / 版本期间」活动多在版本更新前 1~2 天发布预告，
    故用「最近」而非「≤ 发布日」，否则会把预告归到上一版本。
    """
    try:
        pub = datetime.datetime.fromtimestamp(int(created_at)).date()
    except (TypeError, ValueError, OSError):
        return None
    if not updates:
        return None
    return min(updates, key=lambda u: abs((pub - u).days))


def resolve_version_starts(entries: list[dict], version_dates: list[str | datetime.date]) -> list[dict]:
    """把「版本更新后 ~ Y」活动的缺失 start_date 解析为对应版本更新日。

    entries：含 description 的活动条目（extractor.parse_activity_body 输出）。
    当 start_date 缺失、end_date 存在、且 description 含「版本更新后」时，
    start = 距发布日最近的版本更新日（周三）。
    """
    updates = sorted(datetime.date.fromisoformat(str(v)) for v in version_dates)
    out = []
    for e in entries:
        new = dict(e)
        if (not new.get("start_date") and new.get("end_date")
                and "版本更新后" in (new.get("description") or "")):
            vd = _nearest_version_date(new.get("created_at", 0), updates)
            if vd is not None:
                new["start_date"] = vd.isoformat()
        out.append(new)
    return out


def resolve_version_period(entries: list[dict], version_dates: list[str | datetime.date]) -> list[dict]:
    """把「版本期间持续开放」活动的起止解析为整版本周期。

    entries：extractor.parse_activity_body 的输出（含 version_period=True 标记 + created_at）。
    start = 距发布日最近的版本更新日；end = 下版本更新日 − 1 天。
    """
    updates = sorted(datetime.date.fromisoformat(str(v)) for v in version_dates)
    # end = 下个版本更新日 − 1。活动若属于**最新已知版本**，updates 里还没有下一个
    # 版本更新日（推理出的未来那一期此刻尚未并入数据，见 pipeline.py 的调用顺序），
    # 就会算不出 end。按 42 天周期补一期兜底。
    if updates:
        updates = sorted(set(updates) | {updates[-1] + datetime.timedelta(days=VERSION_CYCLE_DAYS)})
    out = []
    for e in entries:
        new = dict(e)
        if not new.get("version_period"):
            out.append(new)
            continue
        vd = _nearest_version_date(new.get("created_at", 0), updates)
        if vd is not None:
            new["start_date"] = vd.isoformat()
            nxt = [u for u in updates if u > vd]
            if nxt:
                new["end_date"] = (nxt[0] - datetime.timedelta(days=1)).isoformat()
        out.append(new)
    return out


def infer_banner_dates(announcements: list[dict], version_dates: list[str | datetime.date]) -> list[dict]:
    """按版本节奏推断卡池起止日期。

    announcements：extractor.find_banner_announcements 的输出，每项含 {title, created_at}。
    version_dates：版本更新日列表（周三），用 extract_version_dates 从数据文件读出。

    阶段判定：以距公告发布日**最近的版本更新日**为锚，发布日 < 锚点 → 上半，否则下半
    （实测上半公告更新前 2 天发、下半更新后 15 天发）。
    起止日期：上半 = [锚点, 锚点+20]，下半 = [锚点+20, 锚点+41]。
    返回 [{title, start_date, end_date, phase, post_id}]，phase ∈ {上半, 下半}。
    逐条就近匹配，跨版本混排也能各自判对。
    """
    updates = [v if isinstance(v, datetime.date) else datetime.date.fromisoformat(str(v))
               for v in version_dates]
    if not updates:
        return []

    entries: list[dict] = []
    for a in announcements:
        pub = None
        try:
            pub = datetime.datetime.fromtimestamp(int(a.get("created_at", 0))).date()
        except (TypeError, ValueError, OSError):
            pub = None
        if pub is None:
            continue  # 无发布时间无法判段（现实中 created_at 总是存在）

        update = min(updates, key=lambda u: abs((pub - u).days))
        phase = "上半" if pub < update else "下半"
        if phase == "上半":
            start = update
            end = update + datetime.timedelta(days=BANNER_PHASE1_END)
        else:
            start = update + datetime.timedelta(days=BANNER_PHASE1_END)
            end = update + datetime.timedelta(days=BANNER_PHASE2_END)

        entry: dict = {
            "title": a.get("title", ""),
            "start_date": _iso(start),
            "end_date": _iso(end),
            "phase": phase,
        }
        if a.get("post_id"):
            entry["post_id"] = a["post_id"]
        entries.append(entry)
    return entries


if __name__ == "__main__":
    from common import yaml_io

    today = datetime.date.today()
    anchor = extract_version_anchor(yaml_io.load_events(GAME))
    print("锚点:", anchor)
    for ev in infer_events(today, anchor):
        print(ev["title"], ev["start_date"], "~", ev["end_date"], "|", ev["tags"])
