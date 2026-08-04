#!/usr/bin/env python3
"""Regenerates dark_mode.svg / light_mode.svg with live profile stats."""
import os
import re
import subprocess
import tempfile
import shutil
import datetime
from dateutil.relativedelta import relativedelta
import requests

USERNAME = os.environ.get("USER_NAME", "Harleywill")
ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
BIRTHDATE = datetime.date(2002, 11, 9)

HEADERS = {"Authorization": f"bearer {ACCESS_TOKEN}"}
GRAPHQL_URL = "https://api.github.com/graphql"


def graphql(query, variables=None):
    r = requests.post(GRAPHQL_URL, json={"query": query, "variables": variables or {}}, headers=HEADERS)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def uptime_string():
    rd = relativedelta(datetime.date.today(), BIRTHDATE)
    parts = []
    if rd.years:
        parts.append(f"{rd.years} year{'s' if rd.years != 1 else ''}")
    if rd.months:
        parts.append(f"{rd.months} month{'s' if rd.months != 1 else ''}")
    parts.append(f"{rd.days} day{'s' if rd.days != 1 else ''}")
    return ", ".join(parts)


def account_created_year():
    query = """
    query($login: String!) {
      user(login: $login) { createdAt }
    }
    """
    data = graphql(query, {"login": USERNAME})
    created = data["user"]["createdAt"]
    return int(created[:4])


def total_commits():
    start_year = account_created_year()
    this_year = datetime.date.today().year
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          restrictedContributionsCount
        }
      }
    }
    """
    total = 0
    for year in range(start_year, this_year + 1):
        frm = f"{year}-01-01T00:00:00Z"
        to = f"{year + 1}-01-01T00:00:00Z"
        cc = graphql(query, {"login": USERNAME, "from": frm, "to": to})["user"]["contributionsCollection"]
        total += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
    return total


def owned_repos():
    repos = []
    page = 1
    while True:
        r = requests.get(
            f"https://api.github.com/users/{USERNAME}/repos",
            params={"type": "owner", "per_page": 100, "page": page},
            headers=HEADERS,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        repos.extend(repo for repo in batch if not repo["fork"])
        page += 1
    return repos


def lines_of_code():
    add_total = 0
    del_total = 0
    workdir = tempfile.mkdtemp(prefix="loc_")
    try:
        for repo in owned_repos():
            if repo["size"] == 0:
                continue
            dest = os.path.join(workdir, repo["name"])
            clone_url = repo["clone_url"].replace(
                "https://", f"https://x-access-token:{ACCESS_TOKEN}@"
            )
            subprocess.run(
                ["git", "clone", "--quiet", "--single-branch", clone_url, dest],
                check=True,
            )
            result = subprocess.run(
                ["git", "-C", dest, "log", "--pretty=tformat:", "--numstat"],
                check=True,
                capture_output=True,
                text=True,
            )
            for line in result.stdout.splitlines():
                m = re.match(r"^(\d+)\s+(\d+)\s+", line)
                if m:
                    add_total += int(m.group(1))
                    del_total += int(m.group(2))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return add_total, del_total


def fmt(n):
    return f"{n:,}"


THEMES = {
    "dark": {
        "bg": "#161b22",
        "text": "#c9d1d9",
        "key": "#ffa657",
        "value": "#a5d6ff",
        "add": "#3fb950",
        "delete": "#f85149",
        "cc": "#616e7f",
    },
    "light": {
        "bg": "#f6f8fa",
        "text": "#24292f",
        "key": "#953800",
        "value": "#0a3069",
        "add": "#1a7f37",
        "delete": "#cf222e",
        "cc": "#c2cfde",
    },
}

WIDTH = 900
TARGET_COL = 42  # character column where values start
LINE_HEIGHT = 20
TOP = 30
LEFT = 15


def dots_for(key, indent=". "):
    prefix_len = len(indent) + len(key) + 1
    dots_needed = max(TARGET_COL - prefix_len, 3)
    return " " + "." * dots_needed + " "


def esc(s):
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_rows(stats):
    rows = []  # (kind, ...)
    rows.append(("header", "harley@williams"))
    rows.append(("kv", "OS", "macOS, Windows"))
    rows.append(("kv", "Uptime", stats["uptime"]))
    rows.append(("kv", "Host", "Home Lab (Self-Hosted VPS)"))
    rows.append(("kv", "Role", "Full-Stack Web Developer"))
    rows.append(("kv", "IDE", "VS Code, Claude Code"))
    rows.append(("blank",))
    rows.append(("kv", "Languages.Programming", "TypeScript, JavaScript, Python, Node.js"))
    rows.append(("kv", "Languages.Computer", "HTML, CSS, JSON, YAML, SQL"))
    rows.append(("kv", "Languages.Real", "English"))
    rows.append(("blank",))
    rows.append(("kv", "Hobbies.Music", "Playing guitar, music"))
    rows.append(("kv", "Hobbies.Tech", "Self-hosting, home-lab tinkering"))
    rows.append(("blank",))
    rows.append(("header", "Contact"))
    rows.append(("kv", "Email", "hjakewilliams@gmail.com"))
    rows.append(("kv", "LinkedIn", "harley-williams"))
    rows.append(("kv", "Website", "harleywilliams.co.uk"))
    rows.append(("blank",))
    rows.append(("header", "GitHub Stats"))
    rows.append(("kv", "Commits", fmt(stats["commits"])))
    rows.append((
        "loc",
        "Lines of Code on GitHub",
        fmt(stats["loc_net"]),
        fmt(stats["loc_add"]),
        fmt(stats["loc_del"]),
    ))
    return rows


def render_svg(theme_name, stats):
    theme = THEMES[theme_name]
    rows = build_rows(stats)
    height = TOP + LINE_HEIGHT * len(rows) + 20

    lines = []
    lines.append(f"<svg xmlns='http://www.w3.org/2000/svg' font-family=\"ConsolasFallback,Consolas,monospace\" width=\"{WIDTH}px\" height=\"{height}px\" font-size=\"16px\">")
    lines.append("<style>")
    lines.append("@font-face { src: local('Consolas'), local('Consolas Bold'); font-family: 'ConsolasFallback'; font-display: swap; -webkit-size-adjust: 109%; size-adjust: 109%; }")
    lines.append(f".key {{fill: {theme['key']};}}")
    lines.append(f".value {{fill: {theme['value']};}}")
    lines.append(f".addColor {{fill: {theme['add']};}}")
    lines.append(f".delColor {{fill: {theme['delete']};}}")
    lines.append(f".cc {{fill: {theme['cc']};}}")
    lines.append("text, tspan {white-space: pre;}")
    lines.append("</style>")
    lines.append(f"<rect width=\"{WIDTH}px\" height=\"{height}px\" fill=\"{theme['bg']}\" rx=\"15\"/>")
    lines.append(f"<text x=\"{LEFT}\" y=\"{TOP}\" fill=\"{theme['text']}\">")

    y = TOP
    dash = "-" + "—" * 47 + "-—-"
    for row in rows:
        if row[0] == "header":
            title = esc(row[1])
            prefix = title if y == TOP else f"- {title}"
            lines.append(f"<tspan x=\"{LEFT}\" y=\"{y}\">{prefix}</tspan> {dash}")
        elif row[0] == "blank":
            lines.append(f"<tspan x=\"{LEFT}\" y=\"{y}\" class=\"cc\">. </tspan>")
        elif row[0] == "kv":
            key, value = row[1], row[2]
            dots = dots_for(key)
            lines.append(
                f"<tspan x=\"{LEFT}\" y=\"{y}\" class=\"cc\">. </tspan>"
                f"<tspan class=\"key\">{esc(key)}</tspan>:"
                f"<tspan class=\"cc\">{esc(dots)}</tspan>"
                f"<tspan class=\"value\">{esc(value)}</tspan>"
            )
        elif row[0] == "loc":
            key, net, add, dele = row[1], row[2], row[3], row[4]
            dots = dots_for(key)
            lines.append(
                f"<tspan x=\"{LEFT}\" y=\"{y}\" class=\"cc\">. </tspan>"
                f"<tspan class=\"key\">{esc(key)}</tspan>:"
                f"<tspan class=\"cc\">{esc(dots)}</tspan>"
                f"<tspan class=\"value\">{esc(net)}</tspan> ( "
                f"<tspan class=\"addColor\">{esc(add)}</tspan><tspan class=\"addColor\">++</tspan>, "
                f"<tspan class=\"delColor\">{esc(dele)}</tspan><tspan class=\"delColor\">--</tspan> )"
            )
        y += LINE_HEIGHT
    lines.append("</text>")
    lines.append("</svg>")
    return "\n".join(lines)


def main():
    add, dele = lines_of_code()
    stats = {
        "uptime": uptime_string(),
        "commits": total_commits(),
        "loc_add": add,
        "loc_del": dele,
        "loc_net": add - dele,
    }
    with open("dark_mode.svg", "w") as f:
        f.write(render_svg("dark", stats) + "\n")
    with open("light_mode.svg", "w") as f:
        f.write(render_svg("light", stats) + "\n")


if __name__ == "__main__":
    main()
