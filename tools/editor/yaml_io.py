"""YAML 数据文件读写模块。

直接操作 data/events/ 下的 YAML 文件，读写活动列表。
"""

import os
from pathlib import Path

import yaml


# 项目根目录（tools/editor/ 的上两级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "events"

# 游戏文件名映射
GAME_FILES = {
    "genshin-impact": "genshin-impact.yaml",
    "honkai-star-rail": "honkai-star-rail.yaml",
    "zenless-zone-zero": "zenless-zone-zero.yaml",
    "tears-of-themis": "tears-of-themis.yaml",
    "honkai-impact-3rd": "honkai-impact-3rd.yaml",
}

GAME_META = {
    "genshin-impact": {"name": "原神", "color": "#4A90D9"},
    "honkai-star-rail": {"name": "崩坏：星穹铁道", "color": "#7B5EA7"},
    "zenless-zone-zero": {"name": "绝区零", "color": "#00E5A0"},
    "tears-of-themis": {"name": "未定事件簿", "color": "#D4929A"},
    "honkai-impact-3rd": {"name": "崩坏3", "color": "#FF6B9D"},
}

EVENT_TYPES = [
    ("version-main", "版本主题活动"),
    ("banner", "卡池/祈愿"),
    ("daily", "签到/每日活动"),
    ("challenge", "挑战/高难活动"),
    ("web-event", "网页联动活动"),
    ("festival", "节日/周年庆典"),
    ("reward", "福利/兑换码"),
    ("update", "版本更新"),
]


def load_events(game_id: str) -> list[dict]:
    """加载某个游戏的全部活动数据"""
    filename = GAME_FILES.get(game_id)
    if not filename:
        raise ValueError(f"未知游戏: {game_id}")

    filepath = DATA_DIR / filename
    if not filepath.exists():
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"{filepath}: 期望 YAML 数组，实际为 {type(data).__name__}")

    return data


def save_events(game_id: str, events: list[dict]) -> str:
    """将活动列表写入 YAML 文件，返回文件路径"""
    filename = GAME_FILES.get(game_id)
    if not filename:
        raise ValueError(f"未知游戏: {game_id}")

    filepath = DATA_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(
            events,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=120,
        )

    return str(filepath)


def list_games() -> list[dict]:
    """列出所有已支持的游戏（包含元数据和活动数）"""
    games = []
    for game_id, filename in GAME_FILES.items():
        filepath = DATA_DIR / filename
        count = 0
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, list):
                count = len(data)

        meta = GAME_META.get(game_id, {"name": game_id, "color": "#999"})
        games.append({
            "id": game_id,
            "name": meta["name"],
            "color": meta["color"],
            "count": count,
        })

    return games


def generate_event_id(game_id: str, title: str, start_date: str) -> str:
    """根据游戏+标题+日期自动生成事件 ID"""
    game_prefix = {
        "genshin-impact": "gi",
        "honkai-star-rail": "hsr",
        "zenless-zone-zero": "zzz",
    }.get(game_id, game_id[:3])

    # 从标题中取前几个有意义的中文字符
    import re
    clean = re.sub(r"[「」『』""'']", "", title)
    words = re.findall(r"[一-鿿]+", clean)
    slug = "-".join(words[:3]) if words else "event"
    # 截短防止 ID 过长
    if len(slug) > 30:
        slug = slug[:30]

    return f"{game_prefix}-{slug}"
