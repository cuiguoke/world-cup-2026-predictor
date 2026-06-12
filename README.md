# 2026 世界杯夺冠预测

这是一个本地运行的 2026 世界杯预测与赛程信息应用。

- 未配置 LLM 时：应用根据完整国际比赛历史数据、正式分组、公开可信赛程/赛果数据、已录入比分和本地统计模型生成预测，并提供近期赛程和已完赛结果浏览。
- 配置 LLM 后：应用升级为 AI 辅助预测助手，支持球队介绍、比赛进程更新、场外资讯关注、AI 信息因子提取与解释报告等能力。

以下是预测的大致流程：

1. 读取男子国家队历史比赛结果。
2. 为每支国家队计算带时间衰减权重的 Elo 评分。
3. 把 Elo 差距转换为预期进球数。
4. 对 48 队世界杯赛制进行多次模拟。
5. 输出各队进入不同阶段的概率，而不是假装只有一条确定的晋级路径。

## 本地网页 MVP

当前工程已经包含一个本地网页应用骨架，面向普通用户使用：

```bash
python3 app.py
```

启动后浏览器会打开类似下面的地址：

```text
http://127.0.0.1:8765
```

macOS 用户也可以双击 `start.command`，Windows 用户可以运行 `start.bat`。

## 项目协作规则

本项目按 SDD 方式推进：先设计和讨论，再形成文档，最后进行实现。详细规则见 `PROJECT_RULES.md`，本地开发和分支流程见 `DEVELOPMENT.md`。

网页 MVP 当前已实现：

- 本地网页服务。
- 顶部状态栏。
- LLM 设置界面占位。
- 2026 世界杯正式分组展示。
- 小组赛比分录入与本地保存。
- 根据已结束比分重新运行预测。
- 在网页中展示夺冠概率排行和阶段概率表。
- OpenAI 兼容 LLM API 配置与连接测试。
- AI 信息源管理：支持 URL 或手动粘贴正文。
- 调用 LLM 从信息源中提取结构化影响因子。
- AI 预测报告生成与 HTML 导出。
- 基础 API：`/api/status`、`/api/groups`、`/api/matches`、`/api/predict`、`/api/llm/test`、`/api/sources`、`/api/factors`、`/api/report/generate`。

核心 MVP 阶段已经完成。后续迭代以 `specs/TODO.md` 中记录的产品能力为准。

LLM 配置说明：

- 支持 OpenAI 兼容 Chat Completions 接口。
- Base URL 示例：`https://api.openai.com/v1`。
- API Key 默认只保存在当前浏览器会话；后端只在当前进程内存中保存测试通过后的配置。
- 停止本地服务或刷新会话后，需要重新配置。

信息源说明：

- 可以填写 URL，也可以直接粘贴正文。
- URL 抓取失败时，页面会提示用户改为粘贴正文。
- LLM 提取到的影响因子会通过固定规则转成小幅 Elo 调整，再进入下一次模拟。
- LLM 不直接输出或覆盖概率，模型调整会在页面和报告中展示。

报告导出说明：

- 在“导出报告”页面点击“生成报告”。
- 系统会运行一次本地预测，并汇总信息源与影响因子。
- 如果 LLM 已配置，会尝试生成 AI 解读；如果没有配置，也会生成基础 HTML 报告。
- 报告保存在本地运行时目录，不包含 API Key。

## 项目主要做了什么

- Elo 初始值为 `1500`。
- 基础 K 值为 `22`。
- 非中立场主场优势为 `60` 个 Elo 点。
- 2026 年三个东道主在赛事模拟中额外获得 `80` 个 Elo 点。
- 比赛更新权重按 `6` 年半衰期衰减，并叠加赛事重要性系数。
- Elo 差距通过 `650` 的 Elo 尺度转换为 Poisson 进球均值。
- 每队基础预期进球数根据输入数据中最近 10 年比赛估计。

这些是默认值，不是唯一正确答案。重点是让假设变得可见、可讨论、可替换。

## 数据

比赛数据文件兼容公开的 `martj42/international_results` 数据集，字段格式如下：

```text
date,home_team,away_team,home_score,away_score,tournament,city,country,neutral
```

数据源备注：

- 数据集：`martj42/international_results`
- 仓库地址：`https://github.com/martj42/international_results`
- 原始 CSV：`https://raw.githubusercontent.com/martj42/international_results/master/results.csv`
- 许可证：CC0-1.0
- 本地文件：`data/results.csv`

当前仓库已内置完整历史数据：

```text
data/results.csv
```

截至本版本，该文件包含 49,477 行国际比赛结果。应用会优先使用 `data/results.csv`；如果该文件不存在，才回退到 `data/sample_results.csv`。

世界杯分组被故意设计成外部输入：

```text
data/groups_2026.json
```

仓库里的 `data/groups_2026.json` 已按 2026 年世界杯正式分组填写。后续如果 FIFA 赛程或队名写法有更新，只需要改这个 JSON 文件，不需要改模拟代码。

## 命令行预测

```bash
python3 worldcup_ai_repro.py \
  --results data/results.csv \
  --groups data/groups_2026.json \
  --simulations 1000 \
  --output ../../outputs/worldcup_2026_probs.csv \
  --meta-output ../../outputs/worldcup_2026_meta.json
```

## 更新历史数据

如果需要拉取数据源的最新版本，可以运行：

```bash
python3 worldcup_ai_repro.py \
  --download \
  --results data/results.csv \
  --groups data/groups_2026.json \
  --simulations 50000 \
  --output ../../outputs/worldcup_2026_probs.csv \
  --meta-output ../../outputs/worldcup_2026_meta.json
```

## 命令行生成图形化结果

`worldcup_ai_repro.py` 输出的 CSV 适合后续分析，但 `sf`、`qf`、`r16`、`r32` 这些字段对普通读者不够友好。可以用 `visualize_predictions.py` 把预测结果转换成 HTML 报告页：

```bash
python3 visualize_predictions.py \
  --input ../../outputs/worldcup_2026_probs.csv \
  --output ../../outputs/worldcup_2026_probs.html \
  --top 16
```

如果只需要一张独立图片，也可以输出 SVG：

```bash
python3 visualize_predictions.py \
  --input ../../outputs/worldcup_2026_probs.csv \
  --output ../../outputs/worldcup_2026_probs.svg \
  --top 16
```

图表会把字段转换成中文：

- `champion`：夺冠
- `final`：进决赛
- `sf`：进四强
- `qf`：进八强
- `r16`：进16强
- `r32`：进32强

如果只是测试样例数据，可以运行：

```bash
python3 visualize_predictions.py \
  --input ../../outputs/worldcup_2026_sample_probs.csv \
  --output ../../outputs/worldcup_2026_sample_probs.html \
  --top 16
```

## 局限与后续改进

32 强淘汰赛使用了公开签位结构，并用确定性的贪心方式分配成绩最好的小组第三名。如果要更贴近官方竞赛操作，可以替换为 FIFA 官方的小组第三名分配表。

这个模型也没有纳入伤病、最终名单、休息天数、旅途消耗、战术克制、博彩公司赔率或球员级别实力。

这是有意保留的简洁基线版本。先把基线跑通，再逐步加入这些因素，才更容易判断每一次升级到底改善了什么。

## 项目规格

如果要继续迭代这个项目，请先阅读 `PROJECT_RULES.md` 和 `specs/` 目录：

- `CHANGELOG.md`：项目当前状态和版本更新记录。
- `specs/PRODUCT_SPEC.md`：产品定位和 MVP 范围。
- `specs/UX_SPEC.md`：本地网页体验。
- `specs/AI_SPEC.md`：LLM 参与方式。
- `specs/DATA_SPEC.md`：本地数据结构。
- `specs/IMPLEMENTATION_PLAN.md`：实现阶段和验收标准。
- `specs/TODO.md`：后续产品迭代清单。
