"""星铁解析规则的离线自检：python starrail/selftest.py

用 fixtures/ 里保存的真实公告（米游社正文 + B站动态原文）断言 parse.py 的每个解析器。
不联网、不写数据文件（**会读**数据文件逐字比对既有条目）。

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

from common import body_cache, calibrate  # noqa: E402
from common import keys  # noqa: E402
from common import yaml_io  # noqa: E402
from starrail import parse, pipeline, rules  # noqa: E402

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


# ─── 总纲的活动段（总纲优先，PLAN.md §1.2）────────────────

def _notes_item(name: str) -> tuple[dict, str]:
    """fixture → (notes, text)，与 pipeline._collect_notes 的产出同形。"""
    d = load(name)
    n = parse.parse_version_notes(d["text"], d["subject"])
    n["post_id"] = d["post_id"]
    return n, d["text"]


def _versions(*names: str) -> dict:
    """{版本号: (起, 止)} —— 与管线同路：说明先变成版本更新条目（`_build_version_events`，
    本版 + 下版），再由条目推表（`_version_table`）。不是另写一套算法。"""
    entries: list[dict] = []
    for n, _text in map(_notes_item, names):
        entries += pipeline._build_version_events(n, None, [])
    return pipeline._version_table(entries)


def test_version_table():
    """版本周期表由**条目**推（2026-09-22 改口径）：止 = 下一条的日期 − 1 天。

    原先是「窗口里每份说明都读、用它们现算」——而那张表本来就推得出来（原神一向如此：
    `inference.extract_version_dates` 从数据文件读版本更新日）。这里钉住新算法，以及
    「本轮候选覆盖数据文件里的旧日期」与「不是版本更新的条目不进表」。
    """
    entries = [{"title": rules.VERSION_UPDATE_TITLE.format(ver="4.4", name="鸣笛于归寂之时"),
                "type": "版本更新", "start_date": "2026-07-15"},
               {"title": rules.VERSION_UPDATE_TITLE.format(ver="4.5", name="挥掷千星的筹码"),
                "type": "版本更新", "start_date": "2026-08-26"},
               {"title": rules.VERSION_PLACEHOLDER_TITLE.format(ver="4.6"),   # 占位：只有日期
                "type": "版本更新", "start_date": "2026-09-28"},
               {"title": "《崩坏：星穹铁道》4.5 版本前瞻特别节目",            # 不是版本更新
                "type": "前瞻直播", "start_date": "2026-09-18"}]
    check("版本周期表由条目推", pipeline._version_table(entries),
          {"4.4": ("2026-07-15", "2026-08-25"),
           "4.5": ("2026-08-26", "2026-09-27"),
           "4.6": ("2026-09-28", None)})         # 最后一条没有下一条，止留空
    check("候选覆盖同名版本的旧日期（更新预告的修正要生效）",
          pipeline._version_table(entries + [
              {"title": rules.VERSION_UPDATE_TITLE.format(ver="4.6", name="月升之前，与兽共舞"),
               "type": "版本更新", "start_date": "2026-10-01"}])["4.5"],
          ("2026-08-26", "2026-09-30"))
    check("没有版本更新条目就没有表", pipeline._version_table([]), {})
    check("标题里没有版本号的不进表",
          pipeline._version_table([{"title": "《崩坏：星穹铁道》停服更新", "type": "版本更新",
                                    "start_date": "2026-09-28"}]), {})

    # 与真实数据文件对：表推出来的 4.4/4.5 期间必须等于**说明正文里算出来的**（改口径前的
    # 算法）。两侧都是真公告、真数据——不一致就说明有一边错了。
    table = pipeline._version_table(yaml_io.load_events(rules.GAME))
    check("数据文件推得的 4.4/4.5 与说明正文一致",
          {v: table.get(v) for v in ("4.4", "4.5")},
          {v: _versions("hsr44_version_notes", "hsr45_version_notes")[v]
           for v in ("4.4", "4.5")})


def test_notes_activities():
    """总纲 `X、全新活动` 段 → 活动名与日期。

    钉住四件事：段号按**后缀**定位（段号每版不同）、嵌套引号降级成『』、
    「N.N版本更新后」换成那一版的开服日、「只解得出一个日期就不收」。fixtures 是冻结的
    真实公告，所以条目数可以直接写死（不是随数据长的名单）。
    """
    versions = _versions("hsr44_version_notes", "hsr45_version_notes")

    check("4.4 总纲活动段",
          [(a["title"], a["start_date"], a["end_date"]) for a in
           parse.parse_version_activities(load("hsr44_version_notes")["text"], versions)],
          [("「反贪『砖』家」", "2026-07-15", "2026-08-25"),   # 总纲写「砖」，公告写『砖』
           ("「命运/银河铁道之夜」", "2026-07-24", "2026-08-25"),
           ("「命运契约•再启」", None, None),                 # 终点「4.6版本结束前」，不猜
           ("「命运赠礼」", "2026-07-24", "2026-08-25"),
           ("「巡星之礼」", None, None)])                     # 总纲没给活动时间
    check("4.5 总纲活动段",
          [(a["title"], a["start_date"], a["end_date"]) for a in
           parse.parse_version_activities(load("hsr45_version_notes")["text"], versions)],
          [("「超限：狂飙大奖赛」", "2026-08-26", "2026-09-27"),
           ("「方寸大冒险」", "2026-09-12", "2026-09-27"),
           ("「巡星之礼」", None, None)])

    # 登录福利（巡星之礼）：总纲里没有 `活动时间：` 的那一条，时段按版本期间算、类型就地判出。
    # 判据是「条目本文没有 `活动时间：`」而不是「日期解不出来」——后者会把「命运契约•再启」
    # （有 `活动时间：`，只是终点写作「4.6版本结束前」）也套上版本期间，落一段错日期。
    welfare = [a for a in parse.parse_version_activities(
        load("hsr45_version_notes")["text"], versions, "4.5") if a["title"] == "「巡星之礼」"][0]
    check("登录福利：时段取版本期间", (welfare["start_date"], welfare["end_date"]),
          ("2026-08-26", "2026-09-27"))
    check("登录福利：类型与描述就地给出（它没有自己的公告可等）",
          (welfare["type"], welfare["description"]),
          ("登录福利", "活动期间，每日登录游戏即可获得签到奖励。完成7日签到累计可领取星轨专票*10！"))
    check("有 `活动时间：` 但终点是相对版本号的不套版本期间（命运契约•再启）",
          [a["start_date"] for a in parse.parse_version_activities(
              load("hsr44_version_notes")["text"], versions, "4.4")
           if a["title"] == "「命运契约•再启」"], [None])

    text45 = load("hsr45_version_notes")["text"]
    check("段号换了也能定位（按后缀，不按段号）",
          [a["title"] for a in parse.parse_version_activities(
              text45.replace("6、全新活动", "9、全新活动"), versions)],
          ["「超限：狂飙大奖赛」", "「方寸大冒险」", "「巡星之礼」"])
    check("没有活动段就返回空", parse.parse_version_activities("1、全新剧情 无所谓", versions), [])
    # 第二道确认：同样没写 `活动时间：`，但没有登录福利的措辞 → 不套版本期间（宁可等，不猜）
    plain = text45.replace(
        "活动期间，每日登录游戏即可获得签到奖励。完成7日签到累计可领取星轨专票*10！",
        "活动期间，完成指定探索任务可获得星轨专票*10！")
    check("没写 `活动时间：` 也不是登录福利措辞的不套版本期间",
          [(a["start_date"], a.get("type")) for a in parse.parse_version_activities(
              plain, versions, "4.5") if a["title"] == "「巡星之礼」"], [(None, None)])
    check("版本开服日未知时不猜（起止留空）",
          [(a["start_date"], a["end_date"]) for a in parse.parse_version_activities(
              load("hsr44_version_notes")["text"], {})][0], (None, None))


def test_notes_candidates():
    """总纲候选：只收当前版本那份、默认类型 + `pending` 标记、日期不齐的不进。"""
    versions = _versions("hsr44_version_notes", "hsr45_version_notes")
    notes45, text45 = _notes_item("hsr45_version_notes")

    cands = pipeline._activities_from_notes(notes45, text45, versions)
    check("只收当前版本那份总纲", [c["title"] for c in cands],
          ["「超限：狂飙大奖赛」", "「方寸大冒险」", "「巡星之礼」"])
    check("候选落默认类型（总纲给不出类型）", [c["type"] for c in cands],
          [calibrate.DEFAULT_ACTIVITY_TYPE] * 2 + ["登录福利"])
    check("候选带 pending 标记（登录福利那条不带）",
          [c.get(keys.PENDING_FIELD) for c in cands], ["总纲", "总纲", None])
    check("登录福利候选带描述（不靠正文公告）",
          [bool(c.get("description")) for c in cands], [False, False, True])
    check("日期不齐的不进候选（4.4 那版的命运契约•再启）",
          any(c["title"] == "「命运契约•再启」" for c in cands), False)
    # 标记必须能过产物 JSON 那道白名单。漏掉它，活动照落盘、标记却带不出去，
    # 下一轮预筛就按「已录入」跳过它的公告正文——描述与配色永远补不上，整条路空转。
    check("产物白名单带 pending", keys.PENDING_FIELD in pipeline.OUT_FIELDS, True)


def test_pending_correction():
    """总纲落盘的那条 → 它自己的公告到了：订正类型、补描述与配色、清掉标记。

    这里是星铁侧的用例。共用模块 `correct_from_candidates` 的完整矩阵（两条护栏、假补、
    幂等、id/日期不动…）建在 zenless/selftest.py 的 test_pending_correction 里——
    那条线是这套机制的主驱动者，不重复整套。
    """
    notes45, text45 = _notes_item("hsr45_version_notes")
    cands = pipeline._activities_from_notes(notes45, text45, _versions("hsr45_version_notes"))
    landed = dict(cands[0])                      # 先落盘的样子：常规活动 + pending
    check("总纲落盘的样子", (landed["type"], landed.get(keys.PENDING_FIELD)),
          ("常规活动", "总纲"))

    # ① 只有总纲候选再过一轮：不许动它。它自己也缺描述与配色，清了标记就等于假补
    #    （标记一清，预筛就不再重抓这条活动的公告正文，那两样永远补不上）
    check("总纲候选不给自己补全", calibrate.correct_from_candidates([landed], cands), [])
    check("标记还在", landed.get(keys.PENDING_FIELD), "总纲")

    # ② 公告到了、类型不变（「超限：狂飙大奖赛」在数据文件里就是常规活动）→ 只补齐
    ann = {"title": "「超限：狂飙大奖赛」", "type": "常规活动",
           "start_date": "2026-08-26", "end_date": "2026-09-27",
           "description": "千星城全新的赛车比赛…", "color": "#fdcccc"}
    check("公告补齐描述与配色", calibrate.correct_from_candidates([landed], [ann]),
          ["「超限：狂飙大奖赛」 ← 公告（补齐描述与配色）"])
    check("描述已补", landed.get("description"), ann["description"])
    check("配色已补（取色排在订正之前才算得出来）", landed.get("color"), ann["color"])
    check("标记已清", keys.PENDING_FIELD in landed, False)
    check("再跑一轮无变更（幂等）", calibrate.correct_from_candidates([landed], [ann]), [])

    # ③ 类型也要改的（「反贪『砖』家」的正文写「4.4版本期间」→ 版本大活动）
    p44 = {"title": "「反贪『砖』家」", "type": calibrate.DEFAULT_ACTIVITY_TYPE,
           "start_date": "2026-07-15", "end_date": "2026-08-25",
           keys.PENDING_FIELD: "总纲"}
    a44 = {**p44, "type": "版本大活动", "color": "#defeef"}
    a44.pop(keys.PENDING_FIELD)
    check("类型与补齐一起发生", calibrate.correct_from_candidates([p44], [a44]),
          ["「反贪『砖』家」 ← 公告（type 常规活动 → 版本大活动）"])
    check("类型已改对", p44["type"], "版本大活动")
    check("配色已补", p44["color"], "#defeef")


def test_body_cache_and_audit():
    """正文缓存的 TTL 语义 + 活动公告的「审一次」闸门。

    缓存是省请求用的，但它同时决定**已落盘的公告还读不读正文**——而一帖多活动只有读正文
    才发现得了（见 parse.parse_activity_bodies）。这里钉住四件事：TTL 到期就当没有、
    audited 记的是「尝试过」（抓失败也算，不然风控期间每轮重试同一批）、`waiting` 的口径
    （还有块解不出日期才再读，全落盘就跳过——见 _needs_body 的 audit 段），以及这些开关
    合成的那道闸门。`waiting` 怎么从块里算出来，由 test_activity_audit_waiting 拿真身钉。
    """
    import datetime as _dt
    import tempfile
    from pathlib import Path as _Path

    tmp = _Path(tempfile.mkdtemp(prefix="hsr-body-cache-"))
    saved = (body_cache.CACHE_DIR, body_cache.BODIES_DIR, body_cache.AUDITED_FILE)
    body_cache.CACHE_DIR, body_cache.BODIES_DIR = tmp, tmp / "bodies"
    body_cache.AUDITED_FILE = tmp / "audited.json"
    try:
        body_cache.put("76891951", text="正文", images=["u"])
        got = body_cache.get("76891951") or {}
        check("存进去能取出来", (got.get("text"), got.get("images")), ("正文", ["u"]))
        check("没存过的取不到", body_cache.get("1"), None)

        # 过期：直接改时间戳（TTL_DAYS 是 14，这里写成一年前）
        stale = _dt.date.today() - _dt.timedelta(days=365)
        body_cache.put("2", text="旧的")
        p = body_cache.BODIES_DIR / "2.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["fetched_at"] = stale.isoformat()
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        check("过期就当没有", body_cache.get("2"), None)

        check("没记过 = 没审过", body_cache.audit_state("76891951"), None)

        # 旧格式（只存一个日期字符串）当 waiting=True：多读一次自纠，不会把「还有块在等版本
        # 周期表」的那篇误判成已经啃干净
        body_cache.AUDITED_FILE.write_text(
            json.dumps({"777": stale.isoformat()}), encoding="utf-8")
        check("旧格式的记录过期了 → 当没审过", body_cache.audit_state("777"), None)
        body_cache.AUDITED_FILE.write_text(
            json.dumps({"777": _dt.date.today().isoformat()}), encoding="utf-8")
        check("旧格式（裸日期）→ 当 waiting=True",
              (body_cache.audit_state("777") or {}).get("waiting"), True)

        body_cache.mark_audited("76891951", waiting=False)
        state = body_cache.audit_state("76891951") or {}
        check("记过 = 审过（连 waiting 一起记）",
              (state.get("date"), state.get("waiting")),
              (_dt.date.today().isoformat(), False))

        # 闸门：已落盘的公告（公告 07-23 发出，活动 07-24 开始 → keys.likely_recorded 认它已录）
        rec = {"title": "「幻造：圣杯战争」", "type": "版本大活动",
               "start_date": "2026-07-24", "end_date": "2026-08-25"}
        cold = {"title": "「幻造：圣杯战争」", "post_id": "100",
                "created_at": int(_dt.datetime(2026, 7, 23, 12).timestamp())}
        body_cache.mark_audited("5", waiting=True)   # 审过，但还有块在等版本表（幻造那种）
        check("已落盘 + 没审过 → 抓一次（补被埋的活动）",
              pipeline._needs_body(dict(cold), [rec], audit=True), True)
        check("已落盘 + 审过且块都落盘 → 跳过（缓存里有正文也不读）",
              pipeline._needs_body({**cold, "post_id": "76891951"}, [rec], audit=True), False)
        check("已落盘 + 上次还有块在等 → 再读一次",
              pipeline._needs_body({**cold, "post_id": "5"}, [rec], audit=True), True)
        check("不带 audit 的调用点（大月卡等）走原来那道闸",
              pipeline._needs_body({**cold, "post_id": "76891951"}, [rec]), False)
        check("没落盘的照抓", pipeline._needs_body(
            {"title": "「新活动」", "post_id": "101"}, [rec], audit=True), True)
    finally:
        (body_cache.CACHE_DIR, body_cache.BODIES_DIR,
         body_cache.AUDITED_FILE) = saved


def test_activity_audit_waiting():
    """读完一篇公告后 `waiting` 按**块**算——它决定下一篇还读不读。

    「已落盘的活动公告就跳过」有个边界：幻造那篇主体早落盘了，可里面还埋着
    「命运契约•再启」，终点写的是 `4.6版本结束前`，而 4.6 只有起没有止（见 _version_table）。
    要是把这篇记成 waiting=False，它就再也不会被读，那条活动永远发现不了。所以这里用真身
    （幻造公告，一帖三活动）钉两头：4.6 的止还没进表 → waiting=True（下轮再读）；4.6 的止
    一进表 → 全部块落盘 → waiting=False（就此跳过）。
    """
    import tempfile
    from pathlib import Path as _Path

    d = load("act_huanzao")
    pid = d["post_id"]
    tmp = _Path(tempfile.mkdtemp(prefix="hsr-body-audit-"))
    saved = (body_cache.CACHE_DIR, body_cache.BODIES_DIR, body_cache.AUDITED_FILE)
    body_cache.CACHE_DIR, body_cache.BODIES_DIR = tmp, tmp / "bodies"
    body_cache.AUDITED_FILE = tmp / "audited.json"
    orig_find, orig_fetch = pipeline.parse.find_activities, pipeline._fetch_text
    pipeline.parse.find_activities = lambda posts: [
        {"title": "「幻造：圣杯战争」", "name": parse._name_of(d["subject"]),
         "post_id": pid, "created_at": 0}]
    pipeline._fetch_text = lambda post_id: (d["text"], ["u"])
    try:
        versions = _versions("hsr44_version_notes", "hsr45_version_notes")
        check("4.6 有起无止（只有一条版本更新条目提到它）",
              versions.get("4.6"), ("2026-09-28", None))
        got = pipeline._build_activities([], versions, [])
        check("一帖三活动逐块产出",
              [(e["title"], e["type"], e["start_date"], e["end_date"]) for e in got],
              [("「幻造：圣杯战争」", "常规活动", "2026-07-24", "2026-08-25"),
               ("「命运契约•再启」", "版本大活动", "2026-07-24", None),
               ("「命运赠礼」", "版本大活动", "2026-07-15", "2026-08-25")])
        check("有块的终点解不出来（等 4.6）→ waiting，下轮还要再看这篇",
              (body_cache.audit_state(pid) or {}).get("waiting"), True)

        v46 = {**versions, "4.6": ("2026-09-28", "2026-10-27")}
        got = pipeline._build_activities([], v46, [])
        check("4.6 的止一进表 → 「命运契约•再启」落盘（终点 = 4.6 的止）",
              (got[1]["start_date"], got[1]["end_date"]), ("2026-07-24", "2026-10-27"))
        check("块全落盘 → 不再 waiting，就此跳过",
              (body_cache.audit_state(pid) or {}).get("waiting"), False)
    finally:
        pipeline.parse.find_activities, pipeline._fetch_text = orig_find, orig_fetch
        (body_cache.CACHE_DIR, body_cache.BODIES_DIR,
         body_cache.AUDITED_FILE) = saved


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

    # 一帖多活动：幻造那篇挂了三块（主体 + 命运契约•再启 + 命运赠礼）
    d = load("act_huanzao")
    bodies = parse.parse_activity_bodies(d["text"], "幻造：圣杯战争")
    check("一帖多活动：块数与名字",
          [(b["name"], b.get("version_period"), b.get("version_end_before")) for b in bodies],
          [("幻造：圣杯战争", None, None),
           ("命运契约•再启", None, "4.6"),
           ("命运赠礼", "4.4", None)])
    check("一帖多活动：主体那块取自己的时段（不串到后两块的）",
          (bodies[0].get("start_date"), bodies[0].get("end_date")),
          ("2026-07-24", "2026-08-25"))
    check("一帖多活动：只解得出一个日期的块不给起止（起点照给、终点留空）",
          (bodies[1].get("start_date"), bodies[1].get("end_date")),
          ("2026-07-24", None))
    check("一帖多活动：既没有绝对日期也没有时刻的那种块不给日期",
          (bodies[2].get("start_date"), bodies[2].get("end_date")), (None, None))

    # 只解得出一个绝对日期的段不许落成「只有一天」的活动（parse_period 会把那一个日期
    # 同时当成起止）。判据与总纲的 _item_period 同一条。
    one = parse.parse_activity_body("▌活动时间 2026/09/01 04:00\n▌参与条件 无")
    check("单日期段不落成一天的活动", (one.get("start_date"), one.get("end_date")), (None, None))


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
    """日期齐全的每条都应命中数据文件里的已有条目，且日期一致。

    这是**标题规则**的回归闸门。标题是去重主键（keys.event_key），拼错一个字，
    下一轮 apply_events 就会把已落盘的条目当成新活动再插一遍——而且日期也是同一套
    日期口径推出来的，一并核对，等于把「标题 + 日期口径」两个假设都钉在真实数据上。

    日期不齐的候选**不要求**命中：管线有日期闸，起止缺一就丢弃，它本就不该出现在
    数据文件里（4.6 的「镇伏『贪饕』，汇聚愿力」就是这种，终点要等 4.6 的更新说明）。
    判据取自管线自己的闸门，不另设例外名单——名单会过期，过期了还留着就会把
    真正的标题规则回归盖住。
    """
    existing = yaml_io.load_events(rules.GAME)

    d44, d45 = load("hsr44_version_notes"), load("hsr45_version_notes")
    notes44 = {**parse.parse_version_notes(d44["text"], d44["subject"]),
               "post_id": d44["post_id"]}
    notes45 = {**parse.parse_version_notes(d45["text"], d45["subject"]),
               "post_id": d45["post_id"]}
    versions = _versions("hsr44_version_notes", "hsr45_version_notes")

    dyn = load("bili_livestream")
    preview = parse.parse_update_preview(load("hsr45_update_preview")["text"])

    candidates = (
        pipeline._build_endgame_events(notes44, versions) + pipeline._build_endgame_events(notes45, versions)
        + pipeline._build_version_events(notes45, preview, parse.find_launches(dyn))
        + pipeline._build_livestreams(parse.find_livestreams(dyn))
    )
    # 卡池、大月卡、活动：标题与日期都从正文夹具解析（日期另有 test_banners /
    # test_activity_bodies 单独断言）。日期一并带上，是为了让下面「日期齐就必须命中」
    # 这条判据能覆盖到它们。
    for name in ("hsr45_banner_1", "hsr45_banner_2", "hsr44_banner_2"):
        for b in parse.parse_banner_body(load(name)["text"]):
            candidates.append({"title": b["title"], "type": "卡池",
                               "start_date": b["start_date"], "end_date": b["end_date"]})
    bp = parse.parse_activity_body(load("hsr45_battle_pass")["text"])
    candidates.append({"title": rules.BATTLE_PASS_TITLE.format(ver="4.5"), "type": "大月卡",
                       "start_date": bp.get("start_date"), "end_date": bp.get("end_date")})
    for name, etype in (("act_chaoxian", "常规活动"), ("act_huacang", "常规活动"),
                        ("act_weimian", "常规活动"), ("act_zhenfu", "版本大活动")):
        act = parse.parse_activity_body(load(name)["text"])
        candidates.append({"title": f"「{parse._name_of(load(name)['subject'])}」",
                           "type": etype,
                           "start_date": act.get("start_date"),
                           "end_date": act.get("end_date")})
    # 总纲优先的候选（当前版本 4.5 那一份）：同样要命中已有条目、日期一致。
    # 4.4 那一份**有意不放进来**：里面那条联动活动总纲写作 `■命运/银河铁道之夜`，公告与
    # 数据文件里都叫 `「幻造：圣杯战争」`（同一活动、名字不同，见 PLAN.md §1.2）。按标题比
    # 对必然落空，塞进来就得为它写一张例外名单，而名单会过期、还会盖住真回归。
    # （原先不放它的理由是另一条：反贪『砖』家的结束日数据里偏了一天，2026-09-22 已订正。）
    candidates += pipeline._activities_from_notes(notes45, d45["text"], versions)

    for c in candidates:
        dup = keys.find_duplicate(c, existing)
        if dup is None:
            if c.get("start_date") and c.get("end_date"):
                check(f"应命中已有条目：{c['title']}", None, "数据文件里的一条")
            else:
                # 日期不齐 → 管线日期闸会丢掉，本就不该在数据文件里
                print(f"   · 日期不齐、暂不落盘：{c['title']}")
            continue
        for f in ("start_date", "end_date"):
            if c.get(f):
                check(f"日期一致 {c['title']} {f}", dup.get(f), c[f])


def main():
    for fn in (test_version_notes, test_version_table, test_notes_activities, test_notes_candidates,
               test_pending_correction, test_body_cache_and_audit,
               test_activity_audit_waiting, test_banners,
               test_activity_bodies,
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
