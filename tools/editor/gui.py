#!/usr/bin/env python3
"""米游活动日历 — 可视化活动编辑器 (tkinter GUI)

用法:
    python tools/editor/gui.py
"""

import re
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser

from yaml_io import load_events, save_events, list_games, EVENT_TYPES, GAME_FILES, DATA_DIR

FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_SMALL = ("Microsoft YaHei UI", 9)

PAD = {"padx": 4, "pady": 2}


class EventEditor:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("米游活动日历 — 数据编辑器")
        self.root.geometry("1250x700")

        self.games = list_games()
        self.current_game: str | None = None
        self.events: list[dict] = []
        self.selected_index: int | None = None

        # 标签库（跨游戏共享，启动时从所有 YAML 中收集）
        self.tag_pool: list[str] = []
        self._collect_all_tags()

        self._build_ui()
        self._refresh_game_list()

    # ─── 标签库 ──────────────────────────────────────────

    def _collect_all_tags(self):
        seen = set()
        for game_id in GAME_FILES:
            events = load_events(game_id)
            for ev in events:
                for t in ev.get("tags", []):
                    seen.add(t)
        self.tag_pool = sorted(seen)

    def _rebuild_tag_pool(self):
        self._collect_all_tags()
        self._refresh_tag_list()

    # ─── UI 构建 ──────────────────────────────────────────

    def _build_ui(self):
        # 顶栏
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, **PAD)
        ttk.Label(top, text="🎮 米游活动日历 — 数据编辑器", font=FONT_BOLD).pack(side=tk.LEFT, padx=8)
        ttk.Label(top, text="开发者工具 — 直接读写 data/events/*.yaml", foreground="gray").pack(side=tk.LEFT, padx=8)
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # 主体三栏
        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, **PAD)

        # ── 左栏：游戏列表 ──
        left = ttk.LabelFrame(body, text="游戏", padding=4)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 4))
        self.game_listbox = tk.Listbox(left, width=22, font=FONT, exportselection=False)
        self.game_listbox.pack(fill=tk.BOTH, expand=True)
        self.game_listbox.bind("<<ListboxSelect>>", self._on_game_select)

        # ── 中栏：活动列表 ──
        center = ttk.LabelFrame(body, text="活动列表", padding=4)
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)

        self.event_tree = ttk.Treeview(
            center, columns=("title", "type", "date", "id"), show="headings", selectmode="browse",
        )
        self.event_tree.heading("title", text="标题")
        self.event_tree.heading("type", text="类型")
        self.event_tree.heading("date", text="日期")
        self.event_tree.heading("id", text="ID")
        self.event_tree.column("title", width=220)
        self.event_tree.column("type", width=90)
        self.event_tree.column("date", width=135)
        self.event_tree.column("id", width=120)
        self.event_tree.pack(fill=tk.BOTH, expand=True)
        self.event_tree.bind("<<TreeviewSelect>>", self._on_event_select)

        btn_frame = ttk.Frame(center)
        btn_frame.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_frame, text="+ 新建活动", command=self._new_event).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑 删除选中", command=self._delete_event).pack(side=tk.LEFT, padx=2)

        # ── 右栏：编辑表单 ──
        right = ttk.LabelFrame(body, text="编辑活动", padding=8)
        right.pack(side=tk.LEFT, fill=tk.BOTH, padx=(4, 0))
        right.columnconfigure(1, weight=1)

        row = 0

        # 标题 — 跨两列
        ttk.Label(right, text="标题", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.W, **PAD)
        self.entry_title = ttk.Entry(right, font=FONT)
        self.entry_title.grid(row=row, column=1, columnspan=2, sticky=tk.EW, **PAD)
        row += 1

        # 类型 — 加宽下拉框
        ttk.Label(right, text="类型", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.W, **PAD)
        self.combo_type = ttk.Combobox(
            right, values=[label for _, label in EVENT_TYPES], state="readonly", font=FONT,
        )
        self.combo_type.grid(row=row, column=1, columnspan=2, sticky=tk.EW, **PAD)
        self.combo_type.set(EVENT_TYPES[0][1])
        row += 1

        # 颜色: hex + 选色按钮 + 预览 + RGB
        ttk.Label(right, text="颜色", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.W, **PAD)

        color_frame = ttk.Frame(right)
        color_frame.grid(row=row, column=1, columnspan=2, sticky=tk.EW, **PAD)

        self.entry_color = ttk.Entry(color_frame, width=9, font=FONT)
        self.entry_color.pack(side=tk.LEFT)
        self.entry_color.bind("<KeyRelease>", lambda e: self._on_color_change())

        ttk.Button(color_frame, text="选色", command=self._pick_color, width=4).pack(side=tk.LEFT, padx=2)

        self.color_preview = tk.Label(color_frame, text="   ", relief=tk.SUNKEN, width=4)
        self.color_preview.pack(side=tk.LEFT, padx=2)

        ttk.Label(color_frame, text="R:", font=FONT_SMALL).pack(side=tk.LEFT, padx=(6, 0))
        self.spin_r = ttk.Spinbox(color_frame, from_=0, to=255, width=4, font=FONT_SMALL, command=self._on_rgb_change)
        self.spin_r.pack(side=tk.LEFT)
        self.spin_r.bind("<KeyRelease>", lambda e: self._on_rgb_change())

        ttk.Label(color_frame, text="G:", font=FONT_SMALL).pack(side=tk.LEFT, padx=(4, 0))
        self.spin_g = ttk.Spinbox(color_frame, from_=0, to=255, width=4, font=FONT_SMALL, command=self._on_rgb_change)
        self.spin_g.pack(side=tk.LEFT)
        self.spin_g.bind("<KeyRelease>", lambda e: self._on_rgb_change())

        ttk.Label(color_frame, text="B:", font=FONT_SMALL).pack(side=tk.LEFT, padx=(4, 0))
        self.spin_b = ttk.Spinbox(color_frame, from_=0, to=255, width=4, font=FONT_SMALL, command=self._on_rgb_change)
        self.spin_b.pack(side=tk.LEFT)
        self.spin_b.bind("<KeyRelease>", lambda e: self._on_rgb_change())
        row += 1

        # 日期
        ttk.Label(right, text="开始", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.W, **PAD)
        date_row = ttk.Frame(right)
        date_row.grid(row=row, column=1, columnspan=2, sticky=tk.W, **PAD)
        self.entry_start = ttk.Entry(date_row, width=14, font=FONT)
        self.entry_start.pack(side=tk.LEFT)
        ttk.Label(date_row, text="YYYY-MM-DD", foreground="gray", font=FONT_SMALL).pack(side=tk.LEFT, padx=4)
        row += 1

        ttk.Label(right, text="结束", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.W, **PAD)
        self.entry_end = ttk.Entry(right, width=14, font=FONT)
        self.entry_end.grid(row=row, column=1, sticky=tk.W, **PAD)
        row += 1

        # 描述
        ttk.Label(right, text="描述", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.NW, **PAD)
        self.text_desc = tk.Text(right, height=3, font=FONT, wrap=tk.WORD)
        self.text_desc.grid(row=row, column=1, columnspan=2, sticky=tk.EW, **PAD)
        row += 1

        # 标签 — 多选列表
        ttk.Label(right, text="标签", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.NW, **PAD)

        tag_frame = ttk.Frame(right)
        tag_frame.grid(row=row, column=1, columnspan=2, sticky=tk.NSEW, **PAD)
        right.rowconfigure(row, weight=1)

        self.tag_listbox = tk.Listbox(tag_frame, selectmode=tk.MULTIPLE, font=FONT_SMALL, exportselection=False, height=6)
        self.tag_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tag_scroll = ttk.Scrollbar(tag_frame, orient=tk.VERTICAL, command=self.tag_listbox.yview)
        tag_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tag_listbox.config(yscrollcommand=tag_scroll.set)

        tag_btns = ttk.Frame(tag_frame)
        tag_btns.pack(side=tk.RIGHT, fill=tk.Y, padx=(2, 0))
        ttk.Button(tag_btns, text="+", width=2, command=self._add_tag_to_pool).pack(pady=1)
        ttk.Button(tag_btns, text="✎", width=2, command=self._manage_tags).pack(pady=1)
        row += 1

        # 按钮
        btn_row = ttk.Frame(right)
        btn_row.grid(row=row, column=0, columnspan=3, pady=(8, 0))
        ttk.Button(btn_row, text="💾 保存", command=self._save_event).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="↩ 撤销修改", command=self._revert_form).pack(side=tk.LEFT, padx=4)

        # 状态栏
        self.status = ttk.Label(self.root, text="就绪", foreground="gray", font=FONT_SMALL)
        self.status.pack(side=tk.BOTTOM, fill=tk.X, **PAD)

    # ─── 颜色处理 ──────────────────────────────────────────

    def _pick_color(self):
        initial = self.entry_color.get().strip() or None
        result = colorchooser.askcolor(color=initial, title="选择色条颜色")
        if result and result[1]:
            self.entry_color.delete(0, tk.END)
            self.entry_color.insert(0, result[1])
            self._hex_to_rgb(result[1])
            self._update_color_preview()

    def _on_color_change(self):
        hex_val = self.entry_color.get().strip()
        if re.match(r"^#[0-9a-fA-F]{6}$", hex_val):
            self._hex_to_rgb(hex_val)
        self._update_color_preview()

    def _on_rgb_change(self):
        try:
            r = int(self.spin_r.get())
            g = int(self.spin_g.get())
            b = int(self.spin_b.get())
            hex_val = f"#{r:02x}{g:02x}{b:02x}"
            self.entry_color.delete(0, tk.END)
            self.entry_color.insert(0, hex_val)
        except ValueError:
            pass
        self._update_color_preview()

    def _hex_to_rgb(self, hex_val: str):
        if re.match(r"^#[0-9a-fA-F]{6}$", hex_val):
            self.spin_r.set(str(int(hex_val[1:3], 16)))
            self.spin_g.set(str(int(hex_val[3:5], 16)))
            self.spin_b.set(str(int(hex_val[5:7], 16)))

    def _update_color_preview(self):
        c = self.entry_color.get().strip()
        if re.match(r"^#[0-9a-fA-F]{6}$", c):
            try:
                self.color_preview.config(bg=c)
                return
            except tk.TclError:
                pass
        self.color_preview.config(bg=self.root.cget("bg"))

    # ─── 标签管理 ──────────────────────────────────────────

    def _refresh_tag_list(self):
        self.tag_listbox.delete(0, tk.END)
        for t in self.tag_pool:
            self.tag_listbox.insert(tk.END, t)

    def _set_tag_selection(self, event_tags: list[str]):
        self.tag_listbox.selection_clear(0, tk.END)
        for i, t in enumerate(self.tag_pool):
            if t in event_tags:
                self.tag_listbox.selection_set(i)

    def _get_selected_tags(self) -> list[str]:
        return [self.tag_pool[i] for i in self.tag_listbox.curselection()]

    def _add_tag_to_pool(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("添加标签")
        dlg.geometry("280x100")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="新标签名:", font=FONT).pack(padx=12, pady=(12, 4))
        entry = ttk.Entry(dlg, font=FONT)
        entry.pack(padx=12, fill=tk.X)
        entry.focus_set()

        def do_add():
            name = entry.get().strip()
            if name and name not in self.tag_pool:
                self.tag_pool.append(name)
                self.tag_pool.sort()
                self._refresh_tag_list()
            dlg.destroy()

        entry.bind("<Return>", lambda e: do_add())
        ttk.Button(dlg, text="添加", command=do_add).pack(pady=8)

    def _manage_tags(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("管理标签库")
        dlg.geometry("300x350")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="标签库（所有游戏共享）", font=FONT_BOLD).pack(padx=12, pady=(12, 4))
        ttk.Label(dlg, text="删除标签会从所有活动数据中移除该标签", foreground="gray", font=FONT_SMALL).pack(padx=12)

        lb = tk.Listbox(dlg, font=FONT)
        lb.pack(padx=12, fill=tk.BOTH, expand=True, pady=4)
        for t in self.tag_pool:
            lb.insert(tk.END, t)

        def do_delete():
            sel = lb.curselection()
            if not sel:
                return
            name = self.tag_pool[sel[0]]
            if messagebox.askyesno("确认", f"删除标签「{name}」?\n将从所有活动中移除。", parent=dlg):
                self._remove_tag_from_all_events(name)
                self.tag_pool.remove(name)
                self._refresh_tag_list()
                lb.delete(sel[0])
                self.status.config(text=f"已删除标签: {name}")

        ttk.Button(dlg, text="🗑 删除选中标签", command=do_delete).pack(pady=8)

    def _remove_tag_from_all_events(self, tag: str):
        for game_id in GAME_FILES:
            events = load_events(game_id)
            changed = False
            for ev in events:
                tags = ev.get("tags", [])
                if tag in tags:
                    tags.remove(tag)
                    if not tags:
                        ev.pop("tags", None)
                    changed = True
            if changed:
                save_events(game_id, events)

    # ─── 游戏列表 ──────────────────────────────────────────

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
        self._rebuild_tag_pool()
        self._refresh_event_list()
        self._clear_form()

    # ─── 活动列表 ──────────────────────────────────────────

    def _refresh_event_list(self):
        type_map = dict(EVENT_TYPES)
        self.event_tree.delete(*self.event_tree.get_children())
        for i, ev in enumerate(self.events):
            self.event_tree.insert(
                "", tk.END, iid=str(i),
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
        self.events.append({
            "id": "", "game": self.current_game, "title": "",
            "type": "version-main", "start_date": "", "end_date": "",
        })
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

    # ─── 表单 ──────────────────────────────────────────────

    def _load_form(self, ev: dict):
        type_map_rev = {label: key for key, label in EVENT_TYPES}

        self.entry_title.delete(0, tk.END)
        self.entry_title.insert(0, ev.get("title", ""))
        self.combo_type.set(type_map_rev.get(ev.get("type", "version-main"), "版本主题活动"))

        color = ev.get("color", "")
        self.entry_color.delete(0, tk.END)
        self.entry_color.insert(0, color)
        if re.match(r"^#[0-9a-fA-F]{6}$", color):
            self._hex_to_rgb(color)
        else:
            self.spin_r.set(""); self.spin_g.set(""); self.spin_b.set("")

        self.entry_start.delete(0, tk.END)
        self.entry_start.insert(0, ev.get("start_date", ""))
        self.entry_end.delete(0, tk.END)
        self.entry_end.insert(0, ev.get("end_date", ""))
        self.text_desc.delete("1.0", tk.END)
        self.text_desc.insert("1.0", ev.get("description", ""))

        self._set_tag_selection(ev.get("tags", []))
        self._update_color_preview()

    def _clear_form(self):
        self.selected_index = None
        for w in [self.entry_title, self.entry_color, self.entry_start, self.entry_end]:
            w.delete(0, tk.END)
        self.combo_type.set(EVENT_TYPES[0][1])
        self.text_desc.delete("1.0", tk.END)
        self.spin_r.set(""); self.spin_g.set(""); self.spin_b.set("")
        self.color_preview.config(bg=self.root.cget("bg"))
        self.tag_listbox.selection_clear(0, tk.END)

    def _revert_form(self):
        if self.selected_index is not None and self.selected_index < len(self.events):
            self._load_form(self.events[self.selected_index])

    # ─── 保存 ──────────────────────────────────────────────

    def _save_event(self):
        if self.selected_index is None or not self.current_game:
            return

        title = self.entry_title.get().strip()
        if not title:
            messagebox.showwarning("提示", "标题不能为空")
            return

        start = self.entry_start.get().strip()
        end = self.entry_end.get().strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", start):
            messagebox.showwarning("提示", "开始日期格式不正确 (YYYY-MM-DD)")
            return
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", end):
            messagebox.showwarning("提示", "结束日期格式不正确 (YYYY-MM-DD)")
            return

        color = self.entry_color.get().strip()
        type_map_rev = {label: key for key, label in EVENT_TYPES}
        ev_type = type_map_rev.get(self.combo_type.get(), "version-main")
        desc = self.text_desc.get("1.0", tk.END).strip()
        tags = self._get_selected_tags()

        ev = self.events[self.selected_index]
        ev["title"] = title
        ev["type"] = ev_type
        ev["start_date"] = start
        ev["end_date"] = end
        if color and re.match(r"^#[0-9a-fA-F]{6}$", color):
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
        if not ev.get("id"):
            ev["id"] = self._auto_id(title, start)

        save_events(self.current_game, self.events)
        self._rebuild_tag_pool()
        self._refresh_event_list()
        self._refresh_game_list()
        self.event_tree.selection_set(str(self.selected_index))
        self.status.config(text=f"已保存 → data/events/{GAME_FILES[self.current_game]}")

    def _auto_id(self, title: str, start_date: str) -> str:
        prefix = {
            "genshin-impact": "gi", "honkai-star-rail": "hsr", "zenless-zone-zero": "zzz",
        }.get(self.current_game, self.current_game[:3])
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
