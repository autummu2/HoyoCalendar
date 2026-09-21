"""星铁活动维护管线：抓公告 → 解析 → 校准 → 写 extracted_hsr.json。

与原神侧的 genshin/pipeline.py 是**并列的两条线**，不是同一套逻辑的参数化：两边公告的
段落标记、卡池标题来源、版本节奏都不同（见 rules.py）。真正通用的三个模块
（common/ 下的 yaml_io / keys / calibrate）直接复用，取色统一走 common/colors。

星铁的信息结构比原神清爽：每版本开服当天发的**版本更新说明**是一份总纲，版本名、
本版起止、下版本日期、高难四支的期名与日期全在里面。所以这条线不用 inference.py
——星铁的版本周期不固定（4.4→4.5 是 42 天，4.5→4.6 是 33 天），「锚点 + 42×n」那种
外推在这里是错的。
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

from common import bilibili, calibrate, keys, yaml_io
from common.colors import pastel_from_url
from common.extractor import fetch_post, fetch_post_list
from starrail import parse, rules

GAME = rules.GAME
FALLBACK_COLOR = rules.FALLBACK_COLOR

# 产物写在自己目录下，与运行时的 cwd 无关
OUT_FILE = Path(__file__).resolve().parent / "extracted_hsr.json"


# ─── 抓取记账 ────────────────────────────────────────────

# 正文抓取成败计数。无人值守运行后人工核查用：风控（retcode 1034）会让正文大面积
# 抓不到，条目因拿不到日期被日期闸丢弃，表现为「本轮 0 新增」，容易被误当成
# 「今天没有新活动」。日志里的这一行是分辨两者的第一依据。
FETCH_STATS = {"ok": 0, "fail": 0, "risk": 0, "skip": 0}


def _count_fetch(fp):
    """记录一次正文抓取的成败。"""
    if fp and "error" not in fp:
        FETCH_STATS["ok"] += 1
        return
    FETCH_STATS["fail"] += 1
    if "1034" in ((fp or {}).get("error") or ""):
        FETCH_STATS["risk"] += 1


def _needs_body(event, existing, alt_types=()):
    """该条目是否还需要抓正文。理由同 genshin/pipeline.py 的 _needs_body：正文只用于取日期/
    描述/配图，都是**新增**才需要的；已落盘的条目不必再抓，稳态请求数由此大降，
    而请求数正是米游社风控的主因。判定复用同一套 keys.find_duplicate，因此不会比
    apply_events 的去重更激进。

    alt_types：候选类型。活动条目的类型要到正文里才知道（「X.Y版本期间」→ 版本大活动），
    预筛时先把两种可能都试一遍，否则已落盘的版本大活动每轮都会被多抓一次。

    命中的条目打 `_body_skipped` 标记：它仍留在列表里参与校准（剪掉会丢校准依据），
    但没日期是正常的，日志不把它报成日期缺口。
    """
    for t in (event.get("type"),) + tuple(alt_types):
        if keys.find_duplicate({**event, "type": t}, existing) is not None:
            event["_body_skipped"] = True
            FETCH_STATS["skip"] += 1
            return False
    return True


def _fetch_text(post_id):
    """抓一条公告正文，返回 (text, images)；失败返回 (None, [])。"""
    fp = fetch_post(post_id, GAME)
    _count_fetch(fp)
    if not fp or "error" in fp:
        return None, []
    return fp.get("text") or "", fp.get("images") or []


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


def _version_period(ver: str | None, notes: dict | None) -> tuple[str | None, str | None]:
    """给定版本号，返回它的 (起, 止)。

    星铁版本周期不固定，起止只能由**相邻两次更新日**相减得出，而版本更新说明里正好
    有「本版开始」与「下版本日期」两个值。下个版本的终点要等它自己的说明（发布时
    它就是当前版本了），所以那时返回 (起, None)——调用方据此放弃本轮收录。
    """
    if not notes or not ver:
        return None, None
    if ver == notes.get("version"):
        return notes.get("start_date"), _minus_day(notes.get("next_version_date"))
    if ver == _next_version_number(notes.get("version")) and notes.get("next_version_date"):
        return notes["next_version_date"], None
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


def _endgame_dates(eg: dict, notes: dict) -> tuple[str | None, str | None]:
    """高难一条的起止。说明里给了就用；异相仲裁只给期名——它的起止实测正好等于
    所在版本期间（4.4、4.5 两期都对得上），按版本周期补。"""
    if eg.get("start_date") and eg.get("end_date"):
        return eg["start_date"], eg["end_date"]
    return _version_period(notes.get("version"), notes)


def _build_endgame_events(notes) -> list[dict]:
    """高难四支。期名与日期都来自版本更新说明的「■玩法」段，不需要抓正文。"""
    if not notes:
        return []
    out = []
    for eg in notes.get("endgame", []):
        start, end = _endgame_dates(eg, notes)
        if not (start and end):
            continue
        out.append({"title": _endgame_title(eg["mode"], eg["name"]), "type": "高难挑战",
                    "start_date": start, "end_date": end,
                    "color": rules.COLORS.get(eg["mode"], FALLBACK_COLOR),
                    "post_id": notes.get("post_id")})
    return out


def _build_sources(notes, preview, lives) -> dict:
    """汇总权威值索引，供 calibrate 核对**已有**条目（只改值，不新增）。

    版本更新 / 前瞻直播走 calibrate.sources_from（机制与原神共用，只是标题里的
    游戏名不同——title 也在被写回的字段里，拼错一个字就会把已有标题改坏）。
    高难由版本更新说明直接给，是这条管线里唯一的权威来源。
    """
    sources = calibrate.sources_from(lives, preview, game_name=rules.GAME_TITLE)
    if notes:
        for eg in notes.get("endgame", []):
            start, end = _endgame_dates(eg, notes)
            if not (start and end):
                continue
            title = _endgame_title(eg["mode"], eg["name"])
            sources[("高难挑战", title)] = {
                "title": title, "start_date": start, "end_date": end,
                "source": "米游社版本更新说明",
            }
    return sources


# ─── 活动 / 卡池 / 大月卡 ─────────────────────────────────

def _build_activities(posts, notes, existing) -> list[dict]:
    """常规活动 / 版本大活动。标题统一为「活动名」（最外层「」）。"""
    out = []
    for a in parse.find_activities(posts):
        a["type"] = "常规活动"
        if not _needs_body(a, existing, alt_types=("版本大活动",)):
            continue
        text, images = _fetch_text(a["post_id"])
        if text is None:
            continue
        body = parse.parse_activity_body(text)
        e = {"title": a["title"], "type": "常规活动", "post_id": a["post_id"],
             "description": body.get("description")}
        ver = body.get("version_period")
        if not ver:
            e["start_date"], e["end_date"] = body.get("start_date"), body.get("end_date")
        else:
            e["type"] = "版本大活动"
            # 版本周期算不全时（如「4.6版本期间」而 4.6 的说明还没发）起止留空，
            # 由日期闸拦下——公告还留在抓取窗口里，等它自己的说明发布后自然被收进来。
            # 这里不猜终点：宁可日历上晚几天出现，也不要一整段错日期。
            e["start_date"], e["end_date"] = _version_period(ver, notes)
        e["images"] = images
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
    FETCH_STATS.update(ok=0, fail=0, risk=0, skip=0)

    events = yaml_io.load_events(GAME)
    posts = fetch_post_list(GAME, page_size=rules.PAGE_SIZE)
    # 列表里偶尔同一篇公告出现两次（实测「位面分裂」活动说明），去重免得白抓一次正文
    posts = list({p["post_id"]: p for p in posts}.values())

    # ① 版本更新说明（总纲）
    notes = None
    for p in parse.find_version_notes(posts):
        text, _ = _fetch_text(p["post_id"])
        if text is not None:
            notes = parse.parse_version_notes(text, p["subject"])
            if notes:
                notes["post_id"] = p["post_id"]
        break
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

    all_events = (
        _build_version_events(notes, preview, launches)
        + _build_livestreams(lives)
        + _build_endgame_events(notes)
        + _build_activities(posts, notes, events)
        + _build_banners(posts)
        + _build_battle_passes(posts, events)
    )

    # 校准：用权威来源核对已有条目（只改值 + 打 calibrated 标记，不新增）
    filled, changes = calibrate.calibrate(events, _build_sources(notes, preview, lives))
    if changes:
        yaml_io.save_events(GAME, filled)
        print("== 校准 ==")
        for c in changes:
            print(" ~", c)

    print(f"== 正文抓取 == 成功 {FETCH_STATS['ok']} / 失败 {FETCH_STATS['fail']}"
          + (f"（其中风控 1034: {FETCH_STATS['risk']}）" if FETCH_STATS["risk"] else "")
          + f" / 跳过正文 {FETCH_STATS['skip']}（已存在）")

    # 日期缺口的最后一道闸：缺日期的条目不进输出，apply_events 那边也会再挡一次
    dropped = [e for e in all_events if not (e.get("start_date") and e.get("end_date"))]
    reported = [e for e in dropped if not e.get("_body_skipped")]
    if reported:
        print("== 跳过（日期不完整）==")
        for e in reported:
            print(" x", e.get("title"), e.get("start_date") or "?", "~", e.get("end_date") or "?")
    all_events = [e for e in all_events if e.get("start_date") and e.get("end_date")]

    # 取色：高难/版本更新/前瞻/大月卡用固定色，其余按封面图取浅色
    for e in all_events:
        if e.get("color"):
            continue
        imgs = e.get("images") or []
        e["color"] = pastel_from_url(imgs[0]) if imgs else FALLBACK_COLOR

    out = [{k: e[k] for k in ("title", "type", "start_date", "end_date", "tags",
                              "color", "description", "post_id") if k in e}
           for e in all_events]
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"written {len(out)} entries → {OUT_FILE}")


def main():
    os.chdir(Path(__file__).resolve().parent.parent)
    run()


if __name__ == "__main__":
    main()
