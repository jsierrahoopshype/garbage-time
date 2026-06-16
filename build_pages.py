#!/usr/bin/env python3
"""
Pre-render static, indexable HTML for the HoopsMatic NBA garbage-time site.

Reads data/garbage_time_for_web.json (produced by an external pipeline — never
written to here) and emits, into the repo root:

  p/<slug>.html               one page per player, server-rendered tables
  p/index.html                A-Z player directory
  leaderboards/<board>-<season>.html
  leaderboards/index.html     leaderboard hub
  sitemap.xml                 every generated page (+ the SPA home)
  robots.txt                  points crawlers at the sitemap

Usage:  python3 build_pages.py
"""

import html
import json
import os
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data", "garbage_time_for_web.json")

BASE_URL = "https://jsierrahoopshype.github.io/garbage-time"

MIN_GAMES = 30
STAR_THRESHOLD = 20
TOP_N = 100

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700'
    '&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">'
)

BOARDS = {
    "stat-padders": "Stat-Padders",
    "biggest-droppers": "Biggest Droppers",
    "star-stat-padders": "Star Stat-Padders",
}
BOARD_BLURB = {
    "stat-padders": "Players ranked by the most garbage-time points accrued — pure stat-padding volume.",
    "biggest-droppers": "Players whose scoring falls the most once garbage time is removed (Δ = real PPG − official PPG).",
    "star-stat-padders": "Real rotation stars (%d+ official PPG) who still pad the most in garbage time." % STAR_THRESHOLD,
}

COUNT_STATS = [("pts", "PTS"), ("reb", "REB"), ("ast", "AST"), ("stl", "STL"),
               ("blk", "BLK"), ("tov", "TOV"), ("fg3m", "3PM")]


def esc(s):
    return html.escape(str(s), quote=True)


def headshot(pid):
    return "https://cdn.nba.com/headshots/nba/latest/260x190/%s.png" % pid


def bucket(o, key, b):
    if key == "efg":
        return (o["fgm"][b] + 0.5 * o["fg3m"][b]) / o["fga"][b] if o["fga"][b] else 0.0
    if key == "fgpct":
        return o["fgm"][b] / o["fga"][b] if o["fga"][b] else 0.0
    v = o.get(key)
    return v[b] if isinstance(v, list) else 0


def pg(total, gp):
    return total / gp if gp else 0.0


def fmt_total(total):
    return "{:,}".format(int(round(total)))


def fmt_pct(v):
    return "%.1f%%" % (v * 100)


def signed(n, digits=1):
    return ("%+." + str(digits) + "f") % n


def delta_cls(n):
    if n < -1e-9:
        return "neg"
    if n > 1e-9:
        return "pos"
    return "flat"


def season_label(season):
    return "Career" if season == "career" else season


def stat_obj(player, season):
    return player["career"] if season == "career" else player["seasons"].get(season)


def build_slug_map(players):
    counts = {}
    for p in players:
        counts[p["slug"]] = counts.get(p["slug"], 0) + 1
    dup = {s for s, n in counts.items() if n > 1}
    slug_of = {}
    for p in players:
        slug_of[p["id"]] = ("%s-%s" % (p["slug"], p["id"])) if p["slug"] in dup else p["slug"]
    return slug_of


def page_head(title, description, canonical_path, og_image=None, og_type="website"):
    canonical = BASE_URL + "/" + canonical_path
    img = og_image or (BASE_URL + "/")
    tags = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>%s</title>" % esc(title),
        '<meta name="description" content="%s">' % esc(description),
        '<link rel="canonical" href="%s">' % esc(canonical),
        '<meta property="og:type" content="%s">' % og_type,
        '<meta property="og:site_name" content="HoopsMatic">',
        '<meta property="og:title" content="%s">' % esc(title),
        '<meta property="og:description" content="%s">' % esc(description),
        '<meta property="og:url" content="%s">' % esc(canonical),
        '<meta property="og:image" content="%s">' % esc(img),
        '<meta name="twitter:card" content="summary">',
        FONTS,
        '<link rel="stylesheet" href="../styles.css">',
        "</head>",
        "<body>",
        '<div class="container">',
    ]
    return "\n".join(tags)


def page_foot(updated):
    stamp = (" · updated " + esc(updated)) if updated else ""
    return (
        '<div class="foot">HoopsMatic · Garbage-time splits derived from play-by-play. '
        '"Real" numbers exclude garbage-time stretches; "official" match the box score.'
        + stamp + "</div>\n</div>\n</body>\n</html>\n"
    )


def board_tabs(active_board, season):
    out = ['<div class="chips">']
    for key, label in BOARDS.items():
        cls = "chip active" if key == active_board else "chip"
        out.append('<a class="%s" href="%s-%s.html">%s</a>' % (cls, key, season, esc(label)))
    out.append("</div>")
    return "".join(out)


def season_tabs(board, seasons, active_season):
    chips = ['<a class="chip%s" href="%s-career.html">Career</a>'
             % (" active" if active_season == "career" else "", board)]
    for s in seasons:
        cls = " active" if s == active_season else ""
        chips.append('<a class="chip%s" href="%s-%s.html">%s</a>' % (cls, board, s, esc(s)))
    return '<div class="chips" style="margin:.6rem 0 1rem">' + "".join(chips) + "</div>"


def render_player(player, slug, updated):
    name = player["name"]
    car = player["career"]
    gp = car["gp"]
    off_ppg = pg(car["pts"][0], gp)
    real_ppg = pg(car["pts"][1], gp)
    gar_pts = car["pts"][2]
    d_ppg = real_ppg - off_ppg
    seasons = sorted(player["seasons"].keys(), reverse=True)

    title = "%s Garbage-Time Stats | HoopsMatic" % name
    desc = ("%s's real vs official production once garbage time is stripped out: "
            "career %.1f real PPG vs %.1f official (%s), %s garbage points over %d games."
            % (name, real_ppg, off_ppg, signed(d_ppg), fmt_total(gar_pts), gp))

    head = page_head(title, desc, "p/%s.html" % slug, og_image=headshot(player["id"]),
                     og_type="profile")

    parts = [head]
    parts.append('<a class="back" href="../index.html">← HoopsMatic Garbage Time</a>')
    parts.append('<div class="ehead">')
    parts.append('<img class="eimg" src="%s" alt="%s" '
                 'onerror="this.onerror=null;this.style.visibility=\'hidden\'">'
                 % (headshot(player["id"]), esc(name)))
    parts.append('<div><h1>%s</h1><div class="esub">Garbage-time splits · '
                 '%d season%s · %d career GP</div></div>'
                 % (esc(name), len(seasons), "" if len(seasons) == 1 else "s", gp))
    parts.append("</div>")

    parts.append('<div class="stat-cards">')
    parts.append('<div class="stat-card"><div class="lbl">Official PPG</div>'
                 '<div class="num flat">%.1f</div><div class="sub">as in the box score</div></div>' % off_ppg)
    parts.append('<div class="stat-card"><div class="lbl">Real PPG</div>'
                 '<div class="num flat">%.1f</div><div class="sub">garbage time removed</div></div>' % real_ppg)
    parts.append('<div class="stat-card"><div class="lbl">Δ PPG (real − official)</div>'
                 '<div class="num %s">%s</div><div class="sub">%s garbage points</div></div>'
                 % (delta_cls(d_ppg), signed(d_ppg), fmt_total(gar_pts)))
    parts.append("</div>")

    parts.append('<div class="section">')
    parts.append('<div class="section-head"><h2>Scoring by season — per game</h2></div>')
    parts.append('<div class="table-wrap"><table class="lb"><thead><tr>'
                 '<th class="left">Season</th><th>GP</th><th>Official PPG</th>'
                 '<th>Real PPG</th><th>Garbage PPG</th><th class="dcol">Δ PPG</th>'
                 '</tr></thead><tbody>')

    def scoring_row(label, o, career=False):
        o_off = pg(o["pts"][0], o["gp"])
        o_real = pg(o["pts"][1], o["gp"])
        o_gar = pg(o["pts"][2], o["gp"])
        d = o_real - o_off
        cls = " career-row" if career else ""
        return ('<tr class="%s"><td class="left">%s</td><td>%d</td><td>%.1f</td>'
                '<td>%.1f</td><td>%.1f</td><td class="dcol delta %s">%s</td></tr>'
                % (cls.strip(), esc(label), o["gp"], o_off, o_real, o_gar, delta_cls(d), signed(d)))

    for s in seasons:
        parts.append(scoring_row(s, player["seasons"][s]))
    parts.append(scoring_row("Career", car, career=True))
    parts.append("</tbody></table></div></div>")

    parts.append('<div class="section">')
    parts.append('<div class="section-head"><h2>Career splits — per game</h2></div>')
    parts.append('<div class="hint">Official = real + garbage. Δ is real minus official '
                 '(negative means production padded in garbage time).</div>')
    parts.append('<div class="table-wrap"><table class="lb"><thead><tr>'
                 '<th class="left">Stat</th><th>Official</th><th>Real</th>'
                 '<th>Garbage</th><th class="dcol">Δ</th></tr></thead><tbody>')
    for key, label in COUNT_STATS:
        o_off = pg(car[key][0], gp)
        o_real = pg(car[key][1], gp)
        o_gar = pg(car[key][2], gp)
        d = o_real - o_off
        parts.append('<tr><td class="left">%s</td><td>%.1f</td><td>%.1f</td>'
                     '<td>%.1f</td><td class="dcol delta %s">%s</td></tr>'
                     % (label, o_off, o_real, o_gar, delta_cls(d), signed(d)))
    e_off = bucket(car, "efg", 0)
    e_real = bucket(car, "efg", 1)
    e_gar = bucket(car, "efg", 2)
    de = (e_real - e_off) * 100
    parts.append('<tr><td class="left">eFG%%</td><td>%s</td><td>%s</td><td>%s</td>'
                 '<td class="dcol delta %s">%s pp</td></tr>'
                 % (fmt_pct(e_off), fmt_pct(e_real), fmt_pct(e_gar), delta_cls(de), signed(de)))
    parts.append("</tbody></table></div></div>")

    parts.append('<p style="margin:.2rem 0 1rem"><a class="chip" href="../index.html?player=%s">'
                 'Explore interactively →</a></p>' % esc(slug))

    parts.append(page_foot(updated))
    return "\n".join(parts)


def leaderboard_rows(players, season):
    rows = []
    for p in players:
        o = stat_obj(p, season)
        if not o or o["gp"] < MIN_GAMES:
            continue
        gp = o["gp"]
        rows.append({
            "p": p, "gp": gp,
            "off_ppg": pg(o["pts"][0], gp),
            "real_ppg": pg(o["pts"][1], gp),
            "gar_pts": o["pts"][2],
            "off_pts": o["pts"][0],
        })
    for r in rows:
        r["d_ppg"] = r["real_ppg"] - r["off_ppg"]
        r["gar_share"] = (r["gar_pts"] / r["off_pts"] * 100) if r["off_pts"] else 0.0
    return rows


def render_leaderboard(board, season, players, slug_of, seasons, updated):
    rows = leaderboard_rows(players, season)
    if board == "biggest-droppers":
        rows.sort(key=lambda r: r["d_ppg"])
        rows = rows[:TOP_N]
    else:
        if board == "star-stat-padders":
            rows = [r for r in rows if r["off_ppg"] >= STAR_THRESHOLD]
        rows.sort(key=lambda r: r["gar_pts"], reverse=True)
        rows = rows[:TOP_N]

    if board == "biggest-droppers":
        cols = [
            ("GP", False, lambda r: "%d" % r["gp"]),
            ("Official PPG", False, lambda r: "%.1f" % r["off_ppg"]),
            ("Real PPG", False, lambda r: "%.1f" % r["real_ppg"]),
            ("Δ PPG", True, lambda r: ('<span class="delta %s">%s</span>'
                                       % (delta_cls(r["d_ppg"]), signed(r["d_ppg"])))),
        ]
    else:
        cols = [
            ("GP", False, lambda r: "%d" % r["gp"]),
            ("Official PPG", False, lambda r: "%.1f" % r["off_ppg"]),
            ("Garbage PTS", True, lambda r: fmt_total(r["gar_pts"])),
            ("Garbage % of pts", False, lambda r: "%.0f%%" % r["gar_share"]),
        ]

    slabel = season_label(season)
    btitle = BOARDS[board]
    title = "NBA Garbage-Time %s — %s | HoopsMatic" % (btitle, slabel)

    if rows:
        lead = rows[0]["p"]["name"]
        if board == "biggest-droppers":
            desc = ("NBA players whose scoring drops most once garbage time is removed, %s. "
                    "%s leads at %s real-minus-official PPG. Min %d games."
                    % (slabel, lead, signed(rows[0]["d_ppg"]), MIN_GAMES))
        elif board == "star-stat-padders":
            desc = ("NBA stars (%d+ official PPG) padding the most in garbage time, %s. "
                    "%s tops it with %s garbage points. Min %d games."
                    % (STAR_THRESHOLD, slabel, lead, fmt_total(rows[0]["gar_pts"]), MIN_GAMES))
        else:
            desc = ("NBA stat-padders by total garbage-time points, %s. "
                    "%s leads with %s garbage points. Min %d games."
                    % (slabel, lead, fmt_total(rows[0]["gar_pts"]), MIN_GAMES))
    else:
        desc = ("NBA garbage-time %s leaderboard, %s. Min %d games."
                % (btitle.lower(), slabel, MIN_GAMES))

    head = page_head(title, desc, "leaderboards/%s-%s.html" % (board, season))
    parts = [head]
    parts.append('<a class="back" href="../index.html">← HoopsMatic Garbage Time</a>')
    parts.append('<div class="hdr"><h1>%s · %s</h1><span class="brand">HoopsMatic</span></div>'
                 % (esc(btitle), esc(slabel)))

    note = "Minimum %d games." % MIN_GAMES
    if board == "star-stat-padders":
        note = "Minimum %d games · %d+ official PPG." % (MIN_GAMES, STAR_THRESHOLD)
    parts.append('<div class="subtitle">%s %s</div>' % (esc(BOARD_BLURB[board]), esc(note)))

    parts.append(board_tabs(board, season))
    parts.append(season_tabs(board, seasons, season))

    th = ['<th class="rank">#</th><th class="left">Player</th>']
    for header, is_d, _ in cols:
        th.append('<th class="%s">%s</th>' % ("dcol" if is_d else "", esc(header)))
    parts.append('<div class="table-wrap"><table class="lb"><thead><tr>'
                 + "".join(th) + "</tr></thead><tbody>")

    ncols = len(cols) + 2
    if not rows:
        parts.append('<tr><td colspan="%d" class="empty">No players meet the filters '
                     'for %s.</td></tr>' % (ncols, esc(slabel)))
    else:
        for i, r in enumerate(rows, 1):
            p = r["p"]
            pslug = slug_of[p["id"]]
            namecell = ('<td class="left"><span class="pcell">'
                        '<img src="%s" alt="" onerror="this.onerror=null;this.style.visibility=\'hidden\'">'
                        '<a href="../p/%s.html">%s</a></span></td>'
                        % (headshot(p["id"]), pslug, esc(p["name"])))
            cells = "".join('<td class="%s">%s</td>' % ("dcol" if is_d else "", fn(r))
                            for _, is_d, fn in cols)
            parts.append('<tr><td class="rank">%d</td>%s%s</tr>' % (i, namecell, cells))
    parts.append("</tbody></table></div>")
    parts.append(page_foot(updated))
    return "\n".join(parts)


def render_players_index(players, slug_of, updated):
    title = "All NBA Players — Garbage-Time Stats | HoopsMatic"
    desc = ("Browse garbage-time real-vs-official stats for every NBA player, %d in all, "
            "seasons 2016-17 through 2025-26." % len(players))
    head = page_head(title, desc, "p/index.html")
    parts = [head]
    parts.append('<a class="back" href="../index.html">← HoopsMatic Garbage Time</a>')
    parts.append('<div class="hdr"><h1>All Players</h1><span class="brand">HoopsMatic</span></div>')
    parts.append('<div class="subtitle">%d players · click any name for their garbage-time splits.</div>'
                 % len(players))

    ordered = sorted(players, key=lambda p: p["name"].lower())
    groups = {}
    for p in ordered:
        letter = p["name"].strip()[:1].upper()
        if not letter.isalpha():
            letter = "#"
        groups.setdefault(letter, []).append(p)

    for letter in sorted(groups.keys()):
        parts.append('<div class="dir-letter">%s</div>' % esc(letter))
        parts.append('<div class="egrid">')
        for p in groups[letter]:
            car = p["career"]
            off = pg(car["pts"][0], car["gp"])
            parts.append('<a class="ecard" href="%s.html">'
                         '<img src="%s" alt="" onerror="this.onerror=null;this.style.visibility=\'hidden\'">'
                         '<span class="en">%s</span><span class="ec">%.1f PPG</span></a>'
                         % (slug_of[p["id"]], headshot(p["id"]), esc(p["name"]), off))
        parts.append("</div>")
    parts.append(page_foot(updated))
    return "\n".join(parts)


def render_leaderboards_index(seasons, updated):
    title = "NBA Garbage-Time Leaderboards | HoopsMatic"
    desc = ("Garbage-time leaderboards: biggest NBA stat-padders, biggest droppers, and "
            "star stat-padders — career and every season from 2016-17 to 2025-26.")
    head = page_head(title, desc, "leaderboards/index.html")
    parts = [head]
    parts.append('<a class="back" href="../index.html">← HoopsMatic Garbage Time</a>')
    parts.append('<div class="hdr"><h1>Leaderboards</h1><span class="brand">HoopsMatic</span></div>')
    parts.append('<div class="subtitle">Career and per-season boards. Minimum %d games.</div>' % MIN_GAMES)
    for board, label in BOARDS.items():
        parts.append('<div class="section">')
        parts.append('<div class="section-head"><h2>%s</h2></div>' % esc(label))
        parts.append('<div class="hint">%s</div>' % esc(BOARD_BLURB[board]))
        chips = ['<a class="chip" href="%s-career.html">Career</a>' % board]
        for s in seasons:
            chips.append('<a class="chip" href="%s-%s.html">%s</a>' % (board, s, esc(s)))
        parts.append('<div class="chips">' + "".join(chips) + "</div>")
        parts.append("</div>")
    parts.append(page_foot(updated))
    return "\n".join(parts)


def write_sitemap(urls, lastmod):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        lines.append("  <url><loc>%s</loc><lastmod>%s</lastmod></url>" % (esc(u), lastmod))
    lines.append("</urlset>\n")
    with open(os.path.join(HERE, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_robots():
    body = "User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % BASE_URL
    with open(os.path.join(HERE, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(body)


def write(path, content):
    full = os.path.join(HERE, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    players = [p for p in data["players"] if (p.get("name") or "").strip()]
    seasons = sorted(data.get("seasons", []), reverse=True)
    updated = data.get("updated", "")
    lastmod = updated if updated else date.today().isoformat()
    try:
        lastmod = datetime.fromisoformat(lastmod.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        lastmod = date.today().isoformat()

    slug_of = build_slug_map(players)

    urls = [BASE_URL + "/", BASE_URL + "/p/index.html", BASE_URL + "/leaderboards/index.html"]

    for p in players:
        slug = slug_of[p["id"]]
        write("p/%s.html" % slug, render_player(p, slug, updated))
        urls.append("%s/p/%s.html" % (BASE_URL, slug))
    write("p/index.html", render_players_index(players, slug_of, updated))

    season_keys = ["career"] + seasons
    for board in BOARDS:
        for season in season_keys:
            write("leaderboards/%s-%s.html" % (board, season),
                  render_leaderboard(board, season, players, slug_of, seasons, updated))
            urls.append("%s/leaderboards/%s-%s.html" % (BASE_URL, board, season))
    write("leaderboards/index.html", render_leaderboards_index(seasons, updated))

    write_sitemap(urls, lastmod)
    write_robots()

    print("Generated %d player pages, %d leaderboard pages, sitemap (%d urls), robots.txt"
          % (len(players), len(BOARDS) * len(season_keys), len(urls)))


if __name__ == "__main__":
    main()
