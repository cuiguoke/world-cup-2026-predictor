#!/usr/bin/env python3
"""
Reproducible World Cup 2026 simulation inspired by the article's Claude workflow.

Input data:
  martj42/international_results style results.csv with columns:
  date,home_team,away_team,home_score,away_score,tournament,city,country,neutral
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


DEFAULT_RESULTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
)

# 2026 年三个东道主。模拟世界杯正赛时给这些球队额外加成，
# 用来近似主场、气候熟悉度、观众支持等因素。
HOSTS_2026 = {"Canada", "Mexico", "United States"}

# 不同公开数据源对国家队名称的写法可能不同。这里做一个轻量别名映射，
# 避免 “Czech Republic” 和 “Czechia” 这类名称差异导致 Elo 查不到。
ALIASES = {
    "Czech Republic": ["Czechia"],
    "Ivory Coast": ["Côte d'Ivoire", "Cote d'Ivoire"],
    "South Korea": ["Korea Republic"],
    "United States": ["USA", "United States of America"],
    "Cape Verde": ["Cabo Verde"],
    "Curacao": ["Curaçao"],
    "DR Congo": ["Congo DR", "Democratic Republic of the Congo"],
    "Iran": ["Iran (Islamic Republic of)"],
    "Turkey": ["Türkiye", "Turkiye"],
}


@dataclass(frozen=True)
class Match:
    played_on: date
    home: str
    away: str
    home_goals: int
    away_goals: int
    tournament: str
    neutral: bool


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def load_matches(path: Path, cutoff: date) -> list[Match]:
    """读取历史比赛，并只保留 cutoff 之前已经发生的比赛。"""
    matches: list[Match] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            played_on = datetime.strptime(row["date"], "%Y-%m-%d").date()
            if played_on >= cutoff:
                continue
            if row.get("home_score", "") == "" or row.get("away_score", "") == "":
                continue
            matches.append(
                Match(
                    played_on=played_on,
                    home=row["home_team"].strip(),
                    away=row["away_team"].strip(),
                    home_goals=int(row["home_score"]),
                    away_goals=int(row["away_score"]),
                    tournament=row.get("tournament", "").strip(),
                    neutral=parse_bool(row.get("neutral", "false")),
                )
            )
    return sorted(matches, key=lambda m: m.played_on)


def ensure_results_csv(path: Path, url: str = DEFAULT_RESULTS_URL) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url} -> {path}")
    urllib.request.urlretrieve(url, path)


def load_groups(path: Path) -> dict[str, list[str]]:
    """读取 12 个小组，每组必须正好 4 支球队。"""
    groups = json.loads(path.read_text(encoding="utf-8"))
    expected = list("ABCDEFGHIJKL")
    if sorted(groups) != expected:
        raise ValueError("Groups JSON must contain exactly groups A through L.")
    for group, teams in groups.items():
        if not isinstance(teams, list) or len(teams) != 4:
            raise ValueError(f"Group {group} must contain exactly four teams.")
    return {group: [str(team) for team in teams] for group, teams in groups.items()}


def tournament_weight(tournament: str) -> float:
    """按赛事重要性调整 Elo 更新幅度。世界杯比赛应比友谊赛更有信息量。"""
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


def recency_weight(played_on: date, cutoff: date, half_life_years: float) -> float:
    """越近的比赛权重越高；旧比赛不会归零，而是保留 20% 的基础权重。"""
    age_years = max((cutoff - played_on).days / 365.25, 0.0)
    return 0.20 + 0.80 * math.exp(-math.log(2) * age_years / half_life_years)


def margin_multiplier(goal_diff: int, elo_diff: float) -> float:
    """大比分胜利提供更多信息，但强队大胜弱队时增益会被压低。"""
    margin = abs(goal_diff)
    if margin <= 1:
        return 1.0
    return math.log(margin + 1) * (2.2 / (0.001 * abs(elo_diff) + 2.2))


def outcome(home_goals: int, away_goals: int) -> float:
    if home_goals > away_goals:
        return 1.0
    if home_goals < away_goals:
        return 0.0
    return 0.5


def expected_score(rating_a: float, rating_b: float) -> float:
    """标准 Elo 期望胜率公式，返回 A 面对 B 的期望得分。"""
    return 1.0 / (1.0 + 10 ** (-(rating_a - rating_b) / 400.0))


def canonical_team(name: str, ratings: dict[str, float]) -> str:
    if name in ratings:
        return name
    for possible in ALIASES.get(name, []):
        if possible in ratings:
            return possible
    return name


def build_elo(
    matches: Iterable[Match],
    cutoff: date,
    *,
    initial: float = 1500.0,
    k_factor: float = 22.0,
    home_advantage: float = 60.0,
    half_life_years: float = 6.0,
) -> dict[str, float]:
    ratings: dict[str, float] = defaultdict(lambda: initial)
    for m in matches:
        home_rating = ratings[m.home]
        away_rating = ratings[m.away]

        # Elo 更新前先给非中立场主队加临时主场优势。
        # 这个优势只用于计算本场预期结果，不会永久写入主队评分。
        venue_advantage = 0.0 if m.neutral else home_advantage
        adjusted_home = home_rating + venue_advantage
        exp_home = expected_score(adjusted_home, away_rating)
        result_home = outcome(m.home_goals, m.away_goals)
        elo_diff = adjusted_home - away_rating

        # 单场比赛的权重由三部分组成：赛事重要性、比赛新旧程度、净胜球信息量。
        weight = (
            tournament_weight(m.tournament)
            * recency_weight(m.played_on, cutoff, half_life_years)
            * margin_multiplier(m.home_goals - m.away_goals, elo_diff)
        )

        # 真实结果高于预期，主队涨分；低于预期，主队扣分。
        # 客队做等额反向调整，保证整体评分池基本守恒。
        delta = k_factor * weight * (result_home - exp_home)
        ratings[m.home] = home_rating + delta
        ratings[m.away] = away_rating - delta
    return dict(ratings)


def recent_goal_base(matches: list[Match], cutoff: date, years: int = 10) -> float:
    """用最近若干年的比赛估计每队每场的基础进球均值。"""
    lower = date(cutoff.year - years, cutoff.month, cutoff.day)
    goals = [
        (m.home_goals + m.away_goals) / 2.0
        for m in matches
        if lower <= m.played_on < cutoff
    ]
    return statistics.mean(goals) if goals else 1.35


def poisson_sample(lam: float, rng: random.Random) -> int:
    """从 Poisson 分布抽样，用于模拟足球比分这种离散进球数。"""
    lam = max(0.05, min(lam, 5.5))
    threshold = math.exp(-lam)
    product = 1.0
    k = 0
    while product > threshold:
        k += 1
        product *= rng.random()
    return k - 1


def score_lambdas(
    team_a: str,
    team_b: str,
    ratings: dict[str, float],
    base_goals: float,
    host_boost: float,
    goal_elo_scale: float,
) -> tuple[float, float]:
    ra = ratings.get(canonical_team(team_a, ratings), 1500.0)
    rb = ratings.get(canonical_team(team_b, ratings), 1500.0)

    # 正赛阶段给东道主额外加成。这里与历史比赛中的普通主场优势分开处理。
    if team_a in HOSTS_2026:
        ra += host_boost
    if team_b in HOSTS_2026:
        rb += host_boost

    # Elo 差距越大，强队的预期进球越高。做裁剪是为了避免极端评分差
    # 让 Poisson 均值膨胀得不现实。
    diff = max(-900.0, min(900.0, ra - rb))
    return (
        base_goals * math.exp(diff / goal_elo_scale),
        base_goals * math.exp(-diff / goal_elo_scale),
    )


def simulate_score(
    team_a: str,
    team_b: str,
    ratings: dict[str, float],
    base_goals: float,
    rng: random.Random,
    host_boost: float,
    goal_elo_scale: float,
) -> tuple[int, int]:
    lam_a, lam_b = score_lambdas(
        team_a, team_b, ratings, base_goals, host_boost, goal_elo_scale
    )
    return poisson_sample(lam_a, rng), poisson_sample(lam_b, rng)


def knockout_winner(
    team_a: str,
    team_b: str,
    ratings: dict[str, float],
    base_goals: float,
    rng: random.Random,
    host_boost: float,
    goal_elo_scale: float,
) -> str:
    """模拟一场淘汰赛；常规时间打平则模拟加时，再用评分加权点球。"""
    a_goals, b_goals = simulate_score(
        team_a, team_b, ratings, base_goals, rng, host_boost, goal_elo_scale
    )
    if a_goals != b_goals:
        return team_a if a_goals > b_goals else team_b

    # 加时赛近似成一场时间更短、进球期望更低的小比赛。
    et_a, et_b = simulate_score(
        team_a, team_b, ratings, base_goals * 0.35, rng, host_boost, goal_elo_scale
    )
    if et_a != et_b:
        return team_a if et_a > et_b else team_b

    ra = ratings.get(canonical_team(team_a, ratings), 1500.0)
    rb = ratings.get(canonical_team(team_b, ratings), 1500.0)
    p_a = expected_score(ra, rb)
    return team_a if rng.random() < p_a else team_b


def group_table(
    teams: list[str],
    ratings: dict[str, float],
    base_goals: float,
    rng: random.Random,
    host_boost: float,
    goal_elo_scale: float,
    fixed_scores: dict[tuple[str, str], tuple[int, int]] | None = None,
) -> list[dict[str, object]]:
    """模拟一个小组的单循环比赛，并按积分、净胜球、进球数等规则排序。"""
    fixed_scores = fixed_scores or {}
    rows = {
        t: {
            "team": t,
            "pts": 0,
            "gf": 0,
            "ga": 0,
            "gd": 0,
            "rating": ratings.get(canonical_team(t, ratings), 1500.0),
        }
        for t in teams
    }
    for i, home in enumerate(teams):
        for away in teams[i + 1 :]:
            if (home, away) in fixed_scores:
                hg, ag = fixed_scores[(home, away)]
            elif (away, home) in fixed_scores:
                ag, hg = fixed_scores[(away, home)]
            else:
                hg, ag = simulate_score(
                    home, away, ratings, base_goals, rng, host_boost, goal_elo_scale
                )
            rows[home]["gf"] += hg
            rows[home]["ga"] += ag
            rows[away]["gf"] += ag
            rows[away]["ga"] += hg
            if hg > ag:
                rows[home]["pts"] += 3
            elif hg < ag:
                rows[away]["pts"] += 3
            else:
                rows[home]["pts"] += 1
                rows[away]["pts"] += 1
    for row in rows.values():
        row["gd"] = row["gf"] - row["ga"]
        row["jitter"] = rng.random()

    # 官方完整排名规则还包括相互战绩、公平竞赛分等。这里使用一组
    # 可复现的近似规则，并用随机抖动打破仍然完全相同的情况。
    return sorted(
        rows.values(),
        key=lambda r: (r["pts"], r["gd"], r["gf"], r["rating"], r["jitter"]),
        reverse=True,
    )


# 32 强签位结构。普通槽位如 1A 表示 A 组第一；3A/B/C/D/F
# 表示从这些小组的第三名晋级队中选一个填入。
R32_SLOTS = [
    ("2A", "2B"),
    ("1C", "2F"),
    ("1E", "3A/B/C/D/F"),
    ("1F", "2C"),
    ("2E", "2I"),
    ("1I", "3C/D/F/G/H"),
    ("1A", "3C/E/F/H/I"),
    ("1L", "3E/H/I/J/K"),
    ("1G", "3A/E/H/I/J"),
    ("1D", "3B/E/F/I/J"),
    ("1H", "2J"),
    ("2K", "2L"),
    ("1B", "3E/F/G/I/J"),
    ("2D", "2G"),
    ("1J", "2H"),
    ("1K", "3D/E/I/J/L"),
]

# 后续轮次按上一轮胜者列表的下标配对。
NEXT_ROUNDS = [
    [(0, 2), (1, 4), (3, 5), (6, 7), (10, 11), (8, 9), (13, 15), (12, 14)],
    [(0, 1), (2, 3), (4, 5), (6, 7)],
    [(0, 1), (2, 3)],
    [(0, 1)],
]


def resolve_slot(
    slot: str,
    positions: dict[str, str],
    thirds: dict[str, str],
    used_thirds: set[str],
) -> str:
    """把签位字符串解析成具体球队名称。"""
    if not slot.startswith("3"):
        return positions[slot]
    allowed = slot[1:].split("/")
    available = [g for g in allowed if g in thirds and g not in used_thirds]
    if not available:
        available = [g for g in thirds if g not in used_thirds]
    chosen_group = available[0]
    used_thirds.add(chosen_group)
    return thirds[chosen_group]


def simulate_tournament(
    groups: dict[str, list[str]],
    ratings: dict[str, float],
    base_goals: float,
    rng: random.Random,
    host_boost: float,
    goal_elo_scale: float,
    fixed_group_scores: dict[str, dict[tuple[str, str], tuple[int, int]]] | None = None,
) -> dict[str, str | list[str]]:
    """模拟一整届世界杯，返回每个阶段还留在赛事中的球队列表。"""
    fixed_group_scores = fixed_group_scores or {}
    positions: dict[str, str] = {}
    third_rows: list[tuple[str, dict[str, object]]] = []
    for group, teams in groups.items():
        table = group_table(
            teams,
            ratings,
            base_goals,
            rng,
            host_boost,
            goal_elo_scale,
            fixed_scores=fixed_group_scores.get(group),
        )
        positions[f"1{group}"] = str(table[0]["team"])
        positions[f"2{group}"] = str(table[1]["team"])
        third_rows.append((group, table[2]))

    third_rows.sort(
        key=lambda item: (
            item[1]["pts"],
            item[1]["gd"],
            item[1]["gf"],
            item[1]["rating"],
            item[1]["jitter"],
        ),
        reverse=True,
    )
    # 12 个小组第三中，成绩最好的 8 支进入 32 强。
    thirds = {group: str(row["team"]) for group, row in third_rows[:8]}

    used_thirds: set[str] = set()
    r32_matches = [
        (
            resolve_slot(left, positions, thirds, used_thirds),
            resolve_slot(right, positions, thirds, used_thirds),
        )
        for left, right in R32_SLOTS
    ]

    r32_teams = [team for match in r32_matches for team in match]
    winners = [
        knockout_winner(a, b, ratings, base_goals, rng, host_boost, goal_elo_scale)
        for a, b in r32_matches
    ]
    stages = {"r32": r32_teams, "r16": winners}
    for round_name, pairings in zip(["qf", "sf", "final", "champion"], NEXT_ROUNDS):
        next_winners = [
            knockout_winner(
                winners[i], winners[j], ratings, base_goals, rng, host_boost, goal_elo_scale
            )
            for i, j in pairings
        ]
        stages[round_name] = next_winners
        winners = next_winners
    return stages


def summarize_counts(counts: dict[str, dict[str, int]], simulations: int) -> list[dict[str, object]]:
    """把阶段计数转换成概率表，并按夺冠概率排序。"""
    rows = []
    for team, stage_counts in counts.items():
        rows.append(
            {
                "team": team,
                "champion": stage_counts["champion"] / simulations,
                "final": stage_counts["final"] / simulations,
                "sf": stage_counts["sf"] / simulations,
                "qf": stage_counts["qf"] / simulations,
                "r16": stage_counts["r16"] / simulations,
                "r32": stage_counts["r32"] / simulations,
            }
        )
    return sorted(rows, key=lambda r: r["champion"], reverse=True)


def run(args: argparse.Namespace) -> None:
    cutoff = datetime.strptime(args.cutoff, "%Y-%m-%d").date()
    results_path = Path(args.results)
    if args.download:
        ensure_results_csv(results_path, args.results_url)

    matches = load_matches(results_path, cutoff)
    ratings = build_elo(
        matches,
        cutoff,
        k_factor=args.k_factor,
        home_advantage=args.home_advantage,
        half_life_years=args.half_life_years,
    )
    base_goals = args.base_goals or recent_goal_base(matches, cutoff)
    groups = load_groups(Path(args.groups))

    # 固定随机种子，确保同样输入和参数能得到同样结果。
    rng = random.Random(args.seed)
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    all_teams = sorted({team for teams in groups.values() for team in teams})
    for team in all_teams:
        counts[team]["qualified"] += 0

    for _ in range(args.simulations):
        result = simulate_tournament(
            groups,
            ratings,
            base_goals,
            rng,
            host_boost=args.host_boost,
            goal_elo_scale=args.goal_elo_scale,
        )
        for stage in ["r32", "r16", "qf", "sf", "final"]:
            for team in result[stage]:
                counts[team][stage] += 1
        for team in result["champion"]:
            counts[str(team)]["champion"] += 1

    rows = summarize_counts(counts, args.simulations)

    # 输出两份文件：CSV 给人看和做表格分析，JSON 记录本次运行参数。
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["team", "champion", "final", "sf", "qf", "r16", "r32"]
        )
        writer.writeheader()
        writer.writerows(rows)

    meta = {
        "cutoff": args.cutoff,
        "matches": len(matches),
        "simulations": args.simulations,
        "base_goals_per_team": base_goals,
        "parameters": {
            "k_factor": args.k_factor,
            "home_advantage": args.home_advantage,
            "host_boost": args.host_boost,
            "half_life_years": args.half_life_years,
            "goal_elo_scale": args.goal_elo_scale,
        },
        "top_10": rows[:10],
    }
    args.meta_output.parent.mkdir(parents=True, exist_ok=True)
    args.meta_output.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Loaded {len(matches):,} matches. Base goals/team={base_goals:.3f}")
    print(f"Wrote {args.output}")
    for row in rows[:10]:
        print(f"{row['team']:<18} champion={row['champion']:.2%} final={row['final']:.2%}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default="data/results.csv", help="Path to results.csv")
    parser.add_argument("--groups", default="data/groups_2026.json", help="Path to 12x4 groups JSON")
    parser.add_argument("--download", action="store_true", help="Download results.csv if missing")
    parser.add_argument("--results-url", default=DEFAULT_RESULTS_URL)
    parser.add_argument("--cutoff", default="2026-06-11")
    parser.add_argument("--simulations", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=20260611)
    parser.add_argument("--k-factor", type=float, default=22.0)
    parser.add_argument("--home-advantage", type=float, default=60.0)
    parser.add_argument("--host-boost", type=float, default=80.0)
    parser.add_argument("--half-life-years", type=float, default=6.0)
    parser.add_argument("--goal-elo-scale", type=float, default=650.0)
    parser.add_argument("--base-goals", type=float, default=None)
    parser.add_argument("--output", type=Path, default=Path("outputs/worldcup_2026_probs.csv"))
    parser.add_argument("--meta-output", type=Path, default=Path("outputs/worldcup_2026_meta.json"))
    return parser


if __name__ == "__main__":
    run(build_parser().parse_args())
