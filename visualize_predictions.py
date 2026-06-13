#!/usr/bin/env python3
"""
Render the simulation CSV into a reader-friendly chart.

The script uses only Python's standard library. It turns model column names such as
sf/qf/r16/r32 into plain Chinese stage labels suitable for articles or reports.
Use a .svg output path for a standalone SVG, or .html for a complete HTML report.
"""

from __future__ import annotations

import argparse
import csv
from html import escape
from pathlib import Path


STAGES = [
    ("champion", "夺冠"),
    ("final", "进决赛"),
    ("sf", "进四强"),
    ("qf", "进八强"),
    ("r16", "进16强"),
    ("r32", "进32强"),
]


def read_rows(path: Path, top: int) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            parsed: dict[str, float | str] = {"team": row["team"]}
            for key, _ in STAGES:
                parsed[key] = float(row[key])
            rows.append(parsed)
    rows.sort(key=lambda r: float(r["champion"]), reverse=True)
    return rows[:top]


def pct(value: float) -> str:
    if value >= 0.1:
        return f"{value * 100:.1f}%"
    return f"{value * 100:.2f}%"


def lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


def heat_color(value: float, max_value: float) -> str:
    """Map a probability to a soft blue-green heatmap color."""
    t = 0.0 if max_value == 0 else min(max(value / max_value, 0.0), 1.0)
    low = (232, 245, 242)
    high = (22, 132, 120)
    r, g, b = (lerp(low[i], high[i], t) for i in range(3))
    return f"rgb({r},{g},{b})"


def text_color(value: float, max_value: float) -> str:
    t = 0.0 if max_value == 0 else value / max_value
    return "#ffffff" if t > 0.58 else "#18302d"


def render_svg(rows: list[dict[str, float | str]], title: str, subtitle: str) -> str:
    margin = 36
    title_h = 86
    bar_h = 28
    bar_area_w = 420
    heat_left = margin + bar_area_w + 58
    cell_w = 86
    cell_h = 34
    label_w = 130
    table_top = title_h + 54
    row_h = 42
    width = heat_left + label_w + cell_w * len(STAGES) + margin
    height = table_top + row_h * len(rows) + 42

    max_champion = max(float(r["champion"]) for r in rows) if rows else 0.0
    max_by_stage = {
        key: max(float(row[key]) for row in rows) if rows else 0.0
        for key, _ in STAGES
    }

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        "text{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',Arial,sans-serif}",
        ".title{font-size:28px;font-weight:700;fill:#17211f}",
        ".subtitle{font-size:14px;fill:#5b6b66}",
        ".axis{font-size:12px;fill:#6b7773}",
        ".team{font-size:13px;font-weight:600;fill:#1d2b28}",
        ".pct{font-size:12px;font-weight:600}",
        ".small{font-size:11px;fill:#6b7773}",
        "</style>",
        '<rect width="100%" height="100%" fill="#fbfcfb"/>',
        f'<text class="title" x="{margin}" y="42">{escape(title)}</text>',
        f'<text class="subtitle" x="{margin}" y="68">{escape(subtitle)}</text>',
        f'<text class="axis" x="{margin}" y="{title_h + 18}">夺冠概率排行</text>',
        f'<text class="axis" x="{heat_left}" y="{title_h + 18}">各阶段晋级概率</text>',
    ]

    for index, row in enumerate(rows):
        y = table_top + index * row_h
        team = str(row["team"])
        champion = float(row["champion"])
        bar_max_w = bar_area_w - 160
        bar_w = 0 if max_champion == 0 else champion / max_champion * bar_max_w
        parts.extend(
            [
                f'<text class="team" x="{margin}" y="{y + 22}">{escape(team)}</text>',
                f'<rect x="{margin + 142}" y="{y + 6}" width="{bar_max_w}" height="{bar_h}" rx="5" fill="#edf3f1"/>',
                f'<rect x="{margin + 142}" y="{y + 6}" width="{bar_w}" height="{bar_h}" rx="5" fill="#168478"/>',
                f'<text class="pct" x="{margin + 154 + bar_w}" y="{y + 25}" fill="#18302d">{pct(champion)}</text>',
            ]
        )

    for col, (_, label) in enumerate(STAGES):
        x = heat_left + label_w + col * cell_w
        parts.append(
            f'<text class="axis" x="{x + cell_w / 2}" y="{table_top - 12}" text-anchor="middle">{escape(label)}</text>'
        )

    for index, row in enumerate(rows):
        y = table_top + index * row_h
        team = str(row["team"])
        parts.append(f'<text class="team" x="{heat_left}" y="{y + 24}">{escape(team)}</text>')
        for col, (key, _) in enumerate(STAGES):
            value = float(row[key])
            x = heat_left + label_w + col * cell_w
            color = heat_color(value, max_by_stage[key])
            fg = text_color(value, max_by_stage[key])
            parts.extend(
                [
                    f'<rect x="{x + 5}" y="{y + 4}" width="{cell_w - 10}" height="{cell_h}" rx="5" fill="{color}"/>',
                    f'<text class="pct" x="{x + cell_w / 2}" y="{y + 26}" fill="{fg}" text-anchor="middle">{pct(value)}</text>',
                ]
            )

    note_y = height - 18
    note = "注：概率来自 Monte Carlo 模拟；样例数据仅用于烟测，不代表真实预测。"
    parts.append(f'<text class="small" x="{margin}" y="{note_y}">{escape(note)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def render_html(rows: list[dict[str, float | str]], title: str, subtitle: str) -> str:
    svg = render_svg(rows, title, subtitle)
    stage_items = "\n".join(
        f"<li><strong>{escape(label)}</strong>：{escape(key)}</li>"
        for key, label in STAGES
    )
    top_team = str(rows[0]["team"]) if rows else "暂无数据"
    top_prob = pct(float(rows[0]["champion"])) if rows else "0%"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f8f7;
      --panel: #ffffff;
      --text: #17211f;
      --muted: #60706b;
      --line: #dfe8e5;
      --accent: #168478;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
      line-height: 1.6;
    }}
    main {{
      max-width: 1240px;
      margin: 0 auto;
      padding: 32px 24px 44px;
    }}
    header {{
      margin-bottom: 20px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
      line-height: 1.2;
    }}
    p {{
      margin: 0;
      color: var(--muted);
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin: 22px 0;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 16px;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
    }}
    .metric strong {{
      display: block;
      margin-top: 4px;
      font-size: 21px;
    }}
    .chart {{
      overflow-x: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .chart svg {{
      display: block;
      min-width: 1080px;
      max-width: none;
    }}
    .legend {{
      display: grid;
      grid-template-columns: repeat(6, minmax(90px, 1fr));
      gap: 8px;
      padding: 16px 2px 0;
      margin: 0;
      list-style: none;
      color: var(--muted);
      font-size: 13px;
    }}
    .legend li {{
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
    }}
    .note {{
      margin-top: 16px;
      font-size: 13px;
    }}
    @media (max-width: 760px) {{
      main {{
        padding: 24px 14px 34px;
      }}
      h1 {{
        font-size: 24px;
      }}
      .summary {{
        grid-template-columns: 1fr;
      }}
      .legend {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{escape(title)}</h1>
      <p>{escape(subtitle)}</p>
    </header>

    <section class="summary" aria-label="预测摘要">
      <div class="metric">
        <span>展示球队数</span>
        <strong>{len(rows)}</strong>
      </div>
      <div class="metric">
        <span>当前最高夺冠概率</span>
        <strong>{escape(top_team)}</strong>
      </div>
      <div class="metric">
        <span>最高夺冠概率数值</span>
        <strong>{top_prob}</strong>
      </div>
    </section>

    <section class="chart" aria-label="世界杯预测概率图表">
      {svg}
    </section>

    <ul class="legend" aria-label="字段说明">
      {stage_items}
    </ul>

    <p class="note">说明：这些概率来自 Monte Carlo 模拟。输入数据、Elo 参数、东道主加成和分组文件发生变化时，结果也会变化。</p>
  </main>
</body>
</html>
"""


def run(args: argparse.Namespace) -> None:
    rows = read_rows(args.input, args.top)
    if args.output.suffix.lower() == ".html":
        content = render_html(rows, args.title, args.subtitle)
    else:
        content = render_svg(rows, args.title, args.subtitle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Wrote {args.output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Prediction CSV from worldcup_simulator.py")
    parser.add_argument("--output", type=Path, required=True, help="Output .svg or .html path")
    parser.add_argument("--top", type=int, default=16, help="Number of teams to show")
    parser.add_argument("--title", default="2026 世界杯预测概率")
    parser.add_argument("--subtitle", default="夺冠热门与各阶段晋级机会")
    return parser


if __name__ == "__main__":
    run(build_parser().parse_args())
