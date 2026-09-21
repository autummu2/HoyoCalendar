"""星铁公告解析 — 纯规则、纯函数，不读写文件、不发请求。

与 extractor.py（原神）并列的一套实现。之所以不共用：两边的段落标记、公告命名、
卡池标题来源、版本节奏都不同（见 rules.py 的说明），硬塞进同一个函数只会变成
一堆 if 分支。真正通用的部分（yaml_io / keys / calibrate.calibrate）走的是共享模块。

每个解析函数的正确性都由 selftest.py 用 fixtures/ 里的真实公告断言。
"""

from __future__ import annotations

import datetime
import re

from starrail import rules


# ─── 通用小工具 ──────────────────────────────────────────

# 书名号：先匹配最外层「」，以兼容嵌套（「反贪『砖』家」「镇伏『贪饕』，汇聚愿力」）。
# 原神侧的 [「『]([^」』]{2,40})[」』] 在嵌套时会截断成「镇伏『贪饕」，星铁里这种标题很多。
RE_OUTER_NAME = re.compile(r"「([^「」]{2,60})」")
RE_ANY_NAME = re.compile(r"[「『]([^」』]{2,40})[」』]")

# 日期，时刻可选（「2026/08/26 4.5版本更新后」这种没有时刻）
RE_DATE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?")

RE_VERSION = re.compile(r"(\d+\.\d+)\s*版本")


def _name_of(subject: str) -> str | None:
    """取公告标题里的活动名。优先最外层「」，退回任意书名号。"""
    m = RE_OUTER_NAME.search(subject or "")
    if not m:
        m = RE_ANY_NAME.search(subject or "")
    return m.group(1).rstrip("！!。：:") if m else None


def _iso(y: str, mo: str, d: str) -> str:
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def _subtract_day(iso: str) -> str:
    return (datetime.date.fromisoformat(iso) - datetime.timedelta(days=1)).isoformat()


def parse_period(seg: str) -> tuple[str | None, str | None]:
    """从时间段文本提取 (start, end)，返回 ISO 日期或 None。

    start = 首个日期，照抄（起止总在白天整点或「版本更新后」，没有减一天的场景）。
    end   = 末个日期；若带时刻且时刻在清晨（≤06:00），减一天——那时刻是游戏日/
            停机维护的分界，该日玩家已经玩不到了。

    实测依据（见 fixtures/ 与 selftest.py）：
      2026/07/27 04:00 - 2026/08/10 03:59 → 8/09（03:59 减一天）
      2026/08/17 04:00 - 2026/09/28 06:00 → 9/27（06:00 也减，停机维护时刻）
      2026/08/26 4.5版本更新后 - 2026/09/28 03:59 → 8/26 ~ 9/27
      2026/07/15 4.4版本更新后 - 2026/08/25 15:00 → 7/15 ~ 8/25（白天时段照抄）
    """
    us = RE_DATE.findall(seg or "")
    if not us:
        return None, None
    y, mo, d, _hh, _mm = us[0]
    start = _iso(y, mo, d)
    y, mo, d, hh, mm = us[-1]
    end = _iso(y, mo, d)
    if hh and int(hh) * 60 + int(mm) <= rules.MORNING_CUTOFF_MIN:
        end = _subtract_day(end)
    return start, end


# ─── 版本更新说明 ────────────────────────────────────────

RE_VERSION_DURATION = re.compile(r"\d+\.\d+版本的持续时间为\s*(.*?)。", re.S)
RE_ENDGAME_THEME = re.compile(r"本期主题：[「『]([^」』]+)[」』]")


def _strip_mode_prefix(name: str) -> str:
    """「异相仲裁•军团再临」→「军团再临」；已是纯期名则原样返回。"""
    for mode in rules.ENDGAME_MODES:
        if name.startswith(mode + "•"):
            return name[len(mode) + 1:]
    return name


def is_version_notes(subject: str) -> bool:
    """是否版本更新说明。排除《云•星穹铁道》的同名公告（云游戏，内容不同）。"""
    return rules.VERSION_NOTES_KEYWORD in (subject or "") and "云•星穹铁道" not in subject


def parse_version_notes(text: str, subject: str) -> dict | None:
    """解析版本更新说明 → {version, name, start_date, next_version_date, endgame}。

    这是星铁最有用的一份公告，每版本开服当天发：
    - 「4.5版本的持续时间为 2026/08/26 4.5版本更新后 - 2026/09/28 06:00」
      → 本版本开始就知道**下个版本的准确日期**（提前 33 天），不必按固定周期外推。
      注意这里的末日期取**原始值**（9/28），不减一天——它是下一版的起点。
    - 「■玩法」段 → 高难四支的期名与日期。

    endgame 每项 {mode, name, start_date, end_date}；异相仲裁只给期名不给日期，
    由调用方按「版本期间」补（见 pipeline）。
    """
    m = RE_VERSION.search(subject or "")
    if not m:
        return None
    version = m.group(1)
    name = None
    m2 = re.search(r"版本「([^」]+)」版本更新说明", subject or "")
    if m2:
        name = m2.group(1)

    result: dict = {"version": version, "name": name}
    seg = RE_VERSION_DURATION.search(text or "")
    if seg:
        us = RE_DATE.findall(seg.group(1))
        if us:
            y, mo, d, _h, _m2 = us[0]
            result["start_date"] = _iso(y, mo, d)
            y, mo, d, _h, _m2 = us[-1]
            result["next_version_date"] = _iso(y, mo, d)

    # 「■玩法」段：高难四支
    gm = re.search(rules.GAMEPLAY_SECTION, text or "", re.S)
    endgame: list[dict] = []
    if gm:
        block = gm.group(1)
        tm = RE_ENDGAME_THEME.search(block)
        if tm:
            # 正文写「异相仲裁•军团再临」，其余三支写「末日幻影•仙客天狼」——
            # 这里统一只留期名，标题由 pipeline 拼成「型名·期名」（数据文件的写法）
            endgame.append({"mode": "异相仲裁", "name": _strip_mode_prefix(tm.group(1))})
        for mode in ("末日幻影", "虚构叙事", "混沌回忆"):
            em = re.search(re.escape(mode) + r"•(.*?)\s+(\d{4})/(\d{1,2})/(\d{1,2})"
                           r"\s+\d{1,2}:\d{2}\s*-\s*(\d{4})/(\d{1,2})/(\d{1,2})"
                           r"\s+(\d{1,2}):(\d{2})", block)
            if not em:
                continue
            start = _iso(em.group(2), em.group(3), em.group(4))
            end = _iso(em.group(5), em.group(6), em.group(7))
            if int(em.group(8)) * 60 + int(em.group(9)) <= rules.MORNING_CUTOFF_MIN:
                end = _subtract_day(end)
            endgame.append({"mode": mode, "name": em.group(1).strip(),
                            "start_date": start, "end_date": end})
    result["endgame"] = endgame
    return result


def find_version_notes(posts: list[dict]) -> list[dict]:
    """从公告列表里筛版本更新说明（取最新一条）。"""
    for p in posts:
        if is_version_notes(p.get("subject", "")):
            return [p]
    return []


# ─── 更新预告（版本更新日最权威的来源）────────────────────

RE_PREVIEW = re.compile(r"预计于\s*(\d{4})/(\d{1,2})/(\d{1,2})\s+\d{1,2}:\d{2}\s*进行版本更新维护"
                        r".{0,40}?更新至\s*(\d+\.\d+)\s*版本[「『]([^」』]+)[」』]", re.S)


def is_update_preview(subject: str) -> bool:
    return rules.UPDATE_PREVIEW_KEYWORD in (subject or "")


def parse_update_preview(text: str) -> dict | None:
    """解析更新预告正文 → {date, version, name}。

    正文：「列车组预计于 2026/08/26 06:00 进行版本更新维护，维护完成后将更新至
    4.5版本「挥掷千星的筹码」。」发布于更新前 2 天，比版本更新说明更晚、更准。
    """
    m = RE_PREVIEW.search(text or "")
    if not m:
        return None
    return {"date": _iso(m.group(1), m.group(2), m.group(3)),
            "version": m.group(4), "name": m.group(5)}


def find_update_previews(posts: list[dict]) -> list[dict]:
    for p in posts:
        if is_update_preview(p.get("subject", "")):
            return [p]
    return []


# ─── 卡池 ────────────────────────────────────────────────

RE_BANNER_SHARED = re.compile(r"本期活动跃迁时间为(.*?)包含如下内容", re.S)
RE_BANNER_POOL_STAR = re.compile(r"角色活动跃迁期间，\s*限定5星角色\s*[「『]([^」』]+)[」』]")


def is_banner(subject: str) -> bool:
    return bool(re.search(rules.BANNER_PATTERN, subject or ""))


def parse_banner_body(text: str) -> list[dict]:
    """解析卡池公告正文 → [{title, start_date, end_date}]，可能多条。

    星铁卡池公告标题只有「（其一/其二）」，5 星名字全在正文里，所以标题要现拼：
    把同一时间段的角色活动跃迁 5 星名用「」连起来 + 「跃迁」。

    两种排版（都实测过）：
    - 有「本期活动跃迁时间为 A - B，包含如下内容」→ 全公告共用一个时间段，
      5 星取所有「角色活动跃迁期间，限定5星角色「X」」。其一/其二都是这种。
    - 没有该句 → 开头段落逐句分组，每句给出自己的一组 5 星和「跃迁时间为 …」。
      4.4 其二这种含「铭心之萃」返场池的排版，返场池 8/05 开、首发池 7/15 开，
      必须拆成两条，否则日期只能二选一。

    拼出的标题与数据文件里既有的条目**逐字一致**（selftest.py 断言），
    所以这些卡池条目不需要任何日期/标题推理。
    """
    text = text or ""
    out: list[dict] = []

    m = RE_BANNER_SHARED.search(text)
    if m:
        start, end = parse_period(m.group(1))
        names: list[str] = []
        for n in RE_BANNER_POOL_STAR.findall(text):
            if n not in names:
                names.append(n)
        if names and start and end:
            out.append({"title": "".join(f"「{n}」" for n in names) + "跃迁",
                        "start_date": start, "end_date": end})
        return out

    # 逐句分组：只看第一个「▌」之前的开头段落
    intro = text.split("▌")[0]
    for sent in intro.split("。"):
        if "限定5星角色" not in sent or "跃迁时间为" not in sent:
            continue
        before = sent.split("与限定5星光锥")[0]
        names = [n for n in RE_ANY_NAME.findall(before)]
        if not names:
            continue
        start, end = parse_period(sent.split("跃迁时间为", 1)[1])
        if not (start and end):
            continue
        out.append({"title": "".join(f"「{n}」" for n in names) + "跃迁",
                    "start_date": start, "end_date": end})
    return out


def find_banners(posts: list[dict]) -> list[dict]:
    """筛出卡池公告，返回 [{subject, post_id, created_at}]（正文留给调用方抓）。"""
    out = []
    for p in posts:
        if is_banner(p.get("subject", "")):
            out.append({"subject": p["subject"], "post_id": p.get("post_id", ""),
                        "created_at": p.get("created_at", 0)})
    return out


# ─── 活动（常规活动 / 版本大活动）─────────────────────────

def is_activity(subject: str) -> bool:
    s = subject or ""
    if is_version_notes(s) or is_update_preview(s) or is_banner(s):
        return False
    if rules.BATTLE_PASS_KEYWORD in s:
        return False
    if any(kw in s for kw in rules.EXCLUDE):
        return False
    return _name_of(s) is not None


def find_activities(posts: list[dict]) -> list[dict]:
    """筛出活动公告，返回 [{title, name, post_id, created_at}]。

    title 统一为「活动名」（取最外层「」），与原神侧同一约定——
    数据文件里既有两条保留了完整标题（「位面分裂」活动：…），已按此约定订正。
    """
    out = []
    for p in posts:
        s = p.get("subject", "")
        if not is_activity(s):
            continue
        name = _name_of(s)
        out.append({"title": f"「{name}」", "name": name,
                    "post_id": p.get("post_id", ""), "created_at": p.get("created_at", 0)})
    return out


def parse_activity_body(text: str) -> dict:
    """解析活动正文 → {description, start_date?, end_date?, version_period?}。

    description 取整段正文（与数据文件里多数条目一致）。
    「X.Y版本期间」→ version_period='X.Y'（版本号，不是 True），起止由调用方按
    版本周期补——星铁版本周期不固定，只能靠版本更新说明给出的相邻更新日相减。
    """
    result: dict = {"description": (text or "").strip() or None}
    m = re.search(rules.ACTIVITY_SECTION + r"(.*?)(?=[▌■]|$)", text or "", re.S)
    if not m:
        return result
    seg = m.group(2)
    vm = re.search(r"(\d+\.\d+)版本期间", seg)
    if vm:
        result["version_period"] = vm.group(1)
        return result
    start, end = parse_period(seg)
    if start:
        result["start_date"] = start
    if end:
        result["end_date"] = end
    return result


# ─── 大月卡（无名勋礼）────────────────────────────────────

def is_battle_pass(subject: str) -> bool:
    return rules.BATTLE_PASS_KEYWORD in (subject or "")


def find_battle_passes(posts: list[dict]) -> list[dict]:
    out = []
    for p in posts:
        if is_battle_pass(p.get("subject", "")):
            m = RE_VERSION.search(p.get("subject", ""))
            out.append({"subject": p["subject"], "post_id": p.get("post_id", ""),
                        "created_at": p.get("created_at", 0),
                        "version": m.group(1) if m else None})
    return out


# ─── B站动态 ─────────────────────────────────────────────

RE_LIVESTREAM = re.compile(r"(\d+\.\d+)版本「([^」]+)」前瞻特别节目将于"
                           r"(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2}):(\d{2})正式播出")
RE_LAUNCH = re.compile(r"(\d+\.\d+)版本「([^」]+)」将于"
                       r"(\d{4})年(\d{1,2})月(\d{1,2})日上线")


def parse_livestream(text: str) -> dict | None:
    """前瞻预告动态 → {version, name, date}。

    闸门用「正式播出」而不是原神那边的「开启」：星铁的**回顾长图**动态里也有
    「开启」（「开启新的冒险旅途」），用「开启」会把回顾当预告，且日期会取错
    （回顾里只有兑换码失效日）。实测踩到过。
    """
    m = RE_LIVESTREAM.search(text or "")
    if not m:
        return None
    return {"version": m.group(1), "name": m.group(2),
            "date": _iso(m.group(3), m.group(4), m.group(5))}


def parse_launch(text: str) -> dict | None:
    """版本上线动态 → {version, name, date}。前瞻当天发布，比维护预告早约 8 天。"""
    m = RE_LAUNCH.search(text or "")
    if not m:
        return None
    return {"version": m.group(1), "name": m.group(2),
            "date": _iso(m.group(3), m.group(4), m.group(5))}


def find_livestreams(items: list[dict]) -> list[dict]:
    out = []
    for d in items:
        r = parse_livestream(d.get("text", ""))
        if r:
            r["id"] = d.get("id", "")
            out.append(r)
    return out


def find_launches(items: list[dict]) -> list[dict]:
    out = []
    for d in items:
        r = parse_launch(d.get("text", ""))
        if r:
            r["id"] = d.get("id", "")
            out.append(r)
    return out
