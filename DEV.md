# 开发者文档

## 技术栈

- **前端**: React 19 + TypeScript + Vite 8 + Tailwind CSS 4 + Zod 4
- **数据**: YAML 静态文件，Vite glob import + js-yaml 解析
- **编辑器**: Python 3 + tkinter + PyYAML + requests
- **CI/CD**: GitHub Actions + Vercel
- **测试**: Vitest + React Testing Library

## 本地开发

```bash
git clone git@github.com:autummu2/HoyoCalendar.git
cd HoyoCalendar

npm install
npm run dev      # 启动开发服务器 (localhost:5173)
npm test         # 运行测试 (26 tests)
npm run build    # 生产构建
```

## 项目结构

```
HoyoCalendar/
├── src/                  # 前端源码 (React)
│   ├── components/
│   │   ├── calendar/     # 日历组件 (CalendarGrid, DayView)
│   │   ├── event/        # 活动详情 (EventDetail)
│   │   ├── filter/       # 筛选器 (GameFilter, TypeFilter, CompletionFilter)
│   │   └── layout/       # 布局 (Header)
│   ├── hooks/            # useEvents, useTheme, useCompletedEvents
│   ├── lib/              # date-utils, data-loader, event-layout, constants
│   └── types/            # Zod schema + TypeScript 类型
├── data/events/          # 活动 YAML 数据文件
├── tools/editor/         # Python 数据编辑器
│   ├── gui.py            # tkinter 图形界面
│   ├── extractor.py      # 公告解析引擎 + 米游社 API
│   ├── yaml_io.py        # YAML 读写模块
│   └── main.py           # 终端交互式界面
├── editor.bat            # 一键启动编辑器
└── DEVELOPMENT_PLAN.md   # 详细开发计划书
```

## 数据编辑器

```bash
# 双击 editor.bat 或命令行
python tools/editor/gui.py
```

功能：
- ✏️ 可视化管理活动数据，直接读写 `data/events/*.yaml`
- 📥 公告解析：粘贴文本 / 米游社 API / Post ID，自动提取字段填入表单
- 🏷️ 动态类型和标签管理（可增删）
- 🚀 一键推送数据到 GitHub，触发 Vercel 自动部署

依赖安装：

```bash
pip install -r tools/editor/requirements.txt
```

## 数据模型

活动数据存储在 `data/events/` 下按游戏分文件的 YAML 中，由 Zod schema（`src/types/events.ts`）校验。

```yaml
- id: "gi-4.0-version"
  game: "genshin-impact"
  title: "「仿若无因飘落的轻雨」4.0 版本"
  type: "版本大活动"
  color: "#DBEAFE"           # 可选，色条背景色
  start_date: "2026-08-16"
  end_date: "2026-09-27"
  description: "枫丹地区开放..."
  tags: ["枫丹", "版本更新"]
  source_url: "https://ys.mihoyo.com/"
  phases:                    # 可选，子阶段
    - title: "上半"
      start_date: "2026-08-16"
      end_date: "2026-09-06"
```

## 分支与部署

- `main` — 生产分支，Vercel 自动部署
- `develop` — 开发主分支
- `feature/<name>` — 功能分支

CI 在 push/PR 到 main 和 develop 时自动运行 lint → test → build。
编辑器推送数据更新到 develop 后自动合并到 main 并触发部署。
