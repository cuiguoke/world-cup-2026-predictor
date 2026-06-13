from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, datetime

from app_config import FULL_RESULTS_PATH, GROUPS_PATH, ROOT, SAMPLE_RESULTS_PATH
from services.schedule import fixed_scores_from_matches, load_or_create_matches
from services.sources import build_factor_adjustments, enriched_factors
from services.teams import localize_prediction, team_display_name
from storage import app_log
from worldcup_simulator import (
    build_elo,
    load_groups,
    load_matches,
    recent_goal_base,
    simulate_tournament,
    summarize_counts,
)


def summarize_group_qualification(
    groups: dict[str, list[str]],
    group_counts: dict[str, dict[str, dict[str, int]]],
    simulations: int,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for group, teams in groups.items():
        rows = []
        for team in teams:
            counts = group_counts[group][team]
            rows.append(
                {
                    "team": team,
                    "team_name": team_display_name(team),
                    "group": group,
                    "first": counts["first"] / simulations,
                    "second": counts["second"] / simulations,
                    "third": counts["third"] / simulations,
                    "top_two": counts["top_two"] / simulations,
                    "qualified": counts["qualified"] / simulations,
                }
            )
        result.append(
            {
                "group": group,
                "rows": sorted(rows, key=lambda row: row["qualified"], reverse=True),
            }
        )
    return result


def run_prediction(simulations: int = 1000) -> dict[str, object]:
    started_at = datetime.now()
    app_log("prediction.start", simulations=simulations)
    cutoff = date(2026, 6, 11)
    groups = load_groups(GROUPS_PATH)
    matches_state = load_or_create_matches()
    fixed_scores = fixed_scores_from_matches(matches_state)
    results_path = FULL_RESULTS_PATH if FULL_RESULTS_PATH.exists() else SAMPLE_RESULTS_PATH
    history = load_matches(results_path, cutoff)
    ratings = build_elo(history, cutoff)
    rating_adjustments, applied_factors = build_factor_adjustments(enriched_factors(), groups)
    for team, delta in rating_adjustments.items():
        ratings[team] = ratings.get(team, 1500.0) + delta
    base_goals = recent_goal_base(history, cutoff)
    rng = random.Random(20260611)
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    group_counts: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )

    for team in sorted({team for teams in groups.values() for team in teams}):
        counts[team]["qualified"] += 0

    for _ in range(simulations):
        result = simulate_tournament(
            groups,
            ratings,
            base_goals,
            rng,
            host_boost=80.0,
            goal_elo_scale=650.0,
            fixed_group_scores=fixed_scores,
        )
        for stage in ["r32", "r16", "qf", "sf", "final"]:
            for team in result[stage]:
                counts[str(team)][stage] += 1
        for team in result["champion"]:
            counts[str(team)]["champion"] += 1
        for group, ranking in dict(result.get("group_rankings", {})).items():
            for item in list(ranking):
                team = str(dict(item).get("team", ""))
                rank = int(dict(item).get("rank", 0))
                if not team or rank <= 0:
                    continue
                if rank == 1:
                    group_counts[str(group)][team]["first"] += 1
                if rank == 2:
                    group_counts[str(group)][team]["second"] += 1
                if rank == 3:
                    group_counts[str(group)][team]["third"] += 1
                if rank <= 2:
                    group_counts[str(group)][team]["top_two"] += 1
                if dict(item).get("qualified"):
                    group_counts[str(group)][team]["qualified"] += 1

    rows = summarize_counts(counts, simulations)
    group_qualification = summarize_group_qualification(groups, group_counts, simulations)
    finished_count = sum(1 for match in matches_state if match.get("status") == "finished")
    elapsed_ms = int((datetime.now() - started_at).total_seconds() * 1000)
    app_log(
        "prediction.done",
        simulations=simulations,
        finished_matches=finished_count,
        ai_factors=len(applied_factors),
        adjustments=len(rating_adjustments),
        elapsed_ms=elapsed_ms,
    )
    return localize_prediction(
        {
            "createdAt": datetime.now().isoformat(timespec="seconds"),
            "simulations": simulations,
            "historySource": str(results_path.relative_to(ROOT)),
            "finishedMatches": finished_count,
            "aiFactorsApplied": len(applied_factors),
            "ratingAdjustments": [
                {"team": team, "team_name": team_display_name(team), "delta": delta}
                for team, delta in sorted(rating_adjustments.items())
            ],
            "appliedFactors": applied_factors,
            "rows": rows,
            "groupQualification": group_qualification,
        }
    )
