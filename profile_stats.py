#!/usr/bin/env python3
"""Generate light/dark SVG profile statistics from the GitHub GraphQL API.\n\nThe workflow credential must expose the contribution data GitHub attributes to the profile.\n"""

import json
import os
import urllib.request
from datetime import datetime, timezone
from html import escape

USERNAME = os.getenv("USER_NAME", "mjr267")
TOKEN = os.environ["GITHUB_TOKEN"]
API = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 0) { totalCount }
            }
          }
        }
      }
    }
    repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]) {
      totalCount
    }
    contributionsCollection {
      contributionCalendar { totalContributions }
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      restrictedContributionsCount
      commitContributionsByRepository(maxRepositories: 100) {
        repository { owner { login } }
        contributions { totalCount }
      }
      issueContributionsByRepository(maxRepositories: 100) {
        repository { owner { login } }
        contributions { totalCount }
      }
      pullRequestContributionsByRepository(maxRepositories: 100) {
        repository { owner { login } }
        contributions { totalCount }
      }
      pullRequestReviewContributionsByRepository(maxRepositories: 100) {
        repository { owner { login } }
        contributions { totalCount }
      }
    }
  }
}
"""

def graphql(query, variables):
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        API,
        data=payload,
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

def generate_svg(stats, dark):
    bg = "#0d1117" if dark else "#ffffff"
    fg = "#c9d1d9" if dark else "#24292f"
    muted = "#8b949e" if dark else "#57606a"
    accent = "#818cf8" if dark else "#4f46e5"
    border = "#30363d" if dark else "#d0d7de"

    rows = [
        ("Account age", stats["account_age"]),
        ("Public repositories", fmt(stats["repos"])),
        ("Repositories contributed to", fmt(stats["contributed"])),
        ("Stars earned", fmt(stats["stars"])),
        ("Followers", fmt(stats["followers"])),
        ("Commits this year", fmt(stats["commits_year"])),
        ("Contributions this year", fmt(stats["contributions_year"])),
        ("Pull requests this year", fmt(stats["prs_year"])),
        ("Issues this year", fmt(stats["issues_year"])),
        ("PR reviews this year", fmt(stats["reviews_year"])),
        ("Owned-repo activity", fmt(stats["owned_activity"])),
        ("Other-org/repo activity", fmt(stats["other_activity"])),
        ("Restricted / unattributed", fmt(stats["restricted_activity"])),
    ]

    row_svg = []
    y = 108
    for label, value in rows:
        row_svg.append(
            f'<text x="36" y="{y}" class="label">{escape(label)}</text>'
            f'<text x="724" y="{y}" text-anchor="end" class="value">{escape(str(value))}</text>'
        )
        y += 30

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="760" height="520" viewBox="0 0 760 520" role="img" aria-label="{USERNAME} GitHub statistics">
<style>
  .title {{ font: 700 22px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {accent}; }}
  .subtitle {{ font: 13px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {muted}; }}
  .label {{ font: 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {fg}; }}
  .value {{ font: 700 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {accent}; }}
</style>
<rect x="1" y="1" width="758" height="518" rx="12" fill="{bg}" stroke="{border}" />
<text x="36" y="46" class="title">{USERNAME}@github</text>
<text x="36" y="70" class="subtitle">automatically refreshed from the GitHub API</text>
<line x1="36" y1="84" x2="724" y2="84" stroke="{border}" />
{"".join(row_svg)}
</svg>'''

def main():
    user = graphql(QUERY, {"login": USERNAME})["user"]
    repos = user["repositories"]["nodes"]
    created = datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    years = now.year - created.year - ((now.month, now.day) < (created.month, created.day))
    months = (now.month - created.month) % 12

    contributions = user["contributionsCollection"]
    grouped = (
        contributions["commitContributionsByRepository"]
        + contributions["issueContributionsByRepository"]
        + contributions["pullRequestContributionsByRepository"]
        + contributions["pullRequestReviewContributionsByRepository"]
    )
    owned_activity = sum(
        item["contributions"]["totalCount"] for item in grouped
        if item["repository"]["owner"]["login"].lower() == USERNAME.lower()
    )
    other_activity = sum(
        item["contributions"]["totalCount"] for item in grouped
        if item["repository"]["owner"]["login"].lower() != USERNAME.lower()
    )

    stats = {
        "account_age": f"{years}y {months}m",
        "repos": user["repositories"]["totalCount"],
        "contributed": user["repositoriesContributedTo"]["totalCount"],
        "stars": sum(repo["stargazerCount"] for repo in repos),
        "followers": user["followers"]["totalCount"],
        "commits_year": contributions["totalCommitContributions"],
        "contributions_year": contributions["contributionCalendar"]["totalContributions"],
        "prs_year": contributions["totalPullRequestContributions"],
        "issues_year": contributions["totalIssueContributions"],
        "reviews_year": contributions["totalPullRequestReviewContributions"],
        "owned_activity": owned_activity,
        "other_activity": other_activity,
        "restricted_activity": contributions["restrictedContributionsCount"],
    }

    for filename, dark in (("dark_mode.svg", True), ("light_mode.svg", False)):
        with open(filename, "w", encoding="utf-8") as handle:
            handle.write(generate_svg(stats, dark))

    print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    main()
