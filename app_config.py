import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
DATA_ROOT = ROOT / "data"
APP_DATA_ROOT = ROOT / "app_data"
GROUPS_PATH = DATA_ROOT / "groups_2026.json"
TEAM_NAMES_ZH_PATH = DATA_ROOT / "team_names_zh.json"
MATCH_SCHEDULE_PATH = DATA_ROOT / "match_schedule_2026.json"
MATCHES_PATH = APP_DATA_ROOT / "matches.json"
SOURCES_PATH = APP_DATA_ROOT / "sources.json"
FACTORS_PATH = APP_DATA_ROOT / "factors.json"
REPORTS_ROOT = APP_DATA_ROOT / "reports"
SAMPLE_RESULTS_PATH = DATA_ROOT / "sample_results.csv"
FULL_RESULTS_PATH = DATA_ROOT / "results.csv"

APP_MODE = os.environ.get("APP_MODE", "local").strip().lower()
if APP_MODE not in {"local", "hosted"}:
    APP_MODE = "local"
ALLOW_USER_SCORE_INPUT = APP_MODE == "local"

GROUP_PAIRINGS = [(0, 1), (2, 3), (0, 2), (3, 1), (3, 0), (1, 2)]

KNOCKOUT_MATCHES = [
    {"id": "M73", "match_number": 73, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "A 组第二", "away_slot": "B 组第二"},
    {"id": "M74", "match_number": 74, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "E 组第一", "away_slot": "A/B/C/D/F 组最佳第三"},
    {"id": "M75", "match_number": 75, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "F 组第一", "away_slot": "C 组第二"},
    {"id": "M76", "match_number": 76, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "C 组第一", "away_slot": "F 组第二"},
    {"id": "M77", "match_number": 77, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "I 组第一", "away_slot": "C/D/F/G/H 组最佳第三"},
    {"id": "M78", "match_number": 78, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "E 组第二", "away_slot": "I 组第二"},
    {"id": "M79", "match_number": 79, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "A 组第一", "away_slot": "C/E/F/H/I 组最佳第三"},
    {"id": "M80", "match_number": 80, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "L 组第一", "away_slot": "E/H/I/J/K 组最佳第三"},
    {"id": "M81", "match_number": 81, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "D 组第一", "away_slot": "B/E/F/I/J 组最佳第三"},
    {"id": "M82", "match_number": 82, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "G 组第一", "away_slot": "A/E/H/I/J 组最佳第三"},
    {"id": "M83", "match_number": 83, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "K 组第二", "away_slot": "L 组第二"},
    {"id": "M84", "match_number": 84, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "H 组第一", "away_slot": "J 组第二"},
    {"id": "M85", "match_number": 85, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "B 组第一", "away_slot": "E/F/G/I/J 组最佳第三"},
    {"id": "M86", "match_number": 86, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "J 组第一", "away_slot": "H 组第二"},
    {"id": "M87", "match_number": 87, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "K 组第一", "away_slot": "D/E/I/J/L 组最佳第三"},
    {"id": "M88", "match_number": 88, "stage": "r32", "round_name": "32 强", "date_range": "2026-06-28 至 2026-07-03", "home_slot": "D 组第二", "away_slot": "G 组第二"},
    {"id": "M89", "match_number": 89, "stage": "r16", "round_name": "16 强", "date_range": "2026-07-04 至 2026-07-07", "home_slot": "第 73 场胜者", "away_slot": "第 75 场胜者"},
    {"id": "M90", "match_number": 90, "stage": "r16", "round_name": "16 强", "date_range": "2026-07-04 至 2026-07-07", "home_slot": "第 74 场胜者", "away_slot": "第 77 场胜者"},
    {"id": "M91", "match_number": 91, "stage": "r16", "round_name": "16 强", "date_range": "2026-07-04 至 2026-07-07", "home_slot": "第 76 场胜者", "away_slot": "第 78 场胜者"},
    {"id": "M92", "match_number": 92, "stage": "r16", "round_name": "16 强", "date_range": "2026-07-04 至 2026-07-07", "home_slot": "第 79 场胜者", "away_slot": "第 80 场胜者"},
    {"id": "M93", "match_number": 93, "stage": "r16", "round_name": "16 强", "date_range": "2026-07-04 至 2026-07-07", "home_slot": "第 83 场胜者", "away_slot": "第 84 场胜者"},
    {"id": "M94", "match_number": 94, "stage": "r16", "round_name": "16 强", "date_range": "2026-07-04 至 2026-07-07", "home_slot": "第 81 场胜者", "away_slot": "第 82 场胜者"},
    {"id": "M95", "match_number": 95, "stage": "r16", "round_name": "16 强", "date_range": "2026-07-04 至 2026-07-07", "home_slot": "第 86 场胜者", "away_slot": "第 88 场胜者"},
    {"id": "M96", "match_number": 96, "stage": "r16", "round_name": "16 强", "date_range": "2026-07-04 至 2026-07-07", "home_slot": "第 85 场胜者", "away_slot": "第 87 场胜者"},
    {"id": "M97", "match_number": 97, "stage": "qf", "round_name": "八强", "date_range": "2026-07-09 至 2026-07-11", "home_slot": "第 89 场胜者", "away_slot": "第 90 场胜者"},
    {"id": "M98", "match_number": 98, "stage": "qf", "round_name": "八强", "date_range": "2026-07-09 至 2026-07-11", "home_slot": "第 93 场胜者", "away_slot": "第 94 场胜者"},
    {"id": "M99", "match_number": 99, "stage": "qf", "round_name": "八强", "date_range": "2026-07-09 至 2026-07-11", "home_slot": "第 91 场胜者", "away_slot": "第 92 场胜者"},
    {"id": "M100", "match_number": 100, "stage": "qf", "round_name": "八强", "date_range": "2026-07-09 至 2026-07-11", "home_slot": "第 95 场胜者", "away_slot": "第 96 场胜者"},
    {"id": "M101", "match_number": 101, "stage": "sf", "round_name": "四强", "date_range": "2026-07-14 至 2026-07-15", "home_slot": "第 97 场胜者", "away_slot": "第 98 场胜者"},
    {"id": "M102", "match_number": 102, "stage": "sf", "round_name": "四强", "date_range": "2026-07-14 至 2026-07-15", "home_slot": "第 99 场胜者", "away_slot": "第 100 场胜者"},
    {"id": "M103", "match_number": 103, "stage": "third_place", "round_name": "三四名决赛", "date_range": "2026-07-18", "home_slot": "第 101 场负者", "away_slot": "第 102 场负者"},
    {"id": "M104", "match_number": 104, "stage": "final", "round_name": "决赛", "date_range": "2026-07-19", "home_slot": "第 101 场胜者", "away_slot": "第 102 场胜者"},
]

KNOCKOUT_DISPLAY_TIMES = {
    73: ("6月29日", "03:00"),
    74: ("6月30日", "04:30"),
    75: ("6月30日", "09:00"),
    76: ("6月30日", "01:00"),
    77: ("7月1日", "05:00"),
    78: ("7月1日", "01:00"),
    79: ("7月1日", "09:00"),
    80: ("7月2日", "00:00"),
    81: ("7月2日", "08:00"),
    82: ("7月2日", "04:00"),
    83: ("7月3日", "07:00"),
    84: ("7月3日", "03:00"),
    85: ("7月3日", "11:00"),
    86: ("7月4日", "06:00"),
    87: ("7月4日", "09:30"),
    88: ("7月4日", "02:00"),
    89: ("7月5日", "05:00"),
    90: ("7月5日", "01:00"),
    91: ("7月6日", "04:00"),
    92: ("7月6日", "08:00"),
    93: ("7月7日", "03:00"),
    94: ("7月7日", "08:00"),
    95: ("7月8日", "00:00"),
    96: ("7月8日", "04:00"),
    97: ("7月10日", "04:00"),
    98: ("7月11日", "03:00"),
    99: ("7月12日", "05:00"),
    100: ("7月12日", "09:00"),
    101: ("7月15日", "03:00"),
    102: ("7月16日", "03:00"),
    103: ("7月19日", "05:00"),
    104: ("7月20日", "03:00"),
}
