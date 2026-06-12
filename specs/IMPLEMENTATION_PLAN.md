# MVP 实现计划

## 1. 技术选型建议

为了降低用户本地运行难度，MVP 推荐：

- 后端：Python `FastAPI` 或标准库 `http.server` + 简单路由。
- 前端：单页 HTML/CSS/JavaScript，不引入复杂构建系统。
- 图表：先复用当前 SVG 生成逻辑，后续可换成 ECharts。
- 存储：本地 JSON 文件。
- 打包：压缩包 + 启动脚本。

如果优先追求界面体验，可用 Vite + React；但这会引入 Node 依赖。MVP 第一版建议少依赖，先跑通产品闭环。

## 2. 架构

```text
browser
  -> local web app
  -> local Python API
      -> prediction engine
      -> local JSON storage
      -> LLM client
      -> report renderer
```

## 3. 阶段拆分

### Phase 1：产品骨架

交付：

- 本地服务启动脚本。
- 单页网页。
- 顶部状态栏。
- 设置页。
- 能读取 `groups_2026.json`。

验收：

- 用户本地运行后能打开网页。
- 页面能显示正式分组。

### Phase 2：比分录入与本地预测

交付：

- 比分录入页面。
- 保存比赛状态到本地 JSON。
- 点击重新预测。
- 展示可视化概率结果。

验收：

- 修改比分后能重新生成预测。
- 页面展示中文指标。
- 不需要 LLM 也能完成基础预测。

### Phase 3：LLM 配置与连接测试

交付：

- Base URL、API Key、模型名配置。
- 测试连接。
- 本地保存配置。
- 错误提示。

验收：

- OpenAI 兼容服务可通过测试。
- 配置错误时页面给出可理解提示。

### Phase 4：信息源与 AI 影响因子

交付：

- 用户添加 URL 或粘贴正文。
- LLM 摘要信息源。
- LLM 提取影响因子。
- 用户审核并确认。

验收：

- LLM 输出结构化 JSON。
- 解析失败有兜底。
- 未确认因素不进入报告主结论。

### Phase 5：AI 报告与导出

交付：

- 预测摘要。
- 概率变化解释。
- 不确定性说明。
- 导出 HTML 报告。

验收：

- 报告面向普通读者。
- 报告列出数据来源。
- 报告不包含 API Key。

### Phase 6：AI 辅助比分录入（后续）

交付：

- 比分录入页增加“AI 识别比分”入口。
- 支持用户粘贴赛果文本，或提供权威赛果 URL。
- LLM 输出待确认比分列表。
- 系统用正式赛程匹配球队和比赛。
- 用户确认后写入 `app_data/matches.json` 并触发重新预测。

验收：

- 能从一段文本中识别多场比分。
- 能识别中文队名、英文队名和常见别名。
- 已有比分与新识别比分冲突时提示用户是否覆盖。
- 低置信度或无法匹配的结果不会自动写入。

## 4. MVP API 草案

```text
GET  /api/status
GET  /api/groups
GET  /api/matches
POST /api/matches
POST /api/predict
GET  /api/predictions/latest
POST /api/llm/test
POST /api/sources
POST /api/sources/{id}/extract
POST /api/reports/export
```

## 5. 前端页面组件

- `StatusBar`
- `SetupPanel`
- `GroupsView`
- `MatchEditor`
- `PredictionDashboard`
- `SourceManager`
- `FactorReview`
- `ReportView`
- `AdvancedSettings`

## 6. 预测引擎改造

当前 `worldcup_ai_repro.py` 是命令行脚本。MVP 实现时建议拆成：

```text
prediction/
  engine.py
  elo.py
  tournament.py
  report_data.py
```

保留 CLI：

```text
worldcup_ai_repro.py
```

网页后端直接调用 Python 函数，而不是 shell 调命令。

## 7. LLM 客户端

新增：

```text
llm_client.py
```

职责：

- 读取配置。
- 调用 OpenAI 兼容 API。
- 超时处理。
- JSON 解析。
- 一次修复重试。

MVP 默认超时：

- 连接测试：15 秒。
- 摘要/提取：60 秒。
- 报告生成：60 秒。

## 8. 打包交付

压缩包结构建议：

```text
worldcup-ai-predictor/
  start.command
  start.bat
  app/
  data/
  README.md
```

macOS 用户双击 `start.command`。

Windows 用户双击 `start.bat`。

如果 Python 不存在，启动脚本提示安装 Python 3.11+。

## 9. 验收清单

MVP 完成时必须满足：

- 能本地启动网页。
- 能配置 LLM API。
- 能显示正式分组。
- 能录入比分。
- 能生成预测图表。
- 能添加信息源。
- 能调用 LLM 提取影响因子。
- 能生成 AI 解读报告。
- LLM 失败时基础预测可用。
- 能导出 HTML。
- 压缩包中不包含缓存文件、API Key 或本机绝对路径。

## 10. MVP 默认决策

为避免实现阶段反复摇摆，MVP 采用以下默认决策：

1. 前端坚持零构建依赖，使用纯 HTML/CSS/JavaScript。
2. API Key 默认只保存在当前会话，不写入磁盘；后续可增加显式“记住密钥”选项。
3. AI 影响因子通过固定规则转成有限 Elo 调整后进入本地模拟，LLM 不直接输出概率。
4. 本地预测模型始终可在无 LLM 状态下运行。

完成规格评审后即可进入 Phase 1 实现。
