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
    """从公告列表里筛**窗口内全部**版本更新说明（列表按时间倒序，第一条即当前版本）。

    返回全部而不是只取最新，是为了让调用方在最新那份抓不到时能往后顺延；但
    `pipeline._collect_notes` **只读第一条**——旧版本的说明不再读（原先读它们只为填版本
    周期表，而那张表现在由已落盘的版本更新条目推，见 `pipeline._version_table`）。
    """
    return [p for p in posts if is_version_notes(p.get("subject", ""))]


# ─── 总纲的活动段（`X、全新活动`）─────────────────────────

# 编号段标题（`3、全新光锥` / `6、全新活动` / `7、其他内容`…）。段号每版不同，所以只用来
# 定界，**不写死段号**——按段名后缀定位，段名变了这里也要跟着改。
RE_NUMBERED_SECTION = re.compile(r"\d+、\S+")
ACTIVITY_SECTION = "全新活动"

# 「N.N版本更新后」是版本开服日的代称（总纲自己给了那一版的开始日期）
RE_VERSION_START = re.compile(r"(\d+\.\d+)\s*版本更新后")

# 一条活动的段落里，名字后面跟着的东西（段内压平成了一行，名字与描述之间只有空格）
RE_ITEM_BREAK = re.compile(r"[ ●※]")

# 同一段里描述之后的字段：`●` 是条目自己的字段（参与条件等），`※` 是备注。
# 空格不算——描述本身含空格，用 RE_ITEM_BREAK 那种切法会把描述切碎。
RE_ITEM_NOTE = re.compile(r"[●※]")


def _demote_quotes(name: str) -> str:
    """活动名 → 公告 subject 里的写法：内层「」降级成『』（与 zenless.parse 同一条规则）。

    总纲写 `■反贪「砖」家`，活动自己的公告标题是 `「反贪『砖』家」活动说明`。数据文件用的是
    后一种，所以这里必须转——否则同一条活动在总纲与公告下有两个名字，去重主键
    （keys.event_key）失配，总纲落盘的那条会被当成另一条活动，而 apply_events 只认主键
    → 插一条重复。
    """
    return name.replace("「", "『").replace("」", "』")


def _item_period(chunk: str, versions: dict) -> tuple[str | None, str | None]:
    """一条活动段落里的 `活动时间：…` → (start, end)；解不出起止返回 (None, None)。"""
    m = re.search(r"活动时间：(.*?)(?=\s+(?:[●※]|参与条件)|$)", chunk)
    if not m:
        return None, None
    seg = m.group(1)
    vm = RE_VERSION_START.search(seg)
    if vm:
        start = (versions.get(vm.group(1)) or (None, None))[0]
        if not start:
            # 那一版的开服日未知（它的说明不在窗口内）→ 不猜。写死或就近取一个值会让整条
            # 起止错位，宁可让这条活动等它自己的公告。
            return None, None
        seg = seg[:vm.start()] + start.replace("-", "/") + seg[vm.end():]
    # 只解得出一个日期的（`2026/07/24 12:00 - 4.6版本结束前`）判为不齐：parse_period 会把
    # 那个日期同时当成起止，于是落一条只有一天的活动。同样宁可等，不要错。
    if len(RE_DATE.findall(seg)) < 2:
        return None, None
    return parse_period(seg)


def parse_version_activities(text: str, versions: dict,
                             version: str | None = None) -> list[dict]:
    """总纲 `X、全新活动` 段列出的活动 → [{name, title, start_date, end_date, ...}]。

    总纲按版本逐个列出本版活动（名字 + `活动时间：`），但给不出**类型**，也没有配图与
    正文描述——那三样只有活动自己的公告才有。所以这一段的用处是**提前**：实测比活动
    自己的公告早 15 天（4.5 总纲 08-26 发布，「方寸大冒险」的公告 09-10 才发），活动因此
    能在版本更新当天就挂上日历（类型/描述/配色随后订正，见 pipeline.py 与 PLAN.md §1.2）。

    段在下一个编号段（`7、其他内容`）处结束；段内按 `■` 切条，条目名取到首个 `●`/`※`/空格。

    versions：{版本号: (起, 止)}，用来解析「N.N版本更新后」。
    version：这份总纲自己的版本号，用来给**没有 `活动时间：`** 的登录福利条目取时段。

    实测每版总纲的登录福利条目（「巡星之礼」）都不写 `活动时间：`，只写「活动期间，
    每日登录…」，而它从来没有自己的公告——不在这里收，它就永远进不了日历。它的时段
    按**版本期间**算（起止就是本版总纲给出的相邻更新日，不是外推），类型判为登录福利；
    描述取条目本文，不需要正文公告，所以也不打 pending 标记（没有公告可等）。
    """
    marks = list(RE_NUMBERED_SECTION.finditer(text or ""))
    head = next((i for i, m in enumerate(marks)
                 if m.group(0).endswith(ACTIVITY_SECTION)), None)
    if head is None:
        return []
    sec_end = marks[head + 1].start() if head + 1 < len(marks) else len(text)

    out: list[dict] = []
    for chunk in text[marks[head].end():sec_end].split("■")[1:]:
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = RE_ITEM_BREAK.split(chunk, maxsplit=1)
        name = _demote_quotes(parts[0])
        if not name:
            continue
        start, end = _item_period(chunk, versions)
        item = {"name": name, "title": f"「{name}」",
                "start_date": start, "end_date": end}
        # 判据是**条目本文里没有 `活动时间：`**，不是「日期解不出来」——两者必须分开：
        # 「命运契约•再启」有 `活动时间：`（只是终点写作「4.6版本结束前」），它的时段不等于
        # 版本期间，给它套版本期间会落一段错日期；「巡星之礼」则是根本没写时段。
        # 措辞作第二道确认，避免把将来某条既没写时段又不是登录福利的条目也当成整版。
        if "活动时间：" not in chunk and any(k in chunk for k in rules.LOGIN_KEYWORDS):
            item["start_date"], item["end_date"] = versions.get(version) or (None, None)
            item["type"] = "登录福利"
            item["description"] = RE_ITEM_NOTE.split(
                parts[1] if len(parts) > 1 else "", maxsplit=1)[0].strip() or None
        out.append(item)
    return out


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


# 时间段里的两种相对写法（绝对日期由 parse_period 直接算完）
RE_VERSION_PERIOD = re.compile(r"(\d+\.\d+)版本期间")      # 两端都取那一版
RE_VERSION_END_BEFORE = re.compile(r"(\d+\.\d+)版本结束前")  # 终点取那一版的终点，起点是段内绝对日期

# 一帖多活动：正文里用 `▌「X」活动说明` 逐块标出自己的活动（实测「幻造：圣杯战争」那篇是三块）。
# 一帖一活动的公告没有这种标题——活动名只在 subject 里，整篇正文就是那一块。
RE_ACTIVITY_HEAD = re.compile(r"[▌■]\s*「([^「」]{1,60})」\s*活动说明")


def parse_activity_body(text: str) -> dict:
    """解析活动正文 → {description, start_date?, end_date?, version_period?, version_end_before?}。

    description 取整段正文（与数据文件里多数条目一致）。

    **时间段只认 `活动时间/限时活动期/开启时间` 那一段**（`ACTIVITY_SECTION`），段外的日期不看
    ——正文里还有参与条件、奖励说明，随手取末个日期会拿到别的日子。

    时间段有三种写法，绝对日期的能在这里算完，两种相对写法要把版本号交回调用方、由版本
    周期表补（星铁版本周期不固定，只能靠相邻两次更新日相减，见 rules.py）：
      `X.Y版本期间`   → version_period='X.Y'    两端都取那一版
      `X.Y版本结束前` → version_end_before='X.Y' 终点取那一版的终点，起点用段内的绝对日期
    那一版不在版本周期表里时**不猜**：起点照给、终点留空，由管线的日期闸丢掉整条。写死或
    按 42 天外推都会落一段错日期，宁可让这条等它自己的说明。
    """
    result: dict = {"description": (text or "").strip() or None}
    m = re.search(rules.ACTIVITY_SECTION + r"(.*?)(?=[▌■]|$)", text or "", re.S)
    if not m:
        return result
    seg = m.group(2)
    vm = RE_VERSION_PERIOD.search(seg)
    if vm:
        result["version_period"] = vm.group(1)
        return result
    start, end = parse_period(seg)
    vm = RE_VERSION_END_BEFORE.search(seg)
    if vm:
        result["version_end_before"] = vm.group(1)
        if start:
            result["start_date"] = start
        return result
    # 只解得出一个绝对日期的判为不齐：parse_period 会把那一个日期同时当成起止，落一条只有
    # 一天的活动。与 _item_period 同一条判据（那里是相对端解不出来时先拦一道）。
    if len(RE_DATE.findall(seg)) < 2:
        return result
    if start:
        result["start_date"] = start
    if end:
        result["end_date"] = end
    return result


def parse_activity_bodies(text: str, name: str) -> list[dict]:
    """一篇活动公告正文 → **一条或多条**活动，每条比 parse_activity_body 多一个 name。

    绝大多数公告一帖一活动：没有 `▌「X」活动说明` 标题，整篇正文就是一块，name 取 subject
    里的名字（与数据文件既有的标题逐字一致）。少数公告一帖多活动（「幻造：圣杯战争」那篇
    除了主体还挂了「命运契约•再启」「命运赠礼」），标题前的部分算首块、每个标题起一块。

    首块没有时间段就不产出——那种公告（如「命运赠礼」有自己的名字、正文只讲主体）留着
    只会多一条无日期的条目被日期闸丢掉。
    """
    text = text or ""
    marks = list(RE_ACTIVITY_HEAD.finditer(text))
    head = text[:marks[0].start()] if marks else text

    out: list[dict] = []
    if re.search(rules.ACTIVITY_SECTION, head):
        body = parse_activity_body(head)
        body["name"] = _demote_quotes(name)
        out.append(body)
    for i, m in enumerate(marks):
        stop = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = parse_activity_body(text[m.end():stop])
        body["name"] = _demote_quotes(m.group(1))
        out.append(body)
    return out


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
