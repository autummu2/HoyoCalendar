"""星铁解析规则的离线自检：python starrail/selftest.py

用 fixtures/ 里保存的真实公告（米游社正文 + B站动态原文）断言 parse.py 的每个解析器。
不联网、不读写数据文件。

重点盯的是**卡池标题**：星铁的 5 星名只在正文里，标题是拼出来的，而标题又是去重主键
（keys.event_key）。拼错一个字，下一轮就会把已落盘的条目当成新活动插一遍。
所以这里逐字比对数据文件里既有的条目。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import keys  # noqa: E402
from common import yaml_io  # noqa: E402
from starrail import parse, pipeline, rules  # noqa: E402

# 离线夹具里必然对不上现有数据的条目（真的还没落盘，不是标题规则出错）
# 2026-09-21：虚构叙事·立界开篇、4.5版本「无名勋礼」已随本轮落盘，移出本集合——
# 它们现在**应该**命中，命中即幂等成立；留在集合里反而会在下一轮误报。
KNOWN_NEW = {
    "「镇伏『贪饕』，汇聚愿力」",    # 4.6 版本大活动，终点要等 4.6 的说明
}

FIXTURES = Path(__file__).parent / "fixtures"

_FAILS: list[str] = []
_CHECKS = 0


def load(name: str):
    with open(FIXTURES / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def check(label: str, got, want):
    global _CHECKS
    _CHECKS += 1
    if got != want:
        _FAILS.append(f"{label}\n      实际 {got!r}\n      期望 {want!r}")


# ─── 版本更新说明 ────────────────────────────────────────

def test_version_notes():
    d44 = load("hsr44_version_notes")
    n44 = parse.parse_version_notes(d44["text"], d44["subject"])
    check("4.4 版本号", n44["version"], "4.4")
    check("4.4 版本名", n44["name"], "鸣笛于归寂之时")
    check("4.4 本版开始", n44["start_date"], "2026-07-15")
    check("4.4 推得下版本日期", n44["next_version_date"], "2026-08-26")
    check("4.4 高难", [(e["mode"], e.get("name"), e.get("start_date"), e.get("end_date"))
                       for e in n44["endgame"]],
          [("异相仲裁", "尘世卷中", None, None),
           ("末日幻影", "兵锋骑士", "2026-07-20", "2026-08-30"),
           ("虚构叙事", "构事生意", "2026-08-03", "2026-09-13"),
           ("混沌回忆", "扫除风暴", "2026-08-17", "2026-09-27")])

    d45 = load("hsr45_version_notes")
    n45 = parse.parse_version_notes(d45["text"], d45["subject"])
    check("4.5 版本号", n45["version"], "4.5")
    check("4.5 版本名", n45["name"], "挥掷千星的筹码")
    check("4.5 本版开始", n45["start_date"], "2026-08-26")
    # 这条就是「不靠固定周期外推」的依据：4.5 一开服就知道 4.6 在 9/28
    check("4.5 推得下版本日期", n45["next_version_date"], "2026-09-28")
    check("4.5 高难", [(e["mode"], e.get("name"), e.get("start_date"), e.get("end_date"))
                       for e in n45["endgame"]],
          [("异相仲裁", "军团再临", None, None),
           ("末日幻影", "仙客天狼", "2026-08-31", "2026-10-04"),
           ("虚构叙事", "立界开篇", "2026-09-14", "2026-10-18")])

    # 《云•星穹铁道》的同名公告不能当版本更新说明
    check("排除云游戏说明", parse.is_version_notes("《云•星穹铁道》4.5版本更新说明"), False)
    check("识别版本更新说明", parse.is_version_notes("4.5版本「挥掷千星的筹码」版本更新说明"), True)


# ─── 卡池：标题必须与数据文件逐字一致 ─────────────────────

def test_banners():
    cases = [
        ("hsr45_banner_1", [("「知更鸟•晴歌（记忆•风）」「风堇（记忆•风）」跃迁",
                             "2026-08-26", "2026-09-12")]),
        ("hsr45_banner_2", [("「砂金•戏浪（欢愉•量子）」「不死途（巡猎•雷）」跃迁",
                             "2026-09-12", "2026-09-27")]),
        # 含「铭心之萃」返场池：同一公告两个时间段，必须拆两条
        ("hsr44_banner_2", [("「姬子•启行（智识•火）」跃迁", "2026-07-15", "2026-08-25"),
                            ("「刻律德菈（同谐•风）」「那刻夏（智识•风）」「砂金（存护•虚数）」跃迁",
                             "2026-08-05", "2026-08-25")]),
    ]
    for name, want in cases:
        d = load(name)
        got = [(b["title"], b["start_date"], b["end_date"])
               for b in parse.parse_banner_body(d["text"])]
        check(f"卡池 {name}", got, want)


# ─── 活动 / 大月卡正文 ───────────────────────────────────

def test_activity_bodies():
    cases = [
        # 段落名三种都在用
        ("act_chaoxian", "▌限时活动期", "2026-08-26", "2026-09-27"),
        ("act_huacang", "▌活动时间", "2026-08-14", "2026-08-23"),
        ("act_weimian", "▌活动时间", "2026-09-07", "2026-09-20"),
        ("hsr45_battle_pass", "▌开启时间", "2026-08-26", "2026-09-27"),
    ]
    for name, _sec, want_start, want_end in cases:
        d = load(name)
        got = parse.parse_activity_body(d["text"])
        check(f"正文 {name}", (got.get("start_date"), got.get("end_date")),
              (want_start, want_end))

    # 「X.Y版本期间」→ 不给日期，只给版本号，交给调用方按版本周期补
    d = load("act_zhenfu")
    got = parse.parse_activity_body(d["text"])
    check("整版活动标记", (got.get("version_period"), got.get("start_date")), ("4.6", None))


# ─── 更新预告 ────────────────────────────────────────────

def test_update_preview():
    d = load("hsr45_update_preview")
    check("更新预告", parse.parse_update_preview(d["text"]),
          {"date": "2026-08-26", "version": "4.5", "name": "挥掷千星的筹码"})


# ─── B站 ─────────────────────────────────────────────────

def test_bilibili():
    items = load("bili_livestream")
    launches = parse.find_launches(items)
    lives = parse.find_livestreams(items)
    check("B站上线日期", [(r["version"], r["name"], r["date"]) for r in launches],
          [("4.6", "月升之前，与兽共舞", "2026-09-28")])
    check("B站前瞻日期", [(r["version"], r["name"], r["date"]) for r in lives],
          [("4.6", "月升之前，与兽共舞", "2026-09-20")])


# ─── 公告分类 ────────────────────────────────────────────

def test_classification():
    should_skip = [
        "4.6版本商店上新", "【2026年9月9日】账号封禁公示",
        "4.5版本游戏优化及已知问题说明（09/16更新）", "列车信箱｜4.5版本意见反馈集中帖",
        "《云•星穹铁道》4.5版本更新说明", "【全新工具】跃迁记录统计功能上线",
        "《云•星穹铁道》「权益升级」活动说明", "4.5版本「挥掷千星的筹码」版本更新说明",
        "4.5版本预下载&更新预告", "4.5版本活动跃迁（其一）", "4.5版本「无名勋礼」更新",
        "「挥掷千星的筹码」开拓任务说明", "「亏成首富，从不要钱开始」开拓续闻说明",
        "官方小程序&企业微信正式上线，每版本领专属星琼福利！",
    ]
    for s in should_skip:
        check(f"非活动应排除：{s}", parse.is_activity(s), False)

    should_keep = {
        "「异器盈界」活动：隧洞遗器限时双倍掉落": "异器盈界",
        "「方寸大冒险」：集结小队挑战强敌，获取命运的足迹、星琼等奖励": "方寸大冒险",
        "「超限：狂飙大奖赛」活动说明": "超限：狂飙大奖赛",
        "「幻造：圣杯战争」活动说明": "幻造：圣杯战争",
        # 嵌套书名号：原神那条 [「『]([^」』]{2,40})[」』] 会截断成「镇伏『贪饕」
        "「镇伏『贪饕』，汇聚愿力」活动说明": "镇伏『贪饕』，汇聚愿力",
        "「反贪『砖』家」活动说明": "反贪『砖』家",
    }
    for s, want_name in should_keep.items():
        check(f"活动名 {s}", parse._name_of(s), want_name)
        check(f"应识别为活动 {s}", parse.is_activity(s), True)


# ─── 交叉核对：本轮会产出的条目 vs 数据文件里的已有条目 ────

def test_matches_existing():
    """除 KNOWN_NEW 外，每条都应命中数据文件里的已有条目，且日期一致。

    这是**标题规则**的回归闸门。标题是去重主键（keys.event_key），拼错一个字，
    下一轮 apply_events 就会把已落盘的条目当成新活动再插一遍——而且日期也是同一套
    日期口径推出来的，一并核对，等于把「标题 + 日期口径」两个假设都钉在真实数据上。
    """
    existing = yaml_io.load_events(rules.GAME)

    d44, d45 = load("hsr44_version_notes"), load("hsr45_version_notes")
    notes44 = {**parse.parse_version_notes(d44["text"], d44["subject"]),
               "post_id": d44["post_id"]}
    notes45 = {**parse.parse_version_notes(d45["text"], d45["subject"]),
               "post_id": d45["post_id"]}

    dyn = load("bili_livestream")
    preview = parse.parse_update_preview(load("hsr45_update_preview")["text"])

    candidates = (
        pipeline._build_endgame_events(notes44) + pipeline._build_endgame_events(notes45)
        + pipeline._build_version_events(notes45, preview, parse.find_launches(dyn))
        + pipeline._build_livestreams(parse.find_livestreams(dyn))
    )
    # 卡池：正文夹具只用来取标题，日期已由 test_banners 逐条断言过
    for name in ("hsr45_banner_1", "hsr45_banner_2", "hsr44_banner_2"):
        for b in parse.parse_banner_body(load(name)["text"]):
            candidates.append({"title": b["title"], "type": "卡池",
                               "start_date": b["start_date"], "end_date": b["end_date"]})
    candidates.append({"title": rules.BATTLE_PASS_TITLE.format(ver="4.5"), "type": "大月卡"})
    # 活动：正文夹具只用来取标题（日期同样已单独断言）
    for name, etype in (("act_chaoxian", "常规活动"), ("act_huacang", "常规活动"),
                        ("act_weimian", "常规活动"), ("act_zhenfu", "版本大活动")):
        candidates.append({"title": f"「{parse._name_of(load(name)['subject'])}」",
                           "type": etype})

    for c in candidates:
        dup = keys.find_duplicate(c, existing)
        if c["title"] in KNOWN_NEW:
            check(f"已知新增不应命中：{c['title']}", dup, None)
            continue
        if dup is None:
            check(f"应命中已有条目：{c['title']}", None, "数据文件里的一条")
            continue
        for f in ("start_date", "end_date"):
            if c.get(f):
                check(f"日期一致 {c['title']} {f}", dup.get(f), c[f])


def main():
    for fn in (test_version_notes, test_banners, test_activity_bodies,
               test_update_preview, test_bilibili, test_classification,
               test_matches_existing):
        fn()

    if _FAILS:
        print(f"✗ {len(_FAILS)} / {_CHECKS} 项不符：\n")
        for f in _FAILS:
            print("  ✗", f)
        return 1
    print(f"✓ 全部 {_CHECKS} 项通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
