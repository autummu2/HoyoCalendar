"""未定事件簿活动维护管线：抓资讯栏 + 公告栏 → 解析 → 写 extracted_tea.json。

与 genshin/、starrail/、zenless/ 并列的第四条线。真正通用的模块
（common/ 下的 yaml_io / keys / colors / body_cache）直接复用。

未定的信息结构与另三端不同，三条差异决定了这条管线的形状：

1. **活动在资讯栏（`type=3`），版本停服更新公告在公告栏（`type=1`）** ——
   两个栏目都抓。`common.extractor.fetch_post_list` 的 `NEWS_TYPE_MAP` 给未定登记的
   是资讯栏，公告栏那一路显式传 `news_type=rules.VERSION_TAB`。
2. **一个活动拆成好几篇发**，所以没有「总纲」可用：每篇帖子自己判类型、自己解日期，
   解不出完整时段就丢，等下一篇带完整时段的（**不落 `pending` 半条数据**，裁定 10）。
   没有归并机制，也没有分组 —— 见 RULES §2.3。
3. **不接 `common.calibrate`**（裁定 19）：管线**只增不改**，落盘后的日期不再被任何
   自动流程改写，要改只能人工手改 YAML。所以这条线是「提取 + 落盘」，没有校准段。

⚠️ `collect` 是纯函数（不联网、不写文件），`run` 只负责抓取与落盘。分开是为了能拿
fixtures/ 里的真实公告离线跑一遍（selftest.py + `python themis/pipeline.py --dry-run`）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 允许直接 `python themis/pipeline.py`（此时 sys.path[0] 是本目录，找不到兄弟模块）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import winreg

# 凭据存注册表（setx 写的也是这里），须在 import extractor 前读入 os.environ
# （见记忆 bili-sessdata-registry）。可选，缺了也不影响运行。
try:
    _k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
    try:
        os.environ["MIYOUSHE_COOKIE"], _ = winreg.QueryValueEx(_k, "MIYOUSHE_COOKIE")
    except OSError:
        pass
except OSError:
    pass

from common import body_cache, keys
from common.colors import pastel_from_url
from common.extractor import fetch_post, fetch_post_list
from themis import parse, rules

GAME = rules.GAME
FALLBACK_COLOR = rules.FALLBACK_COLOR

# 产物写在自己目录下，与运行时的 cwd 无关
OUT_FILE = Path(__file__).resolve().parent / "extracted_tea.json"

# 交给 apply_events 的字段白名单。**没有** `keys.PENDING_FIELD`：未定不用 pending
# （落不了的等下一篇，不落半条，裁定 10），也不需要 calibrate 补字段。
# **也没有 `description`**：未定正文里混着大量礼包/兑换所/抽奖样板文字（商城帖 800+ 字），
# 2026-09-25 裁定「活动描述先都空着」——少一样噪声，等以后想清楚存什么再补。
OUT_FIELDS = ("title", "type", "start_date", "end_date", "color", "tags", "post_id")


# ─── 抓取记账 ────────────────────────────────────────────

# 正文抓取成败计数。无人值守运行后人工核查用：风控（retcode 1034）会让正文大面积
# 抓不到，条目因拿不到日期被日期闸丢弃，表现为「本轮 0 新增」，容易被误当成
# 「今天没有新活动」。日志里的这一行是分辨两者的第一依据。
FETCH_STATS = {"ok": 0, "fail": 0, "risk": 0, "cache": 0}

# 本轮每篇帖子的判定（[{"subject", "verdict", "why", "type"}]）。dry-run 与日志都靠它，
# 因为未定的漏斗是**按帖子**收敛的：50 篇 → 19 篇不进正文 → 21 条候选 → 去重后 18 条。
# 只报「本轮新增几条」看不出是哪一道闸起的作用。
DECISIONS: list[dict] = []


def _note(subject: str, verdict: str, why: str = "", etype: str = "") -> None:
    DECISIONS.append({"subject": subject, "verdict": verdict, "why": why, "type": etype})


def _fetch(post_id):
    """抓一条正文，返回 (text, images)；失败返回 (None, [])。

    本机缓存里有未过期的正文就直接用（见 common/body_cache）——正文发布后基本不变，
    而请求数正是米游社风控的主因。
    """
    hit = body_cache.get(post_id)
    if hit is not None:
        FETCH_STATS["cache"] += 1
        return hit.get("text") or "", hit.get("images") or []
    fp = fetch_post(post_id, GAME)
    if not fp or "error" in fp:
        FETCH_STATS["fail"] += 1
        if "1034" in ((fp or {}).get("error") or ""):
            FETCH_STATS["risk"] += 1
        return None, []
    FETCH_STATS["ok"] += 1
    text, images = fp.get("text") or "", fp.get("images") or []
    body_cache.put(post_id, text=text, images=images)
    return text, images


# ─── 解析（纯函数，离线可跑）─────────────────────────────

def collect(news_posts: list[dict], version_posts: list[dict], body_of) -> list[dict]:
    """列表 + 正文 → 候选条目（不含颜色）。**不联网、不写文件**。

    `body_of(post_id) -> (text, images)` 由调用方给：run 给联网+缓存的 `_fetch`，
    selftest / dry-run 给 fixtures 里的正文。

    漏斗（RULES §2.2）：① 标题负向名单（不取正文）→ ② 正文解不出完整时段就丢
    → ③ 复刻二分（礼包复刻丢）→ ④ 复合标签判版本大活动 → 去重（类型取并集）。

    没有「已录过就跳过」的预筛（另三端有）：未定的候选标题要等正文解析出来才知道
    （列表标题是 `主题丨子标题`，从来不是活动名），列表阶段认不出是哪条活动。
    """
    DECISIONS.clear()
    events: list[dict] = []
    for p in parse.find_news(news_posts):
        subject = p.get("subject") or ""
        post_id = p.get("post_id")
        text, images = body_of(post_id)
        if not text:
            _note(subject, "丢弃", "正文抓不到")
            continue
        etype = parse.classify(subject, text)
        if etype is None:
            _note(subject, "丢弃", "礼包复刻（活动系列/礼包，不上日历）")
            continue
        start, end = parse.parse_period(text)
        if not (start and end):
            _note(subject, "丢弃", "正文解不出完整时段", etype)
            continue
        events.append({
            "title": parse.title_of(subject, text, etype),
            "type": etype,
            "start_date": start,
            "end_date": end,
            "tags": parse.detect_tags(subject, text),
            "images": images,
            "post_id": post_id,
        })
        _note(subject, "候选", f"{start} ~ {end}", etype)
    return _version_events(version_posts) + _merge(events)


def _merge(events: list[dict]) -> list[dict]:
    """同一活动的多篇帖子合成一条：**类型取并集，版本大活动优先**（RULES §2.2）。

    「一篇帖子一条」对未定有个副作用：同一活动往往有多篇帖子带**完全相同的时段**，
    而**只有其中几篇**带版本大活动标签。实测「何人生还」3 篇都是 `7/15 11:00-8/2 04:00`，
    带「阿加莎联动活动」标签的是「玩法说明」那篇，而数据文件里引的那篇正文连
    「阿加莎」都没有。落盘时 apply_events 只插第一条，所以「保留哪篇」就等于
    「类型取哪个」—— 不定。这里显式定下来：版本大活动那篇代表整组。
    """
    out: dict = {}
    for e in events:
        k = keys.event_key(e, GAME)
        prev = out.get(k)
        if prev is None or (e["type"] == "版本大活动" and prev["type"] != "版本大活动"):
            out[k] = e
    return list(out.values())


def _version_events(version_posts: list[dict]) -> list[dict]:
    """当前版本的停服更新条目（公告栏）。

    只发**最新**那一版：公告栏窗口有 8.5 个月，里面躺着 5 份停服公告，全发出来等于
    一次性回填 4 个历史版本，与「首次回填 = 不补」（裁定 14）相抵。列表按时间倒序，
    第一条命中即当前版本。
    """
    notes = parse.parse_version_notes(version_posts)
    if not notes:
        return []
    n = notes[0]
    return [{"title": rules.VERSION_UPDATE_TITLE.format(ver=n["version"]),
             "type": "版本更新", "start_date": n["date"], "end_date": n["date"],
             "color": rules.COLORS["版本更新"], "post_id": n["post_id"],
             "tags": [], "images": []}]


# ─── 编排 ────────────────────────────────────────────────

def run(dry_run: bool = False):
    """抓取 → 解析 → 取色 → 写 extracted_tea.json。

    dry_run=True 只打印判定表、不写产物（RULES §3 验证方式的第一步）。
    """
    FETCH_STATS.update(ok=0, fail=0, risk=0, cache=0)

    version_posts = fetch_post_list(GAME, page_size=rules.PAGE_SIZE,
                                    news_type=rules.VERSION_TAB)
    news_posts = fetch_post_list(GAME, page_size=rules.PAGE_SIZE)
    print(f"== 列表 == 公告栏 {len(version_posts)} 条 / 资讯栏 {len(news_posts)} 条")

    all_events = collect(news_posts, version_posts, _fetch)

    print(f"== 正文抓取 == 成功 {FETCH_STATS['ok']} / 失败 {FETCH_STATS['fail']}"
          + (f"（其中风控 1034: {FETCH_STATS['risk']}）" if FETCH_STATS["risk"] else "")
          + f" / 缓存命中 {FETCH_STATS['cache']}")

    print("== 判定 ==")
    for d in DECISIONS:
        tag = d["verdict"]
        print(f" {'+' if tag == '候选' else ' x'}", d["subject"][:44],
              f"[{d['why']}]" if d["why"] else "")

    # 取色：只有版本更新是固定色（公告栏的帖子没有封面，见 rules.COLORS），
    # 其余一概按封面图取浅色 —— 版本大活动与大月卡也是（2026-09-25 裁定）。
    for e in all_events:
        if e.get("color"):
            continue
        imgs = e.get("images") or []
        e["color"] = pastel_from_url(imgs[0]) if imgs else FALLBACK_COLOR

    if dry_run:
        print("\n== dry-run：不落盘 ==")
        for e in all_events:
            print(f"  {e['type']:<6} {e['start_date']} ~ {e['end_date']}  "
                  f"{e['title']}  [{e.get('color')}]")
        print(f"（共 {len(all_events)} 条，未写 {OUT_FILE.name}）")
        return all_events

    out = [{k: e[k] for k in OUT_FIELDS if k in e} for e in all_events]
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"written {len(out)} entries → {OUT_FILE}")
    return all_events


def main():
    os.chdir(Path(__file__).resolve().parent.parent)
    run(dry_run="--dry-run" in sys.argv)


if __name__ == "__main__":
    main()
