from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app_config import (
    APP_MODE,
    PREDICTION_MODEL_VERSION,
    ROOT,
    SNAPSHOT_MAX_FILES,
    SNAPSHOT_MAX_TOTAL_BYTES,
    SNAPSHOTS_ROOT,
)
from services.teams import team_display_name
from storage import app_log, read_json


def snapshot_files() -> list[Path]:
    if not SNAPSHOTS_ROOT.exists():
        return []
    return sorted(
        [path for path in SNAPSHOTS_ROOT.glob("*.json") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
    )


def snapshot_id_from_time(created_at: datetime) -> str:
    return f"{created_at.strftime('%Y%m%dT%H%M%S%f')}-{PREDICTION_MODEL_VERSION}"


def snapshot_path(snapshot_id: str) -> Path:
    safe_id = "".join(ch for ch in snapshot_id if ch.isalnum() or ch in {"-", "_", "T"})
    if not safe_id or safe_id != snapshot_id:
        raise ValueError("invalid snapshot id")
    return SNAPSHOTS_ROOT / f"{safe_id}.json"


def known_scores_from_matches(matches: list[dict[str, object]]) -> list[dict[str, object]]:
    scores: list[dict[str, object]] = []
    for match in matches:
        if match.get("status") != "finished":
            continue
        home_score = match.get("home_score")
        away_score = match.get("away_score")
        if home_score is None or away_score is None:
            continue
        home = str(match.get("home_team") or "")
        away = str(match.get("away_team") or "")
        scores.append(
            {
                "match_id": match.get("id"),
                "match_number": match.get("match_number"),
                "group": match.get("group"),
                "stage": match.get("stage"),
                "display_date": match.get("display_date", ""),
                "display_time": match.get("display_time", ""),
                "home_team": home,
                "home_team_name": team_display_name(home),
                "away_team": away,
                "away_team_name": team_display_name(away),
                "home_score": int(home_score),
                "away_score": int(away_score),
                "score_source": match.get("score_source", ""),
            }
        )
    return scores


def enforce_snapshot_retention() -> dict[str, object]:
    files = snapshot_files()
    deleted: list[str] = []

    def total_size() -> int:
        return sum(path.stat().st_size for path in files if path.exists())

    while len(files) > SNAPSHOT_MAX_FILES or total_size() > SNAPSHOT_MAX_TOTAL_BYTES:
        oldest = files.pop(0)
        try:
            deleted.append(oldest.name)
            oldest.unlink()
        except OSError as exc:
            app_log("snapshot.prune_failed", file=oldest.name, error=str(exc))
            break

    return {
        "retained": len(snapshot_files()),
        "deleted": deleted,
        "max_files": SNAPSHOT_MAX_FILES,
        "max_total_bytes": SNAPSHOT_MAX_TOTAL_BYTES,
    }


def write_immutable_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def save_prediction_snapshot(
    prediction: dict[str, object],
    matches: list[dict[str, object]],
    model_params: dict[str, object],
) -> dict[str, object]:
    created_at = datetime.now().astimezone()
    snapshot_id = snapshot_id_from_time(created_at)
    path = snapshot_path(snapshot_id)
    payload = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "created_at": created_at.isoformat(timespec="seconds"),
        "app_mode": APP_MODE,
        "model_version": PREDICTION_MODEL_VERSION,
        "simulations": prediction.get("simulations"),
        "history_source": prediction.get("historySource"),
        "finished_matches": prediction.get("finishedMatches"),
        "model_params": model_params,
        "known_scores": known_scores_from_matches(matches),
        "match_predictions": prediction.get("matchPredictions", []),
        "team_stage_predictions": prediction.get("rows", []),
        "group_qualification": prediction.get("groupQualification", []),
        "rating_adjustments": prediction.get("ratingAdjustments", []),
        "applied_factors": prediction.get("appliedFactors", []),
    }
    write_immutable_json(path, payload)
    retention = enforce_snapshot_retention()
    app_log(
        "snapshot.saved",
        snapshot_id=snapshot_id,
        file=str(path.relative_to(ROOT)),
        retained=retention["retained"],
        deleted=len(retention["deleted"]),
    )
    return {
        "snapshot_id": snapshot_id,
        "created_at": payload["created_at"],
        "path": str(path.relative_to(ROOT)),
        "retention": retention,
    }


def snapshot_summary(path: Path) -> dict[str, object]:
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError):
        data = {}
    payload = dict(data) if isinstance(data, dict) else {}
    return {
        "snapshot_id": payload.get("snapshot_id") or path.stem,
        "created_at": payload.get("created_at", ""),
        "model_version": payload.get("model_version", ""),
        "simulations": payload.get("simulations"),
        "finished_matches": payload.get("finished_matches"),
        "history_source": payload.get("history_source", ""),
        "match_predictions": len(payload.get("match_predictions", [])),
        "known_scores": len(payload.get("known_scores", [])),
        "size_bytes": path.stat().st_size,
        "path": str(path.relative_to(ROOT)),
    }


def list_prediction_snapshots(limit: int = 20) -> list[dict[str, object]]:
    files = list(reversed(snapshot_files()))
    return [snapshot_summary(path) for path in files[: max(1, limit)]]


def load_prediction_snapshot(snapshot_id: str) -> dict[str, object]:
    path = snapshot_path(snapshot_id)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(snapshot_id)
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError("invalid snapshot")
    return data


def match_result_label(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def result_probability(prediction: dict[str, object], result: str) -> float:
    key = {"home": "home_win", "draw": "draw", "away": "away_win"}[result]
    return float(prediction.get(key) or 0.0)


def top_pick(prediction: dict[str, object]) -> str:
    candidates = [
        ("home", float(prediction.get("home_win") or 0.0)),
        ("draw", float(prediction.get("draw") or 0.0)),
        ("away", float(prediction.get("away_win") or 0.0)),
    ]
    return max(candidates, key=lambda item: item[1])[0]


def review_label(actual_probability: float, top_pick_hit: bool) -> str:
    if top_pick_hit:
        return "胜负预测命中"
    if actual_probability < 0.20:
        return "冷门"
    if actual_probability < 0.35:
        return "低概率结果"
    return "合理波动"


def prediction_type_for_review(prediction: dict[str, object], was_known: bool) -> str:
    prediction_type = str(prediction.get("prediction_type") or "")
    if prediction_type in {"pre_result_prediction", "post_result_explanation"}:
        return prediction_type
    return "post_result_explanation" if was_known else "pre_result_prediction"


def prediction_type_label(prediction_type: str) -> str:
    if prediction_type == "post_result_explanation":
        return "赛后复盘"
    return "赛前预测"


def build_snapshot_review(
    snapshot_id: str,
    current_matches: list[dict[str, object]],
) -> dict[str, object]:
    snapshot = load_prediction_snapshot(snapshot_id)
    current_by_id = {str(match.get("id")): dict(match) for match in current_matches}
    known_ids = {
        str(score.get("match_id"))
        for score in list(snapshot.get("known_scores", []))
        if isinstance(score, dict)
    }
    rows: list[dict[str, object]] = []

    for prediction in list(snapshot.get("match_predictions", [])):
        if not isinstance(prediction, dict):
            continue
        match_id = str(prediction.get("match_id", ""))
        current = current_by_id.get(match_id)
        if not current or current.get("status") != "finished":
            continue
        home_score = current.get("home_score")
        away_score = current.get("away_score")
        if home_score is None or away_score is None:
            continue
        actual_home_score = int(home_score)
        actual_away_score = int(away_score)
        actual_result = match_result_label(actual_home_score, actual_away_score)
        actual_probability = result_probability(prediction, actual_result)
        predicted_result = top_pick(prediction)
        was_known = match_id in known_ids
        prediction_type = prediction_type_for_review(prediction, was_known)
        top_pick_hit = predicted_result == actual_result
        rows.append(
            {
                "match_id": match_id,
                "match_number": prediction.get("match_number"),
                "group": prediction.get("group"),
                "display_date": prediction.get("display_date", ""),
                "display_time": prediction.get("display_time", ""),
                "home_team": prediction.get("home_team"),
                "home_team_name": prediction.get("home_team_name"),
                "away_team": prediction.get("away_team"),
                "away_team_name": prediction.get("away_team_name"),
                "home_win": prediction.get("home_win"),
                "draw": prediction.get("draw"),
                "away_win": prediction.get("away_win"),
                "actual_home_score": actual_home_score,
                "actual_away_score": actual_away_score,
                "actual_result": actual_result,
                "actual_probability": actual_probability,
                "predicted_result": predicted_result,
                "prediction_type": prediction_type,
                "prediction_type_label": prediction_type_label(prediction_type),
                "top_pick_hit": top_pick_hit,
                "was_known": was_known,
                "review_label": review_label(actual_probability, top_pick_hit),
                "score_source": current.get("score_source", ""),
            }
        )

    hits = [row for row in rows if row["top_pick_hit"]]
    pre_result_rows = [
        row for row in rows if row["prediction_type"] == "pre_result_prediction"
    ]
    post_result_rows = [
        row for row in rows if row["prediction_type"] == "post_result_explanation"
    ]
    pre_result_hits = [row for row in pre_result_rows if row["top_pick_hit"]]
    post_result_hits = [row for row in post_result_rows if row["top_pick_hit"]]
    probability_values = [float(row["actual_probability"]) for row in rows]
    biggest_surprise = min(
        rows,
        key=lambda row: float(row["actual_probability"]),
        default=None,
    )
    summary = {
        "finished_matches": len(rows),
        "known_at_snapshot": sum(1 for row in rows if row["was_known"]),
        "reviewed_matches": len(rows),
        "top_pick_hits": len(hits),
        "top_pick_hit_rate": len(hits) / len(rows) if rows else None,
        "pre_result_matches": len(pre_result_rows),
        "pre_result_hits": len(pre_result_hits),
        "pre_result_hit_rate": (
            len(pre_result_hits) / len(pre_result_rows) if pre_result_rows else None
        ),
        "post_result_matches": len(post_result_rows),
        "post_result_hits": len(post_result_hits),
        "post_result_hit_rate": (
            len(post_result_hits) / len(post_result_rows) if post_result_rows else None
        ),
        "average_actual_probability": (
            sum(probability_values) / len(probability_values) if probability_values else None
        ),
        "biggest_surprise": biggest_surprise,
    }
    rows.sort(key=lambda row: int(row.get("match_number") or 0))
    return {
        "snapshot": snapshot_summary(snapshot_path(str(snapshot.get("snapshot_id")))),
        "summary": summary,
        "matches": rows,
    }
