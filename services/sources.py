import json
import urllib.request
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse

from app_config import FACTORS_PATH, GROUPS_PATH, SOURCES_PATH
from services.llm import call_llm_json
from services.teams import team_display_name, team_model_name
from storage import app_log, read_json, write_json
from worldcup_simulator import load_groups


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
                "created_at": datetime.now().isoformat(timespec="seconds"),
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
