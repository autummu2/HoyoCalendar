"""活动日期校准（修正维护）。

用外部权威来源核对**已有**条目的日期：一致 → 打标记；不一致 → 改成权威值再打标记。
本模块不新增条目（新增由 apply_events 负责），不改 id（前端用 id 追踪「已完成」标记）。

| 类型 | 校准依据 | 权威来源名 |
| 卡池 | B站总览公告 / 特殊祈愿动态的「〓祈愿时间〓」 | B站总览 / B站祈愿时间 |
| 版本大活动 | B站活动动态的「〓活动时间〓」 | B站活动动态 |
| 前瞻直播 | B站前瞻公告（版本名 + 确认日期） | B站前瞻公告 |
| 版本更新 | 米游社维护预告（日期 + 版本号 + 版本名） | 米游社维护预告 |
| 高难挑战（星铁） | 米游社版本更新说明的「■玩法」段 | 米游社版本更新说明 |

常规活动、大月卡、幽境危战、深境螺旋/幻想真境剧诗**不校准**——前两者没有可靠的
B站日期来源（B站活动动态只覆盖多阶段的版本大活动），后者无公告、本就走推理。

另一个入口是 `correct_from_candidates()`：用本轮候选订正已有条目的**类型**，并补全
「先从总纲落盘、还缺公告才有的字段」的活动（绝区零的总纲优先，见 `zenless/PLAN.md` §1.2）。
它同样只改值、不新增、不碰 id 与日期，但匹配方式不一样——按**标题**认而不是按主键，
因为要订正的恰恰包含类型本身，而类型在候选侧可能已经和条目不同。所以它做成独立函数，
不塞进 VALUE_FIELDS。

标记字段 `calibrated`（值为上表的来源名）：
- 有标记 = 已确认，不再重复处理（一次性）。
- 本轮找不到依据就不打标记，下次运行再试——避免「假确认」。
- 顺带摘掉 `keys.PENDING_TAGS` 里的「待确认」标签：确认到了，标签就该消失。
- EventSchema 不是 .strict()，前端 Zod 会静默丢弃该字段，界面无感。

只处理 start_date 在最近 WINDOW_DAYS 天内的未标记条目：更久远的即便有错也已无意义，
且来源动态早被 B站列表翻页刷掉，永远等不到依据（会一直白跑）。

纯函数，不读写数据文件，便于测试与后续接入编辑器或定时任务。
"""

from __future__ import annotations

import datetime

from common import keys

MARKER = "calibrated"
WINDOW_DAYS = 30

# 纳入校准的类型（见模块说明）。
# 高难挑战是给星铁加的：星铁的高难期名与日期都写在版本更新说明里（权威来源），
# 而它恰恰是最容易错的一类（期名/日期都得从正文里抄）。对原神是空转——
# 原神的高难（深境螺旋/幻想真境剧诗）无公告，sources 里没有该类型的键。
CALIBRATED_TYPES = {"卡池", "版本大活动", "前瞻直播", "版本更新", "高难挑战"}

# 值字段：只覆盖这些，其余字段（id/color/description/tags/post_id…）一律不动
VALUE_FIELDS = ("title", "start_date", "end_date")

# 默认（兜底）活动类型。三条管线在**没有肯定信号**时都落回它：原神没有 B站多阶段动态、
# 星铁正文没有「X.Y版本期间」、绝区零正文没有任何类型段标记。所以它只代表「没信号」，
# 不能拿来当判据（见 correct_from_candidates 的护栏）。
DEFAULT_ACTIVITY_TYPE = "常规活动"


def _date(value) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def sources_from(livestreams: list[dict], maintenance: dict | None,
                 game_name: str = "原神") -> dict:
    """构造「版本更新 / 前瞻直播」的权威值索引。

    livestreams：bilibili.find_livestreams 输出（{version, name, date?, id}）
    maintenance：维护预告解析结果 {version, date, name?}，可缺
    game_name：标题里的游戏名。title 是 VALUE_FIELDS 之一，会被写回条目，
               所以这里拼出的标题必须与数据文件里的**逐字一致**。

    版本更新：日期以米游社维护预告为准（更新前 2 天发布，最权威），故覆盖 B站前瞻来源；
              无维护预告时退回 B站前瞻，只补版本名、不动日期（推理值已够准）。
    前瞻直播：B站前瞻公告给出确认日期与版本名。
    """
    src: dict = {}

    for ls in livestreams:
        v, name = ls.get("version"), ls.get("name")
        if not v or not name:
            continue
        live = {"title": f"《{game_name}》{v} 版本「{name}」前瞻特别节目",
                "source": "B站前瞻公告"}
        if ls.get("date"):
            live["start_date"] = ls["date"]
            live["end_date"] = ls["date"]
        src[("前瞻直播", "v", v)] = live
        src.setdefault(("版本更新", "v", v),
                       {"title": f"《{game_name}》{v} 版本「{name}」停服更新",
                        "source": "B站前瞻公告"})

    v = (maintenance or {}).get("version")
    if v:
        entry = {"source": "米游社维护预告"}
        if maintenance.get("date"):
            entry["start_date"] = maintenance["date"]
            entry["end_date"] = maintenance["date"]
        if maintenance.get("name"):
            entry["title"] = f"《{game_name}》{v} 版本「{maintenance['name']}」停服更新"
        src[("版本更新", "v", v)] = entry

    return src


def calibrate(events: list[dict], sources: dict, today: datetime.date | None = None
              ) -> tuple[list[dict], list[str]]:
    """用权威来源校准已有条目，返回 (校准后的事件列表, 变更描述)。

    sources：{event_key: {值字段…, "source": 依据名}}，由各管线汇总各来源后传入。
    today：只处理 start_date >= today − WINDOW_DAYS 的未标记条目。
    """
    today = today or datetime.date.today()
    floor = today - datetime.timedelta(days=WINDOW_DAYS)

    out: list[dict] = []
    changes: list[str] = []

    for ev in events:
        new = dict(ev)
        if MARKER in new or new.get("type") not in CALIBRATED_TYPES:
            out.append(new)
            continue
        start = _date(new.get("start_date"))
        if start is None or start < floor:
            out.append(new)
            continue
        src = sources.get(keys.event_key(new))
        if not src:
            out.append(new)
            continue

        diffs = []
        for field in VALUE_FIELDS:
            want = src.get(field)
            if want and new.get(field) != want:
                diffs.append(f"{field} {new.get(field)} → {want}")
                new[field] = want
        # 确认了就把「待确认」摘掉（见 keys.PENDING_TAGS）。放在这里而不是产出侧：标签的
        # 含义是「等确认」，只有拿到权威来源的这一刻才算确认；产出侧摘掉等于没标过。
        tags = [t for t in (new.get("tags") or []) if t not in keys.PENDING_TAGS]
        if tags:
            new["tags"] = tags
        else:
            new.pop("tags", None)
        new[MARKER] = src["source"]
        changes.append(f"{new.get('title')} ← {src['source']}"
                       + (f"（{'；'.join(diffs)}）" if diffs else "（一致）"))
        out.append(new)

    return out, changes


def correct_from_candidates(events: list[dict], candidates: list[dict]) -> list[str]:
    """用本轮候选订正已有条目，返回变更描述。只改值，不新增、不碰 id 与日期。

    两件事，都只能靠「本轮候选」判：

    1. **订正类型**。候选判出的类型与条目不同、且候选类型**有依据**时写回。
       为什么需要：绝区零的活动先从**总纲**落盘（总纲逐个列出活动名与活动时间，一个都不漏），
       但总纲给不出类型，只能先落默认类型；等它自己的活动说明公告发出来才知道是
       常规活动 / 登录福利 / 网页活动 / 版本大活动。原神也有同一件事——类型来自 B站动态，
       动态出现得比活动公告晚，条目会先落成常规活动。

    2. **补全待补全的条目**（带 `keys.PENDING_FIELD` 标记的，即从总纲落盘的那批）：
       补 `description` 与 `color`（总纲只有一两行简介、且活动段没有配图，这两样只有
       公告才有），然后清掉标记。标记是幂等的开关：清掉后不再重复处理。

       ⚠️ 候选的 `color` 是**管线取色那一步**才填上的，所以调用方必须**先取色再调本函数**
       （取色要排在日期闸之后，免得给马上要丢掉的条目白下载封面图）。顺序错了不会报错，
       只会静默少补一个配色——总纲落盘的那条会一直停在兜底色。

       清标记的前提是**候选本身不缺东西**——带标记的候选（总纲列出的那批，`pending` 值
       就是它落的）一律跳过：总纲那条只有名字与日期，拿它补全只会白清标记、补不上字段，
       而标记一清，下一轮预筛（keys.likely_recorded）就按「已录入」跳过它的公告正文，
       描述与配图再也补不上了。缺口宁可留着（继续重抓正文），不能假补。

    **不动 start_date / end_date / id**：
    - 日期：总纲与公告实测逐条一致（15/15），冲突时以先落盘的总纲为准。日期还在身份主键里，
      改写它的代价更大——主键失配，只能靠 find_duplicate 的同名 7 天兜底认回。
    - id：前端用它追踪「已完成」标记，改了会丢用户的标记（既有规则）。

    **护栏**：候选类型是 DEFAULT_ACTIVITY_TYPE 时**不写回 type**。它代表「没有肯定信号」
    而非判据——三条管线在没有信号时都落回它（原神没有 B站多阶段动态、星铁正文没有
    「X.Y版本期间」、绝区零正文没有类型段标记）。写回它有两个坏结果：把已确认的版本大活动
    降级（原神的 B站列表会被翻页刷掉，刷掉后候选就退回常规活动）；把人工标的
    `登录福利` 抹成常规活动（原神的登录福利条目是手工标的，管线判不出它）。
    """
    changes: list[str] = []
    for c in candidates:
        if c.get(keys.PENDING_FIELD):
            # 「自己还缺东西的候选」不是能补全的那一条（见上面第 2 点）。
            # 总纲列出的活动每轮都会再产出一条这样的候选，它匹配得上待补全的既有条目，
            # 但补不了描述与配图——放它过去就会假补。
            continue
        e = keys.find_duplicate(c, events)
        if e is None:
            continue
        diffs = []
        if c.get("type") and c["type"] != DEFAULT_ACTIVITY_TYPE and c["type"] != e.get("type"):
            diffs.append(f"type {e.get('type')} → {c['type']}")
            e["type"] = c["type"]
        if e.get(keys.PENDING_FIELD):
            for field in ("description", "color"):
                want = c.get(field)
                if want and e.get(field) != want:
                    e[field] = want
            e.pop(keys.PENDING_FIELD, None)
            if not diffs:
                diffs.append("补齐描述与配色")
        if diffs:
            changes.append(f"{e.get('title')} ← 公告（{'；'.join(diffs)}）")
    return changes


if __name__ == "__main__":
    # 演示：一条日期被改错的卡池 + 一条已标记的条目
    evs = [
        {"id": "a", "type": "卡池", "title": "「孤灯夜访」祈愿：「诡灯陌影·菲林斯(雷)」概率UP",
         "start_date": "2026-09-01", "end_date": "2026-09-20"},
        {"id": "b", "type": "常规活动", "title": "「盛材移涌」",
         "start_date": "2026-09-01", "end_date": "2026-09-10", MARKER: "B站总览"},
    ]
    src = {("卡池", "「孤灯夜访」祈愿：「诡灯陌影·菲林斯(雷)」概率UP"):
           {"start_date": "2026-09-02", "end_date": "2026-09-22", "source": "B站总览"}}
    filled, ch = calibrate(evs, src, today=datetime.date(2026, 9, 21))
    for c in ch:
        print(c)
    for e in filled:
        print(e.get("title"), e.get("start_date"), e.get("end_date"), e.get(MARKER))
