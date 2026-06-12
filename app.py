#!/usr/bin/env python3
"""
Local web app for the World Cup AI Predictor MVP.

Phase 1 intentionally uses only Python's standard library. It serves a small
single-page app and exposes basic JSON APIs for status and official groups.
"""

from __future__ import annotations

import json
import mimetypes
import random
import socket
import ssl
import sys
import urllib.error
import urllib.request
import webbrowser
from collections import defaultdict
from datetime import date, datetime
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from worldcup_ai_repro import (
    build_elo,
    load_groups,
    load_matches,
    recent_goal_base,
    simulate_tournament,
    summarize_counts,
)


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
DATA_ROOT = ROOT / "data"
APP_DATA_ROOT = ROOT / "app_data"
GROUPS_PATH = DATA_ROOT / "groups_2026.json"
TEAM_NAMES_ZH_PATH = DATA_ROOT / "team_names_zh.json"
MATCHES_PATH = APP_DATA_ROOT / "matches.json"
SOURCES_PATH = APP_DATA_ROOT / "sources.json"
FACTORS_PATH = APP_DATA_ROOT / "factors.json"
REPORTS_ROOT = APP_DATA_ROOT / "reports"
SAMPLE_RESULTS_PATH = DATA_ROOT / "sample_results.csv"
FULL_RESULTS_PATH = DATA_ROOT / "results.csv"

GROUP_PAIRINGS = [(0, 1), (2, 3), (0, 2), (3, 1), (3, 0), (1, 2)]
LLM_CONFIG: dict[str, str] = {}


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def app_log(event: str, **fields: object) -> None:
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"[app] {datetime.now().isoformat(timespec='seconds')} {event} {details}".rstrip(), flush=True)


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
    localized["home_team_name"] = names.get(home, home)
    localized["away_team_name"] = names.get(away, away)
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


def factor_rating_delta(factor: dict[str, object]) -> int:
    direction = str(factor.get("direction", "neutral")).lower()
    if direction not in {"positive", "negative"}:
        return 0
    severity = str(factor.get("severity", "low")).lower()
    base_by_severity = {"low": 10, "medium": 25, "high": 45}
    base = base_by_severity.get(severity, 10)
    try:
        confidence = float(factor.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0
    confidence = max(0.0, min(confidence, 1.0))
    delta = round(base * confidence)
    return delta if direction == "positive" else -delta


def enrich_factor(factor: dict[str, object]) -> dict[str, object]:
    enriched = dict(factor)
    groups = load_groups(GROUPS_PATH) if GROUPS_PATH.exists() else None
    team = team_model_name(enriched.get("team", ""), groups)
    if team:
        enriched["team"] = team
        enriched["team_name"] = team_display_name(team)
    else:
        enriched["team_name"] = str(enriched.get("team", "unknown"))
    delta = factor_rating_delta(enriched)
    enriched["rating_adjustment"] = delta
    enriched["applied_to_model"] = delta != 0 and team is not None
    return enriched


def enriched_factors() -> list[dict[str, object]]:
    return [enrich_factor(factor) for factor in load_factors()]


def build_factor_adjustments(
    factors: list[dict[str, object]],
    groups: dict[str, list[str]],
) -> tuple[dict[str, int], list[dict[str, object]]]:
    totals: dict[str, int] = defaultdict(int)
    applied: list[dict[str, object]] = []
    for factor in factors:
        factor = enrich_factor(factor)
        team = team_model_name(factor.get("team", ""), groups)
        if not team:
            continue
        delta = factor_rating_delta(factor)
        if delta == 0:
            continue
        totals[team] += delta
        applied.append(
            {
                "factor_id": factor.get("id", ""),
                "team": team,
                "team_name": team_display_name(team),
                "delta": delta,
                "direction": factor.get("direction", "neutral"),
                "severity": factor.get("severity", "low"),
                "confidence": factor.get("confidence", 0),
                "evidence": factor.get("evidence", ""),
                "source_url": factor.get("source_url", ""),
            }
        )
    capped = {team: max(-60, min(60, delta)) for team, delta in totals.items()}
    for item in applied:
        team = str(item["team"])
        item["team_total_delta"] = capped.get(team, 0)
    return capped, applied


def llm_status() -> str:
    required = ["base_url", "api_key", "model"]
    return "configured" if all(LLM_CONFIG.get(key) for key in required) else "not_configured"


def public_llm_config() -> dict[str, object]:
    return {
        "configured": llm_status() == "configured",
        "base_url": LLM_CONFIG.get("base_url", ""),
        "model": LLM_CONFIG.get("model", ""),
        "api_key_present": bool(LLM_CONFIG.get("api_key")),
        "verify_ssl": LLM_CONFIG.get("verify_ssl", "true") != "false",
    }


def normalize_base_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if not base:
        raise ValueError("请填写 Base URL。")
    if not base.startswith(("http://", "https://")):
        raise ValueError("Base URL 必须以 http:// 或 https:// 开头。")
    return base


def readable_http_error(exc: urllib.error.HTTPError) -> str:
    detail = exc.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(detail)
        if isinstance(parsed, dict):
            error = parsed.get("error", parsed)
            if isinstance(error, dict):
                message = error.get("message") or error.get("type") or error
                code = error.get("code")
                if code:
                    return f"LLM 服务返回 HTTP {exc.code}: {message}（{code}）"
                return f"LLM 服务返回 HTTP {exc.code}: {message}"
            return f"LLM 服务返回 HTTP {exc.code}: {error}"
    except json.JSONDecodeError:
        pass
    return f"LLM 服务返回 HTTP {exc.code}: {detail[:300]}"


def ssl_context(verify_ssl: bool) -> ssl.SSLContext | None:
    if not verify_ssl:
        return ssl._create_unverified_context()
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def readable_url_error(exc: urllib.error.URLError) -> str:
    reason = str(exc.reason)
    if "CERTIFICATE_VERIFY_FAILED" in reason:
        return (
            "无法连接到 LLM 服务：本机无法确认这个 HTTPS 服务的身份。"
            "请先确认 Base URL 来自官方或你信任的服务；如果确认可信，"
            "可以勾选“跳过 SSL 证书验证”后重试。"
        )
    return f"无法连接到 LLM 服务：{reason}"


def post_llm_payload(
    base_url: str,
    api_key: str,
    payload: dict[str, object],
    *,
    timeout: int,
    verify_ssl: bool,
) -> tuple[dict[str, object], bool]:
    body = json.dumps(payload).encode("utf-8")
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    def send(should_verify_ssl: bool) -> dict[str, object]:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(
            request,
            timeout=timeout,
            context=ssl_context(should_verify_ssl),
        ) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)

    return send(verify_ssl), verify_ssl


def test_llm_connection(config: dict[str, object]) -> dict[str, object]:
    base_url = normalize_base_url(str(config.get("base_url", "")))
    api_key = str(config.get("api_key", "")).strip()
    model = str(config.get("model", "")).strip()
    verify_ssl = bool(config.get("verify_ssl", True))
    if not api_key:
        raise ValueError("请填写 API Key。")
    if not model:
        raise ValueError("请填写模型名。")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a connection test endpoint. Reply briefly.",
            },
            {"role": "user", "content": "Reply with OK."},
        ],
        "temperature": 0,
        "max_tokens": 8,
        "stream": False,
    }
    try:
        data, used_verify_ssl = post_llm_payload(
            base_url,
            api_key,
            payload,
            timeout=20,
            verify_ssl=verify_ssl,
        )
    except urllib.error.HTTPError as exc:
        raise RuntimeError(readable_http_error(exc)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(readable_url_error(exc)) from exc
    except TimeoutError as exc:
        raise RuntimeError("连接 LLM 服务超时。") from exc

    LLM_CONFIG.clear()
    LLM_CONFIG.update(
        {
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
            "verify_ssl": "true" if used_verify_ssl else "false",
        }
    )
    message = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    return {
        "ok": True,
        "message": (
            (message or "连接成功。")
            if used_verify_ssl
            else f"{message or '连接成功。'}（已按你的选择跳过 SSL 证书验证）"
        ),
        "config": public_llm_config(),
    }


def call_llm_json(messages: list[dict[str, str]], max_tokens: int = 900) -> dict[str, object]:
    if llm_status() != "configured":
        raise ValueError("LLM 尚未配置。请先在设置页测试连接。")

    payload = {
        "model": LLM_CONFIG["model"],
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        data, used_verify_ssl = post_llm_payload(
            LLM_CONFIG["base_url"],
            LLM_CONFIG["api_key"],
            payload,
            timeout=60,
            verify_ssl=LLM_CONFIG.get("verify_ssl", "true") != "false",
        )
        LLM_CONFIG["verify_ssl"] = "true" if used_verify_ssl else "false"
    except urllib.error.HTTPError as exc:
        raise RuntimeError(readable_http_error(exc)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(readable_url_error(exc)) from exc

    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM 没有返回合法 JSON：{content[:300]}") from exc


def load_sources() -> list[dict[str, object]]:
    if not SOURCES_PATH.exists():
        return []
    return list(read_json(SOURCES_PATH).get("sources", []))


def load_factors() -> list[dict[str, object]]:
    if not FACTORS_PATH.exists():
        return []
    return list(read_json(FACTORS_PATH).get("factors", []))


def fetch_url_text(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("信息源 URL 必须以 http:// 或 https:// 开头。")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "WorldCupAIPredictor/0.1 (+local user app)",
            "Accept": "text/html,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read(300_000)
    text = raw.decode("utf-8", errors="replace")
    return text, content_type


def strip_html(text: str) -> str:
    # A lightweight cleanup is enough for MVP; users can paste clean text when needed.
    import re

    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def create_source(payload: dict[str, object]) -> dict[str, object]:
    sources = load_sources()
    source_id = f"src_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(sources) + 1}"
    source_type = str(payload.get("type", "news"))
    url = str(payload.get("url", "")).strip()
    manual_text = str(payload.get("text", "")).strip()
    title = str(payload.get("title", "")).strip() or "未命名信息源"
    fetch_status = "manual"
    content_type = "text/plain"
    warning = ""

    if not manual_text and url:
        try:
            fetched, content_type = fetch_url_text(url)
            manual_text = strip_html(fetched)
            fetch_status = "success"
        except Exception as exc:
            fetch_status = "failed"
            warning = str(exc)

    if not manual_text:
        raise ValueError(warning or "请填写正文，或提供可访问的 URL。")

    source = {
        "id": source_id,
        "url": url,
        "type": source_type,
        "title": title,
        "text": manual_text[:12000],
        "fetch_status": fetch_status,
        "content_type": content_type,
        "warning": warning,
        "added_at": datetime.now().isoformat(timespec="seconds"),
    }
    sources.append(source)
    write_json(SOURCES_PATH, {"sources": sources})
    app_log("source.created", source_id=source_id, type=source_type, fetch_status=fetch_status, has_url=bool(url))
    return source


def delete_source(source_id: str) -> dict[str, object]:
    sources = load_sources()
    remaining_sources = [source for source in sources if source.get("id") != source_id]
    if len(remaining_sources) == len(sources):
        raise ValueError("找不到这个信息源。")

    factors = load_factors()
    remaining_factors = [factor for factor in factors if factor.get("source_id") != source_id]
    write_json(SOURCES_PATH, {"sources": remaining_sources})
    write_json(FACTORS_PATH, {"factors": remaining_factors})
    deleted_factors = len(factors) - len(remaining_factors)
    app_log("source.deleted", source_id=source_id, deleted_factors=deleted_factors)
    return {
        "deleted": True,
        "source_id": source_id,
        "deleted_factors": deleted_factors,
        "sources": remaining_sources,
        "factors": enriched_factors(),
    }


def extract_factors(source_id: str) -> dict[str, object]:
    sources = load_sources()
    source = next((item for item in sources if item.get("id") == source_id), None)
    if not source:
        raise ValueError("找不到这个信息源。")
    app_log("factors.extract.start", source_id=source_id, title=source.get("title", ""))
    groups = load_groups(GROUPS_PATH)

    messages = [
        {
            "role": "system",
            "content": (
                "你是足球赛事信息分析助手。只根据用户提供的信息源正文提取影响因素。"
                "不要编造正文没有的信息。不要给博彩建议。"
                "必须只输出 JSON，格式为 {\"factors\":[...],\"summary\":\"...\",\"warnings\":[...] }。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "source_id": source["id"],
                    "source_title": source["title"],
                    "source_type": source["type"],
                    "source_url": source["url"],
                    "schema": {
                        "team": "球队名或 unknown",
                        "match": "相关比赛或 null",
                        "category": "weather|injury|lineup|fatigue|travel|form|other",
                        "direction": "positive|negative|neutral",
                        "severity": "low|medium|high",
                        "confidence": "0 到 1 的数字",
                        "evidence": "来自正文的简短证据",
                        "source_url": "来源 URL",
                    },
                    "text": str(source["text"])[:9000],
                },
                ensure_ascii=False,
            ),
        },
    ]
    extracted = call_llm_json(messages)
    new_factors = []
    for index, factor in enumerate(extracted.get("factors", []), start=1):
        if not isinstance(factor, dict):
            continue
        normalized_factor = {
            "id": f"factor_{source_id}_{index}",
            "source_id": source_id,
            "team": str(factor.get("team", "unknown")),
            "match": factor.get("match"),
            "category": str(factor.get("category", "other")),
            "direction": str(factor.get("direction", "neutral")),
            "severity": str(factor.get("severity", "low")),
            "confidence": float(factor.get("confidence", 0)),
            "evidence": str(factor.get("evidence", "")),
            "source_url": str(source.get("url", "")),
        }
        model_team = team_model_name(normalized_factor["team"], groups)
        if model_team:
            normalized_factor["team"] = model_team
        normalized_factor["rating_adjustment"] = factor_rating_delta(normalized_factor)
        normalized_factor["applied_to_model"] = normalized_factor["rating_adjustment"] != 0 and model_team is not None
        normalized_factor["team_name"] = team_display_name(model_team) if model_team else str(normalized_factor["team"])
        new_factors.append(
            {
                **normalized_factor,
                "approved_by_user": True,
            }
        )

    existing = [factor for factor in load_factors() if factor.get("source_id") != source_id]
    all_factors = existing + new_factors
    write_json(FACTORS_PATH, {"factors": all_factors})
    app_log("factors.extract.done", source_id=source_id, factor_count=len(new_factors))
    return {
        "source_id": source_id,
        "summary": extracted.get("summary", ""),
        "warnings": extracted.get("warnings", []),
        "factors": new_factors,
    }


def generate_matches() -> list[dict[str, object]]:
    groups = load_groups(GROUPS_PATH)
    matches: list[dict[str, object]] = []
    for group, teams in groups.items():
        for index, (home_idx, away_idx) in enumerate(GROUP_PAIRINGS, start=1):
            matches.append(
                {
                    "id": f"{group}-{index}",
                    "group": group,
                    "home_team": teams[home_idx],
                    "away_team": teams[away_idx],
                    "home_score": None,
                    "away_score": None,
                    "status": "scheduled",
                    "source": "user",
                }
            )
    return matches


def load_or_create_matches() -> list[dict[str, object]]:
    if MATCHES_PATH.exists():
        return list(read_json(MATCHES_PATH).get("matches", []))
    matches = generate_matches()
    write_json(MATCHES_PATH, {"matches": matches})
    return matches


def normalize_matches(matches: list[dict[str, object]]) -> list[dict[str, object]]:
    valid_ids = {match["id"]: dict(match) for match in generate_matches()}
    for incoming in matches:
        match_id = str(incoming.get("id", ""))
        if match_id not in valid_ids:
            continue
        base = valid_ids[match_id]
        home_score = incoming.get("home_score")
        away_score = incoming.get("away_score")
        if home_score in {"", None} or away_score in {"", None}:
            base["home_score"] = None
            base["away_score"] = None
            base["status"] = "scheduled"
        else:
            base["home_score"] = max(0, int(home_score))
            base["away_score"] = max(0, int(away_score))
            base["status"] = "finished"
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

    rows = summarize_counts(counts, simulations)
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
    return localize_prediction({
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
    })


def pct(value: object) -> str:
    number = float(value or 0)
    return f"{number * 100:.1f}%" if number >= 0.1 else f"{number * 100:.2f}%"


def fallback_report_text(prediction: dict[str, object], factors: list[dict[str, object]]) -> dict[str, object]:
    rows = list(prediction.get("rows", []))
    top = rows[0] if rows else {"team": "暂无数据", "champion": 0}
    top_name = str(top.get("team_name") or top.get("team") or "暂无数据")
    return {
        "headline": f"{top_name} 暂列夺冠概率榜首",
        "summary": (
            f"本次报告基于 {prediction.get('simulations')} 次本地模拟生成。"
            f"当前最高夺冠概率为 {pct(top.get('champion'))}。"
            f"系统已记录 {prediction.get('finishedMatches')} 场已结束比分，"
            f"并将 {prediction.get('aiFactorsApplied', 0)} 条 AI 信息源影响因子纳入模型微调。"
        ),
        "uncertainties": [
            "足球比赛具有高随机性，概率不是确定结论。",
            "AI 影响因子来自用户指定信息源，并通过固定规则转成小幅 Elo 调整。",
            "如果使用样例历史数据，结果只能用于流程验证。"
        ],
    }


def llm_report_text(prediction: dict[str, object], factors: list[dict[str, object]]) -> dict[str, object]:
    if llm_status() != "configured":
        return fallback_report_text(prediction, factors)

    messages = [
        {
            "role": "system",
            "content": (
                "你是世界杯预测报告撰写助手。只根据给定预测数据和影响因子写报告。"
                "不要编造伤病、天气、阵容或实时事实。不要给博彩建议。"
                "必须输出 JSON：headline, summary, top_contenders, uncertainties。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "prediction_top_10": list(prediction.get("rows", []))[:10],
                    "finished_matches": prediction.get("finishedMatches"),
                    "simulations": prediction.get("simulations"),
                    "factors": factors[:20],
                },
                ensure_ascii=False,
            ),
        },
    ]
    try:
        result = call_llm_json(messages, max_tokens=1200)
    except Exception:
        return fallback_report_text(prediction, factors)
    return {
        "headline": str(result.get("headline", "")) or "2026 世界杯预测报告",
        "summary": str(result.get("summary", "")),
        "top_contenders": result.get("top_contenders", []),
        "uncertainties": result.get("uncertainties", []),
    }


def report_team_name(row: dict[str, object]) -> str:
    return str(row.get("team_name") or row.get("team") or "")


def report_number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def report_heat_color(value: float) -> str:
    value = max(0.0, min(value, 1.0))
    if value >= 0.75:
        return "#1d4ed8"
    if value >= 0.5:
        return "#3b82f6"
    if value >= 0.25:
        return "#93c5fd"
    if value >= 0.1:
        return "#dbeafe"
    return "#f3f7fb"


def render_champion_bar_chart(rows: list[dict[str, object]]) -> str:
    chart_rows = rows[:10]
    if not chart_rows:
        return '<p class="muted">暂无可视化数据。</p>'

    row_height = 42
    width = 940
    left = 116
    bar_width = 610
    height = 38 + len(chart_rows) * row_height
    max_value = max([report_number(row.get("champion")) for row in chart_rows] + [0.01])
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="夺冠概率排行条形图">',
        '<text x="0" y="18" class="chart-title">夺冠概率排行</text>',
    ]
    for index, row in enumerate(chart_rows):
        y = 36 + index * row_height
        value = report_number(row.get("champion"))
        bar = 0 if max_value == 0 else value / max_value * bar_width
        name = escape(report_team_name(row))
        parts.extend(
            [
                f'<text x="0" y="{y + 18}" class="chart-label">{name}</text>',
                f'<rect x="{left}" y="{y}" width="{bar_width}" height="24" rx="5" class="chart-track"></rect>',
                f'<rect x="{left}" y="{y}" width="{bar:.1f}" height="24" rx="5" class="chart-bar"></rect>',
                f'<text x="{left + bar_width + 16}" y="{y + 18}" class="chart-value">{pct(value)}</text>',
            ]
        )
    parts.append("</svg>")
    return "\n".join(parts)


def render_stage_heatmap(rows: list[dict[str, object]]) -> str:
    heat_rows = rows[:12]
    if not heat_rows:
        return '<p class="muted">暂无阶段概率数据。</p>'

    stages = [
        ("champion", "夺冠"),
        ("final", "决赛"),
        ("sf", "四强"),
        ("qf", "八强"),
        ("r16", "16强"),
        ("r32", "32强"),
    ]
    cell_w = 82
    cell_h = 34
    left = 110
    top = 42
    width = left + len(stages) * cell_w + 16
    height = top + (len(heat_rows) + 1) * cell_h + 16
    parts = [
        f'<svg class="chart heatmap" viewBox="0 0 {width} {height}" role="img" aria-label="阶段概率热力图">',
        '<text x="0" y="18" class="chart-title">阶段概率热力图</text>',
    ]
    for stage_index, (_, label) in enumerate(stages):
        x = left + stage_index * cell_w
        parts.append(f'<text x="{x + cell_w / 2:.1f}" y="{top - 10}" class="heat-head">{label}</text>')
    for row_index, row in enumerate(heat_rows):
        y = top + row_index * cell_h
        parts.append(f'<text x="0" y="{y + 22}" class="chart-label">{escape(report_team_name(row))}</text>')
        for stage_index, (key, _) in enumerate(stages):
            value = report_number(row.get(key))
            x = left + stage_index * cell_w
            color = report_heat_color(value)
            text_color = "#ffffff" if value >= 0.5 else "#1f2a37"
            parts.extend(
                [
                    f'<rect x="{x}" y="{y}" width="{cell_w - 8}" height="{cell_h - 7}" rx="5" fill="{color}"></rect>',
                    f'<text x="{x + (cell_w - 8) / 2:.1f}" y="{y + 19}" fill="{text_color}" class="heat-value">{pct(value)}</text>',
                ]
            )
    parts.append("</svg>")
    return "\n".join(parts)


def render_adjustment_cards(prediction: dict[str, object]) -> str:
    adjustments = list(prediction.get("ratingAdjustments", []))
    if not adjustments:
        return '<p class="muted">本次预测没有可应用的 AI 模型调整。</p>'
    items = []
    for item in adjustments:
        delta = int(item.get("delta", 0))
        sign = "+" if delta > 0 else ""
        tone = "positive" if delta > 0 else "negative"
        items.append(
            f"""
            <li class="adjustment {tone}">
              <strong>{escape(str(item.get('team_name') or item.get('team')))}</strong>
              <span>{sign}{delta} Elo</span>
            </li>
            """
        )
    return f'<ul class="adjustment-list">{"".join(items)}</ul>'


def render_report_html(
    prediction: dict[str, object],
    sources: list[dict[str, object]],
    factors: list[dict[str, object]],
    narrative: dict[str, object],
) -> str:
    rows = list(prediction.get("rows", []))[:16]
    champion_chart = render_champion_bar_chart(rows)
    heatmap = render_stage_heatmap(rows)
    adjustment_cards = render_adjustment_cards(prediction)
    top_cards = "\n".join(
        f"""
        <tr>
          <td>{escape(str(row.get('team_name') or row.get('team', '')))}</td>
          <td>{pct(row.get('champion'))}</td>
          <td>{pct(row.get('final'))}</td>
          <td>{pct(row.get('sf'))}</td>
          <td>{pct(row.get('qf'))}</td>
        </tr>
        """
        for row in rows
    )
    factor_items = "\n".join(
        f"""
        <li>
          <strong>{escape(team_display_name(factor.get('team', 'unknown')))}</strong>
          <span>{escape(str(factor.get('category', 'other')))} · {escape(str(factor.get('direction', 'neutral')))} · 置信度 {pct(float(factor.get('confidence', 0)))}</span>
          <p>{escape(str(factor.get('evidence', '')))}</p>
        </li>
        """
        for factor in factors[:12]
    ) or "<li><p>暂无 AI 提取影响因子。</p></li>"
    source_items = "\n".join(
        f"<li>{escape(str(source.get('title', '未命名信息源')))} <span>{escape(str(source.get('type', 'other')))}</span></li>"
        for source in sources
    ) or "<li>暂无信息源。</li>"
    uncertainties = narrative.get("uncertainties", [])
    uncertainty_items = "\n".join(f"<li>{escape(str(item))}</li>" for item in uncertainties)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(str(narrative.get('headline', '2026 世界杯预测报告')))}</title>
  <style>
    body {{ margin:0; background:#f5f7fb; color:#16211f; font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif; line-height:1.6; }}
    main {{ max-width:1120px; margin:0 auto; padding:34px 22px 48px; }}
    h1 {{ margin:0 0 10px; font-size:30px; }}
    h2 {{ margin:26px 0 10px; font-size:20px; }}
    p, li, td, th {{ font-size:14px; }}
    .muted, span {{ color:#63736e; }}
    .panel {{ background:#fff; border:1px solid #dce3ee; border-radius:8px; padding:18px; margin-top:16px; box-shadow:0 10px 26px rgba(22,32,48,.05); }}
    .visual-grid {{ display:grid; grid-template-columns:minmax(0,1.08fr) minmax(360px,.92fr); gap:16px; align-items:start; }}
    .chart {{ display:block; width:100%; height:auto; overflow:visible; }}
    .chart-title {{ font-size:16px; font-weight:800; fill:#172033; }}
    .chart-label {{ font-size:13px; font-weight:700; fill:#263447; }}
    .chart-value {{ font-size:13px; font-weight:800; fill:#1d4ed8; }}
    .chart-track {{ fill:#eef3f8; }}
    .chart-bar {{ fill:#2563eb; }}
    .heat-head {{ font-size:12px; font-weight:800; fill:#526172; text-anchor:middle; }}
    .heat-value {{ font-size:12px; font-weight:800; text-anchor:middle; }}
    .adjustment-list {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; padding:0; list-style:none; }}
    .adjustment {{ border:1px solid #dce3ee; border-radius:8px; padding:10px 12px; background:#f8fafc; }}
    .adjustment strong {{ display:block; }}
    .adjustment span {{ font-weight:800; }}
    .adjustment.positive span {{ color:#047857; }}
    .adjustment.negative span {{ color:#b45309; }}
    table {{ width:100%; border-collapse:collapse; background:#fff; }}
    th, td {{ padding:10px; border-bottom:1px solid #dce7e3; text-align:right; }}
    th:first-child, td:first-child {{ text-align:left; font-weight:700; }}
    ul {{ margin:0; padding-left:20px; }}
    li {{ margin:8px 0; }}
    @media (max-width: 860px) {{ .visual-grid {{ grid-template-columns:1fr; }} main {{ padding:24px 14px 38px; }} }}
  </style>
</head>
<body>
  <main>
    <p class="muted">本地生成 · {escape(str(prediction.get('createdAt', '')))}</p>
    <h1>{escape(str(narrative.get('headline', '2026 世界杯预测报告')))}</h1>
    <p>{escape(str(narrative.get('summary', '')))}</p>

    <section class="panel">
      <h2>图形化预测结果</h2>
      <p>模拟次数：{escape(str(prediction.get('simulations')))}；已纳入比分：{escape(str(prediction.get('finishedMatches')))} 场；AI 影响因子：{escape(str(prediction.get('aiFactorsApplied', 0)))} 条；历史数据：{escape(str(prediction.get('historySource')))}。</p>
      <div class="visual-grid">
        <div>{champion_chart}</div>
        <div>{heatmap}</div>
      </div>
    </section>

    <section class="panel">
      <h2>AI 模型调整</h2>
      {adjustment_cards}
    </section>

    <section class="panel">
      <h2>预测明细</h2>
      <table>
        <thead><tr><th>球队</th><th>夺冠</th><th>进决赛</th><th>进四强</th><th>进八强</th></tr></thead>
        <tbody>{top_cards}</tbody>
      </table>
    </section>

    <section class="panel">
      <h2>AI 信息源影响因子</h2>
      <ul>{factor_items}</ul>
    </section>

    <section class="panel">
      <h2>使用的信息源</h2>
      <ul>{source_items}</ul>
    </section>

    <section class="panel">
      <h2>不确定性</h2>
      <ul>{uncertainty_items}</ul>
    </section>
  </main>
</body>
</html>
"""


def generate_report(simulations: int = 1000) -> dict[str, object]:
    app_log("report.generate.start", simulations=simulations)
    prediction = run_prediction(simulations)
    sources = load_sources()
    factors = enriched_factors()
    narrative = llm_report_text(prediction, factors)
    html = render_report_html(prediction, sources, factors, narrative)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    report_name = f"worldcup_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    report_path = REPORTS_ROOT / report_name
    report_path.write_text(html, encoding="utf-8")
    app_log("report.generate.done", path=report_path.relative_to(ROOT))
    return {
        "report": {
            "title": narrative.get("headline", "2026 世界杯预测报告"),
            "url": f"/reports/{report_name}",
            "path": str(report_path.relative_to(ROOT)),
            "createdAt": prediction.get("createdAt"),
        },
        "prediction": prediction,
    }


def app_status() -> dict[str, object]:
    groups_ok = GROUPS_PATH.exists()
    team_count = 0
    if groups_ok:
        groups = read_json(GROUPS_PATH)
        team_count = sum(len(teams) for teams in groups.values())
    results_path = FULL_RESULTS_PATH if FULL_RESULTS_PATH.exists() else SAMPLE_RESULTS_PATH

    return {
        "app": "2026 世界杯 AI 预测助手",
        "phase": "MVP Phase 5",
        "groupsLoaded": groups_ok,
        "teamCount": team_count,
        "llmStatus": llm_status(),
        "dataMode": "official_groups_full_history" if results_path == FULL_RESULTS_PATH else "official_groups_sample_results",
        "historySource": str(results_path.relative_to(ROOT)),
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
    }


class AppHandler(BaseHTTPRequestHandler):
    server_version = "WorldCupAIPredictor/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[web] {self.address_string()} - {fmt % args}")

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body_json(self) -> object:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        content_type, _ = mimetypes.guess_type(str(path))
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        app_log("http.get", path=path)

        if path == "/api/status":
            self.send_json(app_status())
            return

        if path == "/api/groups":
            if not GROUPS_PATH.exists():
                self.send_json({"error": "groups_2026.json not found"}, HTTPStatus.NOT_FOUND)
                return
            groups = load_groups(GROUPS_PATH)
            self.send_json({"groups": localize_groups(groups), "teamNames": load_team_names()})
            return

        if path == "/api/matches":
            self.send_json({"matches": localize_matches(load_or_create_matches())})
            return

        if path == "/api/llm/config":
            self.send_json(public_llm_config())
            return

        if path == "/api/sources":
            self.send_json({"sources": load_sources()})
            return

        if path == "/api/factors":
            self.send_json({"factors": enriched_factors()})
            return

        if path.startswith("/reports/"):
            requested = (REPORTS_ROOT / path.removeprefix("/reports/")).resolve()
            if REPORTS_ROOT not in requested.parents and requested != REPORTS_ROOT:
                self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return
            self.send_file(requested)
            return

        if path in {"/", "/index.html"}:
            self.send_file(WEB_ROOT / "index.html")
            return

        requested = (WEB_ROOT / path.lstrip("/")).resolve()
        if WEB_ROOT not in requested.parents and requested != WEB_ROOT:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return
        self.send_file(requested)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        app_log("http.post", path=path)

        try:
            if path == "/api/matches":
                payload = self.read_body_json()
                matches = normalize_matches(list(payload.get("matches", [])))
                write_json(MATCHES_PATH, {"matches": matches})
                finished_count = sum(1 for match in matches if match.get("status") == "finished")
                app_log("matches.saved", total=len(matches), finished=finished_count)
                self.send_json({"matches": localize_matches(matches)})
                return

            if path == "/api/predict":
                payload = self.read_body_json()
                simulations = int(payload.get("simulations", 1000))
                simulations = max(100, min(simulations, 10000))
                self.send_json(run_prediction(simulations))
                return

            if path == "/api/llm/test":
                payload = self.read_body_json()
                app_log("llm.test.start", base_url=payload.get("base_url", ""), model=payload.get("model", ""))
                self.send_json(test_llm_connection(dict(payload)))
                app_log("llm.test.done", model=payload.get("model", ""))
                return

            if path == "/api/sources":
                payload = self.read_body_json()
                source = create_source(dict(payload))
                self.send_json({"source": source, "sources": load_sources()})
                return

            if path.startswith("/api/sources/") and path.endswith("/extract"):
                source_id = path.removeprefix("/api/sources/").removesuffix("/extract")
                self.send_json(extract_factors(source_id))
                return

            if path == "/api/report/generate":
                payload = self.read_body_json()
                simulations = int(payload.get("simulations", 1000))
                simulations = max(100, min(simulations, 10000))
                self.send_json(generate_report(simulations))
                return

            self.send_error(HTTPStatus.NOT_FOUND, "API not found")
        except Exception as exc:
            app_log("http.error", path=path, error=str(exc))
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        app_log("http.delete", path=path)

        try:
            if path.startswith("/api/sources/"):
                source_id = path.removeprefix("/api/sources/")
                if not source_id or "/" in source_id:
                    self.send_error(HTTPStatus.NOT_FOUND, "API not found")
                    return
                self.send_json(delete_source(source_id))
                return

            self.send_error(HTTPStatus.NOT_FOUND, "API not found")
        except Exception as exc:
            app_log("http.error", path=path, error=str(exc))
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)


def find_free_port(start: int = 8765) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No free local port found.")


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    url = f"http://127.0.0.1:{port}"
    print(f"World Cup AI Predictor running at {url}")
    print("Press Ctrl+C to stop.")
    try:
        webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
