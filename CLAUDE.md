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
npm run build        # 生产构建
npm run lint         # 代码检查
npm run preview      # 预览生产构建
```

## 分支策略

- `main` — 生产分支
- `develop` — 开发主分支
- `feature/<name>` — 功能分支
- 合并前需通过 lint + build 检查
