#!/usr/bin/env python3
"""Generate light/dark GitHub activity SVGs, including all-time commit and LOC stats."""

import json
import os
import urllib.request
from html import escape

USERNAME = os.getenv("USER_NAME", "mjr267")
TOKEN = os.environ["GITHUB_TOKEN"]
API = "https://api.github.com/graphql"
AFFILIATIONS = ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"]

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

def generate_svg(stats, dark):
    bg = "#0d1117" if dark else "#ffffff"
    fg = "#c9d1d9" if dark else "#24292f"
    muted = "#8b949e" if dark else "#57606a"
    accent = "#818cf8" if dark else "#4f46e5"
    green = "#3fb950" if dark else "#1a7f37"
    red = "#f85149" if dark else "#cf222e"
    border = "#30363d" if dark else "#d0d7de"

    rows = [
        ("Repositories", None, "section"),
        ("Owned", fmt(stats["owned_repos"]), "normal"),
        ("Other / Contributed", fmt(stats["other_repos"]), "normal"),
        ("Commits", None, "section"),
        ("Owned Repos", fmt(stats["owned_commits"]), "normal"),
        ("Other Repos", fmt(stats["other_commits"]), "normal"),
        ("Total", fmt(stats["total_commits"]), "strong"),
        ("Lines of Code", None, "section"),
        ("Net", fmt(stats["net_loc"]), "strong"),
        ("Added", f'{fmt(stats["additions"])} ++', "add"),
        ("Deleted", f'{fmt(stats["deletions"])} --', "del"),
    ]

    parts = []
    y = 104
    for label, value, kind in rows:
        if kind == "section":
            parts.append(f'<text x="36" y="{y}" class="section">{escape(label)}</text>')
        else:
            cls = {"normal": "value", "strong": "strong", "add": "add", "del": "del"}[kind]
            parts.append(
                f'<text x="52" y="{y}" class="label">{escape(label)}</text>'
                f'<text x="724" y="{y}" text-anchor="end" class="{cls}">{escape(value)}</text>'
            )
        y += 30

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="760" height="440" viewBox="0 0 760 440" role="img" aria-label="{USERNAME} GitHub statistics">
<style>
  .title {{ font: 700 22px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {accent}; }}
  .subtitle {{ font: 13px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {muted}; }}
  .section {{ font: 700 15px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {fg}; }}
  .label {{ font: 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {muted}; }}
  .value {{ font: 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {accent}; }}
  .strong {{ font: 700 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {accent}; }}
  .add {{ font: 700 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {green}; }}
  .del {{ font: 700 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {red}; }}
</style>
<rect x="1" y="1" width="758" height="438" rx="12" fill="{bg}" stroke="{border}" />
<text x="36" y="44" class="title">GitHub Stats</text>
<text x="36" y="68" class="subtitle">owned + accessible organization/collaborator repositories</text>
<line x1="36" y1="82" x2="724" y2="82" stroke="{border}" />
{"".join(parts)}
</svg>'''

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

    for filename, dark in (("dark_mode.svg", True), ("light_mode.svg", False)):
        with open(filename, "w", encoding="utf-8") as handle:
            handle.write(generate_svg(stats, dark))

    print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    main()
