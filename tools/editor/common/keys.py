"""活动条目的去重主键（唯一身份）。

「两个条目是不是同一个活动」只由主键决定，与日期无关——日期是**值**，会被校准修改；
主键是**身份**，一旦确定就不再变。混用两者会导致：日期一改，旧条目认不出来 → 重复插入。

唯一的**有意破例**是活动类（见下表第 2 行与 ACTIVITY_TYPES）：标题会跨版本重名，不带日期
就会把新一期静默丢掉。代价靠 find_duplicate 的日期兜底（口径按端点，见 EXACT_FALLBACK_GAMES）
与「排除日期会被校准改写的类型」封住；周期性事件那几行是同一类破例，只是范围更窄（标题一字不变）。

主键只取不含解析假设的字段。标题格式会随版本变（武器池 7.0 是
`祈愿：「长柄武器·血染荒城」…`，7.1 变成 `「神铸赋形」祈愿：…`），所以能不用
括号解析就不用：

  卡池 / 版本大活动 / 大月卡                        → (类型, 完整标题)
  未定 卡池（返场时标题逐字相同）                    → (类型, 完整标题, 开始日期)，见 DATED_BANNER_GAMES
  常规活动 / 登录福利 / 网页活动                    → (完整标题, 开始日期)（类型要等正文，且会跨版本重名）
  幽境危战                                        → 米游社公告 post_id（标题每期一字不变）
  版本更新 / 前瞻直播                              → (类型, 版本号)
  深境螺旋 / 幻想真境剧诗                          → (标题, 开始日期)（无公告，标题自带 MMDD，带年份防跨年撞）
  「位面分裂」/「花藏繁生」/「异器盈界」             → (标题, 开始日期)（每期标题一字不变）

版本类事件另加一道日期兜底：主键里的版本号是朴素 +0.1 预测（`_version_number`），
且标题一旦生成就不再改号，所以版本号可能预测错；此时主键失配，靠日期兜底仍能认出
是同一事件而不是插一条重复。兜底的宽严按端点分（EXACT_FALLBACK_GAMES）：默认是
「±7 天内同类型/同名」，不接校准的端点只认同名同起日或同源帖。
"""

from __future__ import annotations

import datetime
import re

# 标题完全不变、只能靠公告 id 区分的事件
POST_ID_KEYED_TITLES = {"「幽境危战」"}

# 标题每期一字不变、只能靠日期区分的周期性事件（主键需带日期）
#   原神：标题自带 MMDD（深境螺旋0716），带上日期是为了防跨年撞
#   星铁：双倍掉落类，连括号整串都不变（「位面分裂」），只能靠日期区分
DATED_KEYED_PREFIXES = (
    "深境螺旋", "幻想真境剧诗",                        # 原神
    "「位面分裂」", "「花藏繁生」", "「异器盈界」",       # 星铁
)

# 卡池身份带开始日期的游戏。卡池一般不带日期（标题里就有角色名与池名，不会重名），
# 但这几个游戏的卡池**会返场**：未定的帖子标题里直接写着 `限时返场` / `往期复刻`，
# 同一池子再开的标题逐字相同 —— 两期可能相隔几十天，±7 天兜底救不了，
# 不带日期的话返场那一期会被当成「已录过」静默丢掉。
# ⚠️ 这是前瞻性判据：窗口内还没撞上（手工数据里 `「NXX-冰原上的审判」活动女神之影
# 限时复刻` 是已踩到边界的那条），但返场一旦发生就是静默丢数据。
DATED_BANNER_GAMES = {"tears-of-themis"}

# 版本类事件：主键用版本号
VERSION_KEYED_TYPES = {"版本更新", "前瞻直播"}

# 活动公告最终可能落在的类型。抓取预筛要用的就是这一组：预筛时**类型还没定**
# （绝区零/星铁要抓完正文才知道，原神还要等 B站动态合并），只能按标题认，少算一种
# 就会让已有的那类条目每轮都被多抓一次正文（实测漏掉版本大活动时星铁每轮多抓 2 条）。
ANNOUNCEMENT_ACTIVITY_TYPES = {"常规活动", "版本大活动", "登录福利", "网页活动"}

# 身份带日期的活动类 = 上面那组减去**日期会被校准**的（版本大活动走 B站活动动态）。
# 理由：类型不进主键，改为带开始日期。两个理由各缺一不可：
#
# 1. 类型可能后到。绝区零的版本更新公告（总纲）按版本列出了全部活动与活动时间，
#    但给不出类型（没有「活动常驻说明」/「丽都纪事」这类段标记，也没有活动入口链接），
#    只能先落一个默认类型、等这条活动自己的公告到了再订正。主键里带类型就认不出是
#    同一条，会插重复。
# 2. 去掉类型后，同名跨版本的活动会互吞。实测「全新放送」在 3.0 与 3.2 各有一期，
#    同名同类型，只能靠开始日期区分。
#
# 代价是日期成了身份的一部分：日期被改写后主键就失效（靠 find_duplicate 的日期兜底
# 认回）。所以日期会被校准改写的版本大活动不能进来——它改完就认不回，会插重复。
ACTIVITY_TYPES = ANNOUNCEMENT_ACTIVITY_TYPES - {"版本大活动"}

# 「待补全」标记：身份已定，但还有字段要等外部来源补。目前只有一个来源——绝区零的活动
# 先由**总纲**落盘（总纲逐个列出活动名与活动时间，但给不出类型、配图与公告全文描述），
# 剩下的要等它自己的活动说明公告。
#
# 这类条目**必须**重新抓正文：不抓就拿不到那一轮才知道的类型与配图，而预筛跳过 = 不落盘
# = 那几样永远补不上。所以它是 likely_recorded 的一票否决。
PENDING_FIELD = "pending"

# 「待确认」标签：条目已落盘，但某个字段还没有权威来源确认，确认后由 `calibrate` 摘掉。
# 定义放这里、产出侧与清除侧都引用这里——2026-09-21 之前各写一份字面量，产出侧写的是
# `待确认`，清除侧只认 `待确认版本`，于是原神的标签永远摘不掉，成了永久徽章。
TAG_PENDING_VERSION = "待确认版本"   # 版本号 / 版本名为预测或占位（原神、星铁）
TAG_PENDING_TYPE = "待确认"          # 类型（版本大活动）由 B站多阶段动态判定（原神）
PENDING_TAGS = (TAG_PENDING_VERSION, TAG_PENDING_TYPE)

# 版本号预测错、或活动日期被人工订正时，同类型（活动类则同名）日期相差不超过这个
# 天数视为同一事件。**只给宽口径端点用**（见 EXACT_FALLBACK_GAMES）。
DATE_TOLERANCE_DAYS = 7

# 日期兜底取**精确口径**的端点：同名同起日，或同源帖（候选与条目指向同一篇公告）。
# 判据的出处是两条结构性差异，不是「未定特殊」：
#
#   1. 日期不会被 `calibrate` 自动改写（未定不接校准，裁定 19）—— 校准能把日期挪很远，
#      被校准改写的端点只能用「挨着」近似；
#   2. 一篇公告至多落出一条条目（未定一篇帖子解一条）—— 一篇公告落多条条目的端点里
#      （绝区零总纲），帖子 id 当不了身份判据。
#
# 未定两种都符合，所以人工订正日期后能靠**帖子 id 精确**认回，不需要模糊窗口。而模糊
# 窗口在未定只有假阳性，假阳性的后果是**静默吞掉一条活动**（2026-09-25 实测：9/17 与
# 9/20 两条同名不同期的活动互吞），比「多一条可见的重复」严重得多。
# ⚠️ 未定的调用方**必须传 game**（`apply_events` 传的是 `game_id`）：不传即按宽口径算。
EXACT_FALLBACK_GAMES = {"tears-of-themis"}


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


def event_key(event: dict, game: str | None = None) -> tuple | None:
    """返回条目的去重主键；身份判不出来时返回 None（调用方需容错）。

    `game` 只在 DATED_BANNER_GAMES 里那几个游戏上有影响（卡池要不要带日期）。
    **比对的两侧必须传同一个 game**，否则同一个卡池在候选侧与数据文件侧会算出
    两个主键，apply_events 认不出来就插重复。
    """
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

    if etype == "卡池" and game in DATED_BANNER_GAMES:
        return (etype, title, event.get("start_date") or "")

    if etype in ACTIVITY_TYPES:
        return (title, event.get("start_date") or "")

    return (etype, title)


def _date(value) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def find_duplicate(candidate: dict, existing: list[dict], game: str | None = None) -> dict | None:
    """在 existing 里找与 candidate 同身份的条目，没有则返回 None。

    先按主键精确匹配；主键带日期的两类（版本类与活动类）再补一道兜底：主键失配时
    看同类型（版本类）/ 同名（活动类）条目里有没有认得出是同一事件的。兜底是必需的
    ——版本号是朴素 +0.1 预测，活动的开始日期会被人工订正（本仓库就这么干过），
    一旦值被改写，带日期的主键就认不回来了，没有兜底就会插重复。

    认得出的判据按端点分（EXACT_FALLBACK_GAMES）：

      - 宽口径（默认，三端）：开始日期相差 ≤7 天；
      - 精确口径（未定）：**同名同起日**，或**同源帖** —— 候选与条目指向同一篇公告
        （`post_id` vs `source_url`）。未定不接校准、一篇公告至多一条条目，人工订正
        日期又是在那篇帖子产出的条目上做的，所以帖子 id 就是精确判据，不需要窗口。

    `game` 需与 event_key 的同一侧传一致（见 event_key）。
    """
    key = event_key(candidate, game)
    if key is not None:
        for e in existing:
            if event_key(e, game) == key:
                return e

    etype = candidate.get("type")
    by_version = etype in VERSION_KEYED_TYPES
    # 兜底取**公告可能落到的全部活动类**，比身份集合宽一个「版本大活动」：它不能进主键
    # （日期会被校准改写），但正因为日期进不了主键，才最需要兜底——同一条活动的类型从
    # 常规活动变成版本大活动时主键会失配，兜底再把它排除掉，apply_events 就会插一条重复
    # （离线复现过：「悠悠律动舞力聚会」类型一变，find_duplicate 返回 None）。
    #
    # 未定卡池同理，也要放进兜底：它的主键带日期（DATED_BANNER_GAMES），日期一旦被人工
    # 订正主键就失配，而卡池不在 ANNOUNCEMENT_ACTIVITY_TYPES 里，不放行就会插重复。
    dated_banner = etype == "卡池" and game in DATED_BANNER_GAMES
    if not by_version and not dated_banner and etype not in ANNOUNCEMENT_ACTIVITY_TYPES:
        return None
    d = _date(candidate.get("start_date"))
    if d is None:
        return None
    strict = game in EXACT_FALLBACK_GAMES
    pid = post_id_of(candidate)
    for e in existing:
        # 版本类按类型认，活动类按标题认——这两类的主键里分别含版本号 / 标题
        same = e.get("type") == etype if by_version else e.get("title") == candidate.get("title")
        if not same:
            continue
        # 同源帖：只对精确口径开放。宽口径端点里一篇公告会落出多条条目（绝区零总纲），
        # 帖子 id 在那里当不了身份判据。
        if strict and pid and post_id_of(e) == pid:
            return e
        ed = _date(e.get("start_date"))
        if ed and abs((ed - d).days) <= (0 if strict else DATE_TOLERANCE_DAYS):
            return e
    return None


def likely_recorded(candidate: dict, existing: list[dict]) -> bool:
    """**不抓正文**就判断「这条大概已经录过了」——给抓取预筛用，比 find_duplicate 松。

    活动类的日期写在正文里，候选侧只有列表给的标题、公告 id 与**发布时间**，拿不到日期
    就没法按主键比对，只能按标题认。而标题会跨版本重名（见 ANNOUNCEMENT_ACTIVITY_TYPES），
    一律认成同一条会把新一期漏掉——预筛跳过等于不落盘，是真丢数据。所以再加一道闸：

        同名条目的开始日期不早于公告发布日，才算同一条。

    活动公告总在活动开始前发出（实测 20 条里 19 条如此，中位提前 2 天），所以列表里刚
    出现的公告，对应的活动不可能早就开始过；上一个版本那一期的开始日期远在发布日之前，
    正好被这道闸挡掉。拿不准（没有发布日期）就返回 False 去抓正文：多一次请求可以接受，
    漏一条不行。
    """
    created = candidate.get("created_at")
    if not created:
        return False
    try:
        published = datetime.datetime.fromtimestamp(int(created)).date()
    except (TypeError, ValueError, OSError):
        return False
    for e in existing:
        if e.get("type") not in ANNOUNCEMENT_ACTIVITY_TYPES \
                or e.get("title") != candidate.get("title"):
            continue
        if e.get(PENDING_FIELD):
            return False        # 待补全：类型/配图还等这一轮的正文（见 PENDING_FIELD）
        start = _date(e.get("start_date"))
        if start and start >= published:
            return True
    return False
