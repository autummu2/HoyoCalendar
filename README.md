# HoyoCalendar

一站式查看米哈游游戏活动日程的 Web 日历工具。

## 支持游戏

- 原神 (Genshin Impact)
- 崩坏：星穹铁道 (Honkai: Star Rail)
- 绝区零 (Zenless Zone Zero)

## 功能

- 📅 **月视图日历** — 一眼看清所有游戏活动时间
- 🎨 **游戏品牌色区分** — 不同游戏用不同颜色标识
- 🔍 **点击查看详情** — 点击任意日期查看当天活动
- 🌙 **暗色/亮色主题** — 默认跟随系统

## 本地开发

```bash
npm install
npm run dev      # 启动开发服务器
npm run build    # 构建生产版本
npm run lint     # 代码检查
```

## 技术栈

React 19 + TypeScript + Vite 8 + Tailwind CSS 4 + Zod 4

## 项目结构

```
HoyoCalendar/
├── src/              # 前端源码
├── data/events/      # 活动数据（YAML）
├── public/           # 静态资源
└── DEVELOPMENT_PLAN.md  # 详细开发计划书
```

## 许可证

MIT
