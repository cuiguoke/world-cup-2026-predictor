from __future__ import annotations

import json
from datetime import datetime
from html import escape

from app_config import REPORTS_ROOT, ROOT
from services.llm import call_llm_json, llm_status
from services.prediction import run_prediction
from services.sources import enriched_factors, load_sources
from services.teams import team_display_name
from storage import app_log


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


def render_group_qualification_report(prediction: dict[str, object]) -> str:
    groups = list(prediction.get("groupQualification", []))
    if not groups:
        return '<p class="muted">暂无小组出线预测数据。</p>'
    tables = []
    for group in groups:
        rows = "\n".join(
            f"""
            <tr>
              <td>{escape(str(row.get('team_name') or row.get('team', '')))}</td>
              <td>{pct(row.get('first'))}</td>
              <td>{pct(row.get('top_two'))}</td>
              <td>{pct(row.get('third'))}</td>
              <td>{pct(row.get('qualified'))}</td>
            </tr>
            """
            for row in list(group.get("rows", []))
        )
        tables.append(
            f"""
            <article class="group-qualification-card">
              <h3>{escape(str(group.get('group', '')))} 组</h3>
              <table>
                <thead><tr><th>球队</th><th>头名</th><th>前二</th><th>第三</th><th>晋级</th></tr></thead>
                <tbody>{rows}</tbody>
              </table>
            </article>
            """
        )
    return f'<div class="group-qualification-grid">{"".join(tables)}</div>'


def report_stage_rows(rows: list[dict[str, object]], key: str, limit: int = 4) -> list[dict[str, object]]:
    return sorted(rows, key=lambda row: report_number(row.get(key)), reverse=True)[:limit]


def render_stage_cards_report(prediction: dict[str, object]) -> str:
    rows = list(prediction.get("rows", []))
    group_rows = []
    for group in list(prediction.get("groupQualification", [])):
        leaders = sorted(
            list(group.get("rows", [])),
            key=lambda row: report_number(row.get("qualified")),
            reverse=True,
        )
        if leaders:
            leader = dict(leaders[0])
            leader["group"] = group.get("group", "")
            group_rows.append(leader)
    group_rows = sorted(group_rows, key=lambda row: report_number(row.get("qualified")), reverse=True)[:4]
    cards = [
        ("小组赛", "晋级 32 强", "qualified", group_rows),
        ("32 强", "晋级 16 强", "r16", report_stage_rows(rows, "r16")),
        ("16 强", "晋级八强", "qf", report_stage_rows(rows, "qf")),
        ("八强", "晋级四强", "sf", report_stage_rows(rows, "sf")),
        ("四强", "晋级决赛", "final", report_stage_rows(rows, "final")),
        ("决赛", "夺冠", "champion", report_stage_rows(rows, "champion")),
    ]
    items = []
    for title, label, key, card_rows in cards:
        row_items = "".join(
            f"""
            <li>
              <strong>{escape(str(row.get('team_name') or row.get('team', '')))}</strong>
              <span>{escape(str(row.get('group', '')) + ' 组 · ' if row.get('group') else '')}{pct(row.get(key))}</span>
            </li>
            """
            for row in card_rows
        )
        items.append(
            f"""
            <article class="stage-report-card">
              <h3>{escape(title)}</h3>
              <p>{escape(label)}</p>
              <ul>{row_items}</ul>
            </article>
            """
        )
    return f'<div class="stage-report-grid">{"".join(items)}</div>'


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
    group_qualification_report = render_group_qualification_report(prediction)
    stage_cards_report = render_stage_cards_report(prediction)
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
    .stage-report-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }}
    .stage-report-card {{ border:1px solid #dce3ee; border-radius:8px; padding:12px; background:#fbfdff; }}
    .stage-report-card h3 {{ margin:0 0 4px; font-size:16px; }}
    .stage-report-card p {{ margin:0 0 8px; color:#63736e; }}
    .stage-report-card ul {{ padding-left:0; list-style:none; }}
    .stage-report-card li {{ display:flex; justify-content:space-between; gap:10px; border-top:1px solid #edf2f0; padding-top:7px; }}
    .group-qualification-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(310px,1fr)); gap:14px; }}
    .group-qualification-card {{ border:1px solid #dce3ee; border-radius:8px; padding:12px; background:#fbfdff; overflow-x:auto; }}
    .group-qualification-card h3 {{ margin:0 0 8px; font-size:16px; }}
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
      {stage_cards_report}
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
      <h2>小组出线预测</h2>
      {group_qualification_report}
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
