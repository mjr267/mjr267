#!/usr/bin/env python3
"""Generate the unified GitHub profile card from reachable commit + PR history."""

import json
import os
import urllib.request
from html import escape

USERNAME = os.getenv("USER_NAME", "mjr267")
TOKEN = os.environ["GITHUB_TOKEN"]
GRAPHQL_API = "https://api.github.com/graphql"


def graphql(query, variables):
    req = urllib.request.Request(
        GRAPHQL_API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json", "User-Agent": "mjr267-profile-stats"},
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
        repositories(first: 100, after: $cursor, ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]) {
          nodes { nameWithOwner owner { login } }
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


def authored_prs():
    q = """
    query($query: String!, $cursor: String) {
      search(query: $query, type: ISSUE, first: 100, after: $cursor) {
        nodes {
          ... on PullRequest {
            repository { nameWithOwner owner { login } }
            commits(first: 100) {
              nodes { commit { oid additions deletions author { user { login } } } }
              pageInfo { hasNextPage }
            }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
    """
    out, cursor = [], None
    while True:
        conn = graphql(q, {"query": f"author:{USERNAME} is:pr", "cursor": cursor})["search"]
        out.extend(n for n in conn["nodes"] if n)
        if not conn["pageInfo"]["hasNextPage"]:
            return out
        cursor = conn["pageInfo"]["endCursor"]


def default_branch_commits(repo_name):
    owner, name = repo_name.split("/", 1)
    q = """
    query($owner: String!, $name: String!, $cursor: String) {
      repository(owner: $owner, name: $name) {
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 100, after: $cursor) {
                nodes { oid additions deletions author { user { login } } }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }
      }
    }
    """
    cursor = None
    while True:
        repo = graphql(q, {"owner": owner, "name": name, "cursor": cursor})["repository"]
        if not repo or not repo["defaultBranchRef"]:
            return
        history = repo["defaultBranchRef"]["target"]["history"]
        for node in history["nodes"]:
            yield node
        if not history["pageInfo"]["hasNextPage"]:
            return
        cursor = history["pageInfo"]["endCursor"]


def contribution_totals():
    """Mirror GitHub's profile contribution accounting across every contribution year."""
    years_q = """
    query($login: String!) {
      user(login: $login) { contributionsCollection { contributionYears } }
    }
    """
    years = graphql(years_q, {"login": USERNAME})["user"]["contributionsCollection"]["contributionYears"]
    q = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar { totalContributions }
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
          totalRepositoryContributions
          restrictedContributionsCount
          totalRepositoriesWithContributedCommits
        }
      }
    }
    """
    totals = {
        "contributions": 0, "commits": 0, "issues": 0, "prs": 0,
        "reviews": 0, "repositories_created": 0, "restricted": 0,
        "contributed_repos": 0,
    }
    for year in years:
        d = graphql(q, {
            "login": USERNAME,
            "from": f"{year}-01-01T00:00:00Z",
            "to": f"{year}-12-31T23:59:59Z",
        })["user"]["contributionsCollection"]
        totals["contributions"] += d["contributionCalendar"]["totalContributions"]
        totals["commits"] += d["totalCommitContributions"]
        totals["issues"] += d["totalIssueContributions"]
        totals["prs"] += d["totalPullRequestContributions"]
        totals["reviews"] += d["totalPullRequestReviewContributions"]
        totals["repositories_created"] += d["totalRepositoryContributions"]
        totals["restricted"] += d["restrictedContributionsCount"]
        totals["contributed_repos"] = max(totals["contributed_repos"], d["totalRepositoriesWithContributedCommits"])
    return totals


def collect_stats():
    repos = repositories()
    totals = contribution_totals()
    return {
        "owned_repos": sum(r["owner"]["login"].lower() == USERNAME.lower() for r in repos),
        "other_repos": totals["contributed_repos"],
        "contributions": totals["contributions"],
        "commits": totals["commits"],
        "prs": totals["prs"],
        "reviews": totals["reviews"],
        "issues": totals["issues"],
        "restricted": totals["restricted"],
    }


def theme(dark):
    return {
        "bg": "#0d1117" if dark else "#ffffff", "fg": "#e6edf3" if dark else "#24292f",
        "accent": "#f59e0b" if dark else "#bc6b00", "value": "#9cdcfe" if dark else "#0550ae",
        "green": "#3fb950" if dark else "#1a7f37", "red": "#f85149" if dark else "#cf222e",
        "border": "#30363d" if dark else "#d0d7de", "dot": "#6e7681" if dark else "#8c959f",
    }


def svg_shell(width, height, dark):
    t = theme(dark)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(USERNAME)} profile">
<style>
.title {{ font: 700 18px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {t["fg"]}; }}
.label {{ font: 700 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {t["accent"]}; }}
.text {{ font: 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {t["value"]}; }}
.strong {{ font: 700 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {t["value"]}; }}
.add {{ font: 700 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {t["green"]}; }}
.del {{ font: 700 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {t["red"]}; }}
.leader {{ stroke: {t["dot"]}; stroke-width: 1; opacity: .65; }}
</style>
<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="14" fill="{t["bg"]}" stroke="{t["border"]}" />"""


def stat_row(label, value, y, width=760, cls="text"):
    # Compact terminal ledger: fixed label column, subtle divider, right-aligned value.
    return (
        f'<text x="34" y="{y}" class="label">{escape(label)}</text>'
        f'<line x1="205" y1="{y-18}" x2="205" y2="{y+7}" class="divider"/>'
        f'<text x="{width-34}" y="{y}" text-anchor="end" class="{cls}">{escape(value)}</text>'
    )


def tech_row(label, value, y, width=760):
    # Command-palette style: category tag on the left, value column on the right.
    return (
        f'<text x="34" y="{y}" class="label">{escape(label)}</text>'
        f'<text x="{width-34}" y="{y}" text-anchor="end" class="text">{escape(value)}</text>'
    )


def generate_profile(stats, dark):
    width, height = 760, 856
    lines = [
        '<text x="34" y="46" class="title">About Me ─────────────────────────────────────────────</text>',
        '<text x="34" y="88" class="label">Role</text><text x="200" y="88" class="text">Analytics Engineer / Data Consultant</text>',
        '<text x="34" y="120" class="label">Focus</text><text x="200" y="120" class="text">Analytics Engineering · BI · Data Infrastructure</text>',
        '<text x="200" y="145" class="text">Automation · Developer Tooling</text>',
        '<text x="34" y="178" class="label">Building</text><text x="200" y="178" class="text">Data &amp; analytics projects · Self-hosted infrastructure</text>',
        '<text x="200" y="203" class="text">Automation &amp; AI tooling</text>',
        '<text x="34" y="258" class="title">GitHub Stats ─────────────────────────────────────────</text>',
        stat_row("Contributions.Total", fmt(stats["contributions"]), 300, width, "strong"),
        stat_row("Commits", fmt(stats["commits"]), 334, width),
        stat_row("Pull Requests", fmt(stats["prs"]), 368, width),
        stat_row("Code Reviews", fmt(stats["reviews"]), 402, width),
        stat_row("Issues", fmt(stats["issues"]), 436, width),
        stat_row("Repos.Owned", fmt(stats["owned_repos"]), 470, width),
        stat_row("Repos.Contributed", fmt(stats["other_repos"]), 504, width),
        '<text x="34" y="598" class="title">Tech Stack ───────────────────────────────────────────</text>',
        tech_row("Data Engineering", "dbt, Snowflake, BigQuery, Airbyte, Fivetran", 640, width),
        tech_row("ETL & Reverse ETL", "Funnel.io, Matia", 674, width),
        tech_row("Analytics & BI", "Looker, LookML, Tableau, Power BI", 708, width),
        tech_row("Development", "Python, SQL, Docker, GitHub Actions", 742, width),
        tech_row("Workflow", "Git, GitHub, CI/CD, Automation", 776, width),
        tech_row("Environment", "macOS, Linux, Vercel, Supabase, Cloudflare", 810, width),
    ]
    return svg_shell(width, height, dark) + "".join(lines) + "</svg>"


def main():
    stats = collect_stats()
    for filename, content in {
        "profile_dark.svg": generate_profile(stats, True),
        "profile_light.svg": generate_profile(stats, False),
    }.items():
        with open(filename, "w", encoding="utf-8") as handle:
            handle.write(content)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
