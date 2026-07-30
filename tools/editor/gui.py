#!/usr/bin/env python3
"""米游活动日历 — 可视化活动编辑器 (tkinter GUI)

用法:
    python tools/editor/gui.py
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox

from yaml_io import load_events, save_events, list_games, EVENT_TYPES

FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_SMALL = ("Microsoft YaHei UI", 9)

PAD = {"padx": 4, "pady": 2}


class EventEditor:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("米游活动日历 — 数据编辑器")
        self.root.geometry("1100x650")

        self.games = list_games()
        self.current_game: str | None = None
        self.events: list[dict] = []
        self.selected_index: int | None = None

        self._build_ui()
        self._refresh_game_list()

    # ─── UI 构建 ──────────────────────────────────────

    def _build_ui(self):
        # 顶栏
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, **PAD)

        ttk.Label(top, text="🎮 米游活动日历 — 数据编辑器", font=FONT_BOLD).pack(side=tk.LEFT, padx=8)
        ttk.Label(top, text="开发者工具 — 直接读写 data/events/*.yaml", foreground="gray").pack(side=tk.LEFT, padx=8)

        # 分隔线
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # 主体三栏
        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, **PAD)

        # 左栏：游戏列表
        left = ttk.LabelFrame(body, text="游戏", padding=4)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 4))

        self.game_listbox = tk.Listbox(left, width=22, font=FONT, exportselection=False)
        self.game_listbox.pack(fill=tk.BOTH, expand=True)
        self.game_listbox.bind("<<ListboxSelect>>", self._on_game_select)

        # 中栏：活动列表
        center = ttk.LabelFrame(body, text="活动列表", padding=4)
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)

        self.event_tree = ttk.Treeview(
            center,
            columns=("title", "type", "date", "id"),
            show="headings",
            selectmode="browse",
        )
        self.event_tree.heading("title", text="标题")
        self.event_tree.heading("type", text="类型")
        self.event_tree.heading("date", text="日期")
        self.event_tree.heading("id", text="ID")
        self.event_tree.column("title", width=200)
        self.event_tree.column("type", width=80)
        self.event_tree.column("date", width=130)
        self.event_tree.column("id", width=120)
        self.event_tree.pack(fill=tk.BOTH, expand=True)
        self.event_tree.bind("<<TreeviewSelect>>", self._on_event_select)

        btn_frame = ttk.Frame(center)
        btn_frame.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_frame, text="+ 新建活动", command=self._new_event).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑 删除选中", command=self._delete_event).pack(side=tk.LEFT, padx=2)

        # 右栏：编辑表单
        right = ttk.LabelFrame(body, text="编辑活动", padding=8)
        right.pack(side=tk.LEFT, fill=tk.BOTH, padx=(4, 0))
        self.form_frame = right

        row = 0
        ttk.Label(right, text="标题", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.W, **PAD)
        self.entry_title = ttk.Entry(right, width=35, font=FONT)
        self.entry_title.grid(row=row, column=1, sticky=tk.EW, **PAD)
        row += 1

        ttk.Label(right, text="类型", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.W, **PAD)
        self.combo_type = ttk.Combobox(
            right,
            values=[label for _, label in EVENT_TYPES],
            state="readonly",
            width=32,
            font=FONT,
        )
        self.combo_type.grid(row=row, column=1, sticky=tk.EW, **PAD)
        self.combo_type.set(EVENT_TYPES[0][1])
        row += 1

        ttk.Label(right, text="色条颜色", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.W, **PAD)
        color_row = ttk.Frame(right)
        color_row.grid(row=row, column=1, sticky=tk.EW, **PAD)
        self.entry_color = ttk.Entry(color_row, width=10, font=FONT)
        self.entry_color.pack(side=tk.LEFT)
        self.color_preview = tk.Label(color_row, text="   ", font=FONT, relief=tk.SUNKEN, width=4)
        self.color_preview.pack(side=tk.LEFT, padx=4)
        self.entry_color.bind("<KeyRelease>", lambda e: self._update_color_preview())
        row += 1

        ttk.Label(right, text="开始日期", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.W, **PAD)
        self.entry_start = ttk.Entry(right, width=15, font=FONT)
        self.entry_start.grid(row=row, column=1, sticky=tk.W, **PAD)
        ttk.Label(right, text="格式: YYYY-MM-DD", foreground="gray", font=FONT_SMALL).grid(
            row=row, column=2, sticky=tk.W, **PAD
        )
        row += 1

        ttk.Label(right, text="结束日期", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.W, **PAD)
        self.entry_end = ttk.Entry(right, width=15, font=FONT)
        self.entry_end.grid(row=row, column=1, sticky=tk.W, **PAD)
        row += 1

        ttk.Label(right, text="描述", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.NW, **PAD)
        self.text_desc = tk.Text(right, width=35, height=3, font=FONT, wrap=tk.WORD)
        self.text_desc.grid(row=row, column=1, columnspan=2, sticky=tk.EW, **PAD)
        row += 1

        ttk.Label(right, text="标签 (逗号分隔)", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.W, **PAD)
        self.entry_tags = ttk.Entry(right, width=35, font=FONT)
        self.entry_tags.grid(row=row, column=1, columnspan=2, sticky=tk.EW, **PAD)
        row += 1

        right.columnconfigure(1, weight=1)

        # 按钮
        btn_row = ttk.Frame(right)
        btn_row.grid(row=row, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(btn_row, text="💾 保存", command=self._save_event).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="↩ 撤销修改", command=self._revert_form).pack(side=tk.LEFT, padx=4)

        # 状态栏
        self.status = ttk.Label(self.root, text="就绪", foreground="gray", font=FONT_SMALL)
        self.status.pack(side=tk.BOTTOM, fill=tk.X, **PAD)

    # ─── 游戏列表 ──────────────────────────────────────

    def _refresh_game_list(self):
        self.games = list_games()
        self.game_listbox.delete(0, tk.END)
        for g in self.games:
            self.game_listbox.insert(tk.END, f"  {g['name']} ({g['count']})")

    def _on_game_select(self, event):
        sel = self.game_listbox.curselection()
        if not sel:
            return
        self.current_game = self.games[sel[0]]["id"]
        self.events = load_events(self.current_game)
        self._refresh_event_list()
        self._clear_form()

    # ─── 活动列表 ──────────────────────────────────────

    def _refresh_event_list(self):
        type_map = dict(EVENT_TYPES)
        self.event_tree.delete(*self.event_tree.get_children())
        for i, ev in enumerate(self.events):
            self.event_tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(
                    ev.get("title", ""),
                    type_map.get(ev.get("type", ""), ""),
                    f"{ev.get('start_date','')} ~ {ev.get('end_date','')}",
                    ev.get("id", ""),
                ),
            )

    def _on_event_select(self, event):
        sel = self.event_tree.selection()
        if not sel:
            return
        self.selected_index = int(sel[0])
        self._load_form(self.events[self.selected_index])

    def _new_event(self):
        if not self.current_game:
            messagebox.showwarning("提示", "请先选择游戏")
            return
        self.events.append(
            {"id": "", "game": self.current_game, "title": "", "type": "version-main", "start_date": "", "end_date": ""}
        )
        self.selected_index = len(self.events) - 1
        self._refresh_event_list()
        self.event_tree.selection_set(str(self.selected_index))
        self.event_tree.see(str(self.selected_index))
        self._load_form(self.events[self.selected_index])
        self.status.config(text=f"新建活动 — {self.current_game}")

    def _delete_event(self):
        if self.selected_index is None or not self.current_game:
            return
        ev = self.events[self.selected_index]
        ok = messagebox.askyesno("确认删除", f"删除活动「{ev.get('title', '(无标题)')}」?\n此操作不可恢复。")
        if not ok:
            return
        del self.events[self.selected_index]
        save_events(self.current_game, self.events)
        self.selected_index = None
        self._refresh_event_list()
        self._refresh_game_list()
        self._clear_form()
        self.status.config(text="已删除")

    # ─── 表单 ──────────────────────────────────────────

    def _load_form(self, ev: dict):
        type_map_rev = {label: key for key, label in EVENT_TYPES}
        self.entry_title.delete(0, tk.END)
        self.entry_title.insert(0, ev.get("title", ""))
        type_label = type_map_rev.get(ev.get("type", "version-main"), "版本主题活动")
        self.combo_type.set(type_label)
        self.entry_color.delete(0, tk.END)
        self.entry_color.insert(0, ev.get("color", ""))
        self.entry_start.delete(0, tk.END)
        self.entry_start.insert(0, ev.get("start_date", ""))
        self.entry_end.delete(0, tk.END)
        self.entry_end.insert(0, ev.get("end_date", ""))
        self.text_desc.delete("1.0", tk.END)
        self.text_desc.insert("1.0", ev.get("description", ""))
        tags = ", ".join(ev.get("tags", []))
        self.entry_tags.delete(0, tk.END)
        self.entry_tags.insert(0, tags)
        self._update_color_preview()

    def _clear_form(self):
        self.selected_index = None
        for w in [self.entry_title, self.entry_color, self.entry_start, self.entry_end, self.entry_tags]:
            w.delete(0, tk.END)
        self.combo_type.set(EVENT_TYPES[0][1])
        self.text_desc.delete("1.0", tk.END)
        self.color_preview.config(bg=self.root.cget("bg"))

    def _revert_form(self):
        if self.selected_index is not None and self.selected_index < len(self.events):
            self._load_form(self.events[self.selected_index])

    def _update_color_preview(self):
        c = self.entry_color.get().strip()
        if c.startswith("#") and len(c) == 7:
            try:
                self.color_preview.config(bg=c)
                return
            except tk.TclError:
                pass
        self.color_preview.config(bg=self.root.cget("bg"))

    # ─── 保存 ──────────────────────────────────────────

    def _save_event(self):
        if self.selected_index is None or not self.current_game:
            return

        # 校验
        title = self.entry_title.get().strip()
        if not title:
            messagebox.showwarning("提示", "标题不能为空")
            return

        start = self.entry_start.get().strip()
        end = self.entry_end.get().strip()
        import re

        if not re.match(r"^\d{4}-\d{2}-\d{2}$", start):
            messagebox.showwarning("提示", "开始日期格式不正确 (YYYY-MM-DD)")
            return
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", end):
            messagebox.showwarning("提示", "结束日期格式不正确 (YYYY-MM-DD)")
            return

        # 构建数据
        color = self.entry_color.get().strip()
        type_map_rev = {label: key for key, label in EVENT_TYPES}
        ev_type = type_map_rev.get(self.combo_type.get(), "version-main")
        desc = self.text_desc.get("1.0", tk.END).strip()
        tags_raw = self.entry_tags.get().strip()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

        ev = self.events[self.selected_index]
        ev["title"] = title
        ev["type"] = ev_type
        ev["start_date"] = start
        ev["end_date"] = end
        if color:
            ev["color"] = color
        else:
            ev.pop("color", None)
        if desc:
            ev["description"] = desc
        else:
            ev.pop("description", None)
        if tags:
            ev["tags"] = tags
        else:
            ev.pop("tags", None)

        # 自动生成 ID
        if not ev.get("id"):
            ev["id"] = self._auto_id(title, start)

        # 写入文件
        save_events(self.current_game, self.events)
        self._refresh_event_list()
        self._refresh_game_list()
        self.event_tree.selection_set(str(self.selected_index))
        self.status.config(text=f"已保存 → data/events/{self.current_game}.yaml")

    def _auto_id(self, title: str, start_date: str) -> str:
        import re

        prefix = {"genshin-impact": "gi", "honkai-star-rail": "hsr", "zenless-zone-zero": "zzz"}.get(
            self.current_game, self.current_game[:3]
        )
        clean = re.sub(r"[「」『』""'']", "", title)
        words = re.findall(r"[一-鿿]+", clean)
        slug = "-".join(words[:3]) if words else "event"
        if len(slug) > 30:
            slug = slug[:30]
        return f"{prefix}-{slug}"


def main():
    root = tk.Tk()
    EventEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
