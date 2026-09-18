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
        "accent": "#c9a66b" if dark else "#795f35", "value": "#c9d1d9" if dark else "#424a53",
        "green": "#8aa07c" if dark else "#536b49", "red": "#b98278" if dark else "#8c5148",
        "border": "#262b31" if dark else "#dedbd5", "dot": "#7d8288" if dark else "#77736d",
    }


def svg_shell(width, height, dark):
    t = theme(dark)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(USERNAME)} profile">
<style>
.kicker {{ font: 600 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; letter-spacing: 1.2px; fill: {t["accent"]}; }}
.hero {{ font: 650 30px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: {t["fg"]}; }}
.section {{ font: 600 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; letter-spacing: 1.1px; fill: {t["accent"]}; }}
.stat {{ font: 650 28px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: {t["fg"]}; }}
.statlabel {{ font: 500 10px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; letter-spacing: .5px; fill: {t["dot"]}; }}
.label {{ font: 600 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: {t["fg"]}; }}
.text {{ font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: {t["value"]}; }}
.muted {{ font: 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: {t["dot"]}; }}
.rule {{ stroke: {t["border"]}; stroke-width: 1; }}
</style>
<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="18" fill="{t["bg"]}" stroke="{t["border"]}" />"""


def stat_block(value, label, x, y):
    return (
        f'<text x="{x}" y="{y}" class="stat">{escape(value)}</text>'
        f'<text x="{x}" y="{y+23}" class="statlabel">{escape(label)}</text>'
    )


def stack_line(label, value, y):
    return (
        f'<text x="40" y="{y}" class="label">{escape(label)}</text>'
        f'<text x="218" y="{y}" class="text">{escape(value)}</text>'
    )


def generate_profile(stats, dark):
    width, height = 760, 856
    lines = [
        # Identity: intentionally editorial rather than a faux terminal/dashboard.
        '<text x="40" y="48" class="kicker">mjr267</text>',
        '<text x="40" y="92" class="hero">analytics engineering</text>',
        '<text x="40" y="126" class="hero">+ things I build.</text>',
        '<text x="40" y="162" class="muted">Data systems, BI, automation, infrastructure, and developer tooling.</text>',
        '<line x1="40" y1="194" x2="720" y2="194" class="rule"/>',

        # GitHub activity: large numbers first; labels are deliberately quiet.
        '<text x="40" y="229" class="section">GitHub activity</text>',
        stat_block(fmt(stats["contributions"]), "contributions", 40, 278),
        stat_block(fmt(stats["commits"]), "commits", 280, 278),
        stat_block(fmt(stats["prs"]), "pull requests", 520, 278),
        stat_block(fmt(stats["reviews"]), "code reviews", 40, 352),
        stat_block(fmt(stats["issues"]), "issues", 280, 352),
        stat_block(fmt(stats["owned_repos"]), "repos owned", 520, 352),
        '<line x1="40" y1="400" x2="720" y2="400" class="rule"/>',

        # Work profile: short, human-readable statements instead of key/value filler.
        '<text x="40" y="435" class="section">What I work on</text>',
        '<text x="40" y="474" class="label">Analytics systems</text>',
        '<text x="218" y="474" class="text">warehouses · semantic layers · reporting</text>',
        '<text x="40" y="507" class="label">Engineering</text>',
        '<text x="218" y="507" class="text">pipelines · automation · internal tools</text>',
        '<text x="40" y="540" class="label">Infrastructure</text>',
        '<text x="218" y="540" class="text">cloud services · CI/CD · self-hosted systems</text>',
        '<line x1="40" y1="578" x2="720" y2="578" class="rule"/>',

        # Stack: no pills, badges, boxes, or category backgrounds.
        '<text x="40" y="613" class="section">Tools I use</text>',
        stack_line("Data", "dbt · Snowflake · BigQuery · Airbyte · Fivetran", 652),
        stack_line("BI", "Looker · LookML · Tableau · Power BI", 685),
        stack_line("Build", "Python · SQL · Docker · GitHub Actions", 718),
        stack_line("Platform", "Vercel · Supabase · Cloudflare · Linux", 751),
        stack_line("Workflow", "Git · GitHub · CI/CD · automation", 784),

        '<text x="40" y="824" class="muted">San Diego, CA</text>',
        '<text x="720" y="824" text-anchor="end" class="muted">github.com/mjr267</text>',
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
