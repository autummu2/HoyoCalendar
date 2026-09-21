"""绝区零的日期推理 — 只有高难期次需要推。

总纲的 ▶危局强袭战 / ▶式舆防卫战 两段**只列敌人、不给日期**，但给出期数
（第一期/第二期/第三期）。网格从真实期次反推：

  更新日之后（含当日）的第一个周五 = 首期「危局强袭战」
  「式舆防卫战」= 危局 + 7 天（两档每周交替）
  同类下一期 = + 14 天；每期 14 天（终点 = 下期起点 − 1）

拿 16 条手工录入的期次核对，15 条逐字命中（表见 PLAN.md §2.6）：

  3.1  危局 07-31 / 08-14 / 08-28    式舆 08-07 / 08-21 / 09-04
  3.2  危局 09-11 / 09-25 / 10-09    式舆 09-18 / 10-02 / 10-16

唯一的例外是数据里的「危局强袭战0729」（更新当天，周三，比网格早 2 天）。不需要
例外名单：网格只按**当前版本**的总纲推，3.1 早已不是当前版本，所以那一条永远不会
被重新推出来，也就不会撞车。
"""

from __future__ import annotations

import datetime

from zenless import rules

# 周五（date.weekday()：周一 = 0）
FRIDAY = 4
PERIOD_DAYS = 14


def first_friday_on_or_after(day: datetime.date) -> datetime.date:
    """更新日之后（含当日）的第一个周五。3.1 是周三 → 07-31，3.2 是周三 → 09-11。"""
    return day + datetime.timedelta(days=(FRIDAY - day.weekday()) % 7)


def endgame_periods(update_date: str, counts: dict) -> list[dict]:
    """按网格推出当前版本的高难期次 → [{mode, start_date, end_date}]。

    counts：{型名: 期数}，期数从总纲正文数出来（见 parse.parse_version_notes），
    不写死 3——某一版少一期时网格会跟着变。
    """
    first = first_friday_on_or_after(datetime.date.fromisoformat(update_date))
    out: list[dict] = []
    for i, mode in enumerate(rules.ENDGAME_MODES):
        for k in range(counts.get(mode, 0)):
            start = first + datetime.timedelta(days=7 * i + PERIOD_DAYS * k)
            out.append({"mode": mode,
                        "start_date": start.isoformat(),
                        "end_date": (start + datetime.timedelta(
                            days=PERIOD_DAYS - 1)).isoformat()})
    return out
