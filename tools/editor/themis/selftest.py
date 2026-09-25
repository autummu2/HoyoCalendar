"""未定事件簿解析规则的离线自检：python themis/selftest.py

用 fixtures/ 里的真实抓取结果（资讯栏 50 条 + 公告栏 45 条，2026-09-25 抓，含正文）
断言 parse.py 的每条规则。不联网、不写数据文件（**会读**数据文件逐字比对既有条目）。

重点盯四件事，前三件错了会在下一轮静默插重复条目或改坏日期：
- **标题**：它是去重主键（keys.event_key），得与数据文件里的既有条目对得上。
- **类型**：不在主键里（活动类的身份是标题 + 开始日期），判错不插重复但会一直显示错。
- **日期口径**：终点 `04:00`（未定的游戏日边界）减一天，起点不减；
  `00:00` / `23:59`（中秋、教师节）两个端点都照抄。
- **标签**：不进主键，但会随条目写进数据文件，所以逐条与手工数据交叉验证（test_tags）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import keys, yaml_io  # noqa: E402
from themis import parse, pipeline, rules  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
GAME = rules.GAME

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


NEWS = load("tea_news")                 # 资讯栏 50 条（含正文，2026-09-25 11:00 的快照）
VERSION_POSTS = load("tea_version_posts")   # 公告栏 45 条（只有标题与发布时间）
# 快照之后才出现的一篇（主题是往期复刻、内容是商城上架），单独放：夹具保持「同一时刻的窗口」
SHOP = load("tea_shop_reprint")
BODY = {str(p["post_id"]): p["text"] for p in NEWS}
POST = {p["subject"]: p for p in NEWS}


def body_of(post_id):
    """collect 的注入口：只从 fixtures 取正文，不联网。"""
    return BODY.get(str(post_id), ""), []


# ─── 第一道闸：标题负向名单 ───────────────────────────────

def test_title_skip():
    kept = parse.find_news(NEWS)
    dropped = [p for p in NEWS if p not in kept]
    check("过闸条数", len(kept), 31)
    check("拦下条数", len(dropped), 19)

    # 名单里唯一「带完整时段仍要排除」的一类：累充。第二道闸拦不住它（有日期），
    # 只能靠名单 —— 所以这条同时断言「它确实有完整时段」，否则这条断言会失真。
    lc = "岁悦同欢·莫弈篇丨限时累充活动预告 累计充值得丰厚奖励"
    check("限时累充有完整时段（所以必须靠名单挡）",
          parse.parse_period(POST[lc]["text"]), ("2026-09-20", "2026-09-29"))
    check("限时累充被名单挡下", [p["subject"] for p in kept].count(lc), 0)

    # 节日福利帖**不**在名单里（`快乐丨` 没进名单）：中秋/教师节都带游戏内登录奖励
    check("中秋快乐过闸", "中秋快乐丨佳节长相伴，今宵共团圆" in [p["subject"] for p in kept], True)
    check("教师节快乐过闸", "教师节快乐丨春风化雨，桃李芬芳" in [p["subject"] for p in kept], True)

    # 抽查几条各类非游戏内内容
    for s in ("未定事件簿OST11：暗涌无终丨谜影重重，何人生还？",
              "捐赠证书丨「绘景溯时」公益金额公示",
              "《未定事件簿》×TOPTOY「甜心奇遇」解压键帽盲盒贩售开启",
              "插画分享丨夜阑梦隐，晨光可期"):
        check(f"名单命中 {s[:14]}", s in [p["subject"] for p in kept], False)


# ─── 时间口径 ────────────────────────────────────────────

# (标题前缀, 起, 止)。全部来自正文里的 ▶活动时间
PERIODS = [
    ("中秋快乐", "2026-09-25", "2026-09-27"),          # 00:00 ~ 23:59 两端都照抄
    ("教师节快乐", "2026-09-10", "2026-09-12"),        # 同上，且没有「▶活动时间」字样
    ("邮轮之旅前音", "2026-09-24", "2026-10-17"),       # 终点 04:00 → 减一天
    ("轮替女神之影更新", "2026-09-18", "2026-10-02"),   # 终点 11:00 → 照抄
    ("往期复刻丨「心有所欲」", "2026-09-15", "2026-09-19"),
    ("全新绮思", "2026-09-10", "2026-10-14"),
    ("星航寻梦", "2026-09-10", "2026-09-16"),
    ("爱的未定式·夏彦篇", "2026-09-03", "2026-09-09"),
    ("往期复刻丨「濯影拾辉」", "2026-08-27", "2026-08-31"),
    ("青葱寄愿", "2026-08-27", "2026-09-05"),
    ("NXX特别调查", "2026-08-27", "2026-09-15"),
]


def test_period():
    for prefix, start, end in PERIODS:
        p = next(p for s, p in POST.items() if s.startswith(prefix))
        check(f"日期 {prefix[:14]}", parse.parse_period(p["text"]), (start, end))

    # 起点写成「更新后」：日期部分照抄（本窗口内只有 NXX 预告帖这么写，且它没有终点）
    check("更新后-起点照抄",
          parse.parse_period("▶活动时间：2026年9月30日更新后-10月18日04:00"),
          ("2026-09-30", "2026-10-17"))

    # `至` 不做分隔符：实测 95 篇里 3 次命中全是假阳性，故只认 - – —
    check("不以 至 为分隔符",
          parse.parse_period("将于 1月6日10:30 左右进行更新"), (None, None))
    check("不以 至 为分隔符（摆放至）",
          parse.parse_period("拖动拼图碎片摆放至正确的位置"), (None, None))

    # 终点省略年份、月份回绕 → 跨年
    check("跨年补年份",
          parse.parse_period("活动时间：2026年12月30日11:00-1月5日04:00"),
          ("2026-12-30", "2027-01-04"))


# ─── 分类 ────────────────────────────────────────────────

# (标题, 期望类型)。None = 丢弃
CLASSIFY = [
    # 卡池：信号在主题里的（轮替返场）与在子标题里的（活动女神之影开启）
    ("轮替女神之影更新丨夏彦SSR【夏花永隽】限时返场", "卡池"),
    ("轮替女神之影丨莫弈SSR【莫负良辰】限时返场", "卡池"),
    ("换日线丨活动女神之影开启 夏彦SSR【换日线】概率提升", "卡池"),
    # 复刻二分：女神之影 → 卡池；活动系列 / 礼包 / 商城上架 → 丢弃
    ("往期复刻丨「NXX-冰原上的审判」活动女神之影限时复刻", "卡池"),
    # 复刻的卡池信号只在正文里（子标题是「莫弈生日系列限时复刻」）—— 正文通篇女神之影
    ("往期复刻丨莫弈生日系列限时复刻", "卡池"),
    ("往期复刻丨「NXX-冰原上的审判」活动系列限时复刻", None),
    ("往期复刻丨「濯影拾辉」活动限时复刻", "常规活动"),
    ("往期复刻丨「心有所欲」活动限时复刻", "常规活动"),
    # 大月卡 / 登录福利 / 常规活动
    ("全新绮思丨「秋颂绮思」正式上线，解锁绮思获得丰厚奖励", "大月卡"),
    ("邮轮之旅前音丨限时签到预告 累签可得【女神之泪·限时】×10", "登录福利"),
    ("青葱寄愿丨限时活动开启 签到领取甜心家装图纸及【女神之泪】", "常规活动"),
    # 节日福利：主题以「快乐」结尾 + 正文说登录领邮件（不建节日名单）
    ("中秋快乐丨佳节长相伴，今宵共团圆", "登录福利"),
    ("教师节快乐丨春风化雨，桃李芬芳", "登录福利"),
    # 复合标签 → 版本大活动（标签在正文里）
    ("NXX-非常假日丨全新活动玩法，共度荒岛时光", "版本大活动"),
    ("NXX-非常假日丨活动限定陆景和SSR思绪【我心遥遥】", "版本大活动"),
]


def test_classify():
    for subject, want in CLASSIFY:
        p = POST.get(subject)
        check(f"分类 {subject[:16]}", parse.classify(subject, p["text"] if p else ""), want)

    # 商城上架：`往期复刻丨往期绮思限定甜心服饰常驻上架短笺兑换所`（9/30~10/17）
    # 主题是往期复刻、所以躲过了 `商城上新` 那道标题名单；正文通篇礼包上架与兑换所，
    # 没有玩法。它有完整时段 ⇒ 第二道闸拦不住，只能靠子标题的 `上架` 判据。
    check("商城上架帖丢弃", parse.classify(SHOP["subject"], SHOP["text"]), None)
    check("商城上架帖有完整时段（所以必须靠判据挡）",
          parse.parse_period(SHOP["text"]), ("2026-09-30", "2026-10-17"))

    # 标签判据本身：`◯◯主题活动「◯◯」` 命中，`限时活动「◯◯」` / `◯◯生日活动「◯◯」` 不命中
    check("复合标签命中", parse.big_event_label(
        "✨9月30日更新后，海岛主题活动「NXX-非常假日」正式上线！"), "NXX-非常假日")
    check("限时活动不算版本大活动", parse.big_event_label(
        "「心跳低喃时」限时活动即将开启"), None)
    check("生日活动不算版本大活动", parse.big_event_label(
        "莫弈生日活动「岁悦同欢·莫弈篇」即将开启"), None)


# ─── 标题 ────────────────────────────────────────────────

TITLES = [
    # 与数据文件逐字一致的四类
    ("往期复刻丨「濯影拾辉」活动限时复刻", "常规活动", "「濯影拾辉」活动限时复刻"),
    ("往期复刻丨「NXX-冰原上的审判」活动女神之影限时复刻", "卡池",
     "「NXX-冰原上的审判」活动女神之影限时复刻"),
    ("换日线丨活动女神之影开启 夏彦SSR【换日线】概率提升", "卡池", "夏彦SSR【换日线】"),
    ("全新绮思丨「秋颂绮思」正式上线，解锁绮思获得丰厚奖励", "大月卡", "「秋颂绮思」"),
    ("爱的未定式·夏彦篇丨限时活动预告 全新动态Q版邀请函限时上架", "常规活动",
     "「爱的未定式·夏彦篇」"),
    ("青葱寄愿丨限时活动开启 签到领取甜心家装图纸及【女神之泪】", "常规活动", "「青葱寄愿」"),
    # 靠主题兜底的：子标题里没有「…」
    ("中秋快乐丨佳节长相伴，今宵共团圆", "登录福利", "「中秋快乐」"),
    # 同一期活动的两篇帖子（§4.2 的区分后缀）：子标题含 `生日拼图` 的加后缀，
    # 生日活动本体那篇不加 —— 后缀是逐例名单，不命中的照旧只用主题
    ("岁悦同欢·莫弈篇丨生日拼图限时活动预告", "常规活动", "「岁悦同欢·莫弈篇」生日拼图"),
    ("岁悦同欢·莫弈篇丨免费获取多重生日限定福利", "常规活动", "「岁悦同欢·莫弈篇」"),
    # 轮替返场：主题里是卡池信号，但标题取子标题的角色名，别取成「轮替女神之影更新」
    ("轮替女神之影更新丨夏彦SSR【夏花永隽】限时返场", "卡池", "夏彦SSR【夏花永隽】"),
]


def test_titles():
    for subject, etype, want in TITLES:
        check(f"标题 {subject[:16]}", parse.title_of(subject, "", etype), want)


# ─── 标签 ────────────────────────────────────────────────

# (标题, 期望标签)。正文取自 fixtures 里的真实帖子
TAGS = [
    # 标题命中就不看正文：轮替返场帖的正文把整个轮替池列了一遍
    # （正文里 夏彦/左然/莫弈/陆景和 与 SR 都有，只有标题才指向当期那一个）
    ("轮替女神之影丨莫弈SSR【莫负良辰】限时返场", ["莫弈", "SSR"]),
    ("轮替女神之影更新丨夏彦SSR【夏花永隽】限时返场", ["夏彦", "SSR"]),
    # 活动名在标题里、名字与稀有度拖在子标题（`… 左然MR【幻航】开放获取`）
    ("星航寻梦丨限时活动预告 左然MR【幻航】开放获取", ["左然", "MR"]),
    ("爱的未定式·夏彦篇丨限时活动预告 全新动态Q版邀请函限时上架", ["夏彦"]),
    # 标题认不出 → 退到正文：复刻帖标题只有活动名，左然 MR 只在正文里
    ("往期复刻丨「濯影拾辉」活动限时复刻", ["左然", "MR"]),
    ("往期复刻丨「NXX-冰原上的审判」活动女神之影限时复刻",
     ["夏彦", "左然", "莫弈", "陆景和", "SSR"]),
    # 标题里有名字，正文里的 SSR 就不算 —— 手工数据里 `「爱的未定式·夏彦篇」`
    # 正文写着 SSR（description 就是它）而 tags 只有 `夏彦`，所以标题命中即整条不看正文
    ("往期复刻丨莫弈生日系列限时复刻", ["莫弈"]),
    # 两个来源都认不出 → 没有标签
    ("青葱寄愿丨限时活动开启 签到领取甜心家装图纸及【女神之泪】", []),
    ("NXX特别调查丨限时活动预告 全新拼图【春知】开放获取", []),
]


def test_tags():
    for subject, want in TAGS:
        p = POST[subject]
        check(f"标签 {subject[:16]}", parse.detect_tags(subject, p["text"]), want)

    # 合成的边界：多人按官方顺序（与输入顺序无关）、稀有度排在名字后、联动
    check("多人按官方顺序",
          parse.detect_tags("陆景和 莫弈 夏彦 左然", ""),
          ["夏彦", "左然", "莫弈", "陆景和"])
    check("SR 不误命中 SSR", parse.detect_tags("左然SSR【幻航】", ""), ["左然", "SSR"])
    check("联动", parse.detect_tags("阿加莎联动活动「何人生还」", ""), ["联动"])
    check("正文兜底也认不出就不给标签", parse.detect_tags("青葱寄愿", "签到领图纸"), [])

    # 与手工数据交叉验证：标题能对上的条目，标签集合必须相同（手工缺 tags = 无标签）。
    # ⚠️ 只比集合不比顺序：手工的 3 条旧条目是「稀有度在前」的旧惯例（`['MR','左然']`），
    # 与最新的 3 条（名字在前）不一致。顺序一律名字在前 —— 与卡池标题
    # （`左然MR【幻航】`）的写法一致，由上面的 TAGS 表断言。
    existing = yaml_io.load_events(GAME)
    by_title: dict = {}
    for e in existing:
        by_title.setdefault(e["title"], e)
    n = 0
    for e in pipeline.collect(NEWS, VERSION_POSTS, body_of):
        m = by_title.get(e["title"])
        if not m:
            continue
        n += 1
        check(f"标签与手工一致 {e['title'][:14]}",
              sorted(e["tags"]), sorted(m.get("tags") or []))
    check("可比对条数", n, 10)   # 18 条候选里标题能与手工条目对上的条数。
                                # 加后缀前后都是 10：以前 9/17 那条是**并到** 9/20 那条上
                                # 比对的（两条同名），现在对上的是它自己那条（`…生日拼图`）


# ─── 公告栏：版本停服公告 ─────────────────────────────────

def test_version_notes():
    notes = parse.parse_version_notes(VERSION_POSTS)
    check("停服公告条数", len(notes), 5)
    check("版本序列", [n["version"] for n in notes], ["6.0", "5.9", "5.8", "5.7", "5.6"])
    check("开服日", [n["date"] for n in notes],
          ["2026-08-20", "2026-07-09", "2026-04-30", "2026-03-19", "2026-02-10"])
    # 只发最新那一版：窗口里躺着 5 份，全发等于回填 4 个历史版本（裁定 14）
    evs = pipeline._version_events(VERSION_POSTS)
    check("只发最新版本", [(e["title"], e["start_date"]) for e in evs],
          [("《未定事件簿》6.0 版本停服更新", "2026-08-20")])

    # 标题里的日期没有年份，年份取自发布日；跨年（12 月发 1 月的公告）要 +1 年
    jan = parse.parse_version_notes([
        {"subject": "7.0版本更新丨1月8日08:00停服更新公告", "post_id": "x",
         "created_at": 1798675200},   # 2026-12-31
    ])
    check("跨年公告补年份", jan[0]["date"], "2027-01-08")

    # 日常更新公告 / 内容清单不是停服公告，不进版本条目
    check("日常更新公告不入选", parse.parse_version_notes([
        {"subject": "《未定事件簿》9月17日游戏日常更新公告", "post_id": "y",
         "created_at": 0}]), [])


# ─── 端到端：collect（离线，fixtures 的 50 + 45 条）───────────

# 落盘候选全表。顺序 = 版本更新在前，其余按发布时间倒序（fixtures 的顺序）
EXPECTED = [
    ("《未定事件簿》6.0 版本停服更新", "版本更新", "2026-08-20", "2026-08-20"),
    ("「中秋快乐」", "登录福利", "2026-09-25", "2026-09-27"),
    ("「邮轮之旅前音」", "登录福利", "2026-09-24", "2026-10-17"),
    ("夏彦SSR【夏花永隽】", "卡池", "2026-09-18", "2026-10-02"),
    ("「岁悦同欢·莫弈篇」", "常规活动", "2026-09-20", "2026-09-29"),
    # 生日系列复刻：正文通篇女神之影（两段不同时段的卡池），子标题没有任何卡池字样
    ("莫弈生日系列限时复刻", "卡池", "2026-09-17", "2026-09-19"),
    # 生日拼图：主题兜底 + 子标题里的区分后缀（§4.2），与手工那条逐字相同
    ("「岁悦同欢·莫弈篇」生日拼图", "常规活动", "2026-09-17", "2026-09-24"),
    ("「心有所欲」活动限时复刻", "常规活动", "2026-09-15", "2026-09-19"),
    ("「教师节快乐」", "登录福利", "2026-09-10", "2026-09-12"),
    ("「秋颂绮思」", "大月卡", "2026-09-10", "2026-10-14"),
    ("「星航寻梦」", "常规活动", "2026-09-10", "2026-09-16"),
    ("莫弈SSR【莫负良辰】", "卡池", "2026-09-04", "2026-09-18"),
    ("「爱的未定式·夏彦篇」", "常规活动", "2026-09-03", "2026-09-09"),
    ("夏彦SSR【换日线】", "卡池", "2026-09-03", "2026-09-09"),
    ("「NXX-冰原上的审判」活动女神之影限时复刻", "卡池", "2026-08-27", "2026-09-05"),
    ("「濯影拾辉」活动限时复刻", "常规活动", "2026-08-27", "2026-08-31"),
    ("「青葱寄愿」", "常规活动", "2026-08-27", "2026-09-05"),
    ("「NXX特别调查」", "常规活动", "2026-08-27", "2026-09-15"),
]


def test_collect():
    evs = pipeline.collect(NEWS, VERSION_POSTS, body_of)
    got = [(e["title"], e["type"], e["start_date"], e["end_date"]) for e in evs]
    check("候选条数", len(got), 18)
    check("候选全表", got, EXPECTED)

    # 去重：三篇「岁悦同欢·莫弈篇」合出两条（生日拼图 9/17、生日活动 9/20，两条名字
    # 已由后缀区分），两篇「爱的未定式·夏彦篇」合出一条
    titles = [t for t, *_ in got]
    check("岁悦同欢合出两条", len([t for t in titles if "岁悦同欢" in t]), 2)

    # 漏斗记账：候选 / 丢弃各自有据（日志与 dry-run 都靠 DECISIONS）
    v = [d["verdict"] for d in pipeline.DECISIONS]
    check("判定表条数", len(v), 31)
    check("丢弃条数", v.count("丢弃"), 12)   # 31 条过闸 - 19 条候选（其中 1 组被去重合并）

    # 没有完整时段的一律不落盘 —— NXX-非常假日 这一期在窗口内没有任何带结束日的帖子
    check("无时段不落盘", [t for t, *_ in got if "非常假日" in t], [])


# ─── 身份（主键）：未定卡池带日期、日期兜底取精确口径 ────────

def test_identity():
    card = {"type": "卡池", "title": "夏彦SSR【换日线】", "start_date": "2026-09-03",
            "end_date": "2026-09-09"}
    check("未定卡池主键带日期", keys.event_key(card, GAME),
          ("卡池", "夏彦SSR【换日线】", "2026-09-03"))
    # 另三端不受影响：不给 game 时卡池主键照旧不含日期
    check("三端卡池主键不变", keys.event_key(card), ("卡池", "夏彦SSR【换日线】"))

    # 返场：同一思绪两期，标题逐字相同 → 靠日期区分（不清日期就会静默丢掉新一期）
    rep = {**card, "start_date": "2026-09-18", "end_date": "2026-10-02"}
    check("返场另一期不算重复", keys.find_duplicate(rep, [card], GAME), None)
    check("同其一期能认出", keys.find_duplicate({**card}, [card], GAME)["start_date"],
          "2026-09-03")

    # 日期兜底的口径按端点（keys.EXACT_FALLBACK_GAMES）：
    #   未定不接 calibrate ⇒ 精确口径，只认同名同起日或同源帖，没有 ±7 天的窗口
    #   三端日期会被校准改写 ⇒ 仍是 ±7 天
    act = {"type": "常规活动", "title": "「青葱寄愿」", "start_date": "2026-08-27"}
    moved = {**act, "start_date": "2026-08-29"}
    # ⚠️ 代价就在这里：同名、日期被订正过、又没有同源帖时会插一条**可见的重复**。
    # 旧口径不会插，但那是拿 ±7 天窗口换来的，而窗口的代价是可能静默吞掉一条活动。
    check("未定不认「日期挨着」（3 天也不行）", keys.find_duplicate(moved, [act], GAME), None)
    check("三端仍认「日期挨着」",
          keys.find_duplicate(moved, [act], "genshin-impact"), act)
    # 人工订正日期后主键失配 → 靠同源帖认回（改的正是那篇帖子产出的条目）
    post = {"post_id": "77910710"}
    check("日期被订正后靠同源帖认回",
          keys.find_duplicate({**moved, **post}, [{**act, **post}], GAME)["start_date"],
          "2026-08-27")
    check("同源帖判据不跨活动",
          keys.find_duplicate({**moved, "post_id": "1"}, [{**act, "post_id": "2"}], GAME), None)
    # 两条同名不同期的活动（9/17 拼图 / 9/20 本体）在精确口径下互不吞并
    puzzle = {"type": "常规活动", "title": "「岁悦同欢·莫弈篇」生日拼图",
              "start_date": "2026-09-17"}
    main = {"type": "常规活动", "title": "「岁悦同欢·莫弈篇」", "start_date": "2026-09-20"}
    check("同名不同期各算各的", keys.find_duplicate(main, [puzzle], GAME), None)

    # 活动类的身份不受影响：仍是 (标题, 开始日期)
    check("活动类主键不变", keys.event_key(act, GAME), ("「青葱寄愿」", "2026-08-27"))


# ─── 与数据文件的交叉比对 ─────────────────────────────────

def test_matches_existing():
    existing = yaml_io.load_events(GAME)
    evs = pipeline.collect(NEWS, VERSION_POSTS, body_of)
    dup = {e["title"] for e in evs if keys.find_duplicate(e, existing, GAME)}
    # 标题与手工条目逐字相同的十个 —— 认得出来，apply_events 会跳过
    check("认得出手工已有的条目", sorted(dup),
          ["「NXX-冰原上的审判」活动女神之影限时复刻", "「NXX特别调查」",
           "「岁悦同欢·莫弈篇」", "「岁悦同欢·莫弈篇」生日拼图", "「星航寻梦」",
           "「濯影拾辉」活动限时复刻", "「爱的未定式·夏彦篇」", "「秋颂绮思」",
           "「青葱寄愿」", "夏彦SSR【换日线】"])

    # 标题对齐（RULES §4.2 裁定 15）：手工的 `「星航寻梦」-左然MR【幻航】` /
    # `NXX特别调查-主线第二十章` 已改成管线取的活动名，主键直接命中 ⇒ 首轮零重复。
    for title in ("「星航寻梦」", "「NXX特别调查」"):
        e = next(e for e in evs if e["title"] == title)
        check(f"标题已对齐 {title}", keys.find_duplicate(e, existing, GAME) is not None, True)

    # 「岁悦同欢·莫弈篇」两期**各自主键命中**：
    #   09-20 生日活动本体 → 标题即主题，主键 (标题, 09-20) 命中
    #   09-17 生日拼图     → 候选名带后缀，与手工那条（同名同起日）逐字相同 ⇒ 主键命中
    # 这就是 2026-09-25 收紧判定要达到的效果：两条同名不同期的活动不再靠 ±7 天窗口
    # 区分 —— 那个窗口会把先落的那条吞掉（见 RULES §4.2、keys.EXACT_FALLBACK_GAMES）。
    for date in ("2026-09-20", "2026-09-17"):
        e = next(e for e in evs if "岁悦同欢" in e["title"] and e["start_date"] == date)
        check(f"岁悦同欢 {date} 靠主键认回",
              keys.find_duplicate(e, existing, GAME) is not None, True)


def main():
    for fn in (test_title_skip, test_period, test_classify, test_titles, test_tags,
               test_version_notes, test_collect, test_identity, test_matches_existing):
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
