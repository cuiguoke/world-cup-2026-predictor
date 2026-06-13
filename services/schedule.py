from collections import defaultdict

from app_config import (
    ALLOW_USER_SCORE_INPUT,
    GROUPS_PATH,
    GROUP_PAIRINGS,
    KNOCKOUT_DISPLAY_TIMES,
    KNOCKOUT_MATCHES,
    MATCHES_PATH,
    MATCH_SCHEDULE_PATH,
)
from storage import read_json, write_json
from worldcup_simulator import load_groups


def load_match_schedule() -> dict[str, dict[str, object]]:
    if not MATCH_SCHEDULE_PATH.exists():
        return {}
    data = read_json(MATCH_SCHEDULE_PATH)
    if not isinstance(data, dict):
        return {}
    return {str(key): dict(value) for key, value in data.items() if isinstance(value, dict)}


def generate_matches() -> list[dict[str, object]]:
    groups = load_groups(GROUPS_PATH)
    schedule = load_match_schedule()
    matches: list[dict[str, object]] = []
    match_number = 1
    for group, teams in groups.items():
        for index, (home_idx, away_idx) in enumerate(GROUP_PAIRINGS, start=1):
            match_id = f"{group}-{index}"
            schedule_details = schedule.get(match_id, {})
            home_score = schedule_details.get("home_score")
            away_score = schedule_details.get("away_score")
            has_confirmed_score = home_score is not None and away_score is not None
            status = str(schedule_details.get("status") or ("finished" if has_confirmed_score else "scheduled"))
            is_confirmed = status == "finished" and has_confirmed_score
            matches.append(
                {
                    "id": match_id,
                    "match_number": int(schedule_details.get("match_number") or match_number),
                    "group": group,
                    "stage": "group",
                    "round": index,
                    "date_range": "2026-06-11 至 2026-06-28",
                    "display_date": schedule_details.get("display_date", ""),
                    "display_time": schedule_details.get("display_time", ""),
                    "home_team": teams[home_idx],
                    "away_team": teams[away_idx],
                    "home_score": int(home_score) if home_score is not None else None,
                    "away_score": int(away_score) if away_score is not None else None,
                    "status": status,
                    "source": str(schedule_details.get("source") or "schedule"),
                    "score_source": "official" if is_confirmed else "",
                    "score_locked": is_confirmed,
                    "can_edit_score": ALLOW_USER_SCORE_INPUT and not is_confirmed,
                }
            )
            match_number += 1
    for match in KNOCKOUT_MATCHES:
        display_date, display_time = KNOCKOUT_DISPLAY_TIMES.get(int(match["match_number"]), ("日期待定", ""))
        matches.append(
            dict(
                match,
                display_date=display_date,
                display_time=display_time,
                home_score=None,
                away_score=None,
                status="scheduled",
                source="schedule",
                score_source="",
                score_locked=False,
                can_edit_score=False,
            )
        )
    return matches


def load_or_create_matches() -> list[dict[str, object]]:
    return apply_user_match_overrides(load_user_match_overrides())


def load_user_match_overrides() -> list[dict[str, object]]:
    if not MATCHES_PATH.exists():
        return []
    data = read_json(MATCHES_PATH)
    if not isinstance(data, dict):
        return []
    return list(data.get("matches", []))


def save_user_match_overrides(matches: list[dict[str, object]]) -> list[dict[str, object]]:
    overrides = normalize_user_match_overrides(matches)
    write_json(MATCHES_PATH, {"matches": overrides})
    return apply_user_match_overrides(overrides)


def normalize_matches(matches: list[dict[str, object]]) -> list[dict[str, object]]:
    return apply_user_match_overrides(normalize_user_match_overrides(matches))


def normalize_user_match_overrides(matches: list[dict[str, object]]) -> list[dict[str, object]]:
    valid_ids = {match["id"]: dict(match) for match in generate_matches()}
    overrides: list[dict[str, object]] = []
    for incoming in matches:
        match_id = str(incoming.get("id", ""))
        if match_id not in valid_ids:
            continue
        base = valid_ids[match_id]
        if base.get("stage") != "group" or base.get("score_locked"):
            continue
        home_score = incoming.get("home_score")
        away_score = incoming.get("away_score")
        if home_score in {"", None} or away_score in {"", None}:
            continue
        else:
            overrides.append(
                {
                    "id": match_id,
                    "home_score": max(0, int(home_score)),
                    "away_score": max(0, int(away_score)),
                    "status": "finished",
                    "score_source": "user",
                }
            )
    return overrides


def apply_user_match_overrides(overrides: list[dict[str, object]]) -> list[dict[str, object]]:
    valid_ids = {match["id"]: dict(match) for match in generate_matches()}
    for override in normalize_user_match_overrides(overrides):
        match_id = str(override.get("id", ""))
        base = valid_ids.get(match_id)
        if not base or base.get("score_locked") or not ALLOW_USER_SCORE_INPUT:
            continue
        base["home_score"] = int(override["home_score"])
        base["away_score"] = int(override["away_score"])
        base["status"] = "finished"
        base["score_source"] = "user"
        base["source"] = "user"
        base["can_edit_score"] = True
    return list(valid_ids.values())


def fixed_scores_from_matches(
    matches: list[dict[str, object]],
) -> dict[str, dict[tuple[str, str], tuple[int, int]]]:
    fixed: dict[str, dict[tuple[str, str], tuple[int, int]]] = defaultdict(dict)
    for match in matches:
        if match.get("status") != "finished":
            continue
        home_score = match.get("home_score")
        away_score = match.get("away_score")
        if home_score is None or away_score is None:
            continue
        group = str(match["group"])
        home = str(match["home_team"])
        away = str(match["away_team"])
        fixed[group][(home, away)] = (int(home_score), int(away_score))
    return dict(fixed)
