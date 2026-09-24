"""星铁活动维护管线：抓公告 → 解析 → 校准 → 写 extracted_hsr.json。

与原神侧的 genshin/pipeline.py 是**并列的两条线**，不是同一套逻辑的参数化：两边公告的
段落标记、卡池标题来源、版本节奏都不同（见 rules.py）。真正通用的三个模块
（common/ 下的 yaml_io / keys / calibrate）直接复用，取色统一走 common/colors。

星铁的信息结构比原神清爽：每版本开服当天发的**版本更新说明**是一份总纲，版本名、
本版起止、下版本日期、高难四支的期名与日期、以及**本版全部活动与活动时间**
（`X、全新活动` 段）全在里面。所以这条线不用 inference.py——星铁的版本周期不固定
（4.4→4.5 是 42 天，4.5→4.6 是 33 天），「锚点 + 42×n」那种外推在这里是错的。
**版本周期表本身仍走原神那条路数**（由已确认的版本更新条目推，见 `_version_table`），
只是表里不套固定周期：相邻两次更新日相减就是版本长度。

活动那一整段走「总纲优先」（PLAN.md §1.2）：活动在版本更新当天先以默认类型 + pending
标记落盘，等它自己的公告发出来再由 correct_from_candidates 订正类型、补描述与配色。
run() 里因此有两条硬顺序——取色→订正→校准，理由写在取色那一步的注释里。
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

# 允许直接 `python starrail/pipeline.py`（此时 sys.path[0] 是本目录，找不到兄弟模块）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import winreg

# 凭据存注册表（setx 写的也是这里），须在 import bilibili / extractor 前读入 os.environ
# （见记忆 bili-sessdata-registry）。两个都可选，缺任何一个都不影响运行。
try:
    _k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
    for _name in ("BILI_SESSDATA", "MIYOUSHE_COOKIE"):
        try:
            os.environ[_name], _ = winreg.QueryValueEx(_k, _name)
        except OSError:
            pass
except OSError:
    pass

from common import bilibili, body_cache, calibrate, keys, yaml_io
from common.colors import pastel_from_url
from common.extractor import fetch_post, fetch_post_list
from starrail import parse, rules

GAME = rules.GAME
FALLBACK_COLOR = rules.FALLBACK_COLOR

# 产物写在自己目录下，与运行时的 cwd 无关
OUT_FILE = Path(__file__).resolve().parent / "extracted_hsr.json"

# 交给 apply_events 的字段白名单。`keys.PENDING_FIELD` **必须**在里面：apply_events 靠它把
# 「这条还缺公告才有的字段」写进数据文件，下一轮才据此必抓它的公告正文（keys.likely_recorded）
# 并由 correct_from_candidates 补齐。漏掉它，总纲优先整条路就是空转——活动照落盘，
# 但标记带不出去，描述与配色永远补不上。
OUT_FIELDS = ("title", "type", "start_date", "end_date", "tags", "color",
              "description", "post_id", keys.PENDING_FIELD)


# ─── 抓取记账 ────────────────────────────────────────────

# 正文抓取成败计数。无人值守运行后人工核查用：风控（retcode 1034）会让正文大面积
# 抓不到，条目因拿不到日期被日期闸丢弃，表现为「本轮 0 新增」，容易被误当成
# 「今天没有新活动」。日志里的这一行是分辨两者的第一依据。
FETCH_STATS = {"ok": 0, "fail": 0, "risk": 0, "skip": 0, "cache": 0}


def _count_fetch(fp):
    """记录一次正文抓取的成败。"""
    if fp and "error" not in fp:
        FETCH_STATS["ok"] += 1
        return
    FETCH_STATS["fail"] += 1
    if "1034" in ((fp or {}).get("error") or ""):
        FETCH_STATS["risk"] += 1


def _needs_body(event, existing, audit: bool = False):
    """该条目是否还需要抓正文。理由同 genshin/pipeline.py 的 _needs_body：正文只用于取日期/
    描述/配图，都是**新增**才需要的；已落盘的条目不必再抓，稳态请求数由此大降，
    而请求数正是米游社风控的主因。判定复用同一套 keys.find_duplicate，因此不会比
    apply_events 的去重更激进。

    活动条目的类型要到正文里才知道（「X.Y版本期间」→ 版本大活动），而主键里已经没有
    类型，所以不需要再逐个候选类型试——keys.likely_recorded 按标题认，一道闸就够。

    audit：活动公告专用（一帖多活动）。**已落盘**的活动公告也要读正文——被埋的那条活动的
    名字不在公告列表里（见 parse.parse_activity_bodies），不看正文就发现不了它。但也不是
    每轮都读，判据取自 body_cache.audit_state：
    - 从没审过（或记录过期）→ 抓一次；
    - 上次审出**还有块的日期解不出来**（`waiting`，多半在等版本周期表）→ 再读一次，
      正文在本机就是 0 请求，等那一版的日期一确认就落盘，随后自动转为跳过；
    - 全部块都落盘了 → 按原神那样跳过，连 TTL 都不等（2026-09-22 定）。
    其余调用点（卡池/大月卡）不带 audit——它们正文里没有「活动」可漏，多读一遍是白读。

    命中的条目打 `_body_skipped` 标记：它仍留在列表里参与校准（剪掉会丢校准依据），
    但没日期是正常的，日志不把它报成日期缺口。
    """
    if keys.find_duplicate(event, existing) is not None \
            or keys.likely_recorded(event, existing):
        pid = event.get("post_id")
        if audit:
            state = body_cache.audit_state(pid)
            if state is None or state.get("waiting"):
                return True
        event["_body_skipped"] = True
        FETCH_STATS["skip"] += 1
        return False
    return True


def _fetch_text(post_id):
    """抓一条公告正文，返回 (text, images)；失败返回 (None, [])。

    本机缓存里有未过期的正文就直接用（见 common/body_cache）。
    """
    hit = body_cache.get(post_id)
    if hit is not None:
        FETCH_STATS["cache"] += 1
        return hit.get("text") or "", hit.get("images") or []
    fp = fetch_post(post_id, GAME)
    _count_fetch(fp)
    if not fp or "error" in fp:
        return None, []
    text, images = fp.get("text") or "", fp.get("images") or []
    body_cache.put(post_id, text=text, images=images)
    return text, images


# ─── 版本 ────────────────────────────────────────────────

def _next_version_number(ver: str) -> str | None:
    """4.5 → 4.6。只用于版本更新说明给了「下版本日期」却没给版本号时的占位，
    是个朴素 +0.1 预测（跨大版本如 4.9→5.0 会猜错，靠 keys 的同类型 7 天兜底认回）。"""
    try:
        major, minor = ver.split(".")
        return f"{major}.{int(minor) + 1}"
    except (AttributeError, ValueError):
        return None


def _minus_day(iso: str | None) -> str | None:
    if not iso:
        return None
    return (datetime.date.fromisoformat(iso) - datetime.timedelta(days=1)).isoformat()


def _version_table(entries) -> dict:
    """版本周期表 {版本号: (起, 止)}，由**版本更新条目**推出：止 = 下一条的日期 − 1 天。

    口径与 genshin.inference.extract_version_dates 一致（2026-09-22 改）：版本更新日一经确认
    ——条目落盘并校准——它就是权威值，活动只需查表，不必每轮再从版本更新说明正文里重算一遍。
    原文表是「当轮中间产物」，于是窗口里每份旧说明都得读；改由条目推之后，那几份不用再读，
    也不再受抓取窗口长度限制（相对写法可以指向很早的版本，如 `命运赠礼` 的「4.4版本期间」）。

    entries：数据文件里的条目 + 本轮的候选（`_build_version_events` 的产出）。候选写在后面，
    同名版本的旧值会被覆盖——更新预告 / B站上线动态给出的**修正日期**因此能生效。

    假定「表内相邻即实际相邻」：没落盘的版本不会出现在表里，也就不会被活动引用。星铁版本
    周期不固定，这里不做 42 天那种兜底外推（见模块说明），所以最后一条的止是 None。
    """
    dated: dict[str, str] = {}
    for e in entries:
        if e.get("type") != "版本更新":
            continue
        ver = keys.version_of(e.get("title", ""))
        if ver and e.get("start_date"):
            dated[ver] = e["start_date"]
    ordered = sorted(dated.items(), key=lambda kv: kv[1])
    out: dict[str, tuple] = {}
    for i, (ver, date) in enumerate(ordered):
        nxt = ordered[i + 1][1] if i + 1 < len(ordered) else None
        out[ver] = (date, _minus_day(nxt))
    return out


def _collect_notes(posts) -> tuple[dict | None, str | None]:
    """当前版本的版本更新说明 → (notes, text)；一份都解不出来时 (None, None)。

    只读**最新那一份**。窗口里旧版本的说明原先也要读，唯一用途是填版本周期表，而那张表现在
    由 `_version_table` 从条目推。总纲活动段、高难四支、版本名都在当前这一份里，且每版本都是
    新内容——这一份仍然要抓。返回的 text 给总纲活动段用：那段要解析 HTML content 之外的原文
    （活动段在 text 里压平成一行，`■名 … 活动时间：…`，靠 `■` 切条即可）。

    列表按时间倒序（parse.find_version_notes），第一条即当前版本；抓不到或解析不了的往后顺延。
    """
    for p in parse.find_version_notes(posts):
        text, _ = _fetch_text(p["post_id"])
        if text is None:
            continue
        n = parse.parse_version_notes(text, p["subject"])
        if not n:
            continue
        n["post_id"] = p["post_id"]
        return n, text
    return None, None


def _build_version_events(notes, preview, launches) -> list[dict]:
    """版本更新条目：本版 + 下版。

    日期优先级：米游社更新预告（T−2，最准）> B站上线动态 > 版本更新说明给出的下版本日期。
    只有日期、没有版本名时落一条**占位**（标 待确认版本）：说明是版本开服当天发的，
    此时 B站前瞻还没到，但下个版本的日子已经定了，值得先让日历显示出来。等更新预告或
    B站上线动态一到，calibrate 会把标题补全并摘掉标记（标题就是 VALUE_FIELDS 之一）。
    """
    known: dict[str, dict] = {}

    # 低 → 高优先级依次覆盖
    if notes and notes.get("version") and notes.get("start_date"):
        known[notes["version"]] = {"date": notes["start_date"], "name": notes.get("name")}
    if notes and notes.get("next_version_date"):
        nxt = _next_version_number(notes.get("version"))
        if nxt:
            known.setdefault(nxt, {})["date"] = notes["next_version_date"]
    for l in launches:
        known.setdefault(l["version"], {}).update(date=l["date"], name=l["name"])
    if preview:
        known.setdefault(preview["version"], {}).update(
            date=preview["date"], name=preview["name"])

    out = []
    for ver, info in known.items():
        date = info.get("date")
        if not date:
            continue
        e = {"title": rules.VERSION_UPDATE_TITLE.format(ver=ver, name=info["name"])
             if info.get("name") else rules.VERSION_PLACEHOLDER_TITLE.format(ver=ver),
             "type": "版本更新", "start_date": date, "end_date": date,
             "color": rules.COLORS["版本更新"]}
        if not info.get("name"):
            e["tags"] = [rules.TAG_PENDING_VERSION]
        out.append(e)
    return out


def _build_livestreams(lives) -> list[dict]:
    """前瞻直播条目（B站前瞻预告动态，日期即直播日）。"""
    return [{"title": rules.LIVESTREAM_TITLE.format(ver=l["version"], name=l["name"]),
             "type": "前瞻直播", "start_date": l["date"], "end_date": l["date"],
             "color": rules.COLORS["前瞻直播"]}
            for l in lives]


# ─── 高难 ────────────────────────────────────────────────

def _endgame_title(mode: str, name: str) -> str:
    return f"{mode}·{name}"


def _endgame_dates(eg: dict, versions: dict, ver: str | None) -> tuple[str | None, str | None]:
    """高难一条的起止。说明里给了就用；异相仲裁只给期名——它的起止实测正好等于
    所在版本期间（4.4、4.5 两期都对得上），按版本周期表补。"""
    if eg.get("start_date") and eg.get("end_date"):
        return eg["start_date"], eg["end_date"]
    return versions.get(ver) or (None, None)


def _build_endgame_events(notes, versions) -> list[dict]:
    """高难四支。期名与日期都来自版本更新说明的「■玩法」段（那一份本来就要读：
    总纲活动段与版本名也在里面），只有「异相仲裁」的起止要另查版本周期表。"""
    if not notes:
        return []
    out = []
    for eg in notes.get("endgame", []):
        start, end = _endgame_dates(eg, versions, notes.get("version"))
        if not (start and end):
            continue
        out.append({"title": _endgame_title(eg["mode"], eg["name"]), "type": "高难挑战",
                    "start_date": start, "end_date": end,
                    "color": rules.COLORS.get(eg["mode"], FALLBACK_COLOR),
                    "post_id": notes.get("post_id")})
    return out


def _build_sources(notes, preview, lives, versions) -> dict:
    """汇总权威值索引，供 calibrate 核对**已有**条目（只改值，不新增）。

    版本更新 / 前瞻直播走 calibrate.sources_from（机制与原神共用，只是标题里的
    游戏名不同——title 也在被写回的字段里，拼错一个字就会把已有标题改坏）。
    高难由版本更新说明直接给，是这条管线里唯一的权威来源。
    """
    sources = calibrate.sources_from(lives, preview, game_name=rules.GAME_TITLE)
    if notes:
        for eg in notes.get("endgame", []):
            start, end = _endgame_dates(eg, versions, notes.get("version"))
            if not (start and end):
                continue
            title = _endgame_title(eg["mode"], eg["name"])
            sources[("高难挑战", title)] = {
                "title": title, "start_date": start, "end_date": end,
                "source": "米游社版本更新说明",
            }
    return sources


# ─── 活动 / 卡池 / 大月卡 ─────────────────────────────────

def _activity_dates(body: dict, versions: dict) -> tuple[str | None, str | None]:
    """一条活动的起止。绝对日期解析器已算完，两种相对写法在这里按版本周期表补。

    版本周期算不全时（如「4.6版本结束前」而 4.6 那条版本更新条目还没落盘）终点留空，
    由日期闸丢掉整条——公告还留在抓取窗口里，等下个版本的日期确认后自然被收进来。
    这里不猜终点：宁可日历上晚几天出现，也不要一整段错日期（与 _version_table 同一口径）。
    """
    ver = body.get("version_period")
    if ver:
        return versions.get(ver) or (None, None)
    start, end = body.get("start_date"), body.get("end_date")
    before = body.get("version_end_before")
    if before:
        end = (versions.get(before) or (None, None))[1]
    return start, end


def _build_activities(posts, versions, existing) -> list[dict]:
    """常规活动 / 版本大活动。标题统一为「活动名」（最外层「」）。

    一篇公告可能挂着多条活动（见 parse.parse_activity_bodies），所以这里逐块产出；
    每条都带 post_id，订正时按它回抓正文。

    versions：全部版本的 (起, 止) 表（`_version_table`）。相对写法可能指向**上几版**
    （「4.4版本期间」在 4.5 当口出现）；数据文件里的版本更新条目是累计的，那些版本的周期
    还在表里——这一点比原先「只认窗口里那几份说明」更稳。

    `表必须含全部版本` 的实证：幻造 那篇公告里「命运赠礼」写 `■活动时间 4.4版本期间`，
    而 4.4 早已不是当前版本——只看当前版本就会落空、白丢一条有日期的活动。
    """
    out = []
    for a in parse.find_activities(posts):
        if not _needs_body(a, existing, audit=True):
            continue
        # 抓之前先记「审过」（waiting=False）：抓失败的也要算，否则风控期间每轮重试同一批
        # 公告；解析成功后再按实际结果改写（见 _needs_body）
        body_cache.mark_audited(a["post_id"], waiting=False)
        text, images = _fetch_text(a["post_id"])
        if text is None:
            continue
        blocks = parse.parse_activity_bodies(text, a["name"])
        waiting = False
        for body in blocks:
            e = {"title": f"「{body['name']}」", "type": "常规活动",
                 "post_id": a["post_id"], "description": body.get("description")}
            if body.get("version_period") or body.get("version_end_before"):
                # 时段挂在版本上（版本期间 / 版本结束前）的就是版本大活动——沿用既有判据
                e["type"] = "版本大活动"
            e["start_date"], e["end_date"] = _activity_dates(body, versions)
            e["images"] = images
            out.append(e)
            if not (e["start_date"] and e["end_date"]):
                # 有块这轮解不出日期（多半在等版本表）→ 下轮还要再看这篇。整条仍照原样留着，
                # 由日期闸丢弃并在日志里报出来——「缺口可见」比「少读一次」重要
                waiting = True
        if waiting or not blocks:
            # 一条都没解析出来也记 waiting（格式变了、或抓回来的是残页）——多读一次才可能自纠
            body_cache.mark_audited(a["post_id"], waiting=True)
    return out


def _activities_from_notes(notes, text, versions) -> list[dict]:
    """当前版本总纲 `X、全新活动` 段列出的活动 → 候选（类型等公告订正）。

    notes / text：当前版本的版本更新说明（`_collect_notes` 的产出）。

    这是 PLAN.md §1.2 的「总纲优先」：活动在版本更新当天就落盘，比它自己的公告早 15 天。
    代价是总纲给不出类型，所以先落默认类型 + `keys.PENDING_FIELD` 标记——标记是那条路的
    开关：预筛（keys.likely_recorded）见到它就不跳过正文，抓到公告后由
    calibrate.correct_from_candidates 把类型/描述/配色补齐并清掉标记。

    **只收当前版本那一份总纲**（2026-09-21 定）：窗口里通常还留着上一版的总纲，但它的活动
    要么已经落盘、要么永远不会落盘，而从它产候选有实测风险——4.4 的总纲把那条联动活动写作
    `■命运/银河铁道之夜`，公告与数据文件里都叫 `「幻造：圣杯战争」`（同一活动、名字不同），
    按标题去重认不出来，会插一条重复。旧版本的那几份现在连正文都不再抓（`_collect_notes`）。
    """
    if not notes or text is None:
        return []
    out: list[dict] = []
    for a in parse.parse_version_activities(text, versions, notes.get("version")):
        if not (a.get("start_date") and a.get("end_date")):
            continue     # 日期解不出来的不进候选（与日期闸同一判据）
        e = {"title": a["title"], "type": a.get("type") or calibrate.DEFAULT_ACTIVITY_TYPE,
             "start_date": a["start_date"], "end_date": a["end_date"]}
        if a.get("description"):
            e["description"] = a["description"]
        if not a.get("type"):
            # 类型还要等活动自己的公告来订正，才打标记。登录福利那条（巡星之礼）没有自己的
            # 公告——解析器已从总纲本文判出类型与描述，**不能**打标记：标记没人来清，
            # 会永久留在数据文件里，还要让预筛每轮去抓一篇不存在的正文。
            e[keys.PENDING_FIELD] = "总纲"
        out.append(e)
    return out


def _build_banners(posts) -> list[dict]:
    """卡池。星铁的卡池公告标题只有「（其一/其二）」，5 星名全在正文里，所以标题必须
    抓完正文才能拼——预筛在这里省不掉请求（每版本 2~3 条公告，量很小）。

    同一期卡池会在「其一」「其二」里各出现一次（姬子•启行整版都在池，两篇都写了它），
    所以按标题去重，免得 extracted_hsr.json 里全是重复行、人工核对时看不清。
    """
    out: dict[tuple, dict] = {}
    for b in parse.find_banners(posts):
        text, images = _fetch_text(b["post_id"])
        if text is None:
            continue
        for p in parse.parse_banner_body(text):
            out.setdefault((p["title"], p["start_date"], p["end_date"]),
                           {"title": p["title"], "type": "卡池",
                            "start_date": p["start_date"], "end_date": p["end_date"],
                            "post_id": b["post_id"], "images": images})
    return list(out.values())


def _build_battle_passes(posts, existing) -> list[dict]:
    """无名勋礼（大月卡）。期名每版本都一样，标题必须带版本号，否则去重键会撞。"""
    out = []
    for b in parse.find_battle_passes(posts):
        if not b.get("version"):
            continue
        title = rules.BATTLE_PASS_TITLE.format(ver=b["version"])
        e = {"title": title, "type": "大月卡", "post_id": b["post_id"]}
        if not _needs_body(e, existing):
            continue
        text, _ = _fetch_text(b["post_id"])
        if text is None:
            continue
        body = parse.parse_activity_body(text)
        e["start_date"], e["end_date"] = body.get("start_date"), body.get("end_date")
        e["description"] = body.get("description")
        e["color"] = rules.COLORS["大月卡"]
        out.append(e)
    return out


# ─── 编排 ────────────────────────────────────────────────

def run():
    # 同一进程内可能多次调用（编辑器「自动化维护」可重复按），计数必须每轮归零
    FETCH_STATS.update(ok=0, fail=0, risk=0, skip=0, cache=0)

    events = yaml_io.load_events(GAME)
    posts = fetch_post_list(GAME, page_size=rules.PAGE_SIZE)
    # 列表里偶尔同一篇公告出现两次（实测「位面分裂」活动说明），去重免得白抓一次正文
    posts = list({p["post_id"]: p for p in posts}.values())

    # ① 版本更新说明（总纲）：只读当前版本那一份。版本周期表不在这里出（见 ④），
    #    所以窗口里旧版本的说明不必再读
    notes, notes_text = _collect_notes(posts)
    if notes:
        print(f"== 版本更新说明 == {notes['version']}版本「{notes.get('name') or '?'}」"
              f" → {notes.get('start_date')} ~ 下版本 {notes.get('next_version_date')}")

    # ② 更新预告（T−2，版本更新日最权威的来源）
    preview = None
    for p in parse.find_update_previews(posts):
        text, _ = _fetch_text(p["post_id"])
        if text is not None:
            preview = parse.parse_update_preview(text)
        break
    if preview:
        print(f"== 更新预告 == {preview['version']}版本「{preview['name']}」"
              f" → {preview['date']}")

    # ③ B站动态：前瞻直播 + 版本上线
    dyn = bilibili.fetch_dynamics(rules.BILI_UID, limit=rules.DYN_LIMIT)
    lives = parse.find_livestreams(dyn)
    launches = parse.find_launches(dyn)

    # ④ 版本周期表：由**已确认的版本更新条目**推（数据文件 + 本轮候选，见 _version_table）。
    #    必须排在活动之前——活动里的「N.N版本期间 / N.N版本结束前」全靠它换算成日期。
    version_events = _build_version_events(notes, preview, launches)
    versions = _version_table(events + version_events)
    if versions:
        print("== 版本期间 == " + "，".join(
            f"{v} {s} ~ {e}" for v, (s, e) in versions.items()))

    acts = (_build_activities(posts, versions, events)
            + _activities_from_notes(notes, notes_text, versions))
    # 同一活动可能两条候选都有：总纲列了全部活动，而它自己的公告发出来后就又多一条。
    # 按身份去重、留先出现的那条（公告那条：有真类型与描述，总纲那条只有默认类型）。
    deduped: dict = {}
    for a in acts:
        deduped.setdefault(keys.event_key(a) or (a.get("title"), a.get("start_date")), a)
    acts = list(deduped.values())
    all_events = (
        version_events
        + _build_livestreams(lives)
        + _build_endgame_events(notes, versions)
        + acts
        + _build_banners(posts)
        + _build_battle_passes(posts, events)
    )

    print(f"== 正文抓取 == 成功 {FETCH_STATS['ok']} / 失败 {FETCH_STATS['fail']}"
          + (f"（其中风控 1034: {FETCH_STATS['risk']}）" if FETCH_STATS["risk"] else "")
          + f" / 缓存命中 {FETCH_STATS['cache']} / 跳过正文 {FETCH_STATS['skip']}（已存在）")

    # 日期缺口的最后一道闸：缺日期的条目不进输出，apply_events 那边也会再挡一次
    dropped = [e for e in all_events if not (e.get("start_date") and e.get("end_date"))]
    reported = [e for e in dropped if not e.get("_body_skipped")]
    if reported:
        print("== 跳过（日期不完整）==")
        for e in reported:
            print(" x", e.get("title"), e.get("start_date") or "?", "~", e.get("end_date") or "?")
    all_events = [e for e in all_events if e.get("start_date") and e.get("end_date")]

    # 取色：高难/版本更新/前瞻/大月卡用固定色，其余按封面图取浅色。
    # 必须排在订正之前（订正补的「配色」正是这里的产物），也必须排在日期闸之后
    # （否则会给马上要丢掉的条目白下载一次封面图）。
    for e in all_events:
        if e.get("color"):
            continue
        imgs = e.get("images") or []
        e["color"] = pastel_from_url(imgs[0]) if imgs else FALLBACK_COLOR

    # 订正：类型可能后到——正文里没有「X.Y版本期间」时先落成常规活动、总纲落盘的还缺描述
    # 与配色，都要用本轮候选补。只可能往版本大活动方向订正，反向被 DEFAULT_ACTIVITY_TYPE
    # 护栏挡住。必须在校准之前：版本大活动的主键含类型，类型改对了校准才查得到来源。
    fixes = calibrate.correct_from_candidates(events, acts)

    # 校准：用权威来源核对已有条目（只改值 + 打 calibrated 标记，不新增）
    filled, changes = calibrate.calibrate(events, _build_sources(notes, preview, lives, versions))
    if fixes or changes:
        yaml_io.save_events(GAME, filled)
        if fixes:
            print("== 订正 ==")
            for c in fixes:
                print(" ~", c)
        if changes:
            print("== 校准 ==")
            for c in changes:
                print(" ~", c)

    out = [{k: e[k] for k in OUT_FIELDS if k in e} for e in all_events]
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"written {len(out)} entries → {OUT_FILE}")


def main():
    os.chdir(Path(__file__).resolve().parent.parent)
    run()


if __name__ == "__main__":
    main()
