"""绝区零解析规则的离线自检：python zenless/selftest.py

用 fixtures/ 里保存的真实公告（米游社正文 + B站动态原文）断言 parse.py / inference.py
的每个规则。不联网、不读写数据文件。

重点盯三件事，任何一件错了都会在下一轮静默插重复条目或改坏日期：
- **标题**：它是去重主键（keys.event_key），也得与数据文件里的既有条目逐字一致。
- **类型**：只能从正文判。它**不在**主键里（活动类的身份是标题 + 开始日期），所以判错
  不会插重复，但会一直显示错，仍要盯。
- **日期口径**：终点在清晨（≤06:00/03:59 那类）要减一天，起点不减。
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import bilibili, calibrate, keys, yaml_io  # noqa: E402
from zenless import inference, parse, pipeline, rules  # noqa: E402

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


def _versions() -> dict:
    """窗口里两份总纲给出的版本期间表。"""
    out = {}
    for name in ("zzz31_version_notes", "zzz32_version_notes"):
        d = load(name)
        notes = parse.parse_version_notes(d["text"], d["subject"])
        out[notes["version"]] = parse.version_period(notes)
    return out


# ─── 停服更新公告（总纲）─────────────────────────────────

def test_version_notes():
    d31, d32 = load("zzz31_version_notes"), load("zzz32_version_notes")
    n31 = parse.parse_version_notes(d31["text"], d31["subject"])
    n32 = parse.parse_version_notes(d32["text"], d32["subject"])

    check("3.1 版本号", n31["version"], "3.1")
    check("3.1 版本名", n31["name"], "漫长的告别")
    check("3.1 更新日", n31["start_date"], "2026-07-29")
    check("3.1 下个版本日", n31["next_version_date"], "2026-09-09")
    check("3.1 版本终点", parse.version_period(n31)[1], "2026-09-08")
    check("3.1 持续天数", n31["period_days"], 42)
    check("3.1 高难期数", n31["endgame_counts"], {"危局强袭战": 3, "式舆防卫战": 3})

    check("3.2 版本号", n32["version"], "3.2")
    check("3.2 版本名", n32["name"], "她与她的隐秘往事")
    check("3.2 更新日", n32["start_date"], "2026-09-09")
    check("3.2 下个版本日", n32["next_version_date"], "2026-10-21")
    check("3.2 版本终点", parse.version_period(n32)[1], "2026-10-20")
    check("3.2 持续天数", n32["period_days"], 42)
    # 期数从正文数出来（3.2 的危局写成「第一期试炼/第一期绝境」，要先去重）
    check("3.2 高难期数", n32["endgame_counts"], {"危局强袭战": 3, "式舆防卫战": 3})

    # 两版首尾相接：3.1 的终点 09-08 与 3.2 的更新日 09-09 相邻，各 42 天
    check("版本相接 3.1终点/3.2更新日",
          (parse.version_period(n31)[1], n32["start_date"]), ("2026-09-08", "2026-09-09"))

    check("识别停服更新公告", parse.is_version_notes("3.2版本「她与她的隐秘往事」更新公告"), True)
    check("排除云游戏更新说明", parse.is_version_notes("《云·绝区零》3.2版本更新说明"), False)
    check("排除预下载通知",
          parse.is_version_notes("3.2版本「她与她的隐秘往事」预下载开启&更新通知"), False)


# ─── 卡池：标题必须与数据文件逐字一致 ─────────────────────

def test_banners():
    v = _versions()
    cases = [
        # 3.1 首期：逐段各写时间段，复乐园与霓色天使结束日不同 → 必须拆两条
        ("zzz31_banner_1", [("调频活动-蕾米埃尔", "2026-07-29", "2026-09-08"),
                            ("调频活动-爱芮", "2026-07-29", "2026-08-19")]),
        # 3.1 下期：共用时间段，含「独家重映」自选池（可自选的限定S级代理人也算）
        ("zzz31_banner_2", [("调频活动-希格莉德/琉音/浮波柚叶/浅羽悠真",
                             "2026-08-19", "2026-09-08")]),
        ("zzz32_banner_1", [("调频活动-克拉蕾/南宫羽", "2026-09-09", "2026-09-30")]),
    ]
    for name, want in cases:
        d = load(name)
        got = [(b["title"], b["start_date"], b["end_date"])
               for b in parse.parse_banner_body(d["text"], v)]
        check(f"卡池 {name}", got, want)

    # 音擎的 [名字(特性)] 没有「·」、默认A级代理人不在「限定S级代理人」词后，都不该被取到
    check("音擎不入标题", [n for n in parse._agent_names(
        load("zzz32_banner_1")["text"]) if "猩红渴望" in n or "旋钻机" in n], [])


# ─── 活动正文：日期 + 类型 ────────────────────────────────

# (夹具, 起, 止, 类型)。日期口径：起点照抄，终点在清晨则减一天
ACTIVITIES = [
    ("zzz_act_qialanghua",       "2026-07-29", "2026-09-06", "版本大活动"),
    ("zzz_act_faetong",          "2026-07-29", "2026-09-08", "网页活动"),
    ("zzz_act_maseer",           "2026-07-29", "2026-09-08", "登录福利"),
    ("zzz_act_yunduan",          "2026-07-29", "2026-09-07", "登录福利"),
    ("zzz_act_dianying",         "2026-07-29", "2026-09-08", "常规活动"),
    ("zzz_act_qianneng_shoulie", "2026-07-29", "2026-09-08", "常规活动"),
    ("zzz_act_jiwei",            "2026-08-24", "2026-09-06", "常规活动"),
    ("zzz_act_kacha",            "2026-08-07", "2026-08-23", "常规活动"),
    ("zzz_act_shendu",           "2026-08-12", "2026-08-16", "常规活动"),
    ("zzz_act_shizhan",          "2026-09-02", "2026-09-06", "常规活动"),
    ("zzz_act_qianneng_liehuo",  "2026-09-09", "2026-10-20", "常规活动"),
    ("zzz_act_quanxin",          "2026-09-09", "2026-10-19", "登录福利"),
    ("zzz_act_tianshi",          "2026-09-09", "2026-11-29", "常规活动"),
    ("zzz_act_tanqiu",           "2026-09-10", "2026-10-18", "常规活动"),
    ("zzz_act_jingxi",           "2026-09-23", "2026-10-19", "登录福利"),
    ("zzz_act_xujing",           "2026-09-16", "2026-10-04", "常规活动"),
    ("zzz_act_xianqian",         "2026-09-23", "2026-09-27", "常规活动"),
    ("zzz_act_nine",             "2026-08-19", "2026-09-07", "登录福利"),
    ("zzz_act_kazi",             "2026-08-19", "2026-09-06", "常规活动"),
    ("zzz_act_miaodong",         "2026-08-28", "2026-09-13", "常规活动"),
]


def test_activities():
    v = _versions()
    for name, want_start, want_end, want_type in ACTIVITIES:
        d = load(name)
        body = parse.parse_activity_body(d["text"], v)
        check(f"活动日期 {name}", (body.get("start_date"), body.get("end_date")),
              (want_start, want_end))
        check(f"活动类型 {name}", parse.classify_activity(d["text"], d["content"]), want_type)
        # 名称取自 subject 而非正文：数据文件里的标题就是这个写法
        check(f"活动名 {name}", parse._name_of(d["subject"]), d["subject"].split("」活动说明")[0][1:])

    # 网页活动的判据是「正文有非图床外链」，不是名字或类型字段
    check("法厄同有外链", parse.has_external_link(load("zzz_act_faetong")["content"]), True)
    check("全新放送无外链", parse.has_external_link(load("zzz_act_quanxin")["content"]), False)


# ─── 大月卡 ──────────────────────────────────────────────

def test_battle_passes():
    v = _versions()
    for name, ver, want in (("zzz31_battle_pass", "3.1", ("2026-07-29", "2026-09-06")),
                            ("zzz32_battle_pass", "3.2", ("2026-09-09", "2026-10-18"))):
        d = load(name)
        check(f"大月卡版本 {name}", parse.find_battle_passes([d])[0]["version"], ver)
        body = parse.parse_activity_body(d["text"], v)
        check(f"大月卡日期 {name}", (body.get("start_date"), body.get("end_date")), want)


# ─── 公告分类 ────────────────────────────────────────────

def test_classification():
    should_skip = [
        "3.2版本「她与她的隐秘往事」更新公告", "3.2版本「她与她的隐秘往事」预下载开启&更新通知",
        "3.2版本限时频段（上期）", "3.2版本「丽都城募」说明", "3.2版本「商城」上新说明",
        "《云·绝区零》3.2版本更新说明", "3.2版本已知问题及游戏优化说明（9月16日更新）",
        "新剧情：主线第三季第三章「她与她的隐秘往事」", "「迷宫诡域」常驻玩法开启",
        "「卓越搭档」上新说明", "《绝区零》PC端视觉体验升级功能使用FAQ（7月29日更新）",
    ]
    for s in should_skip:
        check(f"非活动应排除：{s}", parse.is_activity(s), False)

    should_keep = {
        "「全新放送」活动说明": "全新放送",
        # 嵌套书名号：原神那条 [「『]([^」』]{2,40})[」』] 会截断成「『嗯呢」
        "「『嗯呢』大派送！」活动说明": "『嗯呢』大派送！",
        "「『弹球勇者』哐哐当！」活动说明": "『弹球勇者』哐哐当！",
        "「潜能预演·烈火重锤」活动说明": "潜能预演·烈火重锤",
        "「先遣赏金-区域巡防」活动说明": "先遣赏金-区域巡防",
    }
    for s, want_name in should_keep.items():
        check(f"活动名 {s}", parse._name_of(s), want_name)
        check(f"应识别为活动 {s}", parse.is_activity(s), True)


# ─── 高难期次网格 ────────────────────────────────────────

def test_endgame_grid():
    """网格 vs 数据文件里手工录入的期次（16 条中 15 条命中）。"""
    check("3.2 危局", [(e["mode"], e["start_date"], e["end_date"])
                      for e in inference.endgame_periods("2026-09-09",
                                                         {"危局强袭战": 3, "式舆防卫战": 3})],
          [("危局强袭战", "2026-09-11", "2026-09-24"),
           ("危局强袭战", "2026-09-25", "2026-10-08"),
           ("危局强袭战", "2026-10-09", "2026-10-22"),
           ("式舆防卫战", "2026-09-18", "2026-10-01"),
           ("式舆防卫战", "2026-10-02", "2026-10-15"),
           ("式舆防卫战", "2026-10-16", "2026-10-29")])
    # 3.1 网格：危局 07-31/08-14/08-28、式舆 08-07/08-21/09-04
    # 数据里的「危局强袭战0729」是已知例外（更新当天，比网格早 2 天）。网格只按
    # **当前版本**的总纲推，3.1 不是当前版本，所以推不出它、也不会与它撞车。
    got31 = [(e["mode"], e["start_date"], e["end_date"])
             for e in inference.endgame_periods("2026-07-29",
                                                {"危局强袭战": 3, "式舆防卫战": 3})]
    check("3.1 危局首期", got31[0], ("危局强袭战", "2026-07-31", "2026-08-13"))
    check("3.1 式舆首期", got31[3], ("式舆防卫战", "2026-08-07", "2026-08-20"))
    check("3.1 式舆三期", got31[5], ("式舆防卫战", "2026-09-04", "2026-09-17"))


# ─── B站前瞻 ─────────────────────────────────────────────

def test_bilibili():
    """前瞻复用 common.bilibili.parse_livestream——绝区零的写法（「X月X日 …正式开启」，
    不带年份）跟原神一模一样，不用另写一个；只多一道「必须带具体月日」的闸。

    夹具里三条动态都含「前瞻特别节目」：预告（带 8月28日）、前瞻当天那条
    「将于今晚19:30开启！」、以及前瞻结束后的节目本体。只有第一条该被收下。
    """
    items = load("bili_zzz")
    check("含前瞻字样的动态条数", len([d for d in items if "前瞻特别节目" in d["text"]]), 3)
    check("B站前瞻日期", [(l["version"], l["name"], l["date"])
                        for l in parse.find_livestreams(items)],
          [("3.2", "她与她的隐秘往事", "2026-08-28")])


# ─── 交叉核对：本轮会产出的条目 vs 数据文件里的已有条目 ────

# 必须命中的条目（标题格式的回归闸门）。它们就是数据文件里的既有写法，
# 拼错一个字，下一轮 apply_events 就会把已落盘的条目当成新活动再插一遍。
MUST_HIT = ("危局强袭战0911", "式舆防卫战0918", "调频活动-克拉蕾/南宫羽",
            "「惊喜放映企划」", "「恰浪花逐夏而至」")


def test_matches_existing():
    """标题撞上已有条目 → 主键必须真的相同（类型/标题一致），日期必须一致。

    「同标题但类型不同」是最危险的一格：类型是主键的一部分，类型判错 = 主键失配 =
    插一条重复。这里逐条比对，日期也一并核对，等于把「标题 + 类型 + 日期口径」
    三个假设都钉在真实数据上。

    没撞上任何已有条目的候选 = 本轮的新增，逐条打印出来人工过一眼（不当失败）。
    """
    existing = yaml_io.load_events(rules.GAME)
    versions = _versions()
    notes32 = parse.parse_version_notes(load("zzz32_version_notes")["text"],
                                        load("zzz32_version_notes")["subject"])
    notes32["post_id"] = load("zzz32_version_notes")["post_id"]

    candidates: list[dict] = []
    candidates += pipeline._build_version_events(notes32)
    candidates += pipeline._build_endgame_events(notes32)
    candidates += pipeline._build_livestreams(parse.find_livestreams(load("bili_zzz")))
    for name, _s, _e, _t in ACTIVITIES:
        d = load(name)
        body = parse.parse_activity_body(d["text"], versions)
        candidates.append({"title": f"「{parse._name_of(d['subject'])}」",
                           "type": parse.classify_activity(d["text"], d["content"]),
                           "start_date": body.get("start_date"),
                           "end_date": body.get("end_date")})
    for name in ("zzz31_banner_1", "zzz31_banner_2", "zzz32_banner_1"):
        for b in parse.parse_banner_body(load(name)["text"], versions):
            candidates.append({**b, "type": "卡池"})
    for name, ver in (("zzz31_battle_pass", "3.1"), ("zzz32_battle_pass", "3.2")):
        body = parse.parse_activity_body(load(name)["text"], versions)
        candidates.append({"title": rules.BATTLE_PASS_TITLE.format(ver=ver), "type": "大月卡",
                           "start_date": body.get("start_date"),
                           "end_date": body.get("end_date")})

    hits = 0
    for c in candidates:
        if not (c.get("start_date") and c.get("end_date")):
            continue
        dup = keys.find_duplicate(c, existing)
        if dup is None:
            same = [e for e in existing if e.get("title") == c.get("title")]
            if same:
                check(f"同标题不同类型（会插重复）：{c['title']}",
                      c.get("type"), same[0].get("type"))
            else:
                print(f"   · 新增候选：{c['type']:5} {c['start_date']} ~ "
                      f"{c['end_date']}  {c['title']}")
            continue
        hits += 1
        for f in ("start_date", "end_date"):
            check(f"日期不一致（已有 → 本轮解析）{c['title']} {f}", dup.get(f), c[f])

    for title in MUST_HIT:
        check(f"必须命中已有条目：{title}",
              any(c.get("title") == title and keys.find_duplicate(c, existing) is not None
                  for c in candidates), True)


# ─── 总纲的活动段（parse_version_activities）─────────────
# §9 的「总纲优先」全靠它：活动在版本更新当天就落盘，比它自己的公告早 12~35 天。

def test_version_activities():
    """盯三件事：段落边界、引号降级、名字里的空格。

    段落边界最容易错：节号每版本不同（3.1 是「七、全新活动」，3.2 是「六、全新活动」），
    段后面还跟着别的编号段（3.1 有「八、全新玩法」），所以只能按「下一个编号段」收尾；
    活动名里可能有空格（`回归丽都 羽落重逢`），空格切不得。
    引号：总纲写 `• 「嗯呢」大派送！`，公告 subject 是 `「『嗯呢』大派送！」活动说明`，
    内层「」要降级成『』，否则标题对不上、去重认不出。
    """
    v = _versions()
    acts31 = parse.parse_version_activities(load("zzz31_version_notes")["content"], v)
    acts32 = parse.parse_version_activities(load("zzz32_version_notes")["content"], v)
    by31 = {a["name"]: a for a in acts31}
    by32 = {a["name"]: a for a in acts32}

    check("3.1 活动条数（多一条就是段落边界溢出了）", len(acts31), 13)
    check("3.2 活动条数", len(acts32), 11)
    check("3.1 首条", (acts31[0]["name"], acts31[0]["start_date"]), ("玛瑟尔周年馈礼", "2026-07-29"))
    check("3.2 首条", (acts32[0]["name"], acts32[0]["start_date"]), ("全新放送", "2026-09-09"))
    check("名字里的空格保留", "回归丽都 羽落重逢" in by31, True)
    check("内层「」降级成『』", "『嗯呢』大派送！" in by31, True)
    check("标题带上外层「」", by31["『嗯呢』大派送！"]["title"], "「『嗯呢』大派送！」")
    check("3.2 的『嗯呢』从天降是另一期同名活动",
          (by32["『嗯呢』从天降"]["start_date"], by32["『嗯呢』从天降"]["end_date"]),
          ("2026-09-30", "2026-10-19"))
    check("活动时间解不出日期时留空、不猜",
          [a["name"] for a in acts31 if not a["start_date"]], [])


def test_notes_activities_match_data():
    """总纲给的日期与已落盘条目实测逐条一致——这是 §9 敢让总纲先落盘的依据。

    一旦有冲突，说明总纲写的不是活动时间（或解析串了段），那时先落盘就会落错日期。
    """
    v = _versions()
    existing = {e.get("title"): e for e in yaml_io.load_events(rules.GAME)}
    compared: list[str] = []
    for name in ("zzz31_version_notes", "zzz32_version_notes"):
        for a in parse.parse_version_activities(load(name)["content"], v):
            e = existing.get(a["title"])
            if not e:
                continue          # 还没落盘的（正是 §9 要提前收进来的那批）
            compared.append(a["title"])
            check(f"总纲与数据文件日期一致：{a['name']}",
                  (a["start_date"], a["end_date"]), (e.get("start_date"), e.get("end_date")))
    # 比对条数会随数据增长，不能钉死；但必须锚一个已知落盘的活动，
    # 否则标题格式一变（比如引号降级坏了）比对会静默变成空转、假通过。
    check("比对不是空转：3.2 首条已落盘的活动在比对范围内",
          "「全新放送」" in compared, True)


# ─── 订正通道（common/calibrate.correct_from_candidates）──
# 建在绝区零的自检里，理由同下面的 keys：它是共用模块（原神/星铁也调），
# 但主要驱动者是本管线。

def test_pending_correction():
    """先落默认类型 + pending 标记 → 公告到了订正类型并补齐描述/配色。"""
    # 1. 类型订正：默认类型 → 公告判出的类型
    ev = {"id": "zzz-常规-2026-09-「惊喜放映企划」", "type": "常规活动",
          "title": "「惊喜放映企划」", "start_date": "2026-09-23", "end_date": "2026-10-19"}
    cand = {"title": "「惊喜放映企划」", "type": "网页活动",
            "start_date": "2026-09-23", "end_date": "2026-10-19"}
    check("类型订正有变更记录", calibrate.correct_from_candidates([ev], [cand]),
          ["「惊喜放映企划」 ← 公告（type 常规活动 → 网页活动）"])
    check("类型已改对", ev["type"], "网页活动")
    check("id 不动（前端拿它追踪「已完成」）", ev["id"], "zzz-常规-2026-09-「惊喜放映企划」")
    check("日期不动", (ev["start_date"], ev["end_date"]), ("2026-09-23", "2026-10-19"))

    # 2. 护栏：候选是默认类型时不写回——它代表「没肯定信号」，不是判据
    welfare = {"title": "「全新放送」", "type": "登录福利",
               "start_date": "2026-09-09", "end_date": "2026-10-19"}
    check("默认类型不写回（不把登录福利抹成常规活动）",
          calibrate.correct_from_candidates([welfare],
                                            [{**welfare, "type": "常规活动"}]), [])
    check("类型原样保留", welfare["type"], "登录福利")
    check("已确认的版本大活动也不会被降级",
          calibrate.correct_from_candidates(
              [{"title": "「悠悠律动舞力聚会」", "type": "版本大活动",
                "start_date": "2026-07-24", "end_date": "2026-08-10"}],
              [{"title": "「悠悠律动舞力聚会」", "type": "常规活动",
                "start_date": "2026-07-24", "end_date": "2026-08-10"}]), [])

    # 3. 待补全：补描述与配色，然后清掉标记（幂等开关）
    pending = {"title": "「数据悬赏-实战模拟」", "type": "常规活动",
               "start_date": "2026-10-14", "end_date": "2026-10-18",
               keys.PENDING_FIELD: "总纲"}
    full = {"title": "「数据悬赏-实战模拟」", "type": "网页活动",
            "start_date": "2026-10-14", "end_date": "2026-10-18",
            "description": "在「数据悬赏」中完成指定任务…", "color": "#f2d9c8"}
    check("待补全条目同时订正类型并补齐",
          calibrate.correct_from_candidates([pending], [full]),
          ["「数据悬赏-实战模拟」 ← 公告（type 常规活动 → 网页活动）"])
    check("描述已补", pending.get("description"), full["description"])
    check("配色已补", pending.get("color"), full["color"])
    check("标记已清（下轮不再重复处理）", keys.PENDING_FIELD in pending, False)
    check("再跑一轮无变更（幂等）",
          calibrate.correct_from_candidates([pending], [full]), [])

    # 4. 只补描述、类型一致时也要有记录，否则补齐这件事在日志里看不见
    plain = {"title": "「跛脚乌鸦奇探录」", "type": "常规活动",
             "start_date": "2026-10-03", "end_date": "2026-10-18",
             keys.PENDING_FIELD: "总纲"}
    check("类型一致时只报补齐",
          calibrate.correct_from_candidates(
              [plain], [{"title": "「跛脚乌鸦奇探录」", "type": "常规活动",
                        "start_date": "2026-10-03", "end_date": "2026-10-18",
                        "description": "…"}]),
          ["「跛脚乌鸦奇探录」 ← 公告（补齐描述与配色）"])

    # 5. 假补：候选**自己也带标记**（总纲列出的那条，每轮都会再产出一条）→ 不许清标记。
    #    总纲候选补不了描述与配图，清掉标记后预筛就不再重抓它的公告正文，永远补不上。
    waiting = {"title": "「天使应援大作战」", "type": "常规活动",
               "start_date": "2026-09-09", "end_date": "2026-11-29",
               keys.PENDING_FIELD: "总纲"}
    check("带标记的候选不参与订正（否则是假补）",
          calibrate.correct_from_candidates([waiting], [dict(waiting)]), [])
    check("标记保留、继续逼着抓正文", waiting.get(keys.PENDING_FIELD), "总纲")

    # 6. 找不到对应条目（本轮新增的候选）→ 什么都不做，新增归 apply_events 管
    check("候选不在已有条目里 → 无变更",
          calibrate.correct_from_candidates([], [full]), [])

    # 7. 类型变了但主键失配时的兜底：这条曾经会插重复（离线复现过）
    old = {"title": "「悠悠律动舞力聚会」", "type": "常规活动",
           "start_date": "2026-07-24", "end_date": "2026-08-10"}
    check("类型从常规活动变成版本大活动仍认得出同一期",
          keys.find_duplicate({"title": "「悠悠律动舞力聚会」", "type": "版本大活动",
                               "start_date": "2026-07-24", "end_date": "2026-08-10"},
                              [old]), old)


def test_pending_forces_body_fetch():
    """带 pending 的条目必须重抓正文——不然类型/配图永远补不上（预筛跳过 = 不落盘）。"""
    sep8 = int(datetime.datetime(2026, 9, 8, 12).timestamp())
    cand = {"title": "「惊喜放映企划」", "post_id": "9", "created_at": sep8}
    done = {"title": "「惊喜放映企划」", "type": "常规活动",
            "start_date": "2026-09-23", "end_date": "2026-10-19"}
    check("没标记时按锚认定已录入（不抓正文）",
          keys.likely_recorded(cand, [done]), True)
    check("带标记时必须抓正文", keys.likely_recorded(cand, [{**done,
                                                             keys.PENDING_FIELD: "总纲"}]), False)


# ─── 去重身份（common/keys.py）───────────────────────────

# 同一期「全新放送」在两个版本各出现一次（3.0 那期见 miyoushe 文章 76019201），
# 同名同类型，只能靠开始日期区分。
QUANXIN_32 = {"title": "「全新放送」", "type": "登录福利",
              "start_date": "2026-09-09", "end_date": "2026-10-19"}
QUANXIN_30 = {"title": "「全新放送」", "type": "登录福利",
              "start_date": "2026-06-17", "end_date": "2026-07-28"}


def test_activity_identity():
    """活动类身份 = (标题, 开始日期)，**不含类型**。两个后果都要盯住：

    1. 类型不在身份里，所以标题与开始日期相同、类型不同算同一条——这正是「先按默认
       类型落盘、等这条活动自己的公告到了再订正类型」能成立的前提。
    2. 日期进了身份，所以同名跨版本不会互吞；但日期也是会被订正的值（本仓库订正过），
       主键失配时靠 find_duplicate 的同名 7 天兜底认回。
    """
    check("同名跨版本不是同一条", keys.find_duplicate(QUANXIN_30, [QUANXIN_32]), None)
    check("同标题同日期同类型是同一条",
          keys.find_duplicate({**QUANXIN_32}, [QUANXIN_32]), QUANXIN_32)
    check("类型不是身份的一部分（改成默认类型仍认得出）",
          keys.find_duplicate({**QUANXIN_32, "type": "常规活动"}, [QUANXIN_32]), QUANXIN_32)
    check("开始日期被订正 1 天仍认得出（同名 7 天兜底）",
          keys.find_duplicate({**QUANXIN_32, "start_date": "2026-09-10"}, [QUANXIN_32]),
          QUANXIN_32)
    check("同名、日期差 8 天 → 另一条（兜底只认 7 天以内的）",
          keys.find_duplicate({**QUANXIN_32, "start_date": "2026-09-17"}, [QUANXIN_32]), None)


def test_likely_recorded():
    """预筛（不抓正文）的判据：同名，且既有条目的开始日期不早于公告发布日。

    预筛只能按标题认——日期写在正文里，候选侧拿不到。而标题会跨版本重名，一律认成
    同一条就会把新一期漏掉；预筛跳过等于不落盘，是真丢数据。所以加一道锚：活动公告
    总在活动开始前发出，列表里刚出现的公告对应的活动不可能早就开始过。
    """
    aug20 = int(datetime.datetime(2026, 8, 20, 12).timestamp())
    sep8 = int(datetime.datetime(2026, 9, 8, 12).timestamp())
    cand = {"title": "「全新放送」", "post_id": "1", "created_at": sep8}

    check("同名且开始日晚于发布日 → 认定已录入",
          keys.likely_recorded(cand, [QUANXIN_32]), True)
    check("只剩上一版本的同名条目 → 不认定（去抓正文）",
          keys.likely_recorded(cand, [QUANXIN_30]), False)
    check("两期都在、其中一期符合锚 → 认定",
          keys.likely_recorded(cand, [QUANXIN_30, QUANXIN_32]), True)
    check("标题对不上 → 不认定",
          keys.likely_recorded({**cand, "title": "「惊喜放映企划」"}, [QUANXIN_32]), False)
    check("没有发布日期 → 不认定（宁可多抓一次）",
          keys.likely_recorded({**cand, "created_at": 0}, [QUANXIN_32]), False)
    check("发布日期不可解析 → 不认定",
          keys.likely_recorded({**cand, "created_at": "2026-09-08"}, [QUANXIN_32]), False)

    # 高难挑战这类「标题每期一字不变」的条目靠公告 id 定身份（原神「幽境危战」）：
    # 标题匹配 + 开始日在未来**不足以**认定，否则新一期会被当成上一期跳过、整期丢失。
    endgame = {"title": "「幽境危战」", "type": "高难挑战",
               "start_date": "2026-09-25", "end_date": "2026-09-29"}
    check("非活动类不参与按标题认定",
          keys.likely_recorded({"title": "「幽境危战」", "post_id": "2", "created_at": sep8},
                               [endgame]), False)

    # 已结束的同名条目（上一版本的同一活动）不该挡住新一期
    check("同名条目的开始日在发布日之前 → 不认定",
          keys.likely_recorded({"title": "「佳礼来信·感恩答谢」", "post_id": "3",
                                "created_at": aug20},
                               [{"title": "「佳礼来信·感恩答谢」", "type": "登录福利",
                                 "start_date": "2026-07-01", "end_date": "2026-07-20"}]),
          False)


def main():
    for fn in (test_version_notes, test_banners, test_activities, test_battle_passes,
               test_classification, test_endgame_grid, test_bilibili,
               test_matches_existing, test_version_activities,
               test_notes_activities_match_data, test_pending_correction,
               test_pending_forces_body_fetch, test_activity_identity,
               test_likely_recorded):
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
