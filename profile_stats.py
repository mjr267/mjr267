#!/usr/bin/env python3
"""Generate unified light/dark GitHub profile panels and all-time stats."""

import json
import os
import urllib.request
from html import escape

USERNAME = os.getenv("USER_NAME", "mjr267")
TOKEN = os.environ["GITHUB_TOKEN"]
API = "https://api.github.com/graphql"

def graphql(query, variables):
    req = urllib.request.Request(
        API,
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

def get_user():
    query = """
    query($login: String!) {
      user(login: $login) { id }
    }
    """
    return graphql(query, {"login": USERNAME})["user"]

def get_repositories():
    query = """
    query($login: String!, $cursor: String) {
      user(login: $login) {
        repositories(
          first: 100
          after: $cursor
          ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]
        ) {
          nodes {
            nameWithOwner
            owner { login }
            defaultBranchRef { name }
          }
          pageInfo { hasNextPage endCursor }
        }
      }
    }
    """
    repos, cursor = [], None
    while True:
        conn = graphql(query, {"login": USERNAME, "cursor": cursor})["user"]["repositories"]
        repos.extend(conn["nodes"])
        if not conn["pageInfo"]["hasNextPage"]:
            return repos
        cursor = conn["pageInfo"]["endCursor"]

def repo_activity(repo, user_id):
    if not repo["defaultBranchRef"]:
        return 0, 0, 0
    owner, name = repo["nameWithOwner"].split("/", 1)
    branch = repo["defaultBranchRef"]["name"]
    query = """
    query($owner: String!, $name: String!, $branch: String!, $cursor: String, $author: ID!) {
      repository(owner: $owner, name: $name) {
        ref(qualifiedName: $branch) {
          target {
            ... on Commit {
              history(first: 100, after: $cursor, author: {id: $author}) {
                nodes { additions deletions }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }
      }
    }
    """
    commits = additions = deletions = 0
    cursor = None
    while True:
        data = graphql(query, {
            "owner": owner, "name": name, "branch": branch,
            "cursor": cursor, "author": user_id,
        })["repository"]
        if not data or not data["ref"]:
            return commits, additions, deletions
        history = data["ref"]["target"]["history"]
        commits += len(history["nodes"])
        additions += sum(node["additions"] for node in history["nodes"])
        deletions += sum(node["deletions"] for node in history["nodes"])
        if not history["pageInfo"]["hasNextPage"]:
            return commits, additions, deletions
        cursor = history["pageInfo"]["endCursor"]

def theme(dark):
    return {
        "bg": "#0d1117" if dark else "#ffffff",
        "fg": "#e6edf3" if dark else "#24292f",
        "muted": "#8b949e" if dark else "#57606a",
        "accent": "#f59e0b" if dark else "#bc6b00",
        "value": "#9cdcfe" if dark else "#0550ae",
        "green": "#3fb950" if dark else "#1a7f37",
        "red": "#f85149" if dark else "#cf222e",
        "border": "#30363d" if dark else "#d0d7de",
        "dot": "#6e7681" if dark else "#8c959f",
        "panel": "#161b22" if dark else "#f6f8fa",
    }

def svg_shell(width, height, dark, title):
    t = theme(dark)
    head = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
<style>
  .title {{ font: 700 18px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {t["fg"]}; }}
  .label {{ font: 700 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {t["accent"]}; }}
  .text {{ font: 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {t["value"]}; }}
  .muted {{ font: 13px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {t["muted"]}; }}
  .strong {{ font: 700 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {t["value"]}; }}
  .add {{ font: 700 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {t["green"]}; }}
  .del {{ font: 700 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {t["red"]}; }}
  .dots {{ font: 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {t["dot"]}; }}
</style>
<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="14" fill="{t["bg"]}" stroke="{t["border"]}" />
'''
    return head, t

def row(label, value, y, width=760, cls="text", label_x=34, value_x=None, dot_x1=250, dot_x2=520):
    if value_x is None:
        value_x = width - 34
    return (
        f'<text x="{label_x}" y="{y}" class="label">{escape(label)}</text>'
        f'<line x1="{dot_x1}" y1="{y-5}" x2="{dot_x2}" y2="{y-5}" class="leader"/>'
        f'<text x="{value_x}" y="{y}" text-anchor="end" class="{cls}">{escape(value)}</text>'
    )

def generate_profile(stats, dark):
    width, height = 760, 856
    head, t = svg_shell(width, height, dark, f"{USERNAME} profile")
    lines = [
        '<text x="34" y="46" class="title">mjr267@github ─────────────────────────────────────────</text>',
        '<text x="34" y="88" class="label">Role</text>',
        '<text x="200" y="88" class="text">Analytics Engineer / Data Consultant</text>',
        '<text x="34" y="120" class="label">Focus</text>',
        '<text x="200" y="120" class="text">Analytics Engineering · BI · Data Infrastructure</text>',
        '<text x="200" y="145" class="text">Automation · Developer Tooling</text>',
        '<text x="34" y="178" class="label">Building</text>',
        '<text x="200" y="178" class="text">Data & analytics projects · Self-hosted infrastructure</text>',
        '<text x="200" y="203" class="text">Automation & AI tooling</text>',

        '<text x="34" y="258" class="title">GitHub Stats ─────────────────────────────────────────</text>',
        row("Repos.Owned", fmt(stats["owned_repos"]), 300, width, dot_x1=220, dot_x2=620),
        row("Repos.Contributed", fmt(stats["other_repos"]), 334, width, dot_x1=220, dot_x2=620),
        row("Commits.Owned", fmt(stats["owned_commits"]), 368, width, dot_x1=220, dot_x2=620),
        row("Commits.Other", fmt(stats["other_commits"]), 402, width, dot_x1=220, dot_x2=620),
        row("Commits.Total", fmt(stats["total_commits"]), 436, width, "strong", dot_x1=220, dot_x2=620),
        row("Lines.Net", fmt(stats["net_loc"]), 470, width, "strong", dot_x1=220, dot_x2=620),
        row("Lines.Added", f'{fmt(stats["additions"])} ++', 504, width, "add", dot_x1=220, dot_x2=620),
        row("Lines.Deleted", f'{fmt(stats["deletions"])} --', 538, width, "del", dot_x1=220, dot_x2=620),

        '<text x="34" y="598" class="title">Tech Stack ───────────────────────────────────────────</text>',
        row("Data Engineering", "dbt, Snowflake, BigQuery, Airbyte, Fivetran", 640, width, dot_x1=210, dot_x2=360),
        row("ETL & Reverse ETL", "Funnel.io, Matia", 674, width, dot_x1=210, dot_x2=520),
        row("Analytics & BI", "Looker, LookML, Tableau, Power BI", 708, width, dot_x1=210, dot_x2=430),
        row("Development", "Python, SQL, Docker, GitHub Actions", 742, width, dot_x1=210, dot_x2=430),
        row("Workflow", "Git, GitHub, CI/CD, Automation", 776, width, dot_x1=210, dot_x2=475),
        row("Environment", "macOS, Linux, Vercel, Supabase, Cloudflare", 810, width, dot_x1=210, dot_x2=390),
    ]
    return head + "".join(lines) + "</svg>"

def main():
    user = get_user()
    repos = get_repositories()

    stats = {
        "owned_repos": 0, "other_repos": 0,
        "owned_commits": 0, "other_commits": 0,
        "additions": 0, "deletions": 0,
    }

    for repo in repos:
        owned = repo["owner"]["login"].lower() == USERNAME.lower()
        stats["owned_repos" if owned else "other_repos"] += 1
        commits, additions, deletions = repo_activity(repo, user["id"])
        stats["owned_commits" if owned else "other_commits"] += commits
        stats["additions"] += additions
        stats["deletions"] += deletions

    stats["total_commits"] = stats["owned_commits"] + stats["other_commits"]
    stats["net_loc"] = stats["additions"] - stats["deletions"]

    outputs = {
        "profile_dark.svg": generate_profile(stats, True),
        "profile_light.svg": generate_profile(stats, False),
    }
    for filename, content in outputs.items():
        with open(filename, "w", encoding="utf-8") as handle:
            handle.write(content)

    print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    main()
