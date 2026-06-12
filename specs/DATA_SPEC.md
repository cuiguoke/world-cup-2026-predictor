# 数据规格

## 1. 本地数据目录

建议结构：

```text
app_data/
  config.json
  groups_2026.json
  matches.json
  results_history.csv
  sources.json
  factors.json
  predictions/
    2026-06-11T120000.json
  reports/
    2026-06-11T120000.html
```

## 2. 配置数据

`config.json`

```json
{
  "llm": {
    "base_url": "https://api.example.com/v1",
    "api_key_storage": "session",
    "model": "gpt-4.1-mini-compatible",
    "temperature": 0.2
  },
  "model": {
    "simulations": 50000,
    "home_advantage": 60,
    "host_boost": 80,
    "half_life_years": 6,
    "goal_elo_scale": 650,
    "allow_ai_rating_adjustments": false
  }
}
```

MVP 默认不把 API Key 写入磁盘，只保存在当前浏览器会话或本地服务内存中。后续可以增加“记住 API Key”选项，但必须显式提示风险。

## 3. 分组数据

`groups_2026.json`

```json
{
  "A": ["Mexico", "South Africa", "South Korea", "Czech Republic"],
  "B": ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"]
}
```

约束：

- 必须包含 A-L 共 12 个小组。
- 每组必须 4 支球队。
- 球队名称用于匹配历史数据和页面展示。

## 4. 比赛状态数据

`matches.json`

```json
{
  "matches": [
    {
      "id": "A-1",
      "group": "A",
      "home_team": "Mexico",
      "away_team": "South Africa",
      "home_score": 2,
      "away_score": 1,
      "status": "finished",
      "date": "2026-06-11",
      "source": "user"
    }
  ]
}
```

`status` 可选：

- `scheduled`
- `finished`

MVP 不需要完整场馆和开球时间，但结构允许后续添加。

## 5. 信息源数据

`sources.json`

```json
{
  "sources": [
    {
      "id": "src_001",
      "url": "https://example.com/weather",
      "type": "weather",
      "title": "Weather forecast",
      "fetch_status": "success",
      "added_at": "2026-06-11T12:00:00",
      "raw_text_path": "sources/src_001.txt",
      "user_notes": "Mexico opening match weather"
    }
  ]
}
```

`type` 可选：

- `weather`
- `injury`
- `lineup`
- `news`
- `other`

## 6. AI 影响因子数据

`factors.json`

```json
{
  "factors": [
    {
      "id": "factor_001",
      "source_id": "src_001",
      "team": "Mexico",
      "match": "Mexico vs South Africa",
      "category": "weather",
      "direction": "negative",
      "severity": "medium",
      "confidence": 0.72,
      "evidence": "High temperature may reduce pressing intensity.",
      "approved_by_user": true,
      "rating_adjustment": -10
    }
  ]
}
```

约束：

- `approved_by_user=false` 的因素不能进入模型调整。
- `rating_adjustment` 默认 `0`。
- MVP 中调整范围建议限制在 `-30` 到 `+30`。

## 7. 预测结果数据

`predictions/*.json`

```json
{
  "id": "pred_20260611_120000",
  "created_at": "2026-06-11T12:00:00",
  "input_hash": "string",
  "model_params": {
    "simulations": 50000,
    "host_boost": 80
  },
  "rows": [
    {
      "team": "Spain",
      "champion": 0.28,
      "final": 0.45,
      "sf": 0.62,
      "qf": 0.78,
      "r16": 0.91,
      "r32": 0.98
    }
  ],
  "changes": [
    {
      "team": "Spain",
      "metric": "champion",
      "previous": 0.25,
      "current": 0.28,
      "delta": 0.03
    }
  ],
  "warnings": ["string"]
}
```

页面展示时必须转换字段名：

- `champion` -> 夺冠
- `final` -> 进决赛
- `sf` -> 进四强
- `qf` -> 进八强
- `r16` -> 进16强
- `r32` -> 进32强

## 8. 报告数据

报告 HTML 应包含：

- 图表。
- 预测摘要。
- AI 解读。
- 已使用的信息源。
- 模型参数摘要。
- 不确定性说明。

报告不得包含：

- API Key。
- 用户未确认的 AI 因素。
- 未标注来源的事实性结论。
