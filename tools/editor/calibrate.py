"""活动日期校准（修正维护）。

用外部权威来源核对**已有**条目的日期：一致 → 打标记；不一致 → 改成权威值再打标记。
本模块不新增条目（新增由 apply_events 负责），不改 id（前端用 id 追踪「已完成」标记）。

| 类型 | 校准依据 | 权威来源名 |
| 卡池 | B站总览公告 / 特殊祈愿动态的「〓祈愿时间〓」 | B站总览 / B站祈愿时间 |
| 版本大活动 | B站活动动态的「〓活动时间〓」 | B站活动动态 |
| 前瞻直播 | B站前瞻公告（版本名 + 确认日期） | B站前瞻公告 |
| 版本更新 | 米游社维护预告（日期 + 版本号 + 版本名） | 米游社维护预告 |

常规活动、大月卡、幽境危战、深境螺旋/幻想真境剧诗**不校准**——前两者没有可靠的
B站日期来源（B站活动动态只覆盖多阶段的版本大活动），后者无公告、本就走推理。

标记字段 `calibrated`（值为上表的来源名）：
- 有标记 = 已确认，不再重复处理（一次性）。
- 本轮找不到依据就不打标记，下次运行再试——避免「假确认」。
- EventSchema 不是 .strict()，前端 Zod 会静默丢弃该字段，界面无感。

只处理 start_date 在最近 WINDOW_DAYS 天内的未标记条目：更久远的即便有错也已无意义，
且来源动态早被 B站列表翻页刷掉，永远等不到依据（会一直白跑）。

纯函数，不读写数据文件，便于测试与后续接入编辑器或定时任务。
"""

from __future__ import annotations

import datetime

import keys

MARKER = "calibrated"
WINDOW_DAYS = 30
TAG_PENDING_VERSION = "待确认版本"

# 纳入校准的类型（见模块说明）
CALIBRATED_TYPES = {"卡池", "版本大活动", "前瞻直播", "版本更新"}

# 值字段：只覆盖这些，其余字段（id/color/description/tags/post_id…）一律不动
VALUE_FIELDS = ("title", "start_date", "end_date")


def _date(value) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def sources_from(livestreams: list[dict], maintenance: dict | None) -> dict:
    """构造「版本更新 / 前瞻直播」的权威值索引。

    livestreams：bilibili.find_livestreams 输出（{version, name, date?, id}）
    maintenance：维护预告解析结果 {version, date, name?}，可缺

    版本更新：日期以米游社维护预告为准（更新前 2 天发布，最权威），故覆盖 B站前瞻来源；
              无维护预告时退回 B站前瞻，只补版本名、不动日期（推理值已够准）。
    前瞻直播：B站前瞻公告给出确认日期与版本名。
    """
    src: dict = {}

    for ls in livestreams:
        v, name = ls.get("version"), ls.get("name")
        if not v or not name:
            continue
        live = {"title": f"《原神》{v} 版本「{name}」前瞻特别节目",
                "source": "B站前瞻公告"}
        if ls.get("date"):
            live["start_date"] = ls["date"]
            live["end_date"] = ls["date"]
        src[("前瞻直播", "v", v)] = live
        src.setdefault(("版本更新", "v", v),
                       {"title": f"《原神》{v} 版本「{name}」停服更新",
                        "source": "B站前瞻公告"})

    v = (maintenance or {}).get("version")
    if v:
        entry = {"source": "米游社维护预告"}
        if maintenance.get("date"):
            entry["start_date"] = maintenance["date"]
            entry["end_date"] = maintenance["date"]
        if maintenance.get("name"):
            entry["title"] = f"《原神》{v} 版本「{maintenance['name']}」停服更新"
        src[("版本更新", "v", v)] = entry

    return src


def calibrate(events: list[dict], sources: dict, today: datetime.date | None = None
              ) -> tuple[list[dict], list[str]]:
    """用权威来源校准已有条目，返回 (校准后的事件列表, 变更描述)。

    sources：{event_key: {值字段…, "source": 依据名}}，由 run_pipeline 汇总各来源后传入。
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
        tags = [t for t in (new.get("tags") or []) if t != TAG_PENDING_VERSION]
        if tags:
            new["tags"] = tags
        else:
            new.pop("tags", None)
        new[MARKER] = src["source"]
        changes.append(f"{new.get('title')} ← {src['source']}"
                       + (f"（{'；'.join(diffs)}）" if diffs else "（一致）"))
        out.append(new)

    return out, changes


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
