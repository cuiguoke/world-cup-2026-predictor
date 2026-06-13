from app_config import TEAM_NAMES_ZH_PATH
from storage import read_json


def load_team_names() -> dict[str, str]:
    if not TEAM_NAMES_ZH_PATH.exists():
        return {}
    data = read_json(TEAM_NAMES_ZH_PATH)
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def team_display_name(team: object) -> str:
    name = str(team)
    return load_team_names().get(name, name)


def team_model_name(team: object, groups: dict[str, list[str]] | None = None) -> str | None:
    name = str(team).strip()
    if not name or name.lower() == "unknown":
        return None
    names = load_team_names()
    if name in names:
        return name
    reverse_names = {localized: english for english, localized in names.items()}
    if name in reverse_names:
        return reverse_names[name]
    if groups:
        all_teams = {team for teams in groups.values() for team in teams}
        lowered = {team.lower(): team for team in all_teams}
        return lowered.get(name.lower())
    return None


def localize_groups(groups: dict[str, list[str]]) -> dict[str, list[str]]:
    names = load_team_names()
    return {
        group: [names.get(str(team), str(team)) for team in teams]
        for group, teams in groups.items()
    }


def localize_match(match: dict[str, object]) -> dict[str, object]:
    names = load_team_names()
    localized = dict(match)
    home = str(localized.get("home_team", ""))
    away = str(localized.get("away_team", ""))
    match_id = str(localized.get("id", ""))
    try:
        round_number = int(match_id.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        round_number = 0
    localized["home_team_name"] = names.get(home, home)
    localized["away_team_name"] = names.get(away, away)
    localized["stage"] = localized.get("stage", "group")
    stage_names = {
        "group": "小组赛",
        "r32": "32 强",
        "r16": "16 强",
        "qf": "八强",
        "sf": "四强",
        "third_place": "三四名决赛",
        "final": "决赛",
    }
    localized["stage_name"] = stage_names.get(str(localized["stage"]), "赛事")
    localized["round"] = localized.get("round", round_number)
    localized["round_name"] = localized.get("round_name") or (f"第 {localized['round']} 轮" if localized["round"] else localized["stage_name"])
    localized["home_label"] = localized["home_team_name"] if home else str(localized.get("home_slot", "待定"))
    localized["away_label"] = localized["away_team_name"] if away else str(localized.get("away_slot", "待定"))
    return localized


def localize_matches(matches: list[dict[str, object]]) -> list[dict[str, object]]:
    return [localize_match(match) for match in matches]


def localize_prediction(prediction: dict[str, object]) -> dict[str, object]:
    names = load_team_names()
    localized = dict(prediction)
    localized["rows"] = [
        {**dict(row), "team_name": names.get(str(row.get("team", "")), str(row.get("team", "")))}
        for row in prediction.get("rows", [])
    ]
    localized["teamNames"] = names
    return localized
