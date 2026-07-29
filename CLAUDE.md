# CLAUDE.md — HoyoCalendar 项目开发指引

## 项目概述

米游活动日历（HoyoCalendar）— 展示米哈游旗下游戏活动日期的 Web 日历应用。
首期支持：原神、崩坏：星穹铁道、绝区零。

## 技术栈

- React 19 + TypeScript + Vite 8
- Tailwind CSS 4（`@tailwindcss/vite` 插件，无需 `tailwind.config.ts`）
- Zod 4 数据校验
- npm 包管理
- 数据：YAML 静态文件 + Vite 静态导入

## 目录结构

```
src/
├── components/
│   ├── calendar/      # 日历组件
│   ├── event/         # 活动详情组件
│   ├── filter/        # 筛选器组件
│   └── layout/        # 布局组件（Header 等）
├── types/             # TypeScript 类型 + Zod schema
├── hooks/             # 自定义 Hooks
├── lib/               # 工具函数
├── App.tsx
└── main.tsx
data/events/           # 活动 YAML 数据文件（按游戏分文件）
```

---

## 🔀 分支策略（核心规则）

**每个功能必须在独立分支上开发，禁止直接在 `develop` 或 `main` 上修改代码。**

### 分支命名

```
feature/<功能名>     # 新功能，如 feature/game-filter
bugfix/<描述>        # Bug修复，如 bugfix/calendar-render-error
refactor/<内容>      # 重构
data/<描述>          # 数据更新，如 data/gi-4.1-events
docs/<内容>          # 文档更新
```

### 标准开发流程

```bash
# 1. 从 develop 切出新功能分支
git checkout develop
git pull origin develop
git checkout -b feature/my-feature

# 2. 在分支上开发，频繁小步提交
git commit -m "feat(scope): 做了什么"

# 3. 开发完成，确保构建通过
npm run build

# 4. 切回 develop 合并（或发起 PR）
git checkout develop
git pull origin develop
git merge feature/my-feature

# 5. 删除已合并的功能分支
git branch -d feature/my-feature
```

### 合并前检查清单

- [ ] `npm run build` 通过（tsc + vite build）
- [ ] 功能在浏览器中手动验证通过
- [ ] 无 console 报错
- [ ] 如果是 UI 改动，暗色/亮色主题均正常

---

## 📋 开发计划动态维护

**`DEVELOPMENT_PLAN.md` 是本项目的唯一权威计划文档。开发过程中必须同步维护。**

### 何时更新计划书

| 时机 | 更新内容 |
|------|----------|
| **开始一个 Sprint** | 将对应任务标记为 `🚀 进行中` |
| **完成一个 Sprint** | 标记为 `✅ 已完成`，记录实际完成日期 |
| **需求变更** | 更新对应章节，在 `11.1 风险清单` 或新增条目记录变更原因 |
| **技术决策变更** | 更新 `5. 技术架构方案` 对应内容 |
| **新增/删除功能** | 更新 `3. 核心功能规划` 功能全景图 |
| **遇到阻塞问题** | 更新 `11.1 风险清单`，标记风险等级和缓解措施 |
| **版本发布** | 在计划书顶部更新版本号和状态 |

### 维护原则

1. **计划书是活文档** — 不是写完就冻结的，随项目演进而更新
2. **先改计划再写代码** — 避免计划与实现脱节
3. **每次提交如果影响了项目方向/范围/进度，同步更新计划书对应的行**
4. **版本号跟着实际进度走** — 不要出现"计划 v0.2 但实际已经做了 v0.3 的内容"

---

## 开发规则

1. **组件单一职责**: 每个组件只做一件事。日历网格负责渲染，不负责加载数据。
2. **Props 优先**: 数据通过 props 传入，不在组件内部直接 import 数据文件。
3. **状态上提**: 共享状态提升到 App.tsx 或通过 Context 管理。
4. **常量集中**: 日期格式化、颜色映射等常量在 `src/lib/constants.ts` 中定义。
5. **一个组件一个文件**: 同目录放对应的 `*.test.tsx`（待引入测试）。
6. **使用 Conventional Commits**: `feat(scope):`, `fix(scope):`, `refactor(scope):` 等。

## 设计规则

1. 游戏品牌色定义在 `src/index.css` 的 CSS 自定义属性（`--color-genshin` 等）
2. 暗色/亮色主题通过 `.dark` class 切换 CSS 变量
3. 日历组件使用 CSS Grid 布局
4. 不引入第三方 UI 组件库，使用 Tailwind 原生 class + 自定义 CSS 变量

## 数据规则

1. 活动数据文件位于 `data/events/`，按游戏分文件（`genshin-impact.yaml` 等）
2. 每个活动条目必须符合 `src/types/events.ts` 中定义的 Zod Schema
3. 添加/修改数据后，确保 `EventDataFileSchema` 校验通过
4. 日期统一使用 `YYYY-MM-DD` 格式

## 常用命令

```bash
npm run dev          # 启动开发服务器
npm run build        # 生产构建（tsc + vite build）
npm run lint         # 代码检查
npm run preview      # 预览生产构建
```
