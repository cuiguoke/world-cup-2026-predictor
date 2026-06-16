# 当前预测模型说明

本文档从数学和实现角度说明当前世界杯预测模型。它对应 `worldcup_simulator.py` 和 `services/prediction.py` 的现有实现，用于帮助后续维护、参数调整和模型复盘。

当前模型不是一个“知道足球”的大模型预测器，而是一个可审查的统计模拟器：

```text
历史比赛数据
  -> Elo 球队评分
  -> Poisson 比分模拟
  -> 小组赛和淘汰赛路径模拟
  -> Monte Carlo 概率汇总
```

LLM 在当前系统中只负责信息源提取和报告解读，不直接生成夺冠概率。

## 1. 输入和输出

### 输入

核心输入包括：

- 历史国际比赛结果：`data/results.csv`
- 世界杯分组：`data/groups_2026.json`
- 小组赛已完赛比分：官方确认赛果来自 `data/match_schedule_2026.json`，用户本地覆盖比分来自 `app_data/matches.json`
- AI 影响因子：`app_data/factors.json`，可选

历史比赛记录包含：

```text
date, home_team, away_team, home_score, away_score, tournament, neutral
```

预测时会设置一个截止日期 `cutoff`，当前 Web App 使用：

```python
cutoff = date(2026, 6, 11)
```

所有 `played_on >= cutoff` 的历史比赛都会被排除，避免使用未来数据。

### 输出

每支球队会得到一组阶段概率：

```text
r32       进入 32 强
r16       进入 16 强
qf        进入 8 强
sf        进入 4 强
final     进入决赛
champion  夺冠
```

Web App 还会额外输出小组名次和小组出线概率：

```text
first      小组第一
second     小组第二
third      小组第三
top_two    小组前二
qualified  小组出线
```

## 2. Elo 评分模型

Elo 是当前模型的球队实力底座。每支球队从同一个初始分开始，历史比赛会按结果逐场更新评分。

默认参数：

```python
initial = 1500.0
k_factor = 22.0
home_advantage = 60.0
half_life_years = 6.0
```

### 2.1 胜率期望

对于球队 A 和球队 B，A 的期望得分为：

```text
E_A = 1 / (1 + 10 ^ (-(R_A - R_B) / 400))
```

其中：

- `R_A` 是 A 的 Elo
- `R_B` 是 B 的 Elo
- `E_A` 接近 1 表示 A 很可能赢
- `E_A` 接近 0.5 表示两队接近
- `E_A` 接近 0 表示 A 明显弱势

对应代码：

```python
def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** (-(rating_a - rating_b) / 400.0))
```

### 2.2 单场实际结果

单场比赛的实际结果记为：

```text
S_home = 1.0   主队胜
S_home = 0.5   平局
S_home = 0.0   主队负
```

对应代码：

```python
def outcome(home_goals: int, away_goals: int) -> float:
    if home_goals > away_goals:
        return 1.0
    if home_goals < away_goals:
        return 0.0
    return 0.5
```

### 2.3 非中立场主场优势

历史比赛中，如果不是中立场，模型会在计算期望胜率时给主队临时增加主场优势：

```text
R_home_adjusted = R_home + home_advantage
```

当前默认：

```text
home_advantage = 60
```

这个加成只用于当前比赛的期望胜率计算，不会永久写入球队 Elo。

### 2.4 比赛权重

当前模型不会把每场历史比赛看成同等重要。单场权重由三部分相乘：

```text
weight = tournament_weight * recency_weight * margin_multiplier
```

#### 赛事重要性权重

当前实现：

```python
def tournament_weight(tournament: str) -> float:
    name = tournament.lower()
    if "fifa world cup" == name or "world cup" == name:
        return 1.50
    if "qualification" in name or "qualifier" in name:
        return 1.15
    if "uefa euro" in name or "copa am" in name or "african cup" in name:
        return 1.25
    if "friendly" in name:
        return 0.75
    return 1.0
```

含义是：

- 世界杯正赛比普通比赛更有信息量。
- 洲际杯赛、世界杯预选赛也较重要。
- 友谊赛参考价值较低。

#### 时间衰减权重

越近的比赛影响越大。设比赛距截止日期的年份为：

```text
age_years = (cutoff - played_on) / 365.25
```

当前时间权重为：

```text
recency_weight = 0.20 + 0.80 * exp(-ln(2) * age_years / half_life_years)
```

特点：

- 最近比赛权重接近 `1.0`。
- 每过 `half_life_years` 年，衰减部分减半。
- 保留 `0.20` 的基础权重，旧比赛不会完全归零。

对应代码：

```python
def recency_weight(played_on: date, cutoff: date, half_life_years: float) -> float:
    age_years = max((cutoff - played_on).days / 365.25, 0.0)
    return 0.20 + 0.80 * math.exp(-math.log(2) * age_years / half_life_years)
```

#### 净胜球倍数

大比分胜利通常比一球小胜更有信息量，但强队大胜弱队时，信息增益应被压低。

当前实现：

```text
margin_multiplier = ln(abs(goal_diff) + 1) * 2.2 / (0.001 * abs(elo_diff) + 2.2)
```

如果净胜球不超过 1：

```text
margin_multiplier = 1.0
```

对应代码：

```python
def margin_multiplier(goal_diff: int, elo_diff: float) -> float:
    margin = abs(goal_diff)
    if margin <= 1:
        return 1.0
    return math.log(margin + 1) * (2.2 / (0.001 * abs(elo_diff) + 2.2))
```

### 2.5 Elo 更新公式

主队 Elo 更新量：

```text
delta = k_factor * weight * (S_home - E_home)
```

更新后：

```text
R_home_new = R_home_old + delta
R_away_new = R_away_old - delta
```

如果主队表现高于模型预期，`S_home - E_home > 0`，主队涨分；反之扣分。客队做等额反向调整。

核心伪代码：

```python
ratings = defaultdict(lambda: 1500.0)

for match in historical_matches:
    home_rating = ratings[match.home]
    away_rating = ratings[match.away]

    adjusted_home = home_rating
    if not match.neutral:
        adjusted_home += home_advantage

    expected_home = expected_score(adjusted_home, away_rating)
    actual_home = outcome(match.home_goals, match.away_goals)

    weight = (
        tournament_weight(match.tournament)
        * recency_weight(match.played_on, cutoff, half_life_years)
        * margin_multiplier(match.home_goals - match.away_goals, adjusted_home - away_rating)
    )

    delta = k_factor * weight * (actual_home - expected_home)

    ratings[match.home] = home_rating + delta
    ratings[match.away] = away_rating - delta
```

## 3. AI 影响因子的 Elo 微调

Web App 允许用户添加信息源，并调用 LLM 提取结构化影响因子。影响因子不会直接生成概率，而是被转换为有限的 Elo 调整。

简化结构：

```json
{
  "team": "France",
  "category": "injury",
  "direction": "negative",
  "confidence": 0.8
}
```

当前服务层会根据方向、类别和置信度，把因素转换为小幅 Elo delta，再叠加到基础评分上：

```python
ratings[team] = ratings.get(team, 1500.0) + delta
```

这条设计边界很重要：

- LLM 负责阅读和结构化信息。
- 固定规则负责把信息转为模型参数。
- 夺冠概率仍由本地模拟模型计算。

## 4. 进球模型：Elo 到 Poisson

有了球队 Elo 后，模型需要模拟具体比分。当前使用 Poisson 分布，因为足球进球数是非负整数，且单场进球通常较低。

### 4.1 基础进球均值

模型先用最近若干年的历史比赛估计每队每场的基础进球均值：

```text
base_goals = mean((home_goals + away_goals) / 2)
```

当前默认取最近 10 年：

```python
def recent_goal_base(matches: list[Match], cutoff: date, years: int = 10) -> float:
    lower = date(cutoff.year - years, cutoff.month, cutoff.day)
    goals = [
        (m.home_goals + m.away_goals) / 2.0
        for m in matches
        if lower <= m.played_on < cutoff
    ]
    return statistics.mean(goals) if goals else 1.35
```

### 4.2 东道主加成

2026 世界杯由加拿大、墨西哥、美国联合举办。模拟世界杯正赛时，当前模型会给这三支球队额外 Elo 加成：

```text
host_boost = 80
```

这个加成不同于历史比赛里的普通主场优势。它只在世界杯模拟阶段使用。

### 4.3 Elo 差距转成预期进球

设两队经过东道主加成后的评分为 `R_a` 和 `R_b`：

```text
diff = clamp(R_a - R_b, -900, 900)
```

当前模型把 Elo 差距通过指数函数转换为两队预期进球：

```text
lambda_a = base_goals * exp(diff / goal_elo_scale)
lambda_b = base_goals * exp(-diff / goal_elo_scale)
```

当前默认：

```text
goal_elo_scale = 650
```

当 `diff = 0` 时：

```text
lambda_a = lambda_b = base_goals
```

当 A 更强时：

```text
lambda_a > base_goals
lambda_b < base_goals
```

对应代码：

```python
def score_lambdas(team_a, team_b, ratings, base_goals, host_boost, goal_elo_scale):
    ra = ratings.get(canonical_team(team_a, ratings), 1500.0)
    rb = ratings.get(canonical_team(team_b, ratings), 1500.0)

    if team_a in HOSTS_2026:
        ra += host_boost
    if team_b in HOSTS_2026:
        rb += host_boost

    diff = max(-900.0, min(900.0, ra - rb))
    return (
        base_goals * math.exp(diff / goal_elo_scale),
        base_goals * math.exp(-diff / goal_elo_scale),
    )
```

### 4.4 Poisson 抽样

如果某队的预期进球为 `lambda`，则其进球数 `X` 服从：

```text
X ~ Poisson(lambda)
```

概率质量函数：

```text
P(X = k) = exp(-lambda) * lambda^k / k!
```

当前实现使用 Knuth 算法抽样，并把 `lambda` 裁剪在 `[0.05, 5.5]`：

```python
def poisson_sample(lam: float, rng: random.Random) -> int:
    lam = max(0.05, min(lam, 5.5))
    threshold = math.exp(-lam)
    product = 1.0
    k = 0
    while product > threshold:
        k += 1
        product *= rng.random()
    return k - 1
```

单场比分模拟：

```python
def simulate_score(team_a, team_b, ratings, base_goals, rng, host_boost, goal_elo_scale):
    lam_a, lam_b = score_lambdas(
        team_a, team_b, ratings, base_goals, host_boost, goal_elo_scale
    )
    return poisson_sample(lam_a, rng), poisson_sample(lam_b, rng)
```

### 4.5 单场预测聚合

赛事模拟中的 `simulate_score` 是一次随机抽样。为了支持后续预测复盘，当前模型另有单场预测聚合函数，会枚举有限比分范围并计算：

- 主胜、平局、客胜概率。
- 双方期望进球。
- 最可能比分 Top N，用作后续复盘参考，不适合作为单场预测的主结论。

伪代码：

```python
lambda_a, lambda_b = score_lambdas(team_a, team_b, ratings, base_goals, host_boost, scale)

for goals_a in range(0, max_goals + 1):
    for goals_b in range(0, max_goals + 1):
        probability = poisson_pmf(lambda_a, goals_a) * poisson_pmf(lambda_b, goals_b)
        if goals_a > goals_b:
            home_win += probability
        elif goals_a < goals_b:
            away_win += probability
        else:
            draw += probability
```

当前 Web 预测结果会为小组赛 72 场已知对阵输出 `matchPredictions`，每项包含 `home_win`、`draw`、`away_win`、`expected_home_goals`、`expected_away_goals` 和 `top_scorelines`。赛事进程页面优先展示胜平负概率和期望进球，避免把单一最可能比分误读成确定预测。淘汰赛在球队未确定前暂不生成单场预测。

## 5. 小组赛模拟

每个小组有 4 支球队，进行单循环。每场比赛得到比分后，按足球规则累计：

```text
胜：3 分
平：1 分
负：0 分
```

同时记录：

```text
gf  进球
ga  失球
gd  净胜球 = gf - ga
```

当前排序近似规则：

```text
积分 > 净胜球 > 进球数 > Elo > 随机抖动
```

伪代码：

```python
for each group:
    table = init_table(group.teams)

    for each pair(team_a, team_b):
        if this match has a fixed real score:
            goals_a, goals_b = fixed_score
        else:
            goals_a, goals_b = simulate_score(team_a, team_b)

        update_points_goals(table, team_a, team_b, goals_a, goals_b)

    ranking = sort_by(points, goal_difference, goals_for, rating, jitter)
```

需要注意：FIFA 完整排名规则还包含相互战绩、公平竞赛分等。当前实现是一个可复现的近似规则，不是完整官方规则。

## 6. 32 强晋级和淘汰赛模拟

### 6.1 小组出线

2026 世界杯有 12 个小组，每组 4 队。当前模型按如下规则晋级 32 强：

```text
每组前 2 名直接晋级：12 * 2 = 24 队
12 个小组第三里成绩最好的 8 队晋级
合计 32 队
```

小组第三排序使用和小组内类似的字段：

```text
积分 > 净胜球 > 进球数 > Elo > 随机抖动
```

### 6.2 32 强签位

当前模型内置了 32 强签位结构，例如：

```text
("2A", "2B")
("1C", "2F")
("1E", "3A/B/C/D/F")
...
```

普通槽位如 `1A` 表示 A 组第一，`2B` 表示 B 组第二。

包含多个小组的第三名槽位，如：

```text
3A/B/C/D/F
```

表示该场比赛可能接收这些小组的晋级第三名。具体是哪一个小组落入该槽位，不再用可用顺序贪心分配，而是按 2026 世界杯规则附录 C 的第三名组合表查表决定。

项目将组合表保存为：

```text
data/third_place_assignments_2026.json
```

这个文件包含 495 种可能组合。查表键是 8 个晋级第三名小组，例如：

```text
ABCDEFGH
```

表中 8 个第三名槽位按以下组头名顺序排列：

```text
1A, 1B, 1D, 1E, 1G, 1I, 1K, 1L
```

例如当 A-H 组第三名全部晋级时，表中落位为：

```text
1A vs 3H
1B vs 3G
1D vs 3B
1E vs 3C
1G vs 3A
1I vs 3F
1K vs 3D
1L vs 3E
```

模拟过程先根据小组赛结果选出 8 个最佳第三名，再用这 8 个小组组成查表键，最后把具体第三名球队填入对应 32 强比赛。

### 6.3 淘汰赛胜者

每场淘汰赛：

1. 模拟常规时间比分。
2. 如果常规时间分出胜负，胜者晋级。
3. 如果打平，模拟加时赛。
4. 如果加时仍打平，用 Elo 期望胜率近似点球大战胜率。

伪代码：

```python
def knockout_winner(team_a, team_b):
    goals_a, goals_b = simulate_score(team_a, team_b)
    if goals_a != goals_b:
        return team_a if goals_a > goals_b else team_b

    et_a, et_b = simulate_score(team_a, team_b, base_goals * 0.35)
    if et_a != et_b:
        return team_a if et_a > et_b else team_b

    p_a = expected_score(rating_a, rating_b)
    return team_a if random() < p_a else team_b
```

## 7. Monte Carlo 概率汇总

单次世界杯模拟只是一条可能路径。为了得到概率，模型会重复模拟很多次。

设总模拟次数为 `N`。如果某队夺冠次数为 `C_champion`，则：

```text
P(champion) = C_champion / N
```

同理：

```text
P(final) = C_final / N
P(sf) = C_sf / N
P(qf) = C_qf / N
P(r16) = C_r16 / N
P(r32) = C_r32 / N
```

核心伪代码：

```python
counts = defaultdict(lambda: defaultdict(int))

for _ in range(simulations):
    result = simulate_tournament(groups, ratings, base_goals, rng)

    for stage in ["r32", "r16", "qf", "sf", "final"]:
        for team in result[stage]:
            counts[team][stage] += 1

    champion = result["champion"][0]
    counts[champion]["champion"] += 1

rows = []
for team, stage_counts in counts.items():
    rows.append({
        "team": team,
        "champion": stage_counts["champion"] / simulations,
        "final": stage_counts["final"] / simulations,
        "sf": stage_counts["sf"] / simulations,
        "qf": stage_counts["qf"] / simulations,
        "r16": stage_counts["r16"] / simulations,
        "r32": stage_counts["r32"] / simulations,
    })
```

模拟次数越高，估计方差越低，但不会改变模型假设本身。比如 `10000` 次比 `1000` 次更稳定，但不会让没有纳入的数据突然被模型理解。

## 8. Web App 与命令行模型的差异

`worldcup_simulator.py` 可以单独作为 CLI 运行。Web App 通过 `services/prediction.py` 在它之上增加了几层应用逻辑：

```text
worldcup_simulator.py
  -> 纯模型和 CLI

services/prediction.py
  -> 读取已保存比分
  -> 应用 AI 因子 Elo 微调
  -> 统计小组出线概率
  -> 中文本地化结果
```

因此，网页预测结果可能和直接运行 CLI 有差异，主要原因是：

- Web App 会纳入官方确认赛果，以及 `APP_MODE=local` 时 `app_data/matches.json` 中的用户本地覆盖比分。
- Web App 会纳入已审核的 AI 影响因子。
- Web App 输出中文队名和小组出线概率。

## 9. 当前模型的主要假设

当前模型的关键假设包括：

1. 球队实力可以用单一 Elo 分数近似。
2. 历史比赛对当前实力有指数衰减影响。
3. 赛事重要性可以用固定权重近似。
4. Elo 差距可以通过指数函数映射到预期进球。
5. 单队进球数可用 Poisson 分布近似。
6. 东道主优势可用固定 Elo 加成近似。
7. 小组排名规则采用近似排序，而不是完整 FIFA 细则。
8. 点球大战胜率用 Elo 期望胜率近似。
9. AI 影响因子只通过有限 Elo 微调参与模型。

这些假设让模型保持可解释、可复现，但也限制了它的表达能力。

## 10. 当前局限和改进方向

### 局限

- 没有球员级别数据，例如身价、出场时间、伤病、停赛、门将能力。
- 没有战术风格或对位关系。
- 没有赛程间隔、旅途距离、气候和场馆变量。
- 没有博彩赔率或市场共识。
- 没有完整 FIFA 小组排名细则。
- 没有根据真实世界杯历史校准参数。
- Poisson 模型假设较简单，未处理球队攻防强度的独立参数。

### 可优先改进

1. 将 `worldcup_simulator.py` 拆成 `model/elo.py`、`model/scoring.py`、`model/tournament.py`。
2. 为 Elo 更新和单场模拟增加单元测试。
3. 做参数敏感性分析，例如 `host_boost = 0 / 40 / 80 / 120`。
4. 加入真实结果与预测概率的对比视图。
5. 用历史大赛回测校准 `k_factor`、`goal_elo_scale` 和 `host_boost`。
6. 把球队拆成进攻强度和防守强度，而不是只使用单一 Elo。
7. 将官方小组排名规则补完整。

## 11. 最小可复现流程

命令行运行：

```bash
python3 worldcup_simulator.py \
  --results data/results.csv \
  --groups data/groups_2026.json \
  --simulations 1000 \
  --output outputs/worldcup_2026_probs.csv \
  --meta-output outputs/worldcup_2026_meta.json
```

生成离线图表：

```bash
python3 visualize_predictions.py \
  --input outputs/worldcup_2026_probs.csv \
  --output outputs/worldcup_2026_probs.html \
  --top 16
```

Web App 运行：

```bash
python3 app.py
```

然后打开：

```text
http://127.0.0.1:8765
```
