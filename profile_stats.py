#!/usr/bin/env python3
"""Generate a BI-style GitHub analytics dashboard for the profile README."""

import calendar
import datetime as dt
import json
import math
import os
import urllib.request
from collections import defaultdict
from html import escape

USERNAME = os.getenv("USER_NAME", "mjr267")
TOKEN = os.environ["GITHUB_TOKEN"]
GRAPHQL_API = "https://api.github.com/graphql"


def graphql(query, variables):
    req = urllib.request.Request(
        GRAPHQL_API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "mjr267-profile-stats",
        },
    )
    with urllib.request.urlopen(req) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError(result["errors"])
    return result["data"]


def fmt(value):
    return f"{value:,}"


def repositories():
    q = """
    query($login: String!, $cursor: String) {
      user(login: $login) {
        repositories(
          first: 100
          after: $cursor
          ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]
          orderBy: {field: UPDATED_AT, direction: DESC}
        ) {
          nodes {
            nameWithOwner
            owner { login }
            stargazerCount
            primaryLanguage { name }
            isFork
          }
          pageInfo { hasNextPage endCursor }
        }
      }
    }
    """
    out, cursor = [], None
    while True:
        conn = graphql(q, {"login": USERNAME, "cursor": cursor})["user"]["repositories"]
        out.extend(conn["nodes"])
        if not conn["pageInfo"]["hasNextPage"]:
            return out
        cursor = conn["pageInfo"]["endCursor"]


def contribution_years():
    q = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection { contributionYears }
      }
    }
    """
    return graphql(q, {"login": USERNAME})["user"]["contributionsCollection"]["contributionYears"]


def contribution_slice(start, end):
    q = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
                weekday
              }
            }
          }
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
          totalRepositoriesWithContributedCommits
        }
      }
    }
    """
    return graphql(
        q,
        {
            "login": USERNAME,
            "from": start,
            "to": end,
        },
    )["user"]["contributionsCollection"]


def collect_stats():
    repos = repositories()
    years = contribution_years()

    totals = {
        "contributions": 0,
        "commits": 0,
        "issues": 0,
        "prs": 0,
        "reviews": 0,
        "contributed_repos": 0,
    }
    for year in years:
        d = contribution_slice(f"{year}-01-01T00:00:00Z", f"{year}-12-31T23:59:59Z")
        totals["contributions"] += d["contributionCalendar"]["totalContributions"]
        totals["commits"] += d["totalCommitContributions"]
        totals["issues"] += d["totalIssueContributions"]
        totals["prs"] += d["totalPullRequestContributions"]
        totals["reviews"] += d["totalPullRequestReviewContributions"]
        totals["contributed_repos"] = max(
            totals["contributed_repos"],
            d["totalRepositoriesWithContributedCommits"],
        )

    today = dt.datetime.now(dt.timezone.utc).date()
    start_date = today - dt.timedelta(days=364)
    current = contribution_slice(
        f"{start_date.isoformat()}T00:00:00Z",
        f"{today.isoformat()}T23:59:59Z",
    )
    days = [
        day
        for week in current["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
        if start_date.isoformat() <= day["date"] <= today.isoformat()
    ]

    monthly = defaultdict(int)
    for d in days:
        day = dt.date.fromisoformat(d["date"])
        monthly[(day.year, day.month)] += d["contributionCount"]

    month_keys = []
    cursor = dt.date(today.year, today.month, 1)
    for i in range(11, -1, -1):
        year = cursor.year
        month = cursor.month - i
        while month <= 0:
            month += 12
            year -= 1
        month_keys.append((year, month))

    language_counts = defaultdict(int)
    for r in repos:
        if r["primaryLanguage"] and r["primaryLanguage"].get("name"):
            language_counts[r["primaryLanguage"]["name"]] += 1
    languages = sorted(language_counts.items(), key=lambda x: (-x[1], x[0]))[:5]

    owned_repos = [r for r in repos if r["owner"]["login"].lower() == USERNAME.lower()]
    stars = sum(r["stargazerCount"] for r in owned_repos)
    forks = sum(1 for r in owned_repos if r["isFork"])

    return {
        "owned_repos": len(owned_repos),
        "other_repos": totals["contributed_repos"],
        "stars": stars,
        "forks": forks,
        "contributions": totals["contributions"],
        "contributions_365": current["contributionCalendar"]["totalContributions"],
        "commits": totals["commits"],
        "prs": totals["prs"],
        "reviews": totals["reviews"],
        "issues": totals["issues"],
        "days": days,
        "months": [
            {
                "label": calendar.month_abbr[m],
                "value": monthly[(y, m)],
            }
            for y, m in month_keys
        ],
        "languages": languages,
        "updated": now.strftime("%Y-%m-%d %H:%M UTC"),
    }


def theme(dark):
    return {
        "bg": "#0b1117" if dark else "#f7f8fa",
        "panel": "#101820" if dark else "#ffffff",
        "panel2": "#0f171e" if dark else "#fbfbfc",
        "fg": "#f3f4f6" if dark else "#18212a",
        "muted": "#9aa6b2" if dark else "#6b7280",
        "border": "#26323d" if dark else "#d8dde3",
        "grid": "#202b35" if dark else "#e7eaee",
        "accent": "#d5bd7a" if dark else "#8b6d2f",
        "accent2": "#9b8b5e" if dark else "#b89958",
        "heat0": "#202a33" if dark else "#edf0f3",
        "heat1": "#4b4637" if dark else "#e6dfc9",
        "heat2": "#756945" if dark else "#d6c48f",
        "heat3": "#a58d50" if dark else "#bca15a",
        "heat4": "#d9bd6a" if dark else "#8b6d2f",
    }


def text(x, y, value, cls, anchor=None):
    a = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{x}" y="{y}" class="{cls}"{a}>{escape(str(value))}</text>'


def rect(x, y, w, h, cls="panel", rx=12):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" class="{cls}"/>'


def line(x1, y1, x2, y2, cls="grid"):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="{cls}"/>'


def scorecard(x, y, w, h, label, value, sub=None):
    parts = [
        rect(x, y, w, h, "panel", 10),
        text(x + 22, y + 30, label, "card-label"),
        text(x + 22, y + 75, value, "card-value"),
    ]
    if sub:
        parts.append(text(x + 22, y + h - 20, sub, "small"))
    return "".join(parts)


def heat_level(count, max_count):
    if count <= 0 or max_count <= 0:
        return 0
    ratio = count / max_count
    if ratio <= 0.25:
        return 1
    if ratio <= 0.5:
        return 2
    if ratio <= 0.75:
        return 3
    return 4


def render_heatmap(stats, x, y, width, height):
    days = stats["days"]
    max_count = max((d["contributionCount"] for d in days), default=0)
    by_date = {d["date"]: d for d in days}
    start = dt.date.fromisoformat(days[0]["date"]) if days else dt.date.today() - dt.timedelta(days=364)
    start -= dt.timedelta(days=(start.weekday() + 1) % 7)
    cols = 53
    rows = 7
    # Scale the heatmap to use the available panel width instead of leaving
    # dashboard-sized dead space around GitHub's 53x7 contribution grid.
    # The grid is extremely wide (53x7), so width is the limiting dimension.
    # Use a tighter gap and nearly the full panel width; then vertically center
    # the resulting grid in the chart body so it visually fills the panel.
    gap = 1.5
    cell = (width - gap * (cols - 1)) / cols
    grid_height = rows * cell + gap * (rows - 1)
    body_top = y + 24
    body_height = height - 24
    parts = [text(x, y, "Contribution activity", "panel-title")]
    gy = body_top + max(0, (body_height - grid_height) / 2)
    gx = x
    for c in range(cols):
        week_start = start + dt.timedelta(days=c * 7)
        for r in range(7):
            day = week_start + dt.timedelta(days=r)
            d = by_date.get(day.isoformat())
            count = d["contributionCount"] if d else 0
            lvl = heat_level(count, max_count)
            parts.append(
                f'<rect x="{gx + c * (cell + gap):.1f}" y="{gy + r * (cell + gap):.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="2" class="heat{lvl}"/>'
            )
    parts.append(text(x + width, y, f'{fmt(stats["contributions_365"])} in the last 365 days', "small", "end"))
    return "".join(parts)


def render_monthly_bars(stats, x, y, width, height):
    months = stats["months"]
    max_val = max((m["value"] for m in months), default=1)
    chart_top = y + 38
    chart_bottom = y + height - 28
    chart_h = chart_bottom - chart_top
    bar_gap = 8
    bar_w = max(8, (width - 24 - bar_gap * (len(months) - 1)) / len(months))
    parts = [text(x, y, "Contributions by month", "panel-title")]
    for i in range(4):
        gy = chart_top + i * chart_h / 3
        parts.append(line(x, gy, x + width, gy))
    for i, month in enumerate(months):
        bh = 0 if max_val == 0 else month["value"] / max_val * (chart_h - 12)
        bx = x + 8 + i * (bar_w + bar_gap)
        by = chart_bottom - bh
        parts.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" rx="3" class="bar"/>')
        # Put the value above each bar rather than inside it so short bars remain legible.
        value_y = max(chart_top + 11, by - 6)
        parts.append(text(bx + bar_w / 2, value_y, fmt(month["value"]), "bar-value", "middle"))
        parts.append(text(bx + bar_w / 2, chart_bottom + 18, month["label"], "axis", "middle"))
    return "".join(parts)


def render_activity_mix(stats, x, y, width, height):
    values = [
        ("Commits", stats["commits"]),
        ("PRs", stats["prs"]),
        ("Reviews", stats["reviews"]),
        ("Issues", stats["issues"]),
    ]
    total = sum(v for _, v in values) or 1
    cx, cy, r = x + 88, y + 102, 56
    circumference = 2 * math.pi * r
    offset = 0.0
    parts = [text(x, y, "Activity mix", "panel-title")]
    for idx, (label, value) in enumerate(values):
        dash = circumference * value / total
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke-width="16" '
            f'class="donut{idx}" stroke-dasharray="{dash:.2f} {circumference - dash:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {cx} {cy})"/>'
        )
        offset += dash
    parts.append(text(cx, cy + 5, fmt(total), "donut-total", "middle"))
    parts.append(text(cx, cy + 25, "actions", "small", "middle"))
    ly = y + 48
    for idx, (label, value) in enumerate(values):
        lx = x + 176
        parts.append(f'<circle cx="{lx}" cy="{ly - 4}" r="5" class="dot{idx}"/>')
        parts.append(text(lx + 14, ly, label, "legend"))
        parts.append(text(x + width, ly, fmt(value), "legend-value", "end"))
        ly += 28
    return "".join(parts)


def render_languages(stats, x, y, width, height):
    langs = stats["languages"]
    total = sum(v for _, v in langs) or 1
    parts = [text(x, y, "Repository languages", "panel-title")]
    bx = x
    by = y + 38
    remaining_w = width
    for idx, (lang, count) in enumerate(langs):
        w = width * count / total
        parts.append(f'<rect x="{bx:.1f}" y="{by}" width="{w:.1f}" height="12" class="lang{idx}"/>')
        bx += w
        remaining_w -= w
    ly = y + 76
    for idx, (lang, count) in enumerate(langs):
        pct = count / total * 100
        parts.append(f'<circle cx="{x + 5}" cy="{ly - 4}" r="4" class="lang{idx}"/>')
        parts.append(text(x + 16, ly, lang, "legend"))
        parts.append(text(x + width, ly, f"{pct:.0f}%", "legend-value", "end"))
        ly += 25
    return "".join(parts)


def generate_dashboard(stats, dark):
    t = theme(dark)
    width, height = 1180, 760
    css = f"""
<style>
.bg {{ fill: {t["bg"]}; }}
.panel {{ fill: {t["panel"]}; stroke: {t["border"]}; stroke-width: 1; }}
.grid {{ stroke: {t["grid"]}; stroke-width: 1; }}
.title {{ font-family: Arial, Helvetica, sans-serif; font-size: 30px; font-weight: 700; fill: {t["fg"]}; }}
.subtitle {{ font-family: Arial, Helvetica, sans-serif; font-size: 14px; font-weight: 400; fill: {t["muted"]}; }}
.card-label {{ font-family: Arial, Helvetica, sans-serif; font-size: 13px; font-weight: 600; fill: {t["muted"]}; }}
.card-value {{ font-family: Arial, Helvetica, sans-serif; font-size: 32px; font-weight: 700; fill: {t["fg"]}; }}
.panel-title {{ font-family: Arial, Helvetica, sans-serif; font-size: 15px; font-weight: 600; fill: {t["fg"]}; }}
.small {{ font-family: Arial, Helvetica, sans-serif; font-size: 11px; font-weight: 400; fill: {t["muted"]}; }}
.axis {{ font-family: Arial, Helvetica, sans-serif; font-size: 10px; font-weight: 400; fill: {t["muted"]}; }}
.bar-value {{ font-family: Arial, Helvetica, sans-serif; font-size: 10px; font-weight: 600; fill: {t["fg"]}; }}
.legend {{ font-family: Arial, Helvetica, sans-serif; font-size: 12px; font-weight: 400; fill: {t["fg"]}; }}
.legend-value {{ font-family: Arial, Helvetica, sans-serif; font-size: 12px; font-weight: 600; fill: {t["muted"]}; }}
.donut-total {{ font-family: Arial, Helvetica, sans-serif; font-size: 18px; font-weight: 700; fill: {t["fg"]}; }}
.bar {{ fill: {t["accent"]}; }}
.heat0 {{ fill: {t["heat0"]}; }} .heat1 {{ fill: {t["heat1"]}; }} .heat2 {{ fill: {t["heat2"]}; }} .heat3 {{ fill: {t["heat3"]}; }} .heat4 {{ fill: {t["heat4"]}; }}
.donut0,.dot0,.lang0 {{ stroke: {t["accent"]}; fill: {t["accent"]}; }}
.donut1,.dot1,.lang1 {{ stroke: {t["accent2"]}; fill: {t["accent2"]}; }}
.donut2,.dot2,.lang2 {{ stroke: {t["muted"]}; fill: {t["muted"]}; }}
.donut3,.dot3,.lang3 {{ stroke: {t["border"]}; fill: {t["border"]}; }}
.lang4 {{ stroke: {t["grid"]}; fill: {t["grid"]}; }}
</style>
"""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(USERNAME)} GitHub analytics dashboard">',
        css,
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="18" class="bg"/>',
        text(30, 42, USERNAME, "title"),
        text(30, 66, "GitHub analytics", "subtitle"),
        text(width - 30, 42, f'Updated {stats["updated"]}', "subtitle", "end"),

        scorecard(30, 94, 260, 112, "Contributions · all time", fmt(stats["contributions"]), f'{fmt(stats["contributions_365"])} in last 365 days'),
        scorecard(310, 94, 260, 112, "Commits", fmt(stats["commits"]), "GitHub contribution accounting"),
        scorecard(590, 94, 260, 112, "Pull requests", fmt(stats["prs"]), f'{fmt(stats["reviews"])} code reviews'),
        scorecard(870, 94, 280, 112, "Repositories", fmt(stats["owned_repos"]), f'{fmt(stats["other_repos"])} contributed · {fmt(stats["stars"])} stars'),

        rect(30, 226, 720, 248, "panel", 12),
        render_heatmap(stats, 52, 258, 676, 180),

        rect(770, 226, 380, 248, "panel", 12),
        render_monthly_bars(stats, 792, 258, 336, 180),

        rect(30, 494, 360, 232, "panel", 12),
        render_activity_mix(stats, 52, 526, 316, 170),

        rect(410, 494, 360, 232, "panel", 12),
        render_languages(stats, 432, 526, 316, 170),

        rect(790, 494, 360, 232, "panel", 12),
        text(812, 526, "Repository footprint", "panel-title"),
        text(812, 577, fmt(stats["owned_repos"]), "card-value"),
        text(812, 602, "owned repositories", "small"),
        text(962, 577, fmt(stats["other_repos"]), "card-value"),
        text(962, 602, "repos contributed to", "small"),
        line(812, 626, 1128, 626),
        text(812, 658, fmt(stats["stars"]), "card-value"),
        text(812, 683, "stars across owned repos", "small"),
        text(962, 658, fmt(stats["issues"]), "card-value"),
        text(962, 683, "issues opened", "small"),
        "</svg>",
    ]
    return "".join(parts)


def main():
    stats = collect_stats()
    for filename, content in {
        "github_stats_dark.svg": generate_dashboard(stats, True),
        "github_stats_light.svg": generate_dashboard(stats, False),
    }.items():
        with open(filename, "w", encoding="utf-8") as handle:
            handle.write(content)
    print(json.dumps({k: v for k, v in stats.items() if k not in {"days", "months", "languages"}}, indent=2))


if __name__ == "__main__":
    main()
