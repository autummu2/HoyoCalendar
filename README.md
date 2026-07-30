# HoyoCalendar

一站式查看米哈游游戏活动日程的 Web 日历工具。

🌐 **线上地址**: [hoyocalendar-nu.vercel.app](https://hoyocalendar-nu.vercel.app)

## 支持游戏

- 原神 (Genshin Impact)
- 崩坏：星穹铁道 (Honkai: Star Rail)
- 绝区零 (Zenless Zone Zero)

## 功能

- 📅 **月/周/日三视图** — 灵活查看活动分布
- 🎨 **游戏品牌色区分** — 每个活动独立配色
- 🔍 **色条点击查看详情** — 连续色条显示活动名，点击展开详情
- 🏷️ **三态筛选** — 游戏/类型 包含→排除→取消
- ✅ **完成状态标记** — localStorage 持久化
- 🌙 **暗色/亮色主题** — 默认跟随系统
- 🔗 **活动链接** — 点击跳转官方公告

## 数据编辑器（开发者工具）

```bash
# 双击启动
editor.bat

# 或命令行
python tools/editor/gui.py
```

- ✏️ 可视化管理活动数据，直接读写 YAML
- 📥 公告解析：粘贴文本 / 米游社 API / Post ID，自动提取字段
- 🚀 一键推送更新到 GitHub，Vercel 自动部署

## 本地开发

```bash
npm install
npm run dev      # 启动开发服务器
npm run build    # 构建生产版本
npm test         # 运行测试
npm run lint     # 代码检查
```

## 技术栈

React 19 + TypeScript + Vite 8 + Tailwind CSS 4 + Zod 4
Python 3 + tkinter + PyYAML + requests（编辑器）

## 项目结构

```
HoyoCalendar/
├── src/                  # 前端源码 (React)
├── data/events/          # 活动数据 (YAML)
├── tools/editor/         # Python 数据编辑器
├── docs/                 # 文档
├── editor.bat            # 一键启动编辑器
└── DEVELOPMENT_PLAN.md   # 详细开发计划书
```

## 许可证

[GPL v3.0](LICENSE)
