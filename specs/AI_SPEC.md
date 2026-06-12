# AI 规格：LLM 参与方式

## 1. 基本原则

LLM 是分析助手，不是预测核心。它不能直接覆盖本地模型的概率结果，也不能在没有来源的情况下编造事实。

未配置 LLM 时，应用仍应能依靠本地历史数据和统计模型完成基础预测。

配置 LLM 后，LLM 负责增强用户体验：

- 生成球队介绍。
- 辅助更新比赛进程和比分。
- 从权威来源提取 AI 信息因子。
- 解释模型结果和概率变化。
- 生成面向普通读者的预测报告。

本地模型输出概率，LLM 输出解释、结构化信息和待确认更新；LLM 不直接决定最终概率。

## 2. API 兼容性

MVP 支持 OpenAI 兼容接口：

- `base_url`
- `api_key`
- `model`
- `temperature`

默认请求形态参考 Chat Completions：

```json
{
  "model": "user-configured-model",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "temperature": 0.2
}
```

如果后续实现改用 Responses API，需要在设置页标注模式。

## 3. AI 调用场景

### 3.1 测试连接

目的：

- 验证 API Key、Base URL、模型名可用。

输入：

- 一个极短测试提示。

输出：

- 成功/失败。
- 错误原因。

### 3.2 信息源摘要

目的：

- 把用户指定的信息源内容压缩成普通用户可读摘要。

输入：

- URL
- 来源类型
- 抓取到的正文或用户粘贴文本

输出 JSON：

```json
{
  "source_title": "string",
  "source_type": "weather|injury|lineup|news|other",
  "summary": "string",
  "relevant_matches": ["Team A vs Team B"],
  "key_points": ["string"],
  "confidence": 0.0,
  "warnings": ["string"]
}
```

### 3.3 影响因子提取

目的：

- 把非结构化信息转成可展示、可审查、可用于解释的结构化因素。

输出 JSON：

```json
{
  "factors": [
    {
      "team": "string",
      "match": "string|null",
      "category": "weather|injury|lineup|fatigue|travel|form|other",
      "direction": "positive|negative|neutral",
      "severity": "low|medium|high",
      "confidence": 0.0,
      "evidence": "string",
      "source_url": "string"
    }
  ]
}
```

MVP 中这些因素会通过固定规则转成有限 Elo 调整。LLM 不直接输出概率，也不能覆盖本地模拟结果。

### 3.4 AI 辅助比分录入（后续）

目的：

- 减少用户逐场手动输入比分的负担。
- 从用户粘贴的赛果文本，或用户指定的权威赛果 URL 中提取已结束比赛比分。

输入：

- 正式分组和赛程中的比赛列表。
- 用户粘贴的赛果文本，或后端抓取到的赛果网页正文。

输出 JSON：

```json
{
  "matches": [
    {
      "home_team": "string",
      "away_team": "string",
      "home_score": 0,
      "away_score": 0,
      "confidence": 0.0,
      "evidence": "string",
      "source_url": "string|null"
    }
  ],
  "warnings": ["string"]
}
```

约束：

- LLM 只能生成“待确认比分”，不能直接写入 `matches.json`。
- 系统必须用正式赛程校验球队和比赛是否匹配。
- 已存在比分与新识别比分冲突时，必须提示用户选择是否覆盖。
- 低置信度或无法匹配的结果必须进入人工确认状态。

### 3.5 预测报告生成

目的：

- 把概率表、比分更新和影响因子写成普通读者能理解的报告。

输入：

- Top 概率表
- 与上次预测相比的变化
- 已结束比分
- 用户确认过的影响因子
- 模型参数摘要

输出：

- `headline`
- `summary`
- `top_contenders`
- `biggest_movers`
- `uncertainties`
- `data_notes`

## 4. Prompt 规则

系统提示必须包含：

- 不要编造来源没有的信息。
- 不要给博彩建议。
- 不要把概率描述成确定结果。
- 不要声称自己实时知道事实，除非来自用户提供的信息源。
- 输出必须是指定 JSON 格式。

报告提示必须要求：

- 面向普通球迷。
- 解释“为什么概率变化”。
- 明确哪些结论来自模型，哪些来自外部信息源。
- 保留不确定性。

## 5. 失败兜底

LLM 失败时：

- 预测模型仍然可运行。
- 页面显示“AI 解读暂不可用”。
- 用户仍可查看图表。
- 失败原因写入本地日志。

LLM 输出 JSON 解析失败时：

- 尝试一次修复请求。
- 仍失败则显示原始文本摘要，但不进入结构化影响因子。

URL 抓取失败时：

- 允许用户手动粘贴正文。

## 6. 安全与隐私

- API Key 默认只保存在当前会话，不写入导出报告。
- 默认不上传历史比赛数据全文给 LLM。
- 只把必要摘要、Top 结果和用户指定来源发送给 LLM。
- 页面提醒用户不要粘贴敏感个人信息。
- 导出报告不包含 API Key。

## 7. MVP 中 AI 对预测的影响

MVP 默认策略：

- LLM 不直接修改概率。
- LLM 提取的因素会通过固定规则转成有限范围的 Elo 调整，再进入本地模拟。
- 调整规则由系统执行，不允许 LLM 直接输出最终概率或覆盖模拟结果。
- 单队 AI 因素总调整限制在 `-60` 到 `+60` Elo。
- 每个 AI 调整都必须显示来源和置信度。

这样可以保持产品可信：AI 参与了，但不会变成黑箱预言机。
