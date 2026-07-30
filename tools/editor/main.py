#!/usr/bin/env python3
"""米游活动日历 — 可视化活动编辑器（开发者工具）

交互式终端界面，用于编辑 data/events/ 下的 YAML 活动数据文件。

用法:
    python tools/editor/main.py
"""

import os
import sys
from datetime import datetime

import questionary
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from yaml_io import (
    load_events,
    save_events,
    list_games,
    generate_event_id,
    EVENT_TYPES,
    GAME_META,
)

console = Console()

# ─── 样式 ──────────────────────────────────────────────

def _style_choice(choices: list, default: str | None = None) -> str:
    """通用单选，使用 questionary"""
    sel = questionary.select(
        "",
        choices=choices,
        default=default,
        use_arrow_keys=True,
    ).ask()
    if sel is None:
        raise KeyboardInterrupt
    return sel

def _input(label: str, default: str = "") -> str:
    """通用文本输入"""
    val = questionary.text(f"{label}:", default=default).ask()
    if val is None:
        raise KeyboardInterrupt
    return val

def _confirm(label: str, default: bool = True) -> bool:
    """确认对话框"""
    return questionary.confirm(label, default=default).ask()


# ─── 辅助函数 ────────────────────────────────────────────

def _format_date_short(d: str) -> str:
    """将 YYYY-MM-DD 格式化为 MM/DD 简写"""
    try:
        parts = d.split("-")
        return f"{int(parts[1]):02d}/{int(parts[2]):02d}"
    except (ValueError, IndexError):
        return d

def _validate_date(text: str) -> bool | str:
    """校验日期格式 YYYY-MM-DD"""
    if not text:
        return True  # 允许空
    import re
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return "格式必须为 YYYY-MM-DD，如 2026-08-16"
    return True

def _validate_hex_color(text: str) -> bool | str:
    """校验 hex 颜色"""
    if not text:
        return True
    import re
    if not re.match(r"^#[0-9a-fA-F]{6}$", text):
        return "格式必须为 #RRGGBB，如 #DBEAFE"
    return True


# ─── 主流程 ──────────────────────────────────────────────

def main():
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]🎮 米游活动日历 — 数据编辑器[/bold cyan]\n"
        "[dim]开发者工具 — 直接读写 data/events/*.yaml[/dim]",
        border_style="cyan",
    ))

    while True:
        choice = questionary.select(
            "选择操作:",
            choices=[
                {"name": "📋 编辑活动数据", "value": "edit"},
                {"name": "🚪 退出", "value": "quit"},
            ],
        ).ask()

        if choice is None or choice == "quit":
            console.print("\n[dim]再见 👋[/dim]")
            break

        if choice == "edit":
            _select_game()


def _select_game():
    """Step 1: 选择游戏"""
    console.clear()
    games = list_games()

    choices = [
        {
            "name": f"{g['name']} ({g['id']}) — {g['count']} 条活动",
            "value": g["id"],
        }
        for g in games
    ]
    choices.insert(0, {"name": "↩ 返回", "value": None})

    game_id = _style_choice(choices)
    if game_id is None:
        return

    _event_list(game_id)


def _event_list(game_id: str):
    """Step 2: 显示活动列表，选择编辑或新建"""
    events = load_events(game_id)
    game_name = GAME_META[game_id]["name"]

    while True:
        console.clear()
        console.print(f"[bold]{game_name}[/bold] — 活动列表\n")

        # 表格展示
        table = Table(show_header=True, border_style="dim")
        table.add_column("#", width=3, style="dim")
        table.add_column("标题", width=40)
        table.add_column("类型", width=12)
        table.add_column("日期", width=20)
        table.add_column("ID", width=20, style="dim")

        for i, ev in enumerate(events):
            type_label = dict(EVENT_TYPES).get(ev.get("type", ""), ev.get("type", ""))
            date_range = f"{_format_date_short(ev.get('start_date', ''))} ~ {_format_date_short(ev.get('end_date', ''))}"
            table.add_row(
                str(i + 1),
                ev.get("title", "")[:35],
                type_label[:10],
                date_range,
                ev.get("id", "")[:18],
            )

        console.print(table)
        console.print()

        # 选项
        choice_items = [
            {"name": f"  {i+1}. {ev.get('title', '(无标题)')[:50]}", "value": i}
            for i, ev in enumerate(events)
        ]
        choice_items.append({"name": "  [bold]+ 新建活动[/bold]", "value": "new"})
        choice_items.append({"name": "↩ 返回游戏列表", "value": None})

        sel = _style_choice(choice_items, default=str(len(events)) if events else None)

        if sel is None:
            return
        elif sel == "new":
            event = _edit_event(None, game_id)
            if event is not None:
                events.append(event)
                save_events(game_id, events)
                console.print("[green]✓ 已添加[/green]")
                _press_enter()
        else:
            event = _edit_event(events[sel], game_id)
            if event is None:
                # 删除
                del events[sel]
                save_events(game_id, events)
                console.print("[yellow]✓ 已删除[/yellow]")
                _press_enter()
            else:
                events[sel] = event
                save_events(game_id, events)
                console.print("[green]✓ 已保存[/green]")
                _press_enter()


def _edit_event(event: dict | None, game_id: str) -> dict | None:
    """Step 3: 编辑单个活动

    返回:
        dict: 修改后的活动数据 → 保存
        None: 删除此活动
        KeyboardInterrupt / 取消: 不保存
    """
    is_new = event is None
    if is_new:
        event = {
            "id": "",
            "game": game_id,
            "title": "",
            "type": "version-main",
            "start_date": "",
            "end_date": "",
        }

    game_name = GAME_META[game_id]["name"]
    action_label = "新建" if is_new else "编辑"

    console.clear()
    console.print(f"[bold]{game_name}[/bold] — {action_label}活动\n")

    # ── 标题 ──
    title = _input("活动标题", event.get("title", ""))

    # ── 类型 ──
    type_labels = [f"{label} ({key})" for key, label in EVENT_TYPES]
    type_values = [key for key, _ in EVENT_TYPES]
    current_type = event.get("type", "version-main")
    default_idx = type_values.index(current_type) if current_type in type_values else 0
    type_sel = _style_choice(type_labels, default=type_labels[default_idx])
    event_type = type_values[type_labels.index(type_sel)]

    # ── 颜色 ──
    color = _input("色条颜色 (#RRGGBB, 可为空)", event.get("color", ""))

    # ── 日期 ──
    start_date = questionary.text(
        "开始日期 (YYYY-MM-DD):",
        default=event.get("start_date", ""),
        validate=_validate_date,
    ).ask()
    if start_date is None:
        raise KeyboardInterrupt

    end_date = questionary.text(
        "结束日期 (YYYY-MM-DD):",
        default=event.get("end_date", ""),
        validate=_validate_date,
    ).ask()
    if end_date is None:
        raise KeyboardInterrupt

    # ── 描述 ──
    desc = _input("描述 (可选)", event.get("description", ""))

    # ── 标签 ──
    tags = event.get("tags", [])[:]
    tags_str = ", ".join(tags)
    new_tags_str = _input("标签 (逗号分隔)", tags_str)
    tags = [t.strip() for t in new_tags_str.split(",") if t.strip()]

    # ── 阶段 ──
    phases = event.get("phases", [])[:] if event.get("phases") else []
    console.print(f"\n[dim]当前阶段: {len(phases)} 个[/dim]")
    edit_phases = _confirm("是否编辑阶段?", default=False)
    if edit_phases:
        phases = _edit_phases(phases)

    # ── 生成 ID ──
    if is_new or not event.get("id"):
        event_id = generate_event_id(game_id, title, start_date)
        console.print(f"\n[dim]自动生成 ID: {event_id}[/dim]")
        if not _confirm("使用此 ID?", default=True):
            event_id = _input("手动输入 ID", event_id)
    else:
        event_id = event.get("id", "")

    # ── 汇总确认 ──
    console.clear()
    console.print("[bold]确认活动数据:[/bold]\n")
    console.print(f"  ID:       {event_id}")
    console.print(f"  游戏:     {game_name}")
    console.print(f"  标题:     {title}")
    console.print(f"  类型:     {dict(EVENT_TYPES)[event_type]}")
    console.print(f"  颜色:     {color or '(使用游戏默认色)'}")
    console.print(f"  日期:     {start_date} ~ {end_date}")
    console.print(f"  描述:     {desc or '(无)'}")
    console.print(f"  标签:     {', '.join(tags) if tags else '(无)'}")
    console.print(f"  阶段:     {len(phases)} 个")

    action = questionary.select("", choices=[
        {"name": "💾 保存", "value": "save"},
        {"name": "🗑  删除此活动", "value": "delete"},
        {"name": "↩ 取消", "value": "cancel"},
    ]).ask()

    if action == "cancel":
        raise KeyboardInterrupt
    elif action == "delete":
        if _confirm("确认删除此活动? 此操作不可恢复。", default=False):
            return None
        raise KeyboardInterrupt

    # 构建最终数据
    result = {
        "id": event_id,
        "game": game_id,
        "title": title,
        "type": event_type,
        "start_date": start_date,
        "end_date": end_date,
    }
    if desc:
        result["description"] = desc
    if color:
        result["color"] = color
    if tags:
        result["tags"] = tags
    if phases:
        result["phases"] = phases

    return result


def _edit_phases(phases: list[dict]) -> list[dict]:
    """编辑活动子阶段"""
    new_phases = []
    for i, ph in enumerate(phases):
        console.print(f"\n[bold]阶段 {i+1}[/bold]")
        title = _input("  标题", ph.get("title", ""))
        start = questionary.text(
            "  开始日期:", default=ph.get("start_date", ""), validate=_validate_date
        ).ask()
        end = questionary.text(
            "  结束日期:", default=ph.get("end_date", ""), validate=_validate_date
        ).ask()
        if title and start:
            new_phases.append({"title": title, "start_date": start, "end_date": end})

    if _confirm("\n添加新阶段?", default=False):
        console.print("\n[bold]新增阶段[/bold]")
        title = _input("  标题", "")
        start = questionary.text("  开始日期:", default="", validate=_validate_date).ask()
        end = questionary.text("  结束日期:", default="", validate=_validate_date).ask()
        if title and start:
            new_phases.append({"title": title, "start_date": start, "end_date": end})

    return new_phases


def _press_enter():
    console.print("\n[dim]按 Enter 继续...[/dim]", end="")
    input()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]已取消[/dim]")
    except Exception as e:
        console.print(f"\n[red]错误: {e}[/red]")
        sys.exit(1)
