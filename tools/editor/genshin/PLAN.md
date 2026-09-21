# 原神自动化维护 — 现状与待办

> 原神管线的方案**已经落地并跑通**，不存在待批准的方案。本文件记录现状、本轮结构调整、
> 以及未决项。提取规则见 [RULES.md](RULES.md)，项目级计划见
> [DEVELOPMENT_PLAN.md](../../DEVELOPMENT_PLAN.md) §6.3。

## 1. 现状

管线：米游社公告 + B站动态 → 分类/解析 → 推理补日期 → 合并 → 落盘。

```
common/extractor.py     米游社抓取 + 按标题分类 + 正文解析
common/bilibili.py      B站动态抓取 + 解析 + 与米游社结果合并
genshin/inference.py    周期性事件推理（深境螺旋 / 幻想真境剧诗 / 版本更新 / 前瞻 / 卡池）
genshin/pipeline.py     驱动整条管线 → genshin/extracted_full.json
common/apply_events.py  只新增，绝不改已有条目
common/calibrate.py     只改已有条目的值，绝不新增
```

两条职责互不干涉是整套自动化鲁棒性的基础：**新增只增不改、校准只改不增**，
判定都走同一个 `keys.event_key`（身份，与日期无关）。因此不需要状态文件，
也不存在与人工编辑的写冲突。

关键设计决策（2026-09-21 定）见 [DEVELOPMENT_PLAN.md](../../DEVELOPMENT_PLAN.md) §6.3，
不在此重复。

## 2. 本轮结构调整（模块搬迁）

为把两条管线分开放，做了纯搬迁 + 提参数的改动，**原神侧行为不变**：

| 原路径 | 现路径 |
|---|---|
| `tools/editor/yaml_io.py` | `common/yaml_io.py` |
| `tools/editor/keys.py` | `common/keys.py` |
| `tools/editor/calibrate.py` | `common/calibrate.py` |
| `tools/editor/extractor.py` | `common/extractor.py` |
| `tools/editor/bilibili.py` | `common/bilibili.py` |
| `tools/editor/apply_events.py` | `common/apply_events.py` |
| `tools/editor/run_pipeline.py` | `genshin/pipeline.py` |
| `tools/editor/inference.py` | `genshin/inference.py` |
| `tools/editor/EXTRACTION_RULES.md` | `genshin/RULES.md` |
| `tools/editor/extracted_full.json` | `genshin/extracted_full.json` |
| （`run_pipeline.pastel_from_url`） | `common/colors.py`（抽出来给两条管线共用） |

随之的**加法式**改动（不改变原神侧行为）：

- `common/apply_events.py`：`auto_id(...)` / `main(...)` 加 `game_id` 参数，
  产物文件名由调用方传入（原来是写死 `extracted_full.json`）
- `common/calibrate.py`：`sources_from(..., game_name="原神")`，只把写死的游戏名提成参数
- `common/yaml_io.py`：抽出 `GAME_ID_PREFIX` / `GAME_URL_PATH`
- `maintain.py`：改成循环跑两个游戏，各自 try 住（一个出问题不拖累另一个）

## 3. 待办

来自 [RULES.md](RULES.md)，都已确认过处置，不是待定项：

- **三段式复合活动**（`「虹旅藏金·耀星烁熠」` 这类）：正文没有 `〓活动时间〓`，而是
  `〓 子活动名 〓`（标记内带空格）分段，各段各写一行时间。**已确认处置：不加解析分支，
  由人工在编辑器 `main.py` 里手动补录**。会走日期闸丢弃，日志里以 `x` 报出。
- **正文按 `post_id` 本地缓存**：预筛已消掉稳态下的重复抓取，缓存的价值降到
  「同一天内多次运行不重复抓新条目」，优先级低。

## 4. 回归测试结果（2026-09-21，已跑）

模块搬迁后跑了 `python maintain.py` 两轮，全部联网。

| # | 检查项 | 结果 |
|---|---|---|
| 1 | 原神侧输出与搬迁前**逐行一致** | ✅ `data/events/genshin-impact.yaml` **md5 前后完全相同**（`8a6a2aad…`），50 条不变。搬迁动了 `common/` 全部模块的 import 与路径（`PROJECT_ROOT` 从 `parent.parent.parent` 改成 `parents[3]`、产物路径改绝对），这是「行为不变」的运行时证据 |
| 2 | 双游戏入口两节都正常 | ✅ 日志里 `--- 原神 ---` / `--- 崩坏：星穹铁道 ---` 两节齐全，各自 try 住 |
| 3 | 抓取无风控 | ✅ 两轮共 4 次列表 + 20 次正文，**失败 0、风控 0** |
| 4 | 星铁新条目落盘 | ✅ 4 条（22 → 26 条），其中 `「火花（欢愉•火）」「丹恒•腾荒（存护•物理）」「长夜月（记忆•冰）」跃迁` 是**原先手工录入漏掉的一期卡池** |
| 5 | 幂等 | ⚠️ 达成「0 新增」，但**不是字节级不变**：第二轮多打了一个 `calibrated` 标记。原因是 `calibrate` 在同一次运行里排在 `apply_events` 之前，新加的条目要等下一轮才被校准。这是设计使然、会收敛（标记一次性），措辞已在 [RULES.md](RULES.md) §6.4 更正 |
| 6 | `npm run build` | ✅ 通过（tsc + vite，117 modules，1.64s），星铁 chunk 正常产出 |
| 7 | 浏览器确认星铁日历，暗色/亮色各看一遍 | ✅ 渲染正常，4.5 内容与版本更新说明一致 |
| 8 | 点一条 `source_url` 确认 `/sr/` 路径 | ✅ 打开即星铁 4.5 版本更新说明（`/sr/article/…`） |

> **本次调整的全部检查项已通过**：第 1 项是搬迁的关键运行时证据，7、8 两项是产品/链接的人工确认。

## 5. 回归底线（改动 `common/` 后按这个判）

1. `python maintain.py` 跑双游戏，检查 `logs/YYYY-MM-DD.log` 里原神侧输出与改动前**逐行一致**
2. `npm run build`（数据文件结构变了才需要）
3. 幂等：连跑两次，第二次必须 **0 新增**；新条目被校准会滞后一轮，见 §4 第 5 项
