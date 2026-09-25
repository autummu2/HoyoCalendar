"""新增落盘：把管线产出的 JSON 里的新活动写入 data/events/<game_id>.yaml。

本模块**只新增，不改动已有条目**——已有条目的值修正由 calibrate.py 负责。
「是否已存在」按 keys.find_duplicate 判定（主键 + 日期兜底，口径按端点，见 keys.EXACT_FALLBACK_GAMES）。
活动类的主键是 (标题, 开始日期)，**类型不在主键里**——所以「先按默认类型落盘、等公告
到了再订正类型」不会插重复（类型变了主键不变）。把类型改对是 calibrate.correct_from_candidates
的事（在管线里跑，本模块不参与）。

- 新增：find_duplicate 找不到同身份条目。
- 跳过：找到了（日期可能已被人工订正过，靠日期兜底 / 同源帖仍认得出）。

两条管线共用：由调用方传入各自的产物路径（原神 genshin/extracted_full.json、
星铁 starrail/extracted_hsr.json）。

id 遵循 gui._auto_id 约定：{游戏前缀}-{类型前2字}-{YYYY-MM}-{标题去符号取前8字}。
"""
import json
import re
import io

from common import keys
from common import yaml_io

GAME = "genshin-impact"


def auto_id(title: str, start_date: str, type_label: str, game_id: str = GAME) -> str:
    type_short = type_label[:2]
    clean = re.sub(r"[「」『』\"\"'']", "", title)
    words = "".join(re.findall(r"[一-鿿\d]", clean))
    title_part = words[:8] if words else "event"
    date_part = start_date[:7] if start_date else ""
    prefix = yaml_io.GAME_ID_PREFIX.get(game_id, game_id[:3])
    return f"{prefix}-{type_short}-{date_part}-{title_part}"


def main(game_id: str = GAME, filename=None):
    """filename: 该游戏管线的产物 JSON 路径（见 maintain.py）。省略时退回 cwd 下的
    extracted_full.json，仅供直接运行本模块时使用。"""
    extracted = json.load(io.open(filename or "extracted_full.json", encoding="utf-8"))
    events = yaml_io.load_events(game_id)
    used_ids = {e.get("id") for e in events}

    added, skipped, invalid = [], [], []

    for ex in extracted:
        # 防御：无日期的条目写进日历没有意义，直接跳过（genshin/pipeline.py 输出前已过滤一层）
        if not (ex.get("title") and ex.get("start_date") and ex.get("end_date")):
            invalid.append(f"{ex.get('title') or '(无标题)'} {ex.get('start_date') or '?'}~{ex.get('end_date') or '?'}")
            continue
        title, start = ex["title"], ex["start_date"]
        if keys.find_duplicate(ex, events, game_id) is not None:
            skipped.append(title)
            continue
        ev_id = auto_id(title, start, ex["type"], game_id)
        # id 必须唯一（前端用作 React key 与「已完成」追踪键），撞了就加序号
        if ev_id in used_ids:
            n = 2
            while f"{ev_id}-{n}" in used_ids:
                n += 1
            ev_id = f"{ev_id}-{n}"
        used_ids.add(ev_id)
        ev = {
            "id": ev_id,
            "game": game_id,
            "title": title,
            "type": ex["type"],
            "start_date": start,
            "end_date": ex["end_date"],
            "color": ex.get("color", "#cce0f0"),
        }
        if ex.get("description"):
            ev["description"] = ex["description"]
        url_path = yaml_io.GAME_URL_PATH.get(game_id)
        if ex.get("post_id") and url_path:
            ev["source_url"] = f"https://www.miyoushe.com/{url_path}/article/{ex['post_id']}"
        if ex.get("tags"):
            ev["tags"] = ex["tags"]
        if ex.get(keys.PENDING_FIELD):
            # 「这条是从总纲落盘的、还缺公告才有的字段」，要写进数据文件——下一轮
            # 靠它决定必抓正文（keys.likely_recorded）与补全（calibrate.correct_from_candidates）
            ev[keys.PENDING_FIELD] = ex[keys.PENDING_FIELD]
        events.append(ev)
        added.append(f"{title} {start}~{ex['end_date']} [{ex.get('color')}]")

    print("== 新增 ==")
    for a in added:
        print(" +", a)
    print("== 跳过 ==")
    for s in skipped:
        print(" .", s)
    if invalid:
        print("== 跳过（日期不完整）==")
        for s in invalid:
            print(" x", s)

    yaml_io.save_events(game_id, events)
    print(f"\n共 {len(added)} 新增 / {len(skipped)} 跳过"
          f"{f' / {len(invalid)} 日期不完整' if invalid else ''} → 已写入")


if __name__ == "__main__":
    main()
