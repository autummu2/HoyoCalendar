"""一次性驱动：跑完整活动提取管线 → 输出含颜色的完整条目 JSON（供人工核对后落盘）。

流程：米游社公告列表 → 识别活动/卡池/纪行/幽境危战 → 抓正文 → B站动态判定类型/补日期 →
版本日期解析 → 封面图取色（浅色 pastel）。结果写 extracted_full.json。
另：推理未来周期性事件（只新增）；用 B站动态 / 米游社维护预告校准已有条目
（calibrate.py，只改值 + 打 calibrated 标记），有变更直接落盘数据文件。
"""
import datetime
import json
import os
import sys
import winreg
from pathlib import Path

# 允许直接 `python genshin/pipeline.py`（此时 sys.path[0] 是本目录，找不到兄弟包）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 凭据存注册表（setx 写的也是这里），须在 import bilibili / extractor 前读入 os.environ
# （见记忆 bili-sessdata-registry）。两个都可选，缺任何一个都不影响运行。
try:
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
    for _name in ("BILI_SESSDATA", "MIYOUSHE_COOKIE"):
        try:
            os.environ[_name], _ = winreg.QueryValueEx(k, _name)
        except OSError:
            pass
except OSError:
    pass

from common import bilibili, calibrate, keys, yaml_io
from common.colors import FALLBACK_COLOR, pastel_from_url
from common.extractor import (fetch_post_list, fetch_post, find_activity_announcements,
                              find_challenge_announcements, find_battle_pass_announcements,
                              find_banner_announcements, find_special_banner_announcements,
                              find_maintenance_posts, parse_maintenance_body,
                              parse_activity_body)
from genshin import inference

GAME = "genshin-impact"

# 产物写在自己目录下，与运行时的 cwd 无关
OUT_FILE = Path(__file__).resolve().parent / "extracted_full.json"


def _build_sources(merged, banners, dyn, posts):
    """汇总各类型条目的权威值索引，供 calibrate 核对已有条目。

    merged / banners 里带 source 字段的条目（即 B站动态匹配成功者）直接取用；
    「版本更新 / 前瞻直播」另由 B站前瞻公告 + 米游社维护预告构造。
    """
    sources = {}
    for e in list(merged) + list(banners):
        src = e.get("source")
        if not src:
            continue
        k = keys.event_key(e)
        if k:
            sources[k] = {
                "start_date": e.get("start_date"),
                "end_date": e.get("end_date"),
                "source": src,
            }

    maintenance = None
    for m in find_maintenance_posts(posts):
        fp = fetch_post(m.get("post_id", ""))
        if not fp or "error" in fp:
            continue
        parsed = parse_maintenance_body(fp.get("text") or "")
        if parsed:
            maintenance = {**m, **parsed}
            print(f"== 维护预告 == {m['subject']} →", parsed.get("date"), parsed.get("name") or "")
            break

    sources.update(calibrate.sources_from(bilibili.find_livestreams(dyn), maintenance))
    return sources


def _merge_inferred(events, inferred):
    """把推理出的周期性事件并入事件列表（去重），返回 (合并后列表, 新增列表)。

    只新增、不改动已有条目。同身份判定见 keys.find_duplicate。
    """
    added = []
    for e in inferred:
        if keys.find_duplicate(e, events) is None:
            events.append(e)
            added.append(e)
    return events, added


# 正文抓取成败计数。供无人值守运行后人工核查：风控（retcode 1034）会让正文大面积抓不到，
# 条目因拿不到日期被日期闸丢弃，表现为「本轮 0 新增」，容易被误当成「今天没有新活动」。
FETCH_STATS = {"ok": 0, "fail": 0, "risk": 0, "skip": 0}


def _count_fetch(fp):
    """记录一次正文抓取的成败。"""
    if fp and "error" not in fp:
        FETCH_STATS["ok"] += 1
        return
    FETCH_STATS["fail"] += 1
    if "1034" in ((fp or {}).get("error") or ""):
        FETCH_STATS["risk"] += 1


def _needs_body(event, existing):
    """该条目是否还需要抓正文。

    正文只用来取日期 / 描述 / 配图，都是「新增」才需要的东西；已落盘的条目不必再抓。
    稳态下一次运行由此省掉绝大部分正文请求——请求数正是米游社风控的主因。
    判定复用 apply_events 的同名去重（keys.find_duplicate），因此不会比现有去重更激进：
    这里跳过的，apply 本来也会跳过。

    命中的条目打 `_body_skipped` 标记：它仍留在列表里参与 B站合并与校准（否则会丢掉
    校准的权威来源，见 _build_sources），但没日期是正常的，日志不再把它报成日期缺口。
    """
    if keys.find_duplicate(event, existing) is None:
        return True
    event["_body_skipped"] = True
    FETCH_STATS["skip"] += 1
    return False


def run():
    # 同一进程内可能多次调用（编辑器「自动化维护」可重复按），计数必须每轮归零
    FETCH_STATS.update(ok=0, fail=0, risk=0, skip=0)

    posts = fetch_post_list(GAME, page_size=30)
    entries = find_activity_announcements(posts)
    challenges = find_challenge_announcements(posts)
    battle_passes = find_battle_pass_announcements(posts)
    banners = find_banner_announcements(posts) + find_special_banner_announcements(posts)

    # 已落盘条目提前载入，供 _needs_body 判断哪些条目无需再抓正文
    events = yaml_io.load_events(GAME)

    # entries 不带 type（类型要到 B站动态合并后才定：默认常规活动、多阶段信号→版本大活动），
    # 而预筛要类型才能对上键。先按默认值填——与 merge_activities 的默认一致；
    # 已有的版本大活动因此对不上、仍会多抓一次正文（每版本 1~2 条，可接受）。
    for e in entries:
        e.setdefault("type", "常规活动")

    # 抓正文 + 封面图
    for e in entries:
        if not _needs_body(e, events):
            continue
        fp = fetch_post(e["post_id"])
        _count_fetch(fp)
        if not fp or "error" in fp:
            continue
        body = parse_activity_body(fp.get("text", ""))
        if body.get("description"):
            e["description"] = body["description"]
        for key in ("start_date", "end_date"):
            if body.get(key):
                e[key] = body[key]
        if body.get("permanent"):
            e["permanent"] = True
        if body.get("version_period"):
            e["version_period"] = True
        e["images"] = fp.get("images", [])

    # 幽境危战（高难挑战）单独处理：抓正文 + 日期，不参与 B站动态/版本推断
    for c in challenges:
        if not _needs_body(c, events):
            continue
        fp = fetch_post(c["post_id"])
        _count_fetch(fp)
        if not fp or "error" in fp:
            continue
        body = parse_activity_body(fp.get("text", ""))
        if body.get("description"):
            c["description"] = body["description"]
        for key in ("start_date", "end_date"):
            if body.get(key):
                c[key] = body[key]
        c["images"] = fp.get("images", [])
    challenges = [c for c in challenges if c.get("start_date")]

    # 纪行（大月卡）单独处理：正文「版本更新后 ~ Y」，start 由 resolve_version_starts 补
    for b in battle_passes:
        if not _needs_body(b, events):
            continue
        fp = fetch_post(b["post_id"])
        _count_fetch(fp)
        if not fp or "error" in fp:
            continue
        body = parse_activity_body(fp.get("text", ""))
        if body.get("description"):
            b["description"] = body["description"]
        for key in ("start_date", "end_date"):
            if body.get(key):
                b[key] = body[key]
        b["images"] = fp.get("images", [])

    # 永久开放不进日历
    entries = [e for e in entries if not e.get("permanent")]

    # B站动态判定类型 + 补日期
    dyn = bilibili.fetch_dynamics(limit=80)
    acts = bilibili.find_activity_dynamics(dyn)
    merged = bilibili.merge_activities(entries, acts)

    # 版本日期解析（「版本更新后 / 版本期间」）。events 已在前面载入
    vd = inference.extract_version_dates(events)
    merged = inference.resolve_version_starts(merged, vd)
    merged = inference.resolve_version_period(merged, vd)
    battle_passes = inference.resolve_version_starts(battle_passes, vd)

    # 卡池（普通祈愿 + 特殊祈愿）：日期同走版本节奏推断 + B站总览补充，再抓正文取图/描述
    banners = inference.infer_banner_dates(banners, vd)
    banners = bilibili.merge_banners(banners, bilibili.find_summaries(dyn))
    banners = bilibili.merge_special_banners(banners, bilibili.find_special_banner_dynamics(dyn), vd)
    for b in banners:
        b["type"] = "卡池"      # 键含类型，须先定类型再判是否已存在
        if not _needs_body(b, events):
            continue
        fp = fetch_post(b.get("post_id", ""))
        _count_fetch(fp)
        if fp and "error" not in fp:
            if fp.get("text"):
                b["description"] = fp["text"]
            b["images"] = fp.get("images", [])

    # 推理未来周期性事件（深境螺旋/幻想真境剧诗/版本更新/前瞻直播），并入数据
    today = datetime.date.today()
    anchor = inference.extract_version_anchor(events)
    events, inferred_added = _merge_inferred(events, inference.infer_events(today, anchor))

    # 校准：用 B站动态 / 米游社维护预告的权威值核对已有条目（只改值 + 打 calibrated 标记，不新增）
    sources = _build_sources(merged, banners, dyn, posts)
    filled, changes = calibrate.calibrate(events, sources)
    if inferred_added or changes:
        yaml_io.save_events(GAME, filled)
        if inferred_added:
            print("== 推理新增 ==")
            for a in inferred_added:
                print(" +", a["title"], a["start_date"], "~", a["end_date"])
        if changes:
            print("== 校准 ==")
            for c in changes:
                print(" ~", c)

    # 正文抓取小结：风控期间这里会明显异常，是本轮结果是否可信的第一判断依据。
    # 「跳过正文」是已存在于数据文件的条目（无需再抓），不是异常。
    print(f"== 正文抓取 == 成功 {FETCH_STATS['ok']} / 失败 {FETCH_STATS['fail']}"
          + (f"（其中风控 1034: {FETCH_STATS['risk']}）" if FETCH_STATS["risk"] else "")
          + f" / 跳过正文 {FETCH_STATS['skip']}（已存在）")

    # 日期缺口的最后一道闸：无完整日期的条目不进输出。
    # 下游 apply_events 以「标题 + 开始日期」为键写 YAML，缺日期会直接 KeyError；
    # 这里连同类型无关地兜住（如正文用「〓任务开放时间〓」等未识别段落的公告）。
    all_events = merged + challenges + battle_passes + banners
    dropped = [e for e in all_events if not (e.get("start_date") and e.get("end_date"))]
    # 跳过正文的已知重复条目没日期是正常的，不报——否则天天刷一屏，淹掉真正的日期缺口
    reported = [e for e in dropped if not e.get("_body_skipped")]
    if reported:
        print("== 跳过（日期不完整）==")
        for e in reported:
            print(" x", e.get("title"), e.get("start_date") or "?", "~", e.get("end_date") or "?")
    all_events = [e for e in all_events if e.get("start_date") and e.get("end_date")]

    # 取色（常规/版本大活动 + 高难挑战 + 大月卡 + 卡池）
    for e in all_events:
        imgs = e.get("images") or []
        e["color"] = pastel_from_url(imgs[0]) if imgs else FALLBACK_COLOR

    out = [
        {k: e[k] for k in ("title", "type", "start_date", "end_date", "tags", "color", "description", "images", "post_id", "name")
         if k in e}
        for e in all_events
    ]
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"written {len(out)} entries → {OUT_FILE.name}")


if __name__ == "__main__":
    run()
