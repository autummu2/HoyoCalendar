"""绝区零公告解析 — 纯规则、纯函数，不读写文件、不发请求。

与 extractor.py（原神）、starrail/parse.py 并列的第三套实现。真正通用的部分
（yaml_io / keys / calibrate / bilibili 的前瞻解析）直接复用。

绝区零的公告都用【】标段名（原神〓、星铁▌），且 `fetch_post` 给的 text 是
**空格分隔的一整段**（没有换行），所以下面的正则一律用 `\\s*` 连接，不能按行匹配。

每个解析函数的正确性都由 selftest.py 用 fixtures/ 里的真实公告断言。
"""

from __future__ import annotations

import datetime
import re

from common import bilibili
from zenless import rules


# ─── 通用小工具 ──────────────────────────────────────────

# 最外层「」：兼容嵌套书名号（「『嗯呢』大派送！」「『弹球勇者』哐哐当！」）
RE_OUTER_NAME = re.compile(r"「([^「」]{2,60})」")
RE_ANY_NAME = re.compile(r"[「『]([^」』]{2,40})[」』]")

# 日期，时刻可选
RE_DATE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?")

RE_VERSION = re.compile(r"(\d+\.\d+)\s*版本")

# 相对时间段的两端
RE_REL_START = re.compile(r"(\d+\.\d+)版本更新后")
RE_REL_END = re.compile(r"(\d+\.\d+)版本结束")


def _name_of(subject: str) -> str | None:
    """取公告标题里的活动名。优先最外层「」，退回任意书名号。

    原神/星铁那份会 rstrip 掉末尾的「！」，绝区零不能：感叹号是名字本身的一部分
    （「『嗯呢』大派送！」「咔嚓！焦点对决！」），去掉就与数据文件里的标题对不上，
    去重主键（keys.event_key）失配 → 下一轮插一条重复。书名号的捕获组本来就在
    「」之内，不会有游离的标点。
    """
    m = RE_OUTER_NAME.search(subject or "")
    if not m:
        m = RE_ANY_NAME.search(subject or "")
    return m.group(1) if m else None


def _iso(y: str, mo: str, d: str) -> str:
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def _minus_day(iso: str) -> str:
    return (datetime.date.fromisoformat(iso) - datetime.timedelta(days=1)).isoformat()


def _end_of(seg: str) -> str | None:
    """取时间段末端的日期：末个日期，时刻在清晨（≤06:00）则减一天。

    绝区零的区间一律写成 `A ~ B`，B 就是终点。清晨时刻是游戏日/停机维护的分界，
    该日玩家已经玩不到了；白天的时段（11:59/14:59）照抄。核对依据见 selftest.py。
    """
    us = RE_DATE.findall(seg or "")
    if not us:
        return None
    y, mo, d, hh, mm = us[-1]
    end = _iso(y, mo, d)
    if hh and int(hh) * 60 + int(mm) <= rules.MORNING_CUTOFF_MIN:
        end = _minus_day(end)
    return end


def resolve_period(seg: str, versions: dict) -> tuple[str | None, str | None]:
    """时间段文本 → (起, 止)。versions：{版本号: (起, 止)}。

    两种写法都实测过：
      绝对  2026/08/19 10:00 ~ 2026/09/07 03:59
      相对  3.2版本更新后 ~ 3.2版本结束 / 3.2版本更新后 ~ 2026/10/20 03:59

    相对端查总纲那张表（版本边界是公告明写的，不外推）；表里没有该版本号就返回
    None，由管线的日期闸丢掉整条——宁可晚几天，也不要按 42 天周期推出一个错的终点。
    起点照抄（哪怕写着 04:00——那是游戏日边界，当天就能参与）。
    """
    seg = seg or ""
    start = end = None
    m = RE_REL_START.search(seg)
    if m:
        start = (versions.get(m.group(1)) or (None, None))[0]
    else:
        us = RE_DATE.findall(seg)
        if us:
            start = _iso(*us[0][:3])
    m = RE_REL_END.search(seg)
    if m:
        end = (versions.get(m.group(1)) or (None, None))[1]
    else:
        end = _end_of(seg)
    return start, end


# ─── 停服更新公告（总纲）──────────────────────────────────

# 「【更新开始时间】 2026/09/09 06:00 预计5个小时完成。」
RE_UPDATE_START = re.compile(
    r"【更新开始时间】\s*(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})")
# 「3.2版本结束时间为 2026/10/21 06:00 ，该版本共持续42天」
RE_VERSION_END = re.compile(
    r"(\d+\.\d+)版本结束时间为\s*(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})"
    r"\s*，该版本共持续(\d+)天")


def is_version_notes(subject: str) -> bool:
    """是否停服更新公告（总纲）。《云·绝区零》的同名公告内容不同，不匹配本式。"""
    return bool(re.search(rules.VERSION_NOTES_PATTERN, subject or ""))


def parse_version_notes(text: str, subject: str) -> dict | None:
    """解析停服更新公告 → {version, name, start_date, next_version_date,
    period_days, endgame_counts}。

    这是绝区零唯一的「版本边界权威来源」，全部照抄、不做任何外推：
    - 【更新开始时间】→ 版本更新日（当天 06:00 开服，日期照抄）
    - 「X.Y版本结束时间为 D」→ **下一个版本**的更新日（原始值，不减一天）。
      本版本的终点 = 它减一天，由 version_period 算。3.1→09/09、3.2→10/21，
      两版首尾相接：09-08 与 09-09 各 42 天。
    - ▶高难两段的「第一期/第二期/第三期」→ 期数（日期不给，见 inference.py）

    拿不到 next_version_date 时该键为 None，相对写法的活动会被日期闸丢掉，不外推。
    """
    m = RE_VERSION.search(subject or "")
    if not m:
        return None
    result: dict = {"version": m.group(1)}
    m = re.search(r"版本「([^」]+)」更新公告", subject or "")
    result["name"] = m.group(1) if m else None

    m = RE_UPDATE_START.search(text or "")
    if m:
        result["start_date"] = _iso(m.group(1), m.group(2), m.group(3))
    m = RE_VERSION_END.search(text or "")
    if m:
        result["next_version_date"] = _iso(m.group(2), m.group(3), m.group(4))
        result["period_days"] = int(m.group(7))

    result["endgame_counts"] = {}
    for mode, block in re.findall(rules.ENDGAME_SECTION, text or "", re.S):
        result["endgame_counts"][mode] = len(set(re.findall(rules.ENDGAME_INDEX, block)))
    return result


def version_period(notes: dict | None) -> tuple[str | None, str | None]:
    """一个版本的 (起, 止)。终点 = 下个版本更新日 − 1 天（末日期是游戏日边界）。"""
    if not notes or not notes.get("start_date") or not notes.get("next_version_date"):
        return notes.get("start_date") if notes else None, None
    return notes["start_date"], _minus_day(notes["next_version_date"])


def find_version_notes(posts: list[dict]) -> list[dict]:
    """筛出窗口内所有停服更新公告（列表按时间倒序，最前面那条即当前版本）。

    要全部而不是只取最新：活动日期大量用「X.Y版本更新后 / X.Y版本结束」，
    上一个版本的活动还留在抓取窗口里、也还要靠它自己的总纲解出日期。
    """
    return [p for p in posts if is_version_notes(p.get("subject", ""))]


# 总纲正文是逐段 <p> 的 HTML。**段边界是活动名唯一可靠的切分点**：fetch_post 给的 text 是
# 压平过的（空格分隔一整段），名字后面紧跟描述、没有分隔符，而名字里可能有空格
# （`回归丽都 羽落重逢`）——所以这一段必须解析 content，不能解析 text。
RE_PARAGRAPH = re.compile(r"<p>(.*?)</p>", re.S)
RE_TAG = re.compile(r"<[^>]+>")

# 编号段标题（`一、全新代理人` …）。段号每版不同，所以只用来定界与取段名，不写死段号。
RE_NUMBERED_SECTION = re.compile(r"[一二三四五六七八九十]+、(.+?)\s*$")

ACTIVITY_SECTION = "全新活动"


def _paragraphs(content: str) -> list[str]:
    return [RE_TAG.sub("", p).strip() for p in RE_PARAGRAPH.findall(content or "")]


def _demote_quotes(name: str) -> str:
    """活动名 → 公告 subject 里的写法：内层「」降级成『』。

    总纲写 `• 「嗯呢」大派送！`，而活动自己的公告标题是 `「『嗯呢』大派送！」活动说明`
    （§2.2 实测两处）。中文引号的嵌套惯例：外面再包一层「」时内层要降级。数据文件用的
    是后一种，所以这里必须转——否则同一条活动在总纲与公告下有两个名字，去重主键
    （keys.event_key）失配，总纲落盘的那条会被当成另一条活动，而 apply_events 只认主键
    → 插一条重复。
    """
    return name.replace("「", "『").replace("」", "』")


def parse_version_activities(content: str, versions: dict) -> list[dict]:
    """总纲 `X、全新活动` 段列出的活动 → [{name, title, start_date, end_date}]。

    总纲按版本**逐个列出全部活动**（名字 + `活动时间：`，一个都不漏），但给不出**类型**，
    也没有配图（活动段实测 0 张图）与公告全文描述——那三样只有活动自己的活动说明公告才有。
    所以这一段的价值是**提前**：总纲比活动公告早得多（3.2 里「惊喜放映企划」早 12 天、
    「数据悬赏-实战模拟」早 35 天），活动因此能在版本更新当天就挂上日历。

    段在下一个编号段（3.1 是 `八、全新玩法`）处结束。日期复用 resolve_period，与公告同一套。
    """
    ps = _paragraphs(content)
    heads = [i for i, p in enumerate(ps)
             if (m := RE_NUMBERED_SECTION.match(p)) and m.group(1) == ACTIVITY_SECTION]
    if not heads:
        return []
    j = heads[0]
    k = j + 1
    while k < len(ps) and not RE_NUMBERED_SECTION.match(ps[k]):
        k += 1

    out: list[dict] = []
    for p in ps[j + 1:k]:
        if p.startswith("• "):
            name = _demote_quotes(p[2:].strip())
            out.append({"name": name, "title": f"「{name}」",
                        "start_date": None, "end_date": None})
        elif out and out[-1]["start_date"] is None and p.startswith("活动时间："):
            out[-1]["start_date"], out[-1]["end_date"] = resolve_period(
                p[len("活动时间："):], versions)
    return out


# ─── 卡池（限时频段）─────────────────────────────────────

# 共用时间段：「本期代理人与音擎调频活动时间为：A ~ B，包含如下内容」
RE_BANNER_SHARED = re.compile(
    r"本期代理人与音擎调频活动时间为\s*[：:]\s*(.*?)包含如下内容", re.S)
# 逐段排版：每个「X」调频活动 自成一个段落
RE_BANNER_SECTION = re.compile(
    r"「[^」]{1,20}」调频活动(.*?)(?=「[^」]{1,20}」调频活动|$)", re.S)
# 「限定S级代理人 [名字(属性·特性)]」或「可自选的限定S级代理人包含： [A(…)]、[B(…)]」
# 方括号里带圆括号，所以字符类只排除方括号
RE_BANNER_AGENT = re.compile(
    r"限定S级代理人\s*(?:包含\s*[：:])?\s*((?:\[[^\[\]]+\]\s*[、,]?\s*)+)")
# 括号里带「·」的才是代理人（音擎写 [名字(特性)]，没有「·」）
RE_BRACKET_AGENT = re.compile(r"\[([^\[\]（()]+)\([^)\]]*·[^)\]]*\)")


def is_banner(subject: str) -> bool:
    return rules.BANNER_KEYWORD in (subject or "")


def _agent_names(text: str) -> list[str]:
    """按正文出现顺序取全部限定S级代理人名（去重）。

    音擎靠「括号里没有 ·」排除，默认A级代理人靠「不在『限定S级代理人』这个词后面」
    排除——两条判据都是格式判据，不是名字名单。
    """
    out: list[str] = []
    for run in RE_BANNER_AGENT.findall(text or ""):
        for name in RE_BRACKET_AGENT.findall(run):
            if name not in out:
                out.append(name)
    return out


def _banner_entry(names: list[str], start, end) -> list[dict]:
    if not names or not (start and end):
        return []
    return [{"title": rules.BANNER_TITLE_PREFIX + "/".join(names),
             "start_date": start, "end_date": end}]


def parse_banner_body(text: str, versions: dict) -> list[dict]:
    """解析卡池公告正文 → [{title, start_date, end_date}]，可能多条。

    标题沿用数据文件既有的手工格式「调频活动-A/B/…」（不改成官方频段名），
    限定S级代理人的名字只能从正文里取——所以这条线省不掉抓正文的请求。

    两种排版（都实测过）：
    - 共用时间段：开头写「本期代理人与音擎调频活动时间为 …，包含如下内容」，
      全公告一个时间段 → 一条（3.2上期、3.1下期）。
    - 逐段各写：每个「X」调频活动 自带一行「活动时间」→ 各段一条，因为同一公告里
      可以有两档不同的结束日（3.1 首期：复乐园到 09-08、霓色天使到 08-19）。
    """
    text = text or ""
    m = RE_BANNER_SHARED.search(text)
    if m:
        start, end = resolve_period(m.group(1), versions)
        return _banner_entry(_agent_names(text), start, end)

    out: list[dict] = []
    for body in RE_BANNER_SECTION.findall(text):
        m = re.search(r"活动时间\s*[：:]\s*(.*?)(?=活动期间|※|$)", body, re.S)
        if not m:
            continue
        start, end = resolve_period(m.group(1), versions)
        out += _banner_entry(_agent_names(body), start, end)
    return out


def find_banners(posts: list[dict]) -> list[dict]:
    return [{"subject": p["subject"], "post_id": p.get("post_id", ""),
             "created_at": p.get("created_at", 0)}
            for p in posts if is_banner(p.get("subject", ""))]


# ─── 活动 ────────────────────────────────────────────────

RE_EXTERNAL_LINK = re.compile(r"https?://[^\s\"'<>()]{6,}")


def is_activity(subject: str) -> bool:
    """活动公告一律是「「活动名」活动说明」，拿后缀当判据。

    名单式的排除词会过期（写新公告的人不会通知我们），后缀是格式约定。
    实测被它挡掉的：商城上新说明、新剧情：…、云·绝区零版本更新说明、
    已知问题及游戏优化说明、「迷宫诡域」常驻玩法开启。
    """
    s = subject or ""
    if not s.endswith(rules.ACTIVITY_SUFFIX):
        return False
    return not any(k in s for k in rules.EXCLUDE) and _name_of(s) is not None


def find_activities(posts: list[dict]) -> list[dict]:
    out = []
    for p in posts:
        s = p.get("subject", "")
        if not is_activity(s):
            continue
        name = _name_of(s)
        out.append({"title": f"「{name}」", "name": name,
                    "post_id": p.get("post_id", ""), "created_at": p.get("created_at", 0)})
    return out


def has_external_link(content: str) -> bool:
    """正文里除米游社图床以外的链接 → 网页活动。

    实测「法厄同年度大揭秘」正文里的活动入口是 `>>>点击前往参与活动<<<` 指向
    https://mhyurl.cn/…（短链，跳转页每次不同），其余活动只有 upload-bbs 的配图。
    """
    return any(rules.IMAGE_HOST not in u for u in RE_EXTERNAL_LINK.findall(content or ""))


def classify_activity(text: str, content: str) -> str:
    """活动类型。四个类型全部由**正文**派生——总纲判不出来：它既不写活动入口链接，
    也不写「活动常驻说明」段（实测两份总纲里都没有这些标记），所以类型和日期必须
    分别取自两个来源。"""
    if has_external_link(content):
        return "网页活动"
    if any(k in (text or "") for k in rules.PERMANENT_MARKERS):
        return "版本大活动"
    if any(k in (text or "") for k in rules.LOGIN_KEYWORDS):
        return "登录福利"
    return "常规活动"


def parse_activity_body(text: str, versions: dict) -> dict:
    """解析活动正文 → {description, start_date?, end_date?}。

    description 取整段正文（与数据文件里多数条目一致）。
    时间段只取【活动时间】到下一个【（或 ※）之前那一段：丽都城募的
    「※ 2026/10/19 02:59 将关闭…购买」紧跟其后，不切掉就会把那个时刻当成终点。
    """
    result: dict = {"description": (text or "").strip() or None}
    m = re.search(re.escape(rules.ACTIVITY_SECTION) + r"\s*(.*?)(?=【|※|$)", text or "", re.S)
    if not m:
        return result
    start, end = resolve_period(m.group(1), versions)
    if start:
        result["start_date"] = start
    if end:
        result["end_date"] = end
    return result


# ─── 大月卡（丽都城募）────────────────────────────────────

def is_battle_pass(subject: str) -> bool:
    return rules.BATTLE_PASS_KEYWORD in (subject or "")


def find_battle_passes(posts: list[dict]) -> list[dict]:
    out = []
    for p in posts:
        s = p.get("subject", "")
        if not is_battle_pass(s):
            continue
        m = RE_VERSION.search(s)
        out.append({"subject": s, "post_id": p.get("post_id", ""),
                    "created_at": p.get("created_at", 0),
                    "version": m.group(1) if m else None})
    return out


# ─── B站前瞻 ─────────────────────────────────────────────

# 「将于8月28日 19:30正式开启」——需要一条带**具体月日**的预告
RE_LIVESTREAM_DATE = re.compile(r"\d{1,2}\s*月\s*\d{1,2}\s*日")


def find_livestreams(items: list[dict]) -> list[dict]:
    """前瞻预告。复用 common.bilibili.parse_livestream（版本号 / 版本名 / 日期补年），
    但多一道闸门：只认带具体「X月X日」的那条动态。

    B站官方号在前瞻当天会发「…将于今晚19:30开启！」、前瞻结束后再发一条同名
    「…前瞻特别节目」，两条都含「前瞻特别节目」+「开启」，原神那份判据会一并收下，
    而它们都没有日期。绝区零不另写解析，只加这道日期闸。
    """
    out = []
    for d in items:
        if not RE_LIVESTREAM_DATE.search(d.get("text") or ""):
            continue
        r = bilibili.parse_livestream(d.get("text") or "", d.get("pub_ts"))
        if not r or not r.get("date"):
            continue
        r["id"] = d.get("id", "")
        out.append(r)
    return out
