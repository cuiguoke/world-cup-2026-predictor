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
      "stage": "group",
      "match_number": 1,
      "round": 1,
      "date_range": "2026-06-11 至 2026-06-28",
      "display_date": "2026-06-12",
      "display_time": "03:00",
      "home_team": "Mexico",
      "away_team": "South Africa",
      "home_score": 2,
      "away_score": 0,
      "status": "finished",
      "source": "Bing Sports / Wikipedia"
    }
  ]
}
```

`status` 可选：

- `scheduled`
- `finished`

MVP 会为小组赛自动生成 `stage=group` 和 `round`，用于赛事进程视图。当前小组赛精确时间和部分已完赛比分来自 `data/match_schedule_2026.json`。这些已确认赛果属于官方/确定性赛果，不允许普通用户编辑，也不受“清空比分”影响。

`APP_MODE=local` 时，用户保存的未确认比分会作为本地覆盖项写入 `app_data/matches.json` 并参与预测；`APP_MODE=hosted` 时，比分由服务端可信数据源维护，不允许用户手动录入。

当前世界杯赛果维护边界：

- `data/match_schedule_2026.json` 是 2026 世界杯赛程和官方确认赛果的维护入口。
- `data/results.csv` 是历史 Elo 数据集，不随单场世界杯赛果逐场更新。
- 新增已完赛比分时，不应把同一场比赛同时写入 `data/results.csv` 和 `data/match_schedule_2026.json`。
- 只有在明确进行历史数据集版本刷新时，才批量更新 `data/results.csv`，并同步更新 `data/results_source.md`、README 和模型文档中的数据来源说明。

`data/match_schedule_2026.json` 使用本地比赛 ID 作为键，记录外部赛程来源整理后的默认赛程状态：

```json
{
  "A-1": {
    "match_number": 1,
    "display_date": "2026-06-12",
    "display_time": "03:00",
    "home_score": 2,
    "away_score": 0,
    "status": "finished",
    "source": "Bing Sports / Wikipedia"
  }
}
```

字段说明：

- `match_number`：官方场次编号。
- `display_date` / `display_time`：北京时间展示用日期和时间。
- `home_score` / `away_score`：已完赛比分，未完赛时省略。
- `status`：已完赛时为 `finished`，未完赛时可省略并由后端视为 `scheduled`。
- `source`：赛程或比分来源说明。当前小组赛时间和比分参考 Bing 赛事页，并用 Wikipedia 分组赛页面交叉补场次编号。

淘汰赛使用同一个 `matches.json` 结构，但在球队未确定前使用签位字段：

```json
{
  "id": "M73",
  "match_number": 73,
  "stage": "r32",
  "round_name": "32 强",
  "date_range": "2026-06-28 至 2026-07-03",
  "home_slot": "A 组第二",
  "away_slot": "B 组第二",
  "status": "scheduled",
  "source": "schedule"
}
```

淘汰赛阶段可选：

- `r32`
- `r16`
- `qf`
- `sf`
- `third_place`
- `final`

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
  "groupQualification": [
    {
      "group": "A",
      "rows": [
        {
          "team": "Mexico",
          "team_name": "墨西哥",
          "first": 0.42,
          "second": 0.31,
          "third": 0.18,
          "top_two": 0.73,
          "qualified": 0.88
        }
      ]
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
- `groupQualification[].rows[].first` -> 小组头名
- `groupQualification[].rows[].top_two` -> 小组前二
- `groupQualification[].rows[].qualified` -> 晋级 32 强

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
