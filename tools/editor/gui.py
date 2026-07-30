#!/usr/bin/env python3
"""米游活动日历 — 可视化活动编辑器 (tkinter GUI)

用法:
    python tools/editor/gui.py
"""

import calendar
import datetime
import json
import os
import re
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser

from yaml_io import load_events, save_events, list_games, EVENT_TYPES, LEGACY_TYPE_MAP, GAME_FILES, DATA_DIR, PROJECT_ROOT
from extractor import extract, fetch_post, fetch_post_list, html_to_text, GIDS_MAP

TYPE_STATE_FILE = os.path.join(PROJECT_ROOT, "tools", "editor", "type_pool.json")

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
        self.selected_tag_names: list[str] = []
        # 类型库（同标签逻辑：从数据中动态收集，可增删，单选）
        self.type_pool: list[str] = []
        self.event_filter_map: list[int] = []  # display_index → real_index
        self.event_sort = tk.StringVar(value="date")
        self.event_filter_range = tk.StringVar(value="all")
        self.event_search_var = tk.StringVar()
        self._collect_all_tags()
        self._collect_all_types()

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

    # ─── 类型库 ──────────────────────────────────────────

    def _collect_all_types(self):
        # 内置类型始终作为基底
        seen = set()
        for key, label in EVENT_TYPES:
            seen.add(label)
        # 从事件数据收集
        for game_id in GAME_FILES:
            events = load_events(game_id)
            for ev in events:
                t = ev.get("type", "")
                if t:
                    # 旧类型映射
                    seen.add(LEGACY_TYPE_MAP.get(t, t))
        # 加载持久化类型
        saved = self._load_type_state()
        for t in saved:
            seen.add(t)
        self.type_pool = sorted(seen)
        self._save_type_state()

    def _load_type_state(self) -> list[str]:
        try:
            if os.path.exists(TYPE_STATE_FILE):
                with open(TYPE_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    def _save_type_state(self):
        try:
            os.makedirs(os.path.dirname(TYPE_STATE_FILE), exist_ok=True)
            with open(TYPE_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.type_pool, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存类型状态失败: {e}")

    def _rebuild_type_pool(self):
        self._collect_all_types()
        self._refresh_type_combo()

    def _refresh_type_combo(self):
        self.combo_type["values"] = self.type_pool

    # ─── 日期选择器 ──────────────────────────────────────

    def _pick_date(self, entry: ttk.Entry):
        """弹出日历窗口，选中日期后填入 entry"""
        current = entry.get().strip()
        today = datetime.date.today()
        yr, mo, dy = today.year, today.month, today.day
        if re.match(r"^\d{4}-\d{2}-\d{2}$", current):
            py2, pm2, pd2 = int(current[:4]), int(current[5:7]), int(current[8:10])
            if 2020 <= py2 <= 2100:
                yr, mo, dy = py2, pm2, pd2

        dlg = tk.Toplevel(self.root)
        dlg.title("选择日期")
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        px = rx + (rw - 260) // 2
        py = ry + (rh - 240) // 2
        dlg.geometry(f"260x240+{px}+{py}")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)

        nav = ttk.Frame(dlg)
        nav.pack(pady=4)
        ttk.Button(nav, text="◀", width=2, command=lambda: self._cal_nav(-1)).pack(side=tk.LEFT, padx=2)
        self._cal_label = ttk.Label(nav, text="", font=FONT_BOLD, width=16, anchor=tk.CENTER)
        self._cal_label.pack(side=tk.LEFT)
        ttk.Button(nav, text="▶", width=2, command=lambda: self._cal_nav(1)).pack(side=tk.LEFT, padx=2)

        # 星期头
        wf = ttk.Frame(dlg)
        wf.pack()
        for w in ["一", "二", "三", "四", "五", "六", "日"]:
            ttk.Label(wf, text=w, width=3, anchor=tk.CENTER, font=FONT_SMALL).pack(side=tk.LEFT)

        self._cal_grid = ttk.Frame(dlg)
        self._cal_grid.pack(pady=2)
        self._cal_year = yr
        self._cal_month = mo
        self._cal_entry = entry
        self._cal_dlg = dlg
        self._cal_render(yr, mo)

    def _cal_nav(self, delta: int):
        self._cal_month += delta
        if self._cal_month > 12:
            self._cal_month = 1
            self._cal_year += 1
        elif self._cal_month < 1:
            self._cal_month = 12
            self._cal_year -= 1
        self._cal_render(self._cal_year, self._cal_month)

    def _cal_render(self, year: int, month: int):
        self._cal_label.config(text=f"{year}年 {month}月")
        for w in self._cal_grid.winfo_children():
            w.destroy()

        cal = calendar.monthcalendar(year, month)
        for r, week in enumerate(cal):
            for c, day in enumerate(week):
                if day == 0:
                    ttk.Label(self._cal_grid, text="", width=3).grid(row=r, column=c)
                else:
                    btn = ttk.Button(
                        self._cal_grid, text=str(day), width=3,
                        command=lambda d=day: self._cal_select(year, month, d),
                    )
                    btn.grid(row=r, column=c, padx=1, pady=1)

    def _cal_select(self, y: int, m: int, d: int):
        self._cal_entry.delete(0, tk.END)
        self._cal_entry.insert(0, f"{y}-{m:02d}-{d:02d}")
        self._cal_dlg.destroy()

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

        # 筛选排序栏
        filter_bar = ttk.Frame(center)
        filter_bar.pack(fill=tk.X, pady=(4, 0))

        ttk.Label(filter_bar, text="排序:", font=FONT_SMALL).pack(side=tk.LEFT)
        sort_combo = ttk.Combobox(filter_bar, textvariable=self.event_sort, values=["按开始日期", "按标题", "按类型"],
                                  state="readonly", width=10, font=FONT_SMALL)
        sort_combo.pack(side=tk.LEFT, padx=(2, 8))
        sort_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_event_list())

        ttk.Label(filter_bar, text="范围:", font=FONT_SMALL).pack(side=tk.LEFT)
        range_combo = ttk.Combobox(filter_bar, textvariable=self.event_filter_range, values=["全部", "本月", "近30天"],
                                   state="readonly", width=6, font=FONT_SMALL)
        range_combo.pack(side=tk.LEFT, padx=(2, 8))
        range_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_event_list())

        ttk.Label(filter_bar, text="搜索:", font=FONT_SMALL).pack(side=tk.LEFT)
        search_entry = ttk.Entry(filter_bar, textvariable=self.event_search_var, width=14, font=FONT_SMALL)
        search_entry.pack(side=tk.LEFT, padx=2)
        self.event_search_var.trace_add("write", lambda *a: self._refresh_event_list())

        btn_frame = ttk.Frame(center)
        btn_frame.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_frame, text="+ 新建活动", command=self._new_event).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑 删除选中", command=self._delete_event).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📥 解析公告", command=self._open_parser).pack(side=tk.RIGHT, padx=2)

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

        # 类型 — 动态下拉框 + 管理按钮
        ttk.Label(right, text="类型", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.W, **PAD)
        type_row = ttk.Frame(right)
        type_row.grid(row=row, column=1, columnspan=2, sticky=tk.EW, **PAD)
        type_row.columnconfigure(0, weight=1)
        self.combo_type = ttk.Combobox(
            type_row, values=self.type_pool, state="readonly", font=FONT,
        )
        self.combo_type.grid(row=0, column=0, sticky=tk.EW)
        self.combo_type.set(self.type_pool[0] if self.type_pool else "")
        ttk.Button(type_row, text="✎", width=2, command=self._manage_types).grid(row=0, column=1, padx=(2, 0))
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
        ttk.Button(date_row, text="📅", width=3, command=lambda: self._pick_date(self.entry_start)).pack(side=tk.LEFT, padx=2)
        ttk.Label(date_row, text="YYYY-MM-DD", foreground="gray", font=FONT_SMALL).pack(side=tk.LEFT, padx=4)
        row += 1

        ttk.Label(right, text="结束", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.W, **PAD)
        date2_row = ttk.Frame(right)
        date2_row.grid(row=row, column=1, columnspan=2, sticky=tk.W, **PAD)
        self.entry_end = ttk.Entry(date2_row, width=14, font=FONT)
        self.entry_end.pack(side=tk.LEFT)
        ttk.Button(date2_row, text="📅", width=3, command=lambda: self._pick_date(self.entry_end)).pack(side=tk.LEFT, padx=2)
        row += 1

        # 描述
        ttk.Label(right, text="描述", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.NW, **PAD)
        self.text_desc = tk.Text(right, height=3, font=FONT, wrap=tk.WORD)
        self.text_desc.grid(row=row, column=1, columnspan=2, sticky=tk.EW, **PAD)
        row += 1

        # 网页链接
        ttk.Label(right, text="链接", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.W, **PAD)
        self.entry_link = ttk.Entry(right, font=FONT)
        self.entry_link.grid(row=row, column=1, columnspan=2, sticky=tk.EW, **PAD)
        row += 1

        # 标签 — 搜索 + 多选列表 + 已选展示
        ttk.Label(right, text="标签", font=FONT_SMALL).grid(row=row, column=0, sticky=tk.NW, **PAD)

        tag_area = ttk.Frame(right)
        tag_area.grid(row=row, column=1, columnspan=2, sticky=tk.NSEW, **PAD)
        right.rowconfigure(row, weight=1)
        tag_area.columnconfigure(0, weight=1)

        # 搜索框
        self.tag_search_var = tk.StringVar()
        self.tag_search_var.trace_add("write", lambda *a: self._filter_tags())
        tag_search = ttk.Entry(tag_area, textvariable=self.tag_search_var, font=FONT_SMALL)
        tag_search.grid(row=0, column=0, sticky=tk.EW, pady=(0, 2))
        tag_search.insert(0, "")

        # 过滤后的标签列表
        tag_list_frame = ttk.Frame(tag_area)
        tag_list_frame.grid(row=1, column=0, sticky=tk.NSEW)
        tag_area.rowconfigure(1, weight=1)

        self.tag_listbox = tk.Listbox(tag_list_frame, selectmode=tk.MULTIPLE, font=FONT_SMALL, exportselection=False, height=4)
        self.tag_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tag_listbox.bind("<<ListboxSelect>>", self._on_tag_select)
        tag_scroll = ttk.Scrollbar(tag_list_frame, orient=tk.VERTICAL, command=self.tag_listbox.yview)
        tag_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tag_listbox.config(yscrollcommand=tag_scroll.set)

        tag_btns = ttk.Frame(tag_list_frame)
        tag_btns.pack(side=tk.RIGHT, fill=tk.Y, padx=(2, 0))
        ttk.Button(tag_btns, text="+", width=2, command=self._add_tag_to_pool).pack(pady=1)
        ttk.Button(tag_btns, text="✎", width=2, command=self._manage_tags).pack(pady=1)

        # 已选标签展示
        self.selected_tags_frame = ttk.Frame(tag_area)
        self.selected_tags_frame.grid(row=2, column=0, sticky=tk.EW, pady=(4, 0))
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

    def _refresh_tag_list(self, tags: list[str] | None = None):
        if tags is None:
            self._filter_tags()
            return
        self.tag_listbox.delete(0, tk.END)
        for t in tags:
            self.tag_listbox.insert(tk.END, t)

    def _filter_tags(self):
        query = self.tag_search_var.get().strip().lower()
        if not query:
            filtered = self.tag_pool
        else:
            filtered = [t for t in self.tag_pool if query in t.lower()]
        self.tag_listbox.delete(0, tk.END)
        for t in filtered:
            self.tag_listbox.insert(tk.END, t)
        # Restore selection for visible tags
        for i, t in enumerate(filtered):
            if t in self.selected_tag_names:
                self.tag_listbox.selection_set(i)

    def _on_tag_select(self, event=None):
        # Collect all selected tags from visible list
        visible = self._get_visible_tags()
        for i in self.tag_listbox.curselection():
            tag = visible[i]
            if tag not in self.selected_tag_names:
                self.selected_tag_names.append(tag)
        # Remove deselected (tags in selected_tag_names but not in selection AND still visible)
        for i, tag in enumerate(visible):
            if tag in self.selected_tag_names and i not in self.tag_listbox.curselection():
                self.selected_tag_names.remove(tag)
        self._refresh_selected_tags_display()

    def _get_visible_tags(self) -> list[str]:
        return [self.tag_listbox.get(i) for i in range(self.tag_listbox.size())]

    def _get_selected_tags(self) -> list[str]:
        return list(self.selected_tag_names)

    def _refresh_selected_tags_display(self):
        for w in self.selected_tags_frame.winfo_children():
            w.destroy()
        if not self.selected_tag_names:
            ttk.Label(self.selected_tags_frame, text="(未选择)", foreground="gray", font=FONT_SMALL).pack(anchor=tk.W)
            return
        for tag in self.selected_tag_names:
            chip = ttk.Frame(self.selected_tags_frame)
            chip.pack(side=tk.LEFT, padx=(0, 3), pady=1)
            ttk.Label(chip, text=tag, font=FONT_SMALL, background="#E0E7FF", foreground="#3730A3",
                      padding=(4, 1)).pack(side=tk.LEFT)
            btn = ttk.Button(chip, text="×", width=2,
                             command=lambda t=tag: self._remove_selected_tag(t))
            btn.pack(side=tk.LEFT)

    def _remove_selected_tag(self, tag: str):
        if tag in self.selected_tag_names:
            self.selected_tag_names.remove(tag)
        # Update listbox selection
        query = self.tag_search_var.get().strip().lower()
        visible = self.tag_pool if not query else [t for t in self.tag_pool if query in t.lower()]
        for i, t in enumerate(visible):
            if t == tag:
                self.tag_listbox.selection_clear(i)
        self._refresh_selected_tags_display()

    def _set_tag_selection(self, event_tags: list[str]):
        self.selected_tag_names = list(event_tags)
        self.tag_listbox.selection_clear(0, tk.END)
        visible = self._get_visible_tags()
        for i, t in enumerate(visible):
            if t in event_tags:
                self.tag_listbox.selection_set(i)
        self._refresh_selected_tags_display()

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
                # 同步当前编辑活动中的标签选择
                if name in self.selected_tag_names:
                    self.selected_tag_names.remove(name)
                    self._refresh_selected_tags_display()
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
                # 如果当前正在编辑这个游戏，同步刷新内存数据和表单
                if game_id == self.current_game:
                    self.events = load_events(game_id)
                    if self.selected_index is not None and self.selected_index < len(self.events):
                        self.selected_tag_names = list(self.events[self.selected_index].get("tags", []))
                        self._refresh_selected_tags_display()

    def _manage_types(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("管理活动类型")
        dlg.geometry("300x350")
        dlg.transient(self.root)
        dlg.grab_set()
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        dlg.geometry(f"300x350+{rx+(rw-300)//2}+{ry+(rh-350)//2}")

        ttk.Label(dlg, text="活动类型库（跨游戏共享）", font=FONT_BOLD).pack(padx=12, pady=(12, 4))
        ttk.Label(dlg, text="删除类型前需处理使用该类型的活动", foreground="gray", font=FONT_SMALL).pack(padx=12)

        lb = tk.Listbox(dlg, font=FONT)
        lb.pack(padx=12, fill=tk.BOTH, expand=True, pady=4)
        for t in self.type_pool:
            lb.insert(tk.END, t)

        # 添加
        add_frame = ttk.Frame(dlg)
        add_frame.pack(fill=tk.X, padx=12, pady=4)
        add_entry = ttk.Entry(add_frame, font=FONT)
        add_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(add_frame, text="添加", command=lambda: do_add()).pack(side=tk.LEFT, padx=4)

        def do_add():
            name = add_entry.get().strip()
            if name and name not in self.type_pool:
                self.type_pool.append(name)
                self.type_pool.sort()
                self._refresh_type_combo()
                self._save_type_state()
                lb.delete(0, tk.END)
                for t in self.type_pool:
                    lb.insert(tk.END, t)
            add_entry.delete(0, tk.END)

        def do_delete():
            sel = lb.curselection()
            if not sel:
                return
            name = self.type_pool[sel[0]]
            # 检查使用此类型的活动数量
            count = 0
            for game_id in GAME_FILES:
                events = load_events(game_id)
                for ev in events:
                    if ev.get("type") == name:
                        count += 1
            if count > 0:
                ok = messagebox.askyesno("确认删除",
                    f"类型「{name}」被 {count} 个活动使用。\n"
                    f"删除后这些活动的类型不变，但将从可选列表中移除。\n确认删除?",
                    parent=dlg)
                if not ok:
                    return
            self.type_pool.remove(name)
            self._refresh_type_combo()
            self._save_type_state()
            if self.selected_index is not None and self.combo_type.get() == name:
                self.combo_type.set(self.type_pool[0] if self.type_pool else "")
            lb.delete(0, tk.END)
            for t in self.type_pool:
                lb.insert(tk.END, t)
            self.status.config(text=f"已删除类型: {name}")

        ttk.Button(dlg, text="🗑 删除选中类型", command=do_delete).pack(pady=8)
        add_entry.bind("<Return>", lambda e: do_add())

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
        self.tag_search_var.set("")
        self._collect_all_types()
        self._refresh_type_combo()
        self._rebuild_tag_pool()
        self._refresh_event_list()
        self._clear_form()

    # ─── 活动列表 ──────────────────────────────────────────

    def _type_label(self, type_val: str) -> str:
        """将类型值转为显示标签（旧英文key→中文，自定义直接显示）"""
        return LEGACY_TYPE_MAP.get(type_val, dict(EVENT_TYPES).get(type_val, type_val))

    def _type_key(self, label: str) -> str:
        """将显示标签转回类型值（直接返回，类型即标签）"""
        # 当前系统类型即中文标签，直接返回
        return label

    def _refresh_event_list(self):
        today = datetime.date.today()
        search = self.event_search_var.get().strip().lower()

        # 筛选 + 排序
        filtered: list[tuple[int, dict]] = []
        for i, ev in enumerate(self.events):
            start = ev.get("start_date", "")
            # 范围过滤
            if self.event_filter_range.get() == "本月":
                if not start or start[:7] != today.strftime("%Y-%m"):
                    continue
            elif self.event_filter_range.get() == "近30天":
                if start:
                    try:
                        d = datetime.date.fromisoformat(start)
                        if d < today or d > today + datetime.timedelta(days=30):
                            continue
                    except ValueError:
                        pass
            # 搜索过滤
            if search and search not in ev.get("title", "").lower() and search not in ev.get("id", "").lower():
                continue
            filtered.append((i, ev))

        # 排序
        sort_key = self.event_sort.get()
        if sort_key == "按开始日期":
            filtered.sort(key=lambda x: x[1].get("start_date", ""))
        elif sort_key == "按标题":
            filtered.sort(key=lambda x: x[1].get("title", ""))
        elif sort_key == "按类型":
            filtered.sort(key=lambda x: self._type_label(x[1].get("type", "")))
        else:
            filtered.sort(key=lambda x: x[1].get("start_date", ""))

        self.event_filter_map = [f[0] for f in filtered]

        self.event_tree.delete(*self.event_tree.get_children())
        for di, (ri, ev) in enumerate(filtered):
            self.event_tree.insert(
                "", tk.END, iid=str(di),
                values=(
                    ev.get("title", ""),
                    self._type_label(ev.get("type", "")),
                    f"{ev.get('start_date','')} ~ {ev.get('end_date','')}",
                    ev.get("id", ""),
                ),
            )

    def _on_event_select(self, event):
        sel = self.event_tree.selection()
        if not sel:
            return
        di = int(sel[0])
        if di < len(self.event_filter_map):
            self.selected_index = self.event_filter_map[di]
            self._load_form(self.events[self.selected_index])

    def _new_event(self):
        if not self.current_game:
            messagebox.showwarning("提示", "请先选择游戏")
            return
        default_type = self._type_key(self.type_pool[0]) if self.type_pool else "version-main"
        self.events.append({
            "id": "", "game": self.current_game, "title": "",
            "type": default_type, "start_date": "", "end_date": "",
        })
        self.selected_index = len(self.events) - 1
        self._refresh_event_list()
        try:
            di = self.event_filter_map.index(self.selected_index)
            self.event_tree.selection_set(str(di))
            self.event_tree.see(str(di))
        except ValueError:
            pass
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
        self.entry_title.delete(0, tk.END)
        self.entry_title.insert(0, ev.get("title", ""))
        type_label = self._type_label(ev.get("type", ""))
        # 确保 label 在 pool 中
        if type_label not in self.type_pool:
            self.type_pool.append(type_label)
            self.type_pool.sort()
            self._refresh_type_combo()
        self.combo_type.set(type_label)

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
        self.entry_link.delete(0, tk.END)
        self.entry_link.insert(0, ev.get("source_url", ""))

        self._set_tag_selection(ev.get("tags", []))
        self._update_color_preview()

    def _clear_form(self):
        self.selected_index = None
        for w in [self.entry_title, self.entry_color, self.entry_start, self.entry_end, self.entry_link]:
            w.delete(0, tk.END)
        self.combo_type.set(self.type_pool[0] if self.type_pool else "")
        self.text_desc.delete("1.0", tk.END)
        self.spin_r.set(""); self.spin_g.set(""); self.spin_b.set("")
        self.color_preview.config(bg=self.root.cget("bg"))
        self.selected_tag_names = []
        self.tag_listbox.selection_clear(0, tk.END)
        self._refresh_selected_tags_display()

    def _revert_form(self):
        if self.selected_index is not None and self.selected_index < len(self.events):
            self._load_form(self.events[self.selected_index])

    # ─── 公告解析 ────────────────────────────────────────

    def _open_parser(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("📥 解析公告")
        dlg.transient(self.root)
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        dlg.geometry(f"620x680+{rx+(rw-620)//2}+{ry+(rh-680)//2}")
        dlg.grab_set()

        nb = ttk.Notebook(dlg, height=300)
        nb.pack(fill=tk.X, padx=8, pady=8)

        # ── Tab 1: 粘贴文本 ──
        tab1 = ttk.Frame(nb)
        nb.add(tab1, text="粘贴文本")
        ttk.Label(tab1, text="粘贴公告原文，支持 HTML 或纯文本:", font=FONT_SMALL).pack(padx=8, pady=(8, 2))
        text_area = tk.Text(tab1, height=12, font=FONT, wrap=tk.WORD)
        text_area.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # ── Tab 2: 公告列表 ──
        tab2 = ttk.Frame(nb)
        nb.add(tab2, text="公告列表")
        ttk.Label(tab2, text="从米游社获取最新公告 (当前游戏):", font=FONT_SMALL).pack(padx=8, pady=(8, 2))

        list_frame = ttk.Frame(tab2)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8)
        scroll2 = ttk.Scrollbar(list_frame)
        scroll2.pack(side=tk.RIGHT, fill=tk.Y)
        post_listbox = tk.Listbox(list_frame, font=FONT_SMALL, yscrollcommand=scroll2.set)
        post_listbox.pack(fill=tk.BOTH, expand=True)
        scroll2.config(command=post_listbox.yview)

        def refresh_post_list():
            post_listbox.delete(0, tk.END)
            if self.current_game:
                posts = fetch_post_list(self.current_game, 15)
                for p in posts:
                    ts = p.get("created_at", 0)
                    dt = datetime.datetime.fromtimestamp(ts).strftime("%m/%d") if ts else "??"
                    post_listbox.insert(tk.END, f"[{dt}] {p['subject'][:60]}")
                    post_listbox.itemconfig(tk.END, fg="gray" if "已结束" in p["subject"] else "black")
                self._parser_posts = posts
            ttk.Label(list_frame, text=f"共 {len(getattr(self, '_parser_posts', []))} 篇", font=FONT_SMALL).pack()

        ttk.Button(tab2, text="🔄 刷新列表", command=refresh_post_list).pack(pady=4)
        nb.bind("<<NotebookTabChanged>>", lambda e: refresh_post_list() if nb.index(nb.select()) == 1 else None)

        # ── Tab 3: 输入 post_id ──
        tab3 = ttk.Frame(nb)
        nb.add(tab3, text="Post ID")
        ttk.Label(tab3, text="输入公告的 post_id:", font=FONT_SMALL).pack(padx=8, pady=(8, 2))
        ttk.Label(tab3, text="(从 miyoushe.com 公告 URL 的最后一段数字)", foreground="gray", font=FONT_SMALL).pack()
        pid_entry = ttk.Entry(tab3, font=FONT, width=25)
        pid_entry.pack(padx=8, pady=4)

        # ── 结果预览区 ──
        result_frame = ttk.LabelFrame(dlg, text="提取结果", padding=4)
        result_frame.pack(fill=tk.X, padx=8, pady=(0, 4))

        result_labels: dict[str, ttk.Label] = {}
        for field, label in [("title", "标题"), ("type", "类型"), ("start_date", "开始"),
                             ("end_date", "结束"), ("description", "描述")]:
            row = ttk.Frame(result_frame)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=f"{label}:", font=FONT_SMALL, width=5).pack(side=tk.LEFT)
            lbl = ttk.Label(row, text="", font=FONT_SMALL, foreground="gray")
            lbl.pack(side=tk.LEFT, padx=4)
            result_labels[field] = lbl

        tags_label = ttk.Label(result_frame, text="", font=FONT_SMALL, foreground="#3730A3")
        tags_label.pack(anchor=tk.W, padx=44)

        parsed_data: dict = {}

        def do_parse():
            nonlocal parsed_data
            text = ""
            result = None
            tab = nb.index(nb.select())

            if tab == 0:
                text = text_area.get("1.0", tk.END)
            elif tab == 1:
                sel = post_listbox.curselection()
                posts = getattr(self, "_parser_posts", [])
                if not sel or not posts:
                    messagebox.showwarning("提示", "请先刷新公告列表并选择一篇公告", parent=dlg)
                    return
                pid = posts[sel[0]]["post_id"]
                result = fetch_post(pid, self.current_game or "genshin-impact")
                if result and result.get("error"):
                    messagebox.showwarning("提示", f"获取失败: {result['error']}", parent=dlg)
                    return
                text = result.get("text", "") if result else ""
            elif tab == 2:
                pid = pid_entry.get().strip()
                if not pid:
                    messagebox.showwarning("提示", "请输入 post_id", parent=dlg)
                    return
                result = fetch_post(pid, self.current_game or "genshin-impact")
                if result and result.get("error"):
                    messagebox.showwarning("提示", f"获取失败: {result['error']}", parent=dlg)
                    return
                text = result.get("text", "") if result else ""
                if not text:
                    messagebox.showwarning("提示", f"获取 post_id={pid} 失败，正文为空", parent=dlg)
                    return

            if not text.strip():
                reason = result.get("error", "正文为空") if result else "未知错误"
                messagebox.showwarning("提示", f"未获取到公告文本: {reason}", parent=dlg)
                return

            game = self.current_game or "genshin-impact"
            raw_text = html_to_text(text) if "<" in text else text
            parsed_data = extract(raw_text, game)
            # API 获取时优先用 API 返回的标题
            if result and result.get("subject"):
                parsed_data["title"] = result["subject"]

            # 更新预览
            result_labels["title"].config(text=parsed_data.get("title", "(未识别)")[:60])
            result_labels["type"].config(text=self._type_label(parsed_data.get("type", "")))
            result_labels["start_date"].config(text=parsed_data.get("start_date", "(未识别)"))
            result_labels["end_date"].config(text=parsed_data.get("end_date", "(未识别)"))
            desc = parsed_data.get("description", "")
            result_labels["description"].config(text=desc[:80] + ("..." if len(desc) > 80 else ""))
            tags_label.config(text="标签: " + ", ".join(parsed_data.get("tags", [])))

        def do_fill():
            if not parsed_data or not self.current_game:
                return
            # 先创建空白活动条目（内部会设 selected_index 并加载空白表单）
            default_type = self._type_key(self.type_pool[0]) if self.type_pool else "version-main"
            self.events.append({
                "id": "", "game": self.current_game, "title": "",
                "type": default_type, "start_date": "", "end_date": "",
            })
            self.selected_index = len(self.events) - 1
            self._refresh_event_list()
            # 用解析结果填充表单
            self.entry_title.delete(0, tk.END)
            self.entry_title.insert(0, parsed_data.get("title", ""))
            if parsed_data.get("type"):
                type_label = self._type_label(parsed_data["type"])
                # 如果提取的类型不在当前池中（可能已被用户删除），使用默认
                if type_label in self.type_pool:
                    self.combo_type.set(type_label)
                else:
                    self.combo_type.set(self.type_pool[0] if self.type_pool else type_label)
            if parsed_data.get("start_date"):
                self.entry_start.delete(0, tk.END)
                self.entry_start.insert(0, parsed_data["start_date"])
            if parsed_data.get("end_date"):
                self.entry_end.delete(0, tk.END)
                self.entry_end.insert(0, parsed_data["end_date"])
            if parsed_data.get("description"):
                self.text_desc.delete("1.0", tk.END)
                self.text_desc.insert("1.0", parsed_data["description"])
            if parsed_data.get("tags"):
                self.selected_tag_names = [t for t in parsed_data["tags"] if t in self.tag_pool]
                self._set_tag_selection(self.selected_tag_names)
            dlg.destroy()
            self.status.config(text="解析结果已填入表单，请核实后保存")

        btn_bar = ttk.Frame(dlg)
        btn_bar.pack(pady=(0, 8))
        ttk.Button(btn_bar, text="🔍 解析", command=do_parse).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar, text="📋 填入表单", command=do_fill).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar, text="关闭", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

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
        ev_type = self._type_key(self.combo_type.get())
        desc = self.text_desc.get("1.0", tk.END).strip()
        link = self.entry_link.get().strip()
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
        if link:
            ev["source_url"] = link
        else:
            ev.pop("source_url", None)
        if tags:
            ev["tags"] = tags
        else:
            ev.pop("tags", None)
        if not ev.get("id"):
            ev["id"] = self._auto_id(title, start)

        save_events(self.current_game, self.events)
        # 保存后同步标签库（新标签自动加入）
        for t in tags:
            if t not in self.tag_pool:
                self.tag_pool.append(t)
        self.tag_pool.sort()
        self._refresh_tag_list()
        self._refresh_event_list()
        self._refresh_game_list()
        # 找到保存活动在显示列表中的位置
        try:
            di = self.event_filter_map.index(self.selected_index)
            self.event_tree.selection_set(str(di))
            self.event_tree.see(str(di))
        except ValueError:
            pass
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
