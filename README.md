# 2026 世界杯 AI 预测助手

这是一个本地运行的 2026 世界杯预测应用。它的目标不是给出“唯一正确答案”，而是把历史数据、比分进展、人工输入的信息源和 LLM 解读组织在一起，让普通读者可以用更直观的方式观察世界杯走势。

当前版本是一个已经跑通的概念原型：

- 不配置 LLM 时，应用会根据完整国际比赛历史数据、2026 世界杯分组、已录入比分和本地统计模型生成预测。
- 配置 LLM 后，应用可以测试 OpenAI 兼容 API、读取用户添加的信息源、提取影响因子，并生成带 AI 解读的 HTML 报告。
- 当前仍是本地单用户版本，赛程浏览、球队介绍、AI 辅助比分录入、网站化部署和多用户隔离还在 TODO 中。

## 快速开始

在项目目录运行：

```bash
python3 app.py
```

启动后打开：

```text
http://127.0.0.1:8765
```

macOS 用户也可以双击 `start.command`，Windows 用户可以运行 `start.bat`。

## 当前网页能力

本地网页已经支持：

- 查看 2026 世界杯分组。
- 录入小组赛已结束比分，并保存到本地运行目录。
- 设置模拟次数，重新运行预测。
- 用中文队名展示夺冠概率排行和阶段概率表。
- 配置 OpenAI 兼容 LLM API，并测试连接。
- 遇到本机 SSL 证书问题时，给出面向普通用户的提示，并提供显式“跳过 SSL 证书验证”选项。
- 添加 AI 信息源，支持 URL 抓取或手动粘贴正文。
- 调用 LLM 从信息源中提取结构化影响因子。
- 将 AI 影响因子转换为有限的 Elo 微调，再进入下一次本地模拟。
- 导出 HTML 报告，汇总预测结果、已录入比分、信息源、AI 影响因子和 AI 解读。

已实现的后端 API 包括：

```text
/api/status
/api/groups
/api/matches
/api/predict
/api/llm/test
/api/sources
/api/sources/{id}/extract
/api/factors
/api/report/generate
```

## 模型如何工作

当前本地预测模型由三部分组成：Elo 评分、Poisson 进球模拟、Monte Carlo 多次模拟。

### Elo 评分

Elo 可以理解为球队的动态实力分。每支球队从同一个初始分开始，赢球会涨分，输球会降分；爆冷赢球涨得更多，强队赢弱队涨得更少。

当前默认参数：

- 初始 Elo：`1500`
- K 值：`22`
- 非中立场主场优势：`60` 个 Elo 点
- 2026 东道主加成：`80` 个 Elo 点
- 历史比赛半衰期：`6` 年

K 值控制单场比赛对 Elo 的影响幅度。K 值越高，模型越容易被近期单场结果拉动；K 值越低，模型越保守。

### 赛事权重和时间衰减

模型不会把所有比赛看成同样重要：

- 世界杯正赛权重更高。
- 洲际杯赛和世界杯预选赛权重较高。
- 友谊赛权重较低。
- 越近的比赛影响越大，较早的比赛影响会逐步衰减，但不会完全归零。

这样做是为了避免两个极端：只看最近几场导致波动太大，或者把十几年前的比赛看得和近期比赛一样重要。

### 东道主加成

2026 世界杯由美国、加拿大、墨西哥联合举办。当前模型会在世界杯模拟阶段给这三个东道主额外 `80` 个 Elo 点，用来近似主场氛围、旅途适应、气候熟悉度和观众支持。

这个参数不是定论。它会明显影响三支东道主的预测结果，也是后续需要重点复盘的模型假设之一。TODO 中已经记录了“无主场加成、低主场加成、高主场加成”的对照预测需求。

### Poisson 进球模拟

模型会把两队 Elo 差距转换成预期进球数，再用 Poisson 分布模拟比分。简单说：

- 强队的预期进球数更高。
- 弱队仍然可能进球和爆冷。
- 每次模拟都会产生一条可能的世界杯路径。

淘汰赛如果常规时间打平，当前模型会继续模拟加时和胜负结果。

### Monte Carlo 模拟

应用不会只模拟一次，而是重复模拟很多次，然后统计概率。

网页默认模拟次数是 `1000` 次，可在页面中调整。模拟次数的含义：

- `1000` 次：适合快速预览，速度快，但小概率结果会有随机波动。
- `5000` 次：结果更稳定，适合认真比较。
- `10000` 次：更适合导出正式报告，但耗时更长。

模拟次数越高，随机波动越小，但不会让模型本身“更聪明”。它只能让同一套模型假设下的概率估计更稳定。

## AI 在项目中的作用

当前版本里，LLM 不直接预测冠军，也不会直接覆盖概率。它主要做三件事：

1. 检查用户提供的 OpenAI 兼容 API 是否可用。
2. 从用户添加的信息源中提取结构化影响因子，例如伤病、天气、阵容、赛前报道。
3. 为导出的 HTML 报告生成自然语言解读。

LLM 提取出的影响因子会先经过固定规则转换成小幅 Elo 调整，再交给本地模拟模型。因此，最终概率仍由本地模型计算，AI 负责辅助理解和补充上下文。

当前设计刻意保留这条边界：让 LLM 参与信息处理和解释，而不是让它凭空给出一个无法审查的预测数字。

## LLM 配置

应用支持 OpenAI 兼容 Chat Completions 接口。

常见配置示例：

```text
Base URL: https://api.openai.com/v1
模型名: gpt-4.1-mini
```

DeepSeek 示例：

```text
Base URL: https://api.deepseek.com
模型名: deepseek-v4-flash
```

安全说明：

- API Key 默认只保存在当前浏览器会话。
- 后端只在当前本地进程内存中保存测试通过后的配置。
- 停止本地服务或刷新会话后，可能需要重新配置。
- 如果测试连接提示本机无法确认 HTTPS 服务身份，通常是本机 Python CA 证书环境问题；只有在确认 Base URL 来自官方或可信服务时，才建议勾选“跳过 SSL 证书验证”重试。

## 数据来源

### 历史比赛数据

当前仓库内置完整国际比赛历史数据：

```text
data/results.csv
```

数据源：

- 数据集：`martj42/international_results`
- 仓库地址：`https://github.com/martj42/international_results`
- 原始 CSV：`https://raw.githubusercontent.com/martj42/international_results/master/results.csv`
- 许可证：CC0-1.0
- 本地备注：`data/results_source.md`

数据字段兼容：

```text
date,home_team,away_team,home_score,away_score,tournament,city,country,neutral
```

截至当前版本，`data/results.csv` 包含 49,477 行国际比赛结果。应用会优先使用该文件；如果不存在，才回退到 `data/sample_results.csv`。

### 世界杯分组

世界杯分组保存在：

```text
data/groups_2026.json
```

这个文件被设计成外部输入。后续如果 FIFA 赛程、分组、队名写法或参赛队信息发生变化，只需要更新 JSON 和对应中文名映射，不需要改模拟代码。

中文队名映射保存在：

```text
data/team_names_zh.json
```

## 命令行用法

除了本地网页，也可以直接运行命令行预测：

```bash
python3 worldcup_ai_repro.py \
  --results data/results.csv \
  --groups data/groups_2026.json \
  --simulations 1000 \
  --output ../../outputs/worldcup_2026_probs.csv \
  --meta-output ../../outputs/worldcup_2026_meta.json
```

如果需要拉取历史数据源的最新版本：

```bash
python3 worldcup_ai_repro.py \
  --download \
  --results data/results.csv \
  --groups data/groups_2026.json \
  --simulations 50000 \
  --output ../../outputs/worldcup_2026_probs.csv \
  --meta-output ../../outputs/worldcup_2026_meta.json
```

## 生成图形化报告

`worldcup_ai_repro.py` 输出的 CSV 适合程序分析，但 `sf`、`qf`、`r16`、`r32` 这类字段对普通读者不友好。可以用 `visualize_predictions.py` 转成 HTML 或 SVG。

生成 HTML：

```bash
python3 visualize_predictions.py \
  --input ../../outputs/worldcup_2026_probs.csv \
  --output ../../outputs/worldcup_2026_probs.html \
  --top 16
```

生成 SVG：

```bash
python3 visualize_predictions.py \
  --input ../../outputs/worldcup_2026_probs.csv \
  --output ../../outputs/worldcup_2026_probs.svg \
  --top 16
```

字段中文含义：

- `champion`：夺冠
- `final`：进决赛
- `sf`：进四强
- `qf`：进八强
- `r16`：进 16 强
- `r32`：进 32 强

## 当前局限

这个项目现在仍是概念原型，主要限制包括：

- 还没有赛程表视图，不能直接浏览最近几天赛程和已完赛结果。
- 还没有 AI 辅助比分录入，用户仍需手动填写比分。
- 还没有球队介绍、最近历史战绩、当家明星和球员身价信息。
- 还没有小组赛出线预测和按比赛阶段组织的预测卡片。
- 32 强淘汰赛使用公开签位结构，并用确定性的贪心方式分配成绩最好的小组第三名，后续应替换为更贴近官方竞赛操作的规则。
- 模型没有纳入最终名单、伤病、休息天数、旅途消耗、战术克制、博彩公司赔率或球员级别实力。
- 东道主加成、K 值、赛事权重和时间衰减仍需要通过历史回测进一步讨论。
- 当前状态存储适合本地单用户，不适合直接公开部署给多用户使用。

这些限制不是被忘掉了，而是已经纳入 `specs/TODO.md` 追踪。后续 README 更新时也应同步更新 TODO，避免产品边界和开发计划脱节。

## 后续路线

优先级较高的后续工作：

1. 展示已添加信息源正文，提升 AI 影响因子的可审查性。
2. 完善模拟次数说明和报告提示。
3. 增加赛程表、近期赛程和已完赛结果浏览。
4. 系统复盘本地预测模型，特别是东道主加成和 Elo 参数。
5. 增加小组赛出线预测。
6. 按比赛阶段组织预测卡片。
7. 增加 AI 辅助比分录入。
8. 生成世界杯参赛队伍介绍。
9. 设计网站化部署、多用户隔离和默认免费 LLM 方案。

完整清单见：

```text
specs/TODO.md
```

## 项目文档

继续迭代前，请先阅读项目规则和规格文档：

- `PROJECT_RULES.md`：项目协作规则。
- `DEVELOPMENT.md`：本地开发流程和分支策略。
- `CHANGELOG.md`：当前状态和更新记录。
- `specs/PRODUCT_SPEC.md`：产品定位和 MVP 范围。
- `specs/UX_SPEC.md`：本地网页体验。
- `specs/AI_SPEC.md`：LLM 参与方式。
- `specs/DATA_SPEC.md`：本地数据结构。
- `specs/IMPLEMENTATION_PLAN.md`：实现阶段和验收标准。
- `specs/TODO.md`：后续产品迭代清单。

本项目按 SDD 方式推进：先设计和讨论，再形成文档，最后进行实现。涉及用户可见功能变化时，应同步更新 README 和 TODO。
