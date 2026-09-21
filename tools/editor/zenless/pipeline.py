"""绝区零活动维护管线：抓公告 → 解析 → 校准 → 写 extracted_zzz.json。

与 genshin/pipeline.py、starrail/pipeline.py 并列的第三条线。真正通用的模块
（common/ 下的 yaml_io / keys / calibrate / colors / bilibili）直接复用。

绝区零的信息来源分工（三条线里最清楚的一条）：

  停服更新公告（总纲）  版本更新日、版本终点、高难期数、**活动日期的相对写法**
  活动公告（各自）      标题、类型、日期、描述、配图
  限时频段公告          卡池标题（限定S级代理人名只在正文里）与日期
  B站官方账号           前瞻直播日期（米游社不发前瞻预告）

活动**类型**取不到总纲里：实测两份总纲都没有「活动常驻说明」/「丽都纪事」段，
也没有活动入口链接。所以总纲列出的活动先按默认类型落盘（`keys.PENDING_FIELD` 标记），
等它自己的活动说明公告到了再由 calibrate.correct_from_candidates 把类型/描述/配色补齐
——活动因此能在版本更新当天进日历，比它自己的公告早 12~35 天（见 PLAN.md §9）。
标题一律取自公告自己的 subject，总纲那条走 _demote_quotes 把内层「」降级成『』。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 允许直接 `python zenless/pipeline.py`（此时 sys.path[0] 是本目录，找不到兄弟模块）
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
from zenless import inference, parse, rules

GAME = rules.GAME
FALLBACK_COLOR = rules.FALLBACK_COLOR

# 产物写在自己目录下，与运行时的 cwd 无关
OUT_FILE = Path(__file__).resolve().parent / "extracted_zzz.json"


# ─── 抓取记账 ────────────────────────────────────────────

# 正文抓取成败计数。无人值守运行后人工核查用：风控（retcode 1034）会让正文大面积
# 抓不到，条目因拿不到日期被日期闸丢弃，表现为「本轮 0 新增」，容易被误当成
# 「今天没有新活动」。日志里的这一行是分辨两者的第一依据。
FETCH_STATS = {"ok": 0, "fail": 0, "risk": 0, "skip": 0}


def _count_fetch(fp):
    if fp and "error" not in fp:
        FETCH_STATS["ok"] += 1
        return
    FETCH_STATS["fail"] += 1
    if "1034" in ((fp or {}).get("error") or ""):
        FETCH_STATS["risk"] += 1


def _needs_body(event, existing):
    """该条目是否还需要抓正文。理由同 starrail/pipeline.py：正文只用于取日期/类型/
    描述/配图，都是**新增**才需要的；已落盘的条目不必再抓，稳态请求数由此大降，
    而请求数正是米游社风控的主因。

    活动类的类型要到正文里才知道（常驻说明/登录词/外链），而主键里已经没有类型，
    所以不需要再逐个候选类型试——keys.likely_recorded 按标题认，一道闸就够。

    命中的条目打 `_body_skipped` 标记：它仍留在列表里参与校准，但没日期是正常的，
    日志不把它报成日期缺口。
    """
    if keys.find_duplicate(event, existing) is not None \
            or keys.likely_recorded(event, existing):
        event["_body_skipped"] = True
        FETCH_STATS["skip"] += 1
        return False
    return True


def _fetch(post_id):
    """抓一条公告，返回 (text, images, content)；失败返回 (None, [], "")。

    网页活动的判据要看正文里的**原始外链**，所以 content 也一并返回。
    """
    fp = fetch_post(post_id, GAME)
    _count_fetch(fp)
    if not fp or "error" in fp:
        return None, [], ""
    return fp.get("text") or "", fp.get("images") or [], fp.get("content") or ""


# ─── 版本 ────────────────────────────────────────────────

def _collect_versions(posts):
    """抓窗口内所有停服更新公告 → ({版本号: (起, 止)}, 当前版本那份, {版本号: 正文}）。

    活动日期大量写成「X.Y版本更新后 / X.Y版本结束」，要按版本号查表；上一个版本的
    活动还留在抓取窗口里，所以它的总纲也得抓。窗口里一般只有两份总纲，成本可忽略。
    正文 HTML 一并带出，供 _activities_from_notes 解析活动段（text 压平过，解析不了）。
    """
    versions: dict = {}
    current: dict | None = None
    contents: dict = {}
    for p in parse.find_version_notes(posts):
        text, _imgs, content = _fetch(p["post_id"])
        if text is None:
            continue
        notes = parse.parse_version_notes(text, p["subject"])
        if not notes:
            continue
        notes["post_id"] = p["post_id"]
        versions[notes["version"]] = parse.version_period(notes)
        contents[notes["version"]] = content
        if current is None:          # 列表按时间倒序，第一条即当前版本
            current = notes
    return versions, current, contents


def _activities_from_notes(contents, versions):
    """总纲 `X、全新活动` 段列出的活动 → 候选（只有名字与日期，类型等公告订正）。

    这是 §9 的「总纲优先」：活动在版本更新当天就落盘，比它自己的公告早 12~35 天。
    代价是总纲给不出类型，所以先落默认类型 + `keys.PENDING_FIELD` 标记——标记是那条路
    的开关：预筛（keys.likely_recorded）见到它就不跳过正文，抓到公告后由
    calibrate.correct_from_candidates 把类型/描述/配色补齐并清掉标记。
    """
    out: list[dict] = []
    for content in contents.values():
        for a in parse.parse_version_activities(content, versions):
            if not (a.get("start_date") and a.get("end_date")):
                continue     # 日期解不出来的不进候选（与日期闸同一判据）
            out.append({"title": a["title"], "type": calibrate.DEFAULT_ACTIVITY_TYPE,
                        "start_date": a["start_date"], "end_date": a["end_date"],
                        keys.PENDING_FIELD: "总纲"})
    return out


def _build_version_events(notes):
    """当前版本的停服更新条目。日期即版本更新日（开服当天，起止同一天）。

    只发当前版本：版本名只有它自己的总纲给了，而「下个版本的日期」总纲里已经有了
    （写成「X.Y版本结束时间为 …」），提前挂一条没名字的占位不如不做。
    """
    if not (notes and notes.get("start_date") and notes.get("name")):
        return []
    d = notes["start_date"]
    return [{"title": rules.VERSION_UPDATE_TITLE.format(
                ver=notes["version"], name=notes["name"]),
             "type": "版本更新", "start_date": d, "end_date": d,
             "color": rules.COLORS["版本更新"], "post_id": notes.get("post_id")}]


def _build_livestreams(lives):
    return [{"title": rules.LIVESTREAM_TITLE.format(ver=l["version"], name=l["name"]),
             "type": "前瞻直播", "start_date": l["date"], "end_date": l["date"],
             "color": rules.COLORS["前瞻直播"]}
            for l in lives if l.get("version") and l.get("name")]


# ─── 高难 ────────────────────────────────────────────────

def _endgame_periods(notes) -> list[dict]:
    """当前版本的高难期次 → [{title, mode, start_date, end_date}]。"""
    if not (notes and notes.get("start_date")):
        return []
    out = []
    for eg in inference.endgame_periods(notes["start_date"],
                                        notes.get("endgame_counts") or {}):
        iso = eg["start_date"]
        out.append({"title": rules.ENDGAME_TITLE.format(mode=eg["mode"],
                                                        mmdd=iso[5:7] + iso[8:10]),
                    "mode": eg["mode"], "start_date": iso, "end_date": eg["end_date"]})
    return out


def _build_endgame_events(notes) -> list[dict]:
    return [{"title": eg["title"], "type": "高难挑战",
             "start_date": eg["start_date"], "end_date": eg["end_date"],
             "color": rules.COLORS.get(eg["mode"], FALLBACK_COLOR),
             "post_id": (notes or {}).get("post_id")}
            for eg in _endgame_periods(notes)]


# ─── 活动 / 卡池 / 大月卡 ─────────────────────────────────

def _build_activities(posts, versions, existing) -> list[dict]:
    """常规活动 / 版本大活动 / 网页活动 / 登录福利。

    标题「活动名」逐字取自公告 subject——活动名只有它自己最权威，不做二次拼接
    （嵌套写法「『嗯呢』大派送！」原样保留）。类型与日期都从正文派生。
    """
    out = []
    for a in parse.find_activities(posts):
        if not _needs_body(a, existing):
            continue
        text, images, content = _fetch(a["post_id"])
        if text is None:
            continue
        body = parse.parse_activity_body(text, versions)
        out.append({"title": a["title"], "type": parse.classify_activity(text, content),
                    "start_date": body.get("start_date"),
                    "end_date": body.get("end_date"),
                    "description": body.get("description"),
                    "images": images, "post_id": a["post_id"]})
    return out


def _build_banners(posts, versions) -> list[dict]:
    """卡池。限定S级代理人的名字只在正文里，所以标题必须抓完正文才能拼——预筛在这里
    省不掉请求（每版本 2~3 条公告，量很小）。

    同一期在不同公告里各出现一次时按 (标题, 起, 止) 去重，免得产物里全是重复行、
    人工核对时看不清。
    """
    out: dict[tuple, dict] = {}
    for b in parse.find_banners(posts):
        text, images, _content = _fetch(b["post_id"])
        if text is None:
            continue
        for p in parse.parse_banner_body(text, versions):
            out.setdefault((p["title"], p["start_date"], p["end_date"]),
                           {"title": p["title"], "type": "卡池",
                            "start_date": p["start_date"], "end_date": p["end_date"],
                            "post_id": b["post_id"], "images": images})
    return list(out.values())


def _build_battle_passes(posts, versions, existing) -> list[dict]:
    """丽都城募（大月卡）。期名每版本都一样，标题必须带版本号，否则去重键会撞。"""
    out = []
    for b in parse.find_battle_passes(posts):
        if not b.get("version"):
            continue
        e = {"title": rules.BATTLE_PASS_TITLE.format(ver=b["version"]),
             "type": "大月卡", "post_id": b["post_id"]}
        if not _needs_body(e, existing):
            continue
        text, _images, _content = _fetch(b["post_id"])
        if text is None:
            continue
        body = parse.parse_activity_body(text, versions)
        e.update(start_date=body.get("start_date"), end_date=body.get("end_date"),
                 description=body.get("description"), color=rules.COLORS["大月卡"])
        out.append(e)
    return out


# ─── 校准来源 ────────────────────────────────────────────

def _build_sources(lives, notes) -> dict:
    """汇总权威值索引，供 calibrate 核对**已有**条目（只改值，不新增）。

    版本更新 / 前瞻直播走 calibrate.sources_from（机制与原神/星铁共用，标题里的
    游戏名必须传对，否则会把已有标题改坏）；版本更新再被总纲覆盖一次——总纲是
    绝区零版本更新日唯一的权威来源。高难由总纲的期数按网格推，是本管线里唯一
    没有「公告原文日期」可核的一类。
    """
    src = calibrate.sources_from(lives, None, game_name=rules.GAME_TITLE)
    if notes and notes.get("name") and notes.get("start_date"):
        src[("版本更新", "v", notes["version"])] = {
            "title": rules.VERSION_UPDATE_TITLE.format(
                ver=notes["version"], name=notes["name"]),
            "start_date": notes["start_date"], "end_date": notes["start_date"],
            "source": "米游社停服更新公告"}
    for eg in _endgame_periods(notes):
        src[("高难挑战", eg["title"])] = {
            "title": eg["title"], "start_date": eg["start_date"], "end_date": eg["end_date"],
            "source": "总纲期数 + 高难期次网格"}
    return src


# ─── 编排 ────────────────────────────────────────────────

def run():
    # 同一进程内可能多次调用（编辑器「自动化维护」可重复按），计数必须每轮归零
    FETCH_STATS.update(ok=0, fail=0, risk=0, skip=0)

    events = yaml_io.load_events(GAME)
    posts = fetch_post_list(GAME, page_size=rules.PAGE_SIZE)
    posts = list({p["post_id"]: p for p in posts}.values())

    # ① 停服更新公告：当前版本 + 窗口内旧版本（活动日期要按版本号查表）
    versions, notes, contents = _collect_versions(posts)
    for ver, (start, end) in versions.items():
        print(f"== 版本期间 == {ver}  {start} ~ {end}")
    if notes:
        print(f"== 停服更新公告 == {notes['version']}版本「{notes.get('name') or '?'}」"
              f" 更新日 {notes.get('start_date')}"
              f"，下个版本 {notes.get('next_version_date')}"
              f"（本版 {notes.get('period_days')} 天）"
              f"，高难期数 {notes.get('endgame_counts')}")

    # ② B站动态：前瞻直播（米游社不发前瞻预告）
    dyn = bilibili.fetch_dynamics(rules.BILI_UID, limit=rules.DYN_LIMIT)
    lives = parse.find_livestreams(dyn)

    acts = (_build_activities(posts, versions, events)
            + _activities_from_notes(contents, versions))
    # 同一活动可能两条候选都有：总纲列了全部活动，而它自己的公告发出来后就又多一条。
    # 按身份去重、留先出现的那条（公告那条：有真类型与描述，总纲那条只有默认类型）。
    deduped: dict = {}
    for a in acts:
        deduped.setdefault(keys.event_key(a) or (a.get("title"), a.get("start_date")), a)
    acts = list(deduped.values())
    all_events = (
        _build_version_events(notes)
        + _build_livestreams(lives)
        + _build_endgame_events(notes)
        + acts
        + _build_banners(posts, versions)
        + _build_battle_passes(posts, versions, events)
    )

    # 订正：用本轮候选改已有条目的**类型**，并补全总纲落盘那批缺的描述与配色。
    # 必须在校准之前——两者都会写 events，校准读的是订正后的结果（同一轮内可见）。
    fixes = calibrate.correct_from_candidates(events, acts)

    # 校准：用权威来源核对已有条目（只改值 + 打 calibrated 标记，不新增）
    filled, changes = calibrate.calibrate(events, _build_sources(lives, notes))
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

    # 取色：高难/版本更新/前瞻/版本大活动/大月卡用固定色，其余按封面图取浅色
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
