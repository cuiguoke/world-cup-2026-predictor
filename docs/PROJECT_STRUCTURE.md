# 项目结构说明

本文档说明当前代码结构、主要模块职责和运行时调用关系。README 保持面向使用者，这里面向后续开发和拆分维护。

## 顶层结构

```text
.
├── app.py
├── app_config.py
├── storage.py
├── worldcup_simulator.py
├── visualize_predictions.py
├── services/
├── web/
├── data/
├── app_data/
├── specs/
└── docs/
```

## 核心入口

### `app.py`

本地 Web App 入口。当前职责已经收敛为：

- 启动 `ThreadingHTTPServer`。
- 提供静态页面和静态报告文件。
- 暴露 `/api/*` JSON 接口。
- 将预测、赛程、信息源、报告生成等具体逻辑委托给 `services/`。

`app.py` 不再直接承载预测模型、LLM 请求、赛程生成或报告渲染逻辑。

### `worldcup_simulator.py`

底层世界杯模拟引擎，也可以作为命令行工具单独运行。主要职责：

- 读取历史国际比赛结果。
- 构建 Elo 评分。
- 估计基础进球均值。
- 用 Poisson 分布模拟比分。
- 模拟小组赛、32 强到决赛的完整赛事路径。
- 汇总各队进入不同阶段和夺冠的概率。

Web App 通过 `services/prediction.py` 调用这里的模型函数；命令行可以直接运行该文件导出 CSV 和 meta JSON。

### `visualize_predictions.py`

离线可视化工具。它读取 `worldcup_simulator.py` 导出的 CSV，并生成 HTML 或 SVG 图表。它不参与 Web App 的实时 API。

## 配置和基础设施

### `app_config.py`

集中定义路径和赛事常量，包括：

- 项目根目录、Web 目录、数据目录、运行时数据目录。
- 分组、中文队名、赛程、比分、信息源、报告等文件路径。
- 淘汰赛签位、显示时间等赛事结构配置。

### `storage.py`

基础 JSON 读写和应用日志工具。服务层通过这里读写 `app_data/` 下的运行时状态。

## 服务层

`services/` 是 Web App 的业务服务层。目标是让 `app.py` 只做 HTTP 协调，每个服务模块负责一类业务。

```text
services/
├── __init__.py
├── llm.py
├── prediction.py
├── report.py
├── schedule.py
├── sources.py
└── teams.py
```

### `services/schedule.py`

负责赛程和比分状态：

- 从 `data/match_schedule_2026.json` 读取默认赛程。
- 生成 104 场比赛记录。
- 读取官方确认赛果，并标记比分来源和是否可编辑。
- 读取或保存 `app_data/matches.json` 中的用户本地覆盖比分。
- 规范化用户保存的比分覆盖项。
- 将已完赛比分转换为预测模型可用的固定小组赛比分。

### `services/teams.py`

负责球队名称和本地化：

- 读取中文队名映射。
- 将英文模型队名转换为中文展示名。
- 本地化分组、比赛、预测结果。
- 在 AI 因子和模型队名之间做轻量映射。

### `services/llm.py`

负责 OpenAI 兼容 Chat Completions 客户端：

- 保存当前进程内的 LLM 配置。
- 测试 API 连接。
- 处理常见 HTTP、URL、SSL 错误。
- 发起 JSON 格式 LLM 请求。

### `services/sources.py`

负责 AI 信息源和影响因子：

- 读取、创建、删除信息源。
- 抓取 URL 或保存手动正文。
- 调用 LLM 提取结构化影响因子。
- 将影响因子转换为有限的 Elo 调整。

### `services/prediction.py`

Web App 的预测服务。它连接运行时状态和底层模型：

- 读取分组、历史数据、已保存比分。
- 调用 `worldcup_simulator.py` 构建 Elo 和模拟赛事。
- 应用 AI 影响因子的 Elo 微调。
- 汇总夺冠概率、阶段概率和小组出线概率。
- 成功预测后调用 `services/snapshots.py` 保存当前预测快照。
- 返回已中文本地化的预测结果。

### `services/snapshots.py`

负责预测快照持久化：

- 将每次成功预测写入带模型版本的快照文件，例如 `app_data/snapshots/20260615T143041117683-v1.json`；当前模型版本为 `v1`。
- 快照文件用独立 JSON 保存，已保存内容不再修改。
- 按 `SNAPSHOT_MAX_FILES` 和 `SNAPSHOT_MAX_TOTAL_MB` 清理最旧快照，避免本地磁盘无限增长。
- 提供快照列表和单个快照读取能力，为后续预测复盘页面提供数据。

### `services/report.py`

负责报告生成：

- 根据预测结果生成摘要文字。
- 在配置 LLM 时请求 AI 解读；未配置时使用本地 fallback 文案。
- 渲染 HTML 报告。
- 将报告写入 `app_data/reports/`。

## 前端目录

```text
web/
├── index.html
├── app.js
└── styles.css
```

前端是一个本地单页应用，直接调用 `app.py` 提供的 JSON API。主要页面能力包括：

- 分组与出线查看。
- 赛事进程查看。
- 比分录入。`APP_MODE=local` 时可录入未确认比分，`APP_MODE=hosted` 时隐藏手动录入入口。
- 预测结果展示。
- LLM 配置。
- 信息源管理。
- AI 影响因子查看。
- HTML 报告导出。

## 数据目录

### `data/`

项目输入数据，应该尽量保持可审查、可复现：

- `results.csv`：完整国际比赛历史数据。
- `sample_results.csv`：样例历史数据。
- `groups_2026.json`：2026 世界杯分组。
- `sample_groups_2026.json`：样例分组。
- `team_names_zh.json`：中文队名映射。
- `match_schedule_2026.json`：世界杯赛程、北京时间、已知比分和来源标记。
- `third_place_assignments_2026.json`：32 强阶段 8 个最佳小组第三名的 495 种组合落位表。
- `results_source.md`：历史数据来源说明。

### `app_data/`

本地运行时数据，来自用户操作或应用生成：

- `matches.json`：用户本地覆盖比分，只保存可编辑的手动录入结果；官方确认赛果来自 `data/match_schedule_2026.json`。
- `sources.json`：用户添加的信息源。
- `factors.json`：AI 提取后的影响因子。
- `snapshots/`：每次成功重新预测后保存的不可变预测快照，文件名包含模型版本，例如 `20260615T143041117683-v1.json`；默认保留最近 200 个且总占用不超过 50 MB，超过后删除最旧快照。
- `reports/`：导出的 HTML 报告。

## 调用链

### 网页预测

```text
浏览器
  -> POST /api/predict
  -> app.py
  -> services/prediction.py
  -> services/schedule.py
  -> services/sources.py
  -> worldcup_simulator.py
  -> services/teams.py
  -> JSON 响应
```

### 报告生成

```text
浏览器
  -> POST /api/report/generate
  -> app.py
  -> services/report.py
  -> services/prediction.py
  -> services/llm.py
  -> app_data/reports/*.html
```

### 信息源提取

```text
浏览器
  -> POST /api/sources/{id}/extract
  -> app.py
  -> services/sources.py
  -> services/llm.py
  -> app_data/factors.json
```

### 命令行预测

```text
python3 worldcup_simulator.py
  -> data/results.csv
  -> data/groups_2026.json
  -> outputs/*.csv
  -> outputs/*.json
```

### 离线可视化

```text
python3 visualize_predictions.py
  -> outputs/worldcup_2026_probs.csv
  -> outputs/*.html 或 outputs/*.svg
```

## 后续拆分方向

当前 `app.py` 已经明显变薄，后续更值得处理的是预测引擎内部结构：

```text
model/
├── data.py
├── elo.py
├── scoring.py
├── tournament.py
└── cli.py
```

可能的拆分顺序：

1. 从 `worldcup_simulator.py` 抽出 Elo 相关函数。
2. 抽出比分模拟和 Poisson 工具。
3. 抽出世界杯赛制、签位和淘汰赛推进。
4. 保留一个薄的 CLI 入口。
5. 为模型核心增加单元测试，锁定拆分前后的预测行为。
