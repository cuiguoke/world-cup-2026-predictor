# 国际比赛历史数据来源

- 文件：`data/results.csv`
- 来源仓库：`martj42/international_results`
- 原始文件：`https://raw.githubusercontent.com/martj42/international_results/master/results.csv`
- 许可证：CC0-1.0
- 下载时间：2026-06-12

该数据集包含男子国家队正式国际比赛结果，字段为：

```text
date,home_team,away_team,home_score,away_score,tournament,city,country,neutral
```

应用会优先使用 `data/results.csv` 进行 Elo 计算；如果该文件不存在，则回退到 `data/sample_results.csv`。
